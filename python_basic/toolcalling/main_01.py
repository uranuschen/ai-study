import os
import json
from dotenv import load_dotenv
from openai import OpenAI

# 1 环境变量
load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# 2.真正执行的 Python 函数
def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


def multiply(a, b):
    return a * b

# 3. Python 工具映射表
tool_map = {
    "add": add,
    "subtract": subtract,
    "multiply": multiply
}


# 4 工具定义 告诉LLM可以调用它
# name=接口说明 description=工具是干什么的
tools = [
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "计算两个数字的加法",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "number"
                    },
                    "b": {
                        "type": "number"
                    }
                },
                "required": ["a", "b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "subtract",
            "description": "计算两个数字的减法，计算 a - b",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "number"
                    },
                    "b": {
                        "type": "number"
                    }
                },
                "required": ["a", "b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "multiply",
            "description": "计算两个数字的乘法",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "number"
                    },
                    "b": {
                        "type": "number"
                    }
                },
                "required": ["a", "b"]
            }
        }
    }
]


# 5. 用户输入
question = input("请输入问题：")

messages = [
    {
        "role": "user",
        "content": question
    }
]

# 6 第一次调用 LLM
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,
    tools=tools
)

message = response.choices[0].message


# =========================
# 7. 判断是否调用工具
# =========================
if message.tool_calls:

    # 把 assistant 的 tool_call 放入上下文
    messages.append(message)

    for tool_call in message.tool_calls:

        tool_name = tool_call.function.name

        arguments = json.loads(
            tool_call.function.arguments
        )

        print("LLM选择工具：", tool_name)
        print("LLM生成参数：", arguments)

        # =========================
        # 8. 根据名称找到真正的Python函数
        # =========================
        if tool_name not in tool_map:
            raise ValueError(
                f"不存在的工具：{tool_name}"
            )

        func = tool_map[tool_name]
         # =========================
        # 9. 真正执行工具
        # =========================
        result = func(**arguments)

        print("工具执行结果：", result)

        # =========================
        # 10. 把工具结果加入上下文
        # =========================
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            }
        )
        
 # =========================
    # 11. 第二次调用 LLM
    # =========================
    response2 = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        tools=tools
    )

    final_answer = response2.choices[0].message.content

    print("最终答案：", final_answer)

else:
    # LLM认为不需要工具
    print("最终答案：", message.content)
