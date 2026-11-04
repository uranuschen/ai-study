# 第 72 课：MCP Server 与两个最小 Tool

本课只实现 `hello()` 和 `greet(name)`。代码使用普通函数，每个逻辑语句上方都有中文注释。

学习到第 73 课后，同一个 Server 还会提供 `get_order`，见 [订单 MCP Tool](23-mcp-get-order.md)。

```text
main_mcp.py              启动 HTTP 服务，地址为 127.0.0.1:8001/mcp
mcp_server/
  __init__.py            声明 Python 包
  server.py              创建 MCPServer，注册两个工具
```

## 启动

SDK 在 `pyproject.toml` 中固定为 `mcp==2.3.0`。已有项目环境安装 SDK：

```bash
.venv/bin/python -m pip install --only-binary=:all: "mcp==2.3.0"
```

在项目根目录启动：

```bash
.venv/bin/python -B main_mcp.py
```

也可以直接 Run / Debug 根目录的 `main_mcp.py`，或在 VS Code 中选择“启动 MCP（第72课）”。停止时按 Ctrl+C。

MCP 调用地址为 `http://127.0.0.1:8001/mcp`。已有 FastAPI 的地址为 `http://127.0.0.1:8000`，Swagger 为 `http://127.0.0.1:8000/docs`。

## 核心代码怎么执行

1. 导入 `mcp_server/server.py`，创建 `MCPServer` 对象。
2. `@mcp.tool(...)` 把下方函数注册为 Tool；SDK 从参数类型生成 schema。
3. `mcp.streamable_http_app(json_response=True)` 生成 `/mcp` 协议入口，结果返回 JSON。
4. `uvicorn.run(...)` 监听 8001 端口，同时启动 SDK 自带的生命周期。
5. 收到 `tools/list` 时返回工具说明；收到 `tools/call` 时由 SDK 校验并调用对应函数。
6. 关闭服务时，SDK 的生命周期释放内部任务和旧协议会话。

`mcp` 保存注册好的工具，`app` 是 SDK 生成的 HTTP 应用。导入模块只创建对象，直接运行 `main_mcp.py` 才监听端口。生命周期由 [SDK 自带的应用](https://py.sdk.modelcontextprotocol.io/run/asgi/) 管理。

## Postman 调用：主协议 2026-07-28

下列请求都选择 POST，URL 栏只填写：

```text
http://127.0.0.1:8001/mcp
```

Headers：

| 名称 | 值 |
|---|---|
| Content-Type | application/json |
| Accept | application/json, text/event-stream |
| MCP-Protocol-Version | 2026-07-28 |

还需要按本次操作填写下面两个请求头：

| 操作 | Mcp-Method | Mcp-Name |
|---|---|---|
| 发现工具 | tools/list | 不填写 |
| 调用 hello | tools/call | hello |
| 调用 greet | tools/call | greet |

`Mcp-Method` 必须等于正文的 `method`；调用工具时，`Mcp-Name` 必须等于正文的 `params.name`。遗漏或不匹配会返回 HTTP 400 与 `-32020`，这是新协议的 [请求头校验](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#standard-request-headers)。

Body 选择 raw / JSON。`_meta` 中的协议版本与客户端能力是新协议的请求信息，这些字段交给 SDK Client 时会自动填写。本课先用 Postman 直接观察完整 JSON。

**第一步：发现工具。**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

查看返回的 `result.tools`，应有 `hello` 和 `greet`。`greet` 的 `inputSchema` 中包含必填字符串 `name`，这些说明由 SDK 从函数自动生成。

**第二步：调用无参数工具。**

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "hello",
    "arguments": {},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

`result.content` 中的文字为 `你好，MCP！`。

**第三步：调用带参数工具。**

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "greet",
    "arguments": {"name": "小明"},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

`result.content` 中的文字为 `你好，小明！`。使用的是同一个 `/mcp` 地址，`params.name` 决定执行哪个函数，`params.arguments` 提供函数参数。

**第四步：观察参数错误。**

保留第三步请求的其他字段，把 `arguments` 改为 `{}` 或 `{"name": 123}`，观察 SDK 返回的参数错误；工具输入校验错误通过工具失败结果表达。完整错误分类在第 75 课继续学习。

## 新旧协议与传输

| 项目 | 本课约定 |
|---|---|
| SDK | `mcp==2.3.0`，Server 类名为 `MCPServer` |
| 主协议 | `2026-07-28`，每次请求带版本与能力信息，无需 `initialize` 会话 |
| 版本发现 | 主协议可通过 `server/discover` 取得支持版本与能力；上面的请求已明确指定版本 |
| 兼容协议 | `2025-11-25`，旧客户端通过 `initialize` 建立会话 |
| 传输 | Streamable HTTP，本课由 Uvicorn 监听 8001 端口 |

同一个应用由 SDK 按协议版本处理新旧客户端，不需要手写两套 Server。[SDK 兼容机制](https://py.sdk.modelcontextprotocol.io/run/legacy-clients/)

本次已用临时 TestClient 经 HTTP 入口验证两种协议的工具发现与调用、参数错误、请求头不匹配，以及旧协议会话释放；未新增测试文件。新协议的 `server/discover` 也已验证。

Streamable HTTP 通过 HTTP 请求通信；stdio 通过进程的标准输入输出通信。stdio 的 stdout 只能写协议消息，普通输出会破坏通信，因此不要在工具中用 `print()` 打印调试信息。第 78 课再对照 stdio。

本课没有模型调用、业务数据查询或自定义日志。`MCPServer` 的 `version="1.0.0"` 是这个演示 Server 自己的版本，与 SDK 版本和协议版本分别表示不同内容。
