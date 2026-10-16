# 第 60 课：接入阶段 3 Tools

本课把阶段 3 的业务函数调用方式接到 LangGraph 中。先使用本地 JSON 的 `get_order`，观察参数和返回值怎样经过 State；Console 直接输入订单号，租户由入口提供。

本文件保留第 60 课说明，`workflows/business_tool.py` 未改动。根目录 `main_workflow.py` 已切换到第 67 课人工确认，当前运行和 Debug 步骤见 [第 67 课](17-human-in-the-loop.md)；下文记录的是第 60 课当时的入口和断点。

```text
START
  ↓
prepare_node：整理订单号，返回 order_id
  ↓
get_order_node：调用业务 get_order，返回 tool_name 和 tool_result
  ↓
choose_result_route：根据 tool_result["success"] 返回路由标签
  ├── success → answer_node → END
  └── error   → error_answer_node → END
```

`choose_result_route` 是 `get_order` 节点完成后调用的路由函数，并未注册成业务节点。它读取的是已更新的 State，每次只选择一个回答分支。

## Tool、节点和 State

| 位置 | 职责 |
|---|---|
| `business/tools.py` 的 `get_order()` | 接受普通参数，查询 JSON，返回普通字典，不认识 State 或 LangGraph |
| `workflows/business_tool.py` 的 `get_order_node()` | 从 State 取参数，调用 Tool，返回需要写回 State 的字段 |
| `choose_result_route()` | 读取 Tool 的 `success`，返回下一节点的标签 |
| `answer_node()` / `error_answer_node()` | 读取业务数据或错误，写入最终回答和分支 |

建图时的 `run_get_order()` 是一个普通的转交函数：把入口选择的 `data_file` 传给 `get_order_node()`。图中的节点名为 `get_order`，真正的执行顺序为 `run_get_order → get_order_node → business.tools.get_order`。

State 保存 `question`、`tenant_id`、`order_id`、`tool_name`、`tool_result`、`branch` 和 `answer`。入口先填入问题与可信租户，其他字段初始化为空；每个节点只返回自己更新的字段，LangGraph 把这些字段合并到当前 State。

Tool 的成功结果如下；失败时 `success=false`、`data=null`，`error` 填入失败说明：

```json
{
  "success": true,
  "data": {
    "tenant_id": "acme",
    "order_id": "A1002",
    "status": "已支付",
    "amount": "299.00",
    "currency": "CNY",
    "updated_at": "2026-09-28T09:05:00+08:00",
    "source": "json"
  },
  "error": null
}
```

这沿用了阶段 3 的函数名和 `success/data/error` 结构。当前新 Tool 读取 `data/business_demo.json`，原有 `python_basic/toolcalling/` 代码保留对照；旧 MySQL 连接和取消订单写操作没有进入本课入口。

## Run / Debug 入口

打开项目根目录 `main_workflow.py`，解释器选择 `/Users/uranuschen/ai-study/.venv/bin/python`，直接点击 Run 或 Debug，无需填写命令行参数。使用能输入文字的终端，看到提示后输入 `A1002` 并按回车。

```bash
.venv/bin/python -B main_workflow.py
```

入口顶部可以修改 `DATA_FILE` 和 `TENANT_ID`；默认文件是本地样例，默认租户为 `acme`。订单号会去掉两端空格并转成大写，因此 `  a1002  ` 也可以查询。

按以下顺序打断点，用“单步跳过”看字段变化，用“单步进入”进入业务 Tool：

1. 在 `main_workflow.py` 的 `result = graph.invoke(initial_state)` 停下，观察初始字段。`question` 是原始输入，`tenant_id` 来自入口配置。
2. 在 `prepare_node()` 的返回语句停下，观察 `order_id`。继续执行后，这个字段才会合并到 State。
3. 在 `get_order_node()` 的 `result = get_order(...)` 停下。查看订单号、租户和文件路径，再单步进入 `business/tools.py` 的 `get_order()`。
4. 在 `get_order()` 的租户 / 订单号判断处停下，观察 JSON 中两条同号订单为什么只匹配一条。成功后观察 `data` 和返回字典。
5. 在 `get_order_node()` 的返回语句停下，查看局部变量 `result`；此时节点尚未返回，因此 `state["tool_result"]` 还没有本次新结果。
6. 在 `choose_result_route()` 的 `if` 停下，查看合并后的 `state["tool_result"]`。`success=true` 返回 `success`，否则返回 `error`。
7. 在被选中的回答节点停下，查看最终 `branch` 和 `answer`；返回入口后，Console 会打印 Tool 结果和输出。

空订单号、订单不存在、文件缺失、JSON 损坏或字段错误都能进入失败回答并结束。本课不循环；重试和执行预算在后续课程加入。Tool 发生意外异常时，可以在 `get_order_node()` 的 `except` 分支里观察 `error`。

## 对照案例

| 输入 / 配置 | 应观察的结果 |
|---|---|
| 默认租户，输入 `A1001` | 成功分支，待支付，`199.00 CNY` |
| 默认租户，输入 `  a1002  ` | 整理成 `A1002`，成功分支，已支付，`299.00 CNY` |
| 默认租户，输入 `A1003` | 成功分支，已完成，`499.00 CNY` |
| 默认租户，输入 `A9999` | 失败分支，订单不存在或不可读取 |
| 只按回车 | 失败分支，提示非空订单号，不读取 JSON |
| `TENANT_ID="other"`，输入 `A1002` | 该租户订单：已取消，`79.00 CNY` |
| `DATA_FILE` 改成不存在的路径 | 失败分支，提示文件路径或权限问题，结束后恢复配置 |

样例状态截至各记录的 `updated_at`，属于模拟业务数据。金额先用字符串保留精确表示，本课没有金额计算。

## 离线验证

```bash
PYTHONPATH=src .venv/bin/python -B -m unittest discover -s tests -p 'test_business_tools.py' -v
PYTHONPATH=src .venv/bin/python -B -m unittest discover -s tests -p 'test_workflow.py' -v
```

测试覆盖 Tool 返回结构、金额保留、租户隔离、缺失参数、文件 / JSON 错误，以及真实 LangGraph 的成功与失败分支。第 61 课已经加入支付和退款 Tool，练习多节点及按业务结果继续查询，上一课测试继续保留。
