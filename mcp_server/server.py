# 将业务结果字典转换成模型可以读取的 JSON 文字。
import json
# 导入固定版本 SDK 提供的 Server 类。
from mcp.server import MCPServer
# 使用 SDK 的结果对象，明确设置文字、结构化数据和失败标记。
from mcp.types import CallToolResult, TextContent
# 同名业务函数取别名，避免与下方 MCP 工具重名；实际仍是原函数。
from agent_learning.business.tools import get_order as query_order


# 可信租户由 Server 提供，客户端和模型不能通过工具参数更换。
TENANT_ID = "acme"


# 创建 Server；这里只注册工具，导入本文件时还没有启动 HTTP 服务。
mcp: MCPServer = MCPServer("第72课 MCP Server", version="1.0.0", log_level="CRITICAL")


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


# tools/call 参数示例：{"name": "get_order", "arguments": {"order_id": "A1002"}}
# 工具描述说明用途、参数含义和边界，便于模型正确选择。
@mcp.tool(description="按订单号只读查询当前租户的订单状态、金额和更新时间。order_id 是订单编号，例如 A1002。数据来自本地 JSON 样例。不用于查询支付、退款记录或取消订单；租户由 Server 固定提供。")
# 只有 order_id 是对外参数，租户和文件路径都不出现在 inputSchema 中。
def get_order(order_id: str) -> CallToolResult:
    # 复用 business/tools.py 的同一个函数，保留 success/data/error 返回值。
    result = query_order(order_id, TENANT_ID)
    # content 中放业务结果的 JSON 文字，ensure_ascii=False 保留中文。
    text = json.dumps(result, ensure_ascii=False)
    # 把同一份业务结果映射为 MCP 结果，不把业务失败误报成成功。
    return CallToolResult(
        # content 是文字内容列表，供模型读取。
        content=[TextContent(type="text", text=text)],
        # structured_content 是 SDK 2.x 的 Python 字段，协议 JSON 名为 structuredContent。
        structured_content=result,
        # success=False 对应 is_error=True，协议 JSON 名为 isError。
        is_error=not result["success"],
    )
