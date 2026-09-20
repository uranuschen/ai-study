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
```

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

本次仅执行离线测试。真实数据库、模型和问答须由用户自行运行验证。未经用户明确同意，不操作数据库、不删除目录，不执行任何 Git/SVN 操作。
