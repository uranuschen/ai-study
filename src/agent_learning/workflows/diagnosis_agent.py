import json
import time
from pathlib import Path
from uuid import uuid4
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from agent_learning.business.tools import DEFAULT_DATA_FILE, get_order, tool_result
from agent_learning.core.models import SearchFilter
from agent_learning.rag.answering import RAGPipeline
from agent_learning.workflows import recovery_agent as recovery
from agent_learning.workflows.human_approval_agent import APPROVAL_PROMPT, TOOL_SCHEMAS, ApprovalState, complete_tool_call, simulate_cancel_order, validate_approval
from agent_learning.workflows.memory_agent import context_size, prepare_memory_node, trim_messages
from agent_learning.workflows.run_execution import ExecutionStopped, RunExecution
from agent_learning.workflows.tool_model import CompatibleToolModel
from agent_learning.workflows.tracing import TraceRecorder, safe_arguments


# (70) 综合诊断只补充已有工具的使用顺序，不添加新的业务操作。
DIAGNOSIS_PROMPT = (
    "简单查询只调用必要工具。完整订单诊断先查订单，再按业务结果查询支付和退款，必要时查规则。"
    "订单不存在、未支付或没有退款记录时及时说明已知结果，不猜测未查询的事实。"
    "只有用户明确要求取消才请求 cancel_order；人工拒绝后停止，不自行再次请求批准。"
)


# (70) 沿用审批 State，补充第 63 课的预算字段与本轮运行标识。
class DiagnosisState(ApprovalState):
    # (70) 每个新问题独立计预算，恢复暂停任务不重置这些字段。
    limits: dict
    # (70) 所有实际 LLM 请求尝试共用计数，包含 RAG 内层与重试。
    model_steps: int
    # (70) 模型次数上限来自建图参数，不从用户问题提取。
    max_steps: int
    # (70) 真实 Tool 分发次数包含有限重试，审批等待不算执行。
    tool_calls: int
    # (70) 保留实际开始的模型与工具重试次数。
    model_retries: int
    # (70) 业务失败和人工拒绝不增加自动重试。
    tool_retries: int
    # (70) 预算记账包含未知用量的保守预留，不等同于全部实测 Token。
    total_tokens: int
    # (70) 用字符串保存 Decimal 费用估算。
    estimated_cost: str
    # (70) 逐次用量注明外层模型或 RAG 内层作用域。
    usage_history: list
    # (70) 沿用第 63 课的安全等待事件，不保存异常原文。
    events: list
    # (70) 开始时间与可选截止时间使用单调时钟。
    started_at: float
    # (70) 默认关闭时间限制，便于逐步 Debug。
    deadline: float | None
    # (69) 结束耗时包含人工等待和 Debug 停顿，不与父子跨度耗时相加。
    elapsed_seconds: float
    # (69) 同一逻辑会话编号由可信 config 提供。
    thread_id: str
    # (69) 每个新问题一个编号，同一次审批恢复沿用原编号。
    run_id: str
    # (69) 事件只保留白名单元数据，不记录消息、资料正文或原始异常。
    trace_events: list
    # (69) 只从实际 LLM 结束事件汇总用量，避免父子重复计费。
    trace_summary: dict
    # (69) 起止跨度作为普通字典保存，暂停后仍能结束同一跨度。
    run_span: dict
    # (70) 敏感目标在进入 interrupt 前单独保存，避免恢复时重复准备整个批次。
    approval_request: dict
    # (70) 人工响应由程序校验，不当作模型可以提供的工具参数。
    approval_decision: dict
    # (69) 审批跨度跨暂停保留，时间明确包含人工等待。
    approval_span: dict


# (70) 每个节点复制会追加的列表，避免直接修改之前的 Checkpoint State。
def copy_run_state(state: DiagnosisState) -> dict:
    # (70) 沿用原来的消息、工具结果、用量和事件列表复制。
    current = recovery.copy_state(state)
    # (69) 本节点追加记录时不会修改旧快照中的事件列表。
    current["trace_events"] = list(state["trace_events"])
    # (70) 模拟记录跨轮保留，不能因历史消息裁剪清空。
    current["simulated_cancellations"] = list(state.get("simulated_cancellations", []))
    # (70) 返回普通字典供 LangGraph 更新。
    return current


# (70) 统一选择下一个待执行工具，不按照第几次进入路由判断。
def choose_next_route(state: DiagnosisState) -> str:
    # (70) 正常回答与明确拒绝都可以直接收尾。
    if state["stop_reason"] in ("final_answer", "approval_rejected"):
        # (70) 不再发起模型或工具请求。
        return "finish"
    # (70) 业务失败、预算耗尽和永久系统错误进入受控失败分支。
    if state["stop_reason"]:
        # (70) 失败说明不额外花费一次模型调用。
        return "failure"
    # (70) 当前批次的每个 Tool 结果已配齐，才回模型总结。
    if not state["pending_tool_calls"]:
        # (70) 仍延续模型选择工具、结果回传、模型总结的主循环。
        return "model"
    # (70) 敏感操作先准备审批，其他请求进入普通只读 Tool 节点。
    return "prepare_approval" if state["pending_tool_calls"][0]["function"]["name"] == "cancel_order" else "tools"


# (70) 执行前检查工具次数、总时间，以及已产生的模型用量。
def check_tool_budget(state: dict, clock) -> str:
    # (70) 开启时间限制时，不继续执行超过整体期限的任务。
    if recovery.overall_timeout_reached(state, clock):
        # (70) 默认关闭时不会因 Debug 或人工等待触发此分支。
        return "overall_timeout"
    # (70) 执行次数是实际分发尝试，不是记录条数。
    if state["tool_calls"] >= state["limits"]["max_tool_calls"]:
        # (70) 未执行操作不先递增计数。
        return "tool_limit"
    # (70) 内层模型若已超预算，不允许继续其他 Tool。
    return recovery.check_used_budget(state)


# (70) 只读 Tool 保留原接口；RAG 仅增加共享执行对象参数。
def dispatch_tool(name: str, arguments: str, tenant_id: str, pipeline: RAGPipeline, filters: SearchFilter, data_file: Path, execution: RunExecution) -> dict:
    # (70) 三个业务函数仍由第 63 课的严格白名单分发与校验。
    if name in ("get_order", "get_payment", "get_refund"):
        # (70) 身份和本地 JSON 路径由可信程序绑定。
        return recovery.dispatch_tool(name, arguments, tenant_id, data_file)
    # (70) cancel_order 只能走审批分支，不能从普通 Tool 节点执行。
    if name != "ask_knowledge_base":
        # (70) 不执行模型提出的任意函数名。
        return tool_result(False, error="未知工具或工具不允许从普通查询入口执行。")
    # (70) 知识库参数仍只有非空 question。
    try:
        # (70) 不让模型提供租户、资料类型或权限字段。
        parsed = json.loads(arguments)
    # (70) 参数错误属于业务失败，不盲目重试。
    except (ValueError, TypeError):
        # (70) 返回固定说明，不泄露原始参数。
        return tool_result(False, error="知识库参数必须是有效 JSON。")
    # (70) 实际校验不能只依靠发给模型的 schema。
    if not isinstance(parsed, dict) or set(parsed) != {"question"} or not isinstance(parsed["question"], str) or not parsed["question"].strip():
        # (70) 坏参数不能启动检索或模型请求。
        return tool_result(False, error="知识库参数只允许非空字符串 question。")
    # (70) 原 RAG 检索、精排与引用校验保持不变；异常交给当前工作流分类。
    result = pipeline.ask(parsed["question"].strip(), filters, execution=execution)
    # (70) 仍保留原始引用和资料不足状态，不把它们放进脱敏日志。
    return tool_result(True, data={"answer": result["answer"], "citations": result["citations"], "status": result["status"]})


# (70) 模型节点保留整轮裁剪，实际请求由共享执行器检查预算与有限重试。
def model_node(current: dict, model: CompatibleToolModel, trace: TraceRecorder, parent_id: str, max_history_turns: int, max_context_chars: int, clock, sleep) -> None:
    # (70) 新工具说明同样计入上下文字符数。
    current["messages"] = trim_messages(current["messages"], max_history_turns, max_context_chars, TOOL_SCHEMAS)
    # (70) 当前轮不能拆开，超预算时不发出残缺上下文。
    if context_size(current["messages"], TOOL_SCHEMAS) > max_context_chars:
        # (70) 结束原因由程序确定，之前工具结果保留。
        current["stop_reason"] = "context_budget"
        # (70) 不自动摘要或额外请求模型。
        return
    # (70) 每次节点创建本地执行对象，不跨会话共享计数。
    execution = RunExecution(current, trace, parent_id, clock, sleep)
    # (70) 预算或有限重试结束用程序异常通知当前节点。
    try:
        # (70) 继续向原客户端传入消息与五个工具说明。
        message = execution.request(model, current["messages"], TOOL_SCHEMAS)
    # (70) 只拦截明确的受控停止，不把程序错误伪装成业务空结果。
    except ExecutionStopped:
        # (70) 执行器已经保存结束原因与用量。
        return
    # (70) 执行器已保存有效 assistant 与待执行队列，避免用量超限时丢失调用证据。
    # (70) 有工具请求时继续分发，不把同时附带的文字当作最终回答。
    if current["pending_tool_calls"]:
        # (70) 下一条条件边按工具名选择查询或审批。
        return
    # (70) 无工具请求时仍要求非空文字才能正常完成。
    current["answer"] = (message.get("content") or "").strip()
    # (70) 正常回答与空响应都结束，不无限循环。
    current["stop_reason"] = "final_answer" if current["answer"] else "empty_response"


# (70) 每个节点只处理一个只读请求，成功后就保存进度再处理下一个。
def tools_node(current: dict, pipeline: RAGPipeline, filters: SearchFilter, data_file: Path, trace: TraceRecorder, parent_id: str, clock, sleep) -> None:
    # (70) 队首是这一次需要执行的工具。
    call = current["pending_tool_calls"][0]
    # (70) 工具名称只用于白名单分发，不作为任意代码执行。
    name = call["function"]["name"]
    # (69) 日志不回显模型生成的未知函数名。
    safe_name = name if name in ("get_order", "get_payment", "get_refund", "ask_knowledge_base") else "unknown_tool"
    # (70) 只读调用的临时系统错误才可以有限重试。
    for retry_index in range(current["limits"]["max_retries"] + 1):
        # (70) 每次尝试前都检查总 Tool 次数与已消耗预算。
        reason = check_tool_budget(current, clock)
        # (70) 不足以启动本次操作时直接结束，finish 会配齐未执行消息。
        if reason:
            # (70) 不把未执行的请求算成成功或空记录。
            current["stop_reason"] = reason
            # (70) 不启动工具函数。
            return
        # (70) 每次真实分发都计数，参数失败也占一次。
        current["tool_calls"] += 1
        # (70) 只有实际开始额外尝试才计重试。
        current["tool_retries"] += int(retry_index > 0)
        # (69) Tool 与内部 RAG / LLM 子跨度属于同一轮执行。
        span = trace.start("tool", safe_name, parent_id=parent_id, attempt=current["tool_calls"], retry=retry_index, tool_call_id=call["id"])
        # (69) 只保存已脱敏参数摘要，不保留完整问题或订单号。
        current["trace_events"][-1]["arguments"] = safe_arguments(safe_name, call["function"]["arguments"])
        # (70) 该执行器让 RAG 内部模型也累计到本轮预算。
        execution = RunExecution(current, trace, span["span_id"], clock, sleep)
        # (70) 默认没有系统异常，普通业务返回 False 另行处理。
        error = None
        # (70) 所有真实调用都留在这一明确的错误边界内。
        try:
            # (70) 业务函数、混合检索与精排都沿用之前的实现。
            result = dispatch_tool(name, call["function"]["arguments"], current["tenant_id"], pipeline, filters, data_file, execution)
            # (70) 错误返回结构不能冒充正常业务数据。
            if not isinstance(result, dict) or set(result) != {"success", "data", "error"} or type(result["success"]) is not bool:
                # (70) 协议错误不是可自动恢复的临时故障。
                raise ValueError("Tool 返回格式无效。")
        # (70) RAG 内层预算或重试停止不能被 Tool 层再次整体重试。
        except ExecutionStopped as caught:
            # (70) 保留已有结束原因，避免重跑已经发生的内层模型请求。
            error = caught
            # (70) 未取得业务结果不等于查过且无记录。
            result = tool_result(False, error="知识库执行已受控停止，未确认本次规则答案。")
        # (70) 只将异常对象暂存用于分类，不能输出 str(error)。
        except Exception as caught:
            # (70) 原始异常可能包含连接信息、请求体或密钥。
            error = caught
            # (70) 给模型与 Console 的结果使用固定安全说明。
            result = tool_result(False, error="Tool 系统异常，未确认查询结果。")
        # (69) 失败分类、调用 ID 摘要与耗时帮助定位，但不存完整 Tool 结果。
        trace.finish(span, "error" if error else "success" if result["success"] else "business_failure", error=error)
        # (70) 时间关闭时只记录耗时；开启后也不声称终止了远端任务。
        reason = "overall_timeout" if recovery.overall_timeout_reached(current, clock) else ""
        # (70) 同步本地工具只能在返回后检查单次耗时。
        if not reason and current["limits"]["enable_timeouts"] and clock() - span["started_at"] >= current["limits"]["tool_timeout"]:
            # (70) 超时后停止后续调度，不自动重放当前调用。
            reason = "tool_timeout"
        # (70) 内层受控停止已经设置预算或错误原因。
        reason = reason or current["stop_reason"]
        # (70) 无系统异常时，业务成功和业务失败都不重试。
        if error is None:
            # (70) 原始成功空列表保留，不误报查询失败。
            current.update(complete_tool_call(current, result))
            # (70) 业务失败直接进入失败分支，不交给模型无限修正。
            current["stop_reason"] = reason or ("" if result["success"] else "business_error")
            # (70) 当前调用已经配齐，剩余批次由后续节点处理或跳过。
            return
        # (70) 已发生预算停止或不可重试错误时，不继续等待。
        if reason or not recovery.is_temporary_error(error):
            # (70) 记录失败而不是让 finish 标成完全未执行。
            current.update(complete_tool_call(current, result))
            # (70) 保留更具体的内层停止原因。
            current["stop_reason"] = reason or "tool_error"
            # (70) 不继续本次工具尝试。
            return
        # (70) 当前只读调用的额外重试额度已用完。
        if retry_index >= current["limits"]["max_retries"]:
            # (70) 失败结果只回传一次，但每次尝试都已经计数。
            current.update(complete_tool_call(current, result))
            # (70) 进入受控失败分支。
            current["stop_reason"] = "tool_retry_exhausted"
            # (70) 不继续循环。
            return
        # (70) 已到总次数上限时直接结束，不做无意义等待。
        if current["tool_calls"] >= current["limits"]["max_tool_calls"]:
            # (70) 当前调用已经发生过，保留实际失败结果。
            current.update(complete_tool_call(current, result))
            # (70) 后面的工具由 finish 配齐未执行说明。
            current["stop_reason"] = "tool_limit"
            # (70) 不开始下一次工具尝试。
            return
        # (69) 单独记录重试等待，不重复统计为 Tool 执行。
        wait_span = trace.start("node", "tool_retry_wait", parent_id=parent_id, retry=retry_index + 1)
        # (70) 沿用原 Retry-After 和有限等待规则。
        can_retry = recovery.wait_to_retry(current, error, retry_index, clock, sleep, "tool")
        # (69) 状态只表示等待是否允许，不泄露原始错误。
        trace.finish(wait_span, "success" if can_retry else "error")
        # (70) 等待限制不足时保存本次失败后结束。
        if not can_retry:
            # (70) complete_tool_call 默认返回空结束原因，先保留原控制原因。
            reason = current["stop_reason"]
            # (70) 当前请求有实际失败，不把它误标成从未执行。
            current.update(complete_tool_call(current, result))
            # (70) 恢复原有受控停止原因。
            current["stop_reason"] = reason
            # (70) 不再执行该工具。
            return


# (70) 审批准备是独立节点，确认目标和等待跨度在暂停前先存档。
def prepare_approval_node(current: dict, data_file: Path, trace: TraceRecorder, clock, parent_id: str = "") -> None:
    # (70) 每次只为队首取消请求生成审批信息。
    call = current["pending_tool_calls"][0]
    # (70) 清空本次审批字段，不沿用上一个操作的批准。
    current["approval_request"], current["approval_decision"] = {}, {}
    # (70) 预算已不足时不要求人批准不会执行的请求。
    reason = check_tool_budget(current, clock)
    # (70) 未执行操作不增加 Tool 次数。
    if reason:
        # (70) 剩余消息由 finish 配齐。
        current["stop_reason"] = reason
        # (70) 不进入 interrupt。
        return
    # (70) 和第 67 课一样，只允许模型提供订单号。
    try:
        # (70) 审批决定和可信租户不能来自模型参数。
        arguments = json.loads(call["function"]["arguments"])
    # (70) JSON 损坏直接结束，不暴露原始内容。
    except (ValueError, TypeError):
        # (70) 不要求人工批准无效参数。
        current["stop_reason"] = "business_error"
        # (70) 当前未执行操作由 finish 标记未执行。
        return
    # (70) 实际参数还要做严格结构与类型校验。
    if not isinstance(arguments, dict) or set(arguments) != {"order_id"} or not isinstance(arguments["order_id"], str) or not arguments["order_id"].strip():
        # (70) 参数失败不是临时系统故障。
        current["stop_reason"] = "business_error"
        # (70) 不进入审批。
        return
    # (70) 只读检查实际订单，租户始终来自可信 State。
    order_result = get_order(arguments["order_id"], current["tenant_id"], data_file)
    # (70) 不存在或不可读取的订单不支持取消。
    if not order_result["success"]:
        # (70) 配齐当前调用但不模拟执行。
        current.update(complete_tool_call(current, order_result))
        # (70) 业务失败不进入模型重试。
        current["stop_reason"] = "business_error"
        # (70) 后面的请求仍保留到 finish 处理。
        return
    # (70) 使用本地业务函数规范化后的订单号。
    order = order_result["data"]
    # (70) 同会话已模拟过就返回已有事实，不再次审批或执行。
    if order["order_id"] in current["simulated_cancellations"]:
        # (70) 重复请求仍算一次 Tool 处理，避免大量重复调用绕过总次数限制。
        current["tool_calls"] += 1
        # (69) 明确记录跳过执行，而不是伪造又执行了一次模拟取消。
        span = trace.start("tool", "cancel_order", parent_id=parent_id, attempt=current["tool_calls"], tool_call_id=call["id"])
        # (69) 原始参数留在业务 State，日志只保留遮盖后的订单摘要。
        current["trace_events"][-1]["arguments"] = safe_arguments("cancel_order", call["function"]["arguments"])
        # (70) 模拟记录不代表原始 JSON 已取消。
        result = tool_result(True, data={"order_id": order["order_id"], "status": "本会话已模拟取消", "simulated": True, "duplicate": True, "note": "未重复执行；原始 JSON 未修改。"})
        # (70) 当前请求完成后由路由决定下一个工具或模型总结。
        current.update(complete_tool_call(current, result))
        # (69) Tool 已处理但敏感动作未重做。
        trace.finish(span, "skipped")
        # (70) 不重复生成审批请求。
        return
    # (70) 仍只允许待支付订单，已支付取消与退款不在模拟范围内。
    if order["status"] != "待支付":
        # (70) 原始业务结果保留，不把已支付订单冒充可取消。
        current.update(complete_tool_call(current, tool_result(False, error="本课只模拟取消待支付订单。")))
        # (70) 不请求人工批准不支持的业务操作。
        current["stop_reason"] = "business_error"
        # (70) 后续批次不再执行。
        return
    # (70) 沿用原目标字段并绑定本轮 run_id，防止相同调用 ID 下的旧批准跨轮重放。
    current["approval_request"] = {"action": "cancel_order", "order_id": order["order_id"], "tenant_id": current["tenant_id"], "tool_call_id": call["id"], "mode": "simulate", "run_id": current["run_id"]}
    # (69) 跨暂停保存审批节点的跨度，耗时包括人工等待。
    current["approval_span"] = trace.start("node", "approval", parent_id=current["run_span"]["span_id"])


# (70) 仅这个节点动态暂停；恢复只重进本节点，不重做前面工具。
def approval_node(state: DiagnosisState, clock) -> dict:
    # (70) 更新副本不改变上一份待审批快照。
    current = copy_run_state(state)
    # (69) 使用同一 run_id 与已保存的审批跨度。
    trace = TraceRecorder(current, clock)
    # (70) 第一次在这里暂停；恢复时返回 Command 提供的响应。
    decision = interrupt(current["approval_request"])
    # (70) 严格使用第 67 课的目标绑定校验，不允许更换订单或租户。
    if not validate_approval(decision, current["approval_request"]):
        # (69) 无效响应只记录固定状态。
        trace.finish(current["approval_span"], "error", error=ValueError("审批无效"))
        # (70) 不执行模拟取消，剩余批次在 finish 中配齐。
        current["stop_reason"] = "approval_invalid"
        # (70) 结束当前节点。
        return current
    # (70) 人工拒绝也属于一次恢复，但不允许进入执行节点。
    if decision["decision"] == "reject":
        # (69) 拒绝不是模型或工具的系统异常。
        trace.finish(current["approval_span"], "rejected")
        # (70) 当前取消请求记录拒绝事实，后续请求不执行。
        result = tool_result(True, data={"order_id": decision["order_id"], "status": "人工拒绝", "simulated": False, "note": "原始 JSON 未修改。"})
        # (70) 保留原来的停止原因与完整 Tool 消息配对。
        current.update(complete_tool_call(current, result, "approval_rejected", "已拒绝，未执行模拟取消；原始 JSON 未修改。"))
        # (70) 不再请求模型劝说用户批准。
        return current
    # (69) 确认只表示审批通过，执行本身由另一个节点追踪。
    trace.finish(current["approval_span"], "success")
    # (70) 校验过的决定保存进 State，供独立执行节点读取。
    current["approval_decision"] = dict(decision)
    # (70) 恢复不重新 prepare，所以原 run_id 与全部预算保持不变。
    return current


# (70) 敏感操作执行节点不包含 interrupt，也不自动重试模拟取消。
def execute_cancel_node(current: dict, data_file: Path, trace: TraceRecorder, parent_id: str, clock) -> None:
    # (70) 审批等待可能很久，执行前必须再次检查预算。
    reason = check_tool_budget(current, clock)
    # (70) 不把批准当成绕过预算的通行证。
    if reason:
        # (70) 保留批准记录，但明确本次操作未执行。
        current["stop_reason"] = reason
        # (70) 未执行请求由 finish 配对。
        return
    # (70) 只有绑定当前目标的有效确认才能到达模拟函数。
    if not validate_approval(current["approval_decision"], current["approval_request"]) or current["approval_decision"]["decision"] != "approve":
        # (70) 不接受手动拼出的无效 State。
        current["stop_reason"] = "approval_invalid"
        # (70) 不执行业务函数。
        return
    # (70) 订单状态可能在人工等待期间变化，执行前再只读验证一次。
    order_result = get_order(current["approval_request"]["order_id"], current["tenant_id"], data_file)
    # (70) 已不满足待支付条件时，旧批准不能覆盖新业务状态。
    if not order_result["success"] or order_result["data"]["status"] != "待支付":
        # (70) 保留当前查询结果，但不模拟取消。
        current.update(complete_tool_call(current, tool_result(False, error="审批后订单不可读取或状态已变化，未执行模拟取消。")))
        # (70) 进入明确的业务失败分支。
        current["stop_reason"] = "business_error"
        # (70) 不执行取消函数。
        return
    # (70) 只有真正开始执行才增加敏感 Tool 次数。
    current["tool_calls"] += 1
    # (69) 操作结果不记录进日志，日志仅保留状态、次数与耗时。
    span = trace.start("tool", "cancel_order", parent_id=parent_id, attempt=current["tool_calls"], tool_call_id=current["approval_request"]["tool_call_id"])
    # (69) 取消操作也使用同一参数脱敏规则，不输出完整订单号。
    current["trace_events"][-1]["arguments"] = safe_arguments("cancel_order", json.dumps({"order_id": current["approval_request"]["order_id"]}))
    # (70) 敏感执行异常不能沿用只读操作的自动重试。
    try:
        # (70) 直接使用第 67 课模拟函数，不写 JSON、数据库或外部接口。
        result = simulate_cancel_order(order_result["data"])
    # (70) 不把异常原文写进结果，也不声称有副作用的操作必定未执行。
    except Exception as error:
        # (69) 记录安全错误分类与实际执行耗时。
        trace.finish(span, "error", error=error)
        # (70) 结果不确定时禁止自动重试，当前请求仍有对应 Tool 消息。
        current.update(complete_tool_call(current, tool_result(False, error="模拟执行异常，未确认操作结果，不自动重试。")))
        # (70) 由统一失败分支说明执行未确认。
        current["stop_reason"] = "action_error"
        # (70) 不把失败或未知结果写入成功模拟记录。
        return
    # (69) 模拟执行与前面的人工等待分别计时。
    trace.finish(span, "success")
    # (70) 模拟结果与本轮模型请求的调用 ID 配对。
    current.update(complete_tool_call(current, result))
    # (70) 同会话保存简单防重复记录，不宣称生产写操作 exactly-once。
    current["simulated_cancellations"] = current["simulated_cancellations"] + [order_result["data"]["order_id"]]
    # (70) 批准只能用于当前操作，不沿用到后续工具。
    current["approval_request"], current["approval_decision"] = {}, {}


# (70) 把已有 Memory、RAG、恢复、预算与人工确认编排到同一张图。
def build_graph(model: CompatibleToolModel, pipeline: RAGPipeline, filters: SearchFilter, checkpointer: InMemorySaver, data_file: Path = DEFAULT_DATA_FILE, limits=None, max_history_turns: int = 2, max_context_chars: int = 12000, clock=time.monotonic, sleep=time.sleep):
    # (70) 保持之前课程的可信资料范围。
    if filters.doc_type not in ("policy", "process", "faq"):
        # (70) 不让订单资料快照代替当前业务事实。
        raise ValueError("知识库资料类型只能是 policy、process 或 faq。")
    # (70) 两个简单 Memory 参数不接受负数或空预算。
    if type(max_history_turns) is not int or max_history_turns < 0 or type(max_context_chars) is not int or max_context_chars < 1:
        # (70) 无效配置在模型请求前提示。
        raise ValueError("历史轮数必须非负，上下文字符预算必须为正。")
    # (70) 只有显式要求才启用时间限制，默认 Debug 不因暂停超时。
    # (70) 保留原预算函数的配置类型约束，拒绝错误的覆盖参数。
    if limits is not None and not isinstance(limits, dict):
        # (70) 不在启动模型后才发现配置错误。
        raise ValueError("预算覆盖参数必须是字典。")
    # (70) 新课只改变默认时间开关，不修改旧课默认配置。
    trusted_limits = recovery.make_limits({"enable_timeouts": False, **({} if limits is None else limits)})

    # (70) 新问题开始时初始化预算；Command 恢复不会重新进入这个节点。
    def run_prepare(state: DiagnosisState, config: RunnableConfig) -> dict:
        # (70) 保留新输入与旧会话字段，再写入可信的本轮预算。
        current = dict(state)
        # (69) 先建立本轮运行标识，让 prepare 的校验与历史裁剪也计入节点耗时。
        current["thread_id"] = str(config["configurable"]["thread_id"])
        # (69) 新问题生成新编号，Command 恢复不会执行这里。
        current["run_id"] = uuid4().hex
        # (69) 本轮日志与上一轮分开，不清空会话历史。
        current["trace_events"], current["trace_summary"] = [], {}
        # (69) 所有普通节点仍使用同一个整轮父跨度。
        trace = TraceRecorder(current, clock)
        # (69) 总跨度从 prepare 的实际工作之前开始。
        current["run_span"] = trace.start("run", "order_diagnosis")
        # (69) prepare 的输入校验与两次历史裁剪均包含在节点时间中。
        span = trace.start("node", "prepare", parent_id=current["run_span"]["span_id"])
        # (70) 使用第 63 课原有的预算与计数初始化。
        current.update(recovery.prepare_node(state, trusted_limits, clock))
        # (70) 使用第 66 课原有的输入校验、追问历史与整轮裁剪。
        current.update(prepare_memory_node(state, filters, max_history_turns, max_context_chars))
        # (70) 新问题不清空同会话已经模拟过的订单号。
        current["simulated_cancellations"] = list(state.get("simulated_cancellations", []))
        # (70) 上一轮批准不能用于本轮新请求。
        current["approval_request"], current["approval_decision"], current["approval_span"] = {}, {}, {}
        # (70) 输入校验成功后才补充综合流程与审批规则。
        if not current["stop_reason"]:
            # (70) 不重写原业务事实与 RAG 引用边界。
            current["messages"][0]["content"] += APPROVAL_PROMPT + DIAGNOSIS_PROMPT
            # (70) 补充规则后按实际工具说明再检查完整轮次。
            current["messages"] = trim_messages(current["messages"], max_history_turns, max_context_chars, TOOL_SCHEMAS)
        # (69) 只记录校验状态，不记录用户问题或可信过滤器全文。
        trace.finish(span, "error" if current["stop_reason"] else "success")
        # (70) LangGraph 保存新问题的共享 State。
        return current

    # (69) 普通节点统一开始与结束记录；动态 interrupt 节点单独处理。
    def run_logged_node(state: DiagnosisState, name: str, operation) -> dict:
        # (70) 更新副本，不原地修改上一个 Checkpoint。
        current = copy_run_state(state)
        # (69) 使用当前轮的 thread_id 与 run_id。
        trace = TraceRecorder(current, clock)
        # (69) 每个节点的子 Tool / LLM 挂在这个跨度下。
        span = trace.start("node", name, parent_id=current["run_span"]["span_id"])
        # (70) 普通函数显式绑定需要的依赖，不使用反射或装饰器。
        operation(current, trace, span["span_id"])
        # (69) final_answer 是正常完成，预算或系统失败有独立结束状态。
        status = "success" if not current["stop_reason"] or current["stop_reason"] == "final_answer" else current["stop_reason"]
        # (69) 节点不重复记录其内部 LLM 用量。
        trace.finish(span, status)
        # (70) 保留该节点已经完成的队列、预算与追踪进度。
        return current

    # (70) 绑定原模型和 Memory 配置。
    def run_model(state: DiagnosisState) -> dict:
        # (70) 本层只负责编排，不直接创建模型请求。
        def operation(current, trace, parent_id):
            # (70) 实际请求、重试和费用统一放在共享执行器中。
            model_node(current, model, trace, parent_id, max_history_turns, max_context_chars, clock, sleep)
        # (69) 模型节点的耗时包含其内部重试和等待。
        return run_logged_node(state, "model", operation)

    # (70) 绑定业务 JSON 和 RAG，不增加新的工具实现。
    def run_tools(state: DiagnosisState) -> dict:
        # (70) 每次只处理一个待执行调用。
        def operation(current, trace, parent_id):
            # (70) 临时只读异常有限重试，业务失败直接进入失败分支。
            tools_node(current, pipeline, filters, data_file, trace, parent_id, clock, sleep)
        # (69) 工具执行时间和其子模型时间分别观察。
        return run_logged_node(state, "tools", operation)

    # (70) 审批准备单独存档，恢复不重放前面的只读工具。
    def run_prepare_approval(state: DiagnosisState) -> dict:
        # (70) 只校验目标和准备审批信息，不执行取消。
        def operation(current, trace, parent_id):
            # (70) 准备完成后由条件边选择是否进入 interrupt。
            prepare_approval_node(current, data_file, trace, clock, parent_id)
        # (69) 参数准备耗时与人工等待分开记录。
        return run_logged_node(state, "prepare_approval", operation)

    # (70) 动态暂停节点不放进普通日志的宽泛异常边界。
    def run_approval(state: DiagnosisState) -> dict:
        # (70) interrupt 第一次退出，恢复后只重进这个节点。
        return approval_node(state, clock)

    # (70) 审批通过后才执行一次模拟取消。
    def run_execute_cancel(state: DiagnosisState) -> dict:
        # (70) 敏感操作不使用只读 Tool 的自动重试循环。
        def operation(current, trace, parent_id):
            # (70) 原模拟函数不修改 JSON 或数据库。
            execute_cancel_node(current, data_file, trace, parent_id, clock)
        # (69) 真正执行与人工等待使用不同跨度。
        return run_logged_node(state, "execute_cancel", operation)

    # (70) 失败说明沿用原有模板，不调用模型、不回显异常正文。
    def run_failure(state: DiagnosisState) -> dict:
        # (70) 执行失败分支仍然保留此前的业务结果和引用。
        def operation(current, trace, parent_id):
            # (70) 失败模板不能把外部 Tool error 自由文本直接拼到 Console。
            safe_state = {**current, "tool_results": []}
            # (70) 原有预算、超时与重试原因继续使用既有说明。
            current.update(recovery.failure_node(safe_state))
            # (70) 为综合课程补充两种明确的结束原因。
            if current["stop_reason"] in ("context_budget", "approval_invalid"):
                # (70) 只输出程序固定文字，不输出无效参数本身。
                current["answer"] = "上下文预算不足，本轮结束。" if current["stop_reason"] == "context_budget" else "审批参数无效，未执行模拟取消。"
            # (70) 敏感执行异常不能说成确定没有执行，也不能自动重试。
            if current["stop_reason"] == "action_error":
                # (70) 保留结果不确定的边界，实际演示仍只模拟、不写业务数据。
                current["answer"] = "模拟执行异常，操作结果未确认；本轮停止，不自动重试。"
        # (69) 可以直接从追踪记录看到进入了失败节点。
        return run_logged_node(state, "failure", operation)

    # (70) 统一补齐未执行请求、保留结果，然后结束本轮。
    def run_finish(state: DiagnosisState) -> dict:
        # (70) finish 的消息配对与耗时计算继续使用原来的函数。
        def operation(current, trace, parent_id):
            # (70) 未执行不等于查询成功且无记录。
            current.update(recovery.finish_node(current, clock))
        # (69) 完成最后一个图节点后再汇总整轮记录。
        current = run_logged_node(state, "finish", operation)
        # (69) 不将父节点、Tool、RAG 子步骤重复加到模型费用中。
        trace = TraceRecorder(current, clock)
        # (69) 整轮跨度明确包含人工等待和 Debug 停顿。
        trace.finish(current["run_span"], current["stop_reason"])
        # (69) 用量未知与预算预留分别显示，不把未知当成零。
        current["trace_summary"] = trace.summary()
        # (70) 结束后重复 Command 没有待执行节点，不重做模拟取消。
        return current

    # (70) 准备好目标才进入审批，重复或失败则按当前 State 继续路由。
    def choose_approval_route(state: DiagnosisState) -> str:
        # (70) 已失败的准备不能让人继续批准。
        if state["stop_reason"]:
            # (70) 由统一失败节点解释。
            return "failure"
        # (70) 只有实际生成新请求时才等待人工输入。
        return "approval" if state["approval_request"] else choose_next_route(state)

    # (70) 有效确认才去执行节点，拒绝或无效参数按原结束原因收尾。
    def choose_approved_route(state: DiagnosisState) -> str:
        # (70) 不将人工确认当成一次新的模型决策。
        return "execute_cancel" if not state["stop_reason"] else choose_next_route(state)

    # (70) 共享 State 包含业务、Memory、预算、审批与脱敏追踪信息。
    graph = StateGraph(DiagnosisState)
    # (70) 注册新问题准备节点。
    graph.add_node("prepare", run_prepare)
    # (70) 注册外层模型节点。
    graph.add_node("model", run_model)
    # (70) 注册逐条只读 Tool 节点。
    graph.add_node("tools", run_tools)
    # (70) 注册审批信息准备节点。
    graph.add_node("prepare_approval", run_prepare_approval)
    # (70) 注册动态暂停节点。
    graph.add_node("approval", run_approval)
    # (70) 注册只模拟一次的敏感执行节点。
    graph.add_node("execute_cancel", run_execute_cancel)
    # (70) 注册受控失败与统一收尾节点。
    graph.add_node("failure", run_failure)
    # (70) 所有结束路径都经过 finish 配齐消息和统计。
    graph.add_node("finish", run_finish)
    # (70) 只有新问题从 START 开始，Command 恢复沿用暂停节点。
    graph.add_edge(START, "prepare")
    # (70) 保留原输入有效则调用模型的路由。
    graph.add_conditional_edges("prepare", recovery.choose_start_route, {"model": "model", "failure": "failure"})
    # (70) 模型、普通工具和敏感执行共用按 State 判断的条件边。
    for node in ("model", "tools", "execute_cancel"):
        # (70) 最终回答、失败、普通 Tool 和新审批分别路由。
        graph.add_conditional_edges(node, choose_next_route, {"model": "model", "tools": "tools", "prepare_approval": "prepare_approval", "failure": "failure", "finish": "finish"})
    # (70) 准备节点已经单独提交，下一次恢复不再重做。
    graph.add_conditional_edges("prepare_approval", choose_approval_route, {"approval": "approval", "model": "model", "tools": "tools", "prepare_approval": "prepare_approval", "failure": "failure", "finish": "finish"})
    # (70) 只有有效批准才能走执行节点，拒绝和无效参数分别收尾。
    graph.add_conditional_edges("approval", choose_approved_route, {"execute_cancel": "execute_cancel", "failure": "failure", "finish": "finish"})
    # (70) 失败也要配齐 Tool 消息，不留半套协议到下一轮。
    graph.add_edge("failure", "finish")
    # (70) 到 END 后不会自动回到模型或重试。
    graph.add_edge("finish", END)
    # (70) 调度次数与模型次数不同，留出工具、审批与失败分支的余量。
    recursion_limit = 4 * trusted_limits["max_steps"] + 4 * trusted_limits["max_tool_calls"] + 20
    # (70) 继续使用已有内存 Checkpointer，不连接数据库存档器。
    return graph.compile(checkpointer=checkpointer).with_config({"recursion_limit": recursion_limit})
