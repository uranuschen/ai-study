import json
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from langgraph.checkpoint.memory import InMemorySaver
import main_workflow_memory as main_workflow
from agent_learning.core.config import Settings
from agent_learning.core.models import SearchFilter
from agent_learning.workflows import memory_agent, rag_agent
from agent_learning.workflows.tool_model import CompatibleToolModel


# 方法功能：构造真实格式的模型工具请求。
def tool_call(name: str, call_id: str, arguments: dict) -> dict:
    # 工具参数保持 JSON 字符串，调用 ID 原样保留。
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}


# 方法功能：构造一条包含工具选择的 assistant 消息。
def request_tools(calls: list) -> dict:
    # 本轮只有工具请求，尚未给出最终文字回答。
    return {"role": "assistant", "content": "", "tool_calls": calls}


# 方法功能：构造一轮已经完成的普通对话。
def plain_turn(question: str, answer: str) -> list:
    # user 是轮次边界，assistant 是该轮回答。
    return [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]


# 类职责：用预设响应代替模型，记录实际收到的会话消息。
class ScriptedModel:
    # 方法功能：保存离线响应和最近一次模型用量。
    def __init__(self, responses: list):
        # 预设元素可以是消息或异常，不访问真实模型。
        self.responses = responses
        # 每次请求保存独立副本，避免后续 State 更新影响断言。
        self.requests = []
        # Console 可查看用量，但测试不增加预算和费用逻辑。
        self.last_usage = {}

    # 方法功能：采用真实接口，在内存中返回一条预设消息。
    def chat_with_tools(self, messages: list, tools: list) -> dict:
        # 新调用先清空旧用量，失败不能冒充上一轮成功。
        self.last_usage = {}
        # 记录真实节点传入的上下文和工具定义。
        self.requests.append({"messages": deepcopy(messages), "tools": deepcopy(tools)})
        # 多余调用会越界，帮助发现不应发生的重试。
        response = self.responses[len(self.requests) - 1]
        # 模拟模型异常，交给实际节点生成受控结束。
        if isinstance(response, Exception):
            # 不在替身中吞掉异常或执行恢复。
            raise response
        # 用确定性的计数表达上下文越长，输入用量通常越大。
        prompt_tokens = len(json.dumps(messages, ensure_ascii=False))
        # 此处只供 Console 观察，不代表真实模型分词算法。
        self.last_usage = {"prompt_tokens": prompt_tokens, "completion_tokens": 10, "total_tokens": prompt_tokens + 10}
        # 避免生产节点修改预设响应。
        return deepcopy(response)


# 类职责：检查历史保留、会话隔离、整轮裁剪和上下文预算。
class MemoryAgentTests(unittest.TestCase):
    # 方法功能：建立纯内存知识库和可信过滤，不读取环境或数据库。
    def setUp(self):
        # 本课与上一课使用同一个可信租户和规则资料范围。
        self.filters = SearchFilter(tenant_id="acme", max_security_level=1, doc_type="policy")
        # 使用纯内存 RAG 替身，禁止真实检索或加载模型。
        self.pipeline = Mock()
        # 保存完整来源，验证多轮历史不会破坏原引用。
        self.citations = [{"number": 1, "source": "rules/refund.md", "excerpt": "退款规则原文"}]
        # RAG 包装会保留答案、状态、引用，删除内部 trace。
        self.pipeline.ask.return_value = {"answer": "退款规则见 [1]。", "citations": self.citations, "status": "answered", "trace": {}}
        # 每个测试使用自己的逻辑会话编号。
        self.config = {"configurable": {"thread_id": "memory-test"}}
        # 普通输入只提交问题和可信租户，不重置 messages。
        self.initial = {"question": "查 A1002 的退款", "tenant_id": "acme"}
        # 普通系统消息用于直接测试裁剪算法。
        self.system = {"role": "system", "content": "测试规则"}

    # 方法功能：同一会话追问时，模型看到之前的问题和回答。
    def test_same_thread_keeps_messages_for_follow_up(self):
        # 连续两轮直接回答，测试无需业务或 RAG 查询。
        model = ScriptedModel([{"role": "assistant", "content": "A1002 退款记录已说明。"}, {"role": "assistant", "content": "它指的是上一轮的 A1002。"}])
        # 使用真实图和真实内存 Checkpoint。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 第一轮建立会话内容。
        graph.invoke(self.initial, self.config)
        # 记录第一轮替身用量，便于观察上下文增长。
        first_prompt_tokens = model.last_usage["prompt_tokens"]
        # 新问题只传两项，不把消息历史重新设为空。
        result = graph.invoke({"question": "它还在处理中吗？", "tenant_id": "acme"}, self.config)
        # 第二次请求保留首轮问题、回答和新问题。
        self.assertEqual([item["role"] for item in model.requests[1]["messages"]], ["system", "user", "assistant", "user"])
        # 追问所指的历史业务编号仍可见。
        self.assertEqual(model.requests[1]["messages"][1]["content"], self.initial["question"])
        # 本轮回答更新 answer，不沿用上一轮结束状态。
        self.assertEqual((result["answer"], result["stop_reason"]), ("它指的是上一轮的 A1002。", "final_answer"))
        # 同会话只存在一条 system 规则。
        self.assertEqual(sum(item["role"] == "system" for item in result["messages"]), 1)
        # 保留历史后输入用量增长；此计数只用于确定性的离线观察。
        self.assertGreater(model.last_usage["prompt_tokens"], first_prompt_tokens)
        # 仍沿用上一课七个核心 State 字段。
        self.assertEqual(set(result), {"question", "tenant_id", "messages", "pending_tool_calls", "tool_results", "stop_reason", "answer"})

    # 方法功能：不同 thread_id 不共享消息，即使使用同一张图。
    def test_thread_ids_isolate_conversation_history(self):
        # 预设两个会话的首轮，以及第一会话的追问。
        model = ScriptedModel([{"role": "assistant", "content": "会话一。"}, {"role": "assistant", "content": "会话二。"}, {"role": "assistant", "content": "会话一追问。"}])
        # 使用一个存档对象，通过 thread_id 区分内容。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 第二会话使用独立编号。
        other_config = {"configurable": {"thread_id": "memory-other"}}
        # 第一会话查询 A1002。
        graph.invoke(self.initial, self.config)
        # 第二会话查询另一个编号。
        graph.invoke({"question": "查 A1001", "tenant_id": "acme"}, other_config)
        # 第二会话首轮只有自己的输入。
        self.assertEqual([item["content"] for item in model.requests[1]["messages"] if item["role"] == "user"], ["查 A1001"])
        # 第一会话使用相同配置值的新字典继续追问。
        graph.invoke({"question": "它呢？", "tenant_id": "acme"}, {"configurable": {"thread_id": "memory-test"}})
        # 通过配置值查存档，不要求是同一个 Python 字典对象。
        self.assertEqual([item["content"] for item in model.requests[2]["messages"] if item["role"] == "user"], [self.initial["question"], "它呢？"])
        # 第一会话追问不会修改第二会话 State。
        self.assertEqual(graph.get_state(other_config).values["answer"], "会话二。")

    # 方法功能：会话内容由 Checkpointer 保存，换内存存档器后不能凭编号恢复。
    def test_new_saver_does_not_recover_old_conversation(self):
        # 第一张图完成一轮并保存消息。
        first_model = ScriptedModel([{"role": "assistant", "content": "已有会话。"}])
        # 使用第一个内存存档对象。
        first_graph = memory_agent.build_graph(first_model, self.pipeline, self.filters, InMemorySaver())
        # 保存原始会话编号下的 State。
        first_graph.invoke(self.initial, self.config)
        # 第二张图使用全新的内存存档对象。
        second_model = ScriptedModel([{"role": "assistant", "content": "新会话回答。"}])
        # thread_id 相同，也不会跨存档器自动继承消息。
        second_graph = memory_agent.build_graph(second_model, self.pipeline, self.filters, InMemorySaver())
        # 新存档对象最开始没有旧 State。
        self.assertEqual(second_graph.get_state(self.config).values, {})
        # 以同编号提交新问题只能开始新的对话内容。
        second_graph.invoke({"question": "它是什么？", "tenant_id": "acme"}, self.config)
        # 第二张图的模型只看到本次问题。
        self.assertEqual([item["content"] for item in second_model.requests[0]["messages"] if item["role"] == "user"], ["它是什么？"])

    # 方法功能：新输入清空本轮结束字段，但保留上一轮消息。
    def test_prepare_clears_round_fields_without_erasing_history(self):
        # 模拟上一轮已经结束，并保存完整消息。
        messages = [self.system] + plain_turn("第一轮", "第一轮回答")
        # 旧工具历史不属于新一轮的独立结果列表。
        state = {"question": "追问", "tenant_id": "acme", "messages": messages, "pending_tool_calls": [{"id": "old"}], "tool_results": [{"old": True}], "stop_reason": "final_answer", "answer": "旧回答"}
        # 保存调用前副本，检查函数不修改传入字典。
        original = deepcopy(state)
        # 实际执行本课 prepare，而非在测试中复制它的逻辑。
        update = memory_agent.prepare_memory_node(state, self.filters, 2, 12000)
        # system 由可信程序重新创建，旧轮消息保留后追加新问题。
        self.assertEqual(update["messages"][1:], messages[1:] + [{"role": "user", "content": "追问"}])
        # 新 system 保留原规则，并补充多轮追问约定。
        self.assertIn(rag_agent.SYSTEM_PROMPT, update["messages"][0]["content"])
        # 所有当轮控制字段从空值开始。
        self.assertEqual((update["pending_tool_calls"], update["tool_results"], update["stop_reason"], update["answer"]), ([], [], "", ""))
        # 入参没有被原地修改。
        self.assertEqual(state, original)

    # 方法功能：空问题或越权身份仍在 prepare 阶段停止。
    def test_invalid_inputs_stop_before_model(self):
        # 分别检查空问题、错误问题类型和租户不一致。
        for question, tenant_id in ((" ", "acme"), (None, "acme"), ("查订单", "other")):
            # 标记当前场景，避免错误定位不清。
            with self.subTest(question=question, tenant_id=tenant_id):
                # 没有预设响应，任何模型调用都会暴露问题。
                model = ScriptedModel([])
                # 使用独立图和存档。
                graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
                # 运行真实输入校验。
                result = graph.invoke({"question": question, "tenant_id": tenant_id}, self.config)
                # 无效输入直接受控结束。
                self.assertEqual(result["stop_reason"], "invalid_input")
                # 不访问外层模型。
                self.assertEqual(model.requests, [])
        # 不访问内层 RAG。
        self.pipeline.ask.assert_not_called()

    # 方法功能：无效新输入不会覆盖已有历史或追加越权 user 消息。
    def test_invalid_prepare_preserves_existing_history(self):
        # 旧会话已经完成一轮问题。
        messages = [self.system] + plain_turn("旧问题", "旧回答")
        # 本次租户与可信过滤不一致。
        state = {"question": "越权问题", "tenant_id": "other", "messages": messages, "pending_tool_calls": [], "tool_results": [], "stop_reason": "final_answer", "answer": "旧回答"}
        # 实际运行输入校验和历史保护。
        update = memory_agent.prepare_memory_node(state, self.filters, 2, 12000)
        # 旧消息完整保留，不替换成无效输入。
        self.assertEqual(update["messages"], messages)
        # 仍按原规则直接结束，不调用模型。
        self.assertEqual(update["stop_reason"], "invalid_input")

    # 方法功能：历史轮数是旧 user 轮数，不包括当前问题。
    def test_trim_keeps_recent_completed_turns_and_current_question(self):
        # 构造三轮历史和一条新问题。
        messages = [self.system] + plain_turn("第一轮", "回答一") + plain_turn("第二轮", "回答二") + plain_turn("第三轮", "回答三") + [{"role": "user", "content": "当前问题"}]
        # 保存副本验证裁剪不会删除原列表内容。
        original = deepcopy(messages)
        # 最多保留两轮已完成历史。
        trimmed = memory_agent.trim_messages(messages, 2, 12000)
        # 最早一轮完整删除，system 与最新问题仍保留。
        self.assertEqual(trimmed, [self.system] + plain_turn("第二轮", "回答二") + plain_turn("第三轮", "回答三") + [{"role": "user", "content": "当前问题"}])
        # 裁剪是返回新列表，不原地改变输入。
        self.assertEqual(messages, original)

    # 方法功能：零历史轮数保留当前整轮，不保留旧问答。
    def test_zero_history_keeps_entire_current_tool_round(self):
        # 当前轮模型已经选工具，结果已正确配对。
        current = [{"role": "user", "content": "当前退款查询"}, request_tools([tool_call("get_refund", "current-refund", {"order_id": "A1002"})]), {"role": "tool", "tool_call_id": "current-refund", "content": "当前退款结果"}]
        # 在当前轮前放一轮旧消息。
        messages = [self.system] + plain_turn("旧问题", "旧回答") + current
        # 零只禁用旧历史，不截断正在执行的 Tool Calling。
        trimmed = memory_agent.trim_messages(messages, 0, 12000)
        # 当前请求与响应完整保留。
        self.assertEqual(trimmed, [self.system] + current)

    # 方法功能：按轮删除旧消息，不能留下孤立的 Tool 消息。
    def test_trim_removes_old_tool_calls_and_results_as_one_turn(self):
        # 第一旧轮包含两个工具请求和各自的结果。
        old_tools = [{"role": "user", "content": "旧订单和规则"}, request_tools([tool_call("get_order", "old-order", {"order_id": "A1002"}), tool_call("ask_knowledge_base", "old-rule", {"question": "规则？"})]), {"role": "tool", "tool_call_id": "old-order", "content": "订单结果"}, {"role": "tool", "tool_call_id": "old-rule", "content": "规则结果"}, {"role": "assistant", "content": "旧综合回答"}]
        # 在工具轮后放普通旧轮和当前问题。
        messages = [self.system] + old_tools + plain_turn("最近问题", "最近回答") + [{"role": "user", "content": "当前问题"}]
        # 只保留最近一轮已完成历史。
        trimmed = memory_agent.trim_messages(messages, 1, 12000)
        # 整个旧工具轮消失，不能只删除其中一部分。
        self.assertEqual(trimmed, [self.system] + plain_turn("最近问题", "最近回答") + [{"role": "user", "content": "当前问题"}])
        # 没有任何孤立工具响应。
        self.assertFalse(any(item["role"] == "tool" for item in trimmed))

    # 方法功能：字符预算不足时，即使未达到轮数限制也删除整轮旧消息。
    def test_character_budget_removes_old_turns(self):
        # 最新一轮和当前问题应完整保留。
        expected = [self.system] + plain_turn("最近问题", "最近回答") + [{"role": "user", "content": "当前问题"}]
        # 较长旧轮使上下文超出预算。
        messages = [self.system] + plain_turn("很旧的问题" * 100, "很旧的回答" * 100) + expected[1:]
        # 恰好以保留最新内容的大小作为预算。
        budget = memory_agent.context_size(expected)
        # 轮数允许很多轮，但预算要求删除旧轮。
        trimmed = memory_agent.trim_messages(messages, 10, budget)
        # 删除完成后保留完整的最近轮。
        self.assertEqual(trimmed, expected)

    # 方法功能：上下文计数包含完整消息和 Tool schemas，而非只计用户文字。
    def test_context_size_includes_tool_schemas_and_grows_with_messages(self):
        # 只有 system 和 user 的最小消息。
        messages = [self.system, {"role": "user", "content": "问题"}]
        # 单独序列化消息不能覆盖实际工具请求大小。
        messages_only = len(json.dumps(messages, ensure_ascii=False))
        # 原工具说明仍是较大的输入组成部分。
        schemas_only = len(json.dumps(rag_agent.TOOL_SCHEMAS, ensure_ascii=False))
        # 包含两部分的预算估算应大于只算消息。
        self.assertGreaterEqual(memory_agent.context_size(messages), messages_only + schemas_only)
        # 更长的正文增加估算值，不出现固定计数。
        longer = messages + [{"role": "assistant", "content": "补充内容" * 100}]
        # 保留可观察的增长，但不伪称它是精确 Token 数。
        self.assertGreater(memory_agent.context_size(longer), memory_agent.context_size(messages))

    # 方法功能：当前轮自身超预算时停止，而不是截断问题或静默调用模型。
    def test_first_round_over_budget_does_not_call_model(self):
        # 没有可供调用的预设模型响应。
        model = ScriptedModel([])
        # 极小预算甚至容不下工具定义。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver(), max_context_chars=1)
        # 用户问题仍使用正常格式。
        result = graph.invoke(self.initial, self.config)
        # 当轮自身超限明确结束。
        self.assertEqual(result["stop_reason"], "context_budget")
        # 不发送超预算上下文。
        self.assertEqual(model.requests, [])
        # 用户问题没有被切掉一半。
        self.assertEqual(result["messages"][-1]["content"], self.initial["question"])
        # 预算结束也没有待执行节点。
        self.assertEqual(graph.get_state(self.config).next, ())

    # 方法功能：超预算旧轮可以在下一短问题中整轮删除，正常继续会话。
    def test_short_question_recovers_after_previous_round_exceeded_budget(self):
        # 首轮不能调用模型，只有第二短轮需要一次响应。
        model = ScriptedModel([{"role": "assistant", "content": "短问题已完成。"}])
        # 保留正常字符预算，首轮问题自身超过预算。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver(), max_context_chars=12000)
        # 大问题不被静默截断，只会受控结束。
        first = graph.invoke({"question": "很长的问题" * 3000, "tenant_id": "acme"}, self.config)
        # 首轮超预算没有调用模型。
        self.assertEqual((first["stop_reason"], len(model.requests)), ("context_budget", 0))
        # 下一短问题进入新一轮，旧大轮可以整体删除。
        second = graph.invoke({"question": "你好", "tenant_id": "acme"}, self.config)
        # 清空旧 stop_reason 后正常调用一次模型。
        self.assertEqual((second["stop_reason"], len(model.requests)), ("final_answer", 1))
        # 最新上下文只包含短问题，不残留大轮的片段。
        self.assertEqual([item["content"] for item in model.requests[0]["messages"] if item["role"] == "user"], ["你好"])

    # 方法功能：工具结果变长后，在下一次模型调用前再次检查预算。
    def test_large_tool_result_stops_before_second_model_call(self):
        # 首轮选择知识库，响应列表中没有第二轮模型。
        model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "large-rule", {"question": "规则？"})])])
        # 模拟较大的完整 Tool 结果，仍保留引用。
        self.pipeline.ask.return_value = {"answer": "规则正文" * 3000, "citations": self.citations, "status": "answered", "trace": {}}
        # 预算可容纳首轮问题，但容不下大工具结果。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver(), max_context_chars=12000)
        # 实际执行 model → tools → model 预算检查。
        result = graph.invoke(self.initial, self.config)
        # 只执行一次外层模型，不带大结果继续调用。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("context_budget", 1))
        # 工具确实执行一次，不能误报为未查询。
        self.pipeline.ask.assert_called_once_with("规则？", self.filters)
        # 查询结果与引用仍保存在 State，未被静默截断。
        self.assertEqual(result["tool_results"][0]["result"]["data"]["citations"], self.citations)
        # 当前工具请求与响应仍正确配对。
        self.assertEqual(result["messages"][-1]["tool_call_id"], "large-rule")
        # 工具已完成，不残留待执行请求。
        self.assertEqual(result["pending_tool_calls"], [])

    # 方法功能：工具变长时可以删除旧轮，让完整当前轮继续交给模型。
    def test_model_trims_old_round_after_tools_grow_context(self):
        # 当前轮包含正确配对的工具请求和较长结果。
        current = [{"role": "user", "content": "当前问题"}, request_tools([tool_call("ask_knowledge_base", "current-rule", {"question": "规则？"})]), {"role": "tool", "tool_call_id": "current-rule", "content": "当前结果" * 100}]
        # 旧轮较长，和当前工具结果一起超过预算。
        messages = [self.system] + plain_turn("旧问题" * 100, "旧回答" * 100) + current
        # 本课预算允许当前完整工具轮，但不允许带上旧轮。
        budget = memory_agent.context_size([self.system] + current)
        # 本轮工具已经执行，因此没有待处理工具。
        state = {"question": "当前问题", "tenant_id": "acme", "messages": messages, "pending_tool_calls": [], "tool_results": [{"已完成": True}], "stop_reason": "", "answer": ""}
        # 裁剪后模型直接回答。
        model = ScriptedModel([{"role": "assistant", "content": "本轮完成。"}])
        # 实际运行模型前的二次裁剪。
        update = memory_agent.memory_model_node(state, model, 2, budget)
        # 本次请求只带完整当前轮，没有拆掉 Tool 消息。
        self.assertEqual(model.requests[0]["messages"], [self.system] + current)
        # 正常模型回答仍结束，不因为删历史误判预算失败。
        self.assertEqual(update["stop_reason"], "final_answer")

    # 方法功能：工具历史进入下一轮模型上下文，保留来源与调用 ID。
    def test_rag_sources_survive_follow_up_without_requery(self):
        # 第一轮查规则并完成，第二轮只根据历史追问。
        model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "memory-rule", {"question": "退款规则？"})]), {"role": "assistant", "content": "规则见 [1]。"}, {"role": "assistant", "content": "上一轮引用来自 rules/refund.md。"}])
        # 第 66 课不再在工具节点前静态暂停。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 一次 invoke 完成第一轮工具循环。
        first = graph.invoke({"question": "退款规则？", "tenant_id": "acme"}, self.config)
        # 下一轮追问不重新初始化历史。
        second = graph.invoke({"question": "刚才的来源是什么？", "tenant_id": "acme"}, self.config)
        # 第一轮原始结果保存完整引用。
        self.assertEqual(first["tool_results"][0]["result"]["data"]["citations"], self.citations)
        # 第二轮独立结果列表没有冒充本轮发生过新查询。
        self.assertEqual(second["tool_results"], [])
        # 模型仍可以从消息历史看到原工具正文。
        old_tools = [item for item in model.requests[2]["messages"] if item["role"] == "tool"]
        # 保留一条正确配对的历史工具消息。
        self.assertEqual(old_tools[0]["tool_call_id"], "memory-rule")
        # 引用不是由外层模型凭空重建的。
        self.assertEqual(json.loads(old_tools[0]["content"])["data"]["citations"], self.citations)
        # 追问没有重复查询知识库。
        self.pipeline.ask.assert_called_once_with("退款规则？", self.filters)
        # 首轮真正结束，没有残留工具暂停。
        self.assertEqual(first["stop_reason"], "final_answer")

    # 方法功能：本地 JSON 业务工具仍复用原查询与租户过滤。
    def test_business_tool_still_returns_multiple_refund_records(self):
        # 两次模型决策分别选择工具和完成回答。
        model = ScriptedModel([request_tools([tool_call("get_refund", "memory-refund", {"order_id": "A1002"})]), {"role": "assistant", "content": "查询完成。"}])
        # 图只增加 Memory，不重写业务 Tool。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 一个 invoke 跑完原来的工具循环。
        result = graph.invoke(self.initial, self.config)
        # A1002 在当前租户中有两条退款记录。
        self.assertEqual(len(result["tool_results"][0]["result"]["data"]), 2)
        # 多条记录仍对应一次工具调用。
        self.assertEqual(len([item for item in result["messages"] if item["role"] == "tool"]), 1)
        # 纯业务问题不需要查知识库。
        self.pipeline.ask.assert_not_called()

    # 方法功能：模型异常和空响应不会额外触发重试或新知识点。
    def test_model_errors_and_empty_answers_stop_without_retry(self):
        # 同时覆盖调用异常、协议异常和空回复。
        scenarios = [(RuntimeError("测试内部敏感正文"), "model_error"), ({"role": "user", "content": "伪造响应"}, "model_error"), ({"role": "assistant", "content": ""}, "empty_response")]
        # 每种失败使用独立会话图。
        for response, expected in scenarios:
            # 标记不同失败类型。
            with self.subTest(expected=expected):
                # 只允许一次模型尝试。
                model = ScriptedModel([response])
                # 建立真实受控结束图。
                graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
                # 执行本轮输入。
                result = graph.invoke(self.initial, self.config)
                # 保留已有结束语义，没有增加恢复或重试计数。
                self.assertEqual((result["stop_reason"], len(model.requests)), (expected, 1))
                # 原始内部异常不进入最终说明。
                self.assertNotIn("测试内部敏感正文", result["answer"])

    # 方法功能：正常新输入允许从上一轮受控失败后继续会话。
    def test_new_question_clears_previous_model_error(self):
        # 第一轮失败，第二轮是正常新问题而非 None 恢复。
        model = ScriptedModel([RuntimeError("离线异常"), {"role": "assistant", "content": "第二轮完成。"}])
        # 同一逻辑会话保留失败前的用户问题。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 第一轮按原节点逻辑受控结束。
        first = graph.invoke(self.initial, self.config)
        # 新输入重新进入 prepare，清空旧 stop_reason。
        second = graph.invoke({"question": "继续查规则", "tenant_id": "acme"}, self.config)
        # 新一轮能正常调用模型并结束。
        self.assertEqual((first["stop_reason"], second["stop_reason"]), ("model_error", "final_answer"))
        # 模型看到两条用户问题，不把安全错误说明伪装成模型回答。
        self.assertEqual([item["content"] for item in model.requests[1]["messages"] if item["role"] == "user"], [self.initial["question"], "继续查规则"])

    # 方法功能：Memory 仍保留规则资料类型限制。
    def test_record_documents_are_rejected_at_build_time(self):
        # 错误范围应在执行任何模型之前暴露。
        with self.assertRaises(ValueError):
            # 不允许把订单快照用作当前事实。
            memory_agent.build_graph(ScriptedModel([]), self.pipeline, SearchFilter("acme", doc_type="record"), InMemorySaver())

    # 方法功能：错误裁剪参数在建图时被拒绝，零历史仍属于合法配置。
    def test_invalid_history_and_character_limits_are_rejected(self):
        # 负历史或非正字符预算都没有有效学习语义。
        for history, chars in ((-1, 12000), (2, 0), (2, -1)):
            # 标记不同参数组合。
            with self.subTest(history=history, chars=chars):
                # 错误参数必须在执行模型前暴露。
                with self.assertRaises(ValueError):
                    # 仅建图，不产生外部请求。
                    memory_agent.build_graph(ScriptedModel([]), self.pipeline, self.filters, InMemorySaver(), max_history_turns=history, max_context_chars=chars)

    # 方法功能：外层模型用量只作为对象属性，不混入 State 或消息。
    def test_compatible_model_saves_last_usage_without_changing_message(self):
        # 配置只在内存中创建，不读取任何环境文件。
        model = CompatibleToolModel(Settings(llm_api_key="test-only"))
        # 预设一条普通响应和独立用量。
        response = {"message": {"role": "assistant", "content": "回答"}, "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}, "finish_reason": "stop"}
        # 替换最低层请求，禁止网络访问。
        with patch.object(model, "request_with_tools", return_value=response):
            # 调用真实封装方法。
            message = model.chat_with_tools([], rag_agent.TOOL_SCHEMAS)
        # 返回的消息协议保持不变。
        self.assertEqual(message, response["message"])
        # 最近用量单独保存，便于 Console 观察。
        self.assertEqual(model.last_usage, response["usage"])
        # 接口没有提供 usage 时，新记录为空而不是沿用旧值。
        empty_usage = {"message": {"role": "assistant", "content": "第二轮"}, "usage": {}, "finish_reason": "stop"}
        # 仍然替换请求，不使用真实 API。
        with patch.object(model, "request_with_tools", return_value=empty_usage):
            # 未提供用量不影响正常消息返回。
            second_message = model.chat_with_tools([], rag_agent.TOOL_SCHEMAS)
        # 本轮未知用量必须显示未知，不伪称上一轮 Token 数。
        self.assertEqual((second_message, model.last_usage), (empty_usage["message"], {}))
        # 重新设置旧值，验证接下来异常会真正清空。
        model.last_usage = {"prompt_tokens": 999}
        # 后一次异常不能留下上一轮 Token 数。
        with patch.object(model, "request_with_tools", side_effect=RuntimeError("离线请求异常")):
            # 封装允许节点捕获失败，不在模型类里重试。
            with self.assertRaises(RuntimeError):
                # 只调用替身方法，不访问模型 API。
                model.chat_with_tools([], rag_agent.TOOL_SCHEMAS)
        # 失败后旧用量已清空。
        self.assertEqual(model.last_usage, {})

    # 方法功能：真实 Console 连续提问并通过 /new 隔离旧会话。
    def test_console_follow_up_new_session_and_quit(self):
        # 配置仅在内存中创建，替代环境读取。
        settings = Settings(llm_api_key="test-only")
        # 同会话两轮，以及新会话一轮，共三次模型响应。
        model = ScriptedModel([{"role": "assistant", "content": "首轮回答。"}, {"role": "assistant", "content": "追问回答。"}, {"role": "assistant", "content": "新会话回答。"}])
        # 保存实际图，以便检查 Console 生成的会话 State。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 所有外部初始化和交互都使用替身，仅真实图继续运行。
        with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline) as pipeline_builder, patch.object(main_workflow, "build_graph", return_value=graph) as graph_builder, patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", side_effect=["查 A1002", "它的退款呢？", "/new", "你好", "q"]) as user_input, patch("builtins.print") as output, patch.object(graph, "invoke", wraps=graph.invoke) as invoke:
            # 调用真实 Console，多轮测试不会自动访问服务。
            main_workflow.main()
        # 全部问答只构建一次模型管道和一次图。
        pipeline_builder.assert_called_once_with(settings)
        # 同一张图跨会话使用，不能在每次提问时重建存档器。
        self.assertEqual(graph_builder.call_count, 1)
        # 第二轮模型保留首轮问题和回答。
        self.assertEqual([item["role"] for item in model.requests[1]["messages"]], ["system", "user", "assistant", "user"])
        # /new 后只剩新问题，不带旧会话内容。
        self.assertEqual([item["content"] for item in model.requests[2]["messages"] if item["role"] == "user"], ["你好"])
        # 每次 invoke 都只更新入口问题和租户，不能清空历史字段。
        self.assertTrue(all(set(call.args[0]) == {"question", "tenant_id"} for call in invoke.call_args_list))
        # /new 和 q 本身不调用图。
        self.assertEqual((invoke.call_count, user_input.call_count), (3, 5))
        # 新编号保存独立回答。
        other_config = {"configurable": {"thread_id": f"{main_workflow.THREAD_ID}-2"}}
        # 旧会话没有被删除或覆盖。
        self.assertEqual(graph.get_state({"configurable": {"thread_id": main_workflow.THREAD_ID}}).values["answer"], "追问回答。")
        # 新会话确实保存在另一份 State。
        self.assertEqual(graph.get_state(other_config).values["answer"], "新会话回答。")
        # 本课 Debug 配置不设客户端超时，也不下载模型。
        self.assertEqual((settings.llm_timeout, settings.local_files_only), (None, True))
        # Console 可观察接口用量，但不伪称包括 RAG 内层。
        printed = "\n".join(str(argument) for call in output.call_args_list for argument in call.args)
        # 输出明确标出 Token 指标。
        self.assertIn("Token", printed)
        # 输出范围说明防止误把最后一次调用当作总用量。
        self.assertIn("不含 RAG 内层", printed)

    # 方法功能：空白输入和 q 都不会进入图或调用模型。
    def test_console_empty_input_and_quit_do_not_invoke_graph(self):
        # 使用内存配置和没有响应的模型。
        settings = Settings(llm_api_key="test-only")
        # 意外调用模型会暴露错误。
        model = ScriptedModel([])
        # 空白问题不需要真实图，直接检查是否误调用。
        graph = Mock()
        # 替换全部外部初始化，输入只包括空白和退出。
        with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline), patch.object(main_workflow, "build_graph", return_value=graph), patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", side_effect=["   ", "q"]), patch("builtins.print"):
            # 运行真实入口的空输入和退出分支。
            main_workflow.main()
        # 空问题不执行 prepare，也不会写入新一轮。
        graph.invoke.assert_not_called()
        # 没有发出模型请求。
        self.assertEqual(model.requests, [])

    # 方法功能：预算拒绝本轮模型时，Console 不能显示上一轮的 Token 数。
    def test_console_budget_stop_prints_unknown_usage_instead_of_old_tokens(self):
        # 配置仅在内存中创建。
        settings = Settings(llm_api_key="test-only")
        # 首轮成功返回用量，第二轮大问题不应调用模型。
        model = ScriptedModel([{"role": "assistant", "content": "第一轮完成。"}])
        # 使用真实预算图，禁止把替身结果伪造为预算判断。
        graph = memory_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver(), max_context_chars=12000)
        # 将配置、RAG、模型创建与用户交互全部替换。
        with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline), patch.object(main_workflow, "build_graph", return_value=graph), patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", side_effect=["你好", "很长的问题" * 3000, "q"]), patch("builtins.print") as output:
            # 先获得真实替身用量，再触发模型调用前预算拒绝。
            main_workflow.main()
        # 第二轮没有模型调用，旧 usage 已经由入口清空。
        self.assertEqual((len(model.requests), model.last_usage), (1, {}))
        # 只收集 Console 的输入 Token 显示记录。
        usage_values = [call.args[1] for call in output.call_args_list if call.args and str(call.args[0]).startswith("最后一次外层调用输入 Token")]
        # 首轮确实显示了接口提供的数值。
        self.assertGreater(usage_values[0], 0)
        # 第二轮明确显示未知，而非上一轮数字或伪造的零。
        self.assertEqual(usage_values[1], "未返回")

    # 方法功能：图级异常安全退出，不泄露原始异常正文或自动重试。
    def test_console_graph_exception_exits_without_retry_or_error_leak(self):
        # 配置与客户端替身均在内存中。
        settings = Settings(llm_api_key="test-only")
        # 模型曾有旧记录，新问题开始必须清空。
        model = ScriptedModel([])
        # 用量先放入旧值，观察异常时不能保留它。
        model.last_usage = {"prompt_tokens": 999}
        # 图级替身用来模拟框架执行异常。
        graph = Mock()
        # 原始异常细节不能直接打印给用户。
        graph.invoke.side_effect = RuntimeError("测试内部连接信息敏感正文")
        # 只提供一个问题，错误后的意外继续输入会导致测试失败。
        with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline), patch.object(main_workflow, "build_graph", return_value=graph), patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", side_effect=["查 A1002"]) as user_input, patch("builtins.print") as output:
            # 当前入口直接安全结束，不套用第 65 课暂停恢复逻辑。
            main_workflow.main()
        # 图不自动重试，也不再提交新问题。
        self.assertEqual((graph.invoke.call_count, user_input.call_count), (1, 1))
        # 旧模型用量已经清空。
        self.assertEqual(model.last_usage, {})
        # 原始异常正文不出现在 Console。
        printed = "\n".join(str(argument) for call in output.call_args_list for argument in call.args)
        # 安全说明不会暴露内部连接内容。
        self.assertNotIn("测试内部连接信息敏感正文", printed)


# 直接运行测试文件才启动测试，不运行真实 Console 入口。
if __name__ == "__main__":
    # 所有模型、RAG 和配置均为内存替身。
    unittest.main()
