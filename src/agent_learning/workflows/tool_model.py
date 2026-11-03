from openai import OpenAI
from agent_learning.core.config import Settings


# 调用支持 Tool Calling 的模型，只返回后续流程需要的 assistant 消息。
class CompatibleToolModel:
    # 保存配置，构造对象时不发送请求。
    def __init__(self, settings: Settings) -> None:
        # 配置不放入会话消息。
        self.settings: Settings = settings

    # 发送消息和工具说明，让模型选择工具或直接回答。
    def chat_with_tools(self, messages: list, tools: list) -> dict:
        # 缺少密钥时不发送请求。
        if not self.settings.llm_api_key:
            # 只提示配置项名称。
            raise ValueError("请配置 LLM_API_KEY 或 DEEPSEEK_API_KEY。")
        # SDK 不自行重试，由工作流统一做有限重试。
        with OpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            timeout=self.settings.llm_timeout,
            max_retries=0,
        ) as client:
            # 只请求模型，不读取或累计 usage。
            response = client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0,
                max_tokens=1200,
            )
        # 空响应不能当作正常完成。
        if not response.choices:
            # 由工作流给出业务失败说明。
            raise ValueError("模型未返回回答。")
        # 截断的响应不能执行业务工具。
        choice = response.choices[0]
        # 只接受完整回答或完整工具调用。
        if choice.finish_reason not in ("stop", "tool_calls"):
            # 不执行半截工具参数。
            raise ValueError("模型响应不完整。")
        # SDK 对象转成普通字典。
        raw = choice.message.model_dump(exclude_none=True)
        # 只保留消息协议需要的字段。
        message = {"role": "assistant", "content": raw.get("content", "")}
        # 工具调用保留原 ID，便于结果回传。
        if raw.get("tool_calls"):
            # 这部分是调用协议，不是执行日志。
            message["tool_calls"] = raw["tool_calls"]
        # 部分兼容模型要求回传这个协议字段。
        if "reasoning_content" in raw:
            # 仅在模型对话内部使用。
            message["reasoning_content"] = raw["reasoning_content"]
        # 不返回用量或费用信息。
        return message
