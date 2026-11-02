# 第 60 课：业务 Tool 与条件路由

当前入口是 `POST /api/lessons/business-tool`，JSON 入参为 `{"order_id":"A1002"}`。图在 `workflows/business_tool.py`，业务函数在 `business/tools.py`。

执行顺序：prepare 整理订单号 → get_order 查询 → 根据 success 选择成功或失败回答 → END。

业务 Tool 接收普通订单号和服务端租户，只读 JSON，返回 `success/data/error`。图节点从 State 取参数，调用 Tool，再返回需要更新的字典。条件路由读取合并后的 State，只返回下一节点标签。

`POST /api/lessons/conditional-route` 展示普通文字与本地字符数 Tool 的分支，`single-node` 和 `state-flow` 分别展示单节点和两个节点传值。

接口不返回节点或工具执行记录。参数示例在每个 API 方法上方，也可查看 [FastAPI](20-fastapi.md)。
