# AI 学习项目：FastAPI

截至第 70 课已实现的核心内容统一通过 HTTP 调用：资料预览与入库、RAG 问答、订单查询、固定工作流、基础 LangGraph 和支持会话、恢复、人工审批的订单诊断 Agent。

## 启动

```bash
.venv/bin/python -B main_api.py
```

浏览器打开 [Swagger](http://127.0.0.1:8000/docs)。在 IDE 中直接 Run / Debug `main_api.py` 也可以。运行环境需要 `pyproject.toml` 中声明的依赖。

VS Code 的“运行和调试”下拉框选择“启动 FastAPI”，按 F5。项目已提供 `.vscode/launch.json`，固定运行根目录 `main_api.py`，使用项目 `.venv/bin/python`。`src/agent_learning/__main__.py` 只显示旧入口提示，不用于启动 API。

`.vscode/settings.json` 已配置 `src` 导入路径、项目解释器、索引与自动导入补全。API 的 Service 获取函数、Service 的核心组件属性、图构造函数均声明具体类型，方便使用 F12“转到定义”。修改配置后可执行 VS Code 的 `Developer: Reload Window` 重载窗口；调试时进入方法使用 F11。

启动只构造 Service、模型适配对象和图，不建表、不入库、不连接数据库、不请求模型。查询知识库和提问时才使用已配置服务；`POST /api/rag/ingest` 是明确的写入入口。`main_ingest.py` 默认 `WRITE_TO_DB=False`，只做预览。

服务使用单进程和内存 Checkpoint，重启会丢失会话。所有自定义 API 的上方注释都有 JSON 参数示例，GET 接口另注明路径参数和无 JSON 请求体。

## 代码结构

```text
main_api.py                         HTTP 主入口、异常响应、路由注册
src/agent_learning/
  bootstrap.py                      显式创建全部依赖和四个 Service
  api/
    schemas.py                      Pydantic 请求参数
    dependencies.py                 获取应用中已创建的 Service
    rag.py                          资料与问答接口
    orders.py                       订单和固定流程接口
    agent.py                        会话、追问、恢复、审批接口
    lessons.py                      基础课程接口
  services/
    rag_service.py                  资料文件范围检查和 RAG 调用
    order_service.py                业务查询与固定工作流
    agent_service.py                内存会话、串行访问、结果整理
    lesson_service.py               基础图的独立调用
  core/                             配置、数据对象、模型适配
  rag/                              加载、切分、入库、检索、精排、引用校验
  business/                         JSON 订单、支付、退款 Tool
  workflows/                        基础图、固定流程和综合诊断图
```

API 接收请求，Service 调用核心方法，核心流程通过 Repository 或 JSON Tool 获取数据。Service 直接使用普通类，不增加接口类、Impl 或 ORM。表结构仍以 `sql/` 中现有文件为准。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 检查 HTTP 服务，不探测数据库或模型 |
| POST | `/api/rag/preview` | 读取 data 目录内资料并切分预览 |
| POST | `/api/rag/ingest` | 显式向量入库，不自动建表 |
| POST | `/api/rag/ask` | 独立 RAG 问答与引用 |
| GET | `/api/orders/{order_id}` | 查询订单 |
| GET | `/api/orders/{order_id}/payments` | 查询全部支付记录 |
| GET | `/api/orders/{order_id}/refunds` | 查询全部退款记录 |
| POST | `/api/workflows/order-check` | 固定订单、支付、退款流程 |
| POST | `/api/agent/sessions` | 创建会话 |
| POST | `/api/agent/sessions/{session_id}/messages` | 提问与多轮追问 |
| GET | `/api/agent/sessions/{session_id}` | 查看保留的对话和当前待办 |
| POST | `/api/agent/sessions/{session_id}/resume` | 继续普通暂停或可恢复节点 |
| POST | `/api/agent/sessions/{session_id}/approvals` | 批准或拒绝当前模拟操作 |
| POST | `/api/lessons/single-node` | 单节点图 |
| POST | `/api/lessons/state-flow` | 两节点 State 传值 |
| POST | `/api/lessons/conditional-route` | 普通回答与本地 Tool 条件路由 |
| POST | `/api/lessons/business-tool` | 业务 Tool 成功、失败分支 |
| POST | `/api/lessons/pause-demo` | 自动创建演示会话，执行第一步后暂停 |
| POST | `/api/lessons/pause-demo/{session_id}/resume` | 使用演示会话编号继续第二步 |
| POST | `/api/lessons/approval-demo` | 自动创建演示会话，申请模拟取消并等待审批 |

详细调用示例见 [API 使用说明](docs/20-fastapi.md)。

最简单的暂停演示调用 `pause-demo` 和 `pause-demo/{session_id}/resume`：第一个传 `{"question":"你好"}`，内部复用 `create_session()` 生成编号，返回 `paused`；第二个在 URL 中填入刚返回的编号，请求体传 `{}`，返回 `completed`。演示是固定两节点图，不调用模型、业务 Tool 或数据库。

最简单的审批演示先调用 `/api/lessons/approval-demo`，传 `{"order_id":"A1001"}`；取得 `session_id` 和 `approval.approval_id` 后，调用原 `/api/agent/sessions/{session_id}/approvals`，传 `{"approval_id":"返回的审批编号","decision":"approve"}`。固定图通过 `interrupt()` 等待批准，批准后返回模拟取消结果。它只演示流程，不读取、验证或修改实际订单，也不调用模型。

## 会话与执行

先创建会话，把返回的 `session_id` 放在后续 URL 中。同一会话保留最近的完整问答轮次；新建会话用于隔离历史。`pause_before_tools=true` 可演示第 65 课的普通工具前暂停，随后提交空 JSON 到 `resume` 继续。

取消待支付订单 A1001 时，模型只能提出请求。程序验证订单后返回 `waiting_approval` 和 `approval_id`；人工通过审批接口提交 `approve` 或 `reject`。审批编号与本次订单、租户和工具请求绑定，旧编号不可重放。确认后仍只模拟，不写业务 JSON。

`status` 只表达业务待办：`ready`、`completed`、`paused`、`waiting_approval`、`failed`。接口不返回原始 State、节点、Tool 执行记录、重试次数、耗时、Token、费用或异常原文。综合回答的规则引用按每次知识库问题分组，避免不同调用的 `[1]` 混淆。

有限重试、最大模型 / Tool 执行机会和上下文字符上限用于结束流程；没有用量费用记账、Tracing、执行日志或日志平台。网络请求保留普通超时。应用入口关闭 Uvicorn 的访问与框架日志。

## 配置与手动入口

服务端身份在 `bootstrap.py` 中设置，默认租户 acme、读取级别 1。客户端不能提交租户、读取级别、内部图状态或模型连接配置。模型与数据库配置继续由 `core/config.py` 加载，真实凭证不放入源码或接口示例。

`main_ingest.py`、`main_ask.py` 和简短的 `main_workflow.py` 可手动运行。五个重复 Console 入口已合并，原课程的核心图保留在 `workflows/`。`old/`、`python_basic/`、`rag/` 和原课程资料保留用于对照。

当前测试源文件和对应测试缓存已按要求删除，不保留测试运行入口。此次验证使用临时离线核查和 FastAPI TestClient，真实数据库、模型请求与向量入库未执行。

## 第 71 课：MCP 概念

运行 `.venv/bin/python -B main_mcp_basics.py`，用同一个 `hello()` 函数对照直接调用、function calling 与 MCP 调用字段。代码每个逻辑语句上方都有中文注释，使用标准库即可运行。它是概念演示；真实 Server 与 Client 在后续课程实现。

[第 71 课说明](docs/21-mcp-basics.md) 包含调用方式对照、Tools / Resources / Prompts 分工和版本台账。SDK 在 `pyproject.toml` 固定为 `mcp==2.3.0`，主协议为 `2026-07-28`。

## 第 72 课：MCP Server

在项目根目录运行：

```bash
.venv/bin/python -B main_mcp.py
```

也可以直接 Run / Debug `main_mcp.py`，或选择 VS Code 的“启动 MCP（第72课）”。调用地址是 `http://127.0.0.1:8001/mcp`，工具定义在 `mcp_server/server.py`。

本课只有无参数的 `hello` 和带字符串参数的 `greet`。SDK 负责工具发现、参数校验和结果转换；代码每个逻辑语句上方都有中文注释。已通过临时 TestClient 验证 `2026-07-28` 与 `2025-11-25` 两种协议的发现与调用，以及新协议的参数错误，详见 [启动与 Postman 示例](docs/22-mcp-server.md)。

## 第 73 课：get_order MCP Tool

重启同一个 `main_mcp.py`，`tools/list` 会增加 `get_order`。它只接收 `order_id`，复用 `src/agent_learning/business/tools.py` 的原函数，租户在 Server 中固定为 acme。成功或失败的业务字典同时提供文字与结构化结果，`success=false` 对应 MCP 的 `isError=true`。

[第 73 课说明](docs/23-mcp-get-order.md) 包含完整 Postman Headers 与 JSON。普通函数 → MCP 结果的适配代码在 `mcp_server/server.py`，已验证正常查询、订单不存在、跨租户隔离与新旧协议调用。
