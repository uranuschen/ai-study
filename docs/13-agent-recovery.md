# 有限重试与恢复

当前实现统一在 `workflows/diagnosis_agent.py`，临时错误判断位于 `recovery_agent.py`。原独立 Console 入口已合并到 `main_api.py`。

模型和只读工具遇到连接失败、超时、限流或适合重试的服务端错误时，最多额外尝试一次。业务失败、参数错误和永久错误直接结束。敏感模拟动作异常不自动重试。

每轮问题保留有限的模型和工具执行机会，实际失败也会消耗机会。人工等待、普通恢复和审批不会重新经过 prepare，因此不会刷新额度。没有 Token、费用、耗时或重试次数的统计记录，也没有原来的复杂预算执行器。

新会话设置 `pause_before_tools=true` 可以演示工具前暂停。`POST /api/agent/sessions/{session_id}/resume` 使用原 Checkpoint 继续；人工审批必须调用专门的 approvals 接口。已受控结束的任务没有待执行节点，不能恢复成新任务。

完整参数与业务返回见 [FastAPI](20-fastapi.md)。
