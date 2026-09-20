import os
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


class LLMClient:

    def __init__(self):

        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
            timeout=30
        )


    def chat(self, messages):

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=500,
            temperature=0
        )

        return response.choices[0].message.content

    def summarize(self, old_summary, history):

        messages = [
            {
                "role": "system",
                "content": "你负责压缩聊天历史。保留重要事实、用户偏好、已完成事项和当前任务，尽量简洁。"
            },
            {
                "role": "user",
                "content": f"""
    旧摘要：
    {old_summary}

    新增聊天记录：
    {history}

    请生成新的历史摘要。
    """
            }
        ]

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=300,
            temperature=0
        )

        return response.choices[0].message.content