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

## 第 60 课：工作流调用订单 Tool

Debug 入口为根目录 `main_workflow.py`；解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`，无需命令行参数，Console 输入订单号。IDE 使用可输入的终端，不使用只读输出窗口。入口顶部的 `DATA_FILE` 指向 `data/business_demo.json`，`TENANT_ID` 默认 `acme`。

```bash
.venv/bin/python -B main_workflow.py
```

建议按下面顺序打断点：

| 文件 / 方法 | 观察内容 |
|---|---|
| `main_workflow.py` 的 `graph.invoke(initial_state)` | 原始订单号、入口租户、尚未填充的 Tool 结果 |
| `workflows/business_tool.py` 的 `prepare_node()` | `question` 去空格、转大写后写入 `order_id` |
| `workflows/business_tool.py` 的 `get_order_node()` | 将 `order_id`、`tenant_id`、数据文件传给 Tool |
| `business/tools.py` 的 `get_order()` | JSON 内容、同时匹配租户与订单号、统一返回字典 |
| `workflows/business_tool.py` 的 `choose_result_route()` | Tool 结果已经合并到 State，根据 `success` 选择标签 |
| `workflows/business_tool.py` 的 `answer_node()` / `error_answer_node()` | 最终 `branch` 和 `answer` |

成功案例输入 `A1002`；业务失败案例输入 `A9999`；空参数案例只按回车。文件失败案例可临时把 `DATA_FILE` 改为一个不存在的文件，再 Debug，观察 `error_answer_node()`，之后恢复配置。完整学习步骤见 [第 60 课说明](10-workflow-tools.md)。

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
