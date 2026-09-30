# 工作流、业务数据与 MCP 后续接入设计

> 状态：已实现 LangGraph 单节点、双节点 State 传值、条件路由、第 60 课 JSON 订单 Tool、第 61 课多步业务工作流，以及第 62 课模型选工具、执行回传与最大模型调用次数控制的 Agent loop；PostgreSQL 业务 Tool、RAG Tool 和 MCP 尚未接入新工作流。本文件不是执行数据库建表、初始化或连接数据库的授权。

## 已确认的边界

- 现有 `main_ingest.py`、`main_ask.py` 和 `public` 下六张 `kb_*` 表继续服务 RAG，不因学习工作流或 MCP 而改动。
- 后续优先使用现有 PostgreSQL `ragdb`。订单、支付、退款是业务数据，拟放在独立的 `biz` schema；知识库仍保留在 `public`。不把业务表强行切成向量块。
- 工作流与 MCP 共用同一批只读业务 Tool；租户和可读权限来自可信入口，不能让模型根据问题自行提高权限。所有 SQL 使用固定查询与参数绑定，不开放任意 SQL Tool。
- 现有知识库中的订单和退款资料是带 `snapshot_at` 的快照。回答当前状态时，以业务 Tool 返回的最新可用状态及其更新时间为准；RAG 用于制度、流程及注明时间的历史资料，避免旧快照覆盖较新的业务状态。

当前 `RAGPipeline.ask()` 是固定的 RAG 问答链路：检索、精排、组装证据、调用 LLM、校验回答；它不会根据工具结果自主选择下一个 Tool 并循环。历史 `python_basic/toolcalling/` 的消息、工具声明、分发与结果回传方式，已在第 62 课迁移为 `workflows/agent_loop.py` 的 LangGraph 循环，入口为 `main_workflow.py`。模型选择三个只读 JSON Tool，可信租户由程序注入；最多调用模型 `MAX_STEPS` 次，达到上限保留已有结果并结束。当前消息只保留在单次执行内，跨次 Memory 与 Checkpoint 留待后续。

RAG、Agent 工作流和 MCP 可以用于自然语言助手，也可以由 Issue、CI 日志、运维告警、库存预警等结构化事件触发；它们不要求用户先提出问题。RAG 提供相关资料作为证据，Agent 或工作流根据任务和 Tool 结果决定后续步骤，MCP 负责让外部 AI 客户端发现并调用 Tool。不是每个场景都需要同时使用三者；判断依据是是否存在非结构化资料、需要随结果变化的步骤，以及跨客户端复用 Tool 的需求。

研发修复、运维诊断和供应链采购建议都可以按这种方式设计，但不改变现有业务系统的权威地位：测试结果、库存和价格、审批规则由对应系统校验；模型负责分析、提出建议或生成待审阅内容。本项目当前只以订单诊断作为后续学习样例，这些场景不代表已授权执行 Git、数据库或外部写入操作。

## 学习阶段和数据准备

1. **先用 JSON 学工作流。** 独立的 `data/business_demo.json` 已包含订单、支付和退款样例。JSON 是模拟业务系统的数据，不通过 `main_ingest.py` 向量入库。当前 `get_order`、`get_payment`、`get_refund` 都只读查询该文件，返回 `success/data/error`，成功记录带 `source=json` 与 `updated_at`；金额使用字符串保留精确表示。支付、退款返回全部匹配记录列表；成功的空列表表示已查询但无记录，不是执行失败。
2. **再接 PostgreSQL。** 在课程进入真实数据库 Tool 时，分别提供待审阅的建表 SQL 和演示数据 `INSERT` SQL，例如 `sql/05_business_schema.sql` 与 `sql/06_business_seed.sql`。先由用户手动建表，再手动录入演示数据，最后用只读查询核对；程序启动时不自动建表或初始化。
3. **真实数据要另有更新来源。** `INSERT` 演示数据只用于学习，不会自动变成实时订单系统。后续由业务系统、只读 API 或经确认的数据同步方式提供最新状态，并明确返回更新时间。

JSON 演示文件和一次性 `INSERT` 数据都表示录入时的样例状态；程序在查询时读取 PostgreSQL，也只能看到库中最后一次更新的状态。是否“实时”由上游是否持续更新、更新延迟和 `updated_at` 决定，与 JSON/PostgreSQL 或是否经过 MCP 无直接关系。没有持续更新来源时，回答应称为“截至某时刻的状态”。

这三张业务表是学习数据库 Tool 的本地演示数据源，不是企业落地时必须复制的一套订单系统。若企业已有 Spring Boot 订单、支付、退款服务，后续应优先通过它们授权的只读接口获取业务事实；商品搜索、库存、价格和金额计算仍由现有搜索与业务服务负责，不把结构化交易数据切块后交给 RAG 推断。

拟新增的最小表如下；真正写 SQL 时再核对字段和约束，不改 `sql/01_schema.sql`：

| 表 | 主要字段 | 关键关系 |
|---|---|---|
| `biz.orders` | `tenant_id`、`order_id`、状态、金额、币种、`updated_at` | 同租户内订单号唯一 |
| `biz.payments` | `tenant_id`、`payment_id`、`order_id`、状态、金额、支付方式、`updated_at` | 一个订单可有多条支付记录 |
| `biz.refunds` | `tenant_id`、`refund_id`、`order_id`、可选 `payment_id`、状态、金额、原因、`updated_at` | 一个订单可有多条退款记录 |

金额使用精确数值类型，时间保留时区；订单和支付/退款之间的关联要同时约束 `tenant_id`，避免跨租户串数据。查询支付或退款时返回列表，不沿用旧练习代码只取第一条的假设。三表按 `(tenant_id, order_id)` 建常用查询索引。

## 稳定的 Tool 边界与数据源切换

LangGraph 节点、直接调用的 Tool 和 MCP Server 不分别编写 SQL，而是调用同一批业务函数，例如 `get_order`、`get_payment`、`get_refund`。这些函数的参数、返回字段和错误格式在 JSON 与 PostgreSQL 两种实现中保持一致；支付和退款结果允许多条，并带数据来源与更新时间。

```text
LangGraph 节点 / MCP Tool
          ↓
固定的业务 Tool：get_order / get_payment / get_refund
          ↓
由 BUSINESS_DATA_SOURCE 选择读取实现
          ├── json      → 本地模拟 JSON
          └── postgres  → biz.* 表的只读查询

RAG Tool：ask_knowledge_base → 现有 RAGPipeline.ask() → public.kb_* 六表
```

当前第 60、61 课先用普通业务函数读取 JSON，入口直接配置 `DATA_FILE`，便于学习参数、返回值和 State 的关系；工作流按结果查询订单、支付、退款，独立保存各步结果并总结。后续用普通类和明确的创建函数实现两种读取方式，不引入 Protocol、反射配置或复杂插件机制。拟在新入口使用 `BUSINESS_DATA_SOURCE=json|postgres` 选择；JSON 路径单独配置，业务数据库连接地址和凭证单独保存在数据库配置文件，不复制到源码、文档或日志。现有 RAG 的 `DATABASE_URL` 不随业务数据源开关改变。

**“改一个字段即可切换”有前提：两种读取实现、连接信息和统一返回格式都已经准备好。** 从当前 `ragdb` 换到结构相同的另一套 PostgreSQL，还需要数据和连接地址到位；若将来换 MySQL，必须另写并测试 MySQL 读取实现及字段映射，单靠选择字段不会自动转换 SQL。现有 RAG 使用 pgvector，不承诺随业务库开关一起迁移到 MySQL。

## 新目录、入口与 MCP 调用方向

以下是逐课新增的目标位置；Console、`workflows/`、JSON 订单样例和 `business/tools.py` 已创建，PostgreSQL 与 MCP 仍是后续计划，旧 RAG 入口不改动：

```text
main_workflow.py                 # 第 62 课：模型选工具、分发回传与受控循环
main_mcp_server.py               # 本地 MCP Server 入口
main_mcp_client.py               # 独立 MCP Client 演示入口
src/agent_learning/workflows/   # 已有固定多步工作流与有模型调用上限的 Agent 循环
src/agent_learning/business/    # 已实现三个 JSON 查询 Tool；PostgreSQL 留待后续
src/agent_learning/mcp_app/     # MCP Server/Client 适配代码
data/business_demo.json         # 已有订单、支付、退款模拟数据
sql/05_business_schema.sql      # 后续建表文本，用户手动执行
sql/06_business_seed.sql        # 后续演示 INSERT 文本，用户手动执行
```

第一阶段让工作流直接调用业务 Tool 和现有 RAG Tool。学习循环时，工作流在 State 中保存问题、已取得的订单/支付/退款结果、错误和调用次数；每一步决定继续调用哪个 Tool，或在证据足够时结束，并设置最大步骤数避免死循环。订单诊断可以是“查订单 → 按结果查支付或退款 → 必要时查制度 → 总结”，不要求每个问题都调用全部 Tool。

问答入口可以接收自然语言：先识别意图、提取业务编号，缺少必要编号时要求补充。事件入口则可以直接接收订单号、告警编号及事件类型等结构化字段。两种入口最终都调用确定性的业务 Tool。像“查 A1002 退款状态”这类明确问题，单次 Tool 查询即可，不必强行循环。只有下一步取决于上一步结果、可能需要多轮查询或澄清时才使用 Agent 循环。LLM 可以组织说明，但订单状态、金额、权限和审批结论不能由它猜测或代替业务规则决定。

学习 MCP 后，MCP Server 暴露这些 Tool，**工作流中的 MCP Client 调用 Server**；Tool 内的业务逻辑和 JSON/PostgreSQL 切换保持不变。无需先把整个 LangGraph 工作流变成 MCP Tool。只有将来明确需要其他外部 MCP Client 一次调用完整诊断流程时，才额外考虑把工作流作为高层 `diagnose_order` Tool 暴露；此时应避免工作流再通过同一个入口调用自己。

MCP 是供 AI 客户端发现和调用能力的接口层，不替代 Spring Boot 等业务服务；只有单一内部调用方时，直接函数或现有 HTTP API 也可以。项目学习 MCP 时可以做适配演示，但不把“所有业务必须经过 MCP”当成落地目标。

`RAGPipeline.ask()` 当前包含检索和最终 LLM 回答，因此初期包装名应是 `ask_knowledge_base`。如果后续课程需要“只返回证据、不生成答案”的 `search_docs`，再单独抽出检索接口，不把两者混称。

## 验证与权限

- 先用离线数据验证 JSON 读取、同租户隔离、多笔支付/退款、缺失记录、Tool 返回格式及工作流失败分支。
- PostgreSQL 实现与 JSON 实现应跑同一组 Tool 行为用例；真实数据库集成验证只在用户明确授权后进行。
- 将来业务 Tool 使用仅能读取 `biz` 所需表的账户。现有 `codex_ro` 只授权六张知识库表，不默认扩大到新业务表。
- Memory、Checkpoint、MCP 不改变业务 Tool 的读写权限。若后续课程加入写操作，另设计人工确认和权限边界。

项目协作限制仍以根目录 `AGENTS.md` 为准；本文件只记录未来架构与实施顺序。
