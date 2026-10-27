# 第 65 课：Checkpoint

沿用第 64 课的订单 / RAG Agent，只增加图状态保存、会话标识和暂停恢复。没有新增业务流程、自动重试、Token / 预算控制、超时、多线程锁或多轮 Memory。

本课入口保存在根目录 `main_workflow_checkpoint.py`；第 66 课入口保存在 `main_workflow_memory.py`，第 67 课入口保存在 `main_workflow_approval.py`。当前 `main_workflow.py` 已进入 [第 69 / 70 课 Tracing 与订单诊断](19-order-diagnosis.md)。第 65 课的暂停与手动恢复逻辑保留不变。

## 核心流程

`prepare → model → 暂停 → tools → model → … → END`

入口创建 `InMemorySaver`，`checkpoint_agent.py` 复用原 prepare/model/tools 节点，在 `compile()` 中设置 `checkpointer` 和 `interrupt_before=["tools"]`。模型直接回答时不会进入工具前暂停。

1. `config = {"configurable": {"thread_id": THREAD_ID}}`：选择本次逻辑会话。
2. `graph.invoke(next_input, config=config)`：首次 next_input=initial_state，从 prepare 开始，保存每一步图状态。
3. `snapshot = graph.get_state(config)`：values 是已保存的 State，next 是待执行节点。
4. 工具前暂停时，回车令 next_input=None，再执行同一行 invoke 从存档继续；下一批工具仍会再次暂停。
5. 存在有效存档且本次未抛异常时，`snapshot.next` 为空才按图到达 END 处理，打印结果；没有存档或异常后 next 为空时安全退出，不当成成功。

恢复要使用同一个 graph、saver 和 thread_id。不要把初始 dict 再传一次：那会从 prepare 开始新一轮，并清空消息与结果，本课尚未实现多轮问答 Memory。

## State、会话与内存

State 仍是原来的七个字段：question、tenant_id、messages、pending_tool_calls、tool_results、stop_reason、answer。Checkpoint 保存它们，不额外加入业务字段。

同一个 saver 下，不同 thread_id 的存档分别保存；thread_id 是逻辑会话标识，不是操作系统线程，也不替代租户权限校验或并发锁。本课 Console 顺序执行，不演示并发。

`InMemorySaver` 只在当前进程中的 saver 对象里保留。输入 q 退出或重启程序后，存档丢失；本课不写磁盘、不连接 Checkpoint 数据库。不要把内存保存理解成重启后仍可恢复。

## 失败后继续与重复执行

模型节点异常会抛出，入口捕获后查看存档中的待执行 model。先排查或修复原因，再回车令 next_input=None，用同一行 invoke 手动继续；程序没有自动重试。

已完成节点的 State 不必从 prepare 重做，但失败节点会从头执行。如果它在抛异常前已经发出模型请求或产生副作用，恢复可能重复请求、产生额外费用或重复写入。Checkpoint 不保证 exactly-once。本课业务 Tool 仍只读 JSON，写操作幂等性留待真正引入写操作时处理。

已经处理成 `tool_error` 并进入 END 的 Tool 失败，没有待执行节点，不属于这里的失败恢复。重新提交输入是新一轮执行，不是恢复结束的图。

## 运行与 Debug

入口为根目录 `main_workflow_checkpoint.py`，第 64 课原入口保存在 `main_workflow_rag.py`。IDE 解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`，不需要命令行参数。

```bash
.venv/bin/python -B main_workflow_checkpoint.py
```

输入「A1002 的退款状态是什么，按规则通常多久能到账？」在工具前暂停时，观察 pending_tool_calls 尚未执行，回车后观察 tool_results 和 messages 增加。本课暂停仅用于教学，不是敏感操作的人工审批。

断点建议放在入口的 `graph.invoke(next_input, config=config)`、`graph.get_state(config)` 和 `checkpoint_agent.py` 的 `compile()`；同一 invoke 行首次接收 initial_state，恢复时接收 None，节点内部仍单步进入 `rag_agent.py` 的 prepare/model/tools。

默认 `USE_OLLAMA=False` 沿用已有模型配置；`llm_timeout=None` 方便断点，`local_files_only=True` 不下载模型。只有用户运行真实入口时才访问模型，调用 RAG 时才查询现有知识库。本次只做离线验证，不访问真实数据库/API 或下载模型。

## 离线检查

```bash
PYTHONPATH=src:tests .venv/bin/python -B -m unittest test_checkpoint_agent -v
```

测试使用预设模型和 RAG，验证 State 保存、两个 thread_id 隔离、工具前暂停、恢复及模型失败后继续，不访问真实服务。可在测试中的 invoke/get_state 处打断点，确定性观察失败恢复。

参考：[LangGraph Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)、[静态断点与暂停恢复](https://docs.langchain.com/oss/python/langgraph/interrupts)。
