import json
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from langgraph.checkpoint.memory import InMemorySaver
import main_workflow
from agent_learning.core.config import Settings
from agent_learning.core.models import SearchFilter
from agent_learning.workflows import checkpoint_agent, rag_agent


# 方法功能：构造一条真实格式的 Tool Calling 请求。
def tool_call(name: str, call_id: str, arguments: dict) -> dict:
    # 工具参数必须使用 JSON 字符串，而不是直接放入字典。
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}


# 方法功能：表示模型选择了工具，但尚未给出最终回答。
def request_tools(calls: list) -> dict:
    # 保留 assistant 角色和所有本轮工具请求。
    return {"role": "assistant", "content": "", "tool_calls": calls}


# 类职责：用预设消息或异常代替真实模型，记录每次节点尝试。
class ScriptedModel:
    # 方法功能：准备离线响应和局部副作用计数。
    def __init__(self, responses: list):
        # 每个列表元素对应一次模型调用，包括失败的尝试。
        self.responses = responses
        # 记录请求发生在抛出异常之前，便于观察恢复后的重复执行。
        self.requests = []

    # 方法功能：使用真实模型接口，但不访问外部服务。
    def chat_with_tools(self, messages: list, tools: list) -> dict:
        # 每次调用先保存上下文，作为模拟的节点前半段副作用。
        self.requests.append({"messages": deepcopy(messages), "tools": deepcopy(tools)})
        # 按尝试次数取本次离线响应，多余调用会触发测试失败。
        response = self.responses[len(self.requests) - 1]
        # 异常交给真正的 Checkpoint 图处理，不在替身中恢复。
        if isinstance(response, Exception):
            # 模拟节点在更新 State 前失败。
            raise response
        # 避免节点修改测试预设消息。
        return deepcopy(response)


# 类职责：离线检查状态存档、会话隔离、暂停与失败恢复。
class CheckpointAgentTests(unittest.TestCase):
    # 方法功能：准备可信身份、内存知识库和会话配置。
    def setUp(self):
        # 保持原 RAG 课的规则资料边界。
        self.filters = SearchFilter(tenant_id="acme", max_security_level=1, doc_type="policy")
        # 用纯内存对象替代数据库和 RAG 模型。
        self.pipeline = Mock()
        # 保存一份完整引用，检查 Checkpoint 不丢失来源。
        self.citations = [{"number": 1, "source": "rules/refund.md", "excerpt": "退款规则原文"}]
        # 包装 RAG 时只保留答案、引用和状态。
        self.pipeline.ask.return_value = {"answer": "退款规则见 [1]。", "citations": self.citations, "status": "answered", "trace": {}}
        # thread_id 只表示逻辑会话，并不是操作系统线程编号。
        self.config = {"configurable": {"thread_id": "checkpoint-test"}}
        # 每个测试从一份新的用户输入开始。
        self.initial = {"question": "查 A1002 的订单及退款规则", "tenant_id": "acme"}

    # 方法功能：模型选工具后先暂停，State 中只有请求，没有工具执行结果。
    def test_pause_before_tools_saves_state_without_executing_tools(self):
        # 模型只提供一轮工具选择，多余调用会暴露错误。
        call = tool_call("ask_knowledge_base", "rules-call", {"question": "退款规则？"})
        # 预设选择知识库工具。
        model = ScriptedModel([request_tools([call])])
        # 使用真正的内存 Checkpoint，不替换 LangGraph。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 第一次执行经过 prepare 和 model，在 tools 前暂停。
        result = graph.invoke(self.initial, self.config)
        # 读取当前会话的存档，而不是再次执行图。
        snapshot = graph.get_state(self.config)
        # 下一步节点明确是 tools。
        self.assertEqual(snapshot.next, ("tools",))
        # 待执行请求已经写入存档。
        self.assertEqual(snapshot.values["pending_tool_calls"], [call])
        # 暂停时还没有业务或知识库结果。
        self.assertEqual((result["tool_results"], snapshot.values["tool_results"]), ([], []))
        # 暂停不属于自然结束或业务失败。
        self.assertEqual((result["stop_reason"], result["answer"]), ("", ""))
        # 知识库查询尚未发生。
        self.pipeline.ask.assert_not_called()
        # 只调用过一次模型来选择工具。
        self.assertEqual(len(model.requests), 1)

    # 方法功能：None 恢复使用原 State，不重复 prepare 或第一次模型决策。
    def test_resume_runs_saved_tools_and_preserves_complete_sources(self):
        # 第一轮选择工具，第二轮直接给出最终回答。
        model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "rules-call", {"question": "退款规则？"})]), {"role": "assistant", "content": "退款规则见 [1]。"}])
        # 建图时传入同一个内存存档对象。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 先暂停在工具执行前。
        graph.invoke(self.initial, self.config)
        # None 表示从当前会话存档继续，不重新提交用户问题。
        result = graph.invoke(None, self.config)
        # 第二轮回答自然结束。
        self.assertEqual((result["answer"], result["stop_reason"]), ("退款规则见 [1]。", "final_answer"))
        # END 后没有待执行节点。
        self.assertEqual(graph.get_state(self.config).next, ())
        # 只执行一次知识库查询，可信过滤仍来自入口。
        self.pipeline.ask.assert_called_once_with("退款规则？", self.filters)
        # 存档与模型都保留完整引用，不依靠外层模型重建来源。
        self.assertEqual(result["tool_results"][0]["result"]["data"]["citations"], self.citations)
        # 模型选择一次工具、综合回答一次，没有重跑选择节点。
        self.assertEqual(len(model.requests), 2)
        # prepare 没有重新初始化，否则工具消息会丢失。
        self.assertEqual([message["role"] for message in result["messages"]], ["system", "user", "assistant", "tool", "assistant"])
        # State 沿用上一课七个核心字段，不增加预算或重试计数。
        self.assertEqual(set(result), {"question", "tenant_id", "messages", "pending_tool_calls", "tool_results", "stop_reason", "answer"})

    # 方法功能：模型再次选工具时，每一轮都会在 tools 前暂停。
    def test_each_tool_round_pauses_before_execution(self):
        # 用两个已有只读业务 Tool 演示多轮暂停。
        model = ScriptedModel([request_tools([tool_call("get_order", "order-call", {"order_id": "A1002"})]), request_tools([tool_call("get_refund", "refund-call", {"order_id": "A1002"})]), {"role": "assistant", "content": "查询完成。"}])
        # 使用真实图和本地 JSON，仍不连接外部服务。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 第一轮选订单工具后暂停。
        graph.invoke(self.initial, self.config)
        # 恢复后查订单，再选退款工具，并再次暂停。
        result = graph.invoke(None, self.config)
        # 第一轮结果已保存，第二轮工具尚未执行。
        self.assertEqual([item["tool_name"] for item in result["tool_results"]], ["get_order"])
        # 待执行请求变成退款工具。
        self.assertEqual(result["pending_tool_calls"][0]["function"]["name"], "get_refund")
        # 第二次暂停仍然指向 tools 节点。
        self.assertEqual(graph.get_state(self.config).next, ("tools",))
        # 再恢复一次完成剩余查询和最终回答。
        result = graph.invoke(None, self.config)
        # 两份历史都保留，不重新初始化。
        self.assertEqual([item["tool_name"] for item in result["tool_results"]], ["get_order", "get_refund"])
        # 模型总共只有三次实际决策。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("final_answer", 3))
        # 纯订单问题不会误查知识库。
        self.pipeline.ask.assert_not_called()

    # 方法功能：同一张图用不同 thread_id，保存两份互不覆盖的 State。
    def test_thread_ids_isolate_states_and_resume_positions(self):
        # 两个会话分别选各自订单，再分别完成回答。
        model = ScriptedModel([request_tools([tool_call("get_order", "first-order", {"order_id": "A1001"})]), request_tools([tool_call("get_order", "second-order", {"order_id": "A1002"})]), {"role": "assistant", "content": "第一会话完成。"}, {"role": "assistant", "content": "第二会话完成。"}])
        # 两个会话共享图和存档对象，但使用不同存档键。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 第一份会话配置。
        first_config = {"configurable": {"thread_id": "first-thread"}}
        # 第二份会话配置。
        second_config = {"configurable": {"thread_id": "second-thread"}}
        # 第一会话停在订单工具前。
        graph.invoke({"question": "查 A1001", "tenant_id": "acme"}, first_config)
        # 第二会话也独立停在工具前。
        graph.invoke({"question": "查 A1002", "tenant_id": "acme"}, second_config)
        # 第一会话的原始问题不会被第二会话覆盖。
        self.assertEqual(graph.get_state(first_config).values["question"], "查 A1001")
        # 第二会话保存自己的原始问题。
        self.assertEqual(graph.get_state(second_config).values["question"], "查 A1002")
        # 只恢复第一会话。
        first_result = graph.invoke(None, first_config)
        # 第一会话查到自己的订单并结束。
        self.assertEqual(first_result["tool_results"][0]["result"]["data"]["order_id"], "A1001")
        # 第二会话仍暂停，并没有被第一会话恢复。
        self.assertEqual(graph.get_state(second_config).next, ("tools",))
        # 第二会话尚未拥有工具结果。
        self.assertEqual(graph.get_state(second_config).values["tool_results"], [])
        # 使用第二份配置才能恢复第二会话。
        second_result = graph.invoke(None, second_config)
        # 第二会话得到独立订单与答案。
        self.assertEqual((second_result["tool_results"][0]["result"]["data"]["order_id"], second_result["answer"]), ("A1002", "第二会话完成。"))

    # 方法功能：失败后的 model 恢复不重跑已经完成的业务 tools。
    def test_failed_model_resumes_without_repeating_completed_tools(self):
        # 业务 Tool 后第二轮模型失败，人工继续后第三次尝试成功。
        model = ScriptedModel([request_tools([tool_call("get_order", "order-call", {"order_id": "A1002"})]), RuntimeError("离线临时模型异常"), {"role": "assistant", "content": "恢复后完成。"}])
        # 建图保留真实节点和真实 Checkpoint 行为。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 先取得待执行订单请求。
        graph.invoke(self.initial, self.config)
        # 记录实际工具分发次数，不替换查询结果。
        with patch.object(rag_agent, "dispatch_tool", wraps=rag_agent.dispatch_tool) as dispatch:
            # 第一次恢复执行业务 Tool，然后模型异常抛到调用方。
            with self.assertRaisesRegex(RuntimeError, "离线临时模型异常"):
                # 异常前的业务结果由成功的 tools 节点保存。
                graph.invoke(None, self.config)
            # 读取失败后的存档。
            snapshot = graph.get_state(self.config)
            # 失败节点仍然待执行，不是 END。
            self.assertEqual(snapshot.next, ("model",))
            # 前一成功节点的订单结果完整保留。
            self.assertEqual(snapshot.values["tool_results"][0]["result"]["data"]["order_id"], "A1002")
            # 失败尝试尚未写入完成状态。
            self.assertEqual(snapshot.values["stop_reason"], "")
            # 再次人工继续只执行失败的 model。
            result = graph.invoke(None, self.config)
            # 订单分发恰好一次，恢复不重新查 JSON。
            self.assertEqual(dispatch.call_count, 1)
        # 模型初次选工具、失败、再次成功，共三次尝试。
        self.assertEqual((len(model.requests), result["stop_reason"]), (3, "final_answer"))
        # 工具历史没有重复追加。
        self.assertEqual(len(result["tool_results"]), 1)
        # 失败后的再次模型请求仍看到同一份业务上下文。
        self.assertEqual(model.requests[1], model.requests[2])

    # 方法功能：失败节点重新开始，节点内部已发生的外部动作不由 State 自动回滚。
    def test_side_effect_before_failure_can_repeat_on_resume(self):
        # 替身先记录请求，再抛异常，模拟节点内动作已经发生。
        model = ScriptedModel([RuntimeError("第一次失败"), {"role": "assistant", "content": "第二次成功。"}])
        # 真正的 Checkpoint 图负责失败恢复。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 初次模型调用异常，不转成受控结束。
        with self.assertRaises(RuntimeError):
            # prepare 成功状态仍会保存。
            graph.invoke(self.initial, self.config)
        # 第一次节点前半段的请求记录已经产生。
        self.assertEqual(len(model.requests), 1)
        # 恢复同一个待执行 model 节点。
        result = graph.invoke(None, self.config)
        # 前半段的记录动作再次发生，Checkpoint 不提供恰好一次保证。
        self.assertEqual(len(model.requests), 2)
        # 两次尝试使用同一个成功 prepare 的上下文。
        self.assertEqual(model.requests[0], model.requests[1])
        # 失败那次没有追加 assistant，成功那次才更新 State。
        self.assertEqual([message["role"] for message in result["messages"]], ["system", "user", "assistant"])

    # 方法功能：查询不存在订单是业务失败，直接到 END，不是待恢复异常。
    def test_business_failure_is_finished_not_pending_exception(self):
        # 只提供一次决策，确保失败后不会自动再次请求模型。
        model = ScriptedModel([request_tools([tool_call("get_order", "missing-order", {"order_id": "A9999"})])])
        # 本地 JSON 用于实际业务失败分支。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 先暂停在工具前。
        graph.invoke(self.initial, self.config)
        # 恢复后返回业务失败，而不是抛系统异常。
        result = graph.invoke(None, self.config)
        # 查询失败标记受控结束。
        self.assertEqual(result["stop_reason"], "tool_error")
        # END 没有待恢复节点。
        self.assertEqual(graph.get_state(self.config).next, ())
        # 失败结果仍保存在 Checkpoint 中。
        self.assertFalse(result["tool_results"][0]["result"]["success"])
        # 对已结束图传 None 不会重新开始查询。
        self.assertEqual(graph.invoke(None, self.config), result)
        # 模型只做过初次工具选择。
        self.assertEqual(len(model.requests), 1)

    # 方法功能：无工具的正常回答直接结束，不会被 tools 断点暂停。
    def test_direct_answer_finishes_without_pause(self):
        # 模型直接给出一句回答。
        model = ScriptedModel([{"role": "assistant", "content": "请提供订单号。"}])
        # 保持图的 Checkpoint 和 tools 断点。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 一次执行完成。
        result = graph.invoke(self.initial, self.config)
        # 正常 END 与暂停状态明确不同。
        self.assertEqual((result["stop_reason"], graph.get_state(self.config).next), ("final_answer", ()))
        # 不发生知识库查询。
        self.pipeline.ask.assert_not_called()

    # 方法功能：无效输入与越权身份仍在 prepare 后直接 END。
    def test_invalid_inputs_stop_before_model(self):
        # 各种无效输入使用独立图和独立存档。
        for initial in ({"question": " ", "tenant_id": "acme"}, {"question": "查订单", "tenant_id": "other"}):
            # 标记当前输入，便于测试失败时定位。
            with self.subTest(initial=initial):
                # 任何模型调用都表示入口校验错误。
                model = ScriptedModel([])
                # 构建实际校验图。
                graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
                # 运行输入校验。
                result = graph.invoke(initial, self.config)
                # 错误输入被保存为已结束状态。
                self.assertEqual((result["stop_reason"], graph.get_state(self.config).next), ("invalid_input", ()))
                # 没有发出任何模型请求。
                self.assertEqual(model.requests, [])

    # 方法功能：读取存档是只读观察，不会执行下一节点。
    def test_get_state_does_not_resume_execution(self):
        # 模型先选规则查询。
        model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "rules-call", {"question": "退款规则？"})])])
        # 建立实际图和内存存档。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 停在工具前。
        graph.invoke(self.initial, self.config)
        # 读取一次当前状态。
        first = graph.get_state(self.config)
        # 再读取一次不会推进执行。
        second = graph.get_state(self.config)
        # 两次观察到同一份状态。
        self.assertEqual(first.values, second.values)
        # 下一节点也没有变化。
        self.assertEqual((first.next, second.next), (("tools",), ("tools",)))
        # 模型没有新增请求。
        self.assertEqual(len(model.requests), 1)
        # 规则查询没有偷偷执行。
        self.pipeline.ask.assert_not_called()

    # 方法功能：新内存存档不包含旧状态，证明本课不是跨进程持久化。
    def test_new_memory_saver_has_no_previous_state(self):
        # 第一张图保存正常回答。
        first_model = ScriptedModel([{"role": "assistant", "content": "已有存档。"}])
        # 使用第一个内存对象。
        first_graph = checkpoint_agent.build_graph(first_model, self.pipeline, self.filters, InMemorySaver())
        # 写入逻辑会话存档。
        first_graph.invoke(self.initial, self.config)
        # 同名 thread_id 在另一个内存对象里没有对应存档。
        second_graph = checkpoint_agent.build_graph(ScriptedModel([]), self.pipeline, self.filters, InMemorySaver())
        # 只读查看新对象，不执行任何节点。
        snapshot = second_graph.get_state(self.config)
        # 新存档对象返回空状态和空待执行队列。
        self.assertEqual((snapshot.values, snapshot.next), ({}, ()))

    # 方法功能：同会话传新字典会重新经过 prepare，不等同于 None 恢复。
    def test_new_input_resets_round_instead_of_adding_memory(self):
        # 第一轮查订单，第二轮新输入由模型直接回答。
        model = ScriptedModel([request_tools([tool_call("get_order", "first-order", {"order_id": "A1002"})]), {"role": "assistant", "content": "第一轮完成。"}, {"role": "assistant", "content": "第二轮完成。"}])
        # 使用同一图和同一存档对象。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 第一轮先暂停，再恢复完成。
        graph.invoke(self.initial, self.config)
        # 首轮已取得一份业务结果。
        first_result = graph.invoke(None, self.config)
        # 确认第一轮确实执行过工具。
        self.assertEqual(len(first_result["tool_results"]), 1)
        # 新字典作为新一轮输入，会重新执行 START 和 prepare。
        second_result = graph.invoke({"question": "一个新问题", "tenant_id": "acme"}, self.config)
        # 本课没有自动将上一轮消息累积成会话 Memory。
        self.assertEqual(second_result["tool_results"], [])
        # 新 prepare 只保存当前问题的 system、user 和新回答。
        self.assertEqual([message["role"] for message in second_result["messages"]], ["system", "user", "assistant"])
        # 当前用户消息是新问题，不是旧问题或恢复指令。
        self.assertEqual(second_result["messages"][1]["content"], "一个新问题")

    # 方法功能：Checkpoint 不能绕过已有的规则资料类型限制。
    def test_checkpoint_build_rejects_record_documents(self):
        # 防止把订单快照文档当成当前业务事实。
        with self.assertRaises(ValueError):
            # 只建图，不访问知识库或模型。
            checkpoint_agent.build_graph(ScriptedModel([]), self.pipeline, SearchFilter("acme", doc_type="record"), InMemorySaver())

    # 方法功能：真实 Console 用回车继续暂停图，并输出完整知识库来源。
    def test_main_resumes_pause_and_prints_saved_sources(self):
        # 配置直接在内存创建，测试不会读取环境文件。
        settings = Settings(llm_api_key="test-only")
        # 实际模型循环由离线响应驱动。
        model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "main-rules", {"question": "退款规则？"})]), {"role": "assistant", "content": "规则见 [1]。"}])
        # 保留真实 Checkpoint 图，用来读取入口运行后的存档。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 替换全部运行时外部依赖，只保留真实图的执行。
        with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline) as pipeline_builder, patch.object(main_workflow, "build_graph", return_value=graph), patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", side_effect=["退款规则？", ""]) as user_input, patch("builtins.print") as output:
            # 问题后回车，执行原入口的暂停和恢复流程。
            main_workflow.main()
        # 配置和 RAG 的创建保持上一课的简单路径。
        pipeline_builder.assert_called_once_with(settings)
        # Debug 不设客户端超时，且禁止下载缺少的本地模型。
        self.assertEqual((settings.llm_timeout, settings.local_files_only), (None, True))
        # Console 只询问一次问题和一次继续动作。
        self.assertEqual(user_input.call_count, 2)
        # 入口使用同一个 thread_id 完成全部执行。
        snapshot = graph.get_state({"configurable": {"thread_id": main_workflow.THREAD_ID}})
        # 已结束状态完整保存在该会话下。
        self.assertEqual((snapshot.next, snapshot.values["stop_reason"]), ((), "final_answer"))
        # 合并纯内存 print 记录检查原始来源未丢失。
        printed = "\n".join(str(argument) for call in output.call_args_list for argument in call.args)
        # 来源路径仍然显示。
        self.assertIn("rules/refund.md", printed)
        # 原文仍然显示，不只是引用编号。
        self.assertIn("退款规则原文", printed)
        # 知识库只执行过一次，不因暂停重复查询。
        self.pipeline.ask.assert_called_once_with("退款规则？", self.filters)

    # 方法功能：入口遇到模型异常后等待人工继续，不泄露原始异常正文。
    def test_main_continues_failed_node_and_hides_error_details(self):
        # 测试配置不读取任何真实密钥。
        settings = Settings(llm_api_key="test-only")
        # 前序业务结果成功，后序模型失败，再次人工继续成功。
        model = ScriptedModel([request_tools([tool_call("get_order", "main-order", {"order_id": "A1002"})]), RuntimeError("测试内部异常敏感正文"), {"role": "assistant", "content": "人工继续后完成。"}])
        # 用真实图检查成功节点不会重跑。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 所有外部创建函数和交互都替换为内存对象。
        with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline), patch.object(main_workflow, "build_graph", return_value=graph), patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", side_effect=["查 A1002", "", ""]) as user_input, patch("builtins.print") as output, patch.object(rag_agent, "dispatch_tool", wraps=rag_agent.dispatch_tool) as dispatch:
            # 两次回车分别恢复工具暂停和失败的 model 节点。
            main_workflow.main()
        # 订单工具只分发一次，不因后续失败重新执行。
        self.assertEqual(dispatch.call_count, 1)
        # 一次问题加两次人工继续。
        self.assertEqual(user_input.call_count, 3)
        # 模型失败属于一轮尝试，恢复会再执行一次模型请求。
        self.assertEqual(len(model.requests), 3)
        # Console 只显示安全异常说明和最终业务结果。
        printed = "\n".join(str(argument) for call in output.call_args_list for argument in call.args)
        # 原始异常正文不输出到 Console。
        self.assertNotIn("测试内部异常敏感正文", printed)
        # 成功恢复后显示最终回答。
        self.assertIn("人工继续后完成。", printed)

    # 方法功能：退出暂停会话不会执行剩余 Tool。
    def test_main_quit_does_not_execute_pending_tool(self):
        # 使用内存配置隔离环境文件。
        settings = Settings(llm_api_key="test-only")
        # 模型只选择规则工具，没有准备最终回答。
        model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "quit-rules", {"question": "退款规则？"})])])
        # 真正的图停在 tools 节点前。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # q 由替身输入，退出不请求任何外部服务。
        with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline), patch.object(main_workflow, "build_graph", return_value=graph), patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", side_effect=["退款规则？", "q"]), patch("builtins.print"):
            # 运行真实入口的退出分支。
            main_workflow.main()
        # 退出时 Tool 完全未执行。
        self.pipeline.ask.assert_not_called()
        # 内存对象尚在测试作用域中，所以可以观察仍暂停的状态。
        self.assertEqual(graph.get_state({"configurable": {"thread_id": main_workflow.THREAD_ID}}).next, ("tools",))
        # 没有继续调用模型。
        self.assertEqual(len(model.requests), 1)

    # 方法功能：无工具回答一次完成，入口不会多询问继续动作。
    def test_main_direct_answer_needs_no_resume_input(self):
        # 测试只使用内存配置。
        settings = Settings(llm_api_key="test-only")
        # 模型立即回答，没有工具节点。
        model = ScriptedModel([{"role": "assistant", "content": "直接完成。"}])
        # 使用实际 Checkpoint 图。
        graph = checkpoint_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver())
        # 只提供一个问题，意外的继续输入会导致测试失败。
        with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline), patch.object(main_workflow, "build_graph", return_value=graph), patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", side_effect=["你好"]) as user_input, patch("builtins.print"):
            # 运行真实入口的自然 END 分支。
            main_workflow.main()
        # 只读取一次用户问题。
        self.assertEqual(user_input.call_count, 1)
        # 没有知识库调用。
        self.pipeline.ask.assert_not_called()

    # 方法功能：异常且没有待恢复节点时，入口不能误报自然完成。
    def test_main_does_not_report_completion_for_unrecoverable_failure(self):
        # 分别检查完全无存档，以及存在旧值但没有待执行节点的情况。
        for saved_values in ({}, {"answer": "旧回答不能冒充本次成功", "stop_reason": "final_answer", "tool_results": []}):
            # 标记不同存档场景，便于定位失败。
            with self.subTest(saved_values=saved_values):
                # 配置只在内存中创建。
                settings = Settings(llm_api_key="test-only")
                # 替身图只用于模拟框架未生成可恢复任务的异常。
                graph = Mock()
                # 异常内容不能直接显示。
                graph.invoke.side_effect = RuntimeError("测试无存档内部异常正文")
                # 当前没有待执行节点，不应尝试 None 恢复。
                graph.get_state.return_value = Mock(values=saved_values, next=())
                # 替换全部运行时外部依赖，测试不会读配置或访问服务。
                with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=ScriptedModel([])), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline), patch.object(main_workflow, "build_graph", return_value=graph), patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", side_effect=["查询问题"]) as user_input, patch("builtins.print") as output:
                    # 入口应安全结束，不能读取空 State 的 answer 字段。
                    main_workflow.main()
                # 没有待恢复节点时不反复执行图。
                self.assertEqual(graph.invoke.call_count, 1)
                # 没有询问继续，以免循环执行无法恢复的任务。
                self.assertEqual(user_input.call_count, 1)
                # 观察输出是否泄露错误或伪造最终完成。
                printed = "\n".join(str(argument) for call in output.call_args_list for argument in call.args)
                # 原始异常内容不出现在 Console。
                self.assertNotIn("测试无存档内部异常正文", printed)
                # 旧回答也不能冒充本次完成结果。
                self.assertNotIn("旧回答不能冒充本次成功", printed)
                # 本次失败没有正式输出答案。
                self.assertFalse(any(call.args and call.args[0] == "输出：" for call in output.call_args_list))


# 直接运行此文件时才启动离线测试。
if __name__ == "__main__":
    # 测试使用内存模型、内存 RAG 和本地 JSON，不访问外部服务。
    unittest.main()
