# 第 65 课：Checkpoint 暂停与恢复

Checkpoint 保存图的业务状态和待执行位置。API 使用 `session_id` 找到服务端会话，内部将同一个编号作为 LangGraph 的 thread_id，不生成追踪记录。

创建会话时提交 `{"pause_before_tools":true}`。触发普通工具后返回 `paused`，调用 `POST /api/agent/sessions/{session_id}/resume` 并提交 `{}`，通过 `graph.invoke(None, config=原配置)` 继续。

新问题传新的问题字典，从 prepare 开始；普通恢复传 None，沿用原状态；人工审批通过 Command(resume=决定) 恢复。三种调用不能混用。

已受控结束的失败没有待执行节点，不能再次恢复。仍有待执行位置的异常可以恢复，但失败节点会重新执行。敏感模拟动作单独处理异常并结束，不自动重放。

内存 Checkpoint 只在当前进程有效，服务重启后会话消失。当前不接存档数据库，不建立新表。

[API 调用与断点](20-fastapi.md)
