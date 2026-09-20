import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from tools import dispatch_tool
from pydantic import BaseModel

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# json格式化
class RefundAnalysis(BaseModel):
    order_id: str
    refund_status: str
    reason: str
    suggestion: str
    risk: str

def extract_json(text: str) -> str:

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or start >= end:
        raise ValueError("LLM返回内容中没有找到有效JSON")

    return text[start:end + 1]

# 定义工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "根据订单号查询订单信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 A1002"
                    }
                },
                "required": ["order_id"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "取消订单。如果订单已发货，则无法取消",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "需要取消的订单号，例如 A1001"
                    }
                },
                "required": ["order_id"]
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "get_user",
        "description": "根据用户ID查询用户信息",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "用户ID，例如 U1001"
                }
            },
            "required": ["user_id"]
        }
    }
    },
    {
    "type": "function",
    "function": {
        "name": "get_payment",
        "description": "根据订单号查询支付信息",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号，例如 A1001"
                }
            },
            "required": ["order_id"]
        }
    }
    },
    {
    "type": "function",
    "function": {
        "name": "get_refund",
        "description": "根据订单号查询退款信息",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号，例如 A1001"
                }
            },
            "required": ["order_id"]
        }
    }
    }
]


# 获取用户输入
question = input("请输入问题：")


# 初始化上下文 提示词 prompt
messages = [
    {
        "role": "system",
    "content": """
你是一个订单业务助手，可以处理订单、支付、退款以及退款失败分析问题。

你可以调用：
- get_order
- get_payment
- get_refund
- get_user

你必须根据用户的实际问题选择必要的工具，不要调用无关工具。

工具选择规则：

1. 用户只询问订单信息：
   只调用 get_order。

2. 用户只询问支付信息：
   调用 get_payment。

3. 用户只询问退款状态或退款记录：
   调用 get_refund。

4. 用户询问退款失败原因或要求完整分析：
   可以综合调用 get_order、get_payment、get_refund。

5. 只有用户问题确实涉及用户资料时，才调用 get_user。

不要为了获取更多信息而调用与问题无关的工具。
不要重复查询已经得到的信息。
当已有信息足够回答问题时，立即停止调用工具。
只有当用户要求“分析退款失败原因”或“完整退款失败分析”时，
最终返回 RefundAnalysis JSON。

对于普通订单查询、支付查询、退款状态查询，
直接用自然语言回答，不需要返回 JSON。
不要猜测工具中不存在的数据。

如果 get_order 返回 success=false，说明订单不存在或订单查询失败。
此时不要继续调用 get_payment、get_refund 或其他订单相关工具，
直接根据 get_order 的错误信息回答用户。

"""
    },
    {
        "role": "user",
        "content": question
    }
]


# Agent循环：只要LLM还要调用工具，就继续执行
while True:

    # 调用LLM，让模型判断是否需要使用工具
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    message = response.choices[0].message


    # 如果LLM不再调用工具，说明可以直接返回最终答案
    if not message.tool_calls:
        final_content = message.content or ""

        print("LLM原始返回：", final_content)
        try:
            json_content = extract_json(
                final_content
            )

            analysis = RefundAnalysis.model_validate_json(
                json_content
            )

            print("退款分析结果：")
            print("订单号：", analysis.order_id)
            print("退款状态：", analysis.refund_status)
            print("失败原因：", analysis.reason)
            print("处理建议：", analysis.suggestion)
            print("风险等级：", analysis.risk)

        except Exception:
            print("助手回复：", final_content)

            break


    # 把LLM的工具调用请求加入上下文
    messages.append(message)


    # 处理LLM返回的所有工具调用
    for tool_call in message.tool_calls:

        tool_name = tool_call.function.name

        arguments = json.loads(
            tool_call.function.arguments
        )

        print("LLM选择工具：", tool_name)
        print("LLM生成参数：", arguments)

        # 动态调用
        result = dispatch_tool(
            tool_name,
            arguments
        )


        print("工具执行结果：", result)


        # 把工具执行结果加入上下文
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(
                    result,
                    ensure_ascii=False
                )
            }
        )