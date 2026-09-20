# Refund Analysis Agent

一个基于 LLM Tool Calling 实现的订单退款失败分析助手。

项目通过大模型理解用户问题，由 LLM 自动选择合适的业务 Tool，查询订单、用户、支付、退款等数据，并结合多个 Tool 的返回结果分析退款失败原因。

当前项目主要用于学习和实践：

* LLM API 调用
* Tool Calling
* Tool Registry / Dispatcher
* 多 Tool 连续调用
* Tool 参数规范
* Tool 返回结构
* 超时与异常处理
* Tool 调用日志
* Tool 白名单
* SQL 安全控制
* 基础 Agent 工作流程

---

# 1. 项目目标

用户可以直接使用自然语言询问订单相关问题，例如：

```text
A1002订单状态是什么？
```

```text
A1002支付成功了吗？
```

```text
A1002退款状态是什么？
```

```text
A1002为什么退款失败？
```

程序负责完成：

```text
用户问题
   ↓
LLM理解问题
   ↓
选择Tool
   ↓
生成Tool参数
   ↓
执行Tool
   ↓
把Tool结果返回给LLM
   ↓
LLM决定：

继续调用其他Tool
        或
生成最终回答
```

对于复杂问题，可以进行多次 Tool 调用。

---

# 2. 当前实现功能

目前已经完成以下功能：

* `get_order`
* `get_user`
* `get_payment`
* `get_refund`
* 统一 Tool 参数结构
* 统一 Tool 返回结构
* Tool Registry
* Tool Dispatcher
* 单次 Tool Calling 闭环
* 多 Tool 连续调用
* Tool 超时处理
* Tool 异常捕获
* Tool 调用日志
* Tool 白名单
* 禁止 LLM 执行任意 SQL
* 退款失败原因分析
* 10 个问题阶段验收

---

# 3. 项目结构

项目结构大致如下：

```text
toolcalling/
│
├── mian_mysql.py
│
├── tools.py
│
├── db.py
│
├── .env
│
└── README.md
```

各文件职责：

## `mian_mysql.py`

程序主入口。

主要负责：

* 接收用户问题
* 调用 LLM
* 接收 LLM Tool Calling 请求
* 执行对应 Tool
* 将 Tool 结果重新发送给 LLM
* 控制多 Tool 调用流程
* 输出最终回答

---

## `tools.py`

业务 Tool 实现。

目前主要包含：

```python
get_order(order_id)
get_user(...)
get_payment(order_id)
get_refund(order_id)
```

每个 Tool 只负责一个明确的业务能力。

例如：

```text
get_order
```

只查询订单。

```text
get_payment
```

只查询支付信息。

```text
get_refund
```

只查询退款信息。

LLM 不直接访问数据库，而是只能通过这些 Tool 获取数据。

---

## `db.py`

数据库连接模块。

统一负责创建 MySQL Connection。

例如：

```python
conn = get_connection()
```

业务 Tool 不重复创建数据库连接配置。

---

## `.env`

保存本地环境变量，例如：

```text
DEEPSEEK_API_KEY=xxx
```

API Key 不应该直接写在 Python 源代码中。

`.env` 不应该提交到公开 Git 仓库。

---

# 4. LLM

当前项目使用：

```text
DeepSeek
```

模型：

```text
deepseek-chat
```

主要用于：

* 理解用户意图
* Tool 选择
* Tool 参数生成
* 多步 Tool 决策
* 根据查询结果生成最终答案

LLM 本身不直接查询 MySQL。

---

# 5. Tool设计原则

当前项目中的 Tool 使用一个基本原则：

```text
一个Tool负责一个明确能力
```

例如：

```text
get_order
```

负责查询订单。

而不是设计一个：

```text
query_database(sql)
```

让 LLM 自己生成 SQL。

这样做可以减少：

* SQL 注入风险
* 错误 SQL
* 越权查询
* 删除或修改数据
* LLM 幻觉导致的数据操作

---

# 6. Tool统一返回结构

所有 Tool 使用统一返回格式：

```python
{
    "success": True,
    "data": {},
    "error": None
}
```

失败时：

```python
{
    "success": False,
    "data": None,
    "error": "错误信息"
}
```

例如订单不存在：

```python
{
    "success": False,
    "data": None,
    "error": "订单不存在"
}
```

统一返回结构以后，主程序不需要针对每个 Tool 编写完全不同的异常判断。

可以统一按照：

```python
result["success"]
result["data"]
result["error"]
```

进行处理。

---

# 7. Tool Registry

项目通过 Tool Registry 统一管理可以被调用的 Tool。

概念上类似：

```python
TOOL_REGISTRY = {
    "get_order": get_order,
    "get_user": get_user,
    "get_payment": get_payment,
    "get_refund": get_refund
}
```

LLM 返回：

```text
get_order
```

程序再通过 Registry 找到：

```python
get_order
```

对应的 Python 函数。

优点：

* Tool 集中管理
* 方便增加新 Tool
* 避免大量 if / elif
* 可以实现 Tool 白名单
* Dispatcher 与具体业务代码解耦

---

# 8. Tool Dispatcher

Dispatcher 负责：

```text
LLM返回Tool名称
        ↓
检查Tool是否存在
        ↓
检查是否在白名单
        ↓
获取Tool函数
        ↓
传入参数
        ↓
执行Tool
        ↓
返回执行结果
```

LLM 只负责：

```text
决定调用哪个Tool
```

真正是否允许执行，由程序控制。

---

# 9. 单次Tool Calling流程

简单问题例如：

```text
A1002订单状态是什么？
```

流程：

```text
用户
 ↓
LLM
 ↓
get_order
 ↓
MySQL
 ↓
Tool Result
 ↓
LLM
 ↓
最终回答
```

这个过程形成一个完整闭环：

```text
LLM → Tool → LLM
```

---

# 10. 多Tool连续调用

复杂问题例如：

```text
A1002为什么退款失败？
```

单独查询退款表可能无法判断完整原因。

LLM 可以按照实际需要连续调用：

```text
get_order
    ↓
get_payment
    ↓
get_refund
```

再结合数据分析：

```text
订单状态
+
支付状态
+
退款状态
```

最终给出退款失败原因。

完整流程类似：

```text
用户
 ↓
LLM
 ↓
Tool 1
 ↓
LLM
 ↓
Tool 2
 ↓
LLM
 ↓
Tool 3
 ↓
LLM
 ↓
最终回答
```

这已经具备了最基础的 Agent 行为。

LLM 不只是生成文字，而是在：

```text
观察
→ 决策
→ 调用工具
→ 获取结果
→ 再决策
```

---

# 11. Tool超时处理

数据库、HTTP、第三方接口等 Tool 都可能长时间没有返回。

因此项目增加 Tool Timeout。

基本思路：

```text
主线程
   ↓
线程池执行Tool
   ↓
等待指定时间
   ↓
如果执行完成
      返回结果
   ↓
如果超时
      返回Tool超时错误
```

避免某个 Tool 卡住以后整个 Agent 一直无法响应。

---

# 12. Tool异常捕获

Tool 内部统一使用异常处理：

```python
try:
    ...
except Exception as e:
    ...
finally:
    ...
```

异常不会直接导致整个 Agent 程序退出。

而是转换为标准结果：

```python
{
    "success": False,
    "data": None,
    "error": "异常信息"
}
```

之后交给 LLM 或主流程继续处理。

---

# 13. Tool调用日志

每次 Tool 调用记录：

```text
Tool名称
Tool参数
执行耗时
执行状态
错误信息
```

例如：

```text
tool=get_order
args={"order_id": "A1002"}
duration=23ms
success=True
```

日志的作用包括：

* 排查 LLM 是否选错 Tool
* 排查参数是否错误
* 查找慢 Tool
* 查看 Tool 异常
* 分析 Agent 实际执行路径

在真实 Agent 系统中，可观测性非常重要。

---

# 14. Tool白名单

LLM 返回的 Tool 名称不能直接执行。

程序只允许执行已经注册并授权的 Tool。

例如：

```python
ALLOWED_TOOLS = {
    "get_order",
    "get_user",
    "get_payment",
    "get_refund"
}
```

如果 LLM 请求：

```text
delete_order
```

但该 Tool 没有授权，则程序拒绝执行。

基本原则：

```text
LLM负责提出调用请求
程序负责决定是否允许执行
```

不能完全信任 LLM 输出。

---

# 15. 禁止任意SQL

当前项目不向 LLM 提供：

```python
execute_sql(sql)
```

这样的 Tool。

例如用户输入：

```sql
SELECT * FROM users
```

或者：

```sql
DELETE FROM orders
```

LLM 都不能直接执行。

数据库操作必须通过：

```text
get_order
get_user
get_payment
get_refund
```

等预定义 Tool 完成。

这也是 Agent 系统中的一个基础 Guardrail。

---

# 16. 退款失败分析示例

用户输入：

```text
A1002为什么退款失败？
```

LLM 首先可能调用：

```text
get_order
```

获得：

```text
订单状态
订单金额
```

然后调用：

```text
get_payment
```

获得：

```text
支付状态
支付金额
支付方式
```

然后调用：

```text
get_refund
```

获得：

```text
退款状态
退款金额
退款失败原因
```

最后由 LLM 综合分析。

这与普通 SQL 查询不同。

普通程序通常是：

```text
程序员提前规定查询顺序
```

当前 Agent 则开始具备：

```text
LLM根据问题决定下一步查询什么
```

的能力。

---

# 17. 阶段验收

本阶段使用 10 个问题进行 Tool Calling 验收。

测试内容包括：

### 1. 单订单查询

```text
A1002订单状态是什么？
```

验证：

```text
get_order
```

是否正确调用。

---

### 2. 支付查询

```text
A1002支付成功了吗？
```

验证：

```text
get_payment
```

是否正确调用。

---

### 3. 退款查询

```text
A1002退款状态是什么？
```

验证：

```text
get_refund
```

是否正确调用。

---

### 4. 用户相关查询

验证：

```text
get_order
+
get_user
```

之间的数据关联和 Tool 选择能力。

---

### 5. 退款失败分析

```text
A1002为什么退款失败？
```

验证多 Tool 连续调用。

---

### 6. 支付与退款联合分析

验证 LLM 是否能够根据问题选择：

```text
get_payment
+
get_refund
```

而不是无脑调用所有 Tool。

---

### 7. 不存在订单

例如：

```text
A9999为什么退款失败？
```

验证：

* Tool 失败返回
* 异常流程
* 无效数据处理
* 是否避免无意义的后续 Tool 调用

---

### 8. 未授权操作

例如要求删除订单。

验证 Tool 白名单是否能够阻止未授权 Tool。

---

### 9. 任意SQL

例如：

```text
执行 SELECT * FROM users
```

验证系统是否拒绝 LLM 任意访问数据库。

---

### 10. 缺少必要参数

例如：

```text
为什么退款失败？
```

没有提供订单号。

验证 LLM 是否先向用户询问：

```text
order_id
```

而不是自己编造订单号。

---

# 18. 当前Agent已经具备的能力

经过这一阶段后，系统已经可以完成：

```text
自然语言理解
        ↓
Tool选择
        ↓
参数生成
        ↓
Tool执行
        ↓
Tool结果反馈
        ↓
继续决策
        ↓
最终回答
```

已经不再只是：

```text
用户 → LLM → 文本
```

而是：

```text
用户
 ↓
LLM
 ↓
真实程序
 ↓
数据库
 ↓
真实数据
 ↓
LLM
 ↓
用户
```

这是从普通 LLM 应用进入 Agent 开发的重要一步。

---

# 19. 当前项目局限

目前系统仍然属于基础 Agent。

主要局限包括：

## 1. 决策较依赖Prompt

当前很多行为主要通过 System Prompt 告诉 LLM：

```text
什么时候调用Tool
什么时候停止
什么时候询问用户
```

随着 Agent 复杂度增加，只依靠 Prompt 会越来越难维护。

---

## 2. 缺少独立编排层

目前 Tool 调用流程主要由 LLM 自己决定。

还没有独立的：

```text
Workflow
State Machine
Agent Orchestrator
```

负责严格控制业务流程。

---

## 3. Guardrail仍然比较基础

目前已经有：

```text
Tool白名单
禁止任意SQL
```

但完整 Agent 系统还可能需要：

* 参数校验
* 权限控制
* 敏感操作确认
* Tool 调用次数限制
* 最大循环次数
* 输出检查
* Prompt Injection 防护
* 用户权限隔离

---

## 4. 尚未接入RAG

当前知识主要来自：

```text
LLM自身知识
+
数据库Tool
```

还没有接入：

```text
Embedding
Vector Database
RAG
```

因此暂时无法让 Agent 基于大量企业文档进行知识检索。

---

## 5. 对话状态较简单

目前主要处理当前问题以及基础 History。

后续还可以继续学习：

```text
短期Memory
长期Memory
Session State
Agent State
```

---

## 6. Tool数量较少

真实业务 Agent 可能有几十甚至上百个 Tool。

当 Tool 数量增加后，需要进一步解决：

* Tool 分类
* Tool 路由
* Tool 权限
* Tool 描述质量
* Tool 选择准确率
* Tool 编排

---

# 20. 后续学习方向

完成本阶段后，可以继续学习更完整的 Agent 技术。

后续方向包括：

```text
Agent Loop
        ↓
Agent状态管理
        ↓
Workflow / 编排
        ↓
Guardrail
        ↓
RAG
        ↓
Embedding
        ↓
Vector Database
        ↓
企业知识库
        ↓
更完整的Agent项目
```

当前退款分析助手可以继续保留。

后续每学习一个新的 Agent 能力，都可以逐步升级这个项目，而不需要重新开发一个完全新的 Demo。

---

# 21. 本阶段总结

本阶段最重要的不是完成了几个 Python 函数，而是理解了一个 Agent 的基础执行模型：

```text
LLM不是程序本身。
```

LLM主要负责：

```text
理解
+
判断
+
决策
```

Tool负责：

```text
真正执行操作
```

程序负责：

```text
控制
+
安全
+
调度
+
异常处理
```

最终形成：

```text
LLM
+
Tool
+
业务代码
+
数据库
+
安全控制
```

这就是当前退款分析 Agent 的基础架构。

---

## 当前阶段状态

```text
[✓] LLM API

[✓] Structured Output

[✓] 多轮对话

[✓] Tool Calling

[✓] 单Tool闭环

[✓] 多Tool调用

[✓] Tool统一结构

[✓] Registry / Dispatcher

[✓] Timeout

[✓] Exception Handling

[✓] Logging

[✓] Tool白名单

[✓] 禁止任意SQL

[✓] 退款失败分析助手

[✓] 10题阶段验收

[✓] README整理
```

**当前 Tool Calling 阶段完成。**
