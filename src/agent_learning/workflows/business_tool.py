# 导入 State 字段定义工具，与前几课保持同样的写法。
from typing import TypedDict
# 导入路径类，用于选择本课离线数据文件。
from pathlib import Path
# 导入前几课已经使用过的开始、结束和建图对象。
from langgraph.graph import END, START, StateGraph
# 导入阶段 3 风格的业务函数，不导入旧 MySQL 连接代码。
from agent_learning.business.tools import DEFAULT_DATA_FILE, get_order, tool_result


# 类职责：保存输入、可信租户、Tool 参数、Tool 结果和最终回答。
class WorkflowState(TypedDict):
    # 本课 Console 输入订单号，作为原始问题保存。
    question: str
    # 由入口指定的租户身份，不从 question 中生成。
    tenant_id: str
    # prepare 节点整理后的订单号。
    order_id: str
    # 本次实际调用的 Tool 名称。
    tool_name: str
    # Tool 返回的 success、data 和 error 字典。
    tool_result: dict
    # Tool 结果选中的 success 或 error 分支。
    branch: str
    # 最终可在 Console 显示的回答。
    answer: str


# 方法功能：把 Console 输入整理为本课 get_order 需要的订单号。
def prepare_node(state: WorkflowState) -> dict:
    # 本课只接受订单号，去掉两端空格并统一为大写。
    order_id = state["question"].strip().upper()
    # LangGraph 合并这个局部返回值，原始问题和租户仍然保留。
    return {"order_id": order_id}


# 方法功能：从 State 读取参数，调用业务 Tool，并把结果交回工作流。
def get_order_node(state: WorkflowState, data_file: Path = DEFAULT_DATA_FILE) -> dict:
    # 在节点边界接住 Tool 的意外异常，供本课观察失败分支。
    try:
        # 在这一行打断点并单步进入，可以看到真正执行的 Python Tool。
        result = get_order(state["order_id"], state["tenant_id"], data_file=data_file)
    # 预料之外的 Tool 异常也转换为统一失败结果。
    except Exception as error:
        # 在这一行打断点可查看 error；回答不输出内部异常细节。
        result = tool_result(False, error="订单 Tool 执行异常，请在 Debug 中检查异常原因。")
    # 节点负责更新 State，get_order 本身只负责查询并返回业务结果。
    return {"tool_name": "get_order", "tool_result": result}


# 方法功能：get_order 节点结束后，根据更新后的 Tool 结果选择路线。
def choose_result_route(state: WorkflowState) -> str:
    # 这里只判断 Tool 是否成功，不查询数据，也不修改 State。
    if state["tool_result"]["success"]:
        # 标签 success 将由 add_conditional_edges 映射到 answer 节点。
        return "success"
    # 空订单号、订单不存在或文件异常都进入 error_answer 节点。
    return "error"


# 方法功能：读取成功结果并生成确定性的订单说明。
def answer_node(state: WorkflowState) -> dict:
    # 这里读取的是 Tool 节点写回 State 的数据，不重新查询订单。
    order = state["tool_result"]["data"]
    # 直接使用业务数据中的状态与金额，不调用模型猜测事实。
    answer = f"订单 {order['order_id']}：{order['status']}，金额 {order['amount']} {order['currency']}。"
    # 明确说明数据来源和样例更新时间。
    answer += f"这是本地 JSON 模拟结果，截至 {order['updated_at']}。"
    # 保存成功分支标签和最终回答。
    return {"branch": "success", "answer": answer}


# 方法功能：把 Tool 的失败说明变成用户可以看到的提示。
def error_answer_node(state: WorkflowState) -> dict:
    # 读取原始失败原因，避免把文件异常说成订单不存在。
    error = state["tool_result"]["error"]
    # 保存失败分支标签，本课失败后直接结束，不重试或循环。
    return {"branch": "error", "answer": f"订单查询未完成：{error}"}


# 方法功能：建立 prepare → get_order → 成功或失败回答的工作流。
def build_graph(data_file: Path = DEFAULT_DATA_FILE):
    # 这个普通函数把本次选择的数据文件传给已有 Tool 节点。
    def run_get_order(state: WorkflowState) -> dict:
        # 节点职责仍在 get_order_node 中，可以在那里单步进入业务 Tool。
        return get_order_node(state, data_file)

    # 声明所有节点共同读写上面的 State。
    graph = StateGraph(WorkflowState)
    # 注册输入整理节点。
    graph.add_node("prepare", prepare_node)
    # 注册会调用 get_order 的节点，并绑定本课的数据文件。
    graph.add_node("get_order", run_get_order)
    # 注册成功回答节点。
    graph.add_node("answer", answer_node)
    # 注册失败回答节点。
    graph.add_node("error_answer", error_answer_node)
    # 运行开始时先整理订单号。
    graph.add_edge(START, "prepare")
    # prepare 返回 order_id 并更新 State 后，再执行订单 Tool 节点。
    graph.add_edge("prepare", "get_order")
    # get_order 节点结束后调用路由函数；两个回答分支每次只选一个。
    graph.add_conditional_edges("get_order", choose_result_route, {"success": "answer", "error": "error_answer"})
    # 成功回答之后结束，不进入工具循环。
    graph.add_edge("answer", END)
    # 失败说明之后也结束，避免本课引入无上限重试。
    graph.add_edge("error_answer", END)
    # 返回编译好的图，入口用 invoke 传入初始 State。
    return graph.compile()
