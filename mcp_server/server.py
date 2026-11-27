# 导入异步上下文管理器，用于在 MCP 启动阶段校验业务数据源配置。
from contextlib import asynccontextmanager
# 将业务结果字典转换成模型可以读取的 JSON 文字。
import json
# 使用 SDK 支持的异步超时控制。
import anyio
# 协议错误使用 SDK 的异常类型。
from mcp import MCPError
# 导入固定版本 SDK 提供的 Server 类。
from mcp.server import MCPServer
# 使用 SDK 的结果对象，明确设置文字、结构化数据和失败标记。
from mcp.types import CallToolResult, INVALID_PARAMS
# SDK 在请求结构不合法时使用这个校验异常。
from pydantic import ValidationError
# 复用本课的普通校验、错误转换与只读等待函数。
from mcp_server import controls
# 同名业务函数取别名，避免与下方 MCP 工具重名；实际按 BUSINESS_DATA_SOURCE 复用双数据源函数。
from agent_learning.business.tools import (
    ORDER_NOT_FOUND_ERROR,
    PERMISSION_DENIED_ERROR,
    QUERY_TIMEOUT_ERROR,
    create_business_store,
    get_order as query_order,
    get_payment as query_payment,
    get_refund as query_refund,
)


# 可信租户由 Server 提供，客户端和模型不能通过工具参数更换。
TENANT_ID = "acme"
# 支付和退款每次最多返回 10 条，由 Server 固定提供。
MAX_RECORDS = 10


# 方法功能：在 MCP 服务启动阶段校验 BUSINESS_DATA_SOURCE 等配置，此处不连接数据库。
def validate_startup_config():
    # 非法 BUSINESS_DATA_SOURCE 在启动时立即抛 ValueError，与 FastAPI 行为保持一致。
    return create_business_store()


# 方法功能：MCP 应用启动生命周期，仅做配置校验，不执行建表或数据库连接。
@asynccontextmanager
async def mcp_lifespan(server: MCPServer):
    # 启动进入时立即检查业务数据源配置，防止错误配置潜伏到首次查询。
    validate_startup_config()
    # 配置有效后允许服务开始接收 MCP 请求。
    yield {}


# 创建 Server；这里只注册工具与启动生命周期，导入本文件时还不监听端口。
mcp: MCPServer = MCPServer("第72课 MCP Server", version="1.0.0", log_level="CRITICAL", lifespan=mcp_lifespan)


# tools/call 参数示例：{"name": "hello", "arguments": {}}
# 把下面的函数注册成无需参数的工具，说明会出现在 tools/list 中。
@mcp.tool(description="检查 MCP 工具能否正常调用，无需参数。")
# 声明普通 Python 函数，str 表示返回文字。
def hello() -> str:
    # SDK 会把返回文字转换成 MCP 工具结果。
    return "你好，MCP！"


# tools/call 参数示例：{"name": "greet", "arguments": {"name": "小明"}}
# 把下面的函数注册成带参数的工具。
@mcp.tool(description="向指定的人打招呼；name 是对方的名字。")
# SDK 根据 name: str 生成必填字符串参数，不需要手写 inputSchema。
def greet(name: str) -> str:
    # 通过参数生成结果，方便观察 tools/call 如何执行函数。
    return f"你好，{name}！"


# 将业务函数返回的失败结果映射为固定 MCP 错误码，不回显内部错误原文。
def map_business_error_code(result: dict, default_code: str) -> str:
    # 边界已经给出明确错误码（如 PermissionError 转成的 FORBIDDEN）时直接保留。
    if result.get("error_code"):
        # 使用已分类的固定错误代码。
        return result["error_code"]
    # 读取业务层生成的固定提示文案，用于区分权限拒绝、超时与业务缺失。
    error_message = result.get("error")
    # 数据库只读账号权限不足时返回 FORBIDDEN，不自动重试。
    if error_message == PERMISSION_DENIED_ERROR:
        # 与直接抛出 PermissionError 的权限拒绝保持同一错误码。
        return "FORBIDDEN"
    # 数据库端查询超时时返回 TOOL_TIMEOUT，不自动重试。
    if error_message == QUERY_TIMEOUT_ERROR:
        # 与 MCP 等待超时使用同一错误分类。
        return "TOOL_TIMEOUT"
    # 订单工具仅在订单不存在或跨租户不可读时返回 ORDER_UNAVAILABLE。
    if default_code == "ORDER_UNAVAILABLE":
        # 数据库连接失败或配置缺失归入 BUSINESS_ERROR，避免误报成订单不存在。
        if error_message == ORDER_NOT_FOUND_ERROR:
            # 保持不存在与跨租户不可读的统一对外提示。
            return "ORDER_UNAVAILABLE"
        # 其他数据源错误走通用业务查询失败。
        return "BUSINESS_ERROR"
    # 支付与退款查询失败统一使用默认业务错误码。
    return default_code


# tools/call 参数示例：{"name": "get_order", "arguments": {"order_id": "A1002"}}
# 工具描述说明用途、参数含义和边界，便于模型正确选择。
@mcp.tool(description="按订单号只读查询当前租户的订单状态、金额和更新时间。order_id 是订单编号，例如 A1002。数据来源由服务端 BUSINESS_DATA_SOURCE（json 或只读 postgres）配置决定，结果中的 source 会标明来源。不用于查询支付、退款记录或取消订单；租户由 Server 固定提供。")
# 只有 order_id 是对外参数，租户、文件路径和数据库连接都不出现在 inputSchema 中。
async def get_order(order_id: str) -> CallToolResult:
    # 复用 business/tools.py 的同一个函数，按配置支持 JSON 与只读 PostgreSQL。
    result = await controls.read_query(query_order, order_id, TENANT_ID)
    # 区分订单不可读、权限拒绝、超时与数据源异常，均不回显内部原文。
    if not result["success"]:
        # 转换为固定错误表中的错误代码和文字。
        return controls.error_result(map_business_error_code(result, "ORDER_UNAVAILABLE"))
    # 业务成功结果保留原字段。
    return controls.make_result(result)


# 支付与退款共用列表截断和 MCP 结果转换，避免重复编写。
def records_to_mcp(result: dict) -> CallToolResult:
    # 查询失败不伪造空列表，也不回显原始错误文字。
    if not result["success"]:
        # 明确权限拒绝保留 FORBIDDEN，超时保留 TOOL_TIMEOUT，其余业务失败使用固定说明。
        return controls.error_result(map_business_error_code(result, "BUSINESS_ERROR"))
    # 复制外层字典，不改写业务函数返回的原结果。
    current = dict(result)
    # 业务函数已经按可信租户过滤，这里只读取当前租户的记录。
    records = current["data"]
    # 保留原顺序和记录字段，空列表切片后仍是空列表。
    current["data"] = records[:MAX_RECORDS]
    # 数量超过上限才算截断，恰好等于上限仍是完整结果。
    current["truncated"] = len(records) > MAX_RECORDS
    # 截断时给模型和调用方明确的文字提示。
    if current["truncated"]:
        # 提醒这些记录只是部分结果，不能当成完整列表或完整金额汇总。
        current["notice"] = f"仅返回前 {MAX_RECORDS} 条，结果已截断；不能据此判断全部记录或汇总金额。"
    # 文字与结构化数据使用同一份结果，空列表仍然表示成功。
    return controls.make_result(current)


# tools/call 参数示例：{"name": "get_payment", "arguments": {"order_id": "A1002"}}
# 说明查询用途、参数和列表语义，避免被理解为执行支付。
@mcp.tool(description=f"按订单号只读查询当前租户的支付记录。order_id 是订单编号，例如 A1002。返回列表，空列表表示查询成功但无可读支付记录。最多返回 {MAX_RECORDS} 条，超出会标明截断。数据来源由服务端配置决定（json 或只读 postgres），结果中的 source 会标明来源；不执行支付或退款，租户由 Server 提供。")
# 对外仍然只接收订单号，不开放租户、条数或数据源参数。
async def get_payment(order_id: str) -> CallToolResult:
    # 原函数按配置查询当前租户的全部匹配支付记录。
    result = await controls.read_query(query_payment, order_id, TENANT_ID)
    # 统一限制返回条数，并转换成 MCP 结果。
    return records_to_mcp(result)


# tools/call 参数示例：{"name": "get_refund", "arguments": {"order_id": "A1002"}}
# 说明只查询退款记录，不会发起退款。
@mcp.tool(description=f"按订单号只读查询当前租户的退款记录。order_id 是订单编号，例如 A1002。返回列表，空列表表示查询成功但无可读退款记录。最多返回 {MAX_RECORDS} 条，超出会标明截断。数据来源由服务端配置决定（json 或只读 postgres），结果中的 source 会标明来源；不发起退款或取消订单，租户由 Server 提供。")
# 与支付工具使用相同的参数约定。
async def get_refund(order_id: str) -> CallToolResult:
    # 原函数按配置查询当前租户的全部匹配退款记录。
    result = await controls.read_query(query_refund, order_id, TENANT_ID)
    # 复用同一个列表转换函数。
    return records_to_mcp(result)


# SDK 在收到消息后先进入这里；不自行实现 HTTP 或 JSON-RPC 解析。
async def guard_request(ctx, call_next):
    # 请求结构和协议错误使用固定文案，工具错误使用固定业务结果。
    try:
        # 工具发现仍由 SDK 生成，只补充本课的参数约束。
        if ctx.method == "tools/list":
            # 取得 SDK 生成的协议字典。
            result = await call_next(ctx)
            # 每个工具都公开相同的额外字段策略。
            for tool in result["tools"]:
                # 不允许未声明的参数。
                tool["inputSchema"]["additionalProperties"] = False
                # 本课所有参数都是短字符串。
                for rule in tool["inputSchema"].get("properties", {}).values():
                    # 参数的长度约束与实际校验一致。
                    rule.update({"minLength": 1, "maxLength": controls.MAX_ARGUMENT_CHARS})
            # 返回原工具列表，不改变注册方式。
            return result
        # 其他协议方法仍由 SDK 处理。
        if ctx.method != "tools/call":
            # 未知方法的协议异常会由下面统一处理。
            return await call_next(ctx)
        # ctx.params 是 SDK 提供的原始方法参数。
        params = ctx.params
        # 请求结构无效时交回 SDK 校验，避免误判为业务失败。
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            # SDK 负责必需的协议结构校验。
            return await call_next(ctx)
        # 省略或 null arguments 都按没有工具参数处理。
        arguments = params.get("arguments")
        # 缺少参数时使用空字典，随后仍检查必填字段。
        if arguments is None:
            # 不默认补入业务字段。
            arguments = {}
        # arguments 整体必须是对象。
        if not isinstance(arguments, dict):
            # 这是调用请求结构错误，不是对象内字段类型错误。
            raise MCPError(code=INVALID_PARAMS, message="请求结构无效。")
        # 从 SDK 的注册结果查找工具，避免另写工具名配置表。
        schema = None
        # SDK 的普通方法调用不会再次进入消息中间件。
        for tool in await mcp.list_tools():
            # 找到本次调用的参数定义。
            if tool.name == params["name"]:
                # 使用库已经生成的 schema。
                schema = tool.input_schema
                # 找到后不再继续查找。
                break
        # SDK 默认把未知工具当成工具失败，本课明确归为协议错误。
        if schema is None:
            # 不回显客户端提交的工具名称。
            raise MCPError(code=INVALID_PARAMS, message="工具不存在。")
        # 对象内的必填、类型、额外字段属于工具参数校验。
        if not controls.valid_arguments(arguments, schema):
            # 中间件返回的是协议字典，使用 SDK 的公开序列化方法。
            return controls.error_result("INVALID_ARGUMENT").model_dump(mode="json", by_alias=True, exclude_none=True)
        # 限制等待时间，不记录耗时或调用日志。
        try:
            # 三个只读工具使用可取消等待的线程调用。
            with anyio.fail_after(controls.TOOL_TIMEOUT_SECONDS):
                # 执行 SDK 校验和真正的工具函数。
                result = await call_next(ctx)
        # 超时只结束等待，不强制终止底层只读线程。
        except TimeoutError:
            # 返回固定错误，客户端不能自动重试。
            return controls.error_result("TOOL_TIMEOUT").model_dump(mode="json", by_alias=True, exclude_none=True)
        # SDK 或工具返回的任意失败都必须通过固定错误表。
        if result.get("isError"):
            # 本项目工具的错误代码位于结构化结果中。
            data = result.get("structuredContent")
            # SDK 的普通工具错误可能没有结构化数据。
            code = data.get("error_code") if isinstance(data, dict) else "TOOL_ERROR"
            # 不转发 SDK 错误里的输入值或自定义异常文字。
            result = controls.error_result(code).model_dump(mode="json", by_alias=True, exclude_none=True)
        # 同时计算两份内容，按当前 HTTP 编码方式计入中文转义后的字节。
        size = len(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
        # 超限时返回一个小的固定错误，不截断 JSON 字符串。
        if size > controls.MAX_RESULT_BYTES:
            # 避免把不完整结果当作完整回答。
            return controls.error_result("RESULT_TOO_LARGE").model_dump(mode="json", by_alias=True, exclude_none=True)
        # 返回已经通过边界检查的工具结果。
        return result
    # SDK 的结构校验异常不能带着输入值直接返回。
    except ValidationError:
        # 固定错误文本，不返回校验异常详情。
        raise MCPError(code=INVALID_PARAMS, message="请求结构无效。") from None
    # 协议错误保留代码，去掉任意原文和 data。
    except MCPError as error:
        # 这里只区分方法不存在、参数无效和其他协议失败。
        message = "协议请求失败。"
        # 未知协议方法使用标准代码。
        if error.code == -32601:
            # 不把客户端提交的方法名带回响应。
            message = "协议方法不存在。"
        # 非法调用结构与未知工具都属于无效参数。
        elif error.code == INVALID_PARAMS:
            # 保留统一分类，不泄露原始参数。
            message = "请求结构无效或工具不存在。"
        # 显式不转发 error.data。
        raise MCPError(code=error.code, message=message) from None
    # 未预期错误也不输出异常原文或堆栈。
    except Exception:
        # 用标准内部错误代码结束本次协议请求。
        raise MCPError(code=-32603, message="服务处理失败。") from None


# 使用 SDK 的公开中间件入口，工具仍按原来的装饰器注册。
mcp.middleware.append(guard_request)
