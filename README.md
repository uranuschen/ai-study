# AI 学习项目：企业 RAG

当前 RAG 阶段学到第 54 课「优化 Chunk / Top-K / Prompt；资料不足明确回答不知道」。RAG 代码按 old/ 的普通类、函数、字典和现有库调用整理，保留资料入库、用户问答两条主流程；独立的 LangGraph Console 已进入第 61 课「多步订单工作流」，按订单、支付结果选择是否继续查询退款，最后保留已有业务结果并总结。表结构继续以 sql/ 中现有文件为准。

## 直接运行和 Debug

打开下面两个根目录文件，在 IDE 中直接点击 Run / Debug，解释器选择项目 `.venv/bin/python`，不需要填写命令行参数。

| 文件 | 在文件顶部改什么 | 默认行为 |
|---|---|---|
| [main_ingest.py](main_ingest.py) | FILE_PATH、TENANT_ID、WRITE_TO_DB | 当前文件为 WRITE_TO_DB=True；改为 False 才只预览 |
| [main_ask.py](main_ask.py) | QUESTION、TENANT_ID、SECURITY_LEVEL、BUSINESS_MODULE、TAGS、USE_OLLAMA | 默认调用现有模型；USE_OLLAMA=True 时改用本机 Ollama 回答 |

```bash
# 先检查 main_ingest.py 中的 WRITE_TO_DB；False 只预览，True 会写库。
.venv/bin/python main_ingest.py

# 用户完成建表、初始化和真实向量入库后再执行问答。
.venv/bin/python main_ask.py
```

真正入库：用户先手动执行 SQL 建表和初始化，再确认 `main_ingest.py` 的 `WRITE_TO_DB=True` 后运行。当前文件已经设为 `True`；只想预览时先改回 `False`。程序不会自动建表、删表。旧的 `ingest / ask / --write` 子命令已退出使用，不需要再学习 argparse。

## LangGraph Console：第 61 课多步订单工作流

运行 [main_workflow.py](main_workflow.py)，在 Console 直接输入订单号并按回车；IDE Debug 时使用可输入的终端。入口调用 [order_flow.py](src/agent_learning/workflows/order_flow.py)：`START → prepare → get_order → get_payment → get_refund → summarize → END`，但订单不存在、未支付、支付缺失或未成功时，会提前转入总结。节点调用 [业务 Tool](src/agent_learning/business/tools.py)，将三个 `success/data/error` 结果分别写入 State，后面的节点不覆盖前面的结果。Tool 只读取 [本地模拟数据](data/business_demo.json)，不连接数据库或模型，不会扣款或发起退款。

```bash
.venv/bin/python main_workflow.py
```

输入 `A1001` 只查订单；`A1002` 查询订单、全部支付和全部退款；`A1003` 查到支付成功但无退款记录；`A1004` 无支付记录；`A1005` 支付记录未成功；`A9999` 订单不存在。`  a1002  ` 会整理成 `A1002`。入口顶部的 `TENANT_ID` 默认是 `acme`，改为 `other` 后，同号订单、支付和退款都只返回该租户的数据。金额保留字符串表示，回答明确标注模拟数据和更新时间。

Debug 解释器选择项目 `.venv/bin/python`，打开 `main_workflow.py` 点击 Debug，在 `graph.invoke()`、三个查询节点、`choose_order_route()`、`choose_payment_route()` 和 `summarize_node()` 打断点，观察三个结果字段和 `executed_tools`。完整步骤见 [第 61 课说明](docs/11-order-workflow.md)。[single_node.py](src/agent_learning/workflows/single_node.py)、[state_flow.py](src/agent_learning/workflows/state_flow.py)、[conditional_route.py](src/agent_learning/workflows/conditional_route.py) 和上一课 [business_tool.py](src/agent_learning/workflows/business_tool.py) 保留对照；受控 Agent loop、RAG 和 MCP 留待后续。

## 配置在哪里

- [`.env.db`](.env.db)：数据库地址、账号和密码。目标是 `ragdb` 数据库、`public` schema。
- `.env`：DeepSeek Key，支持旧的 `DEEPSEEK_API_KEY`。如果另配 `LLM_API_KEY`，优先用它。
- [`.env.example`](.env.example)：模型、Chunk、Top-K 等参数的填写示例。
- [core/config.py](src/agent_learning/core/config.py)：`load_settings()` 中直接用 `load_dotenv()` 和 `os.getenv()` 读取每项配置，没有字段反射。

配置优先级为系统 / IDE 环境变量 > `.env.db` > `.env`。已有配置文件没有修改，数据库账号密码和模型 Key 不会打印。详见 [配置说明](docs/08-db-config.md)。

## 先看哪些代码

1. `main_ingest.py`：看文件路径和是否写库，然后进入 [IngestionPipeline.run()](src/agent_learning/rag/ingestion.py)。
2. `main_ask.py`：看问题和筛选条件，然后进入 [RAGPipeline.ask()](src/agent_learning/rag/answering.py)。
3. `main_workflow.py`：看初始 State，再进入 [多步订单节点](src/agent_learning/workflows/order_flow.py) 和 [三个业务 Tool](src/agent_learning/business/tools.py)，观察每一步如何保留结果、业务路由如何跳过查询并进入总结；前几课的文件保留对照。
4. [cli.py](src/agent_learning/cli.py)：只负责逐个创建 RAG 对象，不再解析命令。每个对象都有独立变量，便于断点查看。
5. 主流程调用到哪里，再看对应的加载、切分、检索或模型方法。

所有类和方法保留中文职责说明。已经移除 Protocol 接口、dataclass、自动字段转换、动态模型参数适配和自定义连接上下文。BM25 使用 old/ 已用过的 `rank_bm25.BM25Okapi`，CrossEncoder 使用旧环境的 sentence-transformers 3.x 写法。

## 两条流程

资料入库：加载文件 → JSON 字段转正文 → 父子块切分 → 生成向量 → 保存到现有 SQL 定义的表。

用户问答：问题改写 / 意图识别 → 元数据过滤 → 向量与 BM25 召回 → 合并去重与融合 → 候选 Top-K → CrossEncoder 精排 → 上下文截断 → Prompt → LLM → 来源检查或拒答。

表结构保留，因此原文、JSON、父子块、标签和版本检查继续存在。数据库操作集中在 repository.py，不在主流程中展开数据库实现细节。

## 数据库与样例

- [01_schema.sql](sql/01_schema.sql)：6 张表与普通、GIN、HNSW 索引。
- [02_seed_documents.sql](sql/02_seed_documents.sql)：28 条企业原文和标签。
- [03_validation_queries.sql](sql/03_validation_queries.sql)：用户手动检查数量、维度和关联的一组只读查询。
- [04_comments.sql](sql/04_comments.sql)：已建好新版表时单独补充表和字段中文备注，无需删表重建；新建表脚本已包含相同备注。
- [企业 JSON](data/enterprise_documents.json)：与初始化 SQL 对应的原始数据。

初始化 SQL 只保存原文，状态为 pending；真实向量由 `main_ingest.py` 开启写入后生成。旧 `public.kb_documents` 与新结构同名，按用户原定计划自行处理旧表后再建表；本项目不自动删除或迁移。SQL 的历史注释中 `ingest --write` 指的写入操作，现在对应 `WRITE_TO_DB=True`，SQL 文件本身未改动。

## 离线检查

```bash
make test
```

测试仅收集 tests/，不执行 old/ 的脚本、不读取真实 .env、不访问数据库或 LLM。依赖以 pyproject.toml 为准；复用现有 Python 3.11 环境，本次未安装或升级库。

## 资料与限制

[学习路线](docs/00-roadmap.md) · [旧代码盘点](docs/01-inventory.md) · [流程说明](docs/02-architecture.md) · [实验记录](docs/03-experiments.md) · [数据库设计](docs/05-database.md) · [运行与断点](docs/06-running.md) · [后续工作流与 MCP 设计](docs/09-workflow-mcp-design.md)。

BM25 用于小语料；父块保留但问答不自动展开；自动打标和 Agent 留待后续。CLI 改为直接脚本后，租户和权限仍是学习时手动模拟的身份条件。合法引用不等于所有事实都正确，需要固定问题验收。

**协作规则：未经用户同意不操作数据库、不删除目录，不能执行任何 Git/SVN 操作。** old/ 备份和原课程资料保留不动，完整要求见 [AGENTS.md](AGENTS.md)。
