from pathlib import Path
from threading import Lock
from uuid import uuid4
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, StateSnapshot
from agent_learning.core.errors import ServiceError
from agent_learning.core.models import SearchFilter
from agent_learning.rag.answering import RAGPipeline
from agent_learning.workflows import approval_demo, pause_demo
from agent_learning.workflows.diagnosis_agent import build_graph
from agent_learning.workflows.tool_model import CompatibleToolModel


# 管理当前进程内的会话，负责把 HTTP 操作转换成图调用。
class AgentService:
    # 模型、RAG、身份和业务文件由启动代码显式提供。
    def __init__(
        self,
        model: CompatibleToolModel,
        pipeline: RAGPipeline,
        filters: SearchFilter,
        data_file: Path,
    ) -> None:
        # 不同会话使用不同编号隔离状态。
        self.sessions: dict[str, dict] = {}
        # 保护创建会话时对字典的修改。
        self.sessions_lock = Lock()
        # 保存可信身份，不从问题中提取。
        self.tenant_id = filters.tenant_id
        # 内存存档重启后丢失，不创建数据库表。
        checkpointer = InMemorySaver()
        # 普通图连续运行，只在需要人工审批时暂停。
        self.normal_graph: CompiledStateGraph = build_graph(model, pipeline, filters, checkpointer, data_file)
        # 暂停图用于演示第 65 课的工具前 Checkpoint。
        self.paused_graph: CompiledStateGraph = build_graph(
            model, pipeline, filters, checkpointer, data_file, pause_before_tools=True,
        )
        # 最简图也使用现有存档器，由独立会话编号隔离状态。
        self.pause_demo_graph: CompiledStateGraph = pause_demo.build_graph(checkpointer)
        # 审批演示只使用固定图，不经过模型选择工具。
        self.approval_demo_graph: CompiledStateGraph = approval_demo.build_graph(checkpointer)

    # 创建新会话，对应原来的 /new。
    def create_session(
        self,
        pause_before_tools: bool = False,
        graph: CompiledStateGraph | None = None,
    ) -> dict:
        # 编号只用于找到会话，不记录追踪链路。
        session_id = uuid4().hex
        # 内部演示可以指定固定图，普通 API 仍按原来的开关选择。
        if graph is None:
            # 默认使用综合诊断图。
            graph = self.normal_graph
            # 明确要求工具前暂停时才使用暂停图。
            if pause_before_tools:
                # 保留原会话接口的行为。
                graph = self.paused_graph
        # 会话只保存图引用、配置和串行访问锁。
        session = {
            "graph": graph,
            "config": {"configurable": {"thread_id": session_id}},
            "lock": Lock(),
        }
        # 创建期间不修改其他会话的内容。
        with self.sessions_lock:
            # 保存本次会话。
            self.sessions[session_id] = session
        # 会话尚未调用模型。
        return {"session_id": session_id, "status": "ready"}

    # 演示接口内部创建会话，用户只需调用开始和恢复两个接口。
    def start_pause_demo(self, question: str) -> dict:
        # ID、配置和锁仍由现有 create_session 生成。
        created = self.create_session(graph=self.pause_demo_graph)
        # 复用现有提问流程，固定图执行第一步后暂停。
        return self.ask(created["session_id"], question)

    # 直接申请模拟取消，方便演示现有 approvals 接口。
    def start_approval_demo(self, order_id: str) -> dict:
        # 会话编号仍由统一的 create_session 生成。
        created = self.create_session(graph=self.approval_demo_graph)
        # 固定图整理订单号后，直接进入人工审批。
        return self.ask(created["session_id"], order_id)

    # 演示恢复只接受演示会话，避免误传普通 Agent 编号后调用模型。
    def resume_pause_demo(self, session_id: str) -> dict:
        # 只读取现有会话，不生成新编号。
        with self.sessions_lock:
            # 编号来自第一个演示接口。
            session = self.sessions.get(session_id)
        # 服务重启或编号错误时不能恢复。
        if session is None:
            # 返回与其他会话接口一致的不存在说明。
            raise ServiceError(404, "会话不存在，请先创建会话。")
        # 普通 Agent 会话不能走这个演示入口。
        if session["graph"] is not self.pause_demo_graph:
            # 保证这个演示不会触发模型或业务工具。
            raise ServiceError(409, "请使用暂停演示接口返回的 session_id。")
        # 复用原恢复方法的锁、进度检查和 invoke(None)。
        return self.resume(session_id)

    # 取得指定会话，并禁止同一会话并发修改。
    def lock_session(self, session_id: str) -> dict:
        # 创建会话字典受同一把锁保护。
        with self.sessions_lock:
            # 不自动创建客户端随意填写的编号。
            session = self.sessions.get(session_id)
        # 未找到时明确返回不存在。
        if session is None:
            # 服务重启后的旧会话也会进入此分支。
            raise ServiceError(404, "会话不存在，请先创建会话。")
        # 同一会话正在处理另一个请求时，直接提示冲突。
        if not session["lock"].acquire(blocking=False):
            # 不并发覆盖消息或审批请求。
            raise ServiceError(409, "会话正在处理请求，请稍后再试。")
        # 调用方必须在 finally 中释放锁。
        return session

    # 将图状态转换成业务响应，不把整份 State 暴露给 API。
    def response(self, session_id: str, snapshot: StateSnapshot) -> dict:
        # 读取当前已保存的状态。
        state = snapshot.values
        # 未执行过问题时会话处于就绪状态。
        status = "ready"
        # 默认没有待审批操作。
        approval = None
        # 有待执行节点表示尚未完成。
        if snapshot.next:
            # 工具前暂停或失败后可恢复都可以继续执行。
            status = "paused"
            # 人工审批有独立的业务请求。
            request = state.get("approval_request", {})
            # 仅在确实停在审批节点时返回待审批目标。
            if "approval" in snapshot.next and request:
                # 客户端必须调用审批接口，而不是普通恢复。
                status = "waiting_approval"
                # 只返回人工需要确认的业务字段。
                approval = {
                    "approval_id": request["approval_id"],
                    "action": request["action"],
                    "order_id": request["order_id"],
                    "mode": request["mode"],
                }
        # 没有待执行节点且已有本轮结果时，检查业务结束原因。
        elif state:
            # 正常回答和明确拒绝都属于已完成的业务决定。
            status = "completed"
            # 其他受控结束属于业务失败。
            if state.get("stop_reason") not in ("final_answer", "approval_rejected"):
                # 不暴露内部失败事件或异常原文。
                status = "failed"
        # 多次知识库调用的引用按问题分别保留。
        citations = []
        # 这里只读取真正取得的业务结果。
        for item in state.get("tool_results", []):
            # 普通业务查询没有规则引用。
            if item["tool_name"] != "ask_knowledge_base":
                # 跳过订单、支付和退款记录。
                continue
            # 工具失败时没有知识库答案。
            result = item["result"]
            # 失败或未执行的请求不伪造来源。
            if not result["success"]:
                # 继续检查其他已完成的规则查询。
                continue
            # 每组来源对应它自己的规则问题和引用编号。
            data = result["data"]
            # 不将不同 RAG 调用的同号引用混成一组。
            citations.append({
                "question": data["question"],
                "citations": data["citations"],
            })
        # 只返回会话标识、业务结果和人工待办。
        return {
            "session_id": session_id,
            "status": status,
            "answer": state.get("answer", ""),
            "citations": citations,
            "approval": approval,
        }

    # 提交一个新问题；相同会话保留历史。
    def ask(self, session_id: str, question: str) -> dict:
        # 请求结束前独占这个会话。
        session = self.lock_session(session_id)
        # 无论执行成功、失败或暂停都要释放锁。
        try:
            # 从普通会话字典中明确取出图类型，便于补全 invoke / get_state。
            graph: CompiledStateGraph = session["graph"]
            # config 使用 LangGraph 已有的配置类型。
            config: RunnableConfig = session["config"]
            # 取得当前执行进度。
            snapshot = graph.get_state(config)
            # 暂停或待审批时不接受新问题覆盖原任务。
            if snapshot.next:
                # 客户端需要先恢复或审批。
                raise ServiceError(409, "当前问题尚未完成，请先恢复执行或处理审批。")
            # 只提交新问题与服务端身份。
            graph.invoke(
                {"question": question, "tenant_id": self.tenant_id},
                config=config,
            )
            # 从同一 Checkpoint 读取完成或暂停后的结果。
            snapshot = graph.get_state(config)
            # 返回经过挑选的业务字段。
            return self.response(session_id, snapshot)
        # 异常也不能让会话永远保持占用。
        finally:
            # 本次请求结束后允许其他请求访问。
            session["lock"].release()

    # 查看对话和当前待办，不返回模型提示词或原始 Tool 消息。
    def get_session(self, session_id: str) -> dict:
        # 读取时也避免与当前写入交错。
        session = self.lock_session(session_id)
        # 保证读取后释放锁。
        try:
            # 字典本身不说明值的类型，在调用边界明确图类型。
            graph: CompiledStateGraph = session["graph"]
            # 保留同一会话的运行配置。
            config: RunnableConfig = session["config"]
            # 使用原会话配置定位状态。
            snapshot = graph.get_state(config)
            # 先整理当前业务结果。
            result = self.response(session_id, snapshot)
            # 只挑出用户与最终回答。
            messages = []
            # 原始工具协议仍留在内部。
            for message in snapshot.values.get("messages", []):
                # system 和 tool 都不作为对话展示。
                if message["role"] not in ("user", "assistant"):
                    # 继续检查下一条消息。
                    continue
                # 发起工具调用的中间 assistant 也不展示。
                if message.get("tool_calls"):
                    # API 只显示面向用户的对话。
                    continue
                # 不返回 reasoning_content 等内部协议字段。
                messages.append({"role": message["role"], "content": message.get("content", "")})
            # 返回现有会话中保留的完整轮次。
            result["messages"] = messages
            # 不附带消息数量等统计。
            return result
        # 读取失败也释放锁。
        finally:
            # 结束本次访问。
            session["lock"].release()

    # 继续普通暂停或失败后仍有待执行节点的任务。
    def resume(self, session_id: str) -> dict:
        # 不允许同会话并发恢复。
        session = self.lock_session(session_id)
        # 始终释放会话锁。
        try:
            # 字典本身不说明值的类型，在调用边界明确图类型。
            graph: CompiledStateGraph = session["graph"]
            # 保留同一会话的运行配置。
            config: RunnableConfig = session["config"]
            # 检查待执行位置。
            snapshot = graph.get_state(config)
            # 已结束的任务不能再次恢复。
            if not snapshot.next:
                # 不把恢复当作重新提交问题。
                raise ServiceError(409, "没有可恢复的执行。")
            # 人工审批不能被普通恢复绕过。
            if "approval" in snapshot.next and snapshot.values.get("approval_request"):
                # 明确要求提交决定。
                raise ServiceError(409, "当前正在等待人工审批，请调用审批接口。")
            # None 表示继续原状态，不重新执行准备节点。
            graph.invoke(None, config=config)
            # 读取继续后的结果。
            snapshot = graph.get_state(config)
            # 可能继续暂停，也可能已经完成。
            return self.response(session_id, snapshot)
        # 失败后仍保留 Checkpoint，调用方可查看当前待办。
        finally:
            # 避免会话锁泄漏。
            session["lock"].release()

    # 只审批服务端当前保存的请求，客户端不能更换订单或租户。
    def approve(self, session_id: str, approval_id: str, decision: str) -> dict:
        # 同一审批只能串行提交。
        session = self.lock_session(session_id)
        # 任何分支都要释放锁。
        try:
            # 字典本身不说明值的类型，在调用边界明确图类型。
            graph: CompiledStateGraph = session["graph"]
            # 保留同一会话的运行配置。
            config: RunnableConfig = session["config"]
            # 读取当前真正暂停的目标。
            snapshot = graph.get_state(config)
            # 目标请求由图中的准备节点生成。
            request = snapshot.values.get("approval_request", {})
            # 没有待审批节点时不能提交决定。
            if "approval" not in snapshot.next or not request:
                # 重复提交已完成的决定也会被拒绝。
                raise ServiceError(409, "当前没有待审批操作。")
            # 旧编号或其他会话的编号不能用于当前请求。
            if request["approval_id"] != approval_id:
                # 不执行任何模拟动作。
                raise ServiceError(409, "审批编号与当前待审批操作不一致。")
            # 服务层也检查明确的批准或拒绝。
            if decision not in ("approve", "reject"):
                # 不默认批准空值或其他文字。
                raise ServiceError(400, "decision 只能是 approve 或 reject。")
            # 复制真实请求，保留订单、租户和工具调用绑定。
            value = dict(request)
            # 只补入人工决定。
            value["decision"] = decision
            # 恢复同一个图和会话，不重新获得执行机会。
            graph.invoke(Command(resume=value), config=config)
            # 读取恢复后的业务结果。
            snapshot = graph.get_state(config)
            # 后面还有其他审批时会返回新的待办。
            return self.response(session_id, snapshot)
        # 审批失败也要释放锁。
        finally:
            # 保持后续会话可访问。
            session["lock"].release()
