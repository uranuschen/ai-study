import os
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel,ValidationError


# 读取配置
load_dotenv()


# 格式化
class City(BaseModel):
    city:str
    population:int
    province:str

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    timeout=30
)


print("开始调用LLM")
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
         {
            "role": "system",
            "content": "你是一个只返回合法 JSON 的助手。"
        },
        {
            "role":"user",
             "content":
"""
返回上海城市信息。

字段：
city
population
province

population 必须是整数。
"""
        }
    ],
    response_format={
        "type": "json_object"
    },
    max_tokens=500,
    temperature=0
)
print("调用完成")
text = response.choices[0].message.content
print(text)

city=City.model_validate_json(text)

print(city.city)
print(city.population)
print(city.province)


# print("总token:", response.usage.total_tokens)
# print("输入token:", response.usage.prompt_tokens)
# print("输出token:", response.usage.completion_tokens)

