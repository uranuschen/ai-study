class ChatMemory:

    def __init__(self, max_rounds=3):
        self.history = []
        self.summary = ""
        self.max_rounds = max_rounds


    def add_user_message(self, content):
        self.history.append({
            "role": "user",
            "content": content
        })


    def add_assistant_message(self, content):
        self.history.append({
            "role": "assistant",
            "content": content
        })


    def need_summary(self):

        max_messages = self.max_rounds * 2

        return len(self.history) > max_messages


    def get_old_history(self):

        max_messages = self.max_rounds * 2

        return self.history[:-max_messages]


    def keep_recent_history(self):

        max_messages = self.max_rounds * 2

        self.history = self.history[-max_messages:]


    def set_summary(self, summary):
        self.summary = summary


    def build_messages(self, system_message):

        messages = [system_message]

        if self.summary:
            messages.append({
                "role": "system",
                "content": f"历史摘要：{self.summary}"
            })

        messages += self.history

        return messages