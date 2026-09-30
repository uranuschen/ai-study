# 导入 JSON，解析参数并序列化工具结果。
import json
# 导入数学函数，拒绝无穷大和 NaN 配置。
import math
# 导入随机数，为重试等待增加少量抖动。
import random
# 导入时间函数，使用单调时钟计算任务截止时间。
import time
# 导入 Decimal，避免费用累计使用浮点数。
from decimal import Decimal, InvalidOperation
# 导入 HTTP 日期解析，支持 Retry-After 的日期格式。
from email.utils import parsedate_to_datetime
# 导入路径类，业务数据仍为本地 JSON。
from pathlib import Path
# 导入 SDK 异常类型，不打印异常中的凭证或请求内容。
from openai import APIConnectionError, APIStatusError
# 导入 LangGraph 节点编排功能。
from langgraph.graph import END, START, StateGraph
# 复用前几课的三个只读 Tool 和统一返回结构。
from agent_learning.business.tools import DEFAULT_DATA_FILE, get_order, get_payment, get_refund, tool_result
# 复用上一课的消息约定和协议校验，不改动旧图。
from agent_learning.workflows.agent_loop import AgentState, SYSTEM_PROMPT, TOOL_SCHEMAS, prepare_node as prepare_messages, validate_model_message


# 默认预算仅用于教学；单价是演示值，不代表 DeepSeek 当前报价。
DEFAULT_LIMITS = {
    # 所有模型请求尝试都计数，包括失败和重试。
    "max_steps": 5,
    # 所有 Tool 分发尝试都计数，包括失败、拒绝和重试。
    "max_tool_calls": 6,
    # 每次模型决策或每条 Tool 请求最多额外重试两次。
    "max_retries": 2,
    # 图默认保留时间预算；学习入口会显式关闭，避免 Debug 暂停导致失败。
    "enable_timeouts": True,
    # 单次模型 HTTP 请求的客户端超时，单位为秒。
    "model_timeout": 30.0,
    # 同步本地 Tool 返回后检查是否超时，不使用后台线程。
    "tool_timeout": 2.0,
    # 整个任务的协作式截止时间，包含重试等待。
    "overall_timeout": 90.0,
    # 每次模型请求允许生成的最大 Token 数。
    "max_output_tokens": 1200,
    # 单次 invoke 的累计 Token 预算，含失败请求的保守预留。
    "max_total_tokens": 30000,
    # 费用预算与单价使用同一种币种，Decimal 从字符串创建。
    "max_cost": "0.50",
    # 每百万输入 Token 的演示单价；真实运行前按所选模型核对。
    "input_price_per_million": "10",
    # 每百万输出 Token 的演示单价；不假设缓存折扣。
    "output_price_per_million": "20",
    # Console 标注估算费用的币种，避免混用人民币和美元。
    "currency": "CNY",
    # 无 Retry-After 时，第一次重试的基础等待秒数。
    "retry_delay": 0.2,
    # 过长的服务端等待提示直接停止，不提前重试。
    "max_retry_delay": 10.0,
# 结束默认预算字典。
}


# State 仍是普通字典；在上一课字段上增加控制和记录字段。
class RecoveryState(AgentState):
    # 可信入口传入的执行预算，不由用户问题或模型决定。
    limits: dict
    # 单调时钟记录任务开始时刻。
    started_at: float
    # 开启超时时各节点检查截止时间，关闭时为 None。
    deadline: float | None
    # 本次结束时的总耗时，包括重试等待。
    elapsed_seconds: float
    # Tool 执行尝试的累计次数，不是返回记录条数。
    tool_calls: int
    # 实际发生的模型额外重试次数。
    model_retries: int
    # 实际发生的 Tool 额外重试次数。
    tool_retries: int
    # 成功请求用 usage 记账，未知用量使用保守预留。
    total_tokens: int
    # Decimal 累计结果以字符串保存，不把 Decimal 发给模型。
    estimated_cost: str
    # 保存每次模型尝试的用量来源和估算费用。
    usage_history: list
    # 保存尝试、失败、等待与跳过事件，不记录原始异常文本。
    events: list


# 方法功能：合并并检查可信入口的预算，构图错误在请求前暴露。
def make_limits(overrides=None) -> dict:
    # 未提供时使用默认字典，调用方配置不会被修改。
    overrides = {} if overrides is None else overrides
    # 配置必须是普通字典，且不能混入未知字段。
    if not isinstance(overrides, dict) or set(overrides) - set(DEFAULT_LIMITS):
        # 不用字段反射或自动猜测配置名。
        raise ValueError("预算必须是字典，且只能使用 DEFAULT_LIMITS 中的字段。")
    # 复制默认值，避免多次建图互相污染。
    limits = dict(DEFAULT_LIMITS)
    # 用入口提供的参数覆盖默认值。
    limits.update(overrides)
    # 时间开关必须是真正的布尔值，不接受字符串或整数。
    if type(limits["enable_timeouts"]) is not bool:
        # 避免字符串 False 被当成真值而意外启用超时。
        raise ValueError("enable_timeouts 必须是 True 或 False。")
    # 整数上限拒绝布尔值；Tool 次数和重试次数允许为零。
    for name in ("max_steps", "max_tool_calls", "max_retries", "max_output_tokens", "max_total_tokens"):
        # 只有禁用 Tool 和重试这两项允许零。
        minimum = 0 if name in ("max_tool_calls", "max_retries") else 1
        # 小数、负数和布尔值都不能作为调用次数。
        if type(limits[name]) is not int or limits[name] < minimum:
            # 明确指出需要修改哪项配置。
            raise ValueError(f"{name} 必须是大于等于 {minimum} 的整数。")
    # 时间参数必须是有限数值。
    for name in ("model_timeout", "tool_timeout", "overall_timeout", "retry_delay", "max_retry_delay"):
        # 重试等待允许为零，超时与最大等待必须大于零。
        minimum_ok = limits[name] >= 0 if name == "retry_delay" and type(limits[name]) in (int, float) else False
        # 显式拒绝字符串、布尔值、无穷大及非正超时。
        if type(limits[name]) not in (int, float) or not math.isfinite(limits[name]) or not (minimum_ok or limits[name] > 0):
            # 不在任务中途才发现无效超时。
            raise ValueError(f"{name} 必须是有效的秒数。")
    # 教学流程不安排超过一分钟的阻塞等待。
    if limits["max_retry_delay"] > 60:
        # 很长的等待应留给后续调度器处理。
        raise ValueError("max_retry_delay 不得超过 60 秒。")
    # 费用参数显式转换为 Decimal，拒绝 NaN 和无穷大。
    for name in ("max_cost", "input_price_per_million", "output_price_per_million"):
        # 错误的金额文本应在构图时就报错。
        try:
            # 不直接从浮点数构造 Decimal。
            value = Decimal(str(limits[name]))
        # 金额格式错误统一提示配置项。
        except InvalidOperation:
            # 不输出整个配置或任何凭证。
            raise ValueError(f"{name} 必须是有效金额。") from None
        # 单价允许为零，费用预算本身必须大于零。
        if not value.is_finite() or value < 0 or (name == "max_cost" and value == 0):
            # 本地免费模型可显式使用零单价。
            raise ValueError(f"{name} 金额范围不正确。")
        # State 用字符串保存精确金额。
        limits[name] = str(value)
    # 币种只做展示，不自动查询或转换汇率。
    if not isinstance(limits["currency"], str) or not limits["currency"].strip():
        # 防止预算单位含糊不清。
        raise ValueError("currency 必须是非空币种名称。")
    # 返回经过检查的新配置字典。
    return limits


# 方法功能：复制会追加的列表，节点不修改传入的 State。
def copy_state(state: RecoveryState) -> dict:
    # 普通字典复制保留未更新的字段。
    current = dict(state)
    # 本课只会追加这几个列表，不修改历史条目内部字段。
    for name in ("messages", "tool_results", "usage_history", "events"):
        # 每个列表单独复制，便于观察节点前后的 State。
        current[name] = list(state[name])
    # 返回本节点独立的更新字典。
    return current


# 方法功能：初始化消息、计数、任务截止时间和预算记录。
def prepare_node(state: RecoveryState, limits: dict, clock) -> dict:
    # 复用上一课输入校验与消息准备，不调用模型。
    current = prepare_messages(state, limits["max_steps"])
    # 记录单调时钟；系统时间调整不影响总超时。
    started_at = clock()
    # 关闭时间限制时不设置截止时间，但仍记录开始时刻用于显示耗时。
    deadline = started_at + limits["overall_timeout"] if limits["enable_timeouts"] else None
    # 追加本课的控制字段，覆盖输入里可能伪造的计数与预算。
    current.update({"limits": dict(limits), "started_at": started_at, "deadline": deadline, "elapsed_seconds": 0.0, "tool_calls": 0, "model_retries": 0, "tool_retries": 0, "total_tokens": 0, "estimated_cost": "0", "usage_history": [], "events": []})
    # 仍然返回普通字典，由图更新当前 State。
    return current


# 方法功能：根据 Token 数与入口单价计算估算费用，不代表服务端账单。
def estimate_cost(input_tokens: int, output_tokens: int, limits: dict) -> Decimal:
    # 输入和输出分别计费，忽略可能存在的缓存折扣。
    return (Decimal(input_tokens) * Decimal(limits["input_price_per_million"]) + Decimal(output_tokens) * Decimal(limits["output_price_per_million"])) / Decimal(1000000)


# 方法功能：请求前粗估输入大小，不下载 tokenizer，也不冒充精确 Token 数。
def estimate_input_tokens(messages: list) -> int:
    # 同时计入消息和工具 Schema，不能只计算用户问题。
    payload = json.dumps({"messages": messages, "tools": TOOL_SCHEMAS}, ensure_ascii=False)
    # UTF-8 字节数加协议余量作为保守预留，精确数量以 usage 为准。
    return len(payload.encode("utf-8")) + 1024


# 方法功能：记录一次请求的用量，未知用量也不能当作零费用。
def charge_usage(state: dict, usage, reserved_input: int, reserved_output: int) -> None:
    # 默认按本次请求的完整预留记账，适用于异常或缺失 usage。
    input_tokens, output_tokens, source = reserved_input, reserved_output, "estimated_reservation"
    # 只有完整且合法的 usage 才使用接口报告的数字。
    if isinstance(usage, dict) and all(type(usage.get(name)) is int and usage[name] >= 0 for name in ("prompt_tokens", "completion_tokens")):
        # 读取兼容 Chat Completions 的用量字段。
        input_tokens, output_tokens, source = usage["prompt_tokens"], usage["completion_tokens"], "api_usage"
        # total_tokens 大于两项之和时也不能漏记额外用量。
        if type(usage.get("total_tokens")) is int and usage["total_tokens"] > input_tokens + output_tokens:
            # 未分类部分按输入单价计入教学估算。
            input_tokens = usage["total_tokens"] - output_tokens
    # 根据当前入口单价计算本次估算费用。
    cost = estimate_cost(input_tokens, output_tokens, state["limits"])
    # 每次失败请求和重试都会累计，而不是只统计成功结果。
    state["total_tokens"] += input_tokens + output_tokens
    # 金额累计保持 Decimal 精度，写回时仍用字符串。
    state["estimated_cost"] = str(Decimal(state["estimated_cost"]) + cost)
    # 留存每次尝试的计数来源，帮助区分真实 usage 与未知用量。
    state["usage_history"].append({"attempt": state["model_steps"], "input_tokens": input_tokens, "output_tokens": output_tokens, "source": source, "estimated_cost": str(cost)})


# 方法功能：只把明确的临时异常列入重试白名单。
def is_temporary_error(error: Exception) -> bool:
    # 本地临时连接问题、客户端超时与 SDK 连接问题可以有限重试。
    if isinstance(error, (TimeoutError, ConnectionError, APIConnectionError)):
        # 本课工具全为只读，不对写操作沿用这个规则。
        return True
    # HTTP 错误还需要排除配额与账单问题。
    if isinstance(error, APIStatusError):
        # 这些错误需要修改账户或配置，不能靠重试恢复。
        if error.code in ("insufficient_quota", "billing_hard_limit_reached", "invalid_api_key"):
            # 即使 HTTP 状态为 429，也不自动重试。
            return False
        # 认证失败、权限错误和参数错误不在白名单中。
        return error.status_code in (408, 429, 500, 502, 503, 504)
    # 文件格式错误、未知异常和业务失败都不自动重试。
    return False


# 方法功能：计算等待时间，遵守服务端 Retry-After，不提前重试。
def retry_delay(error: Exception, retry_index: int, limits: dict) -> float:
    # 默认使用有上限的指数等待，并增加少量随机抖动。
    delay = min(limits["max_retry_delay"], limits["retry_delay"] * (2 ** min(retry_index, 10)) + random.uniform(0, 0.1))
    # 只有 HTTP 错误有服务端响应头。
    if isinstance(error, APIStatusError):
        # 只读取等待提示，不保存请求头和原始异常文本。
        hint = error.response.headers.get("retry-after")
        # 缺少提示时使用上面的默认等待。
        if hint:
            # 提示可能为秒数，也可能为 HTTP 日期。
            try:
                # 优先按秒数解析常见格式。
                server_delay = float(hint)
            # 秒数解析失败时再尝试日期。
            except ValueError:
                # 日期解析错误也不应破坏失败恢复。
                try:
                    # HTTP 日期使用系统时间，与任务单调时钟分开。
                    server_delay = parsedate_to_datetime(hint).timestamp() - time.time()
                # 无效格式退回有限的默认等待。
                except (ValueError, TypeError, OverflowError):
                    # 不输出原始响应头。
                    server_delay = 0
            # NaN 与无穷大不能进入 sleep。
            if math.isfinite(server_delay) and server_delay > 0:
                # 服务端要求等待更久时不能把提示截短。
                delay = max(delay, server_delay)
    # 超过最大等待的值由调用方拒绝，不提前发出请求。
    return delay


# 方法功能：设置终止原因，失败节点再生成用户可读的说明。
def stop(state: dict, reason: str) -> dict:
    # 结束原因由程序控制，不从模型回复中直接读取。
    state["stop_reason"] = reason
    # 返回当前节点的新 State，不丢失已取得的证据。
    return state


# 方法功能：仅在开启时间限制时检查截止时间，也可预先计入一次重试等待。
def overall_timeout_reached(state: dict, clock, delay: float = 0.0) -> bool:
    # and 会短路；关闭时不会拿 None 截止时间做比较。
    return state["limits"]["enable_timeouts"] and clock() + delay >= state["deadline"]


# 方法功能：开启时取得单次与剩余时间的较小值，关闭时返回 None。
def operation_timeout(state: dict, timeout_name: str, clock):
    # None 也会传给模型 SDK，明确关闭 HTTP 客户端超时。
    if not state["limits"]["enable_timeouts"]:
        # 断点暂停仍计入显示耗时，但不再影响调度。
        return None
    # 开启时每次操作都受整体截止时间约束。
    return min(state["limits"][timeout_name], state["deadline"] - clock())


# 方法功能：每次模型尝试之前检查步骤、总时间和请求预留预算。
def check_model_budget(state: dict, clock, reserved_input: int) -> str:
    # 开启总超时时优先检查，截止后不启动新的请求。
    if overall_timeout_reached(state, clock):
        # 即使尚有调用次数也必须停止。
        return "overall_timeout"
    # 每次实际请求尝试都消耗一步，包括额外重试。
    if state["model_steps"] >= state["max_steps"]:
        # 不为了总结再额外调用一次模型。
        return "max_steps"
    # 预留输入估算和本次最大输出，不只在请求后才检查。
    if state["total_tokens"] + reserved_input + state["limits"]["max_output_tokens"] > state["limits"]["max_total_tokens"]:
        # 预估不足以容纳下一次请求时提前结束。
        return "token_budget"
    # 费用同样在请求前预留。
    if Decimal(state["estimated_cost"]) + estimate_cost(reserved_input, state["limits"]["max_output_tokens"], state["limits"]) > Decimal(state["limits"]["max_cost"]):
        # 不把大于预算的请求主动发给服务端。
        return "cost_budget"
    # 空字符串表示目前允许尝试。
    return ""


# 方法功能：请求返回后按实际 usage 再检查，粗估不保证绝对账单上限。
def check_used_budget(state: dict) -> str:
    # 超过累计 Token 预算时不再运行 Tool 或调用模型。
    if state["total_tokens"] > state["limits"]["max_total_tokens"]:
        # 当前请求已经发生，无法撤回其服务端费用。
        return "token_budget"
    # 估算费用达到预算时也停止后续调度。
    if Decimal(state["estimated_cost"]) > Decimal(state["limits"]["max_cost"]):
        # 这里只控制本次任务，不控制账号其他请求。
        return "cost_budget"
    # 尚未超出预算。
    return ""


# 方法功能：有限等待一次；仅在开启时间限制时检查等待是否超过截止时间。
def wait_to_retry(state: dict, error: Exception, retry_index: int, clock, sleep, kind: str) -> bool:
    # 使用 SDK 错误的响应头或有限指数等待。
    delay = retry_delay(error, retry_index, state["limits"])
    # 很长的服务端等待应直接结束，不把它缩短后重试。
    if delay > state["limits"]["max_retry_delay"]:
        # 保留明确的恢复失败原因。
        stop(state, "retry_delay_limit")
        # 告诉调用方不要再尝试。
        return False
    # 开启时间限制时，不让等待把任务拖过截止时间。
    if overall_timeout_reached(state, clock, delay):
        # 不启动超过本次总时间预算的重试。
        stop(state, "overall_timeout")
        # 无需阻塞到超时才结束。
        return False
    # 只记录安全的类别和等待秒数，不保存异常正文。
    state["events"].append({"kind": kind, "outcome": "retry_wait", "delay_seconds": delay})
    # 离线测试注入虚拟 sleep，实际执行才会短暂等待。
    sleep(delay)
    # 下一轮仍会检查全部预算。
    return True


# 方法功能：一次模型决策内部有限重试；每个请求尝试都单独记账。
def model_node(state: RecoveryState, model, clock, sleep) -> dict:
    # 不直接修改 LangGraph 传入的数据。
    current = copy_state(state)
    # 在当前模型决策内单独计算额外重试次数。
    retry_index = 0
    # 重试由明确的计数和预算终止，不使用无限无条件循环。
    while retry_index <= current["limits"]["max_retries"]:
        # 输入预留包含此前所有工具结果。
        reserved_input = estimate_input_tokens(current["messages"])
        # 每次重试前重新检查全部模型预算。
        reason = check_model_budget(current, clock, reserved_input)
        # 任一预算不满足就直接走失败分支。
        if reason:
            # 不发出本次请求。
            return stop(current, reason)
        # 开启时限制请求时间，关闭时用 None 同时关闭 SDK 超时。
        timeout = operation_timeout(current, "model_timeout", clock)
        # 仅在开启超时时处理检查后的线程调度或 Debug 暂停。
        if timeout is not None and timeout <= 0:
            # 不把未发出的请求计入模型尝试。
            return stop(current, "overall_timeout")
        # 在请求前计数，异常也算一次实际尝试。
        current["model_steps"] += 1
        # 只有真正启动了额外尝试才增加重试计数。
        current["model_retries"] += int(retry_index > 0)
        # 开始计时，用于识别已返回但超时的同步调用。
        started_at = clock()
        # 请求失败时默认没有可信 usage。
        usage = {}
        # 单独保存异常，协议检查失败也会进入受控分支。
        error = None
        # 请求只发送消息与工具说明，不发送预算 State。
        try:
            # SDK 自动重试关闭，timeout 与 max_tokens 由可信入口限制。
            response = model.request_with_tools(current["messages"], TOOL_SCHEMAS, timeout=timeout, max_tokens=current["limits"]["max_output_tokens"])
            # 保存接口报告的用量，即使生成被截断也要计费。
            usage = response.get("usage", {})
            # 校验完整的模型消息，防止执行无效工具请求。
            message = response["message"]
            # 不执行被截断或未知结束类型的工具请求。
            if response.get("finish_reason") not in ("stop", "tool_calls"):
                # 该错误不是临时系统故障，不自动重试。
                raise ValueError("模型响应未完整生成。")
            # 校验角色、参数字符串、调用 ID 等协议字段。
            validate_model_message(message)
            # 成功的 assistant 消息先进入上下文，再由 tools 回传结果。
            current["messages"].append(message)
            # 有效工具调用在结束时也会得到跳过说明，保持 ID 配对。
            current["pending_tool_calls"] = message.get("tool_calls", [])
        # 保留异常类型用于判定临时与永久错误。
        except Exception as caught:
            # 不把异常原文写入 State 或 Console。
            error = caught
        # 失败未知用量也按完整预留计入本次预算。
        charge_usage(current, usage, reserved_input, current["limits"]["max_output_tokens"])
        # 每次实际请求都保存一个可观察事件。
        current["events"].append({"kind": "model", "attempt": current["model_steps"], "outcome": "error" if error else "returned", "error_type": type(error).__name__ if error else "", "elapsed_seconds": clock() - started_at})
        # 开启超时时，截止后不执行迟到响应中的 Tool。
        if overall_timeout_reached(current, clock):
            # 已取得的消息、用量与历史仍然保留。
            return stop(current, "overall_timeout")
        # 输入粗估可能小于接口实际用量，因此返回后再次检查。
        reason = check_used_budget(current)
        # 预算超限优先于开始新工具或重试。
        if reason:
            # 当前请求已经记账，不会当成零费用。
            return stop(current, reason)
        # 仅在开启超时时检测单次请求耗时，Debug 默认不会走此失败分支。
        if timeout is not None and clock() - started_at >= timeout and error is None:
            # 丢弃迟到的回答作为最终答案，但不丢弃已记账用量。
            return stop(current, "model_timeout")
        # 明确的异常才考虑有限重试。
        if error is not None:
            # 非临时错误直接结束，不能盲目反复请求。
            if not is_temporary_error(error):
                # 认证、配置或协议错误由用户处理。
                return stop(current, "model_error")
            # 本次决策的重试次数用完后进入失败恢复节点。
            if retry_index >= current["limits"]["max_retries"]:
                # 不继续循环到成功为止。
                return stop(current, "model_retry_exhausted")
            # 最大模型尝试次数已到时不做无意义等待。
            if current["model_steps"] >= current["max_steps"]:
                # 失败请求也消耗最大步骤数。
                return stop(current, "max_steps")
            # 等待不足时也有明确的终止原因。
            if not wait_to_retry(current, error, retry_index, clock, sleep, "model"):
                # wait_to_retry 已经设置原因。
                return current
            # 只对同一模型决策增加一次额外尝试。
            retry_index += 1
            # 下一轮重新检查时间、Token 与费用。
            continue
        # 有工具请求时把执行交给 tools 节点。
        if current["pending_tool_calls"]:
            # 未结束仍使用空 stop_reason。
            return current
        # 无工具请求时读取模型文字，不把 JSON 数据当成最终答案。
        answer = (message.get("content") or "").strip()
        # 非空文字表示模型自然结束本次任务。
        if answer:
            # 保存模型原文，不额外请求模型总结。
            current["answer"] = answer
            # 这个原因由程序设置，不是 LLM 返回的字段。
            return stop(current, "final_answer")
        # 无工具且无文字时直接结束，避免空响应循环。
        return stop(current, "empty_response")
    # 循环上限保证这里不会继续发出请求。
    return stop(current, "model_retry_exhausted")


# 方法功能：静态分发只读函数，临时异常交给 tools 节点判定。
def dispatch_tool(name: str, arguments: str, tenant_id: str, data_file: Path) -> dict:
    # 仍只允许已实现的三个查询函数，不开放任意代码或写操作。
    tool_map = {"get_order": get_order, "get_payment": get_payment, "get_refund": get_refund}
    # 未知工具不执行，也不自动重试。
    if name not in tool_map:
        # success/data/error 格式保持不变。
        return tool_result(False, error="未知工具，只允许三个只读业务查询。")
    # 模型参数不是可信输入，需要实际解析和检查。
    try:
        # 参数仍是阶段 3 学过的 JSON 字符串。
        parsed = json.loads(arguments)
    # JSON 格式错误属于永久输入问题。
    except (json.JSONDecodeError, TypeError):
        # 不执行 Tool，也不把错误误报成查不到记录。
        return tool_result(False, error="工具参数必须是有效 JSON。")
    # 租户和路径不能由模型提供或覆盖。
    if not isinstance(parsed, dict) or set(parsed) != {"order_id"} or not isinstance(parsed["order_id"], str) or not parsed["order_id"].strip():
        # 参数失败直接走失败分支，不自动修复权限。
        return tool_result(False, error="工具只接受非空字符串 order_id。")
    # 调用真实只读业务函数，身份和路径由程序注入。
    return tool_map[name](parsed["order_id"], tenant_id, data_file=data_file)


# 方法功能：为一条调用保存完整结果，并追加匹配 ID 的 tool 消息。
def record_tool_result(state: dict, call: dict, result: dict, attempts: int, failure_kind: str = "") -> None:
    # 接口上下文保存序列化结果，不把预算或异常对象发给模型。
    state["messages"].append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)})
    # 尝试次数为零表示被跳过；重试次数包含在 attempts 中。
    state["tool_results"].append({"tool_call_id": call["id"], "tool_name": call["function"]["name"], "arguments": call["function"]["arguments"], "result": result, "attempts": attempts, "failure_kind": failure_kind})


# 方法功能：依次执行本轮 Tool；业务失败终止，临时异常有限重试。
def tools_node(state: RecoveryState, data_file: Path, clock, sleep) -> dict:
    # 保留之前的证据，所有更新发生在新的字典与列表中。
    current = copy_state(state)
    # 单独复制待执行调用，按已完成条目逐条移除。
    current["pending_tool_calls"] = list(state["pending_tool_calls"])
    # 这一轮可能包含多个 Tool 请求。
    while current["pending_tool_calls"]:
        # 总是处理当前第一条，不跳过失败后继续查询。
        call = current["pending_tool_calls"][0]
        # 每条调用单独拥有有限重试额度。
        attempts = 0
        # 重试次数是额外尝试，不包括第一次执行。
        retry_index = 0
        # 单条 Tool 也不能无限重试。
        while retry_index <= current["limits"]["max_retries"]:
            # 每次真正执行前检查总时间和总 Tool 次数。
            reason = "overall_timeout" if overall_timeout_reached(current, clock) else ("tool_limit" if current["tool_calls"] >= current["limits"]["max_tool_calls"] else "")
            # 等待可能超时；已经执行过的请求不能误标为完全跳过。
            if reason:
                # 只有尚未尝试的请求才能由 finish 标记为零次。
                if attempts:
                    # 保留上一轮实际失败结果和尝试次数。
                    record_tool_result(current, call, result, attempts, reason)
                    # 当前调用已处理，剩余请求仍由 finish 配齐。
                    current["pending_tool_calls"].pop(0)
                # 不启动新的工具分发。
                return stop(current, reason)
            # 开启时限制本地 Tool 耗时，关闭时不设检测窗口。
            timeout = operation_timeout(current, "tool_timeout", clock)
            # 仅在开启超时时处理前一次检查后的 Debug 暂停。
            if timeout is not None and timeout <= 0:
                # 已经尝试过时仍保留其事实，不声称未执行。
                if attempts:
                    # 保存上一次系统失败结果。
                    record_tool_result(current, call, result, attempts, "overall_timeout")
                    # 该调用已有配对结果。
                    current["pending_tool_calls"].pop(0)
                # 单次操作还没有启动，不增加次数。
                return stop(current, "overall_timeout")
            # 每次分发尝试都计数，包括被拒绝的参数或工具名。
            current["tool_calls"] += 1
            # 只有真正启动额外尝试时增加重试计数。
            current["tool_retries"] += int(retry_index > 0)
            # 记录当前请求实际发生的尝试数。
            attempts += 1
            # 同步函数返回后计算耗时，不创建可能继续运行的后台线程。
            started_at = clock()
            # 默认没有异常，返回结果可能为业务失败。
            error = None
            # 业务 Tool 的普通返回与临时异常分别处理。
            try:
                # 通过静态白名单调用查询函数。
                result = dispatch_tool(call["function"]["name"], call["function"]["arguments"], current["tenant_id"], data_file)
                # 无效 Tool 返回格式不应被当作成功。
                if not isinstance(result, dict) or set(result) != {"success", "data", "error"} or type(result["success"]) is not bool:
                    # 协议错误是永久错误，不在临时异常白名单。
                    raise ValueError("Tool 返回格式无效。")
            # 临时系统异常与程序错误都保留安全的类型记录。
            except Exception as caught:
                # 不把内部路径、密钥或原始异常发给模型。
                error = caught
                # 未拿到结果时不能伪造空数据成功。
                result = tool_result(False, error="Tool 系统异常，未确认查询结果。")
            # 每次执行尝试都保留事件，业务返回 False 与抛异常不同。
            current["events"].append({"kind": "tool", "tool_call_id": call["id"], "attempt": current["tool_calls"], "outcome": "error" if error else ("success" if result["success"] else "business_failure"), "error_type": type(error).__name__ if error else "", "elapsed_seconds": clock() - started_at})
            # 开启时间限制时整体超时优先，关闭时继续正常调度。
            reason = "overall_timeout" if overall_timeout_reached(current, clock) else ""
            # 仅在开启超时时，检测同步 Tool 返回后的耗时。
            if not reason and timeout is not None and clock() - started_at >= timeout:
                # 迟到结果不能被当作按时完成。
                reason = "tool_timeout"
            # 本课超时后直接结束，不重试耗时已超限的同步工具。
            if reason:
                # 保留已得到的真实结果，而不是声称 Tool 没执行。
                record_tool_result(current, call, result, attempts, reason)
                # 已处理这条调用，剩余调用由 finish 配齐跳过说明。
                current["pending_tool_calls"].pop(0)
                # 超时后的远端取消与写操作幂等性留待后续。
                return stop(current, reason)
            # 普通业务返回不重试，包括订单不存在和权限不可读取。
            if error is None:
                # success=false 与成功的空列表必须保留区别。
                record_tool_result(current, call, result, attempts, "" if result["success"] else "business_error")
                # 当前调用已有配对结果，不会重复执行。
                current["pending_tool_calls"].pop(0)
                # 业务失败明确进入 failure 节点，不交给模型无限修正。
                if not result["success"]:
                    # 已取得的之前结果不丢失。
                    return stop(current, "business_error")
                # 当前 Tool 成功后才继续处理本批次下一条。
                break
            # 未知系统错误不重试；临时错误也受单条与总次数限制。
            reason = "tool_error" if not is_temporary_error(error) else "tool_retry_exhausted"
            # 临时故障还有单条重试额度，但总次数已用尽时明确报告 Tool 上限。
            if reason == "tool_retry_exhausted" and retry_index < current["limits"]["max_retries"] and current["tool_calls"] >= current["limits"]["max_tool_calls"]:
                # 不等待，也不发起超出总预算的重试。
                reason = "tool_limit"
            # 只有明确临时异常且还可额外尝试时才等待。
            if reason == "tool_retry_exhausted" and retry_index < current["limits"]["max_retries"] and current["tool_calls"] < current["limits"]["max_tool_calls"]:
                # 等待仍要遵守整体截止时间和 Retry-After。
                if wait_to_retry(current, error, retry_index, clock, sleep, "tool"):
                    # 下一次额外尝试会计入 Tool 总次数。
                    retry_index += 1
                    # 不向上下文追加中间异常，最终结果只配对一次。
                    continue
                # 等待失败时沿用设置好的截止或延迟限制原因。
                reason = current["stop_reason"]
            # 无论是否用尽重试，当前调用都保存失败结果。
            record_tool_result(current, call, result, attempts, reason)
            # 当前调用已经执行过，不能在 finish 中误标成完全跳过。
            current["pending_tool_calls"].pop(0)
            # 进入明确的失败分支，不继续后续业务查询。
            return stop(current, reason)
    # 一轮所有工具成功时，交给下一轮模型决定是否继续。
    return current


# 方法功能：输入错误进失败分支，否则进入模型。
def choose_start_route(state: RecoveryState) -> str:
    # prepare 负责输入校验。
    return "failure" if state["stop_reason"] else "model"


# 方法功能：区分自然完成、工具请求与控制性失败。
def choose_model_route(state: RecoveryState) -> str:
    # 有答案时不再执行其他工具。
    if state["stop_reason"] == "final_answer":
        # 最后一轮恰好达到步骤上限也算自然完成。
        return "finish"
    # 预算、超时、协议或系统失败进入独立节点。
    return "failure" if state["stop_reason"] else "tools"


# 方法功能：Tool 失败进 failure，全部成功才回模型。
def choose_tools_route(state: RecoveryState) -> str:
    # 下一次模型请求前还会再次检查步骤与预算。
    return "failure" if state["stop_reason"] else "model"


# 方法功能：不用 LLM 生成失败说明，保留业务证据且不额外花费。
def failure_node(state: RecoveryState) -> dict:
    # 各种终止原因有不同说明，避免把查询失败说成没有记录。
    reasons = {"invalid_input": "问题或租户身份无效。", "business_error": "业务查询失败，不自动重试。", "model_error": "模型配置、协议或永久系统错误，不自动重试。", "model_retry_exhausted": "模型临时故障，有限重试仍未恢复。", "tool_error": "Tool 永久系统错误，不自动重试。", "tool_retry_exhausted": "Tool 临时故障，有限重试仍未恢复。", "max_steps": "已达到最大模型尝试次数。", "tool_limit": "已达到最大 Tool 尝试次数。", "overall_timeout": "整体时间预算不足或已超时，停止后续调度。", "model_timeout": "模型返回超过单次时间限制。", "tool_timeout": "Tool 返回超过单次时间限制。", "token_budget": "Token 预算不足或实际用量超限。", "cost_budget": "估算费用预算不足或已超限。", "empty_response": "模型没有工具请求，也没有文字回答。", "retry_delay_limit": "服务端要求等待过久，本次不继续重试。"}
    # 未知原因也不伪造成功。
    explanation = reasons.get(state["stop_reason"], "本次任务受控结束。")
    # 已知 Tool 失败保留其业务提示，不输出内部异常正文。
    if state["stop_reason"] == "business_error" and state["tool_results"]:
        # 原始 Tool 返回遵循安全的 success/data/error 约定。
        explanation += " " + str(state["tool_results"][-1]["result"]["error"])
    # 明确已有结果仍在，未查询部分不能补造。
    return {"answer": explanation + " 已取得的 Tool 结果保留；未执行的查询不代表没有业务记录。"}


# 方法功能：补齐未执行工具的配对结果，记录耗时后进入 END。
def finish_node(state: RecoveryState, clock) -> dict:
    # 终止更新不改变以前的消息和结果对象。
    current = copy_state(state)
    # 同批未执行请求也必须有对应 tool_call_id，避免留下半套消息。
    for call in state["pending_tool_calls"]:
        # 明确该查询没有执行，不能返回成功空列表。
        result = tool_result(False, error=f"本次因 {state['stop_reason']} 结束，此 Tool 未执行。")
        # attempts=0 不占 Tool 尝试次数。
        record_tool_result(current, call, result, 0, "skipped")
        # 调试时可以区分跳过与执行失败。
        current["events"].append({"kind": "tool", "tool_call_id": call["id"], "outcome": "skipped"})
    # 所有调用均有配对消息，清空待执行列表。
    current["pending_tool_calls"] = []
    # Debug 断点暂停也计入真实时间，离线测试用虚拟时钟。
    current["elapsed_seconds"] = max(0.0, clock() - state["started_at"])
    # 返回当前任务最终字典，不创建新图或新会话。
    return current


# 方法功能：保留简单函数节点，构建带恢复分支和预算的第 63 课工作流。
def build_graph(model, data_file: Path = DEFAULT_DATA_FILE, limits=None, clock=time.monotonic, sleep=time.sleep):
    # 构图时检查预算，不调用模型或业务 Tool。
    trusted_limits = make_limits(limits)
    # 内部函数绑定可信预算和单调时钟。
    def run_prepare(state: RecoveryState) -> dict:
        # 节点仍只接收一个 State 参数。
        return prepare_node(state, trusted_limits, clock)
    # 内部函数绑定模型与测试可替换的等待函数。
    def run_model(state: RecoveryState) -> dict:
        # 可以在 model_node 中观察每次尝试与预留预算。
        return model_node(state, model, clock, sleep)
    # 内部函数绑定只读 JSON 文件和时钟。
    def run_tools(state: RecoveryState) -> dict:
        # 临时异常的有限重试在 tools_node 中实现。
        return tools_node(state, data_file, clock, sleep)
    # 内部函数绑定结束时的时钟。
    def run_finish(state: RecoveryState) -> dict:
        # 配齐跳过消息并记录最终耗时。
        return finish_node(state, clock)
    # 本课统一使用扩展后的 RecoveryState，不改变旧 AgentState 图。
    graph = StateGraph(RecoveryState)
    # prepare 初始化字段，但不发请求。
    graph.add_node("prepare", run_prepare)
    # model 执行有预算的模型决策。
    graph.add_node("model", run_model)
    # tools 执行有上限的只读工具。
    graph.add_node("tools", run_tools)
    # failure 是明确的失败恢复节点，不调用 LLM。
    graph.add_node("failure", failure_node)
    # finish 处理最后的协议配对与统计。
    graph.add_node("finish", run_finish)
    # 每次 invoke 都从准备节点开始。
    graph.add_edge(START, "prepare")
    # 输入无效直接结束，不消耗模型预算。
    graph.add_conditional_edges("prepare", choose_start_route, {"model": "model", "failure": "failure"})
    # 模型可能选择工具、直接回答或发生控制性失败。
    graph.add_conditional_edges("model", choose_model_route, {"tools": "tools", "failure": "failure", "finish": "finish"})
    # 全部 Tool 成功才继续模型循环。
    graph.add_conditional_edges("tools", choose_tools_route, {"model": "model", "failure": "failure"})
    # 失败说明生成后也统一结束。
    graph.add_edge("failure", "finish")
    # 没有图边能从 END 回到模型。
    graph.add_edge("finish", END)
    # 图调度次数与模型尝试次数不同，为失败和结束节点留出余量。
    return graph.compile().with_config({"recursion_limit": 2 * trusted_limits["max_steps"] + 6})
