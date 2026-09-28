from typing import TypedDict

from langgraph.graph import END, START, StateGraph


# 这个固定前缀只是本课的路由规则，后续课程再学习更复杂的意图识别。
TOOL_PREFIX = "统计字数："


# 类职责：保存原始问题、整理后的问题、选中的分支和最终输出。
class WorkflowState(TypedDict):
    # 入口传入的原始文字。
    question: str
    # prepare 节点整理后的文字，供路由函数和后续节点读取。
    clean_question: str
    # 实际执行的分支，方便在 Console 和断点中观察。
    branch: str
    # 当前分支生成的最终输出。
    answer: str


# 方法功能：去掉原始问题首尾的空格，写入共享 State。
def prepare_node(state: WorkflowState) -> dict:
    # 读取原始问题并整理文字。
    clean_question = state["question"].strip()
    # LangGraph 把返回的字段合并到共享 State。
    return {"clean_question": clean_question}


# 方法功能：根据整理后的问题，决定下一步走普通分支还是 Tool 分支。
def choose_route(state: WorkflowState) -> str:
    # 带固定前缀的问题交给本地 Tool；这是教学规则，不是模型意图识别。
    if state["clean_question"].startswith(TOOL_PREFIX):
        # 返回的标签会被 add_conditional_edges 映射到 tool 节点。
        return "tool"
    # 其他问题进入普通演示回答节点。
    return "normal"


# 方法功能：演示普通问答分支；本课只回显问题，不调用 LLM。
def normal_answer_node(state: WorkflowState) -> dict:
    # 记录实际走过的分支，并生成便于观察的演示输出。
    return {"branch": "normal", "answer": f"普通问答分支收到：{state['clean_question']}"}


# 方法功能：作为本课的本地 Tool，统计一段文字的字符数。
def count_characters(text: str) -> int:
    # Python 的 len 会把文字中的空格和标点也算作字符。
    return len(text)


# 方法功能：从问题中取出待统计文字，调用本地 Tool 并写入回答。
def tool_node(state: WorkflowState) -> dict:
    # 去掉指令前缀，只统计冒号后面的文字。
    content = state["clean_question"][len(TOOL_PREFIX):].strip()
    # 真正调用本地 Tool，便于在此处打断点观察参数和返回值。
    character_count = count_characters(content)
    # 记录实际走过 Tool 分支及统计结果。
    return {"branch": "tool", "answer": f"Tool 统计结果：{content}，共 {character_count} 个字符。"}


# 方法功能：连接准备节点和两个互斥分支，编译为可运行的 LangGraph 图。
def build_graph():
    # 所有节点读写同一份 WorkflowState。
    graph = StateGraph(WorkflowState)
    # 注册负责整理问题的节点。
    graph.add_node("prepare", prepare_node)
    # 注册普通演示回答节点。
    graph.add_node("normal_answer", normal_answer_node)
    # 注册会调用本地函数的 Tool 节点。
    graph.add_node("tool", tool_node)
    # 从 START 进入准备节点。
    graph.add_edge(START, "prepare")
    # prepare 结束后调用 choose_route；每次只会执行映射中的一个分支。
    graph.add_conditional_edges("prepare", choose_route, {"normal": "normal_answer", "tool": "tool"})
    # 普通分支完成后结束。
    graph.add_edge("normal_answer", END)
    # Tool 分支完成后结束。
    graph.add_edge("tool", END)
    # 编译后才可以调用 graph.invoke() 执行。
    return graph.compile()
