import hashlib
import json
import math
import re
import time
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from openai import APIConnectionError, APIStatusError, APITimeoutError


# (69) 只分类错误类型，不把可能含请求、凭证的异常文字写进日志。
def error_kind(error: Exception) -> str:
    # (69) SDK 的超时也属于连接异常，先判断超时才能正确分类。
    if isinstance(error, (TimeoutError, APITimeoutError)):
        # (69) 稳定分类便于统计，不依赖异常原文。
        return "timeout"
    # (69) 本地与模型 SDK 的连接异常使用同一类别。
    if isinstance(error, (ConnectionError, APIConnectionError)):
        # (69) 不记录连接地址或请求头。
        return "connection"
    # (69) HTTP 只保留状态码类别，不保存响应正文。
    if isinstance(error, APIStatusError):
        # (69) 服务端错误和客户端错误分开统计。
        return "http_5xx" if error.status_code >= 500 else "http_4xx"
    # (69) 参数、结构与 JSON 校验错误归入校验失败。
    if isinstance(error, (ValueError, TypeError, KeyError)):
        # (69) 不输出错误参数本身。
        return "validation"
    # (69) 未列入白名单的错误统一分类，不猜测可重试性。
    return "system"


# (69) 参数日志只保留白名单字段，未知字段连字段名也不输出。
def safe_arguments(name: str, arguments: str) -> dict:
    # (69) 工具名称由调用方白名单限制，此处只识别本课实际使用的参数。
    allowed = {"question"} if name == "ask_knowledge_base" else {"order_id"} if name in {"get_order", "get_payment", "get_refund", "cancel_order"} else set()
    # (69) 非字符串参数不能交给 JSON 解析，也不能原样输出。
    if not isinstance(arguments, str):
        # (69) 用固定提示替代可能敏感的原值。
        return {"status": "invalid", "fields": []}
    # (69) JSON 解析失败时只报告无效，不输出原字符串。
    try:
        # (69) 仅在内存中检查工具参数。
        payload = json.loads(arguments)
    # (69) 不让原始 JSON 内容进入异常日志。
    except (ValueError, TypeError, RecursionError):
        # (69) 错误摘要不包含解析器的原始错误文字。
        return {"status": "invalid", "fields": []}
    # (69) 参数必须是字典，数组和标量都不作为合法摘要。
    if not isinstance(payload, dict):
        # (69) 不显示不合法参数中的内容。
        return {"status": "invalid", "fields": []}
    # (69) 只列出允许的字段，避免秘密藏在未知键名中。
    fields = sorted(allowed.intersection(payload))
    # (69) 所有摘要都用固定结构表达是否成功解析。
    result = {"status": "valid", "fields": fields}
    # (69) 问题属于自由文本，始终完整遮盖。
    if "question" in fields:
        # (69) 不截取问题前缀，防止前缀包含姓名或密钥。
        result["question"] = "[REDACTED]"
    # (69) 订单号仅在严格演示格式下保留少量定位信息。
    if "order_id" in fields:
        # (69) 读取值不代表信任其内容。
        order_id = payload["order_id"]
        # (69) 带空格、标点、长文本或非字符串的内容全部遮盖。
        if isinstance(order_id, str) and re.fullmatch(r"[A-Z][0-9]{4,12}", order_id):
            # (69) 例如 A1002 只显示 A***02，仍不记录完整订单号。
            result["order_id"] = order_id[0] + "***" + order_id[-2:]
        # (69) 非标准订单号不能当作可信日志字段。
        else:
            # (69) 固定标记不泄露原始长度或内容。
            result["order_id"] = "[REDACTED]"
    # (69) 不返回原始参数、未知字段或异常内容。
    return result


# (69) 结构化事件仅保存在当前 State，不落盘、不接外部平台。
class TraceRecorder:
    # (69) 只持有本轮 State 与时钟，不创建跨会话的共享事件列表。
    def __init__(self, state: dict, clock=time.monotonic):
        # (69) 由节点负责复制列表，记录器只操作调用方提供的当前列表。
        self.state = state
        # (69) 单调时钟不受系统时间调整影响，也便于离线测试。
        self.clock = clock

    # (69) 受限标识只允许常见技术字符，不能夹带自由文本。
    def _identifier(self, value, fallback: str = "") -> str:
        # (69) 超长、带空格或特殊字符的标识统一遮盖。
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:#-]{1,128}", value):
            # (69) 空值使用调用方指定的固定默认值。
            return fallback if not value else "[REDACTED]"
        # (69) 调用方只传入受信任的技术标识和固定名称。
        return value

    # (69) 金额只接受有限、非负的数值，不保存任意金额文字。
    def _money(self, value) -> str | None:
        # (69) 没有费用就是未知，不冒充零费用。
        if value is None or isinstance(value, bool):
            # (69) 缺失金额保留为 None。
            return None
        # (69) Decimal 保证汇总费用不因浮点累加发生漂移。
        try:
            # (69) 字符串、整数与 Decimal 都经过统一解析。
            amount = Decimal(str(value))
        # (69) 不把非法金额原文写进错误记录。
        except (InvalidOperation, ValueError, TypeError):
            # (69) 无效金额不能进入成本汇总。
            return None
        # (69) 无穷、NaN 与负金额不是有效执行成本。
        if not amount.is_finite() or amount < 0:
            # (69) 保留未知而非误记为零。
            return None
        # (69) State 中保存 JSON 可序列化的精确金额字符串。
        return str(amount)

    # (69) 开始一次节点、工具或模型调用，并返回当前跨度信息。
    def start(self, kind: str, name: str, parent_id: str = "", attempt: int = 0, retry: int = 0, tool_call_id: str = "") -> dict:
        # (69) 跨度种类固定，不允许把任意用户文字用作日志类别。
        if kind not in {"node", "tool", "llm", "approval", "run"}:
            # (69) 配置错误直接提示固定文字。
            raise ValueError("不支持的追踪种类。")
        # (69) 首次实际记录时才创建当前 State 的事件列表。
        events = self.state.setdefault("trace_events", [])
        # (69) 使用随机标识区分跨度，不依赖事件列表是否被复制。
        span_id = uuid4().hex
        # (69) 名称来自程序白名单，额外限制字符与长度。
        safe_name = self._identifier(name, "unknown")
        # (69) 父跨度必须来自当前执行，不能跨 run 关联旧事件。
        parent = next((event for event in reversed(events) if event.get("phase") == "start" and event.get("span_id") == parent_id and event.get("run_id") == self._identifier(self.state.get("run_id")) and event.get("thread_id") == self._identifier(self.state.get("thread_id"))), {})
        # (69) 工具调用 ID 可能来自模型自由输出，统一短哈希后才能记录。
        call_id = "call#" + hashlib.sha256(tool_call_id.encode("utf-8")).hexdigest()[:12] if isinstance(tool_call_id, str) and tool_call_id else ""
        # (69) 仅构造固定字段，不复制 State 中的消息、结果或配置。
        span = {
            "thread_id": self._identifier(self.state.get("thread_id")),
            "run_id": self._identifier(self.state.get("run_id")),
            "span_id": span_id,
            "parent_id": parent.get("span_id", ""),
            "kind": kind,
            "name": safe_name,
            "node": safe_name if kind == "node" else parent.get("node", ""),
            "tool": safe_name if kind == "tool" else parent.get("tool", ""),
            "attempt": attempt if type(attempt) is int and attempt >= 0 else 0,
            "retry": retry if type(retry) is int and retry >= 0 else 0,
            "tool_call_id": call_id or parent.get("tool_call_id", ""),
            "started_at": self.clock(),
        }
        # (69) 开始事件使用独立字典，后续结束不会修改历史事件。
        events.append({**span, "phase": "start", "status": "running"})
        # (69) 调用方把跨度传给 finish，完成同一次调用。
        return span

    # (69) 结束跨度时只保留安全字段、耗时、用量和费用。
    def finish(self, span: dict, status: str, error=None, usage=None, reserved_input: int = 0, reserved_output: int = 0, estimated_cost=None) -> None:
        # (69) 只允许复制记录器定义的字段，不保存调用方附带的任意内容。
        fields = ("thread_id", "run_id", "span_id", "parent_id", "kind", "name", "node", "tool", "attempt", "retry", "tool_call_id", "started_at")
        # (69) span 由 start 返回，结束事件保持同一关联信息。
        event = {name: span[name] for name in fields}
        # (69) 使用单调时间差；负值归零，避免测试时钟回拨造成负耗时。
        duration = self.clock() - span["started_at"]
        # (69) 非有限时间不能进入汇总结果。
        duration = max(0.0, duration) if math.isfinite(duration) else None
        # (69) 错误只保留类别，绝不记录 str(error) 或 traceback。
        event.update({"phase": "end", "status": self._identifier(status, "unknown"), "duration_seconds": duration, "error_kind": error_kind(error) if error is not None else ""})
        # (69) 只有模型调用记录 Token，父节点和工具不能重复记账。
        if event["kind"] == "llm":
            # (69) 两个基础用量必须同时为非负整数，bool 也不能冒充 Token 数。
            known = isinstance(usage, dict) and all(type(usage.get(name)) is int and usage[name] >= 0 for name in ("prompt_tokens", "completion_tokens"))
            # (69) 预留值用于预算控制，不当成接口实际返回的 Token。
            event.update({"usage_source": "api_usage" if known else "unknown", "input_tokens": usage["prompt_tokens"] if known else None, "output_tokens": usage["completion_tokens"] if known else None, "uncategorized_tokens": None, "total_tokens": None, "reserved_input_tokens": reserved_input if type(reserved_input) is int and reserved_input >= 0 else 0, "reserved_output_tokens": reserved_output if type(reserved_output) is int and reserved_output >= 0 else 0})
            # (69) total_tokens 可能还包含未分类用量，不能漏计或重复计算 reasoning 明细。
            if known:
                # (69) 输入与输出之和是最小可信总量。
                total = event["input_tokens"] + event["output_tokens"]
                # (69) 服务端总量合法且更大时，把差额单独保存。
                extra = usage["total_tokens"] - total if type(usage.get("total_tokens")) is int and usage["total_tokens"] > total else 0
                # (69) 原始输入输出不变，未分类差额仍计入总量。
                event.update({"uncategorized_tokens": extra, "total_tokens": total + extra})
            # (69) 同一金额对预算可能含预留，对实际费用必须确认有 API usage。
            cost = self._money(estimated_cost)
            # (69) 明确区分预算扣账金额与依据已知用量估算的费用。
            event.update({"budget_estimated_cost": cost, "estimated_cost": cost if known else None})
        # (69) 每次结束追加一条新事件，不覆盖已有开始事件。
        self.state.setdefault("trace_events", []).append(event)

    # (69) 只聚合当前轮结束事件，父子耗时分组展示但不能相加冒充总耗时。
    def summary(self) -> dict:
        # (69) 限制同一 State 中残留的其他会话和其他轮次事件进入汇总。
        events = [event for event in self.state.get("trace_events", []) if event.get("phase") == "end" and event.get("thread_id") == self._identifier(self.state.get("thread_id")) and event.get("run_id") == self._identifier(self.state.get("run_id"))]
        # (69) 模型结束事件才是用量与费用的唯一统计来源。
        calls = [event for event in events if event.get("kind") == "llm"]
        # (69) 分开统计已知用量，未知用量不默认为零。
        known = [event for event in calls if event.get("usage_source") == "api_usage"]
        # (69) 已知金额可以汇总，但若存在未知调用，就不能声称费用完整。
        known_costs = [event["estimated_cost"] for event in calls if event.get("estimated_cost") is not None]
        # (69) 预算金额可能包含保守预留，单独汇总以免误认为实际消耗。
        budget_costs = [event["budget_estimated_cost"] for event in calls if event.get("budget_estimated_cost") is not None]
        # (69) 金额累加始终使用 Decimal，不使用 float。
        cost_sum = str(sum((Decimal(cost) for cost in known_costs), Decimal("0")))
        # (69) 有任意缺失金额时，整个费用只能标记为部分已知。
        partial = len(known_costs) != len(calls)
        # (69) 币种只接受常用三位代号，不回显任意配置文字。
        currency = self.state.get("limits", {}).get("currency", "UNKNOWN")
        # (69) 费用单位不做汇率换算，也不自动查询模型价格。
        currency = currency if isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency) else "UNKNOWN"
        # (69) 创建固定摘要结构，Console 可以直接展示这些统计字段。
        result = {"thread_id": self._identifier(self.state.get("thread_id")), "run_id": self._identifier(self.state.get("run_id")), "currency": currency, "llm_attempts": len(calls), "known_input_tokens": sum(event["input_tokens"] for event in known), "known_output_tokens": sum(event["output_tokens"] for event in known), "known_uncategorized_tokens": sum(event["uncategorized_tokens"] for event in known), "known_total_tokens": sum(event["total_tokens"] for event in known), "unknown_usage_calls": len(calls) - len(known), "estimated_cost": None if partial else cost_sum, "known_estimated_cost": cost_sum, "cost_is_partial": partial, "budget_estimated_cost": str(sum((Decimal(cost) for cost in budget_costs), Decimal("0"))), "unknown_budget_cost_calls": len(calls) - len(budget_costs), "node_seconds": {}, "tool_seconds": {}}
        # (69) 节点与工具各自按名称合计，不把嵌套时间重复加总。
        for kind, target in (("node", "node_seconds"), ("tool", "tool_seconds")):
            # (69) 开始事件、模型事件和缺失时间都不参与此处求和。
            for event in events:
                # (69) 同一工具多次调用会累计到同一名称。
                if event.get("kind") == kind and type(event.get("duration_seconds")) in (int, float):
                    # (69) 输出仍保持简单字典，便于 Debug 查看。
                    result[target][event["name"]] = result[target].get(event["name"], 0.0) + event["duration_seconds"]
        # (69) 摘要不返回参数、模型内容、工具结果或异常原文。
        return result
