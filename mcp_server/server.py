# 导入固定版本 SDK 提供的 Server 类。
from mcp.server import MCPServer


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
