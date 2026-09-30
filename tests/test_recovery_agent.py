# 导入 JSON，检查回传结果与安全输出。
import json
# 导入深拷贝，避免测试预设被工作流修改。
from copy import deepcopy
# 导入标准测试框架。
import unittest
# 导入替身工具，阻止真实模型请求。
from unittest.mock import patch
# 导入 HTTP 对象，只在内存构造 SDK 错误，不访问网络。
import httpx
# 导入 SDK 错误与真实响应类型。
from openai import APIStatusError
# 导入真实响应类，测试消息与 usage 分离。
from openai.types.chat import ChatCompletion
# 导入真实 Console 接线，配置读取会被替换。
import main_workflow
# 导入纯内存配置，测试不读取 .env。
from agent_learning.core.config import Settings
# 导入只读业务函数，测试恢复后读取真实项目 JSON。
from agent_learning.business.tools import get_refund, tool_result
# 导入本课工作流和预算工具。
from agent_learning.workflows.recovery_agent import DEFAULT_LIMITS, build_graph, estimate_input_tokens, make_limits
# 导入模型适配，SDK 客户端将被替换。
from agent_learning.workflows.tool_model import CompatibleToolModel


# 方法功能：构造完整工具请求，参数仍为 JSON 字符串。
def tool_call(name="get_refund", call_id="r", arguments='{"order_id":"A1002"}') -> dict:
    # 模拟的是协议结构，不代表真实模型判断。
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


# 方法功能：构造消息与用量分开的测试响应。
def response(message=None, calls=None, usage=None) -> dict:
    # 有调用时模拟请求 Tool，没有调用时默认提供最终回答。
    message = {"role": "assistant", "content": "", "tool_calls": calls} if calls is not None else (message or {"role": "assistant", "content": "离线验证完成。"})
    # 默认 usage 是固定测试值，不是接口调用获得的统计。
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120} if usage is None else usage
    # 返回格式与真实适配类一致。
    return {"message": message, "usage": usage, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}


# 类职责：虚拟单调时钟，让超时和等待测试无需真实 sleep。
class FakeClock:
    # 方法功能：从固定时间开始测试。
    def __init__(self):
        # 当前虚拟秒数。
        self.now = 100.0
        # 保存实际要求过的等待时间。
        self.waits = []

    # 方法功能：像 time.monotonic 一样返回当前秒数。
    def __call__(self):
        # 没有真实时间流逝，只有测试主动推进时间。
        return self.now

    # 方法功能：模拟等待，不阻塞测试线程。
    def sleep(self, seconds):
        # 记录等待提示。
        self.waits.append(seconds)
        # 将等待时间计入任务耗时。
        self.now += seconds


# 类职责：按顺序返回结果或抛出异常，仅用于离线流程测试。
class ScriptedBudgetModel:
    # 方法功能：保存预设，不创建 SDK 客户端。
    def __init__(self, responses, repeat=False):
        # 预设可以是字典、异常或推进虚拟时钟的普通函数。
        self.responses = responses
        # 重复模式用于验证循环终止。
        self.repeat = repeat
        # 保存每次实际调用收到的参数。
        self.requests = []

    # 方法功能：模拟第 63 课模型接口。
    def request_with_tools(self, messages, tools, timeout=None, max_tokens=1200):
        # 保存独立副本，不受后续 State 更新影响。
        self.requests.append({"messages": deepcopy(messages), "tools": deepcopy(tools), "timeout": timeout, "max_tokens": max_tokens})
        # 普通模式逐条取值，重复模式始终使用第一条。
        item = self.responses[0 if self.repeat else len(self.requests) - 1]
        # 异常直接交给真实节点处理。
        if isinstance(item, Exception):
            # 不访问外部服务。
            raise item
        # 普通函数用于模拟同步请求耗时。
        if callable(item):
            # 由测试自己推进虚拟时间。
            item = item()
        # 不让图改动预设结果。
        item = deepcopy(item)
        # 重复工具请求仍需不同 ID。
        if self.repeat and item["message"].get("tool_calls"):
            # 修改当前副本中的调用 ID。
            item["message"]["tool_calls"][0]["id"] = f"repeat_{len(self.requests)}"
        # 将预设交给真实图继续执行。
        return item


# 方法功能：用内存响应构造临时或永久 HTTP 错误。
def http_error(status, code=None, retry_after=None):
    # 不包含任何真实账户、主机或凭证。
    headers = {} if retry_after is None else {"retry-after": retry_after}
    # SDK 异常需要 request 对象，但不会发出这个请求。
    reply = httpx.Response(status, headers=headers, request=httpx.Request("POST", "https://example.invalid"))
    # code 为 SDK 可直接读取的错误类别。
    return APIStatusError("offline-only error", response=reply, body={"code": code})


# 类职责：验证恢复、所有预算及消息配对，绝不访问真实 API 或数据库。
class RecoveryAgentTests(unittest.TestCase):
    # 方法功能：创建每个测试独立的时钟。
    def setUp(self):
        # 不在不同测试之间共享任务耗时。
        self.clock = FakeClock()

    # 方法功能：使用真实图执行一次离线任务。
    def run_graph(self, model, limits=None, question="查询 A1002 的退款", tenant="acme"):
        # 入口注入时钟和等待函数，其他节点使用真实实现。
        return build_graph(model, limits=limits, clock=self.clock, sleep=self.clock.sleep).invoke({"question": question, "tenant_id": tenant})

    # 方法功能：保留正常 Agent 循环、多条退款与接口用量。
    def test_normal_loop_and_usage(self):
        # 一次 Tool 请求，第二次模型提供答案。
        model = ScriptedBudgetModel([response(calls=[tool_call()]), response()])
        # 查询项目真实 JSON，不接数据库。
        result = self.run_graph(model)
        # 最终回答包含在模型尝试次数内。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["tool_calls"]), ("final_answer", 2, 1))
        # 两条实际退款记录都保留。
        self.assertEqual(len(result["tool_results"][0]["result"]["data"]), 2)
        # 每次 usage 都计入，而不是只有最后一轮。
        self.assertEqual(result["total_tokens"], 240)
        # 演示单价计算结果是精确 Decimal 字符串。
        self.assertEqual(result["estimated_cost"], "0.0028")
        # 下一次模型确实收到同 ID 的工具结果。
        self.assertEqual(model.requests[1]["messages"][-1]["tool_call_id"], "r")
        # 预算统计不混进请求消息。
        self.assertNotIn("usage", model.requests[1]["messages"][-2])

    # 方法功能：临时模型连接错误只增加有限次数，并记录恢复。
    def test_model_temporary_error_recovers(self):
        # 第一次失败，第二次成功。
        model = ScriptedBudgetModel([ConnectionError("test-secret must not leak"), response()])
        # 用虚拟等待执行重试。
        result = self.run_graph(model)
        # 额外尝试和总尝试分别可观察。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["model_retries"]), ("final_answer", 2, 1))
        # 失败未知用量不能记作零 Token。
        self.assertEqual(result["usage_history"][0]["source"], "estimated_reservation")
        # 不记录原始异常内容，避免凭证泄漏。
        self.assertNotIn("test-secret", json.dumps(result, ensure_ascii=False))
        # 等待发生过但没有真实 sleep。
        self.assertEqual(len(self.clock.waits), 1)

    # 方法功能：临时模型故障达到重试上限后结束。
    def test_model_retry_exhausted(self):
        # 持续临时失败，不能无限等成功。
        model = ScriptedBudgetModel([ConnectionError("offline")], repeat=True)
        # 最多一次额外重试。
        result = self.run_graph(model, {"max_retries": 1})
        # 初次尝试加一次重试等于两次。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["model_retries"]), ("model_retry_exhausted", 2, 1))

    # 方法功能：HTTP 临时故障恢复；认证、配额和未知异常不重试。
    def test_http_and_permanent_error_classification(self):
        # 明确列出允许和禁止自动重试的情况。
        cases = [(http_error(503), True), (http_error(429), True), (http_error(401), False), (http_error(429, "insufficient_quota"), False), (ValueError("bad protocol"), False)]
        # 每种错误独立执行。
        for error, temporary in cases:
            # 标记具体类别。
            with self.subTest(error=type(error).__name__, temporary=temporary):
                # 成功消息只在允许重试时才会被取到。
                model = ScriptedBudgetModel([error, response()])
                # 复用虚拟时间，不读真实配置。
                result = self.run_graph(model)
                # 非临时错误只请求一次。
                self.assertEqual(len(model.requests), 2 if temporary else 1)
                # 永久错误直接进入 failure 节点。
                self.assertEqual(result["stop_reason"], "final_answer" if temporary else "model_error")

    # 方法功能：Retry-After 被遵守，过长提示不被截短后提前重试。
    def test_retry_after_and_delay_limit(self):
        # 服务端要求一秒等待。
        model = ScriptedBudgetModel([http_error(429, retry_after="1"), response()])
        # 真正恢复后返回答案。
        result = self.run_graph(model)
        # 虚拟等待不小于服务端提示。
        self.assertEqual((result["stop_reason"], self.clock.waits), ("final_answer", [1.0]))
        # 过长等待必须明确结束。
        model = ScriptedBudgetModel([http_error(503, retry_after="100")])
        # 不能把 100 秒截为 10 秒后发起重试。
        result = self.run_graph(model)
        # 只发生一次请求。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("retry_delay_limit", 1))

    # 方法功能：业务失败不重试，剩余同批请求不执行且全部有配对结果。
    def test_business_failure_skips_remaining_batch(self):
        # 第一条查不存在订单，第二条即使合法也应跳过。
        model = ScriptedBudgetModel([response(calls=[tool_call("get_order", "missing", '{"order_id":"A9999"}'), tool_call("get_refund", "later")])])
        # 运行实际 JSON 查询。
        result = self.run_graph(model)
        # 业务失败不浪费次数重试或让模型继续查询。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["tool_calls"], result["tool_retries"]), ("business_error", 1, 1, 0))
        # 执行失败与完全未执行明确区分。
        self.assertEqual([item["attempts"] for item in result["tool_results"]], [1, 0])
        # 两个 Tool 请求都有各自 ID 的结果。
        self.assertEqual([item["tool_call_id"] for item in result["messages"] if item["role"] == "tool"], ["missing", "later"])
        # 跳过请求不能伪造为空列表成功。
        self.assertFalse(result["tool_results"][1]["result"]["success"])

    # 方法功能：成功空列表不是业务失败。
    def test_empty_records_are_success_not_failure(self):
        # A1003 没有退款记录，但查询本身成功。
        model = ScriptedBudgetModel([response(calls=[tool_call(arguments='{"order_id":"A1003"}')]), response()])
        # 真正读取项目 JSON。
        result = self.run_graph(model)
        # 允许模型解释没有退款记录。
        self.assertEqual(result["stop_reason"], "final_answer")
        # 保留成功的空列表。
        self.assertEqual(result["tool_results"][0]["result"], tool_result(True, data=[]))

    # 方法功能：Tool 临时异常可恢复，调用 ID 只配对一次。
    def test_tool_temporary_error_recovers(self):
        # 模型请求查询退款。
        model = ScriptedBudgetModel([response(calls=[tool_call()]), response()])
        # 第一条系统异常，下一次读取真实 JSON 的结果。
        with patch("agent_learning.workflows.recovery_agent.dispatch_tool", side_effect=[ConnectionError("offline"), get_refund("A1002", "acme")]):
            # 使用真实恢复节点执行两次分发。
            result = self.run_graph(model)
        # 同一工具发生一次额外重试，共两次执行尝试。
        self.assertEqual((result["stop_reason"], result["tool_calls"], result["tool_retries"]), ("final_answer", 2, 1))
        # 只有最终结果写入工具上下文，不重复使用同 ID。
        self.assertEqual(len([item for item in result["messages"] if item["role"] == "tool"]), 1)
        # 调试历史保留单条请求的实际尝试数。
        self.assertEqual(result["tool_results"][0]["attempts"], 2)

    # 方法功能：Tool 重试耗尽和永久系统错误都有明确分支。
    def test_tool_errors_stop_without_model_followup(self):
        # 临时和永久异常分别处理。
        for error, reason, attempts in ((ConnectionError("offline"), "tool_retry_exhausted", 2), (ValueError("bad result"), "tool_error", 1)):
            # 标记预期的结束原因。
            with self.subTest(reason=reason):
                # 失败后不应取到下一条模型回复。
                model = ScriptedBudgetModel([response(calls=[tool_call()])])
                # 替换 Tool 以模拟系统异常。
                with patch("agent_learning.workflows.recovery_agent.dispatch_tool", side_effect=error):
                    # 一次额外重试足以验证上限。
                    result = self.run_graph(model, {"max_retries": 1})
                # 不无限请求模型修复永久错误。
                self.assertEqual((result["stop_reason"], result["tool_calls"], len(model.requests)), (reason, attempts, 1))

    # 方法功能：总 Tool 次数限制重试，且失败恢复不会丢失已尝试事实。
    def test_tool_retry_consumes_total_limit(self):
        # 模型只请求一次业务查询。
        model = ScriptedBudgetModel([response(calls=[tool_call()])])
        # 第一次尝试就发生临时故障。
        with patch("agent_learning.workflows.recovery_agent.dispatch_tool", side_effect=ConnectionError("offline")) as dispatch:
            # 总 Tool 上限为一，不允许额外重试。
            result = self.run_graph(model, {"max_tool_calls": 1})
        # 总次数不能被单条重试额度绕过。
        self.assertEqual((result["stop_reason"], dispatch.call_count, result["tool_retries"]), ("tool_limit", 1, 0))
        # 曾经执行过的请求不应误报为零次跳过。
        self.assertEqual(result["tool_results"][0]["attempts"], 1)

    # 方法功能：重试等待实际超时后保留第一次尝试，且不启动第二次。
    def test_tool_overslept_retry_keeps_attempt(self):
        # 用虚拟 sleep 模拟系统调度使等待时间超出预期。
        def oversleep(seconds):
            # 不真实阻塞，直接推进到整体截止以后。
            self.clock.now += 100
        # 只请求退款工具。
        model = ScriptedBudgetModel([response(calls=[tool_call()])])
        # 第一次临时异常可以进入等待，但实际等待会超时。
        with patch("agent_learning.workflows.recovery_agent.dispatch_tool", side_effect=ConnectionError("offline")) as dispatch:
            # 注入异常等待函数，验证等待后的重新检查。
            result = build_graph(model, clock=self.clock, sleep=oversleep).invoke({"question": "查退款", "tenant_id": "acme"})
        # 第二次调用没有发生，第一次执行事实仍保留。
        self.assertEqual((result["stop_reason"], dispatch.call_count, result["tool_results"][0]["attempts"]), ("overall_timeout", 1, 1))

    # 方法功能：取得工具证据以后模型失败，之前的结果不会被清空。
    def test_model_failure_preserves_tool_evidence(self):
        # 查到退款后出现永久模型错误。
        model = ScriptedBudgetModel([response(calls=[tool_call()]), ValueError("offline")])
        # 执行正常第一轮查询和第二轮失败分支。
        result = self.run_graph(model)
        # 系统失败不是业务无记录。
        self.assertEqual(result["stop_reason"], "model_error")
        # 实际退款仍保留两笔。
        self.assertEqual(len(result["tool_results"][0]["result"]["data"]), 2)

    # 方法功能：截断与空响应不循环，截断请求的真实用量仍计入。
    def test_incomplete_and_empty_response_are_charged(self):
        # 模拟已经生成 Token 但未完整结束。
        truncated = response()
        # 截断状态不允许执行工具。
        truncated["finish_reason"] = "length"
        # 无工具和无文字应单独受控结束。
        empty = response(message={"role": "assistant", "content": " "})
        # 两种失败独立验证。
        for item, reason in ((truncated, "model_error"), (empty, "empty_response")):
            # 标记结束原因。
            with self.subTest(reason=reason):
                # 一次请求后就应该停止。
                result = self.run_graph(ScriptedBudgetModel([item]))
                # 不能把失败或空响应算成零用量。
                self.assertEqual((result["stop_reason"], result["total_tokens"], result["model_steps"]), (reason, 120, 1))

    # 方法功能：重复 invoke 的预算与消息从零开始，不共享上一任务 State。
    def test_each_invoke_initializes_new_budget(self):
        # 两次任务分别直接得到答案。
        model = ScriptedBudgetModel([response(), response()])
        # 图可以复用，任务 State 不能混在一起。
        graph = build_graph(model, clock=self.clock, sleep=self.clock.sleep)
        # 首次执行传入伪造计数，prepare 应覆盖。
        first = graph.invoke({"question": "第一次", "tenant_id": "acme", "model_steps": 999, "tool_calls": 999, "estimated_cost": "999"})
        # 第二次执行仍是独立任务。
        second = graph.invoke({"question": "第二次", "tenant_id": "acme"})
        # 不继承旧计数，不接受入口问题之外的伪造消耗。
        self.assertEqual((first["model_steps"], second["model_steps"], second["total_tokens"]), (1, 1, 120))
        # 第二次消息没有第一次问题。
        self.assertEqual(model.requests[1]["messages"][1]["content"], "第二次")

    # 方法功能：同批多个 Tool 不能绕过上限，包括禁用全部 Tool。
    def test_batch_tool_limit_and_zero_limit(self):
        # 覆盖允许一条与完全禁止工具的情况。
        for limit in (0, 1):
            # 标记预算。
            with self.subTest(limit=limit):
                # 同批提出两个工具请求。
                model = ScriptedBudgetModel([response(calls=[tool_call("get_payment", "p"), tool_call("get_refund", "r")])])
                # 新上限对整个批次生效。
                result = self.run_graph(model, {"max_tool_calls": limit})
                # 不能实际多分发一条。
                self.assertEqual((result["stop_reason"], result["tool_calls"]), ("tool_limit", limit))
                # 所有模型调用 ID 最终都有结果或跳过说明。
                self.assertEqual(len(result["tool_results"]), 2)

    # 方法功能：模型重试也受 MAX_STEPS 限制，且自然答案可在最后一次完成。
    def test_model_steps_include_retries_and_final_answer(self):
        # 第一次临时失败就已经用掉唯一一步。
        model = ScriptedBudgetModel([ConnectionError("offline"), response()])
        # 不允许隐藏的额外模型调用。
        result = self.run_graph(model, {"max_steps": 1})
        # 达到步骤上限时不做重试等待。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("max_steps", 1))
        # 第一轮已有正常回答时仍属于自然完成。
        result = self.run_graph(ScriptedBudgetModel([response()]), {"max_steps": 1})
        # 不能把已完成答案误标为达到步骤上限。
        self.assertEqual(result["stop_reason"], "final_answer")

    # 方法功能：持续请求工具的模型最终受控结束，最后一轮 Tool 仍保留。
    def test_repeated_tools_stop_at_model_limit(self):
        # 不依赖模型自然结束来避免死循环。
        model = ScriptedBudgetModel([response(calls=[tool_call()])], repeat=True)
        # 提高 Token 预算，使测试专门覆盖步骤上限。
        result = self.run_graph(model, {"max_steps": 3, "max_total_tokens": 100000})
        # 没有第四次请求，也没有为了总结额外调用。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["tool_calls"]), ("max_steps", 3, 3))

    # 方法功能：Token 与费用预留不足时，在第一次请求前就结束。
    def test_preflight_token_and_cost_budget(self):
        # 分别触发两种预算不足。
        for limits, reason in (({"max_total_tokens": 1}, "token_budget"), ({"max_cost": "0.000001"}, "cost_budget")):
            # 标记预算类型。
            with self.subTest(reason=reason):
                # 预设为空，任何请求都会暴露错误。
                model = ScriptedBudgetModel([])
                # 检查请求前拦截。
                result = self.run_graph(model, limits)
                # 未发生请求时没有真实尝试或用量记录。
                self.assertEqual((result["stop_reason"], result["model_steps"], model.requests, result["usage_history"]), (reason, 0, [], []))

    # 方法功能：接口实际用量超过预估时，记账后阻止执行工具。
    def test_reported_usage_can_stop_before_tools(self):
        # 预估足够，但接口报告特别大的用量。
        large_usage = {"prompt_tokens": 1000000, "completion_tokens": 1, "total_tokens": 1000001}
        # 响应中即使有工具，也不能越过实际预算。
        model = ScriptedBudgetModel([response(calls=[tool_call()], usage=large_usage)])
        # 不运行任何实际 Tool。
        result = self.run_graph(model)
        # 预估不是绝对上限，超限后明确停止。
        self.assertEqual((result["stop_reason"], result["total_tokens"], result["tool_calls"]), ("token_budget", 1000001, 0))
        # 请求已经发生，所以保留真实报告的用量与未执行标志。
        self.assertEqual(result["tool_results"][0]["attempts"], 0)
        # 放宽 Token 后可以单独触发费用预算。
        result = self.run_graph(ScriptedBudgetModel([response(usage=large_usage)]), {"max_total_tokens": 2000000})
        # 实际费用超出预留时不能声称自然完成。
        self.assertEqual(result["stop_reason"], "cost_budget")

    # 方法功能：缺失或错误 usage 使用完整预留，不默认为零。
    def test_missing_usage_is_charged_and_output_cap_forwarded(self):
        # 返回缺失用量的普通答案。
        model = ScriptedBudgetModel([response(usage={})])
        # 使用不同输出上限，验证参数传到模型适配层。
        result = self.run_graph(model, {"max_output_tokens": 77})
        # 缺失用量被明确标注为估算。
        self.assertEqual(result["usage_history"][0]["source"], "estimated_reservation")
        # 预留包含工具 Schema 和输出上限。
        self.assertEqual(result["total_tokens"], estimate_input_tokens(model.requests[0]["messages"]) + 77)
        # 不继续使用写死的 1200 输出上限。
        self.assertEqual(model.requests[0]["max_tokens"], 77)

    # 方法功能：总时间不足以等待重试时，不等待、不发第二次请求。
    def test_retry_wait_respects_overall_deadline(self):
        # Retry-After 要求等待五秒。
        model = ScriptedBudgetModel([http_error(503, retry_after="5")])
        # 总预算只有一秒，直接结束。
        result = self.run_graph(model, {"overall_timeout": 1})
        # 一次请求后没有实际重试。
        self.assertEqual((result["stop_reason"], len(model.requests), self.clock.waits), ("overall_timeout", 1, []))

    # 方法功能：同步模型迟到响应不执行其中 Tool，SDK 超时不超过剩余总时间。
    def test_model_single_and_overall_timeout(self):
        # 分别覆盖单次超时与整体超时。
        for limits, reason in (({"model_timeout": 1, "overall_timeout": 10}, "model_timeout"), ({"model_timeout": 10, "overall_timeout": 1}, "overall_timeout")):
            # 标记当前超时类型。
            with self.subTest(reason=reason):
                # 模拟请求两秒后才返回。
                def delayed_response():
                    # 推进单调时钟，不真实等待。
                    self.clock.now += 2
                    # 即使请求 Tool，也不能在超时后执行。
                    return response(calls=[tool_call()])
                # 模型只返回这一条迟到消息。
                model = ScriptedBudgetModel([delayed_response])
                # 真实节点负责检查截止时间。
                result = self.run_graph(model, limits)
                # 超时后不继续查询。
                self.assertEqual((result["stop_reason"], result["tool_calls"]), (reason, 0))
                # 模型请求的超时参数取两者较小值。
                self.assertEqual(model.requests[0]["timeout"], 1)

    # 方法功能：Tool 返回迟到时保留事实，但不继续下一条 Tool 或模型。
    def test_tool_timeout_preserves_late_result_and_skips_next(self):
        # 同批请求支付与退款。
        model = ScriptedBudgetModel([response(calls=[tool_call("get_payment", "p"), tool_call("get_refund", "r")])])
        # 模拟 Tool 在两秒后返回成功数据。
        def delayed_tool(*args, **kwargs):
            # 推进时间，保持整个测试离线。
            self.clock.now += 2
            # 迟到也不能把已经取得的数据抹去。
            return tool_result(True, data=[{"status": "支付成功"}])
        # 不启动可能在超时后继续运行的后台线程。
        with patch("agent_learning.workflows.recovery_agent.dispatch_tool", side_effect=delayed_tool) as dispatch:
            # 单次 Tool 预算为一秒。
            result = self.run_graph(model, {"tool_timeout": 1})
        # 支付执行过，退款没执行，模型没有第二次请求。
        self.assertEqual((result["stop_reason"], dispatch.call_count, len(model.requests)), ("tool_timeout", 1, 1))
        # 迟到的成功事实仍然保留，时间失败另在元数据说明。
        self.assertTrue(result["tool_results"][0]["result"]["success"])
        # 剩余请求明确为零次尝试。
        self.assertEqual(result["tool_results"][1]["attempts"], 0)

    # 方法功能：整体截止后不再启动第二条同批 Tool。
    def test_overall_timeout_between_batch_tools(self):
        # 两条同批 Tool 只允许第一条开始。
        model = ScriptedBudgetModel([response(calls=[tool_call("get_payment", "p"), tool_call("get_refund", "r")])])
        # 第一条耗时超过整个任务预算。
        def delayed_tool(*args, **kwargs):
            # 推进虚拟秒数。
            self.clock.now += 2
            # 返回实际已取得的结果。
            return tool_result(True, data=[])
        # 模拟调用，不访问真实外部服务。
        with patch("agent_learning.workflows.recovery_agent.dispatch_tool", side_effect=delayed_tool) as dispatch:
            # Tool 单次上限大于整体剩余时间。
            result = self.run_graph(model, {"tool_timeout": 10, "overall_timeout": 1})
        # 超时后不能开始剩余 Tool。
        self.assertEqual((result["stop_reason"], dispatch.call_count), ("overall_timeout", 1))

    # 方法功能：关闭超时后，长时间单步调试仍完成循环并记录真实耗时。
    def test_timeouts_disabled_allow_long_model_and_tool(self):
        # 第一次模型调用模拟断点停留一千秒。
        def delayed_request():
            # 只推进虚拟时钟，不真实等待。
            self.clock.now += 1000
            # 请求正常退款查询。
            return response(calls=[tool_call()])
        # 第二次模型调用模拟断点停留三千秒。
        def delayed_answer():
            # 模型耗时远远超过原有单次与整体限制。
            self.clock.now += 3000
            # 仍然提供合法最终回答。
            return response()
        # 本地 Tool 中的断点同样不应触发失败分支。
        def delayed_tool(*args, **kwargs):
            # Tool 的虚拟耗时为两千秒。
            self.clock.now += 2000
            # 保留项目真实 JSON 的多条退款记录。
            return get_refund("A1002", "acme")
        # 使用真实图串联长耗时模型、Tool 和最终模型。
        model = ScriptedBudgetModel([delayed_request, delayed_answer])
        # 替换 Tool 调度，不连接任何外部系统。
        with patch("agent_learning.workflows.recovery_agent.dispatch_tool", side_effect=delayed_tool):
            # 超时值很小，但总开关关闭后不参与流程判断。
            result = self.run_graph(model, {"enable_timeouts": False, "model_timeout": 1, "tool_timeout": 1, "overall_timeout": 1})
        # 程序不设置截止时间，也不因为 Debug 暂停结束。
        self.assertEqual((result["stop_reason"], result["deadline"], result["elapsed_seconds"]), ("final_answer", None, 6000))
        # SDK 每次请求都明确不设置客户端超时。
        self.assertEqual([item["timeout"] for item in model.requests], [None, None])
        # 关闭限制不影响正常次数统计。
        self.assertEqual((result["model_steps"], result["tool_calls"]), (2, 1))
        # 每个操作耗时仍保留，便于调试后分析。
        self.assertEqual([item["elapsed_seconds"] for item in result["events"]], [1000, 2000, 3000])
        # 真实查询结果仍然完整。
        self.assertEqual(len(result["tool_results"][0]["result"]["data"]), 2)

    # 方法功能：关闭超时后，有限模型重试可跨过原本的整体截止时间。
    def test_timeouts_disabled_model_retry_crosses_previous_deadline(self):
        # 服务端要求等待五秒，超过配置中的一秒整体时间。
        model = ScriptedBudgetModel([http_error(503, retry_after="5"), response()])
        # Retry-After 仍然执行，但不再检查整体超时。
        result = self.run_graph(model, {"enable_timeouts": False, "overall_timeout": 1})
        # 等待以后允许第二次请求恢复。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["model_retries"]), ("final_answer", 2, 1))
        # 总耗时继续统计，而不是在禁用超时时归零。
        self.assertEqual((result["deadline"], result["elapsed_seconds"], self.clock.waits), (None, 5, [5.0]))
        # 重试请求也不回退到原有模型超时。
        self.assertEqual([item["timeout"] for item in model.requests], [None, None])

    # 方法功能：关闭超时后，Tool 重试等待中的长暂停不会阻止恢复。
    def test_timeouts_disabled_tool_retry_survives_long_pause(self):
        # 模拟在等待期间单步暂停一万秒。
        def oversleep(seconds):
            # 保留请求的等待时间用于验证有限重试。
            self.clock.waits.append(seconds)
            # 虚拟时间超过所有原有超时限制。
            self.clock.now += 10000
        # Tool 恢复以后仍允许模型生成答案。
        model = ScriptedBudgetModel([response(calls=[tool_call()]), response()])
        # 首次临时异常，第二次正常返回真实退款数据。
        with patch("agent_learning.workflows.recovery_agent.dispatch_tool", side_effect=[ConnectionError("offline"), get_refund("A1002", "acme")]) as dispatch:
            # 用异常长的虚拟暂停执行真实恢复分支。
            result = build_graph(model, limits={"enable_timeouts": False, "overall_timeout": 1}, clock=self.clock, sleep=oversleep).invoke({"question": "查退款", "tenant_id": "acme"})
        # Tool 按有限额度恢复，实际尝试次数正确保留。
        self.assertEqual((result["stop_reason"], dispatch.call_count, result["tool_retries"], result["tool_results"][0]["attempts"]), ("final_answer", 2, 1, 2))
        # 不设置截止时间，但保留长暂停的任务耗时。
        self.assertEqual((result["deadline"], result["elapsed_seconds"], len(self.clock.waits)), (None, 10000, 1))

    # 方法功能：关闭时间限制不等于关闭模型、Tool、Token 或费用预算。
    def test_timeouts_disabled_preserve_non_time_budgets(self):
        # 每种预算使用独立模型预设，确保不能多发请求。
        cases = [({"max_steps": 1}, [ConnectionError("offline")], "max_steps", 1, 0), ({"max_tool_calls": 0}, [response(calls=[tool_call()])], "tool_limit", 1, 0), ({"max_total_tokens": 1}, [], "token_budget", 0, 0), ({"max_cost": "0.000001"}, [], "cost_budget", 0, 0)]
        # 分别运行保留的安全预算分支。
        for limits, replies, reason, model_steps, tool_calls in cases:
            # 标记当前预算类型。
            with self.subTest(reason=reason):
                # 为每项预算统一关闭超时判断。
                limits = dict(limits, enable_timeouts=False)
                # 任意越过预算的模型调用都会耗尽预设并暴露错误。
                model = ScriptedBudgetModel(replies)
                # 使用真实预算检查与失败节点。
                result = self.run_graph(model, limits)
                # 次数和费用分支仍然可终止任务。
                self.assertEqual((result["stop_reason"], result["model_steps"], result["tool_calls"]), (reason, model_steps, tool_calls))
                # 调试开关始终不创建时间截止值。
                self.assertIsNone(result["deadline"])

    # 方法功能：超时开关只能使用布尔值，独立图仍默认开启保护。
    def test_enable_timeouts_requires_boolean(self):
        # 工作流库默认开启，Console 可明确覆盖为关闭。
        self.assertIs(DEFAULT_LIMITS["enable_timeouts"], True)
        # 两个合法值都可以由可信入口传入。
        for enabled in (True, False):
            # 正确布尔值不需要猜测字符串含义。
            self.assertIs(make_limits({"enable_timeouts": enabled})["enable_timeouts"], enabled)
        # 数字、字符串、空值和容器不能替代布尔值。
        for enabled in (1, 0, "false", None, []):
            # 标记具体的无效配置。
            with self.subTest(enabled=enabled):
                # 必须在构图前就拒绝错误开关类型。
                with self.assertRaises(ValueError):
                    # 不启动模型请求。
                    make_limits({"enable_timeouts": enabled})

    # 方法功能：未知工具、非法参数和坏协议都有限结束，租户保持可信。
    def test_invalid_tools_protocol_and_tenant(self):
        # 模型不能添加租户或文件路径参数。
        for call in (tool_call("write_refund"), tool_call(arguments="bad-json"), tool_call(arguments='{"order_id":"A1002","tenant_id":"other"}')):
            # 标记不同输入。
            with self.subTest(call=call):
                # 本课把参数错误作为已知失败，不再交给模型无限修正。
                result = self.run_graph(ScriptedBudgetModel([response(calls=[call])]))
                # 一次分发尝试后明确失败。
                self.assertEqual((result["stop_reason"], result["tool_calls"], result["tool_retries"]), ("business_error", 1, 0))
        # 错误角色不允许进入工具分发。
        result = self.run_graph(ScriptedBudgetModel([response(message={"role": "tool", "content": "wrong"})]))
        # 模型协议错误不重试。
        self.assertEqual((result["stop_reason"], result["tool_calls"]), ("model_error", 0))
        # 问题文字不能覆盖入口租户。
        result = self.run_graph(ScriptedBudgetModel([response(calls=[tool_call()]), response()]), question="查 acme 的 A1002", tenant="other")
        # 同号订单的退款只返回 other 的记录。
        self.assertEqual(result["tool_results"][0]["result"]["data"][0]["tenant_id"], "other")

    # 方法功能：构图配置检查与输入失败均不启动模型。
    def test_invalid_limits_and_input(self):
        # 各类无效配置都应在构图时拒绝。
        for limits in ({"max_steps": True}, {"max_retries": -1}, {"tool_timeout": 0}, {"overall_timeout": float("inf")}, {"max_cost": "NaN"}, {"input_price_per_million": "-1"}, {"unknown": 1}, {"max_retry_delay": 61}):
            # 逐项标记错误配置。
            with self.subTest(limits=limits):
                # 不调用模型，也不读配置文件。
                with self.assertRaises(ValueError):
                    # 普通配置字典应在建图前报错。
                    make_limits(limits)
        # 输入校验也不消耗模型预算。
        model = ScriptedBudgetModel([])
        # 空问题直接进入失败节点。
        result = self.run_graph(model, question=" ")
        # 初始预算字段由 prepare 生成。
        self.assertEqual((result["stop_reason"], result["model_steps"], model.requests), ("invalid_input", 0, []))
        # 默认配置不会被上面错误测试污染。
        self.assertEqual(DEFAULT_LIMITS["max_steps"], 5)


# 类职责：验证真实 SDK 参数与 Console 入口接线，客户端和配置均替换。
class RecoveryAdapterTests(unittest.TestCase):
    # 方法功能：单次超时、输出上限、usage 与 reasoning 字段正确分离。
    def test_adapter_forwards_limits_and_returns_usage(self):
        # 使用真实 SDK 响应类型，但不发出网络请求。
        reply = ChatCompletion(id="offline", object="chat.completion", created=0, model="test", choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "done", "reasoning_content": "fixture"}}], usage={"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14})
        # 凭证仅为测试占位值。
        settings = Settings(llm_api_key="test-only")
        # SDK 请求完全替换，不读取真实环境配置。
        with patch("agent_learning.workflows.tool_model.OpenAI") as client_class:
            # 获取模拟的客户端上下文。
            client = client_class.return_value.__enter__.return_value
            # 返回内存响应。
            client.chat.completions.create.return_value = reply
            # 调用真实适配代码。
            result = CompatibleToolModel(settings).request_with_tools([], [], timeout=1.5, max_tokens=77)
        # SDK 内部没有隐式重试。
        self.assertEqual(client_class.call_args.kwargs["max_retries"], 0)
        # 请求参数使用本次预算。
        self.assertEqual((client_class.call_args.kwargs["timeout"], client.chat.completions.create.call_args.kwargs["max_tokens"]), (1.5, 77))
        # 模型消息保留协议字段，但不包含 usage。
        self.assertEqual(result["message"]["reasoning_content"], "fixture")
        # 用量独立返回，不污染后续消息。
        self.assertEqual(result["usage"]["total_tokens"], 14)
        # 不能把账单字段当作 assistant 内容。
        self.assertNotIn("usage", result["message"])

    # 方法功能：明确传入 None 时禁用 SDK 超时，不回退到配置里的秒数。
    def test_adapter_none_timeout_disables_sdk_limit(self):
        # 在内存创建合法回答，不访问模型接口。
        reply = ChatCompletion(id="offline", object="chat.completion", created=0, model="test", choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}])
        # 配置里仍保留超时，明确验证 None 覆盖它。
        settings = Settings(llm_api_key="test-only", llm_timeout=123)
        # SDK 构造与请求全部替换为离线替身。
        with patch("agent_learning.workflows.tool_model.OpenAI") as client_class:
            # 直接提供内存响应。
            client_class.return_value.__enter__.return_value.chat.completions.create.return_value = reply
            # 调用真实适配器，None 必须保留到 SDK 参数。
            result = CompatibleToolModel(settings).request_with_tools([], [], timeout=None)
        # 不允许把 None 自动替换为 123 秒。
        self.assertIsNone(client_class.call_args.kwargs["timeout"])
        # 调试模式仍然禁用 SDK 内部自动重试。
        self.assertEqual(client_class.call_args.kwargs["max_retries"], 0)
        # 正常消息解析不受超时开关影响。
        self.assertEqual(result["message"]["content"], "done")

    # 方法功能：旧课 chat_with_tools 仍显式使用配置超时，避免变更旧行为。
    def test_legacy_chat_retains_configured_timeout(self):
        # 内存中创建旧接口需要的合法回答。
        reply = ChatCompletion(id="offline", object="chat.completion", created=0, model="test", choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}])
        # 旧课调用仍读取普通配置对象里的超时。
        settings = Settings(llm_api_key="test-only", llm_timeout=123)
        # 不访问真实 API。
        with patch("agent_learning.workflows.tool_model.OpenAI") as client_class:
            # 提供与真实 SDK 一致的消息对象。
            client_class.return_value.__enter__.return_value.chat.completions.create.return_value = reply
            # 旧接口没有新增调试参数。
            result = CompatibleToolModel(settings).chat_with_tools([], [])
        # None 的新语义不应导致旧课程取消超时保护。
        self.assertEqual(client_class.call_args.kwargs["timeout"], 123)
        # 旧接口仍返回消息字典而非带 usage 的外层字典。
        self.assertEqual(result["content"], "done")

    # 方法功能：截断响应也保留用量，恢复图才能先记账。
    def test_truncated_response_keeps_usage(self):
        # 模拟生成被截断但已有 Token 费用。
        reply = ChatCompletion(id="offline", object="chat.completion", created=0, model="test", choices=[{"index": 0, "finish_reason": "length", "message": {"role": "assistant", "content": "partial"}}], usage={"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14})
        # 所有请求替换为内存响应。
        with patch("agent_learning.workflows.tool_model.OpenAI") as client_class:
            # 设置假 SDK 返回。
            client_class.return_value.__enter__.return_value.chat.completions.create.return_value = reply
            # 调用新增的用量接口。
            result = CompatibleToolModel(Settings(llm_api_key="test-only")).request_with_tools([], [])
        # 截断参数不能进入 Tool 分发。
        self.assertEqual((result["finish_reason"], result["message"], result["usage"]["total_tokens"]), ("length", {}, 14))

    # 方法功能：完整入口可以接通新图、真实 JSON 和预算打印。
    def test_console_entry_offline(self):
        # 预设退款查询与最终回答。
        model = ScriptedBudgetModel([response(calls=[tool_call()]), response()])
        # 配置、模型、输入和打印全部使用替身。
        with patch.object(main_workflow, "load_settings", return_value=Settings()), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch("builtins.input", return_value="查询 A1002 退款"), patch("builtins.print") as output:
            # 实际运行根入口和新图，不访问 API。
            main_workflow.main()
        # 两次模型尝试后完成。
        self.assertEqual(len(model.requests), 2)
        # Console 能显示控制统计和真实模拟数据。
        self.assertIn("估算费用", str(output.call_args_list))
        # 多条退款没有丢失。
        self.assertIn("R10022", str(output.call_args_list))

    # 方法功能：根入口默认关闭超时，普通运行与单步调试使用同一接线。
    def test_console_entry_defaults_to_timeouts_disabled(self):
        # 默认调试入口必须明确关闭，而不是依靠很大的超时值。
        self.assertIs(main_workflow.ENABLE_TIMEOUTS, False)
        # 模型直接提供答案，任何额外请求都会耗尽预设。
        model = ScriptedBudgetModel([response()])
        # 替换配置、模型与交互，整个入口仍离线运行。
        with patch.object(main_workflow, "load_settings", return_value=Settings()), patch.object(main_workflow, "CompatibleToolModel", return_value=model), patch("builtins.input", return_value="说明退款流程"), patch("builtins.print"):
            # 运行真实根入口，验证开关已经传入真实图。
            main_workflow.main()
        # 默认入口最终请求 SDK 时明确传入 None。
        self.assertEqual([item["timeout"] for item in model.requests], [None])


# IDE 可直接运行该文件，选择运行 unittest 测试。
if __name__ == "__main__":
    # 所有测试均为离线，异常、等待和模型响应均来自预设。
    unittest.main()
