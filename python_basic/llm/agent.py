from chat_memory import ChatMemory
from llm_client import LLMClient


class Agent:

    def __init__(self):

        self.memory = ChatMemory(max_rounds=3)

        self.llm = LLMClient()

        self.system_message = {
            "role": "system",
            "content": "你是一个编程学习助手，回答简洁清楚。"
        }


    def run(self, question):

        # 1. 保存用户问题
        self.memory.add_user_message(question)

        # 2. 组装上下文
        messages = self.memory.build_messages(
            self.system_message
        )

        # 3. 调用LLM
        answer = self.llm.chat(messages)

        # 4. 保存AI回答
        self.memory.add_assistant_message(answer)

        # 5. 判断是否需要摘要
        if self.memory.need_summary():

            old_history = self.memory.get_old_history()

            new_summary = self.llm.summarize(
                self.memory.summary,
                old_history
            )

            self.memory.set_summary(new_summary)

            self.memory.keep_recent_history()

        return answer