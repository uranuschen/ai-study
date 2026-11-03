# FastAPI 调用与断点

入口是根目录 `main_api.py`。API → Service → RAG / LangGraph / 业务 Tool → Repository / JSON / 模型客户端。

## 资料与独立问答

`POST /api/rag/preview`：

```json
{"file_name": "enterprise_documents.json"}
```

文件名相对于 `data/`，不能越出这个目录。`POST /api/rag/ingest` 使用相同参数，但会实际生成向量并向已有知识库写入；启动服务、预览和本次离线核查均不会执行它的真实写入。

`POST /api/rag/ask`：

```json
{"question": "退款通常多久到账？", "doc_type": "policy", "tags": []}
```

返回 `answer`、`citations`、`status`。可选 `business_module`、`doc_type`、`tags` 只缩小资料范围。租户与可读权限由服务端提供。

## 订单和固定流程

- `GET /api/orders/A1002`
- `GET /api/orders/A1002/payments`
- `GET /api/orders/A1002/refunds`

GET 没有 JSON 请求体。支付与退款成功返回列表，无记录是成功的空列表。

`POST /api/workflows/order-check`：

```json
{"order_id": "A1002"}
```

返回业务说明和已取得的订单、支付、退款结果。被跳过的查询保持空对象，不冒充查询成功但无记录。

## 会话与综合 Agent

1. `POST /api/agent/sessions`，请求体 `{"pause_before_tools": false}`。
2. 保存返回的 `session_id`。
3. `POST /api/agent/sessions/{session_id}/messages`：

```json
{"question": "检查 A1002 的订单、支付和退款情况"}
```

4. 再次对同一个 URL 提问，演示多轮追问：

```json
{"question": "它按规则通常多久到账？"}
```

5. `GET /api/agent/sessions/{session_id}` 查看当前保留的对话和待办。

结果中的 `status` 是业务状态，不是节点执行日志。新会话返回 `ready`；正常回答或人工拒绝返回 `completed`；受控失败返回 `failed`。

服务每次只接受同一会话的一个请求。不存在的会话返回 404；会话忙、暂停时提新问题或提交旧审批编号返回 409；请求字段不符合要求返回 422。系统异常返回固定说明，不回显内部异常或凭证。

## 最简暂停演示：只用两个接口

两个请求都使用 POST，Body 选择 raw / JSON。第一个请求已经在内部调用现有 `create_session()` 生成 ID，不需要另调创建会话接口。

第一个地址：

```text
http://127.0.0.1:8000/api/lessons/pause-demo
```

请求体：

```json
{"question": "你好"}
```

响应示意：

```json
{
  "session_id": "第一个接口返回的新编号",
  "status": "paused",
  "answer": "第一步已执行，等待继续。",
  "citations": [],
  "approval": null
}
```

第二个地址，替换为刚返回的编号：

```text
http://127.0.0.1:8000/api/lessons/pause-demo/{session_id}/resume
```

请求体：

```json
{}
```

返回 `completed`，answer 为 `第二步已执行，之前保存的问题是：你好`。恢复后再次调用返回 409，表示没有待执行节点；传普通 Agent 的编号也会拒绝，避免演示入口触发模型。

核心图在 `workflows/pause_demo.py`：`START → prepare → answer → END`，编译时固定 `interrupt_before=["answer"]`。两次请求使用相同的会话配置和 Checkpoint。此示例没有 LLM、Tool、数据库或执行日志。

## 工具前暂停和恢复

创建会话时提交：

```json
{"pause_before_tools": true}
```

提问触发普通 Tool 后返回 `paused`。调用 `POST /api/agent/sessions/{session_id}/resume`，请求体为 `{}`，继续同一个 Checkpoint。恢复不重新经过 prepare，不刷新本轮执行机会。

保留待执行节点的异常也可以通过该接口继续。已经受控结束的失败没有待执行节点，不能通过恢复接口重新开始；需要提交新问题。

## 最简审批演示：申请取消，再批准

两个请求都使用 POST，Body 选择 raw / JSON。新增接口内部创建会话，不需要先调创建会话接口；批准时复用原有的 approvals 接口。新增接口后需要重启 `main_api.py`。

第一个地址，申请模拟取消：

```text
http://127.0.0.1:8000/api/lessons/approval-demo
```

请求体：

```json
{"order_id": "A1001"}
```

响应示意：

```json
{
  "session_id": "返回的会话编号",
  "status": "waiting_approval",
  "answer": "已申请模拟取消订单 A1001，等待批准。",
  "citations": [],
  "approval": {
    "approval_id": "返回的审批编号",
    "action": "cancel_order",
    "order_id": "A1001",
    "mode": "simulate"
  }
}
```

第二个地址，使用刚返回的会话编号：

```text
http://127.0.0.1:8000/api/agent/sessions/{session_id}/approvals
```

请求体：

```json
{"approval_id": "返回的审批编号", "decision": "approve"}
```

返回 `completed`，answer 为 `审批通过，已演示模拟取消订单 A1001；未修改业务数据。`。改成 `reject` 则直接结束，返回 `已拒绝，未执行模拟取消。`。同一次审批处理后不能再次批准；想重新演示，重新调用第一个接口。

核心图在 `workflows/approval_demo.py`：`START → prepare → approval → cancel → END`。`approval` 中的 `decision = interrupt(request)` 暂停等待；原审批接口通过 `Command(resume=value)` 恢复，人工决定成为 `decision`。只有 `approve` 进入 `cancel`，`reject` 直接结束。

本例只操作 State 中的演示数据，不读取、验证或修改实际订单，不调用 LLM 或数据库。审批请求在 prepare 节点保存，恢复时保留原来的审批编号。

## 综合 Agent 人工审批

对会话提问：

```json
{"question": "请取消订单 A1001"}
```

真正提出取消请求时，返回 `waiting_approval` 和 `approval`：

```json
{
  "approval_id": "服务端生成的当前审批编号",
  "action": "cancel_order",
  "order_id": "A1001",
  "mode": "simulate"
}
```

调用 `POST /api/agent/sessions/{session_id}/approvals`：

```json
{"approval_id": "上一步返回的编号", "decision": "approve"}
```

改为 `reject` 表示拒绝。客户端只提交编号和决定，不能更换订单、租户或模型调用 ID。普通 `resume` 无法绕过审批；重复提交已经完成的审批返回冲突。同一会话成功模拟过的订单不重复模拟。模拟执行异常不自动重试。

模拟不写 JSON 或业务数据库；内存会话不提供重启后的防重复保证。审批能力用于学习，不代表已接入真实订单取消系统。

## 基础课程

以下三个接口接收 `question`：

- `/api/lessons/single-node`：`{"question": "你好"}`。
- `/api/lessons/state-flow`：`{"question": "两个节点传值"}`。
- `/api/lessons/conditional-route`：`{"question": "统计字数：你好世界"}`。

`POST /api/lessons/business-tool` 接收 `{"order_id": "A1002"}`；不存在的订单可以演示失败分支。这些接口均不调用 LLM。

## 建议断点

按 API 函数 → Service 方法 → 核心方法逐层进入：

- RAG：`RagService.ask()` → `RAGPipeline.ask()`。
- 固定流程：`OrderService.check_order()` → `order_flow.py`。
- Agent：`AgentService.ask()` → `diagnosis_agent.build_graph()` 中的节点函数。
- 恢复：`AgentService.resume()` 的 `graph.invoke(None, ...)`。
- 审批：`AgentService.approve()` → `run_approval()` → `run_execute_cancel()`。
- 最简审批：`AgentService.start_approval_demo()` → `approval_demo.prepare_node()` → `approval_node()`；批准后进入 `cancel_node()`。

`bootstrap.py` 只负责显式构造对象；`api/schemas.py` 只定义 HTTP 参数。业务代码保持普通类、函数、字典和 for / if，不增加日志、统计或额外框架。
