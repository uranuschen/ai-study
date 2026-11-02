# 第 61 课：固定多步订单流程

当前入口是 `POST /api/workflows/order-check`，JSON 入参为 `{"order_id":"A1002"}`。核心图在 `workflows/order_flow.py`，Service 在 `services/order_service.py`。

```text
prepare → get_order
             ├─ 查询失败或待支付 → summarize → END
             └─ 其他状态 → get_payment
                              ├─ 查询失败、无记录或没有成功支付 → summarize → END
                              └─ 有成功支付 → get_refund → summarize → END
```

所有 Tool 都是只读 JSON 查询，不调用 RAG、LLM，不执行支付、退款或取消。支付和退款可能有多条，查询成功的空列表表示没有记录。

State 分别保存 `order_result`、`payment_result`、`refund_result`，每个节点只更新自己的业务结果。被跳过的查询保持 `{}`，不能说成已查询但没有记录。执行记录列表已移除。

API 返回 `answer`、`order`、`payments`、`refunds`。具体调用见 [FastAPI](20-fastapi.md)。
