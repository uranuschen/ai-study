from typing import TypedDict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


# 最简演示只保存输入、回答和是否完成。
class PauseState(TypedDict):
    # 入口传入的文字，恢复时继续使用。
    question: str
    # 复用现有会话入口提供的身份。
    tenant_id: str
    # 每一步生成的演示回答。
    answer: str
    # 沿用现有 Service 的业务完成判断。
    stop_reason: str


# 第一步执行后，框架会在第二步之前暂停。
def prepare_node(state: PauseState) -> dict:
    # 返回第一步结果，原问题仍保存在 State 中。
    return {"answer": "第一步已执行，等待继续。", "stop_reason": ""}


# 第二次请求恢复后，读取之前保存的问题。
def answer_node(state: PauseState) -> dict:
    # 直接生成演示文字，不调用模型或工具。
    return {
        "answer": f"第二步已执行，之前保存的问题是：{state['question']}",
        "stop_reason": "final_answer",
    }


# 固定的两节点图，只演示暂停与恢复。
def build_graph(checkpointer: InMemorySaver) -> CompiledStateGraph:
    # 声明两步共用的 State。
    graph = StateGraph(PauseState)
    # 注册第一步。
    graph.add_node("prepare", prepare_node)
    # 注册第二步。
    graph.add_node("answer", answer_node)
    # 开始后先执行第一步。
    graph.add_edge(START, "prepare")
    # 第一步完成后准备执行第二步。
    graph.add_edge("prepare", "answer")
    # 第二步完成后结束。
    graph.add_edge("answer", END)
    # 保存执行状态，并固定在 answer 节点前暂停。
    return graph.compile(checkpointer=checkpointer, interrupt_before=["answer"])
