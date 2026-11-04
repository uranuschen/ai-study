# 第 71 课：用普通字典理解 MCP，本文件没有真实的模型请求或 MCP 通信。
# MCP 相关字典只展示关键字段，完整消息和连接由第 72 课的 SDK 处理。

# 用标准库把 JSON 字符串转成字典，并把示例字典打印出来。
import json


# 普通 Python 函数；以后作为 Tool 暴露时，实际执行的仍是这个函数。
def hello(name: str) -> str:
    # 按传入的名字生成回答。
    return f"你好，{name}！"


# 按直接调用、工具发现、模型选择、工具执行的顺序演示。
def main() -> None:
    # 单一内部调用方可以直接调用函数。
    direct_result = hello("小明")
    # 显示直接调用的结果。
    print("直接函数调用：", direct_result)

    # Server 通过 tools/list 提供工具说明；这里示意列表中的一项。
    # 真实的 tools/list 结果还带 resultType="complete" 以及 ttlMs、cacheScope，本节只展示工具条目本身。
    tool = {
        # name 用来识别要调用的工具。
        "name": "hello",
        # description 说明何时应该使用这个工具。
        "description": "需要向指定的人打招呼时使用；name 是对方的名字。",
        # inputSchema 说明工具允许接收哪些参数。
        "inputSchema": {
            # 参数整体必须是一个对象，也就是 JSON 字典。
            "type": "object",
            # 本例只有一个字符串参数 name。
            "properties": {"name": {"type": "string"}},
            # 调用时必须提供 name。
            "required": ["name"],
            # 调用时不接受其他参数。
            "additionalProperties": False,
        },
    }

    # Client 所在的应用把 MCP 工具说明转换成项目现用的 function calling 格式。
    model_tool = {
        # 告诉模型这是一项可请求调用的函数。
        "type": "function",
        # 名称、说明和参数规则都来自刚才的工具说明。
        "function": {
            # 模型使用这个名称提出调用请求。
            "name": tool["name"],
            # 模型根据说明选择是否调用。
            "description": tool["description"],
            # MCP 的 inputSchema 对应这里的 parameters。
            "parameters": tool["inputSchema"],
        },
    }
    # 说明接下来展示的是交给模型的工具定义。
    print("交给模型的工具定义：")
    # 用缩进显示字典，便于对照两种格式。
    print(json.dumps(model_tool, ensure_ascii=False, indent=2))

    # 手动填写一份模型返回的调用示意，本课不请求 LLM。
    # 项目里真实的 tool_calls 还带 id 与 type="function"，这里只保留名称和参数。
    function_call = {"name": "hello", "arguments": '{"name": "小明"}'}
    # 模型返回的 arguments 是 JSON 字符串，先解析为普通字典。
    arguments = json.loads(function_call["arguments"])
    # Client 使用 tools/call 请求 Server；这里仅展示方法和参数字段。
    # 完整请求还需 jsonrpc 和 id，以及 2026-07-28 要求的 _meta（protocolVersion、clientCapabilities）。
    mcp_call = {
        # tools/call 表示执行一个工具。
        "method": "tools/call",
        # params 保存工具名和已经解析好的参数。
        "params": {"name": function_call["name"], "arguments": arguments},
    }
    # 明确这些字段还没有发送到真实 Server。
    print("MCP 调用字段示意：")
    # 显示与 function calling 不同的调用结构。
    print(json.dumps(mcp_call, ensure_ascii=False, indent=2))

    # 示意 Server 读取工具调用参数。
    tool_arguments = mcp_call["params"]["arguments"]
    # 本例只有 hello，示意 Server 最终执行同一个普通函数。
    result = hello(tool_arguments["name"])
    # 显示函数执行结果；真实 Client 收到结果后再把它交回模型。
    print("Server 执行函数的结果示意：", result)

    # Tools 提供可执行动作，查询也属于动作。
    print("Tools：动作，例如 hello、查询订单。")
    # Resources 提供可读取的上下文数据。
    print("Resources：数据，例如一份制度正文。")
    # Prompts 提供可复用的提示模板。
    print("Prompts：模板，例如订单诊断提示模板。")
    # 给出本课关于使用范围的结论。
    print("只有单一内部调用方时，直接函数或现有 FastAPI 就够。")


# 直接运行本文件时才开始演示。
if __name__ == "__main__":
    # 执行上面定义的演示步骤。
    main()
