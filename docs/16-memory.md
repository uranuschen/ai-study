# 第 66 课：会话 Memory

同一 session_id 的新问题从 prepare 开始，保留已有消息并追加本轮 user。创建新会话隔离历史，对应原 Console 的 /new。

`workflows/memory_agent.py` 按 user 消息将历史分成完整轮次。裁剪时整轮处理，不拆开 assistant 的工具请求和对应 tool 结果。综合图默认保留最近两个旧轮次，并检查消息加工具说明的字符上限。

历史用于理解“它”等追问，不证明业务状态仍然没有变化。询问最新状态时仍应重新查询业务 Tool。当前没有摘要模型、长期记忆或消息数量统计。

`GET /api/agent/sessions/{session_id}` 只返回保留的用户与最终回答，不展示 system、工具协议和模型内部内容。

[API 调用与断点](20-fastapi.md)
