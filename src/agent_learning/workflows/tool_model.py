# 导入已有的兼容模型客户端，沿用阶段 3 的调用方式。
from openai import OpenAI


# 类职责：调用支持 Tool Calling 的模型，并返回普通 assistant 消息字典。
class CompatibleToolModel:
    # 方法功能：保存配置，创建对象时不会访问模型。
    def __init__(self, settings):
        # 配置只保存在对象中，不放进 State 或打印出来。
        self.settings = settings
        # 第 66 课只查看最近一次外层调用的 usage，不加入累计费用或日志系统。
        self.last_usage = {}

    #-- 复用的--
    # 方法功能：把完整消息历史和工具说明交给模型，由模型选择工具或回答。
    def chat_with_tools(self, messages: list, tools: list) -> dict:
        # 先清空旧记录，异常或接口未提供用量时不能冒充上一轮的 Token 数。
        self.last_usage = {}
        # 第 62 课显式保留原配置的超时和返回格式，只取 assistant 消息。
        response = self.request_with_tools(messages, tools, timeout=self.settings.llm_timeout)
        # request_with_tools 已取得 usage；只保存供 Console 观察，不改变返回消息协议。
        self.last_usage = response["usage"]
        # 空响应或生成被截断时，不能当成一次完整的模型决策。
        if response["finish_reason"] not in ("stop", "tool_calls"):
            # 模型节点会受控结束，已取得的业务结果仍保留。
            raise ValueError("模型没有返回完整回答或完整工具调用。")
        # 不把 usage 混进下一轮发给模型的消息中。
        return response["message"]

    # 方法功能：第 63 课同时取得消息和用量，并由工作流指定本次超时与输出上限。
    def request_with_tools(self, messages: list, tools: list, timeout=None, max_tokens: int = 1200) -> dict:
        # 缺少凭证时直接报错，交给模型节点生成结束说明。
        if not self.settings.llm_api_key:
            # 提示配置项名称，不包含凭证内容。
            raise ValueError("请设置 LLM_API_KEY 或 DEEPSEEK_API_KEY")
        # timeout=None 明确关闭 SDK 超时；重试仍由工作流计数，不使用 SDK 自动重试。
        with OpenAI(api_key=self.settings.llm_api_key, base_url=self.settings.llm_base_url, timeout=timeout, max_retries=0) as client:
            # auto 表示模型可以请求工具，也可以直接给出回答。
            response = client.chat.completions.create(model=self.settings.llm_model, messages=messages, tools=tools, tool_choice="auto", temperature=0, max_tokens=max_tokens)
        # 完整响应中的 usage 与消息分开保存，便于预算统计。
        usage = response.usage.model_dump(exclude_none=True) if response.usage is not None else {}
        # 空候选或截断也返回用量，让恢复流程能先记账再结束。
        if not response.choices or response.choices[0].finish_reason not in ("stop", "tool_calls"):
            # 不伪造模型回答，也不执行半截工具参数。
            return {"message": {}, "usage": usage, "finish_reason": response.choices[0].finish_reason if response.choices else "empty"}
        # 将 SDK 消息对象转换成阶段 3 熟悉的普通字典。
        raw_message = response.choices[0].message.model_dump(exclude_none=True)
        # 只保留下一轮请求需要的消息字段。
        message = {"role": "assistant", "content": raw_message.get("content", "")}
        # 模型选择工具时，将完整的调用 ID、名称和参数带回工作流。
        if raw_message.get("tool_calls"):
            # 一轮可以包含多个工具调用，交给 tools 节点依次执行。
            message["tool_calls"] = raw_message["tool_calls"]
        # 部分兼容模型要求下一轮原样携带这个协议字段。
        if "reasoning_content" in raw_message:
            # 仅供接口回传，不作为业务结果或 Console 回答展示。
            message["reasoning_content"] = raw_message["reasoning_content"]
        # 此时尚未执行业务 Tool；usage 不是 assistant 消息的一部分。
        return {"message": message, "usage": usage, "finish_reason": response.choices[0].finish_reason}
