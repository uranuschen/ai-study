# 导入路径类，用于接收入口提供的 JSON 文件位置。
from pathlib import Path
# 导入 TypedDict，用来说明 State 字典中保存哪些字段。
from typing import TypedDict
# 导入 LangGraph 的起点、终点和图构建类。
from langgraph.graph import END, START, StateGraph
# 导入三个只读业务 Tool 和统一结果函数。
from agent_learning.business.tools import DEFAULT_DATA_FILE, get_order, get_payment, get_refund, tool_result


# 类的作用：说明多步工作流共享的 State 字段，不会自动执行业务查询。
class WorkflowState(TypedDict):
    # 保存 Console 原始输入。
    question: str
    # 保存可信入口提供的租户身份。
    tenant_id: str
    # 保存 prepare 整理后的订单号。
    order_id: str
    # 单独保存订单 Tool 的完整结果，后续节点不覆盖它。
    order_result: dict
    # 单独保存支付 Tool 的完整结果，{} 表示尚未查询。
    payment_result: dict
    # 单独保存退款 Tool 的完整结果，{} 表示尚未查询。
    refund_result: dict
    # 保存实际调用的 Tool 名称，便于观察哪些步骤被跳过。
    executed_tools: list
    # 保存总结节点确定的业务结束分支。
    branch: str
    # 保存根据已有业务结果生成的总结。
    answer: str


# 方法功能：整理订单号，并为这次查询准备独立的结果字段。
def prepare_node(state: WorkflowState) -> dict:
    # 去掉两端空格，并将样例订单号转为大写。
    order_id = state["question"].strip().upper()
    # 返回需要写入 State 的字段，租户身份保持入口提供的原值。
    return {
        # 订单号从这里传给后续三个 Tool。
        "order_id": order_id,
        # 订单节点执行前还没有订单结果。
        "order_result": {},
        # 支付节点未执行时保持 {}，不是没有支付记录的 []。
        "payment_result": {},
        # 退款节点未执行时保持 {}，不是没有退款记录的 []。
        "refund_result": {},
        # 每次调用从空的 Tool 执行列表开始。
        "executed_tools": [],
        # 结束分支由总结节点写入。
        "branch": "",
        # 总结节点执行前没有最终回答。
        "answer": "",
    # 结束返回字典。
    }


# 方法功能：查询订单，只更新订单结果和 Tool 执行列表。
def get_order_node(state: WorkflowState, data_file: Path = DEFAULT_DATA_FILE) -> dict:
    # 防止意外的 Python 异常直接中断整个工作流。
    try:
        # 订单号和租户来自 State，文件路径来自入口配置。
        result = get_order(state["order_id"], state["tenant_id"], data_file=data_file)
    # 意外异常与正常的 Tool 失败一样交给业务分支处理。
    except Exception as error:
        # Debug 时在这里查看 error，不把异常详情当成业务事实。
        result = tool_result(False, error="订单 Tool 执行异常，请在 Debug 中检查异常原因。")
    # 返回局部更新，不覆盖之后的支付和退款结果。
    return {
        # 保留 success、data、error 三个字段。
        "order_result": result,
        # 创建新列表，不直接修改原 State 中的列表。
        "executed_tools": state["executed_tools"] + ["get_order"],
    # 结束返回字典。
    }


# 方法功能：订单查询后，根据结果选择查支付或直接总结。
def choose_order_route(state: WorkflowState) -> str:
    # 订单不存在、参数错误或读取失败都不能继续查支付。
    if not state["order_result"]["success"]:
        # 路由只返回目标标签，不修改 State。
        return "summarize"
    # 本课将订单明确标记的待支付、未支付视为提前结束条件。
    if state["order_result"]["data"]["status"] in ("待支付", "未支付"):
        # 保留已有订单结果，跳过支付和退款查询。
        return "summarize"
    # 其他订单状态需要进一步读取支付事实，而不是猜测支付结果。
    return "get_payment"


# 方法功能：查询全部支付记录，不覆盖已经取得的订单结果。
def get_payment_node(state: WorkflowState, data_file: Path = DEFAULT_DATA_FILE) -> dict:
    # 将意外异常转为统一的 Tool 失败结果。
    try:
        # 查询的仍然是同一租户和同一订单。
        result = get_payment(state["order_id"], state["tenant_id"], data_file=data_file)
    # 捕获正常返回格式之外的执行异常。
    except Exception as error:
        # 可以在这里单步检查 error。
        result = tool_result(False, error="支付 Tool 执行异常，请在 Debug 中检查异常原因。")
    # 只返回本节点需要更新的两个字段。
    return {
        # 支付结果保存为列表或失败信息。
        "payment_result": result,
        # 在已执行的订单 Tool 后面追加支付 Tool。
        "executed_tools": state["executed_tools"] + ["get_payment"],
    # 结束返回字典。
    }


# 方法功能：检查支付列表中是否至少有一条成功记录，不只看第一条。
def has_successful_payment(payments: list) -> bool:
    # 逐条查看支付状态，不自行推算金额或支付是否到账。
    for payment in payments:
        # 状态完全匹配本课样例定义时才认为这条支付成功。
        if payment["status"] == "支付成功":
            # 找到一条成功记录就可以继续查询退款。
            return True
    # 空列表、支付失败或支付中都不能认定为支付成功。
    return False


# 方法功能：支付查询后，选择查退款或保留现有结果进入总结。
def choose_payment_route(state: WorkflowState) -> str:
    # 支付 Tool 失败时不继续查退款。
    if not state["payment_result"]["success"]:
        # 支付失败信息仍保留在 State 中。
        return "summarize"
    # 支付记录为空或没有成功支付时也提前结束。
    if not has_successful_payment(state["payment_result"]["data"]):
        # 总结会区分没有记录与有记录但未成功。
        return "summarize"
    # 至少一笔支付成功后再查询退款记录。
    return "get_refund"


# 方法功能：查询全部退款记录，保留前两步已经取得的结果。
def get_refund_node(state: WorkflowState, data_file: Path = DEFAULT_DATA_FILE) -> dict:
    # 将意外异常转换为可总结的失败结果。
    try:
        # 查询退款记录，而不是向业务系统发起退款。
        result = get_refund(state["order_id"], state["tenant_id"], data_file=data_file)
    # 捕获 Tool 意外抛出的异常。
    except Exception as error:
        # Debug 时可在这里检查原始异常。
        result = tool_result(False, error="退款 Tool 执行异常，请在 Debug 中检查异常原因。")
    # 返回局部更新，订单和支付字段仍由 LangGraph 保留。
    return {
        # 成功的空列表表示已查过但没有退款记录。
        "refund_result": result,
        # 记录退款 Tool 确实执行过。
        "executed_tools": state["executed_tools"] + ["get_refund"],
    # 结束返回字典。
    }


# 方法功能：只使用已取得的业务结果总结，并说明为什么结束。
def summarize_node(state: WorkflowState) -> dict:
    # 取出订单结果，后面的代码不会覆盖这个字段。
    order_result = state["order_result"]
    # 取出支付结果；被跳过时仍然是 {}。
    payment_result = state["payment_result"]
    # 取出退款结果；被跳过时仍然是 {}。
    refund_result = state["refund_result"]
    # 用普通列表保存总结的每一行文字。
    lines = []
    # 先假设已经完成全部查询，提前结束时再改成对应分支。
    branch = "completed"
    # 没有成功取得订单时，不能编造订单、支付或退款情况。
    if not order_result["success"]:
        # 订单不存在与订单 Tool 读取失败都保留原始错误说明。
        branch = "order_error"
        # 明确后续两个查询没有执行。
        lines.append(f"订单查询未完成：{order_result['error']} 未查询支付和退款。")
    # 取得订单后，先保留订单本身的事实。
    else:
        # 订单 data 是一个字典，不是支付或退款使用的列表。
        order = order_result["data"]
        # 展示订单状态、金额以及这条数据的更新时间。
        lines.append(f"订单 {order['order_id']}：{order['status']}，金额 {order['amount']} {order['currency']}；截至 {order['updated_at']}。")
        # 订单明确未支付时，不读取被跳过的支付结果。
        if order["status"] in ("待支付", "未支付"):
            # 保存提前结束的业务原因。
            branch = "unpaid"
            # 说明未查询不等于已查出没有记录。
            lines.append("订单尚未支付，结束后续查询；未查询支付和退款。")
        # 继续查支付但 Tool 失败时，也不能推断没有支付记录。
        elif not payment_result["success"]:
            # 保留支付读取失败这个分支。
            branch = "payment_error"
            # 展示错误，同时明确退款没有查询。
            lines.append(f"支付查询未完成：{payment_result['error']} 未查询退款。")
        # 支付查询成功后，展示每条支付记录。
        else:
            # 支付 data 是列表，可以有零条、一条或多条记录。
            payments = payment_result["data"]
            # 不只展示第一条，也不把失败记录丢掉。
            for payment in payments:
                # 展示支付事实及其更新时间。
                lines.append(f"支付 {payment['payment_id']}：{payment['status']}，金额 {payment['amount']} {payment['currency']}；截至 {payment['updated_at']}。")
            # 已查过但列表为空，保留这个正常查询结果。
            if not payments:
                # 没有记录与 Tool 失败是不同分支。
                branch = "payment_missing"
                # 不把缺少支付记录直接等同于订单未支付。
                lines.append("未找到支付记录，无法确认支付成功；结束后续查询，未查询退款。")
            # 有支付记录但没有成功记录时，不继续查询退款。
            elif not has_successful_payment(payments):
                # 保存支付尚未成功的业务原因。
                branch = "payment_not_success"
                # 保留上面所有失败或处理中的支付记录。
                lines.append("支付记录中没有支付成功项；结束后续查询，未查询退款。")
            # 支付成功，但退款 Tool 执行失败时保留前两步事实。
            elif not refund_result["success"]:
                # 退款读取失败不等于没有退款。
                branch = "refund_error"
                # 展示退款失败信息。
                lines.append(f"退款查询未完成：{refund_result['error']}")
            # 退款查询成功后，区分无记录和有记录。
            else:
                # 退款 data 同样是列表。
                refunds = refund_result["data"]
                # 空列表是已查询但无退款的正常业务结果。
                if not refunds:
                    # 保存无退款这个结束原因。
                    branch = "no_refund"
                    # 到此结束，不增加其他 Tool 调用。
                    lines.append("未找到退款记录，结束查询；这不代表已退款，也不代表不能退款。")
                # 有退款记录时逐条保留，不擅自宣称退款都已到账。
                else:
                    # 一个订单可能有多笔部分退款。
                    for refund in refunds:
                        # 展示每笔退款状态、金额、原因和更新时间。
                        lines.append(f"退款 {refund['refund_id']}：{refund['status']}，金额 {refund['amount']} {refund['currency']}，原因：{refund['reason']}；截至 {refund['updated_at']}。")
    # 所有分支都说明当前是模拟数据，不是实时业务诊断。
    lines.append("数据来源：本地 JSON 模拟；以上为记录更新时间对应的状态。")
    # 只新增结束分支和总结，完整 Tool 结果仍然保留在 State 中。
    return {
        # 业务分支可以在 Console 或 Debug 中观察。
        "branch": branch,
        # 按顺序把每段事实拼成多行总结，不调用 LLM。
        "answer": "\n".join(lines),
    # 结束返回字典。
    }


# 方法功能：创建订单、支付、退款、总结节点及业务条件路由。
def build_graph(data_file: Path = DEFAULT_DATA_FILE):
    # 内部函数绑定入口配置的路径，LangGraph 调用时只需传入 State。
    def run_get_order(state: WorkflowState) -> dict:
        # 调用订单节点并将局部更新字典返回给 LangGraph。
        return get_order_node(state, data_file)
    # 为支付节点绑定同一个文件路径。
    def run_get_payment(state: WorkflowState) -> dict:
        # 可以在 get_payment_node 内单步进入业务 Tool。
        return get_payment_node(state, data_file)
    # 为退款节点绑定同一个文件路径。
    def run_get_refund(state: WorkflowState) -> dict:
        # 可以在 get_refund_node 内单步进入业务 Tool。
        return get_refund_node(state, data_file)
    # 使用共享的 State 字段创建图。
    graph = StateGraph(WorkflowState)
    # prepare 负责整理输入和准备结果字段。
    graph.add_node("prepare", prepare_node)
    # get_order 负责查询订单。
    graph.add_node("get_order", run_get_order)
    # get_payment 负责查询支付列表。
    graph.add_node("get_payment", run_get_payment)
    # get_refund 负责查询退款列表。
    graph.add_node("get_refund", run_get_refund)
    # summarize 负责基于已有事实给出总结。
    graph.add_node("summarize", summarize_node)
    # 从 prepare 开始执行。
    graph.add_edge(START, "prepare")
    # 整理输入后一定先查订单。
    graph.add_edge("prepare", "get_order")
    # 订单节点完成并合并 State 后，再调用订单路由函数。
    graph.add_conditional_edges("get_order", choose_order_route, {"get_payment": "get_payment", "summarize": "summarize"})
    # 支付节点完成后，再按支付事实选择退款或总结。
    graph.add_conditional_edges("get_payment", choose_payment_route, {"get_refund": "get_refund", "summarize": "summarize"})
    # 退款是本课最后一个查询节点，无论有无记录都进入总结。
    graph.add_edge("get_refund", "summarize")
    # 每条业务路径最后都结束，没有回边或自动重试。
    graph.add_edge("summarize", END)
    # 编译为可以通过 invoke 执行的工作流。
    return graph.compile()
