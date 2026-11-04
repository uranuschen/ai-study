# 第 71 课：MCP 是什么、解决什么问题

运行根目录的概念示例，每个逻辑语句上方都有中文注释：

```bash
.venv/bin/python -B main_mcp_basics.py
```

本课只用一个 `hello()` 函数和普通字典。模型返回值由代码固定填写；MCP 消息只展示关键字段，不构成完整协议请求，没有启动真实 Server 或 Client。

## 三种调用方式

| 方式 | 负责什么 | 本课对应代码 |
|---|---|---|
| 直接函数 | 当前程序直接执行已有能力 | `hello("小明")` |
| Function calling | 模型根据工具说明，提出工具名与参数；程序负责执行 | `model_tool`、`function_call` |
| MCP | Client 向 Server 发现和调用工具，统一外部工具的接入方式 | `tool`、`mcp_call` 的结构示意 |

MCP 不替代 function calling：应用先从 MCP 取得工具说明，转换成模型认识的格式；模型提出调用请求后，应用再通过 MCP Client 调用 Server，并把结果交回模型。MCP 不规定应用如何调用模型。[官方架构说明](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture)

```text
Server 提供工具说明 → Client 所在应用交给模型
模型提出调用请求 → MCP Client → MCP Server → 普通函数
函数结果 → MCP Client → 模型组织回答
```

Client 负责发起发现和调用；Server 负责暴露工具并执行对应函数。模型选择工具属于 function calling，真正执行函数由程序完成。

## 三种原语

| 原语 | 分工 | 订单场景示例 |
|---|---|---|
| Tools | 执行操作，也包括只读查询 | 按订单号查询订单 |
| Resources | 提供上下文数据 | 一份退款制度正文 |
| Prompts | 提供可复用的提示模板 | 订单诊断说明模板 |

本阶段实现 Tools；Resources、Prompts 先理解分工。[官方原语说明](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture#primitives)

## 版本台账

| 项目 | 课程约定 | 当前状态 |
|---|---|---|
| Python SDK | `mcp==2.3.0` | 已在 `pyproject.toml` 固定并安装；本课示例只依赖标准库 |
| 主协议 | `2026-07-28` | 第 72 课已通过 HTTP 入口验证 |
| 旧客户端兼容 | `2025-11-25` | 第 72 课已验证初始化、工具发现、调用和会话释放 |
| 主传输 | `streamable-http` | 第 72 课使用，入口见 `main_mcp.py` |
| 对照传输 | `stdio` | 第 78 课对照进程与生命周期 |

SDK 版本根据 2026-11-04 核对的 [PyPI 2.3.0 发布](https://pypi.org/project/mcp/2.3.0/) 固定。SDK 2.x 的 Server 类名是 `MCPServer`，后续代码按此版本编写。[官方迁移说明](https://py.sdk.modelcontextprotocol.io/migration/#fastmcp-renamed-to-mcpserver)

主协议使用每次请求携带的版本信息；旧协议使用 `initialize` 握手。本课只展示概念，真实通信实现与兼容验证见 [第 72 课](22-mcp-server.md)。[官方兼容说明](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)

## 什么时候不需要 MCP

**只有单一内部调用方时，直接函数或现有 FastAPI 就够。**需要多个 AI 客户端以统一方式发现并调用同一批能力时，再考虑 MCP。这个取舍也见项目的 [后续架构约定](09-workflow-mcp-design.md)。
