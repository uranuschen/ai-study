# 第 73 课：把 get_order 封装成 MCP Tool

本课在原 Server 中增加一个 `get_order`，只做业务函数复用、工具描述和结果映射。

```text
Postman / MCP Client
        ↓ tools/call，工具名为 get_order
mcp_server/server.py 的 get_order(order_id)
        ↓ query_order 是原函数的别名
src/agent_learning/business/tools.py 的 get_order(order_id, tenant_id)
        ↓
data/business_demo.json
```

`main_mcp.py` 在导入 Server 前把 `src` 加入包路径，根目录直接 Run / Debug 即可。HTTP 地址继续使用 `http://127.0.0.1:8001/mcp`。

## 核心代码

Server 中的 `query_order` 是 `from ... import get_order as query_order` 导入的别名，没有新增查询实现。实际调用仍是：

```python
# 使用 Server 固定的租户查询订单。
result = query_order(order_id, TENANT_ID)
```

`TENANT_ID="acme"` 在 Server 中定义，工具参数只有 `order_id`。`tools/list` 中的 `inputSchema.properties` 也只有 `order_id`；客户端不能更换查询租户或文件路径。

工具描述明确说明何时使用、何时不用和参数含义。模型会根据这些说明选择工具，而实际订单事实来自同一个业务函数。

## 业务结果与 MCP 结果

业务函数返回：

```json
{
  "success": false,
  "data": null,
  "error": "订单不存在或当前租户不可读取。"
}
```

转换时使用同一份结果：

| 用途 | SDK 2.x 的 Python 字段 | HTTP 返回的 JSON 字段 |
|---|---|---|
| 模型读取的文字 | `content`，内含业务结果的 JSON 文字 | `result.content` |
| 程序读取的原始业务结果 | `structured_content`，保留 success/data/error | `result.structuredContent` |
| 工具是否失败 | `is_error = not result["success"]` | `result.isError` |

返回 `CallToolResult` 是为了明确设置业务失败标记。订单不存在属于 Tool 执行失败，HTTP 仍可以返回 200，客户端需要检查 `result.isError`。[SDK 错误结果说明](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/)

## 启动与 Postman 调用

停止原来的 MCP 进程后，在项目根目录重新启动：

```bash
.venv/bin/python -B main_mcp.py
```

Postman 选择 POST，URL 只填写：

```text
http://127.0.0.1:8001/mcp
```

Headers：

| 名称 | 值 |
|---|---|
| Content-Type | application/json |
| Accept | application/json, text/event-stream |
| MCP-Protocol-Version | 2026-07-28 |
| Mcp-Method | tools/call |
| Mcp-Name | get_order |

Body 选择 raw / JSON：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_order",
    "arguments": {"order_id": "A1002"},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

正常查询检查 `result.isError=false`、`result.structuredContent.success=true`。订单号、状态、金额、更新时间和 `source=json` 都在 `result.structuredContent.data` 中。

把订单号改成 `A9999`，应返回 `result.isError=true`，业务结果为上面的失败字典。这个结果不回显其他租户是否存在该订单。

要重新发现工具，使用第 72 课的 `tools/list` 请求：Header 中 `Mcp-Method` 改为 `tools/list`，取消 `Mcp-Name`，Body 中的 `method` 同样改为 `tools/list`，`params` 只保留 `_meta`。工具列表会包含 `hello`、`greet`、`get_order`。

## 学习范围

本次使用临时 TestClient 经 HTTP 入口验证了函数复用、正常与不存在订单、跨租户隔离、参数类型错误、新旧协议调用及原 hello / greet。业务 JSON 的内容未改变，临时样例文件在核查后已释放。

本课查询 JSON 样例，保留金额字符串、来源和更新时间。支付、退款 Tool 在第 74 课实现，统一参数校验与错误分类在第 75 课实现。本课不调用模型或数据库，不添加执行日志、追踪和测试文件。
