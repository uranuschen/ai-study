from agent_learning.business.tools import get_order, get_payment, get_refund
from agent_learning.workflows.order_flow import build_graph


# 对外提供直接查询和固定订单工作流。
class OrderService:
    # 身份与业务数据文件由服务端配置。
    def __init__(self, tenant_id, data_file):
        # 保存可信租户。
        self.tenant_id = tenant_id
        # 订单仍然只读本地 JSON。
        self.data_file = data_file
        # 固定流程只编译一次。
        self.graph = build_graph(data_file)

    # 查询一条订单。
    def get_order(self, order_id: str) -> dict:
        # 复用现有 Tool 的校验和租户过滤。
        return get_order(order_id, self.tenant_id, self.data_file)

    # 查询全部支付记录，允许成功空列表。
    def get_payments(self, order_id: str) -> dict:
        # 不发起支付。
        return get_payment(order_id, self.tenant_id, self.data_file)

    # 查询全部退款记录，允许成功空列表。
    def get_refunds(self, order_id: str) -> dict:
        # 不发起退款。
        return get_refund(order_id, self.tenant_id, self.data_file)

    # 固定流程按业务结果查询订单、支付、退款并生成说明。
    def check_order(self, order_id: str) -> dict:
        # 不使用模型自主选择下一步。
        result = self.graph.invoke({"question": order_id, "tenant_id": self.tenant_id})
        # 只返回业务说明和真正查到的业务结果。
        return {
            "answer": result["answer"],
            "order": result.get("order_result"),
            "payments": result.get("payment_result"),
            "refunds": result.get("refund_result"),
        }
