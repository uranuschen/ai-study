# 调用只读业务函数时，允许超时后停止等待线程结果。
import anyio
# 把统一结果转换成 JSON 文字。
import json
# 使用 SDK 的结果对象。
from mcp.types import CallToolResult, TextContent


# 本课工具参数都是短字符串，由 Server 固定上限。
MAX_ARGUMENT_CHARS = 256
# 单次工具最多等待 5 秒，不统计实际耗时。
TOOL_TIMEOUT_SECONDS = 5
# 限制序列化后的 Tool 结果，包含文字和结构化数据两份内容。
MAX_RESULT_BYTES = 16 * 1024
# 错误文字只从固定表中选择，不回显异常、SQL 或文件路径。
ERROR_MESSAGES = {
    "INVALID_ARGUMENT": "工具参数无效，请检查必填项、字符串类型、长度和额外字段。",
    "ORDER_UNAVAILABLE": "订单不存在或不可读取。",
    "BUSINESS_ERROR": "业务查询失败，请检查输入或数据源。",
    "FORBIDDEN": "无权执行此查询，请联系管理员。",
    "TOOL_TIMEOUT": "工具调用超时，本次未自动重试。",
    "RESULT_TOO_LARGE": "工具结果超过大小限制，请缩小查询范围。",
    "TOOL_ERROR": "工具执行失败，请检查服务配置。",
}


# 成功与失败都使用同一个 MCP 结果转换函数。
def make_result(data: dict) -> CallToolResult:
    # 文字和结构化结果来自同一个字典。
    text = json.dumps(data, ensure_ascii=False)
    # success 决定工具是否失败，空列表本身不表示失败。
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=data,
        is_error=not data["success"],
    )


# 只返回固定错误代码与文字，所有本课错误都不自动重试。
def error_result(code: str) -> CallToolResult:
    # 未知内部错误也不能把原始内容带给客户端。
    if not isinstance(code, str) or code not in ERROR_MESSAGES:
        # 使用通用执行失败说明。
        code = "TOOL_ERROR"
    # retryable 是本项目的处理约定，不是 MCP 自带的重试开关。
    return make_result({
        "success": False,
        "data": None,
        "error": ERROR_MESSAGES[code],
        "error_code": code,
        "retryable": False,
    })


# 根据 SDK 已生成的参数说明，校验本课五个工具的字符串参数。
def valid_arguments(arguments: dict, schema: dict) -> bool:
    # arguments是接口入参里arguments的参数，schema是方法说明注册的时就有的，前面根据传入的入参来判断的。比较方法内和外部是否一致
    if set(arguments) - set(schema.get("properties", {})):
        # 额外字段直接拒绝，不默默忽略。
        return False
    # 检查每个必填字段。
    for name in schema.get("required", []):
        # 缺少字段就不进入工具函数。
        if name not in arguments:
            # 由调用入口返回统一参数错误。
            return False
    # 本课所有已注册参数都是字符串，先精确校验，避免 SDK 类型转换。
    for value in arguments.values():
        # 空白、错误类型和过长输入都不接受。
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_ARGUMENT_CHARS:
            # 错误中不回显输入值。
            return False
    # 无参数的 hello 传空字典也会通过。
    return True


# 业务包装使用异步等待，避免 SDK 同步工具的线程调用屏蔽超时取消。
async def read_query(query, order_id: str, tenant_id: str) -> dict:
    # 错误仅在边界转换，不改变原来的只读查询函数。
    try:
        # 超时取消后不再等待线程；底层只读函数仍可能继续完成。
        return await anyio.to_thread.run_sync(query, order_id, tenant_id, abandon_on_cancel=True)
    # 权限拒绝有明确代码，客户端不能自动重试。
    except PermissionError:
        # 不把权限异常中的路径或其他内部信息返回。
        return {"success": False, "error_code": "FORBIDDEN"}
    # 未预期异常统一隐藏原文。
    except Exception:
        # 由工具包装生成固定错误结果。
        return {"success": False, "error_code": "TOOL_ERROR"}


# 客户端可复用的纯函数：只分类已有响应，不建立连接或重新发送请求。
def classify_response(status_code: int | None, body: dict | None = None) -> dict:
    # 没有 HTTP 响应时，属于连接失败或客户端等待超时。
    if status_code is None:
        # 本课不进行自动重试。
        return {"layer": "http", "code": "CONNECTION_FAILED", "retryable": False}
    # 接入认证失败与工具内部的业务权限拒绝分别处理。
    if status_code in (401, 403):
        # 不通过重试尝试绕过权限。
        return {"layer": "http", "code": "HTTP_AUTH_FAILED", "retryable": False}
    # 非 2xx 也可能携带有效的 JSON-RPC 错误，先检查协议内容。
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        # 协议错误代码必须是整数，不能把任意响应文字当成代码转发。
        code = body["error"].get("code")
        # bool 在 Python 中也属于 int，需要明确排除。
        if type(code) is not int:
            # 格式不正确时停止处理。
            return {"layer": "protocol", "code": "INVALID_RESPONSE", "retryable": False}
        # 不向上层转发错误原文或 data。
        return {"layer": "protocol", "code": code, "retryable": False}
    # 其余 HTTP 失败按传输层处理。
    if status_code < 200 or status_code >= 300:
        # 只返回固定分类。
        return {"layer": "http", "code": "HTTP_FAILED", "retryable": False}
    # 成功状态也要有有效的 MCP 结果对象。
    if not isinstance(body, dict) or not isinstance(body.get("result"), dict):
        # 不把格式错误的响应当成工具成功。
        return {"layer": "protocol", "code": "INVALID_RESPONSE", "retryable": False}
    # 工具执行失败仍可能通过 HTTP 200 返回。
    result = body["result"]
    # isError 存在时必须是布尔值，不能把 0 或字符串当成成功标记。
    if "isError" in result and type(result["isError"]) is not bool:
        # 结果格式错误时停止处理。
        return {"layer": "protocol", "code": "INVALID_RESPONSE", "retryable": False}
    # 读取结构化错误代码，不依赖匹配错误文字。
    if result.get("isError"):
        # 不信任响应中的任意代码或重试建议。
        data = result.get("structuredContent")
        # 没有本项目结构化错误时使用通用代码。
        code = data.get("error_code") if isinstance(data, dict) else None
        # 只接受固定错误表中的代码。
        if not isinstance(code, str) or code not in ERROR_MESSAGES:
            # 其他工具错误同样停止本次处理。
            code = "TOOL_ERROR"
        # FORBIDDEN 与其他本课错误都不会自动重试。
        return {"layer": "tool", "code": code, "retryable": False}
    # HTTP、协议和工具三层都没有报告失败。
    return {"layer": "success", "code": "OK", "retryable": False}
