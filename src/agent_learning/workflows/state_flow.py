from typing import TypedDict

from langgraph.graph import END, START, StateGraph


# 类职责：定义两个节点共同读写的 State 字段。
# question 是原始输入，clean_question 由第一个节点写入，answer 由第二个节点写入。
class WorkflowState(TypedDict):
    # 保存入口传进来的原始文字。
    question: str
    # 保存第一个节点整理后的文字，供第二个节点读取。
    clean_question: str
    # 保存第二个节点生成的最终输出。
    answer: str


# 方法功能：整理入口文字，只更新 State 中的 clean_question。
def prepare_node(state: WorkflowState) -> dict:
    # 读取入口传入的原始文字并去掉首尾空格。
    clean_question = state["question"].strip()
    # LangGraph 会将这个字段写回共享 State。
    return {"clean_question": clean_question}


# 方法功能：读取上一个节点写入的字段，只更新 State 中的 answer。
def answer_node(state: WorkflowState) -> dict:
    # 这里读的是 prepare_node 写入的结果，不直接读取入口的 question。
    clean_question = state["clean_question"]
    # 返回本节点的更新，其他 State 字段会保留。
    return {"answer": f"第二个节点收到：{clean_question}"}


# 方法功能：连接两个节点并编译成可运行的工作流。
# 执行顺序是 START → prepare → answer → END。
def build_graph():
    # 声明所有节点共用上面的 State 字段。
    graph = StateGraph(WorkflowState)
    # 注册第一个节点，负责写入 clean_question。
    graph.add_node("prepare", prepare_node)
    # 注册第二个节点，负责读取 clean_question 并写入 answer。
    graph.add_node("answer", answer_node)
    # 从开始位置进入第一个节点。
    graph.add_edge(START, "prepare")
    # 第一个节点完成后，才执行第二个节点。
    graph.add_edge("prepare", "answer")
    # 第二个节点完成后结束。
    graph.add_edge("answer", END)
    # 编译后才能调用 graph.invoke() 执行。
    return graph.compile()
