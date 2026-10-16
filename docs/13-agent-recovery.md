# 第 63 课：重试、失败恢复与执行预算（保留课程）

本课沿用 DeepSeek 的兼容 Chat Completions 接口。入口保留为根目录 `main_workflow_recovery.py`，图放在 `src/agent_learning/workflows/recovery_agent.py`；当前 `main_workflow.py` 已进入 [第 67 课人工确认](17-human-in-the-loop.md)。第 62 课 `agent_loop.py` 的图保留；模型适配新增 `request_with_tools()`，旧的 `chat_with_tools()` 仍返回原来的 assistant 字典。所有新逻辑语句都有上方中文注释。

运行入口才读取已有模型配置并调用模型。本课实现和测试没有读取 `.env` 密钥，没有真实 API 请求、数据库操作、模型下载或写业务操作。订单、支付、退款继续只读本地 JSON；金额字段仍为字符串，租户与路径只由可信入口注入。

## 先理解三个职责

1. **模型节点**：请求前检查预算；发一次请求；无论成功或失败都计数、记账；只有临时异常才有限重试。
2. **工具节点**：按调用 ID 分发只读查询；普通 `success=false` 直接失败；成功空列表仍为成功；临时异常有限重试。
3. **失败节点**：程序生成结束说明，不额外调用模型。保留已取得证据；同批没执行的请求记录为 `attempts=0`，不冒充查过但无记录。

正常路径：`prepare → model → tools → model → finish → END`。模型直接回答时不进入 tools；业务失败、系统失败、预算不足或启用限制后的超时则进入 `failure → finish → END`。重试发生在节点内部，只有次数与启用的预算允许时才能启动下一次尝试。当前学习入口默认关闭时间限制，断点暂停不会触发超时失败。

## 重试的范围

| 情况 | 本课处理 |
|---|---|
| 查询成功，包括 `data=[]` | 保留结果，继续模型决策 |
| 订单不存在、权限不可读取、参数或 JSON 数据问题，Tool 返回 `success=false` | 不自动重试，进入 `business_error` 分支 |
| 连接错误、请求超时异常、HTTP 408 / 429 / 500 / 502 / 503 / 504 | 有限重试，仍检查步骤和预算；时间限制仅在开启时检查 |
| HTTP 401 / 403、配额不足、已知账单问题、错误参数、坏协议或未知异常 | 不自动重试 |
| 开启时间限制后，同步 Tool 返回时超过单次时间窗口 | 保留实际返回的事实，设置 `tool_timeout`，不启动后续查询 |

`MAX_RETRIES=2` 表示每次模型决策或每条 Tool 请求最多 **额外重试两次**，不是总共只执行两次。实际次数还可能先被其他预算截断。`model_retries`、`tool_retries` 只在真正开始额外尝试时增加，等待后预算不足不算已经重试。

SDK 使用 `max_retries=0`，重试都由工作流管理。等待采用有限的指数退避和少量抖动；HTTP `Retry-After` 支持秒数和日期，不能提前重试。提示等待超过 `max_retry_delay` 时直接结束；开启时间限制时还检查剩余总时间，不把服务端提示截短。关闭超时不改变重试次数或最大退避等待。这与 [OpenAI 官方重试说明](https://developers.openai.com/api/docs/guides/rate-limits) 的计数和等待约定一致；错误分类参考 [SDK 异常说明](https://developers.openai.com/api/docs/guides/error-codes)。

当前 JSON Tool 会把已知文件错误转换成安全的 `success=false`，因此不靠匹配错误文案把它们猜成临时异常。离线测试通过注入 `ConnectionError` 等异常验证未来只读 HTTP Tool 的恢复策略；并不代表已经接入业务 HTTP 服务。

## 预算放在哪里

直接在 `main_workflow_recovery.py` 顶部修改，不使用 argparse 或反射配置。

| 参数 | 默认值 | 意义 |
|---|---|---|
| `MAX_STEPS` | 5 | 实际模型请求尝试总数，含失败、重试与最终回答 |
| `MAX_TOOL_CALLS` | 6 | Tool 分发尝试总数，含同批请求、被拒绝请求与重试 |
| `MAX_RETRIES` | 2 | 单次模型决策 / 单条 Tool 请求的额外尝试上限 |
| `ENABLE_TIMEOUTS` | `False` | 当前入口关闭全部超时限制，便于逐步 Debug；改为 `True` 才启用下面三项 |
| `MODEL_TIMEOUT` | 30 秒 | 开启后生效：单次模型 HTTP 客户端超时，取其与整体剩余时间的较小值 |
| `TOOL_TIMEOUT` | 2 秒 | 开启后生效：同步本地 Tool 返回后的耗时检测窗口 |
| `OVERALL_TIMEOUT` | 90 秒 | 开启后生效：单次任务截止时间，包含重试等待与断点暂停 |
| `MAX_OUTPUT_TOKENS` | 1200 | 每次请求的 `max_tokens` 参数 |
| `MAX_TOTAL_TOKENS` | 30000 | 单次任务累计 Token 预算，含失败未知用量的预留 |
| `MAX_COST` | 0.50 CNY | 按配置单价累计的估算费用预算 |

一条 Tool 请求可能返回多笔支付或退款，但仍只算一次分发尝试。重试两次会算三次；完全跳过的请求算零次，但仍有结果记录。达到模型第五次尝试时，如果已给出正常答案属于 `final_answer`；如果仍请求 Tool，会在 Tool 预算与时间允许时完成这一轮，再结束，不发第六次模型请求。

图的 `recursion_limit` 是另一层调度保护，不等于模型请求数。本课根据 `MAX_STEPS` 设置 `2 * MAX_STEPS + 6`，给 prepare、失败分支、最后的预算检查与 finish 留出节点调度余量。

## Token 与费用：请求前预留，返回后记账

`request_with_tools()` 返回 `message`、`usage`、`finish_reason` 三部分。仅 `message` 追加到模型上下文；`usage` 留在控制流程中，避免混进下一次 assistant 消息。

1. 请求前用 **消息和工具 Schema 的 UTF-8 字节数加余量**粗估输入，再预留最大输出 Token。这不是精确 tokenizer，也不下载 tokenizer。
2. 预留超过剩余 Token 或估算费用预算时，不发出请求。
3. 请求返回后，使用合法的 `usage.prompt_tokens` / `completion_tokens` / `total_tokens` 累计。被截断的响应也计入用量，不能免费忽略。
4. 异常、缺失或错误 usage 按本次完整预留计入，记录 `source=estimated_reservation`，不当作零费用。正常接口用量记录 `source=api_usage`。
5. 实际用量超过粗估或预算时立即停止后续调度，已发生的请求无法撤回。

金额用 `Decimal` 累计，再以字符串存入 State；不引入数据库。`INPUT_PRICE_PER_MILLION="10"`、`OUTPUT_PRICE_PER_MILLION="20"` **是教学演示单价，不是 DeepSeek 当前价格**。真实运行前按你实际使用的模型、输入 / 输出计价与币种核对并修改；本例不自动获取价格、不假设缓存折扣。`USE_OLLAMA=True` 时入口显式使用零费用单价，但仍限制 Token 和尝试次数。

**这里限制的是本次任务的估算，不是账号账单硬上限。** 粗估输入、失败请求用量未知、提供方 tokenizer / 计价差异、缓存折扣及其他并发任务都会影响账单。生产环境还需要模型匹配的计数器、提供方账户级费用限制与账单核对，不能声称当前实现保证绝对不多花一分钱。

## 超时边界与后续检查点

`main_workflow_recovery.py` 默认 `ENABLE_TIMEOUTS=False`，传入图的 `limits["enable_timeouts"]` 也是 `False`：`prepare` 设置 `deadline=None`，跳过整体截止、单次模型耗时、单次 Tool 耗时和重试等待的截止检查。模型适配把 `timeout=None` 原样传给 SDK，明确关闭客户端 HTTP 超时，不回退到配置中的超时秒数。仍用 `time.monotonic()` 记录耗时，包含断点暂停，但这个记录不会影响路由。

需要学习超时分支时，将入口的 `ENABLE_TIMEOUTS=True`。此时使用单调时钟的截止时间，在每次模型、Tool 和重试前检查；操作返回后也检查，迟到模型响应不再执行其中 Tool。SDK 接收不超过剩余时间的 HTTP 超时，但该超时涉及连接 / 读取等阶段，并非远端任务取消凭证。直接调用 `build_graph()` 而不传开关时，图的默认配置仍开启时间限制；旧课 `chat_with_tools()` 仍使用原配置的模型超时。

关闭客户端超时不保证网络或服务提供方永不报错；请求可能持续等待服务返回。真实连接错误、业务失败、重试耗尽以及步骤 / Tool / Token / 费用预算不足，仍会进入失败分支，并非强制把失败改成成功。

本地 JSON Tool 是同步普通函数：本课只能在函数返回后识别单次超时，**不能中断仍在阻塞的 Python 函数**，也不能保证 `invoke()` 在整体截止的那一毫秒立刻返回。没有用 `ThreadPoolExecutor.result(timeout=...)` 冒充取消，因此也没有“前台结束后后台线程继续执行”的隐患。

后续实现检查点，当前不宣称已完成：

- 更严格的任务终止：可取消的异步只读请求或隔离进程；确认超时后没有新的调度，必要时确认工作进程退出。
- 远端取消与结果核对：客户端超时不等于服务端没有处理，不能仅靠超时异常猜测操作未执行。
- 写操作幂等性：支付 / 发起退款等写操作需人工确认、权限校验和稳定的业务幂等键；核对结果之后才决定重试。模型生成的 `tool_call_id` 只是协议配对标识，不自动等于业务幂等键。
- 本课仅 `get_order/get_payment/get_refund` 三个只读查询，没有写操作可被自动重试。

## Run 与逐步 Debug

打开根目录 `main_workflow_recovery.py`，解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`，用可输入问题的 Console 点击 Run / Debug。无需参数。

```bash
.venv/bin/python -B main_workflow_recovery.py
```

`USE_OLLAMA=False` 沿用 `LLM_BASE_URL`、`LLM_MODEL` 与 `LLM_API_KEY` / `DEEPSEEK_API_KEY`；未覆盖时配置默认指向 DeepSeek。已有密钥无需复制到新代码。程序加载配置不会创建数据库连接。实际运行会调用模型并可能产生费用；本次只执行了离线测试。

先输入「查询 A1002 的退款记录」，观察自然完成；再输入「查询 A9999 的订单」，观察 `business_error` 失败分支。真实模型可能直接澄清或选择不同的 Tool，以实际 `tool_calls` 为准，不靠提示词宣称固定路径。

| 断点 | 看什么 |
|---|---|
| `main_workflow_recovery.py` 的 `result = graph.invoke(initial_state)` | 原始问题、可信租户和预算常量 |
| `recovery_agent.prepare_node()` | `limits["enable_timeouts"]=False`、`deadline=None`、初始计数与空历史 |
| `check_model_budget()` | 下一次请求为何允许或被步骤 / Token / 费用截断 |
| `model_node()` 的 `model.request_with_tools(...)` | 每次实际模型尝试、默认 `timeout=None`、输出上限 |
| `tool_model.request_with_tools()` | SDK 请求、消息、usage 与 finish_reason 分离 |
| `charge_usage()` | 本次用量来自 API 还是完整预留，累计 Token 与费用 |
| `is_temporary_error()` / `wait_to_retry()` | 错误类别、重试等待与剩余时间 |
| `tools_node()` 的 `dispatch_tool(...)` | 实际 Tool 尝试数、业务失败与异常区别 |
| `record_tool_result()` | 一条调用可尝试多次，但只追加一次配对结果 |
| `failure_node()` | 程序生成失败说明，不再花费用调用模型 |
| `finish_node()` | 同批未执行请求的 `attempts=0`、配对消息和总耗时 |

当前默认可以在节点内部长时间暂停，无需调大 `OVERALL_TIMEOUT` 或 `TOOL_TIMEOUT`。Console 会显示「超时限制：关闭（可逐步 Debug）」。步骤、Tool 次数、重试次数、Token 与费用预算仍然生效，避免无限循环；只有主动改为 `ENABLE_TIMEOUTS=True` 后，断点暂停才可能触发超时失败。

## 离线重试演示入口

```bash
PYTHONPATH=src .venv/bin/python -B -m unittest discover -s tests -p test_recovery_agent.py -v
```

也可在 IDE 中将以下方法作为 unittest 测试直接 Debug：

- `test_model_temporary_error_recovers`：第一轮连接异常，第二轮成功；看 `model_steps`、`model_retries` 与未知用量预留。
- `test_tool_temporary_error_recovers`：同一 Tool 第一次异常，第二次返回两笔退款；看两次尝试如何只配对一次结果。
- `test_business_failure_skips_remaining_batch`：订单不存在后，同批退款查询不执行；看失败分支与 `attempts=0`。
- `test_tool_overslept_retry_keeps_attempt`：等待本身超时，第一次尝试仍被保留，第二次不开始。
- `test_reported_usage_can_stop_before_tools`：接口实际报告超出预算，记账后不执行 Tool。
- `test_timeouts_disabled_allow_long_model_and_tool`：虚拟时钟模拟模型和 Tool 内数千秒暂停，仍正常返回 `final_answer`；耗时记录保留。
- `test_timeouts_disabled_model_retry_crosses_previous_deadline` / `test_timeouts_disabled_tool_retry_survives_long_pause`：关闭时间限制后跨过原截止时间，仍可在次数与费用预算内恢复。

预设模型与虚拟时钟仅用于离线测试，不放进生产入口，也不冒充真实 LLM 推理。测试覆盖旧图兼容、业务失败、临时 / 永久错误、重试耗尽、每类预算、同批跳过、迟到响应、缺失 usage、证据保留、独立任务初始化、超时开关、Debug 长暂停以及真实 SDK 请求参数组装。
