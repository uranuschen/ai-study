import json
import unittest
from copy import deepcopy
from decimal import Decimal
import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError
from agent_learning.workflows.tracing import TraceRecorder, error_kind, safe_arguments


# (69) 可控时钟使耗时测试不需要真实等待。
class FakeClock:
    # (69) 每个测试独立持有当前秒数。
    def __init__(self):
        # (69) 使用固定起点，避免依赖机器时间。
        self.value = 10.0

    # (69) 与 time.monotonic 使用相同的无参数调用方式。
    def __call__(self):
        # (69) 不自动前进，由测试决定耗时。
        return self.value


# (69) 核对安全日志、父子跨度和不重复计费。
class TracingTests(unittest.TestCase):
    # (69) 只使用内存状态，不读取配置、数据库或模型。
    def setUp(self):
        # (69) 一轮执行与会话各有独立标识。
        self.state = {"thread_id": "lesson-69-test", "run_id": "run-1", "trace_events": [], "limits": {"currency": "CNY"}}
        # (69) 测试时钟可以直接调整数值。
        self.clock = FakeClock()
        # (69) 记录器不创建自己的共享事件列表。
        self.recorder = TraceRecorder(self.state, self.clock)

    # (69) 构造记录器不能提前修改状态。
    def test_initialization_only_holds_state_reference(self):
        # (69) 没有事件列表的状态仍应保持原样。
        state = {"thread_id": "other", "run_id": "other-run"}
        # (69) 保存独立副本用于比较。
        original = deepcopy(state)
        # (69) 创建实例本身不产生事件或默认字段。
        recorder = TraceRecorder(state, self.clock)
        # (69) 不允许构造时隐式重置当前执行。
        self.assertEqual(state, original)
        # (69) 后续记录应作用于同一个显式状态。
        self.assertIs(recorder.state, state)

    # (69) 开始结束使用同一跨度，并记录可检查的耗时。
    def test_start_and_finish_preserve_identity_and_duration(self):
        # (69) 模拟模型节点的第二次尝试。
        span = self.recorder.start("node", "model", attempt=2, retry=1)
        # (69) 模拟节点经过 2.5 秒。
        self.clock.value += 2.5
        # (69) 记录成功结束。
        self.recorder.finish(span, "success")
        # (69) 一次执行应有一条开始和一条结束。
        start, end = self.state["trace_events"]
        # (69) 开始记录不应被结束事件修改。
        self.assertEqual((start["phase"], start["status"]), ("start", "running"))
        # (69) 各关联字段必须保持一致。
        self.assertEqual([end[name] for name in ("thread_id", "run_id", "span_id", "node", "attempt", "retry")], ["lesson-69-test", "run-1", span["span_id"], "model", 2, 1])
        # (69) 时间差由注入时钟确定。
        self.assertEqual(end["duration_seconds"], 2.5)
        # (69) 节点事件不含模型用量，避免父子重复统计。
        self.assertNotIn("input_tokens", end)

    # (69) 嵌套跨度保留节点与工具关系。
    def test_parent_chain_links_rag_model_to_tool_and_node(self):
        # (69) 当前图进入工具节点。
        node = self.recorder.start("node", "tools")
        # (69) RAG 工具属于该节点。
        tool = self.recorder.start("tool", "ask_knowledge_base", parent_id=node["span_id"], tool_call_id="call-1")
        # (69) RAG 内层模型属于该工具。
        llm = self.recorder.start("llm", "rag_model", parent_id=tool["span_id"])
        # (69) 父子链保留精确跨度关系。
        self.assertEqual((tool["parent_id"], llm["parent_id"]), (node["span_id"], tool["span_id"]))
        # (69) 模型事件同样能定位外层节点和工具。
        self.assertEqual((llm["node"], llm["tool"]), ("tools", "ask_knowledge_base"))
        # (69) 调用 ID 经过遮盖但同一调用仍能关联。
        self.assertEqual(llm["tool_call_id"], tool["tool_call_id"])

    # (69) 任意模型调用 ID 都不能原样进入日志。
    def test_tool_call_ids_are_hashed_without_exposing_secrets(self):
        # (69) 即使是合法前缀，也可能含秘密。
        secret = "call_sk-secret-user@example.com"
        # (69) 同一原始 ID 经过相同摘要后仍可关联。
        first = self.recorder.start("tool", "get_order", tool_call_id=secret)
        # (69) 第二条记录不应产生另一套摘要规则。
        second = self.recorder.start("tool", "get_order", tool_call_id=secret)
        # (69) 不保存原始 ID 或其中一部分。
        self.assertNotIn(secret, json.dumps(self.state["trace_events"]))
        # (69) 日志 ID 固定为短哈希格式。
        self.assertRegex(first["tool_call_id"], r"^call#[a-f0-9]{12}$")
        # (69) 同一调用可通过摘要定位。
        self.assertEqual(first["tool_call_id"], second["tool_call_id"])

    # (69) 构造父跨度时必须属于相同会话与执行。
    def test_parent_cannot_cross_run_or_thread(self):
        # (69) 先保留旧轮次节点。
        parent = self.recorder.start("node", "tools")
        # (69) 开启新轮次，不应挂到旧父跨度。
        self.state["run_id"] = "run-2"
        # (69) 传入旧标识也不会关联成功。
        child = self.recorder.start("tool", "get_order", parent_id=parent["span_id"])
        # (69) 不允许跨轮次误关联。
        self.assertEqual(child["parent_id"], "")
        # (69) 同 run 值但不同会话仍然不是同一次执行。
        self.state.update({"run_id": "run-1", "thread_id": "another-thread"})
        # (69) 会话切换后再次尝试旧父标识。
        other = self.recorder.start("tool", "get_order", parent_id=parent["span_id"])
        # (69) 不能串会话。
        self.assertEqual(other["parent_id"], "")

    # (69) 完整 usage 区分输入、输出和未分类用量。
    def test_complete_usage_records_extra_total_without_double_counting_details(self):
        # (69) 内层模型只记录一次用量。
        span = self.recorder.start("llm", "rag_model")
        # (69) total 中的额外 3 个 Token 不能被忽略。
        usage = {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 17, "completion_tokens_details": {"reasoning_tokens": 2}, "secret": "hidden"}
        # (69) 金额来自预算计算，记录器不猜测单价。
        self.recorder.finish(span, "success", usage=usage, reserved_input=100, reserved_output=50, estimated_cost="0.001")
        # (69) 读取实际结束事件。
        event = self.state["trace_events"][-1]
        # (69) 输入输出保留 API 原值，差额单列。
        self.assertEqual((event["input_tokens"], event["output_tokens"], event["uncategorized_tokens"], event["total_tokens"]), (10, 4, 3, 17))
        # (69) 不复制整个 usage，避免未知字段泄漏。
        self.assertNotIn("hidden", json.dumps(event))
        # (69) 摘要总量不再重复相加 reasoning 细项。
        summary = self.recorder.summary()
        # (69) 预留不是实际 Token，不能取代 17。
        self.assertEqual((summary["known_input_tokens"], summary["known_output_tokens"], summary["known_uncategorized_tokens"], summary["known_total_tokens"]), (10, 4, 3, 17))

    # (69) 缺失或非法 usage 只能标为未知。
    def test_missing_or_invalid_usage_does_not_become_zero_or_reservation(self):
        # (69) 包含 bool、负数、缺字段和错误类型。
        cases = (None, {}, {"prompt_tokens": 10}, {"prompt_tokens": True, "completion_tokens": 2}, {"prompt_tokens": -1, "completion_tokens": 2}, {"prompt_tokens": 1.5, "completion_tokens": 2}, {"prompt_tokens": 1, "completion_tokens": "2"})
        # (69) 每种情况都记录一次真实模型尝试。
        for usage in cases:
            # (69) 新建模型跨度。
            span = self.recorder.start("llm", "agent_model")
            # (69) 预留可扣预算，但不能伪装 API 实测。
            self.recorder.finish(span, "error", usage=usage, reserved_input=120, reserved_output=50, estimated_cost="0.01")
            # (69) 检查固定的未知用量标记。
            event = self.state["trace_events"][-1]
            # (69) 未知时输入、输出和总量都不是零。
            self.assertEqual((event["usage_source"], event["input_tokens"], event["output_tokens"], event["total_tokens"]), ("unknown", None, None, None))
            # (69) 预算估算与依据实际用量的估算分开。
            self.assertEqual((event["budget_estimated_cost"], event["estimated_cost"]), ("0.01", None))
        # (69) 每个未知调用都保留计数。
        summary = self.recorder.summary()
        # (69) 没有实际 Token 不能说已消耗预留 Token。
        self.assertEqual((summary["unknown_usage_calls"], summary["known_total_tokens"]), (len(cases), 0))
        # (69) 总费用未知，预算金额仍单独可见。
        self.assertIsNone(summary["estimated_cost"])
        # (69) 以 Decimal 检查金额没有浮点累加误差。
        self.assertEqual(Decimal(summary["budget_estimated_cost"]), Decimal("0.07"))

    # (69) 合法零用量是已知，而不是缺失。
    def test_zero_tokens_are_known_and_total_below_parts_does_not_undercount(self):
        # (69) 零输入输出可被 API 明确报告。
        zero = self.recorder.start("llm", "agent_model")
        # (69) 免费或零用量明确记录为零。
        self.recorder.finish(zero, "success", usage={"prompt_tokens": 0, "completion_tokens": 0}, estimated_cost="0")
        # (69) 再检查不一致的 total 不会减少已知输入输出。
        other = self.recorder.start("llm", "agent_model")
        # (69) 输入输出之和仍然是 7。
        self.recorder.finish(other, "success", usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 3}, estimated_cost="0.001")
        # (69) 两次用量都完整已知。
        summary = self.recorder.summary()
        # (69) 不因为错误 total 低估用量。
        self.assertEqual((summary["llm_attempts"], summary["unknown_usage_calls"], summary["known_total_tokens"]), (2, 0, 7))

    # (69) 节点与工具即使传入 usage，也不重复计算模型消耗。
    def test_nested_node_tool_and_llm_count_tokens_and_cost_only_once(self):
        # (69) 同一调用构造完整的三层关系。
        node = self.recorder.start("node", "tools")
        # (69) 工具内部执行 RAG。
        tool = self.recorder.start("tool", "ask_knowledge_base", parent_id=node["span_id"])
        # (69) RAG 内层模型是唯一计费用量事件。
        llm = self.recorder.start("llm", "rag_model", parent_id=tool["span_id"])
        # (69) 经过一秒后模型完成。
        self.clock.value += 1
        # (69) 单次模型依据实际用量估算费用。
        usage = {"prompt_tokens": 20, "completion_tokens": 5}
        # (69) 记录模型结束。
        self.recorder.finish(llm, "success", usage=usage, estimated_cost="0.01")
        # (69) 工具总耗时为两秒，包含模型耗时。
        self.clock.value += 1
        # (69) 错传给工具的 usage 也不能重复算 Token。
        self.recorder.finish(tool, "success", usage=usage, estimated_cost="0.01")
        # (69) 节点总耗时为三秒，也包含工具耗时。
        self.clock.value += 1
        # (69) 节点属于观测，不是另一笔模型账单。
        self.recorder.finish(node, "success", usage=usage, estimated_cost="0.01")
        # (69) 摘要只统计模型结束事件。
        summary = self.recorder.summary()
        # (69) 不能变成三次调用、75 Token 或三倍费用。
        self.assertEqual((summary["llm_attempts"], summary["known_total_tokens"], summary["estimated_cost"]), (1, 25, "0.01"))
        # (69) 节点与工具时间分组显示，不造出五秒总耗时。
        self.assertEqual((summary["node_seconds"], summary["tool_seconds"]), ({"tools": 3.0}, {"ask_knowledge_base": 2.0}))
        # (69) 摘要没有容易误解的嵌套耗时求和字段。
        self.assertNotIn("total_seconds", summary)

    # (69) 部分已知费用需要明确标记，不能显示成完整账单。
    def test_cost_summary_separates_known_and_reserved_costs(self):
        # (69) 一次返回明确 usage 的模型调用。
        known = self.recorder.start("llm", "agent_model")
        # (69) 已知部分成本为 0.1。
        self.recorder.finish(known, "success", usage={"prompt_tokens": 1, "completion_tokens": 2}, estimated_cost="0.1")
        # (69) 失败调用只有预留成本。
        unknown = self.recorder.start("llm", "agent_model", attempt=2, retry=1)
        # (69) 不能把失败的预留用量称为实际费用。
        self.recorder.finish(unknown, "error", error=TimeoutError("secret"), estimated_cost="0.2")
        # (69) 再有一次既无用量也无可用金额的情况。
        absent = self.recorder.start("llm", "rag_model")
        # (69) 未知金额保持未知。
        self.recorder.finish(absent, "error")
        # (69) 汇总完整性和部分金额各自有字段。
        summary = self.recorder.summary()
        # (69) 不把 0.1 或 0.3 标为完整实际费用。
        self.assertEqual((summary["estimated_cost"], summary["known_estimated_cost"], summary["cost_is_partial"]), (None, "0.1", True))
        # (69) 预算单列，并说明还有一笔预算金额未知。
        self.assertEqual((Decimal(summary["budget_estimated_cost"]), summary["unknown_budget_cost_calls"]), (Decimal("0.3"), 1))
        # (69) 货币单位来自可信预算配置。
        self.assertEqual(summary["currency"], "CNY")

    # (69) 无用量不应因为金额非法而抛错或输出原始文本。
    def test_invalid_cost_is_unknown_and_not_logged(self):
        # (69) 所有不合法金额都应安全归为未知。
        for cost in ("NaN", "Infinity", "-1", "sk-secret", True):
            # (69) 每种金额使用独立跨度。
            span = self.recorder.start("llm", "agent_model")
            # (69) 用量已知也不能猜测合法价格。
            self.recorder.finish(span, "success", usage={"prompt_tokens": 1, "completion_tokens": 1}, estimated_cost=cost)
            # (69) 不合法金额不进入任何费用字段。
            self.assertIsNone(self.state["trace_events"][-1]["budget_estimated_cost"])
        # (69) 密钥样文本不能留在事件中。
        self.assertNotIn("sk-secret", json.dumps(self.state["trace_events"]))

    # (69) 错误分类不使用异常文字。
    def test_errors_have_safe_stable_categories(self):
        # (69) 本地异常使用明确的枚举。
        cases = ((TimeoutError("password=secret"), "timeout"), (ConnectionError("Authorization: secret"), "connection"), (ValueError("private question"), "validation"), (TypeError("private question"), "validation"), (RuntimeError("sk-secret"), "system"))
        # (69) 逐个核对安全分类。
        for error, expected in cases:
            # (69) 分类函数不依赖敏感文字。
            self.assertEqual(error_kind(error), expected)
            # (69) 事件同样只保留分类。
            span = self.recorder.start("node", "model")
            # (69) 错误交给记录器安全处理。
            self.recorder.finish(span, "error", error=error)
            # (69) 保留定位类别但不暴露原文。
            self.assertEqual(self.state["trace_events"][-1]["error_kind"], expected)
        # (69) 模型异常原文不能进入 JSON。
        encoded = json.dumps(self.state["trace_events"])
        # (69) 覆盖密码、认证头、问题与密钥文字。
        self.assertFalse(any(text in encoded for text in ("password", "Authorization", "private question", "sk-secret")))

    # (69) 模型 SDK 的 HTTP 错误只保留类别。
    def test_openai_error_categories_without_network_requests(self):
        # (69) HTTP 请求对象只用于构造离线异常，不实际发送。
        request = httpx.Request("GET", "https://example.invalid")
        # (69) 明确区分 SDK 超时与普通连接错误。
        self.assertEqual(error_kind(APITimeoutError(request=request)), "timeout")
        # (69) SDK 连接异常同样不暴露请求。
        self.assertEqual(error_kind(APIConnectionError(request=request)), "connection")
        # (69) 状态异常只看 HTTP 类别。
        for status, expected in ((400, "http_4xx"), (429, "http_4xx"), (503, "http_5xx")):
            # (69) 构造只存在于内存的响应。
            response = httpx.Response(status, request=request)
            # (69) 敏感错误正文不会成为日志内容。
            error = APIStatusError("sk-secret", response=response, body={"password": "secret"})
            # (69) 分类与正文无关。
            self.assertEqual(error_kind(error), expected)

    # (69) 日志参数只输出固定字段与脱敏结果。
    def test_safe_arguments_masks_order_and_removes_unknown_fields(self):
        # (69) 未知键和值都可能携带秘密。
        arguments = json.dumps({"order_id": "A1002", "password": "secret", "authorization": "Bearer secret", "sk-secret-key": "hidden"})
        # (69) 实际调用脱敏函数。
        result = safe_arguments("get_order", arguments)
        # (69) 标准订单号只保留极少定位信息。
        self.assertEqual(result, {"status": "valid", "fields": ["order_id"], "order_id": "A***02"})
        # (69) 不保留未知字段名或值。
        self.assertNotIn("secret", json.dumps(result))

    # (69) 自由问题始终遮盖，异常订单号也不能原样泄漏。
    def test_safe_arguments_masks_questions_and_nonstandard_order_ids(self):
        # (69) RAG 查询文本不能作为日志摘要。
        result = safe_arguments("ask_knowledge_base", json.dumps({"question": "用户张某的密码是 secret", "order_id": "A1002"}))
        # (69) 非本工具参数也不记录。
        self.assertEqual(result, {"status": "valid", "fields": ["question"], "question": "[REDACTED]"})
        # (69) 订单 ID 不符合固定演示格式时全部遮盖。
        for order_id in ("A1002 secret", "sk-secret", "12345678901", "A1", "A1234567890123456789", {"secret": "value"}, None):
            # (69) JSON 中不论原值类型都不回显。
            masked = safe_arguments("cancel_order", json.dumps({"order_id": order_id}))
            # (69) 非标准值只能得到固定遮盖标记。
            self.assertEqual(masked["order_id"], "[REDACTED]")

    # (69) 错误 JSON 和未知工具都不回显输入。
    def test_safe_arguments_invalid_json_and_unknown_tool_are_safe(self):
        # (69) 解析异常不返回原始文本。
        for arguments in ("password=secret", "[\"secret\"]", "null", "\"secret\"", None, {"password": "secret"}):
            # (69) 参数结构无效时只报告固定状态。
            self.assertEqual(safe_arguments("get_order", arguments), {"status": "invalid", "fields": []})
        # (69) 未知工具不允许任意字段进入日志。
        self.assertEqual(safe_arguments("unknown_tool", '{"order_id":"A1002","question":"secret"}'), {"status": "valid", "fields": []})

    # (69) 汇总不能把别的会话或轮次算进当前执行。
    def test_summary_filters_other_runs_and_threads(self):
        # (69) 第一轮模型报告 3 个 Token。
        first = self.recorder.start("llm", "agent_model")
        # (69) 原轮次完成。
        self.recorder.finish(first, "success", usage={"prompt_tokens": 1, "completion_tokens": 2}, estimated_cost="0.01")
        # (69) 即使残留事件不清空，当前 run 仍应隔离。
        self.state["run_id"] = "run-2"
        # (69) 第二轮明确报告 9 个 Token。
        second = self.recorder.start("llm", "agent_model")
        # (69) 记录当前轮费用。
        self.recorder.finish(second, "success", usage={"prompt_tokens": 4, "completion_tokens": 5}, estimated_cost="0.02")
        # (69) 当前摘要不能统计两轮合计。
        self.assertEqual((self.recorder.summary()["llm_attempts"], self.recorder.summary()["known_total_tokens"]), (1, 9))
        # (69) 切换会话后同 run 值也不应继承旧统计。
        self.state["thread_id"] = "other-thread"
        # (69) 当前会话尚未发生模型请求。
        self.assertEqual(self.recorder.summary()["llm_attempts"], 0)

    # (69) 独立状态与独立记录器不会共享事件。
    def test_recorders_do_not_share_lists_and_same_run_can_continue(self):
        # (69) 第一段节点使用当前记录器。
        span = self.recorder.start("node", "prepare")
        # (69) 完成后把状态复制给下个节点。
        self.recorder.finish(span, "success")
        # (69) 下个节点复制列表后创建另一个记录器。
        copied = {**self.state, "trace_events": list(self.state["trace_events"])}
        # (69) 实例不共享私有累计器，直接读取复制后的 State。
        recorder = TraceRecorder(copied, self.clock)
        # (69) 当前轮可以在新节点中继续追踪。
        next_span = recorder.start("node", "model")
        # (69) 第二段完整结束。
        recorder.finish(next_span, "success")
        # (69) 原状态没有被下个节点继续修改。
        self.assertEqual(len(self.state["trace_events"]), 2)
        # (69) 新状态保留历史事件并新增两条。
        self.assertEqual(len(copied["trace_events"]), 4)
        # (69) 另一轮全新状态默认没有任何共享事件。
        another = TraceRecorder({"thread_id": "other", "run_id": "other"}, self.clock)
        # (69) 空摘要不会看到前两段事件。
        self.assertEqual(another.summary()["node_seconds"], {})

    # (69) 结束事件不会复制调用者额外塞入的敏感字段。
    def test_finish_only_copies_allowlisted_span_fields(self):
        # (69) span 正常由记录器创建。
        span = self.recorder.start("node", "model")
        # (69) 模拟调用方误加上下文或密钥。
        span.update({"messages": [{"content": "private"}], "settings": {"api_key": "secret"}})
        # (69) 结束事件只能取固定字段。
        self.recorder.finish(span, "error", error=RuntimeError("secret"))
        # (69) 不允许额外值出现在事件中。
        self.assertNotIn("secret", json.dumps(self.state["trace_events"]))
        # (69) 原始消息字段也不能复制。
        self.assertNotIn("messages", self.state["trace_events"][-1])

    # (69) 不合法技术标识和货币文字不能进入可显示日志。
    def test_untrusted_identifiers_and_currency_are_redacted(self):
        # (69) 标识中意外带自由文本时拒绝原样输出。
        self.state.update({"thread_id": "user@example.com secret", "run_id": "Bearer secret", "limits": {"currency": "password secret"}})
        # (69) 名称与状态额外做格式保护。
        span = self.recorder.start("node", "name secret", attempt=True, retry=-1)
        # (69) 错误状态也不能放任任意文本。
        self.recorder.finish(span, "password secret")
        # (69) 不合法标识统一遮盖。
        self.assertNotIn("secret", json.dumps(self.state["trace_events"]))
        # (69) Bool 与负数不作为合法尝试计数。
        self.assertEqual((span["attempt"], span["retry"]), (0, 0))
        # (69) 未识别币种明确显示未知。
        self.assertEqual(self.recorder.summary()["currency"], "UNKNOWN")

    # (69) 没有任何模型调用时用量和费用合计为零。
    def test_empty_summary_is_explicit_and_json_serializable(self):
        # (69) 尚未执行的本轮仍能显示结构化摘要。
        summary = self.recorder.summary()
        # (69) 没有发生请求不同于发生请求但用量未知。
        self.assertEqual((summary["llm_attempts"], summary["unknown_usage_calls"], summary["estimated_cost"], summary["cost_is_partial"]), (0, 0, "0", False))
        # (69) 无需额外编码器就能放进 State 或 Console。
        json.dumps(summary, ensure_ascii=False)

    # (69) 倒退或异常时钟不会导致负耗时、NaN 汇总。
    def test_nonpositive_or_nonfinite_duration_is_safe(self):
        # (69) 先检查时钟回拨。
        span = self.recorder.start("node", "prepare")
        # (69) 人工把测试时钟倒退。
        self.clock.value -= 1
        # (69) 负时间差归零。
        self.recorder.finish(span, "success")
        # (69) 日志不出现负数。
        self.assertEqual(self.state["trace_events"][-1]["duration_seconds"], 0)
        # (69) 再模拟非有限时间。
        another = self.recorder.start("node", "model")
        # (69) 异常时钟只能形成未知耗时。
        self.clock.value = float("inf")
        # (69) 结束记录仍能生成。
        self.recorder.finish(another, "success")
        # (69) 无穷不会进入摘要。
        self.assertIsNone(self.state["trace_events"][-1]["duration_seconds"])
        # (69) 只有零耗时的 prepare 参与按名称汇总。
        self.assertEqual(self.recorder.summary()["node_seconds"], {"prepare": 0.0})


# (69) 支持直接运行本课离线测试。
if __name__ == "__main__":
    # (69) unittest 只运行当前模块的内存测试。
    unittest.main()
