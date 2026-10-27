# 第 69 课：节点、Tool、Token 与耗时 Tracing

入口为 `main_workflow.py`，与 [第 70 课订单诊断](19-order-diagnosis.md) 共用完整流程；追踪辅助在 `src/agent_learning/workflows/tracing.py`，内外层模型共用的执行器在 `run_execution.py`。相关新加 / 调整代码上方以 `# (69)` 标记，不接外部平台，不新增日志文件。

本课不是再加订单业务，而是把「哪一次执行、哪一步、成功还是失败、用了多久和多少 Token」串起来。原始 messages 与业务结果仍按原流程存在 State；Tracing 另建安全摘要，不能直接把整个 State 打进日志。

## 一次执行怎样串起来

`thread_id → run_id → 节点 span → Tool span → RAG / LLM 子 span`

- `thread_id`：逻辑会话，关联历史和 Checkpoint，不是操作系统线程或权限凭据。
- `run_id`：本轮问题的编号。新问题重新生成；人工审批恢复仍用原编号，不清空当前追踪或预算。
- `span_id` / `parent_id`：当前步骤和父步骤，用于知道某次模型请求属于哪一个节点或 Tool。
- `tool_call_id`：Tracing 中以短哈希表示，协议消息本身仍保留原 ID，便于请求与结果配对。

`TraceRecorder.start()` 写开始事件，`finish()` 写结束事件，`summary()` 汇总本轮结束事件。每条记录只包含固定技术字段：种类 / 名称、状态、尝试次数、重试次数、单调时钟时间与安全错误类别。单调时钟适合计算间隔，不是业务更新时间或墙上日期。

RAG 的六个阶段分别是 `rag_query`（意图与过滤）、`rag_retrieve`（混合召回）、`rag_rerank`（精排）、`rag_context`（证据整理）、`rag_generate`（生成）、`rag_validate`（校验）。它们归属于知识库 Tool，内部实际 LLM 请求归属于生成阶段；无有效证据时跳过生成和校验，不产生虚假模型用量。

## 记录什么，不记录什么

| 边界 | 记录 | 不记录 |
|---|---|---|
| 节点 / Tool | 名称、开始 / 结束、状态、耗时、尝试 / 重试 | 整份 State、完整 Tool 结果 |
| Tool 参数 | 白名单字段摘要，订单号部分遮盖，规则问题完整遮盖 | 任意 JSON、未知字段、自由文本 |
| 模型请求 | 外层 / RAG 内层、用量、预留、估算费用 | Prompt、messages、资料正文、模型原始输出 |
| 失败 | timeout / connection / HTTP 类别 / validation / system，以及受控结束原因 | `str(error)`、响应正文、请求头、密钥、连接串 |

脱敏是只挑安全字段，而不是先把所有内容写入再替换几段文字。日志摘要不等于业务证据；最终回答与 RAG 引用仍由原有结果链路提供。

## Token 与费用的边界

只在每次实际 LLM 请求结束时记一次用量。外层 Agent 和 RAG 内层都要计入；模型失败与重试也留下独立尝试记录。RAG 作为 Tool 包含内部模型，但 Tool 事件不再累计同一笔 Token / 费用。

接口合法返回 `prompt_tokens` / `completion_tokens` 时，分别作为输入 / 输出用量；如果 `total_tokens` 更大，差额在 Trace 中单独作为未分类用量保留。预算沿用第 63 课的保守办法，把这个差额按输入单价计入估算；不是在输入 / 输出之外重复加整份总量。reasoning 等明细不能再不加区分地重复相加。字段定义见 [Chat Completions 官方接口说明](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。

接口没返回完整 usage 时：

- Trace 的实际 Token 为未知，不填零，不把粗估伪装成 API 用量。
- 预算按请求前的保守预留扣账，防止失败后无限重试绕过限制。
- 汇总分开显示已知 Token、未知用量次数、已知费用估算和含预留的预算估算；有未知调用时，总费用标记不完整。

费用按「输入 Token × 输入单价 + 输出 Token × 输出单价」估算，再除以百万；金额使用 `Decimal`，以字符串存在 State。入口单价只是教学演示值，不是 DeepSeek 实时报价，也未计算缓存折扣、其他并发任务或账号账单；不能承诺账单绝对不超支。

## 耗时不能简单全加

节点耗时通常已经包含内部 Tool / LLM 耗时，因此不能把父子跨度全部相加当总耗时。本轮墙钟间隔单独记录，节点与 Tool 按名称分别汇总，只用来找慢点。

人工审批会让本轮间隔增加，但不是模型一直工作；不要把等待人工的时间当模型推理时间。默认关闭时间限制，Debug 停留只影响记录的耗时，不触发超时失败。

`SHOW_TRACE_EVENTS=True` 时，收尾后的 Console 只打印 `phase="end"` 的完成事件；设为 False 只展示汇总，不影响 State 中保留的完整起止事件。审批暂停时只打印截至当时的汇总，已完成事件可在 State 查看，避免恢复后重复打印同一条事件；日志不显示原始模型调用 ID。

## 看一次失败

先看本轮 `stop_reason`，再通过相同 `run_id` 定位失败的节点 / Tool / LLM 结束事件，检查错误类别、尝试次数、重试和耗时。最后查看模型用量是 API 返回还是未知预留，判断为何进入次数、Token 或费用预算分支。

实现和回归只使用离线预设模型，不连接数据库、调用真实模型或下载模型。实际服务的延迟、用量与费用由用户运行入口后再观察，不能拿离线预设数字当真实成本。

```bash
PYTHONPATH=src:tests .venv/bin/python -B -m unittest test_tracing -v
```

可单独 Debug `test_nested_node_tool_and_llm_count_tokens_and_cost_only_once` 看嵌套统计；`test_cost_summary_separates_known_and_reserved_costs` 看实际已知与预算预留的区别；参数和异常脱敏也由离线用例检查。
