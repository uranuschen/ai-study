from typing import TypedDict

from langgraph.graph import END, START, StateGraph


# 类职责：规定单节点工作流在节点之间传递哪些字段。
# question 是入口给出的文字；answer 是节点写回的结果。
class ConsoleState(TypedDict):
    # 保存用户在 Console 输入的文字。
    question: str
    # 保存节点处理后的输出文字。
    answer: str


# 方法功能：读取 State 中的问题，返回本节点要更新的 answer 字段。
# LangGraph 会把返回的字典合并到 State，而不是要求节点返回整个 State。
def echo_node(state: ConsoleState) -> dict:
    # 从 State 读取用户输入。
    question = state["question"]
    # 只生成演示文字，本阶段不调用模型或数据库。
    return {"answer": f"单节点收到：{question}"}


# 方法功能：创建并编译只有一个节点的 LangGraph 工作流。
# 执行顺序固定为 START → echo → END。
def build_graph():
    # 用上面的字段定义创建共享 State 图。
    graph = StateGraph(ConsoleState)
    # 把普通 Python 函数注册为图中的一个节点。
    graph.add_node("echo", echo_node)
    # 指定从开始位置进入 echo 节点。
    graph.add_edge(START, "echo")
    # 指定 echo 执行后结束工作流。
    graph.add_edge("echo", END)
    # 编译后才能调用 graph.invoke() 执行。
    return graph.compile()
