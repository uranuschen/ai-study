import json
import unittest
from unittest.mock import Mock, patch
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
import main_workflow as lesson67
from agent_learning.business.tools import DEFAULT_DATA_FILE, get_order
from agent_learning.core.config import Settings
from agent_learning.core.models import SearchFilter
from agent_learning.workflows import human_approval_agent
from test_memory_agent import ScriptedModel, request_tools, tool_call


#（67课新加）检查真实动态暂停、审批参数绑定和模拟执行边界，不访问外部服务。
class HumanApprovalAgentTests(unittest.TestCase):
    #（67课新加）每个测试单独构造可信身份、纯内存资料和会话配置。
    def setUp(self):
        #（67课新加）模型和人工提交的参数都不能覆盖这一可信租户。
        self.filters = SearchFilter(tenant_id="acme", max_security_level=1, doc_type="policy")
        #（67课新加）知识库只是离线替身，不检索数据库或加载模型。
        self.pipeline = Mock()
        #（67课新加）只返回本课需要的规则结果与引用。
        self.pipeline.ask.return_value = {"answer": "规则见 [1]。", "citations": [{"number": 1, "source": "rules.md", "excerpt": "规则原文"}], "status": "answered"}
        #（67课新加）不同测试使用不同内存存档器，即使编号相同也不会继承状态。
        self.config = {"configurable": {"thread_id": "approval-test"}}
        #（67课新加）样例中 A1001 是待支付订单，可以申请模拟取消。
        self.initial = {"question": "请模拟取消 A1001", "tenant_id": "acme"}

    #（67课新加）用现有模型替身建立真实图，只省去网络调用。
    def build(self, responses: list, **kwargs):
        #（67课新加）每一次外层模型调用都记录实际消息和工具说明。
        model = ScriptedModel(responses)
        #（67课新加）保留真实 LangGraph、动态 interrupt 和内存 Checkpoint。
        graph = human_approval_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver(), **kwargs)
        #（67课新加）返回二者，便于同时检查业务结果和模型次数。
        return model, graph

    #（67课新加）先请求取消，再提供一条结束回答；首次 invoke 应停在人工审批前。
    def pause_cancel(self, calls: list | None = None):
        #（67课新加）默认只请求一个敏感操作，不在测试里代替生产节点执行。
        calls = calls if calls is not None else [tool_call("cancel_order", "cancel-1", {"order_id": "A1001"})]
        #（67课新加）批准后正常返回模型总结，拒绝时不应使用第二条响应。
        model, graph = self.build([request_tools(calls), {"role": "assistant", "content": "已模拟取消，原始 JSON 未改。"}])
        #（67课新加）首次运行保存待审批节点，而不是执行模拟操作。
        result = graph.invoke(self.initial, self.config)
        #（67课新加）读取真正的 interrupt 值，不能在测试中伪造审批目标。
        request = result["__interrupt__"][0].value
        #（67课新加）返回暂停结果，允许测试检查恢复前后的完整 State。
        return model, graph, result, request

    #（67课新加）检查每个 assistant 工具请求都获得且只获得一个对应响应。
    def assert_tool_pairs(self, result: dict, expected_ids: list):
        #（67课新加）实际消息顺序应与本次批量工具调用顺序一致。
        ids = [message["tool_call_id"] for message in result["messages"] if message["role"] == "tool"]
        #（67课新加）失败和拒绝也不能留下孤立工具请求。
        self.assertEqual(ids, expected_ids)
        #（67课新加）已完成或停止的批次不能保留待执行工具。
        self.assertEqual(result["pending_tool_calls"], [])

    #（67课新加）模型选择敏感操作后先暂停，不提前执行，不进入第二次模型。
    def test_first_invoke_pauses_before_simulation(self):
        #（67课新加）直接包住真实模拟函数，检查是否过早执行。
        with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）使用实际图运行到动态审批点。
            model, graph, result, request = self.pause_cancel()
        #（67课新加）审批对象同时包含动作、订单、租户、调用编号和模拟模式。
        self.assertEqual(request, {"action": "cancel_order", "order_id": "A1001", "tenant_id": "acme", "tool_call_id": "cancel-1", "mode": "simulate"})
        #（67课新加）第一次只允许模型选工具，不允许模型自行批准。
        self.assertEqual(len(model.requests), 1)
        #（67课新加）实际业务执行必须在人工恢复后才发生。
        simulate.assert_not_called()
        #（67课新加）暂停不是最终回答，也不能冒充已经有工具结果。
        self.assertEqual((result["stop_reason"], result["tool_results"]), ("", []))
        #（67课新加）Checkpoint 中仍有待执行节点。
        self.assertTrue(graph.get_state(self.config).next)

    #（67课新加）同一配置恢复审批，实际调用一次模拟函数并回到模型总结。
    def test_approve_executes_once_and_keeps_original_json(self):
        #（67课新加）读取只读原始字节，确认整个流程没有写业务文件。
        original = DEFAULT_DATA_FILE.read_bytes()
        #（67课新加）包住实际模拟函数，避免仅凭回答文字判断执行成功。
        with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）先取得真实待审批对象。
            model, graph, paused, request = self.pause_cancel()
            #（67课新加）人工决定必须携带未被修改的原审批参数。
            result = graph.invoke(Command(resume={**request, "decision": "approve"}), self.config)
        #（67课新加）审批前后的 invoke 合计只执行一次模拟操作。
        self.assertEqual(simulate.call_count, 1)
        #（67课新加）真实结果明确标注模拟状态与原始状态，不能宣称线上订单已取消。
        data = result["tool_results"][0]["result"]["data"]
        #（67课新加）保留操作对象和来源边界。
        self.assertEqual((data["order_id"], data["tenant_id"], data["status"], data["original_status"], data["simulated"], data["source"]), ("A1001", "acme", "模拟已取消", "待支付", True, "simulation"))
        #（67课新加）当前会话保留模拟已执行编号，供后续请求检查重复。
        self.assertEqual(result["simulated_cancellations"], ["A1001"])
        #（67课新加）模型第二次读到完整工具结果后生成最终文字。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("final_answer", 2))
        #（67课新加）工具响应与原始 call ID 正确配对。
        self.assert_tool_pairs(result, ["cancel-1"])
        #（67课新加）正常结束后没有待审批或待执行节点。
        self.assertEqual(graph.get_state(self.config).next, ())
        #（67课新加）本次模拟不能写 JSON，更不能把模拟状态保存成业务事实。
        self.assertEqual(DEFAULT_DATA_FILE.read_bytes(), original)

    #（67课新加）人工拒绝后直接结束，不执行敏感操作，也不让模型再次劝说批准。
    def test_reject_stops_without_simulation_or_second_model(self):
        #（67课新加）用调用记录验证拒绝后的执行边界。
        with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）运行到实际审批暂停点。
            model, graph, paused, request = self.pause_cancel()
            #（67课新加）原审批对象不变，只增加人工拒绝决定。
            result = graph.invoke(Command(resume={**request, "decision": "reject"}), self.config)
        #（67课新加）拒绝不需要重试和额外模型调用。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("approval_rejected", 1))
        #（67课新加）模拟函数未执行，不留下已取消编号。
        simulate.assert_not_called()
        #（67课新加）取消失败仍返回与请求配对的 Tool 消息。
        self.assert_tool_pairs(result, ["cancel-1"])
        #（67课新加）success 只表示拒绝已正常处理，不表示执行了取消。
        self.assertEqual((result["tool_results"][0]["result"]["data"]["simulated"], result["tool_results"][0]["result"]["data"]["status"]), (False, "人工拒绝"))
        #（67课新加）图已结束而不是保持隐式待审批。
        self.assertEqual(graph.get_state(self.config).next, ())

    #（67课新加）人工提交不能改订单、租户、动作、调用编号、模式或决定格式。
    def test_changed_approval_parameters_are_rejected(self):
        #（67课新加）逐项覆盖可能造成审批错配的参数。
        changes = [{"order_id": "A1002"}, {"tenant_id": "other"}, {"tool_call_id": "other-call"}, {"action": "get_refund"}, {"mode": "real"}, {"decision": True}, {"decision": "yes"}, {"extra": "not-allowed"}]
        #（67课新加）每个场景从一个新的真实暂停状态开始。
        for change in changes:
            #（67课新加）定位具体被篡改字段。
            with self.subTest(change=change):
                #（67课新加）不使用模拟替身代替审批校验。
                with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
                    #（67课新加）取得本次真正待确认的动作。
                    model, graph, paused, request = self.pause_cancel()
                    #（67课新加）在确认参数中故意注入错误，实际运行恢复节点。
                    result = graph.invoke(Command(resume={**request, "decision": "approve", **change}), self.config)
                #（67课新加）错误审批受控结束，不回到模型或执行模拟。
                self.assertEqual((result["stop_reason"], len(model.requests)), ("approval_invalid", 1))
                #（67课新加）审批参数不一致时绝不能执行。
                simulate.assert_not_called()
                #（67课新加）错误响应仍要与模型请求配对。
                self.assert_tool_pairs(result, ["cancel-1"])

    #（67课新加）缺字段、字符串和列表都不能冒充正确的人工审批对象。
    def test_missing_or_wrong_type_approval_is_rejected(self):
        #（67课新加）避免只校验 decision 而漏掉审批目标绑定。
        for payload in ("approve", ["approve"], {"decision": "approve"}):
            #（67课新加）为每种坏格式使用独立图。
            with self.subTest(payload=payload):
                #（67课新加）先在可信目标前暂停。
                model, graph, paused, request = self.pause_cancel()
                #（67课新加）实际执行坏格式恢复，不直接调用校验函数。
                result = graph.invoke(Command(resume=payload), self.config)
                #（67课新加）审批缺少身份绑定不能通过。
                self.assertEqual((result["stop_reason"], len(model.requests)), ("approval_invalid", 1))
                #（67课新加）本次没有任何已模拟取消记录。
                self.assertEqual(result["simulated_cancellations"], [])

    #（67课新加）错误工具 JSON 和额外参数应在人工审批之前停止。
    def test_bad_cancel_tool_arguments_do_not_pause(self):
        #（67课新加）覆盖损坏 JSON、错误顶层类型、缺字段、额外字段和空值。
        arguments = ("{bad json", "[]", "{}", '{"order_id":"A1001","tenant_id":"other"}', '{"order_id":""}', '{"order_id":"   "}', '{"order_id":1001}')
        #（67课新加）每种工具错误都从新的模型响应开始。
        for raw in arguments:
            #（67课新加）将具体 JSON 参数写入失败标记。
            with self.subTest(arguments=raw):
                #（67课新加）工具调用结构有效，仅故意修改工具参数。
                call = tool_call("cancel_order", "bad-args", {"order_id": "A1001"})
                #（67课新加）传递未经自动修复的原始模型参数。
                call["function"]["arguments"] = raw
                #（67课新加）不提供第二次模型响应，意外调用会暴露错误。
                model, graph = self.build([request_tools([call])])
                #（67课新加）真实分支检查参数，不能靠模型说明来保证安全。
                result = graph.invoke(self.initial, self.config)
                #（67课新加）坏参数不能触发人工审批，更不能执行。
                self.assertNotIn("__interrupt__", result)
                #（67课新加）需要明确结束原因，不允许继续循环。
                self.assertTrue(result["stop_reason"])
                #（67课新加）没有新模型调用或成功结果。
                self.assertEqual((len(model.requests), result["tool_results"][0]["result"]["success"]), (1, False))
                #（67课新加）即使失败也保留协议配对。
                self.assert_tool_pairs(result, ["bad-args"])

    #（67课新加）订单不存在、已支付或已完成时不能进入取消审批。
    def test_missing_or_non_pending_order_is_not_approvable(self):
        #（67课新加）只允许本课明确支持的待支付模拟取消。
        for order_id in ("A9999", "A1002", "A1003"):
            #（67课新加）标出对应业务状态。
            with self.subTest(order_id=order_id):
                #（67课新加）包住真实执行函数，保证非法业务状态不会执行。
                with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
                    #（67课新加）模型只发起一次工具请求。
                    model, graph = self.build([request_tools([tool_call("cancel_order", "not-pending", {"order_id": order_id})])])
                    #（67课新加）业务校验应在 interrupt 之前完成。
                    result = graph.invoke(self.initial, self.config)
                #（67课新加）不能让用户批准一个业务上不允许的操作。
                self.assertNotIn("__interrupt__", result)
                #（67课新加）失败和执行次数都明确可检查。
                self.assertEqual((len(model.requests), result["tool_results"][0]["result"]["success"]), (1, False))
                #（67课新加）没有模拟操作发生。
                simulate.assert_not_called()

    #（67课新加）可信租户不匹配时，在模型之前就结束本轮。
    def test_untrusted_tenant_is_rejected_before_model(self):
        #（67课新加）没有预设响应，任何模型调用都不在本次授权范围。
        model, graph = self.build([])
        #（67课新加）租户身份由入口校验，而不是模型或人工输入来修正。
        result = graph.invoke({"question": "取消 A1001", "tenant_id": "other"}, self.config)
        #（67课新加）业务校验和人工审批均不应发生。
        self.assertEqual((result["stop_reason"], model.requests), ("invalid_input", []))
        #（67课新加）无效租户不能进入待确认状态。
        self.assertNotIn("__interrupt__", result)

    #（67课新加）大小写和空格整理后，审批绑定规范化的实际订单号。
    def test_order_id_is_normalized_before_approval(self):
        #（67课新加）按照现有业务 Tool 的规则整理订单号。
        model, graph, result, request = self.pause_cancel([tool_call("cancel_order", "cancel-normalized", {"order_id": " a1001 "})])
        #（67课新加）用户看到的审批编号应该是 JSON 里实际找到的编号。
        self.assertEqual(request["order_id"], "A1001")
        #（67课新加）保留原工具调用 ID，不能重新生成。
        self.assertEqual(request["tool_call_id"], "cancel-normalized")

    #（67课新加）已完成图重复恢复不能重放模拟操作。
    def test_repeated_command_and_none_after_completion_do_not_execute_again(self):
        #（67课新加）执行计数涵盖首次恢复以及之后的重复恢复。
        with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）先得到合法审批参数。
            model, graph, paused, request = self.pause_cancel()
            #（67课新加）保存同一个确认决定，后续故意重复提交。
            command = Command(resume={**request, "decision": "approve"})
            #（67课新加）首次恢复正常完成模拟取消。
            first = graph.invoke(command, self.config)
            #（67课新加）图已结束时再提交同样决定，不应重新进入执行节点。
            repeated = graph.invoke(command, self.config)
            #（67课新加）结束图继续用 None 也不是新一轮输入。
            continued = graph.invoke(None, self.config)
        #（67课新加）重复恢复不能造成重复模拟或额外模型调用。
        self.assertEqual((simulate.call_count, len(model.requests)), (1, 2))
        #（67课新加）原先执行记录和消息都未再增加。
        self.assertEqual((first["simulated_cancellations"], repeated["simulated_cancellations"], continued["simulated_cancellations"]), (["A1001"], ["A1001"], ["A1001"]))
        #（67课新加）整个会话只保留一个本次工具结果。
        self.assertEqual(len(graph.get_state(self.config).values["tool_results"]), 1)

    #（67课新加）同会话新一轮重复取消，返回已模拟说明而不再次审批或执行。
    def test_same_thread_new_round_does_not_repeat_simulation(self):
        #（67课新加）预设两轮模型选择与各自总结。
        responses = [request_tools([tool_call("cancel_order", "first-cancel", {"order_id": "A1001"})]), {"role": "assistant", "content": "首次模拟完成。"}, request_tools([tool_call("cancel_order", "second-cancel", {"order_id": "A1001"})]), {"role": "assistant", "content": "已模拟取消，不重复执行。"}]
        #（67课新加）同图同存档器使用相同 thread_id。
        model, graph = self.build(responses)
        #（67课新加）实际模拟函数负责首次执行，重复请求不能再次调用。
        with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）第一轮先暂停。
            first = graph.invoke(self.initial, self.config)
            #（67课新加）人工批准第一轮操作。
            graph.invoke(Command(resume={**first["__interrupt__"][0].value, "decision": "approve"}), self.config)
            #（67课新加）第二轮是新输入，不是恢复，仍应检查会话执行记录。
            second = graph.invoke({"question": "再模拟取消一次 A1001", "tenant_id": "acme"}, self.config)
        #（67课新加）重复请求不新增审批或模拟执行。
        self.assertEqual((simulate.call_count, second["stop_reason"]), (1, "final_answer"))
        #（67课新加）执行记录跨轮保留，而且不重复添加编号。
        self.assertEqual(second["simulated_cancellations"], ["A1001"])
        #（67课新加）第二轮仍给模型完整工具响应，只是不重复执行。
        self.assertNotIn("__interrupt__", second)
        #（67课新加）多轮消息保留最初问题，证明没有重建无关会话。
        self.assertEqual([message["content"] for message in model.requests[2]["messages"] if message["role"] == "user"], [self.initial["question"], "再模拟取消一次 A1001"])

    #（67课新加）模拟去重仅在当前会话内有效，不能声称不同 thread_id 全局幂等。
    def test_another_thread_requires_its_own_approval(self):
        #（67课新加）两会话各自请求和完成一次模拟。
        responses = [request_tools([tool_call("cancel_order", "thread-one", {"order_id": "A1001"})]), {"role": "assistant", "content": "会话一完成。"}, request_tools([tool_call("cancel_order", "thread-two", {"order_id": "A1001"})]), {"role": "assistant", "content": "会话二完成。"}]
        #（67课新加）共享一张图，靠 thread_id 隔离状态。
        model, graph = self.build(responses)
        #（67课新加）第二会话有自己的审批与执行记录。
        other = {"configurable": {"thread_id": "approval-other"}}
        #（67课新加）记录两个会话的实际模拟调用。
        with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）第一会话申请取消。
            first = graph.invoke(self.initial, self.config)
            #（67课新加）批准第一会话并完成。
            graph.invoke(Command(resume={**first["__interrupt__"][0].value, "decision": "approve"}), self.config)
            #（67课新加）同一订单的第二会话仍必须独立暂停。
            second = graph.invoke(self.initial, other)
            #（67课新加）第二会话还没批准前不应继承已执行记录。
            self.assertEqual(second["simulated_cancellations"], [])
            #（67课新加）批准本会话原始审批请求。
            graph.invoke(Command(resume={**second["__interrupt__"][0].value, "decision": "approve"}), other)
        #（67课新加）两个会话隔离，但没有承诺全局只执行一次。
        self.assertEqual(simulate.call_count, 2)
        #（67课新加）第二会话模型只看到自己的问题。
        self.assertEqual([item["content"] for item in model.requests[2]["messages"] if item["role"] == "user"], [self.initial["question"]])

    #（67课新加）同批先查订单再审批，恢复不应重新执行已经完成的只读节点。
    def test_read_only_call_before_interrupt_is_not_replayed(self):
        #（67课新加）一个 assistant 同时请求先查询、后取消。
        calls = [tool_call("get_order", "read-first", {"order_id": "A1001"}), tool_call("cancel_order", "cancel-second", {"order_id": "A1001"})]
        #（67课新加）拦住旧业务分发器里的实际只读函数，区分前置业务查询与审批内部检查。
        with patch("agent_learning.workflows.agent_loop.get_order", wraps=get_order) as read_order:
            #（67课新加）第一次执行只读查询，然后保存状态并停在审批节点。
            model, graph, paused, request = self.pause_cancel(calls)
            #（67课新加）暂停前已经保存一条只读结果。
            self.assertEqual([item["tool_call_id"] for item in paused["tool_results"]], ["read-first"])
            #（67课新加）批准后从审批节点恢复，不重跑整个工具循环。
            result = graph.invoke(Command(resume={**request, "decision": "approve"}), self.config)
        #（67课新加）前置只读 Tool 只执行一次，不受审批节点重入影响。
        self.assertEqual(read_order.call_count, 1)
        #（67课新加）两条工具请求都得到原 ID 对应结果。
        self.assert_tool_pairs(result, ["read-first", "cancel-second"])
        #（67课新加）一次选工具与一次最终回答，没有人为制造第三次模型调用。
        self.assertEqual(len(model.requests), 2)

    #（67课新加）同批两次取消同订单，首次人工确认后只执行一次模拟。
    def test_two_cancel_calls_for_same_order_execute_only_once(self):
        #（67课新加）模型可以生成多个调用，程序不能依赖模型避免重复。
        calls = [tool_call("cancel_order", "cancel-a", {"order_id": "A1001"}), tool_call("cancel_order", "cancel-b", {"order_id": "A1001"})]
        #（67课新加）记录真实模拟执行次数。
        with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）先批准第一个取消请求。
            model, graph, paused, request = self.pause_cancel(calls)
            #（67课新加）第二条同订单请求读取会话执行记录，不能再暂停或执行。
            result = graph.invoke(Command(resume={**request, "decision": "approve"}), self.config)
        #（67课新加）结果里两条响应仍完整配对。
        self.assert_tool_pairs(result, ["cancel-a", "cancel-b"])
        #（67课新加）只执行一次且只保存一个订单号。
        self.assertEqual((simulate.call_count, result["simulated_cancellations"]), (1, ["A1001"]))
        #（67课新加）不留下第二个审批请求。
        self.assertNotIn("__interrupt__", result)

    #（67课新加）拒绝第一敏感调用后，剩余请求配齐未执行说明，不执行后续查询。
    def test_reject_pairs_and_skips_remaining_batch_calls(self):
        #（67课新加）后续包含规则查询及重复取消，全部需要配对但不能执行。
        calls = [tool_call("cancel_order", "reject-first", {"order_id": "A1001"}), tool_call("ask_knowledge_base", "skip-rag", {"question": "取消规则？"}), tool_call("cancel_order", "skip-cancel", {"order_id": "A1001"})]
        #（67课新加）在第一敏感操作前真实暂停。
        model, graph, paused, request = self.pause_cancel(calls)
        #（67课新加）人工明确拒绝整个后续执行路径。
        result = graph.invoke(Command(resume={**request, "decision": "reject"}), self.config)
        #（67课新加）三条请求都必须有响应，不能丢弃尚未执行的 ID。
        self.assert_tool_pairs(result, ["reject-first", "skip-rag", "skip-cancel"])
        #（67课新加）后面的 RAG 不应运行。
        self.pipeline.ask.assert_not_called()
        #（67课新加）第一条是正常处理的拒绝，但敏感操作没有执行。
        self.assertFalse(result["tool_results"][0]["result"]["data"]["simulated"])
        #（67课新加）其余 Tool 返回未执行，而不是伪造查询成功。
        self.assertTrue(all(not item["result"]["success"] for item in result["tool_results"][1:]))
        #（67课新加）拒绝后不需要额外模型总结。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("approval_rejected", 1))

    #（67课新加）前置只读失败时，同批取消应明确未执行，不能进入审批。
    def test_failed_read_only_call_skips_pending_cancel(self):
        #（67课新加）订单不存在会使第一工具查询失败。
        calls = [tool_call("get_order", "read-failed", {"order_id": "A9999"}), tool_call("cancel_order", "skip-after-failure", {"order_id": "A1001"})]
        #（67课新加）没有额外模型响应，失败直接结束。
        model, graph = self.build([request_tools(calls)])
        #（67课新加）执行真实失败分支。
        result = graph.invoke(self.initial, self.config)
        #（67课新加）失败后取消操作不能进入人工批准队列。
        self.assertNotIn("__interrupt__", result)
        #（67课新加）每条请求都匹配失败或未执行说明。
        self.assert_tool_pairs(result, ["read-failed", "skip-after-failure"])
        #（67课新加）不用第二次模型调用判断是否继续。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("tool_error", 1))

    #（67课新加）普通问答没有敏感动作，直接结束而不是统一在 tools 前暂停。
    def test_plain_answer_does_not_pause(self):
        #（67课新加）模型可以直接生成完整非空回答。
        model, graph = self.build([{"role": "assistant", "content": "请提供需要查询的订单号。"}])
        #（67课新加）运行正常消息路线。
        result = graph.invoke({"question": "你好", "tenant_id": "acme"}, self.config)
        #（67课新加）没有动态审批或新的模拟记录。
        self.assertEqual((result["stop_reason"], len(model.requests), result["simulated_cancellations"]), ("final_answer", 1, []))
        #（67课新加）确认没有沿用第 65 课所有工具前静态暂停的设置。
        self.assertNotIn("__interrupt__", result)

    #（67课新加）规则查询与本地退款查询继续按原工具循环执行，不需要人工审批。
    def test_read_only_and_rag_tools_do_not_pause(self):
        #（67课新加）一次模型请求两个只读工具。
        calls = [tool_call("get_refund", "read-refund", {"order_id": "A1002"}), tool_call("ask_knowledge_base", "read-policy", {"question": "退款通常多久到账？"})]
        #（67课新加）第二次模型读结果生成综合说明。
        model, graph = self.build([request_tools(calls), {"role": "assistant", "content": "退款有两条记录，规则见 [1]。"}])
        #（67课新加）一次 invoke 应完成只读全流程。
        result = graph.invoke({"question": "查 A1002 退款和规则", "tenant_id": "acme"}, self.config)
        #（67课新加）保留原有两条退款记录，不因新增审批改变业务数据。
        self.assertEqual(len(result["tool_results"][0]["result"]["data"]), 2)
        #（67课新加）知识库引用继续保存在工具结果里。
        self.assertEqual(result["tool_results"][1]["result"]["data"]["citations"][0]["source"], "rules.md")
        #（67课新加）仍使用可信过滤对象，不让模型指定资料权限。
        self.pipeline.ask.assert_called_once_with("退款通常多久到账？", self.filters)
        #（67课新加）两个工具响应都正确配对。
        self.assert_tool_pairs(result, ["read-refund", "read-policy"])
        #（67课新加）不新增审批暂停。
        self.assertNotIn("__interrupt__", result)
        #（67课新加）只需要选择工具和最后总结两次模型调用。
        self.assertEqual(len(model.requests), 2)

    #（67课新加）新 schema 只允许订单号，租户和审批决定必须由可信程序提供。
    def test_cancel_schema_is_present_and_has_only_order_id(self):
        #（67课新加）通过真正模型节点观察传入的 schema。
        model, graph = self.build([{"role": "assistant", "content": "您好。"}])
        #（67课新加）不选择工具也应该把可用工具说明带给模型。
        graph.invoke({"question": "你好", "tenant_id": "acme"}, self.config)
        #（67课新加）保留四个原有只读工具，只新增一个取消工具。
        schemas = model.requests[0]["tools"]
        #（67课新加）检查工具名称，没有新增无关课程功能。
        self.assertEqual({item["function"]["name"] for item in schemas}, {"get_order", "get_payment", "get_refund", "ask_knowledge_base", "cancel_order"})
        #（67课新加）取实际取消工具参数说明。
        parameters = next(item["function"]["parameters"] for item in schemas if item["function"]["name"] == "cancel_order")
        #（67课新加）模型不能提供审批、租户、文件路径或真实执行模式。
        self.assertEqual((set(parameters["properties"]), parameters["required"], parameters["additionalProperties"]), ({"order_id"}, ["order_id"], False))

    #（67课新加）上下文预算也要包含新增敏感工具，不能只计算旧四个 schema。
    def test_context_budget_includes_new_cancel_schema(self):
        #（67课新加）先用一次正常调用获得真正的提示词和工具定义。
        model, graph = self.build([{"role": "assistant", "content": "您好。"}])
        #（67课新加）输入内容固定，第二张图会使用相同提示词。
        initial = {"question": "你好", "tenant_id": "acme"}
        #（67课新加）获得模型真正接收到的完整初次上下文。
        graph.invoke(initial, self.config)
        #（67课新加）以实际 messages 与五工具说明的大小减一作为预算。
        request = model.requests[0]
        #（67课新加）这里是字符保护预算，不伪称精确 Token 计算。
        budget = len(json.dumps({"messages": request["messages"], "tools": request["tools"]}, ensure_ascii=False)) - 1
        #（67课新加）空响应列表保证不应发出超预算请求。
        blocked_model, blocked_graph = self.build([], max_context_chars=budget)
        #（67课新加）实际节点应在模型之前阻止超预算上下文。
        result = blocked_graph.invoke(initial, self.config)
        #（67课新加）多出的新 schema 也被计入，不能错误地允许请求。
        self.assertEqual((result["stop_reason"], blocked_model.requests), ("context_budget", []))

    #（67课新加）保留上一课资料范围、轮数和上下文预算的建图参数检查。
    def test_invalid_build_parameters_are_rejected(self):
        #（67课新加）非法历史或预算参数不能等到运行模型后才失败。
        for history, chars in ((-1, 12000), (2, 0)):
            #（67课新加）逐项检查配置边界。
            with self.subTest(history=history, chars=chars):
                #（67课新加）使用已有图构建校验，不增加测试专用校验。
                with self.assertRaises(ValueError):
                    #（67课新加）不进入模型或工具。
                    self.build([], max_history_turns=history, max_context_chars=chars)
        #（67课新加）RAG 的 record 文档限制也不应被取消审批绕过。
        with self.assertRaises(ValueError):
            #（67课新加）只构建图，传入错误规则资料范围。
            human_approval_agent.build_graph(ScriptedModel([]), self.pipeline, SearchFilter("acme", doc_type="record"), InMemorySaver())

    #（67课新加）动态暂停时 None 不是批准，只会再次停在同一审批节点。
    def test_none_during_pause_does_not_approve(self):
        #（67课新加）检查实际模拟函数没有被误当成恢复动作执行。
        with patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）第一次 invoke 取得动态暂停点。
            model, graph, paused, request = self.pause_cancel()
            #（67课新加）故意使用旧静态断点的继续写法，不能提供人工决定。
            repeated = graph.invoke(None, self.config)
        #（67课新加）没有批准参数就没有执行。
        simulate.assert_not_called()
        #（67课新加）恢复仍显示原审批目标，并非自动跳过审批。
        self.assertEqual(repeated["__interrupt__"][0].value, request)
        #（67课新加）同一取消请求保存在存档里，继续等待人工选择。
        snapshot = graph.get_state(self.config)
        #（67课新加）具体节点仍是审批，不重走模型或准备节点。
        self.assertEqual(snapshot.next, ("approval",))
        #（67课新加）取消调用和首次工具选择次数都没有改变。
        self.assertEqual((snapshot.values["pending_tool_calls"][0]["id"], len(model.requests)), ("cancel-1", 1))

    #（67课新加）Console 模糊输入不能默认确认，只有明确 y/approve 才能恢复。
    def test_console_approval_rejects_ambiguous_input_before_approve(self):
        #（67课新加）检查两种明确批准输入都映射为严格 approve 决定。
        for choice in ("y", "approve"):
            #（67课新加）每种输入使用真实审批图。
            with self.subTest(choice=choice):
                #（67课新加）第一次正常运行到暂停，不读配置文件。
                model, graph, paused, request = self.pause_cancel()
                #（67课新加）先给空输入、切会话和模糊回答，最后才明确批准。
                with patch("builtins.input", side_effect=["", "/new", "yes", choice]) as user_input, patch("builtins.print"), patch.object(graph, "invoke", wraps=graph.invoke) as invoke:
                    #（67课新加）实际调用入口 helper，不能由测试自己构造正确决定。
                    result = lesson67.resume_approvals(graph, paused, self.config)
                #（67课新加）前三次错误输入没有调用 graph.invoke，只有明确批准才恢复。
                self.assertEqual((user_input.call_count, invoke.call_count), (4, 1))
                #（67课新加）恢复值保留全部审批目标，仅加入决定。
                self.assertEqual(invoke.call_args.args[0].resume, {**request, "decision": "approve"})
                #（67课新加）确认后图正常进入模型总结。
                self.assertEqual((result["stop_reason"], len(model.requests)), ("final_answer", 2))

    #（67课新加）Console 的 n/reject 两种明确拒绝都恢复为拒绝分支。
    def test_console_explicit_reject_stops_without_second_model(self):
        #（67课新加）拒绝格式由入口规范化，不让用户修改其他审批参数。
        for choice in ("n", "reject"):
            #（67课新加）两种拒绝输入都需要验证。
            with self.subTest(choice=choice):
                #（67课新加）取得实际待审批结果。
                model, graph, paused, request = self.pause_cancel()
                #（67课新加）替换用户交互，不替换实际图恢复。
                with patch("builtins.input", return_value=choice), patch("builtins.print"), patch.object(graph, "invoke", wraps=graph.invoke) as invoke:
                    #（67课新加）入口生成真实 Command(resume=...)。
                    result = lesson67.resume_approvals(graph, paused, self.config)
                #（67课新加）拒绝后没有第二次模型调用。
                self.assertEqual((result["stop_reason"], len(model.requests)), ("approval_rejected", 1))
                #（67课新加）人工决定与原目标绑定，不能只发送一个布尔值。
                self.assertEqual(invoke.call_args.args[0].resume, {**request, "decision": "reject"})

    #（67课新加）审批中 q 只退出交互，不提交恢复值，也不执行操作。
    def test_console_quit_keeps_pending_interrupt_without_execution(self):
        #（67课新加）运行到真实敏感操作暂停点。
        model, graph, paused, request = self.pause_cancel()
        #（67课新加）检查 helper 是否误调用恢复或取消函数。
        with patch("builtins.input", return_value="q"), patch("builtins.print"), patch.object(graph, "invoke", wraps=graph.invoke) as invoke, patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）q 应告诉 main 退出，而不是默认拒绝或批准。
            result = lesson67.resume_approvals(graph, paused, self.config)
        #（67课新加）入口退出信号与图恢复的 None 输入不是同一回事。
        self.assertIsNone(result)
        #（67课新加）没有向图提交任何恢复值。
        invoke.assert_not_called()
        #（67课新加）待审批操作未执行。
        simulate.assert_not_called()
        #（67课新加）当前进程里仍停在审批；不承诺进程退出后还能保留内存。
        self.assertEqual((graph.get_state(self.config).next, len(model.requests)), (("approval",), 1))

    #（67课新加）完整 Console 保留会话追问，并在 /new 后重新独立审批。
    def test_console_main_supports_approve_follow_up_new_thread_and_reject(self):
        #（67课新加）真实配置对象在内存中创建，不读取环境文件。
        settings = Settings(llm_api_key="test-only")
        #（67课新加）首会话批准、追问，新会话拒绝；仅提供应发生的四次模型响应。
        responses = [request_tools([tool_call("cancel_order", "console-cancel", {"order_id": "A1001"})]), {"role": "assistant", "content": "首会话模拟取消。"}, {"role": "assistant", "content": "仅模拟，JSON 未修改。"}, request_tools([tool_call("cancel_order", "new-cancel", {"order_id": "A1001"})])]
        #（67课新加）保留真实图和存档，替换外部初始化与 Console 输入。
        model, graph = self.build(responses)
        #（67课新加）审批输入在当前轮消耗，不作为新问题写入消息历史。
        with patch.object(lesson67, "load_settings", return_value=settings), patch.object(lesson67, "CompatibleToolModel", return_value=model), patch.object(lesson67, "build_pipeline", return_value=self.pipeline), patch.object(lesson67, "build_graph", return_value=graph) as builder, patch.object(lesson67, "USE_OLLAMA", False), patch("builtins.input", side_effect=["请取消 A1001", "y", "它取消了吗？", "/new", "请取消 A1001", "n", "q"]), patch("builtins.print"), patch.object(human_approval_agent, "simulate_cancel_order", wraps=human_approval_agent.simulate_cancel_order) as simulate:
            #（67课新加）真实入口自行管理普通输入和审批恢复。
            lesson67.main()
        #（67课新加）不因多轮问题而重建图或存档。
        self.assertEqual(builder.call_count, 1)
        #（67课新加）批准只在第一会话执行一次，新会话的拒绝不执行。
        self.assertEqual(simulate.call_count, 1)
        #（67课新加）首会话追问保留原始问题与实际工具结果。
        self.assertEqual([item["content"] for item in model.requests[2]["messages"] if item["role"] == "user"], ["请取消 A1001", "它取消了吗？"])
        #（67课新加）新会话不继承旧轮问题。
        self.assertEqual([item["content"] for item in model.requests[3]["messages"] if item["role"] == "user"], ["请取消 A1001"])
        #（67课新加）会话一保留自己的模拟记录。
        first = graph.get_state({"configurable": {"thread_id": lesson67.THREAD_ID}}).values
        #（67课新加）会话二拒绝，不从会话一继承取消执行记录。
        second = graph.get_state({"configurable": {"thread_id": f"{lesson67.THREAD_ID}-2"}}).values
        #（67课新加）明确验证两会话状态与执行边界。
        self.assertEqual((first["simulated_cancellations"], second["simulated_cancellations"], second["stop_reason"]), (["A1001"], [], "approval_rejected"))
        #（67课新加）入口保留 Debug 无超时与不下载本地模型的配置。
        self.assertEqual((settings.llm_timeout, settings.local_files_only), (None, True))
