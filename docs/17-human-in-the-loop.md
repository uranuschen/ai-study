# 第 67 课：敏感操作人工确认

在第 66 课上只增加模拟取消订单的审批流程。订单、支付、退款查询与 RAG 保持原逻辑；继续保留会话消息、整轮裁剪和字符预算，不增加真实写操作、自动重试、审批数据库或 Tracing。新加 / 调整代码的上方注释分别标为 `（67课新加）` / `（67课调整）`。

本课入口保留在 `main_workflow_approval.py`，图：`src/agent_learning/workflows/human_approval_agent.py`。当前 `main_workflow.py` 已进入 [第 69 / 70 课 Tracing 与订单诊断](19-order-diagnosis.md)；本课简版逻辑保留不变，第 66 课入口仍在 `main_workflow_memory.py`。

## 主要流程

`新问题 → prepare → model → 普通 Tool / approval → model → END`

普通查询 Tool 直接执行；只有模型提出 `cancel_order` 才进入 approval 节点：

1. 检查模型参数只包含非空 `order_id`，用可信 `tenant_id` 查询本地 JSON。
2. 订单不存在、不可读取或不是待支付状态，直接以 `tool_error` 结束，不发起审批。本课用 `A1001` 演示；`A1002` 已支付，不支持模拟取消。
3. 同会话已经模拟取消过该订单，返回防重复结果，不再次暂停或执行。
4. 构造待审批信息，执行 `interrupt(request)` 暂停。
5. 人工确认 / 拒绝后，用 `Command(resume=...)` 恢复；校验决定与目标参数。
6. 确认才调用模拟函数，把结果写入 tool 消息和 State，再让模型总结。拒绝以 `approval_rejected` 结束，不再请求模型；格式或目标不匹配以 `approval_invalid` 结束。

同一模型回复可能请求多个 Tool。本课逐个处理队列：普通查询执行完立即保存进度，下一个取消请求单独进入审批节点。因此审批恢复不会为了重跑同一节点而再次执行前面的查询。失败 / 拒绝后，剩余请求不执行，但仍补上对应 `tool_call_id` 的未执行消息，避免下一轮消息协议缺项。

## 暂停与恢复的关键代码

```python
#（67课新加）只有敏感节点在满足业务条件时主动暂停。
decision = interrupt(request)

#（67课新加）固定键名与嵌套结构，编号值由入口选择。
config = {"configurable": {"thread_id": THREAD_ID}}

#（67课新加）确认 / 拒绝使用同一个图、存档器和会话编号。
result = graph.invoke(Command(resume={**request, "decision": "approve"}), config=config)
```

`interrupt()` 首次调用暂停并把 request 交给外部；本次 `invoke()` 返回的 `result["__interrupt__"][0].value` 就是入口展示的审批信息。恢复值成为审批节点中的 decision。

重要区别：恢复时审批节点从函数开头重新执行，不是继续执行之前 Python 栈中的下一行。因此参数解析和只读订单校验会再做一次；模拟取消必须放在 `interrupt()` 返回、审批校验成功之后。不要用宽泛 `try/except` 包住 interrupt，把正常暂停误当成失败。

图使用 `graph.compile(checkpointer=checkpointer)`，没有第 65 课的 `interrupt_before=["tools"]`。第 65 课是静态断点，可用 `invoke(None, config)` 继续；第 67 课需要人工决定，使用 `Command(resume=...)`。不要在审批未完成时提交新 question 覆盖当前任务。

## 审批参数

待审批信息只有以下五个字段，程序从本次工具请求与可信身份构造：

```python
request = {
    "action": "cancel_order",
    "order_id": "A1001",
    "tenant_id": "acme",
    "tool_call_id": "模型返回的本次工具调用 ID",
    "mode": "simulate",
}
```

恢复值必须严格为这五个字段加一个 `decision`，且五个字段的值都与当前 request 一致；decision 只接受 `approve` / `reject`。缺字段、额外字段、仅传字符串、修改订单 / 租户 / 操作 / 调用 ID 都不能执行取消。模型的工具参数只能传订单号，不能自行传 approved、tenant_id 或数据文件路径。

Console 自动保留 request，只让人选择决定；不是让人重新填写订单参数。thread_id 隔离存档，tenant_id 决定业务权限，两者用途不同；thread_id 不代替权限校验或并发锁。

## 模拟结果与重复恢复边界

确认后的结果包含 `status="模拟已取消"`、`simulated=True`、`source="simulation"`，保留 `original_status` 和原记录的 `source_updated_at`。JSON 没有改动，后续 `get_order` 仍会读到原来的待支付状态；回答必须说明是模拟结果，不能称为真实取消成功。

State 中的 `simulated_cancellations` 保存同会话已经模拟取消的订单号，不随历史消息裁剪清空。正常重复取消同一订单只返回 `duplicate=True`，不再调用模拟函数；已经进入 END 后重复提交旧 Command，也不会重新执行已完成的模拟节点。拒绝不会写入这份成功模拟记录。

这只是本课正常执行路径的检查，不是生产写操作 exactly-once 保证：如果真实写操作已经发生、节点尚未保存成功就崩溃，重新执行仍可能重复。内存存档退出 / 重启即丢失，换 thread_id 也没有原会话的防重复记录。本课不实现外部业务幂等键，不真实取消订单。

## 运行与 Debug

```bash
.venv/bin/python -B main_workflow_approval.py
```

IDE 解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`，不需要命令行参数。建议先输入 `取消 A1001 订单`：

- 输入 `y` / `approve`：确认模拟，随后模型总结。
- 输入 `n` / `reject`：拒绝并结束当前轮。
- 审批时输入空值、其他文字或 `/new`：继续等待合法决定，不执行取消。
- 输入 `q`：退出；当前进程的内存存档不跨进程保留。

完成一轮后可再次要求取消 A1001，观察同会话防重复结果；也可输入 `取消 A1002 订单`，观察业务失败不进入审批。正常提问时 `/new` 切换新会话，q 退出。真实模型选择工具与顺序不固定，以返回的 tool_calls 为准。

建议断点依次放在：

1. 入口首次 `graph.invoke()`：只提交新问题和可信租户。
2. `approval_node()` 的 `interrupt(request)`：观察暂停信息和本次工具调用 ID。
3. 入口 `resume_approvals()`：看 `result["__interrupt__"]`、人工输入及 `Command(resume=...)`。
4. `validate_approval()`：检查决定和审批目标是否严格匹配。
5. `simulate_cancel_order()`：只有有效人工确认才进入；观察原状态和模拟来源。
6. `complete_tool_call()`、`choose_tool_route()`：看 tool 消息配对、队列推进、拒绝走 END，以及模拟成功后返回 model 总结。

用户运行真实入口时会调用配置的外层模型；仅在模型选择 RAG 时查询知识库，有有效证据时才调用内层模型。入口保留无客户端超时以方便 Debug、本地模型文件限制不下载；本次实现只运行离线测试，不访问数据库 / API、不修改业务 JSON。

## 离线检查

```bash
PYTHONPATH=src:tests .venv/bin/python -B -m unittest test_human_approval_agent -v
```

预设模型与 RAG 用于检查：普通 Tool 不暂停、确认 / 拒绝、审批参数绑定、业务失败、多个请求的消息配对、同会话重复模拟和已结束恢复。真实模型对话由用户运行入口后验证。

参考：[LangGraph 动态 interrupt 与 Command 恢复](https://docs.langchain.com/oss/python/langgraph/interrupts)。
