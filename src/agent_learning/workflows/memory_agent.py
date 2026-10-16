import json
from pathlib import Path
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from agent_learning.business.tools import DEFAULT_DATA_FILE
from agent_learning.core.models import SearchFilter
from agent_learning.rag.answering import RAGPipeline
from agent_learning.workflows.rag_agent import AgentState, TOOL_SCHEMAS, choose_continue_route, choose_model_route, model_node, prepare_node, tools_node
from agent_learning.workflows.tool_model import CompatibleToolModel


# 只补充多轮追问的规则，不增加摘要模型或长期记忆。
MEMORY_PROMPT = (
    # 模型可以根据保留的历史理解代词；被裁掉的信息不能凭空补回。
    "这是多轮会话，可用保留的历史理解追问；历史中缺少订单编号时先询问，不猜编号。"
    # 历史帮助理解问题，但不能证明业务状态仍然没有变化。
    "历史工具结果不是实时状态；用户询问现在或最新状态时重新查询业务工具。"
)


# 方法功能：计算消息与工具说明的 JSON 字符数，作为本课的简单上下文预算。
#（67课调整）允许计入新增工具说明；旧课程仍使用原来的四个工具。
def context_size(messages: list, tool_schemas: list | None = None) -> int:
    #（67课调整）计算实际消息与本图工具说明的 JSON 字符数，不是精确 Token 数。
    return len(json.dumps({"messages": messages, "tools": TOOL_SCHEMAS if tool_schemas is None else tool_schemas}, ensure_ascii=False))


# 方法功能：按完整问答轮次裁剪历史，始终保留 system 和当前轮次。
#（67课调整）新增可选工具说明参数，保证裁剪依据与本次模型请求一致。
def trim_messages(messages: list, max_history_turns: int, max_context_chars: int, tool_schemas: list | None = None) -> list:
    # 空历史暂时没有可裁剪的内容。
    if not messages:
        # 返回新的空列表，不修改调用方的数据。
        return []
    # 第一条 system 是程序提供的可信规则，不参与历史删除。
    system = messages[0]
    # 每个子列表是一条 user 消息及其后续 assistant / tool 消息。
    turns = []
    # 从 system 后开始分组，工具请求与结果保留在同一轮中。
    for message in messages[1:]:
        # 新 user 消息表示新一轮问题。
        if message["role"] == "user":
            # 开始一个新的完整轮次。
            turns.append([message])
        # 当前轮中的所有模型和工具消息一起保存。
        elif turns:
            # 不按单条消息切割，避免留下孤立的 tool_call_id。
            turns[-1].append(message)
    # 没有 user 时只保留 system。
    if not turns:
        # 正常 prepare 会在它后面追加新的 user。
        return [system]
    # 当前轮之外，最多保留指定数量的旧轮次。
    turns = turns[-(max_history_turns + 1):]
    # 展开轮次列表，顺序与原消息一致。
    kept = [system] + [message for turn in turns for message in turn]
    #（67课调整）根据本图的工具说明检查预算，只删除最旧的完整轮次。
    while len(turns) > 1 and context_size(kept, tool_schemas) > max_context_chars:
        # 整轮删除，因此 assistant 工具请求和 tool 结果会一起离开上下文。
        turns.pop(0)
        # 重新计算剩余消息，预算判断包含工具说明。
        kept = [system] + [message for turn in turns for message in turn]
    # 当前轮本身超预算时也完整返回，由模型节点决定受控结束。
    return kept


#-- 复用的--
# 方法功能：复用原 prepare 的输入校验与本轮字段初始化，只改变消息历史的保留方式。
def prepare_memory_node(state: AgentState, filters: SearchFilter, max_history_turns: int, max_context_chars: int) -> dict:
    # 沿用原来的问题与租户校验，同时清空本轮工具结果、结束原因和答案。
    current = prepare_node(state, filters)
    # 无效输入仍直接结束，不把历史发给模型。
    if current["stop_reason"]:
        # 输入错误不能覆盖已保留的会话内容，也不追加无效 user 消息。
        current["messages"] = list(state.get("messages", []))
        # 沿用上一课的 invalid_input 说明。
        return current
    # 这里的历史由相同 thread_id 的 Checkpointer 自动带入。
    history = state.get("messages", [])
    # 原 prepare 创建了新的 system 字典，可安全补充多轮规则。
    current["messages"][0]["content"] += MEMORY_PROMPT
    # 保留新 system，接上旧会话内容，最后追加本次 user；不重复旧 system。
    messages = current["messages"][:1] + history[1:] + current["messages"][1:]
    # 新一轮开始时先限制历史轮数与上下文字符数。
    current["messages"] = trim_messages(messages, max_history_turns, max_context_chars)
    # 仍使用原来的七个 State 字段，没有额外摘要或日志字段。
    return current


#-- 复用的--
# 方法功能：每次模型请求前检查上下文，再复用原 model 节点的 Tool Calling 与回答判断。
#（67课调整）工具说明可由新课程传入；其余 Memory 与结束判断保持不变。
def memory_model_node(state: AgentState, model: CompatibleToolModel, max_history_turns: int, max_context_chars: int, tool_schemas: list | None = None) -> dict:
    #（67课调整）每次模型请求前，按实际工具说明裁剪历史。
    messages = trim_messages(state["messages"], max_history_turns, max_context_chars, tool_schemas)
    #（67课调整）当前轮连同本图工具说明仍超预算时，不发出模型请求。
    if context_size(messages, tool_schemas) > max_context_chars:
        # 保留完整消息和已取得的 Tool 结果，避免发送残缺的工具协议。
        return {"messages": messages, "pending_tool_calls": [], "stop_reason": "context_budget", "answer": "当前轮问题或工具结果超过上下文字符预算，本轮结束；请缩短问题或调整 MAX_CONTEXT_CHARS。"}
    # 用普通字典副本将裁剪后的消息交给原模型节点。
    current = dict(state)
    # 只替换本次模型可见的消息，不改业务问题和权限身份。
    current["messages"] = messages
    # 即使原节点返回 model_error，也要把本次裁剪写回 State。
    update = {"messages": messages}
    #（67课调整）将实际工具说明传给原模型节点，保留消息和最终回答的处理。
    update.update(model_node(current, model, tool_schemas=tool_schemas))
    # LangGraph 将更新字典写回本会话 State。
    return update


#-- 复用的--
# 方法功能：沿用 prepare / model / tools 编排和条件路由，只替换前两个节点为 Memory 包装。
def build_graph(model: CompatibleToolModel, pipeline: RAGPipeline, filters: SearchFilter, checkpointer: InMemorySaver, data_file: Path = DEFAULT_DATA_FILE, max_history_turns: int = 2, max_context_chars: int = 12000):
    # 仍然只查规则资料，不能把知识库订单快照当成当前业务事实。
    if filters.doc_type not in ("policy", "process", "faq"):
        # 沿用之前课程的资料边界。
        raise ValueError("本课知识库 DOC_TYPE 只能是 policy、process 或 faq，不能查询 record 快照。")
    # 两个预算来自建图参数，不从用户问题读取。
    if max_history_turns < 0 or max_context_chars < 1:
        # 历史可设为零轮，但字符预算必须是正数。
        raise ValueError("历史轮数不能为负，上下文字符预算必须为正。")
    #-- 复用的--
    # 方法功能：绑定可信过滤器和本课裁剪参数。
    def run_prepare(state: AgentState) -> dict:
        # 新问题进入 prepare；Checkpoint 已经读取本会话上一轮 State。
        return prepare_memory_node(state, filters, max_history_turns, max_context_chars)
    #-- 复用的--
    # 方法功能：绑定原模型与裁剪参数。
    def run_model(state: AgentState) -> dict:
        # 保留模型选择工具与最终回答的原流程。
        return memory_model_node(state, model, max_history_turns, max_context_chars)
    #-- 复用的--
    # 方法功能：直接复用业务 JSON 与 RAG Tool 节点。
    def run_tools(state: AgentState) -> dict:
        # 工具结果仍通过 role=tool 和 tool_call_id 回传。
        return tools_node(state, pipeline, filters, data_file)
    # 继续使用原来的七字段 State，不另建复杂的 Memory 对象。
    graph = StateGraph(AgentState)
    # 注册只增加历史保留的初始化节点。
    graph.add_node("prepare", run_prepare)
    # 注册每次调用前裁剪的模型节点。
    graph.add_node("model", run_model)
    # 注册完全复用的工具节点。
    graph.add_node("tools", run_tools)
    # 每个新问题从 prepare 开始，但不会清空已保留的 messages。
    graph.add_edge(START, "prepare")
    # 原路由仍按 stop_reason 判断是否继续。
    graph.add_conditional_edges("prepare", choose_continue_route, {"model": "model", "end": END})
    # 有工具请求才进入 tools，否则结束本轮。
    graph.add_conditional_edges("model", choose_model_route, {"tools": "tools", "end": END})
    # 成功工具结果回模型；已处理的工具失败仍结束。
    graph.add_conditional_edges("tools", choose_continue_route, {"model": "model", "end": END})
    # 复用 Checkpointer 保存会话；本课不再逐次暂停 tools，只观察多轮追问。
    return graph.compile(checkpointer=checkpointer)
