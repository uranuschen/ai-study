# 当前学习范围

以项目已经实现的内容为准，截至第 70 课的核心能力统一通过 `main_api.py` 提供。原 Python 与课程资料保留用于对照，不逐个包装成 HTTP 接口。

| 已学内容 | 当前实现 |
|---|---|
| Python / LLM / Tool Calling 基础 | 普通类、函数、字典、模型客户端与工具协议 |
| RAG 加载、切分、Embedding、版本与入库 | `rag/`，提供预览和显式入库接口 |
| 混合检索、过滤、精排、引用、拒答 | `RAGPipeline.ask()`，返回答案与引用 |
| 单节点、双节点 State、条件路由 | 独立基础课程 API；另有两个最简暂停 / 恢复演示接口 |
| 第 60–61 课业务 Tool 与固定工作流 | JSON 订单、支付、退款查询和固定流程 API |
| 第 62–64 课 Agent / 重试 / RAG Tool | 综合诊断图，模型按需调用业务与知识库 Tool |
| 第 65 课 Checkpoint | 可选工具前暂停，使用同一会话恢复 |
| 第 66 课 Memory | 保留完整历史轮次，按轮数和字符上限裁剪 |
| 第 67 课人工确认 | 当前审批编号绑定模拟取消请求，明确批准 / 拒绝 |
| 第 69 课追踪 | 按用户要求从当前程序移除 |
| 第 70 课综合诊断 | 会话、查询、规则引用、有限重试、执行限制与审批贯通 |
| 第 71 课 MCP 概念 | `main_mcp_basics.py`，对照直接函数、function calling、MCP 与三种原语；版本台账见第 71 课文档 |
| 第 72 课 MCP Server | `main_mcp.py` 启动 Streamable HTTP，注册 hello / greet，并验证新旧协议调用 |
| 第 73 课订单 MCP Tool | 复用 JSON get_order，Server 固定租户，映射文字、结构化结果与业务失败标记 |

当前不保留用量费用统计、执行日志、追踪事件或测试文件。最大执行机会与上下文字符上限只用于结束流程，不作为统计返回。支付、退款与 RAG 的 MCP Tool、MCP Client、真实业务库 Tool、微调留待后续课程。

[当前 API 与目录](../README.md) · [调用与断点](20-fastapi.md) · [第 71 课 MCP 概念](21-mcp-basics.md) · [第 72 课 MCP Server](22-mcp-server.md) · [第 73 课订单 Tool](23-mcp-get-order.md) · [后续业务与 MCP 设计](09-workflow-mcp-design.md)
