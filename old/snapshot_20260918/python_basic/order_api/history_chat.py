import os
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    timeout=30
)


system_message = {
    "role": "system",
    "content": "你是一个编程学习助手，回答简洁清楚，优先使用Java类比解释Python。"
}


history = []

MAX_ROUNDS = 3


while True:

    question = input("你：")

    if question == "exit":
        break


    history.append({
        "role": "user",
        "content": question
    })


    messages = [system_message] + history


    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        max_tokens=500,
        temperature=0
    )


    answer = response.choices[0].message.content


    print("AI：", answer)


    history.append({
        "role": "assistant",
        "content": answer
    })


    if len(history) > MAX_ROUNDS * 2:
        history = history[-MAX_ROUNDS * 2:]