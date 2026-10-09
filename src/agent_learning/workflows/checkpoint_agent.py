from pathlib import Path
from langgraph.graph import END, START, StateGraph
from agent_learning.business.tools import DEFAULT_DATA_FILE
from agent_learning.core.models import SearchFilter
from agent_learning.workflows.rag_agent import AgentState, choose_continue_route, choose_model_route, model_node, prepare_node, tools_node


# 方法功能：复用上一课三个节点，只增加状态保存和 Tool 前暂停。
def build_graph(model, pipeline, filters: SearchFilter, checkpointer, data_file: Path = DEFAULT_DATA_FILE):
    # 沿用上一课的规则资料范围，不把订单快照当成当前事实。
    if filters.doc_type not in ("policy", "process", "faq"):
        # 错误配置在执行前暴露。
        raise ValueError("本课知识库 DOC_TYPE 只能是 policy、process 或 faq，不能查询 record 快照。")
    # 绑定入口提供的可信过滤条件。
    def run_prepare(state: AgentState) -> dict:
        # 只在新输入开始时初始化；恢复时不会重新走这个节点。
        return prepare_node(state, filters)
    # 绑定真实模型或离线替身。
    def run_model(state: AgentState) -> dict:
        # 模型异常抛出后留在此节点，手动恢复会从该节点开头再执行。
        return model_node(state, model, raise_errors=True)
    # 绑定原来的 RAG 和 JSON 查询，不新增业务流程。
    def run_tools(state: AgentState) -> dict:
        # Tool 的已处理失败仍走 END，本课不改成自动重试。
        return tools_node(state, pipeline, filters, data_file)
    # 仍使用上一课相同的七个 State 字段。
    graph = StateGraph(AgentState)
    # 注册初始化节点。
    graph.add_node("prepare", run_prepare)
    # 注册模型节点。
    graph.add_node("model", run_model)
    # 注册工具节点。
    graph.add_node("tools", run_tools)
    # 新输入从 prepare 开始。
    graph.add_edge(START, "prepare")
    # 输入有效才进入模型，否则结束。
    graph.add_conditional_edges("prepare", choose_continue_route, {"model": "model", "end": END})
    # 模型选择工具才进入 tools，有回答就结束。
    graph.add_conditional_edges("model", choose_model_route, {"tools": "tools", "end": END})
    # 成功的 Tool 结果回传给模型，已处理的 Tool 失败则结束。
    graph.add_conditional_edges("tools", choose_continue_route, {"model": "model", "end": END})
    # 保存 State；每次进入 tools 前先暂停，用 invoke(None, 同一 config) 继续。
    return graph.compile(checkpointer=checkpointer, interrupt_before=["tools"])
