import json
import unittest
from unittest.mock import Mock, patch
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from openai.types.chat import ChatCompletion
import main_workflow as lesson70
from agent_learning.business.tools import DEFAULT_DATA_FILE, get_order, get_refund, tool_result
from agent_learning.core.config import Settings
from agent_learning.core.models import Hit, SearchFilter
from agent_learning.core.providers import CompatibleChatModel
from agent_learning.rag.answering import AnswerValidator, ContextBuilder, PromptBuilder, RAGPipeline
from agent_learning.rag.retrieval import QueryProcessor
from agent_learning.workflows import diagnosis_agent
from test_memory_agent import tool_call
from test_recovery_agent import FakeClock, ScriptedBudgetModel, response


# (70) 用纯内存模型检查 RAG 内层调用，不创建网络客户端。
class InnerModel:
    # (70) 保存一次回答或错误，供共享预算执行器调用。
    def __init__(self, error=None, usage=None, content="退款规则见 [1]。"):
        # (70) 未提供错误时正常生成规则答案。
        self.error = error
        # (70) 固定用量只属于离线测试，不冒充真实模型统计。
        self.usage = {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40} if usage is None else usage
        # (70) 真实 RAG 管道测试可提供可校验的 JSON 回答。
        self.content = content
        # (70) 记录实际调用次数，发现预算耗尽后多发请求。
        self.calls = []

    # (70) 与真实 RAG 模型的可计费请求接口保持一致。
    def request(self, messages, timeout=None, max_tokens=1200, max_retries=0):
        # (70) 记录传入参数，不连接 LLM API。
        self.calls.append({"messages": messages, "timeout": timeout, "max_tokens": max_tokens, "max_retries": max_retries})
        # (70) 可主动抛出临时或永久错误，验证内层恢复边界。
        if self.error is not None:
            # (70) 真实工作流负责分类错误，替身不自行重试。
            raise self.error
        # (70) 内层和外层分别记账，返回明确的接口用量。
        return {"content": self.content, "usage": dict(self.usage), "finish_reason": "stop"}


# (70) 只模拟资料检索结果，保留 RAG 内层模型的真实预算路径。
class InnerPipeline:
    # (70) 接收测试用模型，避免构造向量模型和数据库连接。
    def __init__(self, model):
        # (70) 由集成工作流提供的执行器调用这一模型。
        self.llm = model

    # (70) 保持 RAG 的统一问答接口。
    def ask(self, question, filters, execution=None):
        # (70) 执行器贯通本轮模型次数、Token 和费用预算。
        answer = execution.chat(self.llm, [{"role": "user", "content": question}])
        # (70) 引用是内存样例，不访问真实知识库。
        return {"answer": answer, "status": "answered", "citations": [{"number": 1, "source": "refund-rules.md", "excerpt": "通常按支付渠道到账。"}]}


# (70) 覆盖业务、RAG、Memory、审批、失败恢复与预算的真实图集成。
class DiagnosisAgentTests(unittest.TestCase):
    # (70) 每个测试独立创建身份、时钟和内存存档。
    def setUp(self):
        # (70) 租户和资料范围由可信入口提供。
        self.filters = SearchFilter(tenant_id="acme", max_security_level=1, doc_type="policy")
        # (70) 测试不受真实时间和 Debug 暂停影响。
        self.clock = FakeClock()
        # (70) 默认规则回答不实际调用内层模型，专门场景再用 InnerPipeline。
        self.pipeline = Mock()
        # (70) 保留引用和回答状态，检查来源边界。
        self.pipeline.ask.return_value = {"answer": "规则见 [1]。", "status": "answered", "citations": [{"number": 1, "source": "rules.md", "excerpt": "规则原文"}]}
        # (70) 同一测试内使用固定 thread_id 恢复状态。
        self.config = {"configurable": {"thread_id": "diagnosis-test"}}
        # (70) 基本问题只提交业务输入，不伪造预算和消息。
        self.initial = {"question": "查询 A1002 的退款", "tenant_id": "acme"}

    # (70) 默认给足离线预算，只让各场景指定的限制成为终止原因。
    def build(self, responses, limits=None, pipeline=None, **kwargs):
        # (70) 外层模型返回协议消息和独立 usage。
        model = ScriptedBudgetModel(responses)
        # (70) 时间限制关闭，仅记录耗时，避免调试超时。
        trusted_limits = {"enable_timeouts": False, "max_steps": 10, "max_tool_calls": 12, "max_total_tokens": 100000, "max_cost": "10", "retry_delay": 0}
        # (70) 仅可信测试参数能修改本轮预算。
        trusted_limits.update(limits or {})
        # (70) 使用真实 StateGraph 和 Checkpoint，不用假图代替执行。
        graph = diagnosis_agent.build_graph(model, pipeline if pipeline is not None else self.pipeline, self.filters, InMemorySaver(), limits=trusted_limits, clock=self.clock, sleep=self.clock.sleep, **kwargs)
        # (70) 同时返回模型，便于核对是否发生额外请求。
        return model, graph

    # (70) 每个 assistant 工具请求都必须配一个响应，停止后不能留孤立调用。
    def assert_tool_pairs(self, result, expected_ids):
        # (70) 同时覆盖成功、失败和未执行消息的协议配对。
        actual = [message["tool_call_id"] for message in result["messages"] if message["role"] == "tool"]
        # (70) 执行顺序与原调用顺序一致。
        self.assertEqual(actual, expected_ids)
        # (70) 已结束轮次没有悬空请求。
        self.assertEqual(result["pending_tool_calls"], [])

    # (70) 检索与精排用替身，其余意图、上下文、提示词和引用校验用真实实现。
    def real_pipeline(self, hits, llm=None):
        # (70) 直接构造默认配置，不读取 .env。
        settings = Settings()
        # (70) 向量检索和数据库全部由纯内存候选替代。
        retriever = Mock()
        # (70) 记录只保留本次独立字典，避免跨测试污染。
        retriever.retrieve.return_value = (hits, {})
        # (70) 不加载 CrossEncoder 权重，候选相关度由测试给定。
        reranker = Mock()
        # (70) 保留候选原文和预设精排分数。
        reranker.rank.return_value = hits
        # (70) 默认内层模型返回合法引用回答。
        llm = llm or InnerModel(content='{"answerable":true,"answer":"退款按渠道到账 [1]。","citations":[1]}')
        # (70) 执行真实 RAGPipeline.ask 的阶段追踪与共享预算路径。
        return RAGPipeline(QueryProcessor(), retriever, reranker, ContextBuilder(settings), PromptBuilder(), llm, AnswerValidator(), settings)

    # (70) 返回一个真正暂停的敏感请求，后续测试只提交人工决定。
    def pause_cancel(self, limits=None, calls=None):
        # (70) 默认取消 A1001，其他测试可混合普通查询与取消。
        calls = calls or [tool_call("cancel_order", "cancel-1", {"order_id": "A1001"})]
        # (70) 第二个响应仅在确认成功且预算足够时才允许使用。
        model, graph = self.build([response(calls=calls), response()], limits=limits)
        # (70) 第一次 invoke 只能到审批点，不执行敏感操作。
        paused = graph.invoke({"question": "请模拟取消 A1001", "tenant_id": "acme"}, self.config)
        # (70) 审批必须绑定实际中断对象，不能测试中另造目标。
        return model, graph, paused, paused["__interrupt__"][0].value

    # (70) 最小查询沿用 model → Tool → model，不强行进入 RAG 或审批。
    def test_simple_query_counts_usage_and_keeps_sources(self):
        # (70) 第一个请求查业务，第二个生成总结。
        model, graph = self.build([response(calls=[tool_call("get_refund", "refund-1", {"order_id": "A1002"})]), response()])
        # (70) 读取项目 JSON，只读执行。
        result = graph.invoke(self.initial, self.config)
        # (70) 两次模型和一次 Tool 分别计数。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["tool_calls"]), ("final_answer", 2, 1))
        # (70) 模型每次报告 120 个测试 Token。
        self.assertEqual(result["total_tokens"], 240)
        # (70) 两条退款记录不被汇总日志替代或丢失。
        self.assertEqual(len(result["tool_results"][0]["result"]["data"]), 2)
        # (70) 普通查询不滥用资料检索。
        self.pipeline.ask.assert_not_called()
        # (70) 原调用 ID 正确回传。
        self.assert_tool_pairs(result, ["refund-1"])
        # (70) Token 明细不泄漏到模型消息里。
        self.assertNotIn("usage", model.requests[1]["messages"][-2])

    # (70) 一轮贯通订单、支付、退款和规则资料，按原 ID 分别返回。
    def test_multistep_business_and_rag_keep_citations(self):
        # (70) 批量请求的每个 Tool 仍由独立节点执行并保存进度。
        calls = [tool_call("get_order", "order", {"order_id": "A1002"}), tool_call("get_payment", "payment", {"order_id": "A1002"}), tool_call("get_refund", "refund", {"order_id": "A1002"}), tool_call("ask_knowledge_base", "kb", {"question": "退款通常多久到账"})]
        # (70) 准备一个选择工具和一个最终回答。
        model, graph = self.build([response(calls=calls), response()])
        # (70) 离线执行所有真实业务 Tool 和假资料检索。
        result = graph.invoke(self.initial, self.config)
        # (70) 业务查询和规则查询都记为实际工具尝试。
        self.assertEqual((result["stop_reason"], result["tool_calls"], len(model.requests)), ("final_answer", 4, 2))
        # (70) 工具信息保留各自来源，不只保留最后一个。
        self.assertEqual([item["tool_name"] for item in result["tool_results"]], ["get_order", "get_payment", "get_refund", "ask_knowledge_base"])
        # (70) RAG 引用作为 Tool 数据交给模型。
        self.assertEqual(result["tool_results"][-1]["result"]["data"]["citations"][0]["source"], "rules.md")
        # (70) 所有请求都有配对消息。
        self.assert_tool_pairs(result, ["order", "payment", "refund", "kb"])

    # (70) 查不到退款记录是成功空列表，不是系统错误。
    def test_no_refund_records_continue_to_model(self):
        # (70) A1003 存在但没有退款记录。
        model, graph = self.build([response(calls=[tool_call("get_refund", "empty", {"order_id": "A1003"})]), response()])
        # (70) 正常执行一次只读查询。
        result = graph.invoke(self.initial, self.config)
        # (70) 无记录允许模型解释，不重试查询。
        self.assertEqual((result["stop_reason"], result["tool_calls"], result["tool_retries"]), ("final_answer", 1, 0))
        # (70) 保留真实的成功空列表。
        self.assertEqual(result["tool_results"][0]["result"], tool_result(True, data=[]))

    # (70) 订单不存在时直接业务失败，后续同批请求不继续。
    def test_missing_order_stops_batch_without_retry(self):
        # (70) 第二个请求本来合法，但前面的业务失败要求提前停止。
        calls = [tool_call("get_order", "missing", {"order_id": "A9999"}), tool_call("get_refund", "skipped", {"order_id": "A1002"})]
        # (70) 不提供第二次模型响应，意外调用会使测试失败。
        model, graph = self.build([response(calls=calls)])
        # (70) 不存在订单依旧走实际 JSON 查询。
        result = graph.invoke(self.initial, self.config)
        # (70) 不把业务失败当成可恢复系统故障。
        self.assertEqual((result["stop_reason"], result["tool_calls"], result["tool_retries"], len(model.requests)), ("business_error", 1, 0, 1))
        # (70) 未执行项必须明确标记失败，而非假装空列表。
        self.assertFalse(result["tool_results"][1]["result"]["success"])
        # (70) 未执行请求也补齐 Tool 协议消息。
        self.assert_tool_pairs(result, ["missing", "skipped"])

    # (70) 模型临时连接错误有限重试，并保守计入未知用量。
    def test_model_temporary_failure_recovers_without_secret_logging(self):
        # (70) 故意放入敏感错误文本，检查不泄漏到追踪里。
        model, graph = self.build([ConnectionError("Authorization Bearer test-secret-70"), response()])
        # (70) 使用虚拟等待，不实际 sleep。
        result = graph.invoke(self.initial, self.config)
        # (70) 一次初始失败加一次恢复成功。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["model_retries"], len(model.requests)), ("final_answer", 2, 1, 2))
        # (70) 未知用量不是免费请求。
        self.assertEqual(result["usage_history"][0]["source"], "estimated_reservation")
        # (70) Tracing 不输出原始异常、请求头或密钥。
        self.assertNotIn("test-secret-70", json.dumps(result["trace_events"], ensure_ascii=False))

    # (70) 模型临时故障达到上限就结束，不无限循环。
    def test_model_retry_exhaustion_is_finite(self):
        # (70) 最多一次额外重试，两次预设都失败。
        model, graph = self.build([ConnectionError("offline"), ConnectionError("offline")], limits={"max_retries": 1})
        # (70) 图自身处理失败分支。
        result = graph.invoke(self.initial, self.config)
        # (70) 不能为总结错误再调用模型。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["model_retries"], len(model.requests)), ("model_retry_exhausted", 2, 1, 2))

    # (70) 永久模型错误不重试，即使仍有预算。
    def test_model_permanent_failure_does_not_retry(self):
        # (70) 错误协议不是暂时网络故障。
        model, graph = self.build([ValueError("secret-protocol-detail")])
        # (70) 外层失败分支受控结束。
        result = graph.invoke(self.initial, self.config)
        # (70) 不消耗额外模型次数修复永久错误。
        self.assertEqual((result["stop_reason"], result["model_retries"], len(model.requests)), ("model_error", 0, 1))
        # (70) 失败追踪只保留安全类别。
        self.assertNotIn("secret-protocol-detail", json.dumps(result["trace_events"], ensure_ascii=False))

    # (70) 只读 Tool 的临时错误允许有限重试，但结果只回传一次。
    def test_tool_temporary_error_recovers_with_single_tool_message(self):
        # (70) 模型请求一个退款查询。
        model, graph = self.build([response(calls=[tool_call("get_refund", "retry-tool", {"order_id": "A1002"})]), response()])
        # (70) 首次连接失败，第二次返回实际 JSON 的只读结果。
        with patch.object(diagnosis_agent, "dispatch_tool", side_effect=[ConnectionError("offline"), get_refund("A1002", "acme")]) as dispatch:
            # (70) 执行真实重试代码，不在测试替身里重试。
            result = graph.invoke(self.initial, self.config)
        # (70) 两次尝试只对应一个逻辑工具调用。
        self.assertEqual((result["stop_reason"], result["tool_calls"], result["tool_retries"], dispatch.call_count), ("final_answer", 2, 1, 2))
        # (70) 相同 call ID 不重复写工具消息。
        self.assert_tool_pairs(result, ["retry-tool"])

    # (70) Tool 永久异常或重试耗尽均不能继续后续模型请求。
    def test_tool_error_branches_are_finite(self):
        # (70) 分别验证永久故障与临时故障耗尽。
        for error, reason, attempts in ((ValueError("secret-tool-detail"), "tool_error", 1), (ConnectionError("offline"), "tool_retry_exhausted", 2)):
            # (70) 每个分支重新创建图，避免状态串扰。
            with self.subTest(reason=reason):
                # (70) 第二个请求必须被跳过并补齐协议。
                model, graph = self.build([response(calls=[tool_call("get_refund", "failed", {"order_id": "A1002"}), tool_call("get_order", "skipped", {"order_id": "A1002"})])], limits={"max_retries": 1})
                # (70) 只替换业务分发，不替换工作流节点。
                with patch.object(diagnosis_agent, "dispatch_tool", side_effect=error):
                    # (70) 通过实际图路由到失败结束。
                    result = graph.invoke(self.initial, self.config)
                # (70) 重试有上限，失败后不再总结。
                self.assertEqual((result["stop_reason"], result["tool_calls"], len(model.requests)), (reason, attempts, 1))
                # (70) 每条请求都具有对应响应。
                self.assert_tool_pairs(result, ["failed", "skipped"])
                # (70) 原始异常文本不写入追踪。
                self.assertNotIn("secret-tool-detail", json.dumps(result["trace_events"], ensure_ascii=False))

    # (70) 模型最大步骤数包含最终总结，耗尽后不能额外调用一次。
    def test_model_step_budget_stops_before_extra_summary(self):
        # (70) 一次选工具已经用完唯一模型步骤。
        model, graph = self.build([response(calls=[tool_call("get_refund", "step", {"order_id": "A1002"})])], limits={"max_steps": 1})
        # (70) 工具结果可保留，但不能超预算总结。
        result = graph.invoke(self.initial, self.config)
        # (70) 请求前检查阻止第二次模型。
        self.assertEqual((result["stop_reason"], result["model_steps"], len(model.requests)), ("max_steps", 1, 1))
        # (70) 不会留下未配对的工具调用。
        self.assert_tool_pairs(result, ["step"])

    # (70) Tool 额度不足时不执行剩余请求，并保留已成功证据。
    def test_tool_budget_preserves_first_result_and_skips_next(self):
        # (70) 同批两个普通工具，仅允许一次执行。
        calls = [tool_call("get_order", "first", {"order_id": "A1002"}), tool_call("get_refund", "second", {"order_id": "A1002"})]
        # (70) 第二次模型无预算分支不需要执行。
        model, graph = self.build([response(calls=calls)], limits={"max_tool_calls": 1})
        # (70) 以实际 Tool 调用额度终止。
        result = graph.invoke(self.initial, self.config)
        # (70) 第一项成功，第二项未执行，不把两项都丢弃。
        self.assertEqual((result["stop_reason"], result["tool_calls"], [item["result"]["success"] for item in result["tool_results"]]), ("tool_limit", 1, [True, False]))
        # (70) 预算失败同样补齐原始工具 ID。
        self.assert_tool_pairs(result, ["first", "second"])

    # (70) 临时 Tool 重试也消耗同一个总 Tool 额度。
    def test_tool_retry_cannot_bypass_total_tool_budget(self):
        # (70) 只允许一次尝试，不允许再重试。
        model, graph = self.build([response(calls=[tool_call("get_refund", "limited", {"order_id": "A1002"})])], limits={"max_tool_calls": 1})
        # (70) 一次临时异常后即应停止。
        with patch.object(diagnosis_agent, "dispatch_tool", side_effect=ConnectionError("offline")) as dispatch:
            # (70) 没有后台重试或独立预算。
            result = graph.invoke(self.initial, self.config)
        # (70) 不能借重试跳过 Tool 上限。
        self.assertEqual((result["stop_reason"], result["tool_calls"], dispatch.call_count), ("tool_limit", 1, 1))

    # (70) Token 和费用都在请求前预留，额度不足则零模型请求。
    def test_token_and_cost_budgets_stop_before_request(self):
        # (70) 分别设置明显不足的额度。
        for limits, reason in (({"max_total_tokens": 1}, "token_budget"), ({"max_cost": "0.00000001"}, "cost_budget")):
            # (70) 每个额度单独验证，避免一个限制掩盖另一个。
            with self.subTest(reason=reason):
                # (70) 不预设回答，意外请求立即暴露。
                model, graph = self.build([], limits=limits)
                # (70) 请求前预算分支直接结束。
                result = graph.invoke(self.initial, self.config)
                # (70) 从未发出的请求不能计为已花费 Token。
                self.assertEqual((result["stop_reason"], result["model_steps"], result["total_tokens"], model.requests), (reason, 0, 0, []))

    # (70) 实际接口用量超出预估后停止 Tool 调度，不再增加费用。
    def test_reported_usage_exhaustion_stops_before_tool_execution(self):
        # (70) 将已返回用量故意设为超过整个任务的上限。
        huge_usage = {"prompt_tokens": 100001, "completion_tokens": 1, "total_tokens": 100002}
        # (70) 消息仍请求业务 Tool，但额度已被这次模型用完。
        model, graph = self.build([response(calls=[tool_call("get_refund", "over", {"order_id": "A1002"})], usage=huge_usage)])
        # (70) 完成本次已发生请求的记账后终止。
        result = graph.invoke(self.initial, self.config)
        # (70) 不因请求里有 Tool 就越过用量限制。
        self.assertEqual((result["stop_reason"], result["tool_calls"], result["total_tokens"]), ("token_budget", 0, 100002))
        # (70) 未执行工具依旧配上原因消息。
        self.assert_tool_pairs(result, ["over"])

    # (70) RAG 内层 LLM 与外层共享模型次数、Token 和费用。
    def test_rag_inner_model_usage_is_counted_once(self):
        # (70) 内层报告 40 个 Token，与外层的两次 120 分开。
        inner = InnerModel()
        # (70) 用轻量 Pipeline 调用真实共享执行器。
        model, graph = self.build([response(calls=[tool_call("ask_knowledge_base", "inner", {"question": "退款规则"})]), response()], pipeline=InnerPipeline(inner))
        # (70) 不执行检索数据库，只测试模型账本贯通。
        result = graph.invoke(self.initial, self.config)
        # (70) 两次外层加一次内层等于三次模型请求。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["total_tokens"], len(model.requests), len(inner.calls)), ("final_answer", 3, 280, 2, 1))
        # (70) 账单来源区分外层 Agent 与内层 RAG，不能重复加总父节点。
        self.assertEqual([item["scope"] for item in result["usage_history"]], ["agent_model", "rag_model", "agent_model"])
        # (70) SDK 不能在预算执行器之外隐藏重试。
        self.assertEqual(inner.calls[0]["max_retries"], 0)

    # (70) 外层用完模型次数后，RAG 内层不得绕过上限发请求。
    def test_rag_inner_model_respects_shared_step_limit(self):
        # (70) 第一次外层选工具就耗尽唯一模型额度。
        inner = InnerModel()
        # (70) RAG 仍由真实 Tool 调用，但内部不能开始请求。
        model, graph = self.build([response(calls=[tool_call("ask_knowledge_base", "inner-blocked", {"question": "退款规则"})])], limits={"max_steps": 1}, pipeline=InnerPipeline(inner))
        # (70) 内层失败沿原任务受控结束。
        result = graph.invoke(self.initial, self.config)
        # (70) 不把内层次数独立重置为零。
        self.assertEqual((result["stop_reason"], result["model_steps"], len(inner.calls)), ("max_steps", 1, 0))
        # (70) 预算不足也为资料请求返回配对失败结果。
        self.assert_tool_pairs(result, ["inner-blocked"])

    # (70) RAG 已生成结果时保留规则证据，但不能绕过额度再做外层总结。
    def test_rag_result_is_preserved_when_summary_step_budget_is_exhausted(self):
        # (70) 额度只够一次外层决策和一次内层规则生成。
        inner = InnerModel()
        # (70) 第二条外层响应不提供，避免意外超预算被掩盖。
        model, graph = self.build([response(calls=[tool_call("ask_knowledge_base", "kb-limited", {"question": "退款规则"})])], limits={"max_steps": 2}, pipeline=InnerPipeline(inner))
        # (70) 资料生成仍使用共享账本。
        result = graph.invoke(self.initial, self.config)
        # (70) 两次模型尝试全部计入，没有额外总结。
        self.assertEqual((result["stop_reason"], result["model_steps"], result["total_tokens"], len(model.requests), len(inner.calls)), ("max_steps", 2, 160, 1, 1))
        # (70) 已获得的规则与来源不因后续预算失败而清空。
        self.assertEqual(result["tool_results"][0]["result"]["data"]["citations"][0]["source"], "refund-rules.md")

    # (70) RAG 内层永久错误保留失败阶段，不把原始异常写进追踪。
    def test_rag_inner_failure_is_traced_and_stops_outer_followup(self):
        # (70) 敏感错误内容只能用于测试泄漏防护。
        inner = InnerModel(error=ValueError("private-inner-model-secret-70"))
        # (70) 模型只发起资料查询，失败后不应再要求总结。
        model, graph = self.build([response(calls=[tool_call("ask_knowledge_base", "kb-failed", {"question": "退款规则"})])], pipeline=InnerPipeline(inner))
        # (70) 内层错误沿统一受控失败流程返回。
        result = graph.invoke(self.initial, self.config)
        # (70) 一次外层加一次内层，不重试永久错误。
        self.assertEqual((result["model_steps"], len(model.requests), len(inner.calls)), (2, 1, 1))
        # (70) 原始错误内容不进入安全追踪。
        self.assertNotIn("private-inner-model-secret-70", json.dumps(result["trace_events"], ensure_ascii=False))
        # (70) 资料工具返回明确失败并与原请求配对。
        self.assertFalse(result["tool_results"][0]["result"]["success"])
        # (70) 即使内部失败，也不能留下孤立的 assistant 工具调用。
        self.assert_tool_pairs(result, ["kb-failed"])

    # (70) 真实 RAG 管道贯通六个阶段，用量只从实际模型事件统计一次。
    def test_real_rag_pipeline_traces_all_stages_and_counts_once(self):
        # (70) 使用内存文档，不连接向量库或全文检索服务。
        pipeline = self.real_pipeline([Hit("rule-1", "doc-1", "退款通常按支付渠道到账。", source="real-rules.md", rerank_score=0.9)])
        # (70) 外层选资料工具，内层生成规则，再由外层总结。
        model, graph = self.build([response(calls=[tool_call("ask_knowledge_base", "real-kb", {"question": "退款通常多久到账"})]), response()], pipeline=pipeline)
        # (70) 只有检索和模型是替身，RAG 编排与校验是真实实现。
        result = graph.invoke(self.initial, self.config)
        # (70) 取各阶段结束事件，开始事件不重复计算。
        stages = [item["name"] for item in result["trace_events"] if item.get("phase") == "end" and item.get("kind") == "node" and item.get("name", "").startswith("rag_")]
        # (70) 能定位意图、召回、精排、上下文、生成和引用校验六个阶段。
        self.assertEqual(stages, ["rag_query", "rag_retrieve", "rag_rerank", "rag_context", "rag_generate", "rag_validate"])
        # (70) 父 Tool 与父节点不再重复累计子模型 Token。
        self.assertEqual((result["trace_summary"]["llm_attempts"], result["trace_summary"]["known_total_tokens"], result["total_tokens"]), (3, 280, 280))
        # (70) 真实引用校验保留候选来源。
        self.assertEqual(result["tool_results"][0]["result"]["data"]["citations"][0]["source"], "real-rules.md")

    # (70) 真实 RAG 无证据时跳过内层模型，不产生虚假的 Token 或费用。
    def test_real_rag_insufficient_evidence_skips_inner_model(self):
        # (70) 零候选只走到上下文整理，之后按原规则拒答。
        pipeline = self.real_pipeline([])
        # (70) 外层仍可以基于明确的资料不足状态结束。
        model, graph = self.build([response(calls=[tool_call("ask_knowledge_base", "no-evidence", {"question": "退款规则"})]), response()], pipeline=pipeline)
        # (70) 调用真实管道，不用 Mock 返回不足状态。
        result = graph.invoke(self.initial, self.config)
        # (70) 内层模型从未请求，外层两次用量正常计入。
        self.assertEqual((pipeline.llm.calls, result["model_steps"], result["total_tokens"]), ([], 2, 240))
        # (70) 资料不足不是工具执行异常，也不重试。
        self.assertEqual((result["stop_reason"], result["tool_retries"], result["tool_results"][0]["result"]["data"]["status"]), ("final_answer", 0, "insufficient_evidence"))
        # (70) 没有开始生成阶段，不能统计不存在的模型调用。
        self.assertNotIn("rag_generate", [item["name"] for item in result["trace_events"]])

    # (70) 真实检索失败能指出 rag_retrieve 阶段，且不记录原始数据库错误。
    def test_real_rag_retrieval_failure_keeps_stage_without_secret(self):
        # (70) 管道本身真实执行，只有检索器抛出内存异常。
        pipeline = self.real_pipeline([])
        # (70) 错误正文故意带秘密标记，不能进入 Tracing。
        pipeline.retriever.retrieve.side_effect = ValueError("db-password-secret-70")
        # (70) 永久检索错误后不准备额外外层回答。
        model, graph = self.build([response(calls=[tool_call("ask_knowledge_base", "retrieve-failed", {"question": "退款规则"})])], pipeline=pipeline)
        # (70) 真实 ask 错误边界会结束当前阶段并交给工作流。
        result = graph.invoke(self.initial, self.config)
        # (70) 找到真正失败的召回阶段，而非只有笼统 Tool 失败。
        failures = [item for item in result["trace_events"] if item.get("phase") == "end" and item.get("name") == "rag_retrieve"]
        # (70) 失败有明确阶段与错误状态。
        self.assertEqual([item["status"] for item in failures], ["error"])
        # (70) 未开始生成，不能计算内层请求。
        self.assertEqual((len(model.requests), pipeline.llm.calls, result["stop_reason"]), (1, [], "tool_error"))
        # (70) 原始异常文本不会泄漏到追踪或汇总。
        self.assertNotIn("db-password-secret-70", json.dumps(result["trace_events"], ensure_ascii=False))

    # (70) 真实管道生成阶段额度不足时应指向 rag_generate，不能当无证据。
    def test_real_rag_generation_budget_failure_keeps_stage(self):
        # (70) 候选证据足够，仅故意耗尽模型步骤。
        pipeline = self.real_pipeline([Hit("rule-1", "doc-1", "退款按渠道到账。", rerank_score=0.9)])
        # (70) 唯一模型额度由外层选工具使用。
        model, graph = self.build([response(calls=[tool_call("ask_knowledge_base", "generate-blocked", {"question": "退款规则"})])], limits={"max_steps": 1}, pipeline=pipeline)
        # (70) 执行到生成阶段，但不发起内层请求。
        result = graph.invoke(self.initial, self.config)
        # (70) 保留预算停止原因而不是改写为工具普通失败。
        self.assertEqual((result["stop_reason"], pipeline.llm.calls, result["model_steps"]), ("max_steps", [], 1))
        # (70) 生成阶段明确结束为失败，支持定位额度不足发生处。
        failures = [item for item in result["trace_events"] if item.get("phase") == "end" and item.get("name") == "rag_generate"]
        # (70) 不应遗留一个永不结束的生成跨度。
        self.assertEqual([item["status"] for item in failures], ["error"])

    # (69) 真实 RAG 模型适配器保留 SDK 参数、用量和响应结构，不连接服务。
    def test_rag_sdk_request_forwards_limits_and_preserves_response_fields(self):
        # (69) 使用真实 SDK 响应类型，只在内存中构造。
        reply = ChatCompletion(id="offline-rag", object="chat.completion", created=0, model="test", choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "规则见 [1]。"}}], usage={"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14})
        # (69) 配置超时不同于 None，验证显式关闭超时不会被默认值覆盖。
        settings = Settings(llm_api_key="offline-only", llm_timeout=123)
        # (69) 请求和构造都替换，不访问真实 LLM API。
        with patch("openai.OpenAI") as client_class:
            # (69) 客户端上下文返回离线响应。
            client = client_class.return_value.__enter__.return_value
            # (69) 模型消息与用量都来自这一固定内存对象。
            client.chat.completions.create.return_value = reply
            # (69) 执行真实适配代码，不让 SDK 自己做隐藏重试。
            result = CompatibleChatModel(settings).request([{"role": "user", "content": "退款规则"}], timeout=None, max_tokens=77, max_retries=0)
        # (69) None 原样传给 SDK，Debug 暂停不会变成 HTTP 超时。
        self.assertIsNone(client_class.call_args.kwargs["timeout"])
        # (69) 请求输出上限由调用方提供。
        self.assertEqual((client_class.call_args.kwargs["max_retries"], client.chat.completions.create.call_args.kwargs["max_tokens"]), (0, 77))
        # (69) 内容、usage 和结束原因独立返回，不混入正文。
        self.assertEqual(result, {"content": "规则见 [1]。", "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}, "finish_reason": "stop"})

    # (70) SDK 缺失 usage 时预算保守预留，但追踪的真实 Token 必须是未知。
    def test_missing_rag_sdk_usage_is_reserved_but_trace_tokens_stay_unknown(self):
        # (69) 真实响应没有 usage，不能自行补成零用量。
        reply = ChatCompletion(id="offline-rag-unknown", object="chat.completion", created=0, model="test", choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"answerable":true,"answer":"退款按渠道到账 [1]。","citations":[1]}'}}])
        # (69) 真实适配器只使用内存中的占位配置。
        llm = CompatibleChatModel(Settings(llm_api_key="offline-only"))
        # (70) 除检索和精排替身外，使用真实管道与真实模型适配器。
        pipeline = self.real_pipeline([Hit("rule-unknown", "doc-1", "退款按渠道到账。", rerank_score=0.9)], llm=llm)
        # (70) 外层两次调用有用量，内层 SDK 这一调用用量未知。
        model, graph = self.build([response(calls=[tool_call("ask_knowledge_base", "unknown-usage", {"question": "退款规则"})]), response()], pipeline=pipeline)
        # (69) SDK 构造和网络请求被完全替换。
        with patch("openai.OpenAI") as client_class:
            # (69) 真实 request 解析这一无 usage 响应。
            client_class.return_value.__enter__.return_value.chat.completions.create.return_value = reply
            # (70) 共享执行器负责本轮记账，不能让内层遗漏预算。
            result = graph.invoke(self.initial, self.config)
        # (70) 只在未知调用上采用保守预留。
        self.assertEqual(result["usage_history"][1]["source"], "estimated_reservation")
        # (70) 已知外层 240 个 Token 之外还有内层预留，不能算成免费。
        self.assertGreater(result["total_tokens"], 240)
        # (69) 只取内层实际模型调用的结束记录。
        unknown = [item for item in result["trace_events"] if item.get("kind") == "llm" and item.get("name") == "rag_model" and item.get("phase") == "end"]
        # (69) 未知 Token 和费用保持 None，不把保护性估计冒充实测。
        self.assertEqual([(item["usage_source"], item["input_tokens"], item["output_tokens"], item["total_tokens"], item["estimated_cost"]) for item in unknown], [("unknown", None, None, None, None)])
        # (69) 汇总明确有一条用量未知，不能显示完整费用。
        self.assertEqual((result["trace_summary"]["unknown_usage_calls"], result["trace_summary"]["estimated_cost"], result["trace_summary"]["cost_is_partial"]), (1, None, True))

    # (70) 敏感操作前保存状态，确认后模拟一次，原始 JSON 永远不改。
    def test_approval_executes_once_and_repeated_resume_is_safe(self):
        # (70) 只读原始字节作对照，不创建备份或改业务文件。
        original = DEFAULT_DATA_FILE.read_bytes()
        # (70) 包住模拟函数，确认实际执行次数。
        with patch.object(diagnosis_agent, "simulate_cancel_order", wraps=diagnosis_agent.simulate_cancel_order) as simulate:
            # (70) 第一次只选工具并暂停。
            model, graph, paused, request = self.pause_cancel()
            # (70) 未人工批准之前不能执行模拟。
            simulate.assert_not_called()
            # (70) 使用原审批参数绑定目标，仅增加人工决定。
            decision = Command(resume={**request, "decision": "approve"})
            # (70) 同一个配置恢复此前暂停任务。
            result = graph.invoke(decision, self.config)
            # (70) 已结束的工作流重复恢复，不能重放敏感操作。
            repeated = graph.invoke(decision, self.config)
        # (70) 重复恢复既不执行第二次，也不再调用模型。
        self.assertEqual((result["stop_reason"], simulate.call_count, len(model.requests)), ("final_answer", 1, 2))
        # (70) 同会话保留一条简单防重复记录。
        self.assertEqual((result["simulated_cancellations"], repeated["simulated_cancellations"]), (["A1001"], ["A1001"]))
        # (70) 模拟执行不能伪装成原业务数据已改变。
        self.assertTrue(result["tool_results"][0]["result"]["data"]["simulated"])
        # (70) 原始 JSON 未变。
        self.assertEqual(DEFAULT_DATA_FILE.read_bytes(), original)

    # (70) 拒绝或篡改目标都结束，不执行模拟，也不再请求模型。
    def test_approval_rejected_or_invalid_never_executes(self):
        # (70) 合法拒绝与越权确认分别走明确原因。
        for change, reason in (({"decision": "reject"}, "approval_rejected"), ({"decision": "approve", "order_id": "A1002"}, "approval_invalid")):
            # (70) 每个分支使用全新真实暂停状态。
            with self.subTest(reason=reason):
                # (70) 监测敏感执行边界。
                with patch.object(diagnosis_agent, "simulate_cancel_order", wraps=diagnosis_agent.simulate_cancel_order) as simulate:
                    # (70) 后续普通请求也应按停止原因跳过。
                    calls = [tool_call("cancel_order", "cancel-1", {"order_id": "A1001"}), tool_call("get_order", "later", {"order_id": "A1002"})]
                    # (70) 获取当前待确认目标。
                    model, graph, paused, request = self.pause_cancel(calls=calls)
                    # (70) 提交拒绝或故意错配订单的决定。
                    result = graph.invoke(Command(resume={**request, **change}), self.config)
                # (70) 人工决定不是另起一轮模型请求。
                self.assertEqual((result["stop_reason"], len(model.requests)), (reason, 1))
                # (70) 未确认或确认目标不一致均不得执行。
                simulate.assert_not_called()
                # (70) 后续请求被补成未执行响应，协议仍完整。
                self.assert_tool_pairs(result, ["cancel-1", "later"])

    # (70) 即使订单和 call ID 相同，其他会话的旧批准也不能用于本会话。
    def test_approval_from_other_thread_is_rejected_even_with_same_call_id(self):
        # (70) 故意让两次模型请求使用相同工具调用编号。
        same_call = tool_call("cancel_order", "same-call", {"order_id": "A1001"})
        # (70) 两会话各自暂停，不提供任何总结响应。
        model, graph = self.build([response(calls=[same_call]), response(calls=[same_call])])
        # (70) 第一个会话保存自己的待审批目标。
        first = graph.invoke({"question": "取消 A1001", "tenant_id": "acme"}, self.config)
        # (70) 第二会话的身份相同，但执行编号应不同。
        other_config = {"configurable": {"thread_id": "approval-other-thread"}}
        # (70) 同一张图仍需要为新会话生成独立审批记录。
        other = graph.invoke({"question": "取消 A1001", "tenant_id": "acme"}, other_config)
        # (70) 构造来自第一会话的确认，不能覆盖成第二会话的新目标。
        old_decision = {**first["__interrupt__"][0].value, "decision": "approve"}
        # (70) 跨会话提交时绝不能执行敏感操作。
        with patch.object(diagnosis_agent, "simulate_cancel_order", wraps=diagnosis_agent.simulate_cancel_order) as simulate:
            # (70) 保持第二会话 config，但故意使用旧会话的批准对象。
            result = graph.invoke(Command(resume=old_decision), other_config)
        # (70) call ID 一致仍需 run_id 匹配，不能只校验订单号。
        self.assertNotEqual(first["__interrupt__"][0].value["run_id"], other["__interrupt__"][0].value["run_id"])
        # (70) 错配批准受控拒绝，不回模型。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("approval_invalid", 2))
        # (70) 没有任何敏感执行。
        simulate.assert_not_called()

    # (70) 同一个 thread 的新问题也不能借用上一轮的审批目标。
    def test_approval_from_previous_run_is_rejected_on_same_thread(self):
        # (70) 让两个新问题使用完全相同的模型调用 ID 和订单号。
        same_call = tool_call("cancel_order", "same-call", {"order_id": "A1001"})
        # (70) 两次模型均只提出取消，由人工分别处理。
        model, graph = self.build([response(calls=[same_call]), response(calls=[same_call])])
        # (70) 第一轮正常生成待审批目标。
        first = graph.invoke({"question": "取消 A1001", "tenant_id": "acme"}, self.config)
        # (70) 保存旧目标，稍后模拟错误地重放批准。
        old_request = first["__interrupt__"][0].value
        # (70) 第一轮拒绝结束，不把订单写入已模拟清单。
        graph.invoke(Command(resume={**old_request, "decision": "reject"}), self.config)
        # (70) 新问题产生新的 run_id，但仍使用同一个 thread_id。
        second = graph.invoke({"question": "重新申请取消 A1001", "tenant_id": "acme"}, self.config)
        # (70) 新一轮需要与自己的实际审批记录匹配。
        self.assertNotEqual(old_request["run_id"], second["__interrupt__"][0].value["run_id"])
        # (70) 检查旧审批参数不会导致实际执行。
        with patch.object(diagnosis_agent, "simulate_cancel_order", wraps=diagnosis_agent.simulate_cancel_order) as simulate:
            # (70) 故意携带旧 run_id 对新一轮提交批准。
            result = graph.invoke(Command(resume={**old_request, "decision": "approve"}), self.config)
        # (70) 新轮的错误批准受控结束，不继承上轮权限。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("approval_invalid", 2))
        # (70) 不执行敏感操作。
        simulate.assert_not_called()

    # (70) 敏感执行即使发生临时异常也不自动重试，结果明确为未确认。
    def test_cancel_execution_error_is_not_retried_or_reported_as_not_executed(self):
        # (70) 真实运行到审批暂停，错误只发生在确认后的执行阶段。
        model, graph, paused, request = self.pause_cancel(limits={"max_retries": 3})
        # (70) 错误正文含敏感标记，不能记录到结果或日志。
        with patch.object(diagnosis_agent, "simulate_cancel_order", side_effect=TimeoutError("private-action-secret-70")) as simulate:
            # (70) 批准后一次执行超时，不得拿只读重试策略重放。
            result = graph.invoke(Command(resume={**request, "decision": "approve"}), self.config)
        # (70) 一次执行尝试，无额外模型总结或自动 Tool 重试。
        self.assertEqual((result["stop_reason"], simulate.call_count, result["tool_calls"], result["tool_retries"], len(model.requests)), ("action_error", 1, 1, 0, 1))
        # (70) 未确认结果不写成功模拟记录。
        self.assertEqual(result["simulated_cancellations"], [])
        # (70) 对可能有副作用的失败不能声称确定没执行。
        self.assertIn("结果未确认", result["answer"])
        # (70) 错误事件保留超时类别，不保留原始异常。
        events = [item for item in result["trace_events"] if item.get("kind") == "tool" and item.get("name") == "cancel_order" and item.get("phase") == "end"]
        # (70) 分类足以定位故障类型。
        self.assertEqual([(item["status"], item["error_kind"]) for item in events], [("error", "timeout")])
        # (70) 异常原文不进入任何 State 日志或 Tool 返回。
        self.assertNotIn("private-action-secret-70", json.dumps(result, ensure_ascii=False))
        # (70) 失败 Tool 与原调用仍有完整协议配对。
        self.assert_tool_pairs(result, ["cancel-1"])

    # (70) 人工等待期间订单已支付时，旧批准不能覆盖新的业务状态。
    def test_order_state_change_during_approval_blocks_simulation(self):
        # (70) 保存原始字节作只读对照，不创建或清理任何目录。
        original = DEFAULT_DATA_FILE.read_bytes()
        # (70) 审批前读到真实样例中的待支付状态。
        pending = get_order("A1001", "acme")
        # (70) 第二次只在替身响应中改状态，不修改原始 JSON。
        paid = {**pending, "data": {**pending["data"], "status": "已支付"}}
        # (70) 审批准备和真正执行前分别读取一次状态。
        with patch.object(diagnosis_agent, "get_order", side_effect=[pending, paid]) as read_order, patch.object(diagnosis_agent, "simulate_cancel_order", wraps=diagnosis_agent.simulate_cancel_order) as simulate:
            # (70) 初次检查待支付，因此允许生成待审批请求。
            model, graph, paused, request = self.pause_cancel()
            # (70) 人工确认后必须按最新状态再次检查。
            result = graph.invoke(Command(resume={**request, "decision": "approve"}), self.config)
        # (70) 旧批准不能放行已支付订单，且不再请求模型总结。
        self.assertEqual((result["stop_reason"], read_order.call_count, len(model.requests)), ("business_error", 2, 1))
        # (70) 没有实际模拟执行，也不保存成功模拟记录。
        simulate.assert_not_called()
        # (70) 失败仍有对应的 Tool 消息，不破坏模型协议。
        self.assert_tool_pairs(result, ["cancel-1"])
        # (70) 业务事实改变只存在测试副本，原始文件未修改。
        self.assertEqual(DEFAULT_DATA_FILE.read_bytes(), original)

    # (70) 审批恢复必须沿用已有账本，不能重置预算逃过步骤上限。
    def test_resume_does_not_reset_model_budget_or_run_identity(self):
        # (70) 第一次模型选择取消后已经用完模型步骤。
        model, graph, paused, request = self.pause_cancel(limits={"max_steps": 1})
        # (70) 记住暂停前的执行编号和用量。
        identity = (paused["run_id"], paused["model_steps"], paused["total_tokens"])
        # (70) 合法确认允许模拟，但不能超预算生成额外总结。
        result = graph.invoke(Command(resume={**request, "decision": "approve"}), self.config)
        # (70) 恢复不走 prepare 重置本轮计数。
        self.assertEqual((result["run_id"], result["model_steps"], result["total_tokens"]), identity)
        # (70) 第二次模型被上限阻止。
        self.assertEqual((result["stop_reason"], len(model.requests)), ("max_steps", 1))

    # (70) 普通 Tool 后再审批，恢复时不应重做已完成查询。
    def test_resume_does_not_repeat_preceding_read_tool(self):
        # (70) 先查询退款，再审批取消不同订单。
        calls = [tool_call("get_refund", "before", {"order_id": "A1002"}), tool_call("cancel_order", "cancel-1", {"order_id": "A1001"})]
        # (70) 包住分发函数检查真实只读调用次数。
        with patch.object(diagnosis_agent, "dispatch_tool", wraps=diagnosis_agent.dispatch_tool) as dispatch:
            # (70) 首次调用已完成查询并暂停在取消审批。
            model, graph, paused, request = self.pause_cancel(calls=calls)
            # (70) 恢复从审批节点开始，不是从工具批次开头。
            result = graph.invoke(Command(resume={**request, "decision": "approve"}), self.config)
        # (70) 审批前的普通查询只执行一次。
        self.assertEqual(dispatch.call_count, 1)
        # (70) 两个请求顺序配对，未重复保存查询结果。
        self.assert_tool_pairs(result, ["before", "cancel-1"])

    # (70) 同会话新一轮再次取消已模拟订单，不重复执行也不再次审批。
    def test_same_thread_duplicate_cancel_does_not_execute_again(self):
        # (70) 两轮模型都提出同一个订单，但使用各自的调用 ID。
        responses = [response(calls=[tool_call("cancel_order", "cancel-first", {"order_id": "A1001"})]), response(), response(calls=[tool_call("cancel_order", "cancel-again", {"order_id": "A1001"})]), response()]
        # (70) Memory 和模拟防重复记录由同一个 Checkpoint 保存。
        model, graph = self.build(responses)
        # (70) 包住模拟执行函数，避免仅凭最终文字判断。
        with patch.object(diagnosis_agent, "simulate_cancel_order", wraps=diagnosis_agent.simulate_cancel_order) as simulate:
            # (70) 第一轮正常进入审批。
            paused = graph.invoke({"question": "取消 A1001", "tenant_id": "acme"}, self.config)
            # (70) 审批目标来自当前中断记录。
            request = paused["__interrupt__"][0].value
            # (70) 第一轮确认后执行模拟。
            graph.invoke(Command(resume={**request, "decision": "approve"}), self.config)
            # (70) 第二轮同订单直接返回已有模拟记录。
            second = graph.invoke({"question": "再取消 A1001", "tenant_id": "acme"}, self.config)
        # (70) 不能为同一会话同一订单再次执行。
        self.assertEqual(simulate.call_count, 1)
        # (70) 新轮不再暂停，也不把防重复结果当真实取消。
        self.assertNotIn("__interrupt__", second)
        # (70) 重复调用结果明确注明未执行。
        self.assertTrue(second["tool_results"][0]["result"]["data"]["duplicate"])

    # (70) 非待支付或不存在的订单必须在人工审批前失败。
    def test_unsupported_cancel_does_not_pause_or_execute(self):
        # (70) 已支付订单和不存在订单都不支持本课模拟取消。
        for order_id in ("A1002", "A9999"):
            # (70) 各业务分支独立执行。
            with self.subTest(order_id=order_id):
                # (70) 只提供模型的取消请求。
                model, graph = self.build([response(calls=[tool_call("cancel_order", "unsupported", {"order_id": order_id})])])
                # (70) 实际执行业务校验，不伪造审批结果。
                result = graph.invoke(self.initial, self.config)
                # (70) 不向用户请求业务上不支持的授权。
                self.assertNotIn("__interrupt__", result)
                # (70) 失败不产生模拟记录或额外模型请求。
                self.assertEqual((result["simulated_cancellations"], len(model.requests)), ([], 1))
                # (70) 失败也完成原始工具调用协议。
                self.assert_tool_pairs(result, ["unsupported"])

    # (70) 同会话追问保留消息，但每个新问题重新开始本轮统计。
    def test_followup_keeps_history_but_resets_round_budget_and_trace(self):
        # (70) 两轮都是直接回答，不涉及外部服务。
        model, graph = self.build([response(), response()])
        # (70) 首轮建立 Memory。
        first = graph.invoke(self.initial, self.config)
        # (70) 新问题只传输入，不手动覆盖消息和预算。
        second = graph.invoke({"question": "它现在的情况呢", "tenant_id": "acme"}, self.config)
        # (70) 同一会话的新执行编号不同。
        self.assertNotEqual(first["run_id"], second["run_id"])
        # (70) 本轮账本重新计一次请求，而不是两轮累计。
        self.assertEqual((first["model_steps"], second["model_steps"], second["total_tokens"]), (1, 1, 120))
        # (70) 会话历史仍可用于追问。
        self.assertEqual([item["content"] for item in model.requests[1]["messages"] if item["role"] == "user"], [self.initial["question"], "它现在的情况呢"])

    # (70) 不同 thread_id 隔离消息、模拟记录和追踪身份。
    def test_threads_do_not_share_memory_or_trace(self):
        # (70) 同一张图服务两个独立会话。
        model, graph = self.build([response(), response()])
        # (70) 第一个会话查询退款。
        first = graph.invoke(self.initial, self.config)
        # (70) 第二会话通过新的 thread_id 独立执行。
        second = graph.invoke({"question": "查询 A1001", "tenant_id": "acme"}, {"configurable": {"thread_id": "diagnosis-other"}})
        # (70) 第二次请求看不到第一会话的问题。
        self.assertEqual([item["content"] for item in model.requests[1]["messages"] if item["role"] == "user"], ["查询 A1001"])
        # (70) 追踪明确标注实际会话编号。
        self.assertEqual((first["thread_id"], second["thread_id"]), ("diagnosis-test", "diagnosis-other"))
        # (70) 第一会话的结果未被第二会话覆盖。
        self.assertEqual(graph.get_state(self.config).values["run_id"], first["run_id"])

    # (70) 裁剪按完整轮次处理，保持当前用户问题和系统规则。
    def test_zero_history_turns_removes_previous_round(self):
        # (70) 不保留旧轮次，仍保留正在执行的本轮。
        model, graph = self.build([response(), response()], max_history_turns=0)
        # (70) 先完成一个普通问题。
        graph.invoke(self.initial, self.config)
        # (70) 再询问一个新的问题。
        graph.invoke({"question": "新问题", "tenant_id": "acme"}, self.config)
        # (70) 第二轮只有当前问题，不留下孤立旧消息。
        self.assertEqual([item["role"] for item in model.requests[1]["messages"]], ["system", "user"])
        # (70) 当前问题不能在裁剪中丢掉。
        self.assertEqual(model.requests[1]["messages"][-1]["content"], "新问题")

    # (70) 当前问题过大时在模型前结束，而非截断成另一问题。
    def test_context_character_budget_stops_without_model(self):
        # (70) 系统规则和 Schema 已超过这个极小上限。
        model, graph = self.build([], max_context_chars=1)
        # (70) 使用真实上下文检查，不启用 API tokenizer。
        result = graph.invoke(self.initial, self.config)
        # (70) 没有真实请求，也没有计费。
        self.assertEqual((result["stop_reason"], model.requests, result["total_tokens"]), ("context_budget", [], 0))

    # (70) 默认仅统计时间，不因人工输入或 Debug 等待超时。
    def test_default_timeout_switch_is_disabled_during_approval_wait(self):
        # (70) 不传时间开关，检查本课默认值。
        model = ScriptedBudgetModel([response(calls=[tool_call("cancel_order", "wait", {"order_id": "A1001"})]), response()])
        # (70) 其他预算保持真实默认值，使用虚拟时钟。
        graph = diagnosis_agent.build_graph(model, self.pipeline, self.filters, InMemorySaver(), clock=self.clock, sleep=self.clock.sleep)
        # (70) 首次执行到实际审批点。
        paused = graph.invoke({"question": "取消 A1001", "tenant_id": "acme"}, self.config)
        # (70) 模拟长时间单步调试或人工等待。
        self.clock.now += 100000
        # (70) 人工确认后按原状态继续。
        result = graph.invoke(Command(resume={**paused["__interrupt__"][0].value, "decision": "approve"}), self.config)
        # (70) 默认关闭时间限制，但仍记录流逝时间。
        self.assertEqual((result["limits"]["enable_timeouts"], result["stop_reason"]), (False, "final_answer"))

    # (70) 用户问题中的伪造 Token 或错误文本不进入追踪正文。
    def test_tracing_does_not_dump_question_or_raw_tool_results(self):
        # (70) 在用户内容放入可识别的敏感标记。
        secret = "private-question-secret-70"
        # (70) 模型直接回复，避免任何模型推断依赖。
        model, graph = self.build([response()])
        # (70) 业务输入保留在 State，但不得被自动当日志正文输出。
        result = graph.invoke({"question": f"查询 A1002 {secret}", "tenant_id": "acme"}, self.config)
        # (70) 追踪只记录结构化安全元数据。
        trace = json.dumps({"events": result["trace_events"], "summary": result["trace_summary"]}, ensure_ascii=False)
        # (70) 不泄漏用户原始提问。
        self.assertNotIn(secret, trace)
        # (70) 每轮确实具有追踪事件，而非通过不记录任何内容绕过脱敏要求。
        self.assertTrue(result["trace_events"])

    # (70) 真实 Console 串起批准、同会话追问、新会话与拒绝。
    def test_console_main_supports_followup_new_thread_and_approval(self):
        # (70) 配置在内存构造，不调用 load_settings 读取环境文件。
        settings = Settings(llm_api_key="offline-test-key")
        # (70) 首会话取消、总结、追问，新会话取消后人工拒绝。
        model = ScriptedBudgetModel([response(calls=[tool_call("cancel_order", "console-first", {"order_id": "A1001"})]), response(), response(), response(calls=[tool_call("cancel_order", "console-other", {"order_id": "A1001"})])])
        # (70) 保留入口实际构造的图，执行后检查两份会话存档。
        graphs = []
        # (70) 构图仍调用真实实现，不用假 State 代替完整执行。
        def capture_graph(*args, **kwargs):
            # (70) 返回真实 LangGraph，便于 Console 正常执行审批。
            graph = diagnosis_agent.build_graph(*args, **kwargs)
            # (70) 当前 main 只构造一张共享图。
            graphs.append(graph)
            # (70) 不额外重写入口配置。
            return graph
        # (70) 所有外部依赖和交互都替换，不访问 API、数据库或真实 stdin。
        with patch.object(lesson70, "load_settings", return_value=settings), patch.object(lesson70, "CompatibleToolModel", return_value=model), patch.object(lesson70, "build_pipeline", return_value=self.pipeline), patch.object(lesson70, "build_graph", side_effect=capture_graph), patch("builtins.input", side_effect=["取消 A1001", "y", "只是模拟对吧", "/new", "取消 A1001", "n", "q"]), patch("builtins.print"):
            # (70) 直接运行当前正式入口的 main。
            lesson70.main()
        # (70) 只构造一次依赖和工作流，不为每个问题重新建图。
        self.assertEqual(len(graphs), 1)
        # (70) 新会话的首轮只看到自己的用户问题。
        self.assertEqual([item["content"] for item in model.requests[3]["messages"] if item["role"] == "user"], ["取消 A1001"])
        # (70) 原会话模拟记录不因切新会话被清空。
        first = graphs[0].get_state({"configurable": {"thread_id": lesson70.THREAD_ID}}).values
        # (70) 新会话拒绝后没有借用前一会话已批准记录。
        other = graphs[0].get_state({"configurable": {"thread_id": f"{lesson70.THREAD_ID}-2"}}).values
        # (70) 隔离业务状态与执行结束原因。
        self.assertEqual((first["simulated_cancellations"], other["simulated_cancellations"], other["stop_reason"]), (["A1001"], [], "approval_rejected"))

    # (70) 审批中模糊输入不能默认批准，只有明确决定才恢复。
    def test_console_approval_waits_for_explicit_decision(self):
        # (70) 真实执行到人工审批点。
        model, graph, paused, request = self.pause_cancel()
        # (70) 空白、切会话和模糊 yes 都不是本课批准格式。
        with patch("builtins.input", side_effect=["", "/new", "yes", "approve"]) as user_input, patch("builtins.print"), patch.object(graph, "invoke", wraps=graph.invoke) as invoke:
            # (70) 入口生成恢复值，测试不替它拼正确决定。
            result = lesson70.resume_approvals(graph, paused, self.config)
        # (70) 前三次无效输入不能调用图恢复。
        self.assertEqual((user_input.call_count, invoke.call_count), (4, 1))
        # (70) 审批完整绑定当前目标，不能只发字符串 approve。
        self.assertEqual(invoke.call_args.args[0].resume, {**request, "decision": "approve"})
        # (70) 恢复成功后仍按原模型流程总结。
        self.assertEqual(result["stop_reason"], "final_answer")

    # (70) 审批界面退出不提交任何恢复值，待审批任务保持未执行。
    def test_console_quit_does_not_resume_or_execute(self):
        # (70) 取消请求已经暂停，但还没有人工决定。
        model, graph, paused, request = self.pause_cancel()
        # (70) 退出只影响外层交互，不伪装成批准或拒绝。
        with patch("builtins.input", return_value="q"), patch("builtins.print"), patch.object(graph, "invoke", wraps=graph.invoke) as invoke:
            # (70) 实际调用入口 helper。
            result = lesson70.resume_approvals(graph, paused, self.config)
        # (70) 返回 None 通知 main 退出。
        self.assertIsNone(result)
        # (70) q 不触发图内部恢复。
        invoke.assert_not_called()
        # (70) 当前内存中仍保留未执行的审批任务。
        self.assertEqual((graph.get_state(self.config).next, len(model.requests)), (("approval",), 1))

    # (70) Console Tracing 不打印原始问题、完整 Tool 结果或密钥。
    def test_console_trace_does_not_print_raw_tool_or_question(self):
        # (70) 内存配置的密钥只用于替身，不得进入日志。
        settings = Settings(llm_api_key="private-config-secret-70")
        # (70) 模型选择一个普通业务 Tool，再直接给非敏感总结。
        model = ScriptedBudgetModel([response(calls=[tool_call("get_refund", "console-private", {"order_id": "A1002"})]), response()])
        # (70) 原始结果可包含业务敏感值，但日志只能记录元数据。
        private_result = tool_result(True, data={"private": "private-tool-secret-70"})
        # (70) 执行完整入口，只替换实际依赖和用户输入。
        with patch.object(lesson70, "load_settings", return_value=settings), patch.object(lesson70, "CompatibleToolModel", return_value=model), patch.object(lesson70, "build_pipeline", return_value=self.pipeline), patch.object(diagnosis_agent, "dispatch_tool", return_value=private_result), patch("builtins.input", side_effect=["查询 A1002 private-question-secret-70", "q"]), patch("builtins.print") as printed:
            # (70) 不单测打印 helper，检查实际 main 的输出路径。
            lesson70.main()
        # (70) 所有 Console 输出都转成文本做泄漏检查。
        text = "\n".join(" ".join(str(value) for value in call.args) for call in printed.call_args_list)
        # (70) 不以关闭全部追踪来掩盖泄漏。
        self.assertIn("Tracing 汇总", text)
        # (70) 问题、结果和配置密钥都不自动打印。
        for secret in ("private-config-secret-70", "private-tool-secret-70", "private-question-secret-70"):
            # (70) 每种秘密分别定位，便于排查。
            self.assertNotIn(secret, text)

    # (70) 未处理程序异常也只提示安全说明，不回显原始异常文本。
    def test_console_unhandled_error_does_not_leak_details(self):
        # (70) 配置完全在内存构造。
        settings = Settings(llm_api_key="offline-test-key")
        # (70) 模拟发生在图边界外的未知错误。
        graph = Mock()
        # (70) 原异常故意带一个可识别的秘密。
        graph.invoke.side_effect = RuntimeError("private-unhandled-secret-70")
        # (70) 完整入口必须安全退出，不能继续提交新问题覆盖任务。
        with patch.object(lesson70, "load_settings", return_value=settings), patch.object(lesson70, "CompatibleToolModel"), patch.object(lesson70, "build_pipeline", return_value=self.pipeline), patch.object(lesson70, "build_graph", return_value=graph), patch("builtins.input", return_value="查 A1002") as user_input, patch("builtins.print") as printed:
            # (70) 未知异常走 main 的最终保护边界。
            lesson70.main()
        # (70) 一次失败后立即退出，不陷入反复调用。
        self.assertEqual((graph.invoke.call_count, user_input.call_count), (1, 1))
        # (70) Console 不能打印异常原文或连接详情。
        text = "\n".join(" ".join(str(value) for value in call.args) for call in printed.call_args_list)
        # (70) 安全提示保留，但秘密不泄漏。
        self.assertNotIn("private-unhandled-secret-70", text)


    # (70) 同批重复取消也消耗 Tool 处理额度，不能依靠去重结果无限绕过预算。
    def test_duplicate_cancel_requests_cannot_bypass_tool_limit(self):
        # (70) 让同一模型响应包含三个不同调用 ID、相同订单的取消请求。
        calls = [tool_call("cancel_order", f"duplicate-{index}", {"order_id": "A1001"}) for index in range(3)]
        # (70) 两次额度只允许首次模拟与一次防重复处理。
        with patch.object(diagnosis_agent, "simulate_cancel_order", wraps=diagnosis_agent.simulate_cancel_order) as simulate:
            # (70) 使用真实中断，只确认第一个实际待审批请求。
            model, graph, paused, request = self.pause_cancel(limits={"max_tool_calls": 2}, calls=calls)
            # (70) 第三个请求应进入预算失败，而不是继续处理大量重复调用。
            result = graph.invoke(Command(resume={**request, "decision": "approve"}), self.config)
        # (70) 模拟只执行一次，后续重复处理也不能绕过次数上限。
        self.assertEqual((simulate.call_count, result["tool_calls"], result["stop_reason"], len(model.requests)), (1, 2, "tool_limit", 1))
        # (70) 全部请求仍有配对结果，未执行不冒充空数据。
        self.assert_tool_pairs(result, ["duplicate-0", "duplicate-1", "duplicate-2"])
        # (70) 第二条明确是防重复结果，第三条明确未执行。
        self.assertTrue(result["tool_results"][1]["result"]["data"]["duplicate"])
        # (70) 最后的预算拦截不产生额外敏感动作。
        self.assertFalse(result["tool_results"][2]["result"]["success"])


# (70) 允许独立运行该文件，不启动正式入口。
if __name__ == "__main__":
    # (70) 所有测试均为离线，不读取密钥或连接数据库。
    unittest.main()
