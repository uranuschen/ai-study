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
| 后续 Agent 与更深入课程 | 暂不实现；用户继续学习时单独建目录 |

课程表自身将第 56–70 课标为 Agent 与工作流，第 101–120 课标为模型微调与评测，后续还有部署等内容。用户将后续学习统称为 AI Agent 深入阶段，本次以用户明确的“当前只做入库和问答”作为范围，不根据课程标题扩大开发任务。

建议下一步：先用同一组问题观察两路召回，再调 Chunk / Overlap / Top-K，然后校准拒答阈值，最后比较 Prompt。一次只改变一个因素，记录失败案例。完成 RAG 验收后，可将 `RAGPipeline.ask()` 包装为只读 Tool；届时再引入 Agent 状态、工具循环、最大步数和 Memory。

协作限制：未获同意不接触数据库，不删除目录，不执行 Git/SVN。
