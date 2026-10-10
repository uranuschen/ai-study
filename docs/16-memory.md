# 第 66 课：会话 Memory

只在上一课基础上加入多轮追问、历史裁剪和简单上下文预算。继续使用普通 dict / list 和原 RAG Agent，不引入摘要、长期 Memory、数据库存档、自动重试、超时或 Tracing；复用的方法上方标有 `#-- 复用的--`。

## 核心流程

`新问题 → prepare 追加 user → 整轮裁剪 → model → tools → 整轮裁剪 → model → … → END → 等待追问`

入口只创建一次模型、RAG 管道、graph 和 `InMemorySaver`。每轮提交 `question` 和可信 `tenant_id`，并使用同一个配置：

```python
config = {"configurable": {"thread_id": THREAD_ID}}
```

这是固定键名和嵌套格式，会话编号值可自定义。同一存档器中，相同 thread_id 读取同一会话 State，不同编号分别保存。它是逻辑会话编号，不是系统线程或并发锁。

本课与第 65 课的区别：新问题传入新的 dict，从 prepare 开始新一轮；不是传 None 恢复暂停点。本课不设置 `interrupt_before=["tools"]`，工具正常执行，不要求每次回车继续。第 65 课暂停演示保留在 `main_workflow_checkpoint.py`。

## 每轮保留什么、重置什么

- `messages`：使用本轮固定的 system 规则，接上同会话旧的 user / assistant / tool 消息，再追加本轮 user；不会重复追加旧 system。
- `pending_tool_calls`、`tool_results`、`stop_reason`、`answer`：开始新一轮时清空，避免沿用上一轮的结束原因或结果。
- `question`、`tenant_id`：使用本轮输入，仍复用原问题类型、非空和租户一致性校验。

旧轮次的业务 Tool / RAG 内容仍在 messages 中；当前 `tool_results` 只展示本轮结果。模型根据历史理解「它」等追问，不由代码硬写订单号。历史是之前的观察，不自动变成最新事实；需要当前状态时仍应查询业务 Tool，保留记录时间与来源边界。

输入无效时保留旧 messages，不追加无效问题，也不调用模型。

## 历史裁剪与上下文预算

入口顶部直接修改两个参数：

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `MAX_HISTORY_TURNS` | 2 | 最多保留 2 个旧轮次，另保留当前轮 |
| `MAX_CONTEXT_CHARS` | 12000 | messages 与 Tool schemas 的 JSON 字符数上限 |

`trim_messages()` 按 user 消息划分轮次，每次模型请求前优先删除最旧的完整轮次，保留 system 和当前轮。整轮包括 user、assistant 工具请求、对应 tool 结果和最终 assistant；不能只删一条 tool，否则会破坏工具调用 ID 配对。超出字符预算时可继续裁掉旧轮次，不新增摘要调用。

`context_size()` 统计 `{"messages": messages, "tools": TOOL_SCHEMAS}` 的 JSON 字符数。它不是实际 Token 数，也不是精确 API 请求字节数；中文、英文和不同模型的分词方式不同，不能直接换算成 Token。

如果只剩 system 与当前轮仍超预算，返回 `stop_reason="context_budget"`，不再请求模型，也不截断当前 Tool 结果。新增模型回复、Tool 结果后可能再次增长，所以下一次请求前还要检查。

Console 显示最近一次外层模型请求的 `prompt_tokens`，来自接口已有的 usage；接口未返回时显示「未返回」。它不是整轮累计 Token，也不含 RAG 内部模型调用，不能用于计算完整成本。历史和工具结果增加时通常会增长；裁剪后可能下降，但本课不实现准确 Token 预算。

## Memory 与 Checkpoint 的区别

Memory 是交给模型理解追问的会话内容；Checkpoint 是保存图 State 和执行进度的机制。本课把 messages 放在 State 中，由 Checkpoint 带到下一轮，模型本身没有因此修改权重。

裁剪更新当前 State 的 messages，减少下一次请求内容；不删除旧 Checkpoint 快照，不能当成存档空间清理。`InMemorySaver` 只在同一进程保留，退出或重启后丢失，没有跨进程持久化或长期用户记忆。

输入 `/new` 切换新的 thread_id，开始空历史，不删除旧存档；输入 q 退出。新的会话不会自动带入旧会话的订单号。

## 运行与 Debug

入口为根目录 `main_workflow.py`，图在 `src/agent_learning/workflows/memory_agent.py`。IDE 解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`，不需要参数。

```bash
.venv/bin/python -B main_workflow.py
```

建议连续输入：

1. `A1002 的退款状态是什么？`
2. `它退款处理中，是否代表已经到账？`
3. `/new`
4. `它的订单号是什么？`

第二轮应带着第一轮历史，模型可按需要查询规则；新会话没有第一轮消息，不能凭旧会话回答 A1002。真实模型选择 Tool 的数量与顺序不固定，以 Debug 中的请求为准。

断点顺序：

1. 入口的 `graph.invoke()`：追问只传新问题和租户，不覆盖 messages。
2. `prepare_memory_node()`：检查旧消息和追加 user，以及当轮字段重置。
3. `trim_messages()` 与 `context_size()`：对比裁剪前后轮次、字符数和完整 Tool 配对。
4. `memory_model_node()` → 原 `rag_agent.model_node()`：查看带历史的模型请求。
5. 原 `rag_agent.tools_node()`：观察 JSON / RAG 结果如何加入当前轮，再进入模型。

用户运行真实入口时才读取配置并调用外层模型；模型选择 RAG 时才查询已有知识库，有有效证据时才调用内层模型。入口保持 `llm_timeout=None` 便于断点，`local_files_only=True` 不下载模型。模型或 Tool 已处理的失败受控结束当前轮，不做自动重试。

## 离线检查

```bash
PYTHONPATH=src:tests .venv/bin/python -B -m unittest test_memory_agent -v
```

测试使用预设模型和 RAG，验证追问历史、会话隔离、整轮裁剪、预算结束与 Tool 消息配对，不读取真实配置、不访问数据库 / API 或下载模型。真实对话结果由用户运行入口后验证。

参考：[LangGraph 会话 Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)、[Checkpoint 与会话持久化](https://docs.langchain.com/oss/python/langgraph/persistence)。
