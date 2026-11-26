# 第 75 课：参数校验与错误分类

本课继续使用 `mcp==2.3.0`。工具仍放在 `mcp_server/server.py`，新增普通函数模块 `mcp_server/controls.py`，不建立连接框架或日志系统。

```text
HTTP 请求
  ↓ SDK 处理 HTTP 与 JSON-RPC
guard_request：工具名、必填、类型、额外字段
  ↓ 最多等待 5 秒
原 Tool → 原只读业务函数
  ↓ 固定错误文字、Tool 结果大小检查
MCP 响应 → classify_response 分类，失败时停止
```

## 一张错误映射表

以下为当前实现经 HTTP 入口核对后的行为。HTTP 连接失败本身没有服务器响应；401 / 403 的分类使用合成响应核查，当前本地 Server 尚未配置登录或 OAuth。

| 层级 | 情况 | HTTP / 协议结果 | 本项目错误代码 | 自动重试 |
|---|---|---|---|---|
| HTTP | 服务没启动、连接失败、客户端等待超时 | 没有 HTTP 响应 | CONNECTION_FAILED | 否 |
| HTTP | 接入认证或授权失败 | 401 / 403 | HTTP_AUTH_FAILED | 否 |
| HTTP | 其他没有 JSON-RPC 错误体的 HTTP 失败 | 非 2xx | HTTP_FAILED | 否 |
| JSON-RPC | 请求正文不是合法 JSON | 400，error.code=-32700 | -32700 | 否 |
| JSON-RPC | JSON-RPC 版本等消息结构无效 | 400，error.code=-32600 | -32600 | 否 |
| JSON-RPC | method 不存在 | 404，error.code=-32601 | -32601 | 否 |
| JSON-RPC | 工具不存在，或 arguments 整体不是对象 | 400，error.code=-32602 | -32602 | 否 |
| JSON-RPC | 新协议请求头与正文不一致 | 400，error.code=-32020 | -32020 | 否 |
| Tool | 缺必填、字符串类型不符、额外字段、空白或过长 | 200，result.isError=true | INVALID_ARGUMENT | 否 |
| Tool | 订单不存在或不可读取 | 200，result.isError=true | ORDER_UNAVAILABLE | 否 |
| Tool | 支付或退款查询失败 | 200，result.isError=true | BUSINESS_ERROR | 否 |
| Tool | 查询明确抛出 PermissionError | 200，result.isError=true | FORBIDDEN | 否 |
| Tool | 超过等待时间 | 200，result.isError=true | TOOL_TIMEOUT | 否 |
| Tool | 结果超过字节上限 | 200，result.isError=true | RESULT_TOO_LARGE | 否 |
| Tool | 其他内部异常 | 200，result.isError=true | TOOL_ERROR | 否 |

HTTP 400 / 404 如果带有效的 JSON-RPC `error`，客户端按协议错误处理。HTTP 200 也要继续检查 `result.isError`。支付、退款成功但无记录仍然返回 `data=[]`、`isError=false`。

SDK 默认会忽略额外参数，未知工具默认也会作为工具失败返回。本课通过 SDK 支持的普通中间件明确拒绝额外字段，并将未知工具归入协议错误。SDK 升级后需要重新核对行为。[固定版本的中间件接口](https://py.sdk.modelcontextprotocol.io/advanced/middleware/)、[SDK 错误说明](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/)

## 参数校验在哪里

`guard_request` 从 `mcp.list_tools()` 读取 SDK 已生成的参数说明，没有另外维护工具名配置表。

`controls.valid_arguments()` 使用普通 for / if 检查本课五个工具：

1. 必填参数必须存在。
2. 有参数时必须是字符串，拒绝数字、布尔值、列表和 null。
3. 只允许声明过的字段，额外的 `tenant_id`、文件路径或其他字段全部拒绝。
4. 字符串不能全为空白，长度不超过 256 个字符。

`hello` 仍接受空参数 `{}`。`tools/list` 同时公开 `additionalProperties=false`、`minLength` 和 `maxLength`。空白字符串由入口的 `strip()` 判断拒绝。

`arguments=[]` 是整个调用参数容器错误，属于协议错误；`arguments={"order_id":123}` 是容器内的工具字段错误，属于 Tool 错误。

## 固定错误与不可自动重试

`controls.error_result()` 只从固定错误表选择文字，不使用 `str(error)`，也不返回 SQL、路径、堆栈、SDK 校验的原始输入或异常 data。

例如订单查询失败时，`result.structuredContent` 为：

```json
{
  "success": false,
  "data": null,
  "error": "订单不存在或不可读取。",
  "error_code": "ORDER_UNAVAILABLE",
  "retryable": false
}
```

`error_code` 与 `retryable` 是本项目业务字段。`isError` 只是失败标记，并不会替客户端阻止重试。本课的 `classify_response()` 固定返回 `retryable=false`；明确权限拒绝不能因为远端声称可以重试就继续发送请求。

这个纯函数只分类已收到的响应，不发网络请求。后续 Client 的响应处理函数可以使用：

```python
# 导入已有的错误分类函数。
from mcp_server.controls import classify_response


# 在客户端收到 HTTP 响应后调用，不在这里重新发送请求。
def handle_response(response):
    # HTTP 失败可能返回普通文字或 HTML，不能假设总是 JSON。
    try:
        # 只解析已有响应，不发起新请求。
        body = response.json()
    # 非 JSON 响应交给 HTTP 层分类。
    except ValueError:
        # 不回显 HTML 或其他原始内容。
        body = None
    # 先区分 HTTP、协议和工具失败。
    decision = classify_response(response.status_code, body)
    # 本课所有失败都直接交给上层处理。
    if decision["layer"] != "success":
        # 返回错误决定，结束本次调用，不自动重试。
        return decision
    # 三层都成功时再使用工具结果。
    return body["result"]
```

连接失败没有 response，调用 `classify_response(None)`。正式 MCP Client 的连接、工具发现与释放仍在第 78 课实现。服务端固定 `TENANT_ID` 是租户绑定，不等同于接入认证。

## 耗时与结果大小限制

| 设置 | 当前值 | 限制对象 |
|---|---|---|
| MAX_ARGUMENT_CHARS | 256 | 本课工具的单个字符串参数 |
| TOOL_TIMEOUT_SECONDS | 5 秒 | SDK 工具调用的等待时间 |
| MAX_RESULT_BYTES | 16 KiB | 序列化后的 Tool 结果，包含文字、结构化内容与结果元数据 |

Tool 结果按当前 HTTP JSON 编码方式计入中文转义后的 UTF-8 字节。外层 JSON-RPC 的 `jsonrpc/id/result` 包装还会增加少量开销，因此不是整个 HTTP 响应恰好 16 KiB。超限返回完整的 `RESULT_TOO_LARGE` 错误，不切断 JSON 或伪造完整数据。

第 74 课的 `MAX_RECORDS=10` 继续限制支付、退款的记录条数。记录少但单条内容过大时，字节上限仍会生效。

三个业务包装函数改为 `async def`，通过 `read_query()` 等待原同步查询。`abandon_on_cancel=True` 允许超时后结束等待；底层只读线程仍可能继续完成，不代表查询被强制终止，因此不自动重试。后续接真实 HTTP 或数据库时还需要对应客户端、驱动的超时。

## Postman：先运行正常请求，再修改参数

重启原 MCP 进程：

```bash
.venv/bin/python -B main_mcp.py
```

POST 地址：

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

只修改正文中的 `arguments`，观察下面的结果：

| arguments | 预期 |
|---|---|
| `{"order_id":"A1002"}` | 成功，租户为 acme |
| `{}` | INVALID_ARGUMENT |
| `{"order_id":123}` | INVALID_ARGUMENT |
| `{"order_id":" "}` | INVALID_ARGUMENT |
| `{"order_id":"A1002","tenant_id":"other"}` | INVALID_ARGUMENT，不进入查询 |
| `{"order_id":"A9999"}` | ORDER_UNAVAILABLE |
| `[]` | 协议错误 -32602 |

验证未知工具时，把 Header 的 `Mcp-Name` 和正文 `params.name` 同时改成 `missing_tool`，得到协议错误 -32602。只修改其中一个会先触发请求头不匹配错误 -32020。

本次验证使用临时 TestClient、替身查询和合成 HTTP 响应，覆盖实际 SDK 分类、权限、异常隐藏、超时等待与中文结果字节上限；不访问 LLM 或数据库，不新增测试文件。
