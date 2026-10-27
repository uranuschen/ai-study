# 第 64 课：把 RAG 封装为 Agent Tool

本课入口保存在 `main_workflow_rag.py`；第 65 课入口保存在 `main_workflow_checkpoint.py`，第 66 课入口保存在 `main_workflow_memory.py`，第 67 课入口保存在 `main_workflow_approval.py`。当前 `main_workflow.py` 已进入 [第 69 / 70 课 Tracing 与订单诊断](19-order-diagnosis.md)。

本课只学核心：把现有 `RAGPipeline.ask()` 包装成 `ask_knowledge_base`，让模型按需要查询规则，再保留来源并综合回答。不新增 Token 统计、次数预算、超时、重试、Memory、Checkpoint 或 Tracing；第 63 课完整入口保存在 `main_workflow_recovery.py`。

## 核心流程

`prepare → model → tools → model → … → END`

- `prepare`：准备 system/user 消息和空结果。
- `model`：把 messages 与四个 Tool 的说明交给 LLM；有 tool_calls 就查工具，否则回答后结束。
- `tools`：执行 get_order/get_payment/get_refund 或 ask_knowledge_base，把结果作为 tool 消息回传。
- `ask_knowledge_base(question, pipeline, filters)`：调用原 `pipeline.ask()`，返回统一的 success/data/error；data 保留 answer、citations、status，不带 trace。
- Tool 执行失败直接 END，不重试；同批剩余调用标记未执行并配齐调用 ID。资料不足则保留 RAG 状态，由模型说明。

例如「A1002 的退款状态是什么，按规则通常多久能到账？」可以用 get_refund 查状态，用 ask_knowledge_base 查规则；顺序由模型选择。单纯查退款记录不必调用 RAG，查规则也不必查订单。

外层模型负责选工具和综合回答；原 RAG 内部仍包含检索、精排、证据组装、调用 LLM 和引用检查，并非只返回检索片段。无有效证据时直接返回资料不足，不调用内层 LLM。

## 运行和 Debug

本课入口是根目录 `main_workflow_rag.py`，图在 `src/agent_learning/workflows/rag_agent.py`。IDE 解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`，无需参数。

```bash
.venv/bin/python -B main_workflow_rag.py
```

用户运行时才读取已有配置、调用模型；调用 RAG 时会查询现有知识库。USE_OLLAMA 可切换到本机已有且支持 Tool Calling 的模型。入口设置 `settings.llm_timeout=None` 便于断点，`settings.local_files_only=True` 不下载模型；缺少本地模型或知识库资料需先准备。本次只做离线验证，不默认访问真实数据库或模型。

建议按以下顺序单步：

1. `main_workflow_rag.py`：创建原有 build_pipeline(settings) 和模型，再进入 graph.invoke()。
2. `rag_agent.prepare_node()`：查看初始 messages。
3. `model_node()`：查看模型返回的工具名称、参数和调用 ID。
4. `dispatch_tool()` → `ask_knowledge_base()` → `RAGPipeline.ask()`：查看规则问题、可信 filters、RAG 答案与引用。
5. `tools_node()`：查看 tool_call_id 配对，以及结果如何追加到 messages。
6. 再进 `model_node()`：模型基于工具结果给出回答后进入 END。

Console 打印 answer、stop_reason 和完整 tool_results，便于对照原始 RAG 答案及来源。每次调用的引用编号只属于这次调用，不跨调用合并。

## 来源与事实边界

- **订单事实**只以业务 Tool 返回的数据及 updated_at 为准；本地 JSON 是模拟状态，不冒充实时系统。
- **规则资料**由 ask_knowledge_base 查询；入口固定可信租户 acme、SECURITY_LEVEL=1、DOC_TYPE="policy"，实际参数只允许 question。提示模型只问规则、不带订单号；模型不能提供或修改租户、权限。
- DOC_TYPE 可改为 process/faq；本课不允许 record 或 None，避免查询订单快照覆盖业务事实。
- 知识库缺资料或引用无效时，保留原 RAG 的 status 与拒答说明；不编造规则、到账期限或来源。
- 原始引用保留不等于外层回答每句话都经过严格语义校验，本课只实现工具边界和来源保留。

现有 `sql/02_seed_documents.sql` 描述了 REFUND-POLICY 规则资料，但本次未核查真实库是否已入库、可检索；不执行种子或入库脚本。

## 离线检查

```bash
PYTHONPATH=src .venv/bin/python -B -m unittest discover -s tests -p test_rag_agent.py -v
```

离线测试替换模型和 RAG，不访问数据库/API，不读取真实密钥或下载模型。真实服务演示由用户运行入口后验证。
