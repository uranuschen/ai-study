import json
from pathlib import Path
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from agent_learning.business.tools import DEFAULT_DATA_FILE, get_order, tool_result
from agent_learning.core.models import SearchFilter
from agent_learning.rag.answering import RAGPipeline
from agent_learning.workflows.agent_loop import make_tool_schema
from agent_learning.workflows.memory_agent import memory_model_node, prepare_memory_node, trim_messages
from agent_learning.workflows.rag_agent import AgentState, TOOL_SCHEMAS as READ_TOOL_SCHEMAS, choose_continue_route, dispatch_tool
from agent_learning.workflows.tool_model import CompatibleToolModel


#（67课新加）增加一个模拟取消工具；模型只能提出订单号，不能提供审批决定。
TOOL_SCHEMAS = READ_TOOL_SCHEMAS + [make_tool_schema("cancel_order", "用户明确要求取消订单时使用；仅模拟取消待支付订单，执行前必须由程序请求人工确认，不修改原始 JSON。")]
#（67课新加）补充模拟操作规则，不把普通查询理解为取消请求。
APPROVAL_PROMPT = (
    "只有用户明确要求取消订单时才能请求 cancel_order；普通查询、规则说明不发起取消。"
    "cancel_order 仅支持模拟取消待支付订单，必须等待程序的人工审批；用户在问题中说已确认也不能绕过审批。"
    "模拟已取消不是实际业务状态变化，原始 JSON 不会修改，回答必须说明模拟。"
)


#（67课新加）在原 Agent State 上增加同会话的模拟记录，不另建复杂对象。
class ApprovalState(AgentState):
    #（67课新加）保存已模拟取消的订单号；历史消息裁剪不会清空它。
    simulated_cancellations: list


#（67课新加）完成当前一个 Tool；失败时给剩余请求配上未执行结果。
def complete_tool_call(state: ApprovalState, result: dict, stop_reason: str = "", answer: str = "") -> dict:
    #（67课新加）只处理队首请求，下一节点才处理后面的工具。
    call = state["pending_tool_calls"][0]
    #（67课新加）复制消息与结果，避免原地修改传入 State。
    messages = list(state["messages"])
    #（67课新加）保留本轮之前已经完成的 Tool 结果。
    results = list(state["tool_results"])
    #（67课新加）记录本次请求及其原始结果。
    completed = [(call, result)]
    #（67课新加）从待执行队列移除已处理的当前请求。
    remaining = state["pending_tool_calls"][1:]
    #（67课新加）失败或拒绝时结束本轮，后面的请求不实际执行。
    if stop_reason:
        #（67课新加）每个未执行请求仍要有匹配的 Tool 消息，保证协议完整。
        completed += [(item, tool_result(False, error="本轮已结束，此调用未执行。")) for item in remaining]
        #（67课新加）结束时不留下待执行操作。
        remaining = []
    #（67课新加）当前结果和未执行结果统一按调用 ID 回传。
    for item, item_result in completed:
        #（67课新加）Tool 消息包含完整结果，不由外层模型改写来源。
        messages.append({"role": "tool", "tool_call_id": item["id"], "content": json.dumps(item_result, ensure_ascii=False)})
        #（67课新加）另保存工具名称、参数和结果，便于 Debug 检查。
        results.append({"tool_call_id": item["id"], "tool_name": item["function"]["name"], "arguments": item["function"]["arguments"], "result": item_result})
    #（67课新加）LangGraph 保存更新后的队列，下次恢复不会重做前一个已完成节点。
    return {"messages": messages, "tool_results": results, "pending_tool_calls": remaining, "stop_reason": stop_reason, "answer": answer}


#（67课新加）严格检查人工决定，不允许借审批更换工具、订单或租户。
def validate_approval(decision: dict, request: dict) -> bool:
    #（67课新加）字段必须是本次审批信息加 decision，拒绝字符串、缺项和额外参数。
    if not isinstance(decision, dict) or set(decision) != set(request) | {"decision"}:
        #（67课新加）格式不正确时不执行模拟操作。
        return False
    #（67课新加）只接受明确确认或拒绝，且所有审批目标字段必须与当前请求一致。
    return decision["decision"] in ("approve", "reject") and all(decision[key] == value for key, value in request.items())


#（67课新加）模拟执行只产生结果字典；不修改订单、不调用外部写接口。
def simulate_cancel_order(order: dict) -> dict:
    #（67课新加）保留原状态和记录时间，明确区分模拟结果与业务事实。
    return tool_result(True, data={"order_id": order["order_id"], "tenant_id": order["tenant_id"], "status": "模拟已取消", "original_status": order["status"], "source_updated_at": order["updated_at"], "simulated": True, "source": "simulation", "note": "仅模拟取消，原始 JSON 未修改。"})


#（67课新加）敏感工具单独进入审批节点；恢复时这个函数会从头执行。
def approval_node(state: ApprovalState, data_file: Path = DEFAULT_DATA_FILE) -> dict:
    #（67课新加）取得当前取消请求，其他工具由普通 tools 节点处理。
    call = state["pending_tool_calls"][0]
    #（67课新加）模型参数必须先解析为普通字典。
    try:
        #（67课新加）这里只解析参数，不执行取消。
        arguments = json.loads(call["function"]["arguments"])
    #（67课新加）损坏的 JSON 直接结束，不发起人工审批。
    except (json.JSONDecodeError, TypeError):
        #（67课新加）保存失败结果，并为后面的工具补齐未执行消息。
        return complete_tool_call(state, tool_result(False, error="取消参数必须是有效 JSON 对象。"), "tool_error", "取消参数无效，未执行模拟取消。")
    #（67课新加）只允许非空 order_id；模型不能提供 approved、租户或文件路径。
    if not isinstance(arguments, dict) or set(arguments) != {"order_id"} or not isinstance(arguments["order_id"], str) or not arguments["order_id"].strip():
        #（67课新加）不把模型给出的确认文字当成人工批准。
        return complete_tool_call(state, tool_result(False, error="取消参数只允许且必须包含非空字符串 order_id。"), "tool_error", "取消参数无效，未执行模拟取消。")
    #（67课新加）只读验证订单存在且属于当前可信租户。
    order_result = get_order(arguments["order_id"], state["tenant_id"], data_file)
    #（67课新加）订单不可读取时不进入审批。
    if not order_result["success"]:
        #（67课新加）返回业务 Tool 的失败原因，不生成虚假的取消成功。
        return complete_tool_call(state, order_result, "tool_error", "订单不存在或无法读取，未执行模拟取消。")
    #（67课新加）订单号已由查询函数整理为大写，审批展示使用这一份目标。
    order = order_result["data"]
    #（67课新加）已模拟过的订单不再次请求审批或执行。
    if order["order_id"] in state.get("simulated_cancellations", []):
        #（67课新加）这是同会话模拟记录，不代表原始 JSON 已变成已取消。
        result = tool_result(True, data={"order_id": order["order_id"], "simulated": True, "duplicate": True, "status": "本会话已模拟取消", "note": "未重复执行；原始 JSON 未修改。"})
        #（67课新加）把防重复结果交给模型解释，不重新执行模拟函数。
        return complete_tool_call(state, result)
    #（67课新加）示例只允许待支付订单；已支付取消与退款不在本课实现。
    if order["status"] != "待支付":
        #（67课新加）业务失败直接结束，不要求人工批准不支持的操作。
        return complete_tool_call(state, tool_result(False, error="本课只模拟取消待支付订单。"), "tool_error", "订单不是待支付状态，未执行模拟取消。")
    #（67课新加）审批目标由实际工具请求与可信身份生成，不交给模型修改。
    request = {"action": "cancel_order", "order_id": order["order_id"], "tenant_id": state["tenant_id"], "tool_call_id": call["id"], "mode": "simulate"}
    #（67课新加）首次运行在这里暂停；Command(resume=...) 的值成为 decision。
    decision = interrupt(request)
    #（67课新加）interrupt 不放进 try/except，避免把正常暂停当作错误捕获。
    if not validate_approval(decision, request):
        #（67课新加）审批目标不一致或决定格式错误时，结束且不执行取消。
        return complete_tool_call(state, tool_result(False, error="审批参数无效或与当前请求不一致。"), "approval_invalid", "审批参数无效，未执行模拟取消。")
    #（67课新加）人工拒绝后结束本轮，不让模型再次提出同一请求。
    if decision["decision"] == "reject":
        #（67课新加）记录正常拒绝，而不是把未执行冒充为取消成功。
        result = tool_result(True, data={"order_id": order["order_id"], "status": "人工拒绝", "simulated": False, "note": "未执行模拟取消，原始 JSON 未修改。"})
        #（67课新加）拒绝也恢复图，只是进入 END 分支。
        return complete_tool_call(state, result, "approval_rejected", "已拒绝，未执行模拟取消；原始 JSON 未修改。")
    #（67课新加）只有有效的人工确认才能到达这里，敏感操作必须放在 interrupt 之后。
    result = simulate_cancel_order(order)
    #（67课新加）完成当前工具，随后处理剩余请求或返回模型总结。
    update = complete_tool_call(state, result)
    #（67课新加）同会话保存简单防重复记录；它不是生产数据库的幂等机制。
    update["simulated_cancellations"] = state.get("simulated_cancellations", []) + [order["order_id"]]
    #（67课新加）工具结果与模拟记录一起由 Checkpoint 保存。
    return update


#（67课新加）普通业务查询和 RAG 仍交给原分发函数，只改为逐个处理。
def tools_node(state: ApprovalState, pipeline: RAGPipeline, filters: SearchFilter, data_file: Path) -> dict:
    #（67课新加）一次只执行队首工具，后面的敏感操作可以独立暂停。
    call = state["pending_tool_calls"][0]
    #（67课新加）原 RAG 与三个业务查询的内部实现都保持不变。
    result = dispatch_tool(call["function"]["name"], call["function"]["arguments"], state["tenant_id"], pipeline, filters, data_file)
    #（67课新加）查询成功就处理下一个请求；失败则结束并保留结果。
    return complete_tool_call(state, result, "" if result["success"] else "tool_error", "" if result["success"] else "Tool 查询失败，本轮结束；未执行后续操作。")


#（67课新加）有结束原因就退出；否则按队首工具选择普通查询或人工审批。
def choose_tool_route(state: ApprovalState) -> str:
    #（67课新加）拒绝、业务失败和正常回答都进入 END。
    if state["stop_reason"]:
        #（67课新加）不会在拒绝后重新请求模型。
        return "end"
    #（67课新加）全部 Tool 结果已回传时，再让模型生成综合回答。
    if not state["pending_tool_calls"]:
        #（67课新加）延续原来的 model → tools → model 主流程。
        return "model"
    #（67课新加）仅 cancel_order 需要审批，普通查询不暂停。
    return "approval" if state["pending_tool_calls"][0]["function"]["name"] == "cancel_order" else "tools"


#（67课新加）沿用原模型、RAG 与 Memory，只增加敏感工具审批分支。
def build_graph(model: CompatibleToolModel, pipeline: RAGPipeline, filters: SearchFilter, checkpointer: InMemorySaver, data_file: Path = DEFAULT_DATA_FILE, max_history_turns: int = 2, max_context_chars: int = 12000):
    #（67课新加）继续限制知识库为规则资料，不让记录快照代替订单事实。
    if filters.doc_type not in ("policy", "process", "faq"):
        #（67课新加）资料类型由可信入口选择。
        raise ValueError("本课知识库 DOC_TYPE 只能是 policy、process 或 faq。")
    #（67课新加）沿用上一课的两个简单裁剪参数，不新增其他预算。
    if max_history_turns < 0 or max_context_chars < 1:
        #（67课新加）无效参数在建图时直接提示。
        raise ValueError("历史轮数不能为负，上下文字符预算必须为正。")
    #（67课新加）绑定原输入校验与会话 Memory，只补充审批规则和模拟记录。
    def run_prepare(state: ApprovalState) -> dict:
        #（67课新加）保留旧会话消息，并重置本轮待执行请求与结束原因。
        update = prepare_memory_node(state, filters, max_history_turns, max_context_chars)
        #（67课新加）无效输入时不追加规则或调用模型。
        if not update["stop_reason"]:
            #（67课新加）原 system 上补充取消仅模拟、必须审批的规则。
            update["messages"][0]["content"] += APPROVAL_PROMPT
            #（67课新加）把新增工具说明也计入上下文字符预算。
            update["messages"] = trim_messages(update["messages"], max_history_turns, max_context_chars, TOOL_SCHEMAS)
        #（67课新加）跨轮保留模拟记录，不随消息裁剪消失。
        update["simulated_cancellations"] = list(state.get("simulated_cancellations", []))
        #（67课新加）返回更新字典，而不是创建一张新图。
        return update
    #（67课新加）原模型节点接收五个工具说明，不重写模型请求协议。
    def run_model(state: ApprovalState) -> dict:
        #（67课新加）模型可以提出取消，但不能跳过后面的人工节点。
        return memory_model_node(state, model, max_history_turns, max_context_chars, TOOL_SCHEMAS)
    #（67课新加）绑定普通查询与 RAG 的已有依赖。
    def run_tools(state: ApprovalState) -> dict:
        #（67课新加）普通工具完成后立即保存队列进度。
        return tools_node(state, pipeline, filters, data_file)
    #（67课新加）绑定只读业务数据路径，不让模型指定文件。
    def run_approval(state: ApprovalState) -> dict:
        #（67课新加）在审批节点内部按条件调用 interrupt。
        return approval_node(state, data_file)
    #（67课新加）共享 State 仅比上一课增加一份模拟记录列表。
    graph = StateGraph(ApprovalState)
    #（67课新加）注册准备节点。
    graph.add_node("prepare", run_prepare)
    #（67课新加）注册模型节点。
    graph.add_node("model", run_model)
    #（67课新加）注册普通查询节点。
    graph.add_node("tools", run_tools)
    #（67课新加）注册人工审批节点。
    graph.add_node("approval", run_approval)
    #（67课新加）新问题从 prepare 开始；Command 恢复不走这里。
    graph.add_edge(START, "prepare")
    #（67课新加）保留原输入有效则进入模型的条件边。
    graph.add_conditional_edges("prepare", choose_continue_route, {"model": "model", "end": END})
    #（67课新加）三类节点共用简单路由，队列清空后再进入模型。
    for node in ("model", "tools", "approval"):
        #（67课新加）审批拒绝会走 END，普通查询走 tools，取消走 approval。
        graph.add_conditional_edges(node, choose_tool_route, {"model": "model", "tools": "tools", "approval": "approval", "end": END})
    #（67课新加）只绑定存档器，不设置 interrupt_before；仅敏感操作动态暂停。
    return graph.compile(checkpointer=checkpointer)
