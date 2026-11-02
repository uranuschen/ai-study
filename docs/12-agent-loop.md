# 第 62 课：Agent 循环

核心技术点是：模型读取消息与工具说明 → 返回 tool_calls → 程序按白名单执行 Tool → 用相同 tool_call_id 回传结果 → 模型继续判断或给出最终回答。

普通函数负责真实业务，模型只选择工具名和业务参数。租户、读取权限、文件路径和人工决定都由服务端提供。无工具调用且有完整文字时才视为最终回答，截断响应和坏协议不能执行工具。

原基础图保留在 `workflows/agent_loop.py`。当前完整入口通过 `api/agent.py`、`services/agent_service.py` 和 `workflows/diagnosis_agent.py` 提供，包含后续课程的 RAG、会话与审批。

创建会话后，调用 `POST /api/agent/sessions/{session_id}/messages`，例如 `{"question":"查询 A1002 的退款记录"}`。程序保留内部执行上限，避免模型无限循环；没有执行统计或日志返回。

[API 调用与断点](20-fastapi.md)
