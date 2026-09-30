# 直接运行与断点调试

## 入库

打开根目录 `main_ingest.py`，只需要看这三个变量：

```python
FILE_PATH = BASE_DIR / "data" / "enterprise_documents.json"  # 修改导入文件。
TENANT_ID = "acme"  # 默认租户。
WRITE_TO_DB = False  # 先预览；用户准备好表后，改为 True 才实际写库。
```

在 IDE 中选择解释器 `/Users/uranuschen/ai-study/.venv/bin/python`，对这个文件点击 Debug。建议在 `main()` 中的 `pipeline.run(...)` 打断点，单步进入 `IngestionPipeline.run()`，观察 `documents`、`parents`、`chunks`、`vectors` 和 `status`。

不再需要填写 ingest、文件路径或 --write 等启动参数。

## 问答

打开根目录 `main_ask.py`，修改：

```python
QUESTION = "A1002 的退款到账了吗？"  # 修改你的问题。
TENANT_ID = "acme"  # 当前租户。
SECURITY_LEVEL = 1  # 允许读取的资料级别。
BUSINESS_MODULE = None  # 只查财务时改为 "finance"。
DOC_TYPE = None  # 只查制度时改为 "policy"。
TAGS = []  # 需要时填已有标签。
USE_OLLAMA = True  # 当前用本机 Ollama 回答；改为 False 时使用 DeepSeek。
OLLAMA_MODEL = "qwen3:8b"  # 本机安装的 8B Q4 模型；可改为 "deepseek-r1:7b"。
```

`USE_OLLAMA=True` 时，只有最后的回答模型切换到本机 `http://127.0.0.1:11434/v1`。向量检索、BM25、精排、数据库过滤和引用校验都沿用原流程。Ollama 的模型名要与 `ollama list` 显示的一致；本机已验证 `qwen3:8b` 和 `deepseek-r1:7b` 都是 `Q4_K_M`。兼容客户端传入的 `ollama` 只是本地占位 key，不是 DeepSeek 密钥。改为 `False` 即恢复在线模型。

本地模型可能输出 Markdown 代码围栏，程序只去掉最外层围栏；如果 JSON 字段或引用编号仍不符合要求，依然明确拒答。Qwen 8B 的独立格式测试约 71 秒返回；开始调用 Ollama 时终端会显示等待提示，最终答案仍要等模型完成后才会打印。

在 `pipeline.ask(QUESTION, filters)` 打断点，进入 `RAGPipeline.ask()`，依次观察：

| 变量 | 含义 |
|---|---|
| plan | 改写问题、意图、业务编号 |
| effective | 本次实际过滤条件 |
| hits | 两路检索融合后的候选 |
| ranked | CrossEncoder 重排结果 |
| supported | 达到相关性阈值的证据 |
| context | 实际交给 LLM 的正文 |
| citations | 原文来源与位置 |
| raw | 模型原始回答 |
| answer | 检查后的最终答案 |

## 第 64 课：把 RAG 封装为 Agent Tool

当前入口为根目录 `main_workflow.py`，解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`。图只保留 `prepare → model → tools → model → END`；模型可以直接回答，也可以按需要调用业务 Tool 和 `ask_knowledge_base`。没有 Token 统计、预算、重试或时间限制。

```bash
.venv/bin/python -B main_workflow.py
```

建议输入「A1002 的退款状态是什么，按规则通常多久能到账？」模型用业务 Tool 查状态，用 RAG 查规则，再组织答案；单纯查退款记录时不必调用 RAG。实际选工具顺序由模型返回的 `tool_calls` 决定。

断点依次放在 `main_workflow.py` 的 `graph.invoke()`、`rag_agent.model_node()`、`dispatch_tool()`、`ask_knowledge_base()`、`RAGPipeline.ask()` 和 `tools_node()`。观察 RAG 返回的 `answer/citations/status` 如何进入 tool 消息，再成为下一轮模型的上下文。Console 保留每次调用的原始结果和引用。

入口固定 `TENANT_ID="acme"`、`SECURITY_LEVEL=1`、`DOC_TYPE="policy"`；资料类型可改 `process/faq`，本课不查订单快照 `record`，也不设为 `None`。模型只能提供规则问题，不能修改过滤条件。设置 `llm_timeout=None` 方便 Debug，`local_files_only=True` 不下载模型。

用户运行时会访问所配置的模型；调用 RAG 时还会查询现有知识库，有有效证据时才在 RAG 内部调用模型。资料或模型缺失需先准备，本次没有访问真实服务。完整课时说明与离线入口见 [第 64 课](14-rag-agent-tool.md)。

## 第 63 课：重试、失败恢复与预算（保留入口）

Debug 入口保留为根目录 `main_workflow_recovery.py`；解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`，无需命令行参数。运行会实际访问所配置的模型；`USE_OLLAMA=False` 沿用已有 DeepSeek 兼容配置，改为 `True` 时使用本机已有、支持 Tool Calling 的模型。业务 Tool 仍只读 JSON。`MAX_STEPS` 包含失败、重试和最终回答，`MAX_TOOL_CALLS` 限制全部分发尝试，另有重试、时间、Token 和估算费用参数。单价为教学演示值，真实运行前需核对。

```bash
.venv/bin/python -B main_workflow_recovery.py
```

建议按下面顺序打断点：

| 文件 / 方法 | 观察内容 |
|---|---|
| `main_workflow_recovery.py` 的 `graph.invoke(initial_state)` | 原始问题、可信租户、最大模型调用次数 |
| `workflows/recovery_agent.py` 的 `prepare_node()` | 消息、可信预算、截止时间、初始计数 |
| `check_model_budget()` / `charge_usage()` | 请求前预留、返回后实际或未知用量记账 |
| `model_node()` | 有限重试、每次实际尝试、临时与永久错误 |
| `workflows/tool_model.py` 的 `request_with_tools()` | SDK 接收 timeout / max_tokens，返回消息与 usage |
| `dispatch_tool()` / `tools_node()` | 静态白名单、可信租户、Tool 总次数与业务失败 |
| `wait_to_retry()` | Retry-After、等待上限和剩余总时间 |
| `failure_node()` | 不调用 LLM，明确说明失败原因 |
| `finish_node()` | 为跳过请求配齐 ID，保留证据并记录总耗时 |

先输入「查询 A1002 的退款记录」，观察模型是否直接选择 `get_refund`。再输入「完整检查 A1002 的订单、支付和退款」，观察模型逐轮选择或同轮请求多个 Tool。真实模型路径可能变化，判断依据是返回的 `tool_calls`，本课没有固定写死订单 → 支付 → 退款。

将 `MAX_STEPS` 暂改为 `1`，如果第一轮请求工具，会在其他预算允许时保存这一批结果后结束；第一轮直接回答则正常完成。当前默认 `ENABLE_TIMEOUTS=False`：模型 SDK、Tool 与整体超时均关闭，`deadline=None`，断点暂停不会触发超时失败；耗时统计、次数、Token 与费用预算仍生效。需要演示超时分支时再改为 `True`。开启后的同步超时是返回后的检测与停止后续调度，不是远端强取消。完整说明与具体离线 Debug 方法见 [第 63 课](13-agent-recovery.md)。离线运行 `tests/test_recovery_agent.py` 可观察预设临时错误恢复与预算失败，旧图测试和第 60–62 课文件保留对照。

## 配置和依赖

数据库在 `.env.db`，DeepSeek Key 在 `.env`；`load_settings()` 使用旧代码熟悉的 `load_dotenv()` 和 `os.getenv()` 读取。支持旧 `DEEPSEEK_API_KEY`，非空的 `LLM_API_KEY` 优先。配置文件位置不随 IDE 工作目录改变。详情见 [配置说明](08-db-config.md)。

继续使用旧环境的 sentence-transformers 3.x、rank_bm25、jieba、psycopg2 和模型。默认 LOCAL_FILES_ONLY=true，不自动下载模型。模型文件缺失时由用户自行决定如何准备，不会在测试中下载。

PDF 按页加载；Word 提取段落和表格；Excel 首行为表头并按行保留来源；JSON 保留 payload 和指定向量化字段。普通文件默认 module=general、doc_type=reference、version=1.0，需要指定版本或更多业务字段时使用企业 JSON。

## 常见情况

| 情况 | 处理 |
|---|---|
| 初始化后没有向量 | 原文是 pending；用户运行 main_ingest.py，设置 WRITE_TO_DB=True |
| 同版本内容或切分参数变化 | 提升 JSON 中的 version 再导入，不覆盖旧版本 |
| 模型缓存不存在 | 准备本地模型，或由用户决定设置 LOCAL_FILES_ONLY=false 下载 |
| 查不到标签 | 当前精确匹配已有标签，不自动包含父标签的所有子标签 |
| 返回资料不足 | 看 filters、hits、ranked 和 context，确认资料存在且有权限读取 |
| 返回 invalid_citations | 模型引用的编号缺失或越界，程序已拒答 |
| 数据库或模型报错 | 按异常定位，不把运行失败当成资料不足 |

自动测试默认离线运行；本地 Ollama 的独立格式测试不访问数据库。完整问答由用户运行验证。未经用户明确同意，不操作数据库、不删除目录，不执行任何 Git/SVN 操作。
