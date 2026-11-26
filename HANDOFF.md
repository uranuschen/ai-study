# 项目交接

更新于 2026-11-26。FastAPI 已覆盖第 70 课核心内容，独立 MCP Server 已完成第 71–75 课。本轮最后的开发任务是第 75 课的参数校验、错误分层、超时和结果大小限制。之后已说明如何用 Postman 触发 `guard_request()`。第 76–80 课待开发。

## 项目背景

这是一个 Python 练习项目。业务场景是查询订单、支付和退款，结合制度资料回答问题，并用人工审批演示模拟取消。Python 3.11+、FastAPI、Pydantic 和 Uvicorn 提供 HTTP 接口，LangGraph 管理流程和会话，现有 RAG 使用 PostgreSQL/pgvector 和 OpenAI 兼容模型。当前订单数据来自本地 JSON。项目结构、完整接口与启动说明见 [README](README.md)，后续设计见 [工作流与 MCP 设计](docs/09-workflow-mcp-design.md)。

## 已完成及需要保留

| 位置 | 关键实现和修改原因 |
|---|---|
| [main_api.py](main_api.py)、[bootstrap.py](src/agent_learning/bootstrap.py) | `create_app(services=None)` 注册四组路由，`build_services()` 显式构造 `RagService`、`OrderService`、`AgentService`、`LessonService`。独立保留应用装配和替身注入，便于离线调试。 |
| [agent_service.py](src/agent_learning/services/agent_service.py)、[diagnosis_agent.py](src/agent_learning/workflows/diagnosis_agent.py) | `AgentService.create_session()` 绑定图和内存存档配置；`ask()` 启动新问题，`resume()` 用原配置 `invoke(None)` 继续待执行节点，`approve()` 校验当前审批编号后用 `Command(resume=value)` 提交决定。`diagnosis_agent.build_graph()` 保留执行次数上限及审批分支。 |
| [lessons.py](src/agent_learning/api/lessons.py)、[pause_demo.py](src/agent_learning/workflows/pause_demo.py)、[approval_demo.py](src/agent_learning/workflows/approval_demo.py) | 固定图便于单步看清两种暂停。普通演示在 `answer` 节点前暂停，审批演示在 `approval_node()` 调用 `interrupt()`。两者复用会话，批准仅模拟取消。 |
| [main_mcp_basics.py](main_mcp_basics.py)、[main_mcp.py](main_mcp.py)、[pyproject.toml](pyproject.toml) | 第 71 课的 `hello()`、`main()` 对照直接函数、模型工具调用和 MCP；第 72 课用 SDK 的 `MCPServer` 创建独立 Streamable HTTP 入口。固定 `mcp==2.3.0`、主协议 `2026-07-28`，兼容 `2025-11-25`。 |
| [mcp_server/server.py](mcp_server/server.py)、[business/tools.py](src/agent_learning/business/tools.py) | 已注册 `hello`、`greet`、`get_order`、`get_payment`、`get_refund`。三个业务包装复用原 JSON 函数，租户固定为 `acme`，对外只收 `order_id`。保留中文状态原值（如“已支付”）、金额字符串、来源和 `updated_at`。`records_to_mcp()` 保留原顺序，空列表表示成功，超过 10 条才截断并附 `notice`。 |
| [mcp_server/server.py](mcp_server/server.py)、[mcp_server/controls.py](mcp_server/controls.py) | `mcp.middleware.append(guard_request)` 让 SDK 在工具调用前校验，在调用后检查结果。新增 `valid_arguments()`、`make_result()`、`error_result()`、`read_query()`、`classify_response()`。统一拒绝非法参数、隐藏内部错误并限制等待时间及返回大小；响应分类函数可供后续 Client 复用。 |

保留 [JSON 样例](data/business_demo.json)、[IDE 启动配置](.vscode/launch.json) 和 [第 71–75 课入口及文档索引](docs/00-roadmap.md)。以上是已核实的实现和接手时应保留的代码。**Git 未提交状态待核实**。按 [AGENTS.md](AGENTS.md) 未执行 Git/SVN，未找到可用的现成 diff，无法确认暂存、未暂存或未跟踪文件，或相对提交的改动范围。有用户提供的 diff 时可再对照本表。

## 第 75 课的接口约定

- 调用 `POST /mcp` 的 `tools/call` 时，SDK 进入 `guard_request()`；校验通过后由 `await call_next(ctx)` 执行对应工具。当前工具字段仅允许非空白字符串，最长 256 字符，拒绝缺少必填项、错误类型和额外字段。工具名与参数定义从 SDK 注册结果取得。
- HTTP 连接或认证失败由客户端分类。未知工具、`arguments=[]` 等结构错误返回 JSON-RPC `error`，此处为 HTTP 400 / `-32602`。已注册工具的字段错误、业务失败返回 HTTP 200 / `result.isError=true`，机器可读错误码在 `structuredContent.error_code`。例如 `INVALID_ARGUMENT`、`ORDER_UNAVAILABLE`、`FORBIDDEN`。使用固定错误文字，权限拒绝和本课其他错误均不自动重试。
- 订单缺失和不可读统一显示“订单不存在或不可读取。”；显式抛出的 `PermissionError` 由 `read_query()` 分类为 `FORBIDDEN`。当前 JSON 业务函数内部捕获的 `OSError` 仍走通用失败路径。固定租户只提供查询边界，HTTP 登录和 OAuth 尚未接入。
- 单次工具等待默认 5 秒，结果限制 16 KiB，按当前 HTTP 编码计算 `result`（含文字和结构化数据），外层 JSON-RPC 包装另有开销。新增 RAG 工具时明确评估 256 字符输入和 16 KiB 结果限制。错误映射与可复制请求见 [第 75 课](docs/25-mcp-validation-errors.md)。

## 报错、排查和避坑

本轮离线复核未发现阻塞性代码 Bug。以下是已核实的返回或历史问题：

| 现象 | 原因和处理进度 |
|---|---|
| 直接调试包内入口报 `ModuleNotFoundError: No module named 'agent_learning'`（历史） | 直接运行包内脚本时导入路径不完整。根目录的 FastAPI、MCP 入口已经设置 `src` 导入路径，本轮导入及离线调用通过。 |
| Postman `-32700 Parse error`（历史）、`-32020`（已复测） | 前者表示请求体无法解析为 JSON，历史请求原文未确认；后者表示主协议请求头与正文不匹配。Body 用 raw JSON，`Mcp-Method` 对齐 `method`；调用工具时 `Mcp-Name` 对齐 `params.name`。主协议每次带 `_meta`，旧协议先 `initialize`。完整示例见 [第 75 课](docs/25-mcp-validation-errors.md)。 |
| 恢复报“没有可恢复的执行。”，或审批报“当前没有待审批操作。”（已复测） | `snapshot.next` 已空，或当前会话没有待审批请求。完成后重复提交返回 409，属于预期业务行为。先用固定演示进入暂停，再用同一个 `session_id` 和本次返回的审批编号操作。会话仅在进程内，重启即丢失。 |

之前验证的三个实现陷阱：

- 直接依赖 SDK 默认校验会忽略额外字段，并把未知工具归成工具失败。现由 `guard_request()` 显式处理；升级 SDK 后应重跑这些边界用例。
- 只给同步工具套 `fail_after()` 无法按时结束等待。三个业务包装现采用异步等待和 `abandon_on_cancel=True`。到期后服务可返回超时结果，底层只读线程仍可能跑完。真实数据库或 HTTP 调用后续还要配置驱动或客户端超时。
- 用 `ensure_ascii=False` 的字节数衡量当前 HTTP 结果会低估转义后的中文大小。已改成和实际 HTTP 编码一致的紧凑 ASCII 转义计算，并复测超限返回 `RESULT_TOO_LARGE`。客户端判断 `isError` 须检查布尔类型，避免把 `0` 等值误判为成功。

## 当前运行和验证状态

- **已复测**：55 个入口及应用 Python 文件在内存中编译通过，当前虚拟环境为 `mcp==2.3.0`，`pip check` 通过，第 71 课脚本可运行。FastAPI TestClient 使用替身依赖验证 `/health`、20 条 OpenAPI 路径、暂停/恢复、批准/拒绝及重复请求 409。
- **已复测**：MCP 经 TestClient 验证主协议发现和五个工具、旧协议握手及订单调用、样例租户隔离、空列表、截断、参数拒绝、协议错误。权限异常、超时和超大中文结果用替身验证，401/403 用合成响应验证。
- **待验证**：本轮未监听端口，也未用桌面 Postman、真实数据库、实际认证、模型或向量写入联调。实际启动从根目录运行 `.venv/bin/python -B main_api.py`（8000，Swagger 为 `/docs`）或 `.venv/bin/python -B main_mcp.py`（8001，`/mcp`）。

## 下一步与验收

| 优先级 | 待完成 | 验收标准 |
|---|---|---|
| 1 · 第 76 课 | 业务 PostgreSQL 只读实现。先出 SQL 文本供用户审阅和手动执行；连接与权限另行确认。保留拟定的 `BUSINESS_DATA_SOURCE=json\|postgres`，查询参数绑定并始终带租户条件。 | JSON 路径继续可用。两种数据源的字段、来源标记、空列表及租户隔离符合同一接口约定；真实查询只在获授权后验收。现有 `codex_ro` 授权不覆盖业务表。 |
| 2 · 第 77 课 | 把现有 [rag_agent.ask_knowledge_base()](src/agent_learning/workflows/rag_agent.py) 或其复用的 `RAGPipeline.ask()` 包装成 MCP Tool。使用服务端过滤条件，限制引用条数及字符数。 | 返回答案、引用和状态；无足够资料时清楚表达无法回答。先用离线替身覆盖有依据、无依据和输出上限。 |
| 3 · 第 78 课 | 实现正式 MCP Client，覆盖连接、发现、调用、释放、超时，并对照 stdio。 | 能列出并调用服务端工具；连接失败、协议错误、工具错误可区分，权限拒绝无自动重试。 |
| 4 · 第 79 课 | Agent 通过 `TOOL_SOURCE=local\|mcp` 显式选择来源。给 MCP 工具加前缀，结果按外部数据处理，取消审批留在本地。 | 相同业务问题的结果一致；MCP 不可用时明确报错，避免隐式切回本地；审批守卫仍有效。 |
| 5 · 第 80 课 | 收口阶段演示与运行说明。 | 可按说明启动，复现三层错误、权限拒绝、超时及大小限制；说明直接函数、FastAPI、MCP 的适用场景。 |

## 本轮交接约束

此次交付仅写根目录 `HANDOFF.md`。后续按课推进，每课保留最小可运行示例，说明入口、断点和可复制的请求。第 76 课的 SQL 文本交付与实际数据库执行分开。其余项目规则直接查阅 [AGENTS.md](AGENTS.md)。
