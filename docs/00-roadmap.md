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
| 56–60 Agent 与工作流入门 | 已完成概念、单节点、双节点 State 传值、普通回答 / 本地 Tool 条件路由，以及调用 JSON 订单 Tool 的成功 / 失败路由 |
| 61 多步订单工作流 | 已实现订单、支付、退款、总结；按业务结果提前结束，保留全部已查询结果 |
| 62 阶段 3 Tool Calling 迁移 | 已实现模型选择工具、分发执行、tool_call_id 结果回传、受控循环及最大模型调用次数 |
| 63 重试、恢复与执行预算 | 已实现有限重试、业务失败分支、模型 / Tool 次数、协作式超时和 Token / 估算费用控制；强取消与写幂等留作检查点 |
| 64 RAG 封装为 Agent Tool | 已接入 ask_knowledge_base，保留 RAG 答案、引用与状态；只学模型和工具循环，不加入预算或重试 |
| 65 Checkpoint | 在简版 RAG Agent 中保存 State，以 thread_id 区分会话；工具前暂停、手动恢复及失败后继续；识别重复执行风险 |
| 66–70 Agent 与工作流进阶 | 会话 Memory、人工确认、Tracing 和综合验收 |

课程表自身将第 56–70 课标为 Agent 与工作流，第 101–120 课标为模型微调与评测，后续还有部署等内容。最初按用户要求只整理 RAG 入库和问答；随后按用户的新要求，逐课增加独立的 LangGraph Console，不根据课程标题自动扩大到其他功能。

RAG 的后续验收仍可用同一组问题观察两路召回，再调 Chunk / Overlap / Top-K、拒答阈值和 Prompt。当前根入口进入 [第 66 课：会话 Memory](16-memory.md)，沿用模型与工具循环、内存 Checkpoint，只增加同会话追问、整轮历史裁剪和字符预算，不加入摘要或自动重试。第 60–65 课代码保留对照；第 65 课入口为 `main_workflow_checkpoint.py`，说明见 [Checkpoint](15-checkpoint.md)；第 64 课入口为 `main_workflow_rag.py`，说明见 [RAG Tool](14-rag-agent-tool.md)；第 63 课入口为 `main_workflow_recovery.py`，说明见 [重试和预算](13-agent-recovery.md)。

协作限制：未获同意不接触数据库，不删除目录，不执行 Git/SVN。
