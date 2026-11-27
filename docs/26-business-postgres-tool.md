# 第 76 课：可切换数据源的只读数据库 Tool

本课扩展 `get_order`、`get_payment`、`get_refund`，通过配置开关 `BUSINESS_DATA_SOURCE=json|postgres` 在本地 JSON 与只读 PostgreSQL 业务表之间二选一切换。JSON 模式继续保持默认可用；FastAPI（`main_api.py`）、LangGraph 工作流与 MCP Server（`main_mcp.py`）共用同一套业务函数与配置。

```text
FastAPI / LangGraph 工作流 / MCP Server
                ↓
  business/tools.py：get_order / get_payment / get_refund
                ↓
  create_business_store() 按 BUSINESS_DATA_SOURCE 二选一
        ├── json      → JsonBusinessStore     → data/business_demo.json
        └── postgres  → PostgresBusinessStore → ragdb 的 biz.orders / biz.payments / biz.refunds
```

程序启动、配置加载和查询都不会自动建表、初始化或写入数据。现有 `public.kb_*` 六张知识库表与 RAG 的 `DATABASE_URL` 保持原样不变。

## 配置项与切换方式

配置由 `src/agent_learning/core/config.py` 的 `load_settings()` 统一读取，优先级保持“系统 / IDE 环境变量 > `.env.db` > `.env`”：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `BUSINESS_DATA_SOURCE` | `json` | 仅允许 `json` 或 `postgres`；非法值在 FastAPI 与 MCP Server 启动阶段均立即报错，不静默回退 |
| `BUSINESS_DATABASE_URL` | 空字符串 | 独立的业务只读连接串，建议放在 `.env.db`；仅使用业务只读账号，不复用 RAG 的 `DATABASE_URL` |
| `BUSINESS_DATA_FILE` | 空字符串 | 可选自定义本地 JSON 路径；为空时默认读取 `data/business_demo.json` |

`.env.db` 中增加业务只读连接配置示例（请替换为实际密码，不要将真实密码提交或写入源码/文档）：

```dotenv
# 原有 RAG 知识库连接串保持不变
DATABASE_URL=postgresql://...

# 第 76 课新增：业务只读账号连接串与数据源开关
BUSINESS_DATABASE_URL=postgresql://biz_ro:<你的密码>@localhost:5432/ragdb
BUSINESS_DATA_SOURCE=json
```

切换数据源时，把 `BUSINESS_DATA_SOURCE` 改为 `postgres` 或 `json` 并重启服务即可；也可以在启动命令中临时覆盖：

```bash
# 使用 JSON 模式（默认）
BUSINESS_DATA_SOURCE=json .venv/bin/python -B main_api.py
BUSINESS_DATA_SOURCE=json .venv/bin/python -B main_mcp.py

# 使用只读 PostgreSQL 模式（前提：已手动建表、导入数据并配置 BUSINESS_DATABASE_URL）
BUSINESS_DATA_SOURCE=postgres .venv/bin/python -B main_api.py
BUSINESS_DATA_SOURCE=postgres .venv/bin/python -B main_mcp.py
```

若配置为 `BUSINESS_DATA_SOURCE=postgres` 但未配置 `BUSINESS_DATABASE_URL` 或数据库不可用，查询会明确返回失败，不会悄悄回退到 JSON。

## 待审阅 SQL 与手动执行顺序

所有 SQL 文件仅提供文本供审阅，由用户在 `ragdb` 中手动执行，不会被程序自动运行：

| 顺序 | 文件或手动语句 | 作用 |
|---|---|---|
| 1 | `sql/05_business_schema.sql` | 新建独立 `biz` schema、`biz.orders`、`biz.payments`、`biz.refunds`、外键、索引与中文备注；不改动 `public.kb_*` |
| 2 | `sql/06_business_seed.sql` | 导入与 `data/business_demo.json` 一一对应的 6 条订单、5 条支付、3 条退款（重复执行使用 `ON CONFLICT DO NOTHING`） |
| 3 | 管理员手动建账号（前置步骤） | 首次部署先在 `ragdb` 执行 `CREATE ROLE biz_ro LOGIN PASSWORD '<替换为你的强密码>';`（不在脚本中自动执行占位口令） |
| 4 | `sql/07_business_readonly_role.sql` | 检查 `biz_ro` 已存在，并仅授予 `biz` 三张表最小 `SELECT` 权限，不涉及 `public.kb_*` 与写权限 |

现有 `codex_ro` 仍仅覆盖 `public.kb_*` 六张知识库表，不扩大到业务表。

## 两种数据源的行为一致性约定

`JsonBusinessStore`（`src/agent_learning/business/tools.py`）与 `PostgresBusinessStore`（`src/agent_learning/business/postgres_store.py`）对外遵循同一份参数与返回结构：

1. **函数签名与外层结构一致**：参数仍为 `(order_id, tenant_id, ...)`，外层始终返回 `{"success": bool, "data": ..., "error": ...}`。
2. **输入归一化一致**：`order_id` 去掉两端空格并转大写；`tenant_id` 只去两端空格、保留大小写。
3. **字段格式一致**：
   - `amount`：两种数据源统一通过 `format_amount()` 校验并转换为两位小数字符串（如 `"299"` → `"299.00"`），不转为 `float`。
   - `updated_at`：两种数据源统一通过 `format_updated_at()` 校验带时区并转换为 `+08:00` 秒级 ISO 字符串（如 UTC 时间也会统一转为 `+08:00`）。
   - `refunds.payment_id`：允许为空；有值时为字符串，无值时两种模式统一为 `null`（Python `None`）。
   - `source`：JSON 模式返回 `"json"`，PostgreSQL 模式返回 `"postgres"`，用于明确区分数据来源。
4. **列表顺序与空列表语义一致**：
   - 两种数据源统一按实际更新时间与记录编号升序排列（`updated_at ASC, payment_id ASC` / `updated_at ASC, refund_id ASC`），即使自定义 JSON 为倒序或乱序，结果顺序与 MCP 截取的前 10 条也完全一致。
   - 支付与退款查无记录时返回 `{"success": true, "data": [], "error": null}`，属于正常查询成功；MCP 层仍限制最多返回 10 条并保留 `truncated` / `notice`。
5. **错误与权限分类一致**：
   - 订单不存在或属于其他租户：统一返回 `订单不存在或当前租户不可读取。`（MCP 映射为 `ORDER_UNAVAILABLE`）。
   - 数据库权限不足（SQLSTATE `42501`）：返回固定权限提示，MCP 映射为 `FORBIDDEN`（不自动重试）。
   - 数据库语句超时（SQLSTATE `57014`，事务内设置 `statement_timeout=4000ms`）：返回固定超时提示，MCP 映射为 `TOOL_TIMEOUT`（不自动重试）。
   - 连接失败或未配置 `BUSINESS_DATABASE_URL`：返回固定安全提示，不泄露 SQL、表名或账号；MCP 映射为 `BUSINESS_ERROR`，不会误报成 `ORDER_UNAVAILABLE`。

## 只读查询与安全保护

`PostgresBusinessStore` 的每次查询都满足四项约束：

1. **固定 SQL**：仅使用模块中声明的三条只读 `SELECT` 常量（`ORDER_SQL`、`PAYMENT_SQL`、`REFUND_SQL`），不拼接用户输入。
2. **参数绑定与租户过滤**：所有查询固定包含 `WHERE tenant_id = %s AND order_id = %s`，租户仅来自服务端可信入口。
3. **双重只读保护**：建连后调用 `connection.set_session(readonly=True)`，并在事务首句执行 `SET TRANSACTION READ ONLY`。
4. **双超时与显式关闭**：建连使用 `connect_timeout=3`，事务内执行 `SELECT set_config('statement_timeout', '4000ms', true)`，退出 `finally` 始终调用 `connection.close()`。

## 调试断点与双模式对照检查项

建议调试断点位置：
- 配置切换：`src/agent_learning/business/tools.py` 中的 `create_business_store()`、`resolve_business_store()`
- PostgreSQL 只读查询：`src/agent_learning/business/postgres_store.py` 中的 `open_connection()`、`run_readonly_query()`、`map_database_error()`
- MCP 错误码映射：`mcp_server/server.py` 中的 `map_business_error_code()`

用户手动执行 SQL、授权并配置好 `BUSINESS_DATABASE_URL` 后，可在 `json` 与 `postgres` 两种模式下分别调用以下接口对照结果（除 `source` 分别为 `"json"` 与 `"postgres"` 外，业务字段与错误语义应完全一致）：

| 场景 | FastAPI 接口 | MCP 工具与参数 | 预期结果 |
|---|---|---|---|
| 多笔支付与退款 | `GET /api/orders/A1002`、`/payments`、`/refunds` | `get_order` / `get_payment` / `get_refund` (`{"order_id":"A1002"}`) | 订单金额 `"299.00"`；2 条支付（`P10020`、`P10021`）；2 条退款（`R10021`、`R10022`） |
| 租户隔离 | 服务端固定 `acme` 查询 `A1002` | 同上 | 仅返回 `acme` 记录，不出现 `other` 的 `79.00`、`POTHER21`、`ROTHER21` |
| 成功空列表 | `GET /api/orders/A1001/payments`、`/refunds` | `get_payment` / `get_refund` (`{"order_id":"A1001"}`) | `success=true`、`data=[]`、MCP `isError=false` |
| 订单不存在 | `GET /api/orders/A9999` | `get_order` (`{"order_id":"A9999"}`) | `success=false`，MCP `error_code=ORDER_UNAVAILABLE` |
| 固定订单工作流 | `POST /api/workflows/order-check` (`{"order_id":"A1002"}`) | — | 返回一致的订单/支付/退款明细，来源文案随 `source` 切换 |

本次离线阶段已使用内存 PostgreSQL 替身、FastAPI TestClient 与 MCP TestClient 核对上述全部路径、可选 `payment_id=None`、只读事务顺序、权限拒绝（`42501` → `FORBIDDEN`）及超时（`57014` → `TOOL_TIMEOUT`），未连接真实数据库，也未新增测试文件。
