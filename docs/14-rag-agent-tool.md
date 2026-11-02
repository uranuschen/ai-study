# 第 64 课：把 RAG 作为 Agent Tool

`ask_knowledge_base` 只接收规则问题，例如 `{"question":"退款通常多久到账？"}`。内部复用 `RAGPipeline.ask()`，返回原始答案、引用和资料是否足够等业务结果。

Agent 模型可以按需选择订单、支付、退款和知识库 Tool。订单事实来自 JSON；知识库只查询服务端限制的 policy/process/faq 资料，不能用旧快照替代订单当前状态。

知识库资料不足时明确拒答。多个规则查询的引用按问题分组，每组的 `[1]` 只对应那一次查询，不能混合不同查询的来源。

基础图保留在 `workflows/rag_agent.py`；当前综合图在 `diagnosis_agent.py`。统一通过会话消息接口使用，例如 `{"question":"查询 A1002 的退款，并说明通常到账规则"}`。

[API 调用与断点](20-fastapi.md)
