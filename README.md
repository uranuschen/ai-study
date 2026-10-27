# AI 学习项目：企业 RAG

当前 RAG 阶段保留第 54 课的问答链路；LangGraph Console 已进入第 69 / 70 课「Tracing 与订单问题诊断综合」。复用业务 Tool、RAG、会话 Memory、Checkpoint、人工确认与有限重试，把次数、Token 和估算费用限制贯通；只增加必要的追踪与汇总，不接外部日志平台。订单数据仍为只读 JSON，取消仅模拟；表结构不变。

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

## LangGraph Console：第 69 / 70 课 Tracing 与订单诊断

运行 [main_workflow.py](main_workflow.py)。入口调用 [diagnosis_agent.py](src/agent_learning/workflows/diagnosis_agent.py)，追踪辅助在 [tracing.py](src/agent_learning/workflows/tracing.py)。新加 / 调整逻辑用 `# (69)` 标记 Tracing、`# (70)` 标记综合流程；前面课程的独立入口保留。

```bash
.venv/bin/python main_workflow.py
```

可以先问「查询 A1002 的退款记录」，再问「它按规则通常多久到账？」；模型根据证据选择业务 Tool 或 RAG，不要求每次都调用全部工具。订单事实保留 JSON 的 `updated_at`，RAG 保留引用与资料不足状态，二者不能混成实时事实。

输入「请取消订单 A1001」练习审批：`interrupt(request)` 暂停，输入 `y` / `approve` 确认或 `n` / `reject` 拒绝，再由 `Command(resume=...)` 恢复同一任务。审批绑定订单、租户、工具调用 ID 与本轮 `run_id`，旧批准不能跨轮重放；确认才进入模拟执行节点，不修改 [业务 JSON](data/business_demo.json) 或数据库。`A1002` 已支付，不支持这个简化取消规则。同会话成功模拟记录保存在 State，不等于生产写操作 exactly-once 保证。

每个新问题生成一个 `run_id`，在同一 `thread_id` 下保留历史但重新初始化本轮预算；人工审批恢复沿用原 `run_id` 和计数，不能重置预算。临时系统错误有限重试，业务失败、永久错误、拒绝或预算不足受控结束，不靠 LLM 再生成失败说明。

Tracing 记录会话 / 本轮编号、节点 / Tool / LLM、状态、尝试与耗时，以及输入 / 输出 Token、费用估算和安全失败原因。只在 State 与 Console 展示，不写日志文件，不记录完整问题、资料、结果、密钥或异常正文。外层 Agent 与 RAG 内层的实际 LLM 尝试都计入总次数和预算；父节点包含的耗时不与子调用相加，内层模型费用也不重复记到 Tool 上。

默认关闭时间限制，Debug 停留只增加耗时，不因断点触发超时。次数、Token 和费用预算仍生效；接口缺失 usage 时，Tracing 标记未知，预算按保守预留计入。演示单价不是 DeepSeek 当前报价，估算费用不是账号账单硬上限。正常提问 `/new` 切换会话，`q` 退出；审批未完成时不能提交新问题。内存存档不跨进程保留。

具体技术点见 [第 69 课 Tracing](docs/18-tracing.md)，运行、断点、验收场景和 5 分钟演示见 [第 70 课订单诊断](docs/19-order-diagnosis.md)。本次只做离线验证，没有查询真实知识库、调用真实模型或下载模型。用户主动运行入口才会请求已配置的服务；RAG 被选择时才查询知识库，有有效证据时还会请求内部模型。

第 67 课保留在 [main_workflow_approval.py](main_workflow_approval.py)，详见 [人工确认](docs/17-human-in-the-loop.md)；第 66、65、64、63 课分别保留 [Memory](main_workflow_memory.py)、[Checkpoint](main_workflow_checkpoint.py)、[RAG Tool](main_workflow_rag.py)、[重试与预算](main_workflow_recovery.py) 独立入口。

## 配置在哪里

- [`.env.db`](.env.db)：数据库地址、账号和密码。目标是 `ragdb` 数据库、`public` schema。
- `.env`：DeepSeek Key，支持旧的 `DEEPSEEK_API_KEY`。如果另配 `LLM_API_KEY`，优先用它。
- [`.env.public.example`](.env.public.example)：可公开的空凭证模板；数据库连接串、模型 Key 均为空。真实值只填写到本地 `.env.db` / `.env`。
- [core/config.py](src/agent_learning/core/config.py)：`load_settings()` 中直接用 `load_dotenv()` 和 `os.getenv()` 读取每项配置，没有字段反射。

配置优先级为系统 / IDE 环境变量 > `.env.db` > `.env`。真实配置文件没有修改。详细配置说明 `docs/08-db-config.md` 含本地连接信息，仅在本地保留，不作为公开仓库文档上传。

## 上传前的敏感信息保护

`.gitignore` 排除了 `.env`、`.env.db`、其他环境配置及其备份、PostgreSQL 密码文件、常见私钥、虚拟环境和本机 IDE 配置。原 `.env.example` 也含直接写入的连接信息，不能作为公开模板；请使用 `.env.public.example`，且保持其中凭证为空。

`old/` 备份、`docs/08-db-config.md`，以及 `python_basic/rag/` 中的 `db.py`、`document_ingest_pipeline.py`、`vector_search_test.py`、`test_pgvector.py`、`prefilter_test.py` 含旧的数据库配置，也已加入忽略规则。原文件仍留在本地，没有删除或改写。

忽略规则只影响未被 Git 跟踪的文件，不能移除已跟踪内容或历史记录。上传前需自行确认暂存内容和历史中没有凭证；如果密钥或密码曾经公开，应立即撤销或更换。不要把终端输出、截图、数据库导出或其他秘密副本放入待上传文件。本次没有执行任何 Git 操作，也没有核查 Git 跟踪状态或历史。

## 先看哪些代码

1. `main_ingest.py`：看文件路径和是否写库，然后进入 [IngestionPipeline.run()](src/agent_learning/rag/ingestion.py)。
2. `main_ask.py`：看问题和筛选条件，然后进入 [RAGPipeline.ask()](src/agent_learning/rag/answering.py)。
3. `main_workflow.py`：看可信租户、预算、thread_id 和审批恢复，再进入 [订单诊断图](src/agent_learning/workflows/diagnosis_agent.py)；[Tracing](src/agent_learning/workflows/tracing.py) 记录关键边界，不改变订单业务结果。旧课入口用于逐项对照。
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

BM25 用于小语料；父块保留但问答不自动展开；自动打标留待后续。CLI 改为直接脚本后，租户和权限仍是学习时手动模拟的身份条件。保留合法引用不等于外层 Agent 每句话都经过事实校验，需要固定问题验收。

**协作规则：未经用户同意不操作数据库、不删除目录，不能执行任何 Git/SVN 操作。** old/ 备份和原课程资料保留不动，完整要求见 [AGENTS.md](AGENTS.md)。
