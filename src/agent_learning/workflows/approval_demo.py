from typing import TypedDict
from uuid import uuid4
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from agent_learning.workflows.human_approval_agent import validate_approval


# 只保存取消申请、人工决定和演示结果，不查询业务数据。
class ApprovalDemoState(TypedDict):
    # 复用现有 ask 入口，question 在本例中保存订单号。
    question: str
    # 租户来自服务端，不由请求正文提供。
    tenant_id: str
    # 准备节点整理后的订单号。
    order_id: str
    # 当前待审批的具体请求。
    approval_request: dict
    # 只有有效的 approve 决定才能设为 True。
    approved: bool
    # 面向调用方的演示说明。
    answer: str
    # 沿用现有 Service 的业务完成判断。
    stop_reason: str


# 先生成并保存审批请求，恢复时不会重新生成编号。
def prepare_node(state: ApprovalDemoState) -> dict:
    # 本例只整理订单号，不检查真实订单状态。
    order_id = state["question"].strip().upper()
    # 请求绑定订单、租户和本次审批编号。
    request = {
        "approval_id": uuid4().hex,
        "action": "cancel_order",
        "order_id": order_id,
        "tenant_id": state["tenant_id"],
        "mode": "simulate",
    }
    # 把请求写入 Checkpoint，接下来才进入人工等待。
    return {
        "order_id": order_id,
        "approval_request": request,
        "approved": False,
        "answer": f"已申请模拟取消订单 {order_id}，等待批准。",
        "stop_reason": "",
    }


# 核心：第一次在 interrupt 暂停，恢复时取得人工决定。
def approval_node(state: ApprovalDemoState) -> dict:
    # approvals 接口提交的恢复值，会成为这里的 decision。
    decision = interrupt(state["approval_request"])
    # 检查决定仍然绑定原订单、租户和审批编号。
    if not validate_approval(decision, state["approval_request"]):
        # 无效决定直接结束，不执行取消节点。
        return {
            "approved": False,
            "approval_request": {},
            "answer": "审批无效，未执行模拟取消。",
            "stop_reason": "approval_invalid",
        }
    # 明确拒绝时结束本轮。
    if decision["decision"] == "reject":
        # 拒绝也是已处理完的业务决定。
        return {
            "approved": False,
            "approval_request": {},
            "answer": "已拒绝，未执行模拟取消。",
            "stop_reason": "approval_rejected",
        }
    # 有效批准后，条件边才允许进入取消节点。
    return {"approved": True}


# 本例只返回演示结果，不调用真实取消接口或修改订单。
def cancel_node(state: ApprovalDemoState) -> dict:
    # 到达此节点表示人工已经批准。
    return {
        "answer": f"审批通过，已演示模拟取消订单 {state['order_id']}；未修改业务数据。",
        "approval_request": {},
        "stop_reason": "final_answer",
    }


# 根据人工决定选择执行取消还是结束。
def choose_route(state: ApprovalDemoState) -> str:
    # 只有有效批准可以进入取消节点。
    if state["approved"]:
        # 不让拒绝或无效决定执行模拟动作。
        return "cancel"
    # 拒绝和无效决定直接结束。
    return "end"


# 编译固定图，人工暂停由节点内的 interrupt 实现。
def build_graph(checkpointer: InMemorySaver) -> CompiledStateGraph:
    # 声明本例共享的状态。
    graph = StateGraph(ApprovalDemoState)
    # 准备并保存审批目标。
    graph.add_node("prepare", prepare_node)
    # 这个节点的名称与现有 approvals 接口一致。
    graph.add_node("approval", approval_node)
    # 批准后才进入模拟取消。
    graph.add_node("cancel", cancel_node)
    # 新申请先生成审批请求。
    graph.add_edge(START, "prepare")
    # 请求保存后进入人工等待。
    graph.add_edge("prepare", "approval")
    # 按明确决定选择后续节点。
    graph.add_conditional_edges("approval", choose_route, {"cancel": "cancel", "end": END})
    # 模拟结果生成后结束。
    graph.add_edge("cancel", END)
    # 不设置 interrupt_before，直接在审批节点中动态暂停。
    return graph.compile(checkpointer=checkpointer)
