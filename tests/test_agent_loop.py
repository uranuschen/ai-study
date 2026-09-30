# 导入 JSON，构造模型参数并检查回传结果。
import json
# 导入深拷贝，保存每轮模型实际看到的消息。
from copy import deepcopy
# 导入标准测试框架。
import unittest
# 导入替身工具，阻止测试访问真实模型和配置文件。
from unittest.mock import Mock, patch
# 导入 SDK 的真实响应类型，验证消息序列化。
from openai.types.chat import ChatCompletion
# 导入 Console 入口，测试实际组装流程。
import main_workflow_recovery as main_workflow
# 导入纯内存配置对象，不读取环境文件。
from agent_learning.core.config import Settings
# 导入本课图与工具说明。
from agent_learning.workflows.agent_loop import TOOL_SCHEMAS, build_graph
# 导入真实模型适配类，网络客户端将在测试中替换。
from agent_learning.workflows.tool_model import CompatibleToolModel


# 方法功能：创建一条具有真实协议结构的模型工具请求。
def tool_call(name: str, call_id: str, arguments: str = '{"order_id": "A1002"}') -> dict:
    # 参数保留为 JSON 字符串，交给实际分发代码解析。
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


# 方法功能：把一批工具请求包装为 assistant 消息。
def request_tools(calls: list) -> dict:
    # 空文本表示模型这一轮选择调用工具。
    return {"role": "assistant", "content": "", "tool_calls": calls}


# 类职责：按预设顺序返回模型消息，仅用于离线协议和控制流程测试。
class ScriptedModel:
    # 方法功能：保存待返回消息；这些预设内容不是真实模型判断。
    def __init__(self, responses: list, repeat: bool = False):
        # 测试可以提供正常消息或异常对象。
        self.responses = responses
        # 用重复工具请求验证循环上限。
        self.repeat = repeat
        # 保存每次模型收到的完整消息。
        self.requests = []

    # 方法功能：使用和真实模型相同的接口接收消息与工具说明。
    def chat_with_tools(self, messages: list, tools: list) -> dict:
        # 留存独立副本，避免后续节点影响历史断言。
        self.requests.append({"messages": deepcopy(messages), "tools": deepcopy(tools)})
        # 普通测试按次序取下一条响应。
        index = len(self.requests) - 1
        # 重复模式每一轮都返回同一种工具请求。
        if self.repeat:
            # 复用第一条预设内容，模拟持续请求工具的模型。
            index = 0
        # 超出预设次数会报错，让测试暴露多余模型调用。
        response = self.responses[index]
        # 异常对象用于模拟请求失败。
        if isinstance(response, Exception):
            # 让真实模型节点捕获该异常。
            raise response
        # 返回独立字典，不让图修改预设。
        response = deepcopy(response)
        # 重复模式为每轮调用分配不同 ID。
        if self.repeat:
            # 只为本测试的单一重复工具请求修改调用 ID。
            response["tool_calls"][0]["id"] = f"repeat_{len(self.requests)}"
        # 交给真实 LangGraph 执行后续节点。
        return response

    # 方法功能：兼容当前第 63 课 Console 的用量接口，仍不访问真实 API。
    def request_with_tools(self, messages: list, tools: list, timeout=None, max_tokens: int = 1200) -> dict:
        # 复用旧课的预设消息，保持旧图行为不变。
        message = self.chat_with_tools(messages, tools)
        # 返回明确的测试用量，不把 usage 混入 assistant 消息。
        return {"message": message, "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}


# 类职责：使用真实 LangGraph 和 JSON Tool 验证完整消息循环与退出边界。
class AgentLoopTests(unittest.TestCase):
    # 方法功能：完整的三轮 Tool 结果逐次回传给模型，第四次模型调用给出答案。
    def test_full_loop_returns_each_tool_result_to_model(self):
        # 每次只请求下一步，验证真实循环而不是一轮执行全部工具。
        model = ScriptedModel([
            # 第一轮查订单。
            request_tools([tool_call("get_order", "order_call")]),
            # 第二轮查支付。
            request_tools([tool_call("get_payment", "payment_call")]),
            # 第三轮查退款。
            request_tools([tool_call("get_refund", "refund_call")]),
            # 第四轮返回最终答案。
            {"role": "assistant", "content": "离线预设回答：已收到订单、支付、退款结果。"},
        # 结束预设响应列表。
        ])
        # 实际创建并执行本课图，业务 Tool 读取项目 JSON。
        result = build_graph(model, max_steps=4).invoke({"question": "完整检查 A1002", "tenant_id": "acme"})
        # 最后一轮生成回答也计入模型调用次数。
        self.assertEqual(result["model_steps"], 4)
        # 最后一轮恰好到上限但已给出答案，应算自然结束。
        self.assertEqual(result["stop_reason"], "final_answer")
        # 查询历史的顺序与模型请求一致。
        self.assertEqual([item["tool_name"] for item in result["tool_results"]], ["get_order", "get_payment", "get_refund"])
        # 第二次模型调用必须看得到第一轮工具请求和结果。
        self.assertEqual([item["role"] for item in model.requests[1]["messages"]], ["system", "user", "assistant", "tool"])
        # tool 消息必须使用对应 assistant 请求的 ID。
        self.assertEqual(model.requests[1]["messages"][-1]["tool_call_id"], "order_call")
        # 模型实际收到的是当前租户的订单事实。
        self.assertEqual(json.loads(model.requests[1]["messages"][-1]["content"])["data"]["amount"], "299.00")
        # 最后一次调用应看到三条 Tool 结果，不能丢弃早期证据。
        self.assertEqual([item["tool_call_id"] for item in model.requests[3]["messages"] if item["role"] == "tool"], ["order_call", "payment_call", "refund_call"])
        # 多笔退款都已回传。
        self.assertEqual(len(json.loads(model.requests[3]["messages"][-1]["content"])["data"]), 2)
        # 返回的工具说明保持一致。
        self.assertEqual(model.requests[0]["tools"], TOOL_SCHEMAS)

    # 方法功能：模型可以直接回答或要求用户补订单号，不强制查三个 Tool。
    def test_direct_answer_does_not_execute_tools(self):
        # 缺少编号时模型可直接澄清。
        model = ScriptedModel([{"role": "assistant", "content": "请提供订单号。"}])
        # 替换业务分发函数，验证不会执行任何 Tool。
        with patch("agent_learning.workflows.agent_loop.dispatch_tool") as dispatch:
            # 执行真实图。
            result = build_graph(model).invoke({"question": "帮我查询退款", "tenant_id": "acme"})
        # 无工具请求时一次模型调用就结束。
        self.assertEqual((result["model_steps"], result["stop_reason"], result["tool_results"]), (1, "final_answer", []))
        # 模型原始文字作为回答返回。
        self.assertEqual(result["answer"], "请提供订单号。")
        # 业务分发没有被触发。
        dispatch.assert_not_called()

    # 方法功能：同一轮多次工具调用均有配对结果，且租户由入口注入。
    def test_multiple_calls_are_paired_and_tenant_is_trusted(self):
        # 这一轮可以直接查询支付和退款。
        model = ScriptedModel([request_tools([tool_call("get_payment", "p"), tool_call("get_refund", "r")]), {"role": "assistant", "content": "已收到。"}])
        # 入口身份为 other，即使问题要求 acme，也不能改变工具权限。
        result = build_graph(model).invoke({"question": "查询 acme 的 A1002", "tenant_id": "other"})
        # 第二轮模型收到同一批调用的全部结果。
        tool_messages = model.requests[1]["messages"][-2:]
        # 调用 ID 与请求一一匹配。
        self.assertEqual([item["tool_call_id"] for item in tool_messages], ["p", "r"])
        # 支付和退款都只返回 other 的记录。
        for item in result["tool_results"]:
            # 该租户各有一条记录。
            self.assertEqual(len(item["result"]["data"]), 1)
            # 不能混入同号 acme 的记录。
            self.assertEqual(item["result"]["data"][0]["tenant_id"], "other")

    # 方法功能：持续请求 Tool 的模型会在指定次数后受控结束。
    def test_repeated_tool_requests_stop_exactly_at_limit(self):
        # 同时覆盖最小上限、常用值和超过旧默认图步数的情况。
        for limit in (1, 5, 30):
            # 分别标记每个上限。
            with self.subTest(limit=limit):
                # 模拟每轮继续请求订单查询。
                model = ScriptedModel([request_tools([tool_call("get_order", "repeat")])], repeat=True)
                # 使用图自身设置的调度余量执行，不手动提高测试配置。
                result = build_graph(model, max_steps=limit).invoke({"question": "查询 A1002", "tenant_id": "acme"})
                # 到达业务上限时正常返回，而不是 GraphRecursionError。
                self.assertEqual(result["stop_reason"], "max_steps")
                # 不能为了额外总结再多调用一次模型。
                self.assertEqual(len(model.requests), limit)
                # 最后一轮工具仍然执行并被保留。
                self.assertEqual(len(result["tool_results"]), limit)
                # 最后一个 assistant 工具请求已有对应结果。
                self.assertEqual(result["messages"][-1]["role"], "tool")
                # 本轮待执行调用应清空。
                self.assertEqual(result["pending_tool_calls"], [])
                # 必须明确告知答案尚未生成完整。
                self.assertIn("尚未生成完整回答", result["answer"])

    # 方法功能：错误工具名、参数 JSON 和越权参数均回传受控失败。
    def test_dispatch_errors_return_tool_messages_without_execution(self):
        # 每个错误都必须有对应 tool_call_id 结果，保证协议完整。
        calls = [
            # 未开放写操作工具。
            tool_call("cancel_order", "unknown"),
            # 参数字符串不是合法 JSON。
            tool_call("get_order", "bad_json", "{broken"),
            # JSON 列表不是参数字典。
            tool_call("get_order", "bad_type", "[]"),
            # 模型不能覆盖可信租户。
            tool_call("get_order", "tenant_override", '{"order_id":"A1002","tenant_id":"other"}'),
            # 模型不能覆盖业务数据路径。
            tool_call("get_order", "path_override", '{"order_id":"A1002","data_file":"elsewhere"}'),
            # 缺少订单号也不能执行。
            tool_call("get_order", "missing", "{}"),
            # 错误类型不能隐式转换为订单号。
            tool_call("get_order", "number", '{"order_id":123}'),
        # 结束无效调用列表。
        ]
        # 下一轮模型可以读取错误并回答。
        model = ScriptedModel([request_tools(calls), {"role": "assistant", "content": "工具参数无效，已结束。"}])
        # 监听底层订单函数，确保参数失败未进入业务查询。
        with patch("agent_learning.workflows.agent_loop.get_order") as get_order:
            # 执行真实分发和消息回传。
            result = build_graph(model).invoke({"question": "查询 A1002", "tenant_id": "acme"})
        # 每条失败都被保留。
        self.assertEqual(len(result["tool_results"]), len(calls))
        # 所有失败都明确返回 success=false。
        self.assertTrue(all(not item["result"]["success"] for item in result["tool_results"]))
        # 下一轮模型看得到全部失败的对应 ID。
        self.assertEqual([item["tool_call_id"] for item in model.requests[1]["messages"] if item["role"] == "tool"], [item["id"] for item in calls])
        # 参数校验失败不会调用业务函数。
        get_order.assert_not_called()

    # 方法功能：业务查无记录和 Tool 意外异常都以结果形式回传模型。
    def test_business_failure_and_exception_are_returned(self):
        # 分别覆盖正常业务失败和意外执行异常。
        for tool_exception in (False, True):
            # 标记当前测试场景。
            with self.subTest(tool_exception=tool_exception):
                # 查询不存在的订单。
                model = ScriptedModel([request_tools([tool_call("get_order", "missing", '{"order_id":"A9999"}')]), {"role": "assistant", "content": "订单查询失败。"}])
                # 意外异常场景使用替身，正常场景运行实际 Tool。
                if tool_exception:
                    # 模拟业务执行失败。
                    with patch("agent_learning.workflows.agent_loop.get_order", side_effect=RuntimeError("测试异常")):
                        # 真正执行整个图。
                        result = build_graph(model).invoke({"question": "查询 A9999", "tenant_id": "acme"})
                # 正常查询会返回不存在订单的业务失败。
                else:
                    # 使用真实 JSON Tool。
                    result = build_graph(model).invoke({"question": "查询 A9999", "tenant_id": "acme"})
                # 失败消息应到达下一次模型请求。
                self.assertFalse(json.loads(model.requests[1]["messages"][-1]["content"])["success"])
                # 图由模型读取错误并自然结束。
                self.assertEqual(result["stop_reason"], "final_answer")

    # 方法功能：后续模型请求失败时，前一轮真实 Tool 结果仍被保留。
    def test_model_error_preserves_previous_evidence(self):
        # 第一轮查退款，第二轮模拟模型连接失败。
        model = ScriptedModel([request_tools([tool_call("get_refund", "r")]), RuntimeError("测试连接失败")])
        # 运行实际图。
        result = build_graph(model).invoke({"question": "查询 A1002 的退款", "tenant_id": "acme"})
        # 模型失败有独立退出原因。
        self.assertEqual((result["stop_reason"], result["model_steps"]), ("model_error", 2))
        # 已取得的两笔退款仍存在。
        self.assertEqual(len(result["tool_results"][0]["result"]["data"]), 2)
        # 对用户不输出原始异常内容。
        self.assertNotIn("测试连接失败", result["answer"])

    # 方法功能：模型返回空内容时结束，避免无效循环。
    def test_empty_response_stops(self):
        # 同时没有工具请求和回答文字。
        model = ScriptedModel([{"role": "assistant", "content": "  "}])
        # 执行完整图。
        result = build_graph(model).invoke({"question": "你好", "tenant_id": "acme"})
        # 空响应只消耗一次模型调用。
        self.assertEqual((result["stop_reason"], result["model_steps"]), ("empty_response", 1))

    # 方法功能：缺少或重复调用 ID 时，阻止无法配对的工具执行。
    def test_invalid_model_protocol_stops_before_tools(self):
        # 覆盖错误角色、错误调用列表和重复调用 ID。
        responses = [
            # 不能把模型伪造的 tool 角色直接加入历史。
            {"role": "tool", "content": "wrong"},
            # 工具调用不是列表。
            {"role": "assistant", "tool_calls": "wrong"},
            # 重复 ID 无法明确匹配两条返回。
            request_tools([tool_call("get_order", "same"), tool_call("get_refund", "same")]),
            # 空 ID 无法配对。
            request_tools([tool_call("get_order", "")]),
        # 结束无效响应列表。
        ]
        # 每种情况均独立执行。
        for response in responses:
            # 标记当前无效响应。
            with self.subTest(response=response):
                # 模型只返回这一条无效响应。
                model = ScriptedModel([response])
                # 分发函数不应收到任何调用。
                with patch("agent_learning.workflows.agent_loop.dispatch_tool") as dispatch:
                    # 真实模型节点负责检测协议问题。
                    result = build_graph(model).invoke({"question": "查询 A1002", "tenant_id": "acme"})
                # 无效协议按模型错误受控退出。
                self.assertEqual(result["stop_reason"], "model_error")
                # 不执行不可回传的工具请求。
                dispatch.assert_not_called()

    # 方法功能：输入与预算校验发生在模型调用之前。
    def test_invalid_input_and_budget_do_not_call_model(self):
        # 空预设模型不应收到请求。
        model = ScriptedModel([])
        # 空问题和缺租户分别应受控结束。
        for question, tenant in ((" ", "acme"), ("查 A1002", "")):
            # 执行输入检查路径。
            result = build_graph(model).invoke({"question": question, "tenant_id": tenant})
            # 不消耗模型调用次数。
            self.assertEqual((result["stop_reason"], result["model_steps"]), ("invalid_input", 0))
        # 所有无效输入都没有进入模型。
        self.assertEqual(model.requests, [])
        # 配置中的无效上限应在构图时就报错。
        for limit in (0, -1, 1.5, True):
            # 确认错误类型清晰。
            with self.assertRaises(ValueError):
                # 不执行图或发出请求。
                build_graph(model, max_steps=limit)


# 类职责：验证真实 SDK 请求组装和 Console 接线，所有外部请求均替换。
class ToolModelAdapterTests(unittest.TestCase):
    # 方法功能：确认工具说明、历史、自动选择和无隐式重试传入 SDK。
    def test_sdk_request_and_assistant_message_roundtrip(self):
        # 构造真实 SDK 可解析的 assistant 消息，附带可选协议字段。
        message = request_tools([tool_call("get_refund", "r")])
        # 外部兼容接口可能要求下一轮携带该字段。
        message["reasoning_content"] = "offline protocol fixture"
        # 使用真实 SDK 响应类型验证 model_dump 的格式。
        response = ChatCompletion(id="test", object="chat.completion", created=0, model="test", choices=[{"index": 0, "finish_reason": "tool_calls", "message": message}])
        # 所有凭证均为测试占位值，不读取用户配置。
        settings = Settings(llm_api_key="test-only", llm_model="test-model", llm_timeout=7)
        # 替换客户端本身，避免真实网络调用。
        with patch("agent_learning.workflows.tool_model.OpenAI") as client_class:
            # 模拟客户端上下文管理器。
            client = client_class.return_value.__enter__.return_value
            # 模拟完整的 SDK 响应。
            client.chat.completions.create.return_value = response
            # 调用真实适配方法。
            result = CompatibleToolModel(settings).chat_with_tools([{"role": "user", "content": "查退款"}], TOOL_SCHEMAS)
        # tool_call_id 及参数字符串完整保留。
        self.assertEqual(result["tool_calls"], message["tool_calls"])
        # 可选协议字段必须保留供下一轮回传。
        self.assertEqual(result["reasoning_content"], message["reasoning_content"])
        # SDK 不隐式增加请求次数。
        self.assertEqual(client_class.call_args.kwargs["max_retries"], 0)
        # 使用已有请求超时。
        self.assertEqual(client_class.call_args.kwargs["timeout"], 7)
        # 真实请求包含模型选择工具所需的信息。
        self.assertEqual(client.chat.completions.create.call_args.kwargs["tools"], TOOL_SCHEMAS)
        # 模型可以按问题选择工具或直接回答。
        self.assertEqual(client.chat.completions.create.call_args.kwargs["tool_choice"], "auto")

    # 方法功能：被截断的生成结果不能当成最终答案或执行请求。
    def test_truncated_response_is_rejected(self):
        # SDK 以 length 表示生成达到长度限制。
        response = Mock(choices=[Mock(finish_reason="length")])
        # 阻止真实网络调用。
        with patch("agent_learning.workflows.tool_model.OpenAI") as client_class:
            # 返回截断响应。
            client_class.return_value.__enter__.return_value.chat.completions.create.return_value = response
            # 适配层必须报错，模型节点再生成受控结束说明。
            with self.assertRaises(ValueError):
                # 使用纯内存配置。
                CompatibleToolModel(Settings(llm_api_key="test-only")).chat_with_tools([], TOOL_SCHEMAS)

    # 方法功能：真实入口能接通模型对象、实际 JSON Tool 和结果打印。
    def test_console_entry_runs_offline_with_injected_model(self):
        # 预设一次退款查询和最终回答。
        model = ScriptedModel([request_tools([tool_call("get_refund", "r")]), {"role": "assistant", "content": "离线入口验证完成。"}])
        # 同时替换配置、模型对象、输入和打印，不读取真实环境文件。
        with patch.object(main_workflow, "load_settings", return_value=Settings()), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch("builtins.input", return_value="查 A1002 的退款"), patch("builtins.print") as output:
            # 执行真实 main 和真实图。
            main_workflow.main()
        # 必须完成一次 Tool 调用和一次最终回答。
        self.assertEqual(len(model.requests), 2)
        # Console 应展示自然退出和保留结果。
        self.assertIn("final_answer", str(output.call_args_list))
        # 实际业务记录应出现在打印结果里。
        self.assertIn("R10021", str(output.call_args_list))


# 允许从 IDE 单独运行这组离线验证。
if __name__ == "__main__":
    # 所有模型调用均由替身提供，不访问 LLM、数据库或模型下载服务。
    unittest.main()
