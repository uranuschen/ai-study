# 第 61 课：多步订单工作流

本课在第 60 课 JSON 订单 Tool 上增加支付、退款查询和总结。先理解顺序链路 `订单 → 支付 → 退款 → 总结`，再将订单、支付后的普通连线替换为业务条件路由。所有 Tool 都是只读查询，不执行支付或退款；不连接数据库、RAG 或 LLM。

本文件保留第 61 课说明，`workflows/order_flow.py` 未改动。根目录 `main_workflow.py` 已切换到第 63 课，当前入口会调用模型，运行与 Debug 见 [第 63 课](13-agent-recovery.md)。下文入口步骤记录第 61 课当时的配置；本课离线测试仍可独立运行。

## 执行顺序与提前结束

```text
START → prepare → get_order
                    ├─ 查询失败 / 订单不存在 / 待支付或未支付 → summarize → END
                    └─ 其他状态 → get_payment
                                     ├─ 查询失败 / 无记录 / 没有支付成功项 → summarize → END
                                     └─ 至少一笔支付成功 → get_refund → summarize → END
```

`choose_order_route()` 和 `choose_payment_route()` 是路由函数，不是独立节点。节点返回字典并合并到 State 后，LangGraph 才调用对应路由。路由只返回下一节点的标签，不修改业务数据。

退款查询后不再有新的业务 Tool，所以有退款、无退款或退款查询失败都会直接总结并结束。无退款是正常业务结果，不进入循环，也不尝试发起退款。图没有回边，每个查询 Tool 最多执行一次。

订单明确标记「待支付 / 未支付」时跳过支付、退款；其他状态先读支付记录验证。比如订单「已取消」不能一概视为没有支付，它可能先支付后取消。本课样例 `other` 的 `A1002` 就保留了支付及退款记录。

## 代码位置

| 文件 | 职责 |
|---|---|
| `main_workflow.py` | Console / Debug 入口，直接配置 `DATA_FILE` 和可信 `TENANT_ID` |
| `src/agent_learning/workflows/order_flow.py` | State、三个查询节点、两处条件路由、总结节点与建图 |
| `src/agent_learning/business/tools.py` | `get_order`、`get_payment`、`get_refund` 只读业务函数 |
| `data/business_demo.json` | 本地订单、支付、退款模拟数据，金额用字符串保存 |
| `tests/test_order_flow.py` | 离线 Tool 与真实 LangGraph 分支测试 |

上一课 `workflows/business_tool.py` 保留不动。三个 `run_get_*()` 仍是 `build_graph()` 内部的普通函数，用来把入口文件路径传给节点：`run_get_payment → get_payment_node → get_payment → read_order_records`。

## 保留各步结果

State 分别保存 `order_result`、`payment_result`、`refund_result`。每个查询节点只返回自己的结果字段和新的 `executed_tools` 列表，LangGraph 合并更新时保留其他字段。例如支付节点不会将订单结果替换为支付结果。

| 保存的值 | 含义 |
|---|---|
| `{}` | 节点未执行，尚未查询；不能说没有业务记录 |
| `{"success": true, "data": [], "error": null}` | 支付或退款已查询成功，但没有匹配记录 |
| `{"success": true, "data": [...], "error": null}` | 查询成功，保留全部同租户、同订单的支付或退款记录 |
| `{"success": false, "data": null, "error": "..."}` | 查询失败，保留错误；不能推断没有记录 |

订单成功结果的 `data` 是单个字典，支付、退款成功结果的 `data` 是列表。`has_successful_payment()` 遍历全部支付，只要至少一条状态是「支付成功」就查退款；不会只看第一笔失败记录。总结会保留每笔记录的真实状态，不把「退款中」说成「退款到账」。本课不计算累计金额。

## Run / Debug 入口

在 IDE 打开根目录 `main_workflow.py`，解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`，点击 Run / Debug。无需参数，使用能输入文字的终端。

```bash
.venv/bin/python -B main_workflow.py
```

按下面顺序打断点：

1. `main_workflow.py` 的 `result = graph.invoke(initial_state)`：查看原始问题、可信租户和三个空结果字段。
2. `order_flow.py` 的 `prepare_node()`：查看订单号去空格、转大写，以及这次执行的字段初始化。
3. `get_order_node()` 的 `result = get_order(...)`：单步进入订单 Tool，看统一返回字典。
4. `choose_order_route()`：此时 `state["order_result"]` 已经更新。输入 `A1001` 或 `A9999` 时返回 `summarize`，支付、退款节点的断点不会命中。
5. `get_payment_node()` 与 `choose_payment_route()`：输入 `A1002`，观察第一笔失败、第二笔成功，仍然继续查退款；输入 `A1004` 或 `A1005`，观察提前进入总结。
6. `get_refund_node()`：输入 `A1003`，观察 `success=True`、`data=[]`，这与未执行的 `{}` 不同。
7. `summarize_node()`：观察三个原始结果、`executed_tools`、最终 `branch` 和 `answer`，确认总结不再次调用 Tool。

文件读取失败也会总结并结束。Tool 意外抛出异常时，在三个查询节点的 `except` 分支查看局部变量 `error`。本课是失败分支处理，不是自动重试或持久化恢复；这些留待后续课程。

## 对照案例

| 输入（默认租户 acme） | 实际调用 Tool | 结束分支 |
|---|---|---|
| `A9999` 或空输入 | get_order | order_error |
| `A1001` | get_order | unpaid |
| `  a1002  ` | get_order → get_payment → get_refund | completed：两笔支付、两笔退款都保留 |
| `A1003` | get_order → get_payment → get_refund | no_refund：已查过，但无退款记录 |
| `A1004` | get_order → get_payment | payment_missing |
| `A1005` | get_order → get_payment | payment_not_success |
| 数据文件不存在或损坏 | get_order | order_error：保留文件错误 |

`A1004`、`A1005` 故意让订单状态与支付记录不足或未成功的情况并存，用来练习不凭订单文字推断支付事实。总结保留两边原始结果，明确无法确认成功，不把缺失记录改写成「订单一定未支付」。改入口 `TENANT_ID="other"` 查询同号 `A1002`，三种数据都只能来自 `other`，金额为该租户的 `79.00 CNY`。

`completed` 只表示按本课规则完成了三个查询，不表示所有退款成功，也不表示用户的问题已经得到真实系统验证。数据都是 JSON 模拟样例，事实时间以各记录的 `updated_at` 为准。

## 离线测试与本课验收

```bash
PYTHONPATH=src .venv/bin/python -B -m unittest discover -s tests -p 'test_order_flow.py' -v
PYTHONPATH=src .venv/bin/python -B -m unittest discover -s tests -p 'test_business_tools.py' -v
```

验收时依次演示不存在订单、未支付订单、完整查询、无退款；说明路由为何选择下一步、被跳过的 Tool 为什么没有执行，以及后续节点为什么没有覆盖已有结果。下一课再学习受控 Agent loop，本课仍然是程序规则决定路径的确定性工作流。
