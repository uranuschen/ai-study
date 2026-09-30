# 导入 JSON，构造工具参数并读取模型收到的工具结果。
import json
# 导入深拷贝，避免后续节点修改测试历史。
from copy import deepcopy
# 导入标准测试框架。
import unittest
# 导入内存替身，隔离配置、模型、数据库和本地模型加载。
from unittest.mock import Mock, patch
# 导入本课 Console 入口，验证真实接线。
import main_workflow
# 导入普通配置对象，测试不读取环境文件。
from agent_learning.core.config import Settings
# 导入可信过滤对象，验证规则资料和租户边界。
from agent_learning.core.models import SearchFilter
# 导入本课实际实现，测试不复制 Agent 的执行逻辑。
from agent_learning.workflows.rag_agent import TOOL_SCHEMAS, ask_knowledge_base, build_graph


# 方法功能：创建一条模型返回的工具调用。
def tool_call(name: str, call_id: str, arguments: dict) -> dict:
    # 参数使用真实 Tool Calling 所要求的 JSON 字符串。
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}


# 方法功能：创建一轮 assistant 的工具请求消息。
def request_tools(calls: list) -> dict:
    # 工具请求阶段没有最终文字回答。
    return {"role": "assistant", "content": "", "tool_calls": calls}


# 类职责：按预设顺序返回模型消息，不访问任何真实模型。
class ScriptedModel:
    # 方法功能：保存预设消息和每次请求内容。
    def __init__(self, responses: list):
        # 响应也可以是异常，用来检查受控结束。
        self.responses = responses
        # 保存独立的消息和工具说明副本。
        self.requests = []

    # 方法功能：采用实际模型的接口，记录消息并返回本轮预设。
    def chat_with_tools(self, messages: list, tools: list) -> dict:
        # 保存模型实际看到的完整上下文。
        self.requests.append({"messages": deepcopy(messages), "tools": deepcopy(tools)})
        # 多余调用会超出列表，帮助发现不应发生的重试。
        response = self.responses[len(self.requests) - 1]
        # 模拟真实模型请求抛出的异常。
        if isinstance(response, Exception):
            # 交给实际节点处理，不在测试替身内转换错误。
            raise response
        # 返回独立副本，避免执行节点修改预设。
        return deepcopy(response)


# 类职责：离线检查业务事实、规则资料和工具消息的最简循环。
class RAGAgentTests(unittest.TestCase):
    # 方法功能：准备可信过滤和纯内存 RAG 替身。
    def setUp(self):
        # 默认只查询 acme 租户的一级规则资料。
        self.filters = SearchFilter(tenant_id="acme", max_security_level=1, doc_type="policy")
        # 引用包含原文、位置和来源，不能在包装时丢掉。
        self.citations = [{"number": 1, "chunk_id": "chunk-1", "document_id": "doc-1", "title": "退款规则", "source": "rules/refund.md", "location": {"page": 2}, "excerpt": "退款审核通过后，按规则处理到账。"}]
        # trace 只用于原 RAG 内部诊断，不属于本课回传内容。
        self.rag_result = {"answer": "退款到账需按规则处理。[1]", "citations": self.citations, "status": "answered", "trace": {"internal": "不回传"}}
        # ask 的替身不会查询数据库或加载任何模型。
        self.pipeline = Mock()
        # 预设完整的 RAG 返回结构。
        self.pipeline.ask.return_value = self.rag_result

    # 方法功能：查退款、查规则、综合回答，每轮工具结果都回传给模型。
    def test_refund_then_rag_then_final_answer(self):
        # 模型选择顺序由预设消息表示，业务 Tool 使用实际 JSON。
        model = ScriptedModel([
            # 第一轮获取订单事实。
            request_tools([tool_call("get_refund", "refund-call", {"order_id": "A1002"})]),
            # 第二轮查询知识库规则。
            request_tools([tool_call("ask_knowledge_base", "rag-call", {"question": "退款审核通过后多久到账？"})]),
            # 第三轮生成最终回答。
            {"role": "assistant", "content": "退款事实以记录更新时间为准，到账规则见 [1]。"},
        # 结束模型响应列表。
        ])
        # 实际执行本课图，不连接任何外部服务。
        result = build_graph(model, self.pipeline, self.filters).invoke({"question": "查询 A1002 的退款及到账规则", "tenant_id": "acme"})
        # 模型最终回答触发自然结束。
        self.assertEqual(result["stop_reason"], "final_answer")
        # 两类工具都出现在历史中。
        self.assertEqual([item["tool_name"] for item in result["tool_results"]], ["get_refund", "ask_knowledge_base"])
        # 业务数据中的更新时间必须仍然存在。
        self.assertTrue(all(item["updated_at"] for item in result["tool_results"][0]["result"]["data"]))
        # 包装后的引用完整保留，且不混入内部 trace。
        self.assertEqual(result["tool_results"][1]["result"]["data"], {"answer": self.rag_result["answer"], "citations": self.citations, "status": "answered"})
        # 最后一轮包含两个正确配对的工具结果。
        tool_messages = [item for item in model.requests[2]["messages"] if item["role"] == "tool"]
        # API 调用 ID 不是订单号，必须原样匹配。
        self.assertEqual([item["tool_call_id"] for item in tool_messages], ["refund-call", "rag-call"])
        # 模型看到的 RAG 引用和程序保留的引用一致。
        self.assertEqual(json.loads(tool_messages[1]["content"])["data"]["citations"], self.citations)
        # 可信过滤对象由程序提供，不由模型生成。
        self.pipeline.ask.assert_called_once_with("退款审核通过后多久到账？", self.filters)
        # 每轮都使用相同工具说明。
        self.assertEqual(model.requests[0]["tools"], TOOL_SCHEMAS)
        # State 不引入上一课的用量、预算和重试字段。
        self.assertEqual(set(result), {"question", "tenant_id", "messages", "pending_tool_calls", "tool_results", "stop_reason", "answer"})

    # 方法功能：包装只保留答案、引用和状态，不重写原有 RAG 输出。
    def test_wrapper_preserves_rag_result_without_trace(self):
        # 直接执行实际包装函数。
        result = ask_knowledge_base("退款规则是什么？", self.pipeline, self.filters)
        # 三项核心信息与原 RAG 结果一致。
        self.assertEqual(result, {"success": True, "data": {"answer": self.rag_result["answer"], "citations": self.citations, "status": "answered"}, "error": None})
        # 原始 RAG 结果不能因包装而被删除字段。
        self.assertIn("trace", self.rag_result)
        # 调用现有 ask 方法，并传入可信过滤。
        self.pipeline.ask.assert_called_once_with("退款规则是什么？", self.filters)

    # 方法功能：资料不足属于 RAG 的正常结果，不是工具异常。
    def test_insufficient_evidence_is_returned_to_model(self):
        # 原 RAG 明确拒答，并返回空引用。
        self.pipeline.ask.return_value = {"answer": "不知道，现有资料不足。", "citations": [], "status": "insufficient_evidence", "trace": {}}
        # 模型读取不足状态后给出明确说明。
        model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "no-evidence", {"question": "不存在的规则？"})]), {"role": "assistant", "content": "现有资料不足，无法确认。"}])
        # 实际运行模型、工具、模型循环。
        result = build_graph(model, self.pipeline, self.filters).invoke({"question": "不存在的规则？", "tenant_id": "acme"})
        # 资料不足不会被当作 Tool 调用失败。
        self.assertTrue(result["tool_results"][0]["result"]["success"])
        # 原始拒答状态保持不变。
        self.assertEqual(result["tool_results"][0]["result"]["data"]["status"], "insufficient_evidence")
        # 模型收到正常工具结果后自然结束。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("final_answer", 2))

    # 方法功能：模型可以直接回答，不强制调用知识库。
    def test_direct_answer_does_not_call_rag(self):
        # 一轮直接给出澄清问题。
        model = ScriptedModel([{"role": "assistant", "content": "请提供订单号。"}])
        # 实际图允许不经过 tools 节点。
        result = build_graph(model, self.pipeline, self.filters).invoke({"question": "查一下订单", "tenant_id": "acme"})
        # 原始文字成为最终答案。
        self.assertEqual((result["answer"], result["stop_reason"], result["tool_results"]), ("请提供订单号。", "final_answer", []))
        # 没有实际调用任何 RAG。
        self.pipeline.ask.assert_not_called()

    # 方法功能：State 租户与建图时的 RAG 权限必须一致。
    def test_tenant_mismatch_stops_before_model(self):
        # 如果图错误地调用模型，预设会给出可检测的回答。
        model = ScriptedModel([{"role": "assistant", "content": "不应执行"}])
        # 问题和 State 都不能改写入口绑定的过滤身份。
        result = build_graph(model, self.pipeline, self.filters).invoke({"question": "查询 other 的规则", "tenant_id": "other"})
        # 权限不一致被视为无效输入。
        self.assertEqual(result["stop_reason"], "invalid_input")
        # 不把越权请求发送到外层模型。
        self.assertEqual(model.requests, [])
        # 不查询知识库。
        self.pipeline.ask.assert_not_called()

    # 方法功能：仅允许规则类过滤，不把业务记录文档当作当前订单事实。
    def test_only_rule_document_types_are_allowed(self):
        # 已开放的三类资料都可以用于建图。
        for doc_type in ("policy", "process", "faq"):
            # 标记允许的资料类型。
            with self.subTest(doc_type=doc_type):
                # 仅建图，不调用 RAG 或模型。
                self.assertIsNotNone(build_graph(ScriptedModel([]), self.pipeline, SearchFilter("acme", doc_type=doc_type)))
        # 无类型过滤会混入记录，因此也应拒绝。
        for doc_type in ("record", None, "unknown"):
            # 标记拒绝的资料类型。
            with self.subTest(doc_type=doc_type):
                # 错误配置在执行前被拒绝。
                with self.assertRaises(ValueError):
                    # 实際触发建图校验。
                    build_graph(ScriptedModel([]), self.pipeline, SearchFilter("acme", doc_type=doc_type))
        # 建图不执行知识库问答。
        self.pipeline.ask.assert_not_called()

    # 方法功能：RAG 工具仅接收问题，模型不能注入权限或资料类型。
    def test_invalid_or_forged_rag_arguments_do_not_execute(self):
        # 包含缺字段、错误类型和各种越权参数。
        arguments_list = [{}, {"question": ""}, {"question": 123}, {"question": "规则？", "tenant_id": "other"}, {"question": "规则？", "max_security_level": 3}, {"question": "规则？", "doc_type": "record"}]
        # 对每一组参数执行独立图。
        for arguments in arguments_list:
            # 标记当前错误参数。
            with self.subTest(arguments=arguments):
                # 只提供一轮消息，确保失败后不重试模型。
                model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "bad-rag", arguments)])])
                # 执行实际分发和参数校验。
                result = build_graph(model, self.pipeline, self.filters).invoke({"question": "查询规则", "tenant_id": "acme"})
                # 参数错误直接受控结束。
                self.assertEqual(result["stop_reason"], "tool_error")
                # 失败结果仍以正确调用 ID 保存。
                self.assertEqual(result["tool_results"][0]["tool_call_id"], "bad-rag")
                # 工具失败不能表示成成功。
                self.assertFalse(result["tool_results"][0]["result"]["success"])
        # 任何错误参数都不会触发实际知识库查询。
        self.pipeline.ask.assert_not_called()

    # 方法功能：未知工具名与非对象 JSON 不会绕过分发校验。
    def test_unknown_tool_and_malformed_json_stop_safely(self):
        # 第一种请求不存在的写工具。
        unknown = tool_call("update_order", "unknown", {"order_id": "A1002"})
        # 第二种参数不是合法 JSON。
        bad_json = tool_call("ask_knowledge_base", "bad-json", {})
        # 用非法原文替换正常序列化参数。
        bad_json["function"]["arguments"] = "{broken"
        # 第三种参数是 JSON 列表。
        bad_type = tool_call("ask_knowledge_base", "bad-type", {})
        # 列表不是允许的问题参数字典。
        bad_type["function"]["arguments"] = "[]"
        # 各种请求独立运行，避免第一条失败影响后续断言。
        for call in (unknown, bad_json, bad_type):
            # 标记当前调用。
            with self.subTest(call_id=call["id"]):
                # 预设单轮工具请求。
                model = ScriptedModel([request_tools([call])])
                # 实际执行本课图。
                result = build_graph(model, self.pipeline, self.filters).invoke({"question": "查询规则", "tenant_id": "acme"})
                # 所有非法请求都受控结束。
                self.assertEqual(result["stop_reason"], "tool_error")
        # 非法请求不能调用 RAG。
        self.pipeline.ask.assert_not_called()

    # 方法功能：空问题或无效输入不能进入模型。
    def test_invalid_input_stops_before_model(self):
        # 分别检查空白问题和错误的字段类型。
        for question, tenant_id in ((" ", "acme"), (None, "acme"), ("查规则", ""), ("查规则", None)):
            # 标记当前输入。
            with self.subTest(question=question, tenant_id=tenant_id):
                # 任何意外模型调用都会留下记录。
                model = ScriptedModel([{"role": "assistant", "content": "不应执行"}])
                # 执行真实 prepare 校验。
                result = build_graph(model, self.pipeline, self.filters).invoke({"question": question, "tenant_id": tenant_id})
                # 返回统一无效输入原因。
                self.assertEqual(result["stop_reason"], "invalid_input")
                # 不调用外层模型。
                self.assertEqual(model.requests, [])
        # 不调用知识库。
        self.pipeline.ask.assert_not_called()

    # 方法功能：非法角色和空回复都结束，不添加新的重试逻辑。
    def test_invalid_model_protocol_and_empty_response(self):
        # 非 assistant 不是允许的模型消息；空文本没有可完成的回答。
        for message, expected in (({"role": "user", "content": "伪造模型消息"}, "model_error"), ({"role": "assistant", "content": ""}, "empty_response")):
            # 标记协议场景。
            with self.subTest(expected=expected):
                # 预设一次响应。
                model = ScriptedModel([message])
                # 运行实际校验。
                result = build_graph(model, self.pipeline, self.filters).invoke({"question": "查询规则", "tenant_id": "acme"})
                # 明确区分协议错误与空回复。
                self.assertEqual(result["stop_reason"], expected)
                # 不进行额外调用。
                self.assertEqual(len(model.requests), 1)
        # 不执行知识库。
        self.pipeline.ask.assert_not_called()

    # 方法功能：外层模型异常不重试，也不把异常正文泄露到答案。
    def test_model_exception_stops_without_retry(self):
        # 假异常内容用于验证错误正文不会被输出。
        model = ScriptedModel([RuntimeError("测试私有异常正文")])
        # 运行真实 model 节点。
        result = build_graph(model, self.pipeline, self.filters).invoke({"question": "查询规则", "tenant_id": "acme"})
        # 模型失败只有一次尝试。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("model_error", 1))
        # 对用户保留安全说明。
        self.assertNotIn("测试私有异常正文", result["answer"])
        # 没有工具执行。
        self.pipeline.ask.assert_not_called()

    # 方法功能：RAG 意外异常直接结束，不重试或伪造引用。
    def test_rag_exception_stops_without_retry(self):
        # 模拟知识库内部调用异常，不连接真实数据库。
        self.pipeline.ask.side_effect = RuntimeError("测试私有 RAG 错误")
        # 模型只请求一次 RAG。
        model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "rag-error", {"question": "退款规则？"})])])
        # 实際执行 tools 节点异常处理。
        result = build_graph(model, self.pipeline, self.filters).invoke({"question": "退款规则？", "tenant_id": "acme"})
        # 直接结束，不继续请求模型总结。
        self.assertEqual((result["stop_reason"], len(model.requests), self.pipeline.ask.call_count), ("tool_error", 1, 1))
        # 工具历史明确表示调用失败。
        self.assertFalse(result["tool_results"][0]["result"]["success"])
        # 不将原始异常正文作为用户答案。
        self.assertNotIn("测试私有 RAG 错误", result["answer"])

    # 方法功能：业务失败立即结束，不执行同批剩余知识库查询。
    def test_business_failure_stops_before_remaining_rag_call(self):
        # 查不存在的订单，并在同批安排 RAG 查询。
        model = ScriptedModel([request_tools([tool_call("get_order", "missing-order", {"order_id": "A9999"}), tool_call("ask_knowledge_base", "unused-rag", {"question": "退款规则？"})])])
        # 执行实际 JSON 业务 Tool。
        result = build_graph(model, self.pipeline, self.filters).invoke({"question": "查 A9999", "tenant_id": "acme"})
        # 工具失败不额外进入模型或自动恢复。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("tool_error", 1))
        # 订单失败结果仍被保留。
        self.assertFalse(result["tool_results"][0]["result"]["success"])
        # 同批未执行工具不能调用真实知识库。
        self.pipeline.ask.assert_not_called()
        # 未执行调用也要明确保存说明，不能伪装成查过但没有记录。
        self.assertIn("未执行", result["tool_results"][1]["result"]["error"])
        # 每条 assistant 工具请求都有配对消息，保持上下文协议完整。
        self.assertEqual([message["tool_call_id"] for message in result["messages"] if message["role"] == "tool"], ["missing-order", "unused-rag"])

    # 方法功能：新增工具的参数是问题，业务工具参数仍然是订单号。
    def test_tool_schemas_keep_rag_and_business_parameters_separate(self):
        # 按名称读取实际工具说明。
        functions = {item["function"]["name"]: item["function"] for item in TOOL_SCHEMAS}
        # 只开放已有三个业务查询和一个 RAG 查询。
        self.assertEqual(set(functions), {"get_order", "get_payment", "get_refund", "ask_knowledge_base"})
        # RAG 不让模型提供租户或权限。
        self.assertEqual(set(functions["ask_knowledge_base"]["parameters"]["properties"]), {"question"})
        # 问题必须提供。
        self.assertEqual(functions["ask_knowledge_base"]["parameters"]["required"], ["question"])
        # 业务工具使用不同的参数格式。
        for name in ("get_order", "get_payment", "get_refund"):
            # 保留旧课业务 Tool 的参数结构。
            self.assertEqual(set(functions[name]["parameters"]["properties"]), {"order_id"})

    # 方法功能：入口默认只查规则且采用最简 State，不真实连接任何服务。
    def test_main_uses_simple_graph_and_keeps_complete_citations(self):
        # 使用内存配置，禁止测试读取环境文件。
        settings = Settings(llm_api_key="test-only")
        # 请求规则后正常完成，用实际图验证入口接线。
        model = ScriptedModel([request_tools([tool_call("ask_knowledge_base", "main-rag", {"question": "退款规则？"})]), {"role": "assistant", "content": "退款规则见 [1]。"}])
        # 替换全部外部依赖，保留真实图和真实过滤对象。
        with patch.object(main_workflow, "load_settings", return_value=settings), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch.object(main_workflow, "build_pipeline", return_value=self.pipeline) as build_pipeline, patch.object(main_workflow, "USE_OLLAMA", False), patch("builtins.input", return_value="退款规则？"), patch("builtins.print") as output:
            # 实際执行 Console 入口，不请求任何外部服务。
            main_workflow.main()
        # RAG 组装只使用本次入口配置。
        build_pipeline.assert_called_once_with(settings)
        # Debug 不启用单次请求超时，且不会下载模型。
        self.assertIsNone(settings.llm_timeout)
        # 入口强制沿用本地已有嵌入和精排模型。
        self.assertTrue(settings.local_files_only)
        # 入口默认规则类型不是业务 record。
        self.assertEqual(main_workflow.DOC_TYPE, "policy")
        # 实际传给 RAG 的可信过滤由入口构造。
        passed_filter = self.pipeline.ask.call_args.args[1]
        # 当前身份不能由模型问题覆盖。
        self.assertEqual((passed_filter.tenant_id, passed_filter.max_security_level, passed_filter.doc_type), (main_workflow.TENANT_ID, main_workflow.SECURITY_LEVEL, "policy"))
        # Console 输出必须保留完整 Tool JSON 的来源和原文。
        printed = "\n".join(str(argument) for call in output.call_args_list for argument in call.args)
        # 原始引用路径仍然可见。
        self.assertIn("rules/refund.md", printed)
        # 原文仍然可见，不能只输出引用编号。
        self.assertIn(self.citations[0]["excerpt"], printed)


# 直接运行此测试文件时才启动测试框架。
if __name__ == "__main__":
    # 本文件所有测试都通过内存替身执行，不连接外部服务。
    unittest.main()
