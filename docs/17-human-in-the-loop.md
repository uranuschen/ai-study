# 第 67 课：模拟取消前的人工确认

当前入口为会话提问和 approvals 接口，核心逻辑在 `workflows/diagnosis_agent.py`。

```text
模型提出 cancel_order
  → prepare_approval：验证订单并保存独立审批编号
  → approval：interrupt 暂停，等待明确批准或拒绝
  → execute_cancel：有效批准后再次查订单，只执行模拟
  → 继续模型或收尾
```

只有待支付订单可以模拟取消，演示使用 A1001。订单号由模型提出，租户来自服务端；人工决定不能替换订单、租户或工具请求。approval_id 每次新请求重新生成，旧编号不可用于另一轮或另一会话。

调用 `POST /api/agent/sessions/{session_id}/approvals`，提交 `{"approval_id":"当前编号","decision":"approve"}`；改成 reject 表示拒绝。程序从真实待审批请求构造恢复值，用同一配置的 Command(resume=...) 交回图。

审批准备、人工等待和模拟执行分节点。恢复不重跑之前已经完成的查询，拒绝后不继续请求模型，同会话成功模拟过的订单不重复模拟。模拟异常明确说明结果未确认，不自动重试。

只生成业务结果，不修改 JSON、数据库或真实订单。内存状态不提供跨重启的防重复保证。

[API 调用与断点](20-fastapi.md)
