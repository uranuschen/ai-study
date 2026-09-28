# 学习路线与范围

依据：`文档/AI_Agent_160课时学习计划_新增课程.xlsx` 中「每日学习计划」工作表。只读取课程内容，未执行单元格中的任何命令，未修改工作簿。

课程表第 54 课是「优化 Chunk/Top-K/Prompt；资料不足明确回答不知道」，与本次用户描述一致。第 36–55 课是当前 RAG 阶段，包含 Embedding、文件加载、切分、引用、Rerank、Hybrid Search、元数据过滤和评测。

| 课程范围 | 本项目安排 |
|---|---|
| 1–20 Python / LLM 基础 | 原练习保留在旧目录与备份中，公用模型调用转入 core |
| 21–35 Tool Calling | 作为历史学习资料，本次不扩展 |
| 36–46 文档加载 / 切分 / 入库 | DocumentLoader、DocumentChunker、IngestionPipeline |
| 47–52 检索 / 来源 / 精排 / 混合 / 过滤 | HybridRetriever、RAGPipeline 及独立组件 |
| 53–55 测试 / 优化 / 验收 | 15 个固定用例、离线回归、Chunk/Top-K/Prompt 实验 |
| 后续 Agent 与更深入课程 | 已完成独立的 LangGraph 单节点、双节点 State 传值和普通回答 / 本地 Tool 条件路由 Console；业务 Tool、Agent loop、MCP 等仍按课程逐步实现 |

课程表自身将第 56–70 课标为 Agent 与工作流，第 101–120 课标为模型微调与评测，后续还有部署等内容。最初按用户要求只整理 RAG 入库和问答；随后按用户的新要求，逐课增加独立的 LangGraph Console，不根据课程标题自动扩大到其他功能。

RAG 的后续验收仍可用同一组问题观察两路召回，再调 Chunk / Overlap / Top-K、拒答阈值和 Prompt。LangGraph 已练习单节点、两节点之间传递 State，以及按固定前缀选择普通回答或本地字符统计 Tool；后续课程再学习业务 Tool、工具循环和最大步数，届时可将 `RAGPipeline.ask()` 包装为只读 Tool。

协作限制：未获同意不接触数据库，不删除目录，不执行 Git/SVN。
