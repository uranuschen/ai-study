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
        if error.status_code >= 500:
            # (69) 5xx 表示服务端错误。
            return "http_5xx"
        # (69) 其他 HTTP 错误归入客户端错误。
        return "http_4xx"
    # (69) 参数、结构与 JSON 校验错误归入校验失败。
    if isinstance(error, (ValueError, TypeError, KeyError)):
        # (69) 不输出错误参数本身。
        return "validation"
    # (69) 未列入白名单的错误统一分类，不猜测可重试性。
    return "system"


# (69) 参数日志只保留白名单字段，未知字段连字段名也不输出。
def safe_arguments(name: str, arguments: str) -> dict:
    # (69) 工具名称由调用方白名单限制，此处只识别本课实际使用的参数。
    if name == "ask_knowledge_base":
        # (69) 知识库工具只接受问题字段。
        allowed = {"question"}
    # (69) 订单类工具只接受订单号字段。
    elif name in {"get_order", "get_payment", "get_refund", "cancel_order"}:
        # (69) 不把其他业务字段写入日志。
        allowed = {"order_id"}
    # (69) 未知工具没有可记录的参数。
    else:
        # (69) 创建空集合，表示不允许任何字段。
        allowed = set()
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
    fields = []
    # (69) 逐个检查白名单字段是否出现在参数中。
    for field in allowed:
        # (69) 参数中确实有这个字段时才记录字段名。
        if field in payload:
            # (69) 这里只添加字段名，不添加原始字段值。
            fields.append(field)
    # (69) 固定字段顺序，便于对照日志和测试结果。
    fields.sort()
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
            if not value:
                # (69) 例如没有父跨度时，保留默认空字符串。
                return fallback
            # (69) 非空但格式不合法的内容全部遮盖。
            return "[REDACTED]"
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
    def start(
        self,
        kind: str,
        name: str,
        parent_id: str = "",
        attempt: int = 0,
        retry: int = 0,
        tool_call_id: str = "",
    ) -> dict:
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
        # (69) 先取出本轮和本会话的安全编号，后面逐项比较。
        run_id = self._identifier(self.state.get("run_id"))
        # (69) 父事件必须属于同一个会话。
        thread_id = self._identifier(self.state.get("thread_id"))
        # (69) 默认没有父事件，找不到时继续使用空字典。
        parent = {}
        # (69) 从最新事件往前找，找到第一个符合条件的事件就停止。
        for event in reversed(events):
            # (69) 父事件必须是开始事件，结束事件直接跳过。
            if event.get("phase") != "start":
                # (69) continue 表示继续检查上一条事件。
                continue
            # (69) 跨度编号必须等于调用方传入的父跨度编号。
            if event.get("span_id") != parent_id:
                # (69) 不是要找的父跨度就跳过。
                continue
            # (69) 其他轮次的事件不能作为本轮的父事件。
            if event.get("run_id") != run_id:
                # (69) 跳过旧问题留下的事件。
                continue
            # (69) 其他会话的事件也不能作为父事件。
            if event.get("thread_id") != thread_id:
                # (69) 跳过其他会话的事件。
                continue
            # (69) 四项检查都通过，保存找到的父事件。
            parent = event
            # (69) break 表示已经找到，不再继续往前搜索。
            break
        # (69) 默认没有工具调用编号。
        call_id = ""
        # (69) 工具调用 ID 可能来自模型自由输出，只接受非空字符串。
        if isinstance(tool_call_id, str) and tool_call_id:
            # (69) 先把字符串转换成哈希函数需要的字节。
            call_bytes = tool_call_id.encode("utf-8")
            # (69) 哈希摘要用于定位调用，不回显原始调用 ID。
            call_hash = hashlib.sha256(call_bytes).hexdigest()
            # (69) 只保留前 12 位摘要，并加上固定前缀。
            call_id = "call#" + call_hash[:12]
        # (69) 子步骤没有新的调用编号时，沿用父事件的安全编号。
        if not call_id:
            # (69) 没有父事件时得到空字符串。
            call_id = parent.get("tool_call_id", "")
        # (69) 默认沿用父事件所属的节点。
        node_name = parent.get("node", "")
        # (69) 当前事件本身就是节点时，使用当前节点名。
        if kind == "node":
            # (69) 子 Tool 和模型可据此知道自己属于哪个节点。
            node_name = safe_name
        # (69) 默认沿用父事件所属的工具。
        tool_name = parent.get("tool", "")
        # (69) 当前事件本身就是工具时，使用当前工具名。
        if kind == "tool":
            # (69) 工具内部的模型调用可继承这个名称。
            tool_name = safe_name
        # (69) 不合法的尝试次数统一记为零。
        safe_attempt = 0
        # (69) bool 不能冒充整数次数。
        if type(attempt) is int and attempt >= 0:
            # (69) 保存合法的非负次数。
            safe_attempt = attempt
        # (69) 不合法的重试次数也统一记为零。
        safe_retry = 0
        # (69) 只接受非负整数重试次数。
        if type(retry) is int and retry >= 0:
            # (69) 保存合法的重试次数。
            safe_retry = retry
        # (69) 仅构造固定字段，不复制 State 中的消息、结果或配置。
        span = {
            "thread_id": thread_id,
            "run_id": run_id,
            "span_id": span_id,
            "parent_id": parent.get("span_id", ""),
            "kind": kind,
            "name": safe_name,
            "node": node_name,
            "tool": tool_name,
            "attempt": safe_attempt,
            "retry": safe_retry,
            "tool_call_id": call_id,
            "started_at": self.clock(),
        }
        # (69) 开始事件使用独立字典，后续结束不会修改历史事件。
        event = dict(span)
        # (69) 标明这是开始事件。
        event["phase"] = "start"
        # (69) 刚开始的步骤处于运行中。
        event["status"] = "running"
        # (69) 将新事件加入本轮列表。
        events.append(event)
        # (69) 调用方把跨度传给 finish，完成同一次调用。
        return span

    # (69) 结束跨度时只保留安全字段、耗时、用量和费用。
    def finish(
        self,
        span: dict,
        status: str,
        error=None,
        usage=None,
        reserved_input: int = 0,
        reserved_output: int = 0,
        estimated_cost=None,
    ) -> None:
        # (69) 只允许复制记录器定义的字段，不保存调用方附带的任意内容。
        fields = (
            "thread_id",
            "run_id",
            "span_id",
            "parent_id",
            "kind",
            "name",
            "node",
            "tool",
            "attempt",
            "retry",
            "tool_call_id",
            "started_at",
        )
        # (69) 新建结束事件，不修改原来的开始记录。
        event = {}
        # (69) 逐个复制允许记录的字段。
        for name in fields:
            # (69) span 由 start 返回，结束事件保持同一关联信息。
            event[name] = span[name]
        # (69) 使用单调时间差；负值归零，避免测试时钟回拨造成负耗时。
        duration = self.clock() - span["started_at"]
        # (69) 非有限时间不能进入汇总结果。
        if not math.isfinite(duration):
            # (69) 无穷或 NaN 用未知表示。
            duration = None
        # (69) 零耗时与测试时钟回拨造成的负耗时统一记为 0.0。
        elif duration <= 0:
            # (69) 耗时最小为零秒。
            duration = 0.0
        # (69) 标明当前事件是结束事件。
        event["phase"] = "end"
        # (69) 状态也经过安全字符检查。
        event["status"] = self._identifier(status, "unknown")
        # (69) 保存刚才算出的耗时。
        event["duration_seconds"] = duration
        # (69) 默认没有错误类别。
        event["error_kind"] = ""
        # (69) 有异常时只保存类别，不保存异常正文。
        if error is not None:
            # (69) 不调用 str(error)，避免暴露请求或凭证。
            event["error_kind"] = error_kind(error)
        # (69) 只有模型调用记录 Token，父节点和工具不能重复记账。
        if event["kind"] == "llm":
            # (69) 默认用量未知，只有两个基础字段都合法时才算已知。
            known = False
            # (69) 先确认 usage 是字典，才能读取其中的字段。
            if isinstance(usage, dict):
                # (69) 接下来逐个检查输入与输出 Token。
                known = True
                # (69) 两个字段都必须是非负整数。
                for name in ("prompt_tokens", "completion_tokens"):
                    # (69) 缺失字段得到 None，也会被下面的类型检查拒绝。
                    token_count = usage.get(name)
                    # (69) bool 不能冒充 Token 数。
                    if type(token_count) is not int:
                        # (69) 任意一个字段不合法，整次用量就是未知。
                        known = False
                        # (69) 已经确定无效，不必再检查另一个字段。
                        break
                    # (69) Token 数也不能是负数。
                    if token_count < 0:
                        # (69) 负数用量不能参与统计。
                        known = False
                        # (69) 停止本次字段检查。
                        break
            # (69) 先填写未知用量的默认记录。
            event.update({
                "usage_source": "unknown",
                "input_tokens": None,
                "output_tokens": None,
                "uncategorized_tokens": None,
                "total_tokens": None,
                "reserved_input_tokens": 0,
                "reserved_output_tokens": 0,
            })
            # (69) 输入预留只接受非负整数。
            if type(reserved_input) is int and reserved_input >= 0:
                # (69) 预留只用于预算，不冒充接口实测用量。
                event["reserved_input_tokens"] = reserved_input
            # (69) 输出预留也只接受非负整数。
            if type(reserved_output) is int and reserved_output >= 0:
                # (69) 单独保存输出预留。
                event["reserved_output_tokens"] = reserved_output
            # (69) total_tokens 可能还包含未分类用量，不能漏计或重复计算 reasoning 明细。
            if known:
                # (69) 两个基础字段都有效，标明用量来自接口。
                event["usage_source"] = "api_usage"
                # (69) 输入 Token 不和其他明细重复相加。
                event["input_tokens"] = usage["prompt_tokens"]
                # (69) 输出 Token 单独保存。
                event["output_tokens"] = usage["completion_tokens"]
                # (69) 输入与输出之和是最小可信总量。
                total = event["input_tokens"] + event["output_tokens"]
                # (69) 默认没有额外的未分类用量。
                extra = 0
                # (69) 读取服务端报告的总 Token 数。
                reported_total = usage.get("total_tokens")
                # (69) 只接受整数，且只补上大于输入输出之和的差额。
                if type(reported_total) is int and reported_total > total:
                    # (69) 差额单独保存，不能再加一遍整个服务端总量。
                    extra = reported_total - total
                # (69) 原始输入输出不变，未分类差额仍计入总量。
                event["uncategorized_tokens"] = extra
                # (69) 总量等于输入、输出与额外差额之和。
                event["total_tokens"] = total + extra
            # (69) 同一金额对预算可能含预留，对实际费用必须确认有 API usage。
            cost = self._money(estimated_cost)
            # (69) 明确区分预算扣账金额与依据已知用量估算的费用。
            event["budget_estimated_cost"] = cost
            # (69) 用量未知时，实际费用估算也标为未知。
            event["estimated_cost"] = None
            # (69) 只有用量已知时，才能把这笔金额计入已知费用。
            if known:
                # (69) 这里只存一次金额，汇总时不再向父节点重复记费。
                event["estimated_cost"] = cost
        # (69) 每次结束追加一条新事件，不覆盖已有开始事件。
        events = self.state.setdefault("trace_events", [])
        # (69) 将完成记录加入当前事件列表。
        events.append(event)

    # (69) 只聚合当前轮结束事件，父子耗时分组展示但不能相加冒充总耗时。
    def summary(self) -> dict:
        # (69) 先取出当前会话的安全编号。
        thread_id = self._identifier(self.state.get("thread_id"))
        # (69) 再取出当前问题的安全编号。
        run_id = self._identifier(self.state.get("run_id"))
        # (69) 先准备空列表，只收集属于本轮的完成事件。
        events = []
        # (69) 限制同一 State 中残留的其他会话和其他轮次事件进入汇总。
        for event in self.state.get("trace_events", []):
            # (69) 开始事件不参与汇总。
            if event.get("phase") != "end":
                # (69) 继续检查下一条事件。
                continue
            # (69) 其他会话的事件不参与本次统计。
            if event.get("thread_id") != thread_id:
                # (69) 保持会话之间的统计隔离。
                continue
            # (69) 同会话中的其他问题也不参与统计。
            if event.get("run_id") != run_id:
                # (69) 保持每一轮问题的成本独立。
                continue
            # (69) 三项检查都通过，收集当前完成事件。
            events.append(event)
        # (69) 模型尝试次数从零开始累计。
        llm_attempts = 0
        # (69) 单独统计有合法接口用量的模型调用数。
        known_usage_calls = 0
        # (69) 输入 Token 单独累计。
        input_tokens = 0
        # (69) 输出 Token 单独累计。
        output_tokens = 0
        # (69) 未分类 Token 单独累计。
        uncategorized_tokens = 0
        # (69) 这里只累计已知的总 Token，未知用量不当成零用量。
        total_tokens = 0
        # (69) 记录有已知费用的调用数，用于判断费用是否完整。
        known_cost_calls = 0
        # (69) 金额用 Decimal 累加，避免浮点误差。
        cost_sum = Decimal("0")
        # (69) 记录有预算金额的调用数。
        budget_cost_calls = 0
        # (69) 预算金额可能含预留，和已知费用分开累计。
        budget_cost_sum = Decimal("0")
        # (69) 按顺序检查每条本轮完成事件。
        for event in events:
            # (69) 只有实际模型调用参与 Token 和费用统计。
            if event.get("kind") != "llm":
                # (69) 跳过父节点和 Tool，避免重复记账。
                continue
            # (69) 失败和重试的模型调用也各算一次尝试。
            llm_attempts += 1
            # (69) 只有接口用量已知时，才累计实测 Token。
            if event.get("usage_source") == "api_usage":
                # (69) 这次调用的基础用量有效。
                known_usage_calls += 1
                # (69) 累计输入 Token。
                input_tokens += event["input_tokens"]
                # (69) 累计输出 Token。
                output_tokens += event["output_tokens"]
                # (69) 累计服务端报告的额外差额。
                uncategorized_tokens += event["uncategorized_tokens"]
                # (69) 总量已包含差额，不能再次添加明细。
                total_tokens += event["total_tokens"]
            # (69) 读取这次调用的已知费用估算。
            cost = event.get("estimated_cost")
            # (69) 未知金额不作为零金额参与已知费用统计。
            if cost is not None:
                # (69) 当前调用有已知费用。
                known_cost_calls += 1
                # (69) 把金额字符串转换成 Decimal 后累加。
                cost_sum += Decimal(cost)
            # (69) 读取可能包含保守预留的预算金额。
            budget_cost = event.get("budget_estimated_cost")
            # (69) 没有预算金额时，保留缺失状态。
            if budget_cost is not None:
                # (69) 当前调用有预算记账金额。
                budget_cost_calls += 1
                # (69) 预算金额单独求和。
                budget_cost_sum += Decimal(budget_cost)
        # (69) 有任意缺失金额时，整个费用只能标记为部分已知。
        partial = known_cost_calls != llm_attempts
        # (69) 币种只接受常用三位代号，不回显任意配置文字。
        currency = self.state.get("limits", {}).get("currency", "UNKNOWN")
        # (69) 费用单位不做汇率换算，也不自动查询模型价格。
        if not isinstance(currency, str):
            # (69) 非字符串不能作为币种。
            currency = "UNKNOWN"
        # (69) 字符串也必须符合三位大写字母格式。
        elif not re.fullmatch(r"[A-Z]{3}", currency):
            # (69) 不回显任意币种文字。
            currency = "UNKNOWN"
        # (69) 默认总费用未知。
        estimated_cost = None
        # (69) 每次模型调用的费用都已知时，总费用才完整。
        if not partial:
            # (69) State 中金额统一保存为字符串。
            estimated_cost = str(cost_sum)
        # (69) 创建固定摘要结构，Console 可以直接展示这些统计字段。
        result = {
            "thread_id": thread_id,
            "run_id": run_id,
            "currency": currency,
            "llm_attempts": llm_attempts,
            "known_input_tokens": input_tokens,
            "known_output_tokens": output_tokens,
            "known_uncategorized_tokens": uncategorized_tokens,
            "known_total_tokens": total_tokens,
            "unknown_usage_calls": llm_attempts - known_usage_calls,
            "estimated_cost": estimated_cost,
            "known_estimated_cost": str(cost_sum),
            "cost_is_partial": partial,
            "budget_estimated_cost": str(budget_cost_sum),
            "unknown_budget_cost_calls": llm_attempts - budget_cost_calls,
            "node_seconds": {},
            "tool_seconds": {},
        }
        # (69) 节点与工具各自按名称累计耗时。
        for event in events:
            # (69) 先判断这条记录属于节点还是工具。
            kind = event.get("kind")
            # (69) 节点耗时写入节点统计字典。
            if kind == "node":
                # (69) 后面的累加会更新这个字典。
                seconds_by_name = result["node_seconds"]
            # (69) 工具耗时写入另一份字典。
            elif kind == "tool":
                # (69) 不把父节点时间与工具时间混在一起。
                seconds_by_name = result["tool_seconds"]
            # (69) 其他类型不参与按名称统计。
            else:
                # (69) 模型耗时等仍保留在原始事件中。
                continue
            # (69) 读取本次耗时。
            duration = event.get("duration_seconds")
            # (69) 未知耗时不能参与求和。
            if type(duration) not in (int, float):
                # (69) 跳过缺失或无效的耗时。
                continue
            # (69) 取出节点名或工具名。
            name = event["name"]
            # (69) 第一次出现这个名称时，已有耗时按零计算。
            previous_seconds = seconds_by_name.get(name, 0.0)
            # (69) 同一名称多次执行时，累计它们的耗时。
            seconds_by_name[name] = previous_seconds + duration
        # (69) 摘要不返回参数、模型内容、工具结果或异常原文。
        return result
