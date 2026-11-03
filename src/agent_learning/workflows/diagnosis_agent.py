import json
from pathlib import Path
from uuid import uuid4
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from agent_learning.business.tools import DEFAULT_DATA_FILE, get_order, get_payment, get_refund, tool_result
from agent_learning.core.models import SearchFilter
from agent_learning.rag.answering import RAGPipeline
from agent_learning.workflows.agent_loop import validate_model_message
from agent_learning.workflows.human_approval_agent import APPROVAL_PROMPT, TOOL_SCHEMAS, simulate_cancel_order, validate_approval
from agent_learning.workflows.memory_agent import context_size, prepare_memory_node, trim_messages
from agent_learning.workflows.rag_agent import AgentState
from agent_learning.workflows.recovery_agent import is_temporary_error
from agent_learning.workflows.tool_model import CompatibleToolModel


# 综合诊断只补充工具选择规则，订单事实仍由业务 Tool 提供。
DIAGNOSIS_PROMPT = (
    "完整诊断先查订单，再根据结果查询支付、退款，必要时查规则。"
    "订单不存在、未支付或没有退款记录时及时说明，不猜测未查询的事实。"
    "已有信息足够时回答，不重复调用工具。人工拒绝后停止。"
)


# 会话只保存业务消息、待执行操作和维持流程所需的控制字段。
class DiagnosisState(AgentState):
    # 剩余次数用于防止无限调用，不作为统计结果返回。
    remaining_steps: int
    # 限制一轮问题中的工具执行次数。
    remaining_tools: int
    # 同一会话已成功模拟取消的订单。
    simulated_cancellations: list
    # 保存当前待审批的具体操作。
    approval_request: dict
    # 保存人工提交的决定。
    approval_decision: dict


# 复制当前节点会修改的列表，避免改写之前的 Checkpoint。
def copy_state(state: DiagnosisState) -> dict:
    # 先复制外层字典。
    current = dict(state)
    # 再复制需要追加内容的列表。
    for name in ("messages", "pending_tool_calls", "tool_results", "simulated_cancellations"):
        # 不修改旧列表本身。
        current[name] = list(state.get(name, []))
    # 返回当前节点的状态副本。
    return current


# 完成队首 Tool，保存业务结果并配齐模型协议消息。
def complete_call(current: dict, result: dict) -> None:
    # 每次只处理一个工具，执行后即可保存进度。
    call = current["pending_tool_calls"][0]
    # 工具结果使用原始调用 ID 回传给模型。
    current["messages"].append({
        "role": "tool",
        "tool_call_id": call["id"],
        "content": json.dumps(result, ensure_ascii=False),
    })
    # 业务结果保留在 State 中，供回答和引用使用。
    current["tool_results"].append({
        "tool_name": call["function"]["name"],
        "result": result,
    })
    # 已处理的请求从队列移除，恢复时不再执行。
    current["pending_tool_calls"] = current["pending_tool_calls"][1:]


# 模型只能提供工具规定的一个业务参数。
def parse_argument(arguments: str, field: str) -> str:
    # JSON 损坏时由调用节点统一处理失败。
    parsed = json.loads(arguments)
    # 参数必须是字典。
    if not isinstance(parsed, dict):
        # 不接受列表或标量。
        raise ValueError("工具参数必须是对象。")
    # 不允许额外的租户、权限或审批字段。
    if set(parsed) != {field}:
        # 字段必须与工具约定完全一致。
        raise ValueError("工具参数字段无效。")
    # 取出实际业务参数。
    value = parsed[field]
    # 业务参数必须是非空文字。
    if not isinstance(value, str) or not value.strip():
        # 不发送空问题或空订单号。
        raise ValueError("工具参数不能为空。")
    # 返回清理后的参数。
    return value.strip()


# 只读 Tool 使用明确分支分发，不执行模型提供的任意函数。
def dispatch_tool(
    call: dict,
    tenant_id: str,
    pipeline: RAGPipeline,
    filters: SearchFilter,
    data_file: Path,
) -> dict:
    # 读取工具名和 JSON 参数。
    function = call["function"]
    # 知识库只接收规则问题。
    if function["name"] == "ask_knowledge_base":
        # 租户和权限仍使用服务端传入的 filters。
        question = parse_argument(function["arguments"], "question")
        # 直接复用 RAG 问答方法。
        data = dict(pipeline.ask(question, filters))
        # 保存规则问题，多个 RAG 调用的引用可以分别展示。
        data["question"] = question
        # 资料不足也是已完成的业务查询。
        return tool_result(True, data=data)
    # 业务查询只接受订单号。
    order_id = parse_argument(function["arguments"], "order_id")
    # 明确分发订单查询。
    if function["name"] == "get_order":
        # 身份和文件路径不由模型提供。
        return get_order(order_id, tenant_id, data_file)
    # 支付查询返回全部匹配记录。
    if function["name"] == "get_payment":
        # 不发起支付。
        return get_payment(order_id, tenant_id, data_file)
    # 退款查询返回全部匹配记录。
    if function["name"] == "get_refund":
        # 不发起退款。
        return get_refund(order_id, tenant_id, data_file)
    # 取消订单只能进入人工审批分支。
    return tool_result(False, error="未知工具或工具不允许从查询节点执行。")


# 按当前业务状态选择下一步，不依赖进入节点的次数。
def choose_route(state: DiagnosisState) -> str:
    # 已有结束原因就统一收尾。
    if state["stop_reason"]:
        # 不再调用模型解释错误。
        return "finish"
    # 没有待执行工具时回到模型。
    if not state["pending_tool_calls"]:
        # 模型可以总结已有结果。
        return "model"
    # 取出队首请求。
    call = state["pending_tool_calls"][0]
    # 取消订单先准备人工审批。
    if call["function"]["name"] == "cancel_order":
        # 普通工具不会进入此分支。
        return "prepare_approval"
    # 其他请求进入只读工具节点。
    return "tools"


# 编排已有核心能力，不记录节点、Tool、Token、费用或耗时事件。
def build_graph(
    model: CompatibleToolModel,
    pipeline: RAGPipeline,
    filters: SearchFilter,
    checkpointer: InMemorySaver,
    data_file: Path = DEFAULT_DATA_FILE,
    max_steps: int = 10,
    max_tool_calls: int = 12,
    max_retries: int = 1,
    max_history_turns: int = 2,
    max_context_chars: int = 12000,
    pause_before_tools: bool = False,
) -> CompiledStateGraph:
    # RAG 只能查询规则资料，不能用订单快照代替业务事实。
    if filters.doc_type not in ("policy", "process", "faq"):
        # 参数由可信服务端配置。
        raise ValueError("Agent 只允许查询 policy、process、faq 资料。")
    # 检查执行上限。
    for value in (max_steps, max_tool_calls, max_context_chars):
        # bool 不能当作次数或字符预算。
        if type(value) is not int or value < 1:
            # 无效配置不进入模型调用。
            raise ValueError("执行次数和上下文字符上限必须是正整数。")
    # 检查允许为零的参数。
    for value in (max_retries, max_history_turns):
        # 零次重试和零轮历史都有效。
        if type(value) is not int or value < 0:
            # 不接受负数或其他类型。
            raise ValueError("重试次数和历史轮数必须是非负整数。")

    # 新问题初始化本轮字段，恢复不会重新执行这里。
    def run_prepare(state: DiagnosisState) -> dict:
        # 复用多轮消息准备与完整轮次裁剪。
        current = prepare_memory_node(state, filters, max_history_turns, max_context_chars)
        # 每个新问题获得有限的模型执行机会。
        current["remaining_steps"] = max_steps
        # 工具次数也只在新问题时初始化。
        current["remaining_tools"] = max_tool_calls
        # 同会话成功模拟的记录跨轮保留。
        current["simulated_cancellations"] = list(state.get("simulated_cancellations", []))
        # 上一轮审批不能用于本轮新请求。
        current["approval_request"] = {}
        # 新问题还没有人工决定。
        current["approval_decision"] = {}
        # 输入有效时补充综合诊断和审批规则。
        if not current["stop_reason"]:
            # 原始资料不改变这些程序规则。
            current["messages"][0]["content"] += APPROVAL_PROMPT + DIAGNOSIS_PROMPT
        # 返回需要写回的状态。
        return current

    # 模型节点只负责选择工具或生成回答。
    def run_model(state: DiagnosisState) -> dict:
        # 本节点使用自己的列表副本。
        current = copy_state(state)
        # 按完整轮次裁剪历史，不能拆开工具请求和结果。
        current["messages"] = trim_messages(
            current["messages"], max_history_turns, max_context_chars, TOOL_SCHEMAS,
        )
        # 当前轮本身过长就受控结束。
        if context_size(current["messages"], TOOL_SCHEMAS) > max_context_chars:
            # 不额外请求模型生成摘要。
            current["stop_reason"] = "context_budget"
            # 交给收尾节点说明原因。
            return current
        # 临时错误最多额外尝试指定次数，不记录重试统计。
        for attempt in range(max_retries + 1):
            # 每次实际请求前检查剩余机会。
            if current["remaining_steps"] <= 0:
                # 达到上限后不再为了总结请求模型。
                current["stop_reason"] = "model_limit"
                # 保留已经取得的业务结果。
                return current
            # 失败尝试也消耗一次机会。
            current["remaining_steps"] -= 1
            # 这里只捕获模型请求和响应校验的异常。
            try:
                # 使用普通消息和固定工具说明调用模型。
                message = model.chat_with_tools(current["messages"], TOOL_SCHEMAS)
                # 坏协议不能执行业务工具。
                validate_model_message(message)
            # 不记录异常原文。
            except Exception as error:
                # 临时错误且仍有重试机会时再尝试一次。
                if is_temporary_error(error) and attempt < max_retries:
                    # 不生成等待事件或日志。
                    continue
                # 永久错误或重试用尽时受控结束。
                current["stop_reason"] = "model_error"
                # 收尾节点使用固定说明。
                return current
            # 模型响应先保存在会话消息中。
            current["messages"].append(message)
            # 保存这次模型请求的工具队列。
            current["pending_tool_calls"] = message.get("tool_calls", [])
            # 有工具请求时由条件边继续分发。
            if current["pending_tool_calls"]:
                # 附带文字暂不作为最终回答。
                return current
            # 没有工具请求时取出最终文字。
            content = message.get("content")
            # 空内容不能当作正常回答。
            if not content or not content.strip():
                # 不无限请求空响应。
                current["stop_reason"] = "empty_response"
                # 交给收尾节点说明。
                return current
            # 保存完整回答。
            current["answer"] = content.strip()
            # 标明本轮正常完成。
            current["stop_reason"] = "final_answer"
            # 本次问题结束。
            return current

    # 每次节点只处理一个只读工具，成功后立即保存进度。
    def run_tools(state: DiagnosisState) -> dict:
        # 不修改上一个 Checkpoint 的列表。
        current = copy_state(state)
        # 取出队首工具。
        call = current["pending_tool_calls"][0]
        # 只对临时系统错误做有限重试。
        for attempt in range(max_retries + 1):
            # 实际分发前检查工具上限。
            if current["remaining_tools"] <= 0:
                # 人工恢复也不能刷新上限。
                current["stop_reason"] = "tool_limit"
                # 未执行请求由收尾节点配对。
                return current
            # 参数失败和临时失败同样消耗机会。
            current["remaining_tools"] -= 1
            # 普通查询可以有限重试，敏感操作不在这里执行。
            try:
                # 租户、知识库权限和文件路径均由服务端提供。
                result = dispatch_tool(call, current["tenant_id"], pipeline, filters, data_file)
            # 不保存异常原文或失败追踪事件。
            except Exception as error:
                # 临时故障且仍有机会才重试。
                if is_temporary_error(error) and attempt < max_retries:
                    # 成功的前序节点不会重新执行。
                    continue
                # 给当前请求配上明确的失败结果。
                complete_call(current, tool_result(False, error="工具查询失败。"))
                # 停止后续工具和模型请求。
                current["stop_reason"] = "tool_error"
                # 保留前面成功查询的证据。
                return current
            # 完整业务结果按调用 ID 回传。
            complete_call(current, result)
            # 业务失败不自动重试。
            if not result["success"]:
                # 资料不足和成功空列表不进入这个分支。
                current["stop_reason"] = "business_error"
            # 当前工具已完成，后续队列由下一次节点处理。
            return current

    # 审批请求独立存档，恢复时不会生成新的审批编号。
    def run_prepare_approval(state: DiagnosisState) -> dict:
        # 复制当前状态。
        current = copy_state(state)
        # 工具机会已用完时不再请求人工批准。
        if current["remaining_tools"] <= 0:
            # 由统一收尾节点结束。
            current["stop_reason"] = "tool_limit"
            # 不进入人工等待。
            return current
        # 先验证模型提供的订单号。
        try:
            # 人工决定和租户不能来自模型。
            order_id = parse_argument(current["pending_tool_calls"][0]["function"]["arguments"], "order_id")
        # 无效参数不进入审批。
        except (ValueError, TypeError):
            # 直接结束本轮。
            current["stop_reason"] = "business_error"
            # 不执行模拟取消。
            return current
        # 只读验证目标订单。
        result = get_order(order_id, current["tenant_id"], data_file)
        # 不可读订单不支持取消。
        if not result["success"]:
            # 保存查询失败的业务结果。
            complete_call(current, result)
            # 由收尾节点给出说明。
            current["stop_reason"] = "business_error"
            # 不让人批准无效目标。
            return current
        # 使用经过业务函数整理的订单信息。
        order = result["data"]
        # 同会话已成功模拟的订单不再重复执行。
        if order["order_id"] in current["simulated_cancellations"]:
            # 重复请求也消耗一次工具处理机会。
            current["remaining_tools"] -= 1
            # 明确返回已有模拟结果。
            complete_call(current, tool_result(True, data={
                "order_id": order["order_id"],
                "simulated": True,
                "duplicate": True,
                "note": "本会话已模拟取消，未重复执行；原始 JSON 未修改。",
            }))
            # 不重新要求审批。
            return current
        # 只模拟取消待支付订单。
        if order["status"] != "待支付":
            # 保存具体业务失败。
            complete_call(current, tool_result(False, error="仅支持模拟取消待支付订单。"))
            # 不请求批准不支持的操作。
            current["stop_reason"] = "business_error"
            # 当前问题结束。
            return current
        # 每次审批都有独立编号，旧批准不能用于新请求。
        current["approval_request"] = {
            "approval_id": uuid4().hex,
            "action": "cancel_order",
            "order_id": order["order_id"],
            "tenant_id": current["tenant_id"],
            "tool_call_id": current["pending_tool_calls"][0]["id"],
            "mode": "simulate",
        }
        # 当前请求还没有人工决定。
        current["approval_decision"] = {}
        # 请求随本节点提交到 Checkpoint。
        return current

    # 只有审批节点动态暂停，interrupt 不放入异常捕获范围。
    def run_approval(state: DiagnosisState) -> dict:
        # 恢复只重进当前节点。
        current = copy_state(state)
        # 第一次暂停；恢复时取得 API 提交的决定。
        decision = interrupt(current["approval_request"])
        # 人工决定必须完全绑定当前目标。
        if not validate_approval(decision, current["approval_request"]):
            # 无效决定不能执行操作。
            current["stop_reason"] = "approval_invalid"
            # 交给收尾节点处理。
            return current
        # 明确拒绝后不再让模型请求批准。
        if decision["decision"] == "reject":
            # 拒绝是正常的业务决定。
            current["stop_reason"] = "approval_rejected"
            # 收尾节点会配齐未执行消息。
            return current
        # 仅保存已经验证的决定。
        current["approval_decision"] = dict(decision)
        # 下一个独立节点才执行模拟操作。
        return current

    # 模拟执行与审批分开，避免审批节点重跑时提前执行操作。
    def run_execute_cancel(state: DiagnosisState) -> dict:
        # 复制本次节点状态。
        current = copy_state(state)
        # 执行前再次检查机会。
        if current["remaining_tools"] <= 0:
            # 人工等待不会重置次数。
            current["stop_reason"] = "tool_limit"
            # 不执行模拟。
            return current
        # 再次验证决定与当前请求匹配。
        if not validate_approval(current["approval_decision"], current["approval_request"]):
            # 防止绕过审批节点手动拼接状态。
            current["stop_reason"] = "approval_invalid"
            # 不执行模拟。
            return current
        # 决定必须明确表示批准。
        if current["approval_decision"]["decision"] != "approve":
            # 拒绝不能进入执行函数。
            current["stop_reason"] = "approval_invalid"
            # 保留业务边界。
            return current
        # 人工等待期间状态可能变化，执行前重新查询。
        result = get_order(current["approval_request"]["order_id"], current["tenant_id"], data_file)
        # 不可读或不再待支付时停止。
        if not result["success"] or result["data"]["status"] != "待支付":
            # 不将旧批准用于新的业务状态。
            current["stop_reason"] = "business_error"
            # 当前操作不执行。
            return current
        # 真正进入模拟函数才消耗一次工具机会。
        current["remaining_tools"] -= 1
        # 敏感动作异常不自动重试。
        try:
            # 只生成结果字典，不写 JSON 或数据库。
            simulated = simulate_cancel_order(result["data"])
        # 不确定结果必须明确说明。
        except Exception:
            # 给当前请求配上失败结果。
            complete_call(current, tool_result(False, error="模拟执行结果未确认。"))
            # 不声称已经回滚或一定未执行。
            current["stop_reason"] = "action_error"
            # 不自动重试模拟动作。
            return current
        # 完成当前请求，保留模拟来源。
        complete_call(current, simulated)
        # 只记录业务上的成功模拟结果。
        current["simulated_cancellations"].append(result["data"]["order_id"])
        # 已完成的审批不能再使用。
        current["approval_request"] = {}
        # 同时清空决定。
        current["approval_decision"] = {}
        # 由条件边处理后续请求。
        return current

    # 统一补齐未执行请求并生成固定失败说明。
    def run_finish(state: DiagnosisState) -> dict:
        # 保留之前的业务结果。
        current = copy_state(state)
        # 每个未执行工具也要有对应协议消息。
        while current["pending_tool_calls"]:
            # 不把未执行冒充为查询成功。
            complete_call(current, tool_result(False, error="本轮结束，此请求未执行。"))
        # 正常回答之外的结束原因使用固定说明。
        reasons = {
            "invalid_input": "请输入有效问题，并使用服务端配置的身份。",
            "model_limit": "已达到本轮模型执行上限，停止继续调用。",
            "tool_limit": "已达到本轮工具执行上限，停止继续调用。",
            "context_budget": "本轮内容过长，请缩短问题或工具结果。",
            "model_error": "模型调用失败或响应无效，本轮结束。",
            "empty_response": "模型未给出有效回答，本轮结束。",
            "tool_error": "工具查询失败，本轮结束。",
            "business_error": "订单不存在、不可读取或不满足操作条件，本轮结束。",
            "approval_invalid": "审批参数无效，未执行模拟取消。",
            "approval_rejected": "已拒绝模拟取消，原始 JSON 未修改。",
            "action_error": "模拟执行结果未确认，本轮停止，不自动重试。",
        }
        # 失败或拒绝不再额外请求模型解释。
        if current["stop_reason"] != "final_answer":
            # 保存简短的业务说明。
            current["answer"] = reasons.get(current["stop_reason"], "本轮已结束。")
            # 将程序说明作为会话回答，下一轮可以正常追问。
            current["messages"].append({"role": "assistant", "content": current["answer"]})
        # 收尾后不保留可复用的旧批准。
        current["approval_request"] = {}
        # 同时清空已消费的决定。
        current["approval_decision"] = {}
        # 不生成统计或日志汇总。
        return current

    # 审批准备成功才进入人工等待。
    def choose_approval_route(state: DiagnosisState) -> str:
        # 准备失败时先收尾。
        if state["stop_reason"]:
            # 不再请求人工批准。
            return "finish"
        # 新请求需要等待人工决定。
        if state["approval_request"]:
            # 下一节点会动态暂停。
            return "approval"
        # 重复模拟等情况按当前队列继续。
        return choose_route(state)

    # 审批通过后才能执行模拟动作。
    def choose_decision_route(state: DiagnosisState) -> str:
        # 拒绝和无效参数都直接结束。
        if state["stop_reason"]:
            # 不进入敏感执行节点。
            return "finish"
        # 有效批准进入独立执行节点。
        return "execute_cancel"

    # 共享状态只保存业务和流程控制字段。
    graph = StateGraph(DiagnosisState)
    # 注册各个核心步骤。
    graph.add_node("prepare", run_prepare)
    # 模型负责选择工具和回答。
    graph.add_node("model", run_model)
    # 普通工具按队列逐个执行。
    graph.add_node("tools", run_tools)
    # 审批请求先独立保存。
    graph.add_node("prepare_approval", run_prepare_approval)
    # 审批节点只负责暂停和决定校验。
    graph.add_node("approval", run_approval)
    # 真正模拟动作在另一个节点中。
    graph.add_node("execute_cancel", run_execute_cancel)
    # 所有结束路径统一收尾。
    graph.add_node("finish", run_finish)
    # 新问题从准备节点开始。
    graph.add_edge(START, "prepare")
    # 普通节点完成后按当前状态路由。
    for name in ("prepare", "model", "tools", "execute_cancel"):
        # 路由标签与目标节点直接对应。
        graph.add_conditional_edges(name, choose_route, {
            "model": "model",
            "tools": "tools",
            "prepare_approval": "prepare_approval",
            "finish": "finish",
        })
    # 审批请求准备完成后进入人工等待。
    graph.add_conditional_edges("prepare_approval", choose_approval_route, {
        "approval": "approval",
        "model": "model",
        "tools": "tools",
        "prepare_approval": "prepare_approval",
        "finish": "finish",
    })
    # 批准后才进入模拟执行。
    graph.add_conditional_edges("approval", choose_decision_route, {
        "execute_cancel": "execute_cancel",
        "finish": "finish",
    })
    # 收尾后结束本轮。
    graph.add_edge("finish", END)
    # 默认不在普通工具前暂停。
    pause_nodes = []
    # 第 65 课可选择在工具执行前暂停。
    if pause_before_tools:
        # 人工审批仍使用独立的动态暂停。
        pause_nodes = ["tools"]
    # 使用同一存档器保存会话和执行进度。
    compiled = graph.compile(checkpointer=checkpointer, interrupt_before=pause_nodes)
    # 调度上限为工具、审批和收尾节点留出空间。
    return compiled.with_config({"recursion_limit": 4 * max_steps + 4 * max_tool_calls + 20})
