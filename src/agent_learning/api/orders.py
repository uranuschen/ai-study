from fastapi import APIRouter, Depends, Path
from agent_learning.api.dependencies import get_order_service
from agent_learning.api.schemas import OrderRequest
from agent_learning.services.order_service import OrderService


# 订单查询和固定流程统一归入业务接口。
router = APIRouter(tags=["订单业务"])


# 参数 JSON 示意：{"order_id": "A1002"}；实际为 GET /api/orders/A1002，无 JSON 请求体。
# 路径参数是订单号，租户由服务端提供。
@router.get("/api/orders/{order_id}")
def get_order(
    order_id: str = Path(min_length=1, max_length=64),
    service: OrderService = Depends(get_order_service),
) -> dict:
    # 直接查询，不调用 LLM。
    return service.get_order(order_id)


# 参数 JSON 示意：{"order_id": "A1002"}；实际为 GET /api/orders/A1002/payments，无 JSON 请求体。
# 返回全部匹配支付记录。
@router.get("/api/orders/{order_id}/payments")
def get_payments(
    order_id: str = Path(min_length=1, max_length=64),
    service: OrderService = Depends(get_order_service),
) -> dict:
    # 成功空列表表示没有支付记录。
    return service.get_payments(order_id)


# 参数 JSON 示意：{"order_id": "A1002"}；实际为 GET /api/orders/A1002/refunds，无 JSON 请求体。
# 返回全部匹配退款记录，不发起退款。
@router.get("/api/orders/{order_id}/refunds")
def get_refunds(
    order_id: str = Path(min_length=1, max_length=64),
    service: OrderService = Depends(get_order_service),
) -> dict:
    # 直接复用退款 Tool。
    return service.get_refunds(order_id)


# JSON 入参示例：{"order_id": "A1002"}
# 演示第 61 课固定的订单、支付、退款和总结流程。
@router.post("/api/workflows/order-check")
def check_order(body: OrderRequest, service: OrderService = Depends(get_order_service)) -> dict:
    # 哪些步骤执行由业务结果决定。
    return service.check_order(body.order_id)
