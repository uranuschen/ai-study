# 第 74 课：支付与退款 MCP Tools

本课新增 `get_payment(order_id)` 和 `get_refund(order_id)`，复用 `business/tools.py` 中同名的业务函数。Server 通过别名 `query_payment`、`query_refund` 调用原函数，可信租户仍固定为 `acme`。

第 75 课之后，查询失败会转换成固定错误代码与文字；成功列表和本课截断约定继续保留，详见 [校验与错误分类](25-mcp-validation-errors.md)。

```text
MCP 工具 get_payment / get_refund
        ↓ 原业务函数按租户和订单号查询 JSON
records_to_mcp
        ↓ 保留前 10 条，标明是否截断
content + structuredContent + isError
```

工具只公开 `order_id`，查询不执行支付或退款。状态、金额字符串、币种、`source=json`、`updated_at` 等记录字段原样保留。MCP 的文字和结构化结果使用同一份字典，延续 [第 73 课的结果映射](23-mcp-get-order.md)。

## 列表与截断

`mcp_server/server.py` 中 `MAX_RECORDS = 10` 控制支付和退款的返回条数。两种工具共用一个普通函数 `records_to_mcp`，不增加客户端分页参数。

| 查询结果 | data | success / isError | truncated |
|---|---|---|---|
| 无匹配记录 | `[]` | `true` / `false` | `false` |
| 1 至 10 条 | 完整列表 | `true` / `false` | `false` |
| 超过 10 条 | 原顺序的前 10 条 | `true` / `false` | `true` |
| 查询失败 | 保留原函数返回值，通常是 `null` | `false` / `true` | 不添加 |

`truncated` 位于 `result.structuredContent` 的业务字典中。截断时还会增加 `notice`，明确提示：

```text
仅返回前 10 条，结果已截断；不能据此判断全部记录或汇总金额。
```

这些字段也会一起写入 `content` 的 JSON 文字，供模型读取。成功的空列表与截断都不属于工具失败。业务函数先按租户过滤，MCP 再限制返回条数；这里限制的是响应条数，原业务函数仍读取全部匹配记录。

## 启动与 Postman

停止原 MCP 进程，在项目根目录重新启动：

```bash
.venv/bin/python -B main_mcp.py
```

Postman 方法选 POST，URL 只填写：

```text
http://127.0.0.1:8001/mcp
```

两个请求共用下面的 Headers：

| 名称 | 值 |
|---|---|
| Content-Type | application/json |
| Accept | application/json, text/event-stream |
| MCP-Protocol-Version | 2026-07-28 |
| Mcp-Method | tools/call |

`Mcp-Name` 要随工具名切换：

| 操作 | Mcp-Name | Body 中 params.name |
|---|---|---|
| 查询支付 | get_payment | get_payment |
| 查询退款 | get_refund | get_refund |

**支付请求**，Body 选 raw / JSON：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_payment",
    "arguments": {"order_id": "A1002"},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

**退款请求**，同时将 Header 的 `Mcp-Name` 改为 `get_refund`：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_refund",
    "arguments": {"order_id": "A1002"},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

## 观察三种结果

1. **多条记录**：默认样例中，`A1002` 在 acme 下有两笔支付和两笔退款，分别调用两个工具查看列表。
2. **空列表**：把订单号改成 `A1001`。`result.isError` 为 `false`，`result.structuredContent` 如下：

```json
{
  "success": true,
  "data": [],
  "error": null,
  "truncated": false
}
```

3. **截断提示**：临时把 `MAX_RECORDS` 改成 `1`，重启后查询 `A1002`，列表只有一条，`truncated=true`，`notice` 会提示只返回前 1 条。观察后改回 `10` 并重启。

空列表只说明当前租户可读范围内没有匹配记录；要确认订单是否存在，应调用 `get_order`。数据读取失败则保留原来的失败结果，不能转换成“查询成功但无记录”。

执行 `tools/list` 时，Header 的 `Mcp-Method` 改为 `tools/list`，不填 `Mcp-Name`，正文使用 [第 72 课的发现请求](22-mcp-server.md)。当前列表包含 `hello`、`greet`、`get_order`、`get_payment`、`get_refund`。

本次使用临时 TestClient 经 HTTP 入口核查多条记录、空列表、0 / 10 / 11 条边界、混合租户、业务失败、文字与结构化结果一致，以及新旧协议调用。原业务 JSON 未修改，没有新增测试文件。
