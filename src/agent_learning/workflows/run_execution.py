import json
import time
from agent_learning.workflows.agent_loop import validate_model_message
from agent_learning.workflows import recovery_agent as recovery
from agent_learning.workflows.tracing import TraceRecorder


# (70) 仅传递程序确定的结束原因，不携带原始异常或请求内容。
class ExecutionStopped(RuntimeError):
    # (70) 使用普通异常类，让 RAG 与外层 Agent 共用同一个退出边界。
    pass


# (70) 一次节点执行使用一个普通对象，绑定同一轮预算与追踪记录。
class RunExecution:
    # (70) 依赖显式传入，不将运行信息存进全局变量或模型对象。
    def __init__(self, state: dict, trace: TraceRecorder, parent_id: str = "", clock=time.monotonic, sleep=time.sleep):
        # (70) 外层模型、RAG 内层模型共同更新这一轮的 State 副本。
        self.state = state
        # (69) 事件写入当前 run_id 对应的记录列表。
        self.trace = trace
        # (69) 父节点或父 Tool 的 span_id 用于串联调用关系。
        self.parent_id = parent_id
        # (70) 离线测试可以注入虚拟时钟和等待函数。
        self.clock, self.sleep = clock, sleep
        # (69) RAG 步骤只在本次调用中使用，不跨线程共享。
        self.rag_stage = None

    # (69) 进入新的 RAG 步骤时，结束前一个步骤并开始新记录。
    def stage(self, name: str) -> None:
        # (69) 前一个步骤正常返回，不再重复计入其子模型的 Token。
        self.finish_stage()
        # (69) RAG 步骤属于当前知识库 Tool，而不是另一轮对话。
        self.rag_stage = self.trace.start("node", name, parent_id=self.parent_id)

    # (69) 记录 RAG 步骤的成功或安全错误分类，不保留原始异常文本。
    def finish_stage(self, error: Exception | None = None) -> None:
        # (69) 无活动步骤时不生成重复记录。
        if self.rag_stage is not None:
            # (69) 步骤耗时与内部 LLM 耗时有包含关系，不能直接相加。
            self.trace.finish(self.rag_stage, "error" if error else "success", error=error)
            # (69) 一个步骤只结束一次。
            self.rag_stage = None

    # (70) 设置受控退出原因，再让外层节点生成失败说明。
    def stop(self, reason: str) -> None:
        # (70) 原因来自白名单预算与流程判断，不来自异常字符串。
        self.state["stop_reason"] = reason
        # (70) 不在内部继续请求模型生成错误解释。
        raise ExecutionStopped(reason)

    # (70) 每次实际 LLM 尝试都检查同一份预算，内外层调用采用相同规则。
    def request(self, model, messages: list, tools: list | None = None):
        # (69) 只记录固定作用域名称，不记录模型问题或返回正文。
        scope = "agent_model" if tools is not None else "rag_model"
        # (70) 有限循环只负责当前模型决策的临时系统错误。
        for retry_index in range(self.state["limits"]["max_retries"] + 1):
            # (70) 输入预留包含实际消息和本次工具说明，不冒充精确分词。
            payload = json.dumps({"messages": messages, "tools": tools or []}, ensure_ascii=False)
            # (70) 沿用第 63 课 UTF-8 字节数加协议余量的保护性估计。
            reserved_input = len(payload.encode("utf-8")) + 1024
            # (70) 失败重试和 RAG 内层请求也不能绕过总次数与费用检查。
            reason = recovery.check_model_budget(self.state, self.clock, reserved_input)
            # (70) 预算不足时不发送请求。
            if reason:
                # (70) 保留已经取得的业务结果与追踪记录。
                self.stop(reason)
            # (70) Debug 默认关闭时间限制，传给 SDK 的 timeout 为 None。
            timeout = recovery.operation_timeout(self.state, "model_timeout", self.clock)
            # (70) 开启超时时，在实际请求前再检查剩余时间。
            if timeout is not None and timeout <= 0:
                # (70) 尚未发送的请求不占模型次数。
                self.stop("overall_timeout")
            # (70) 每次真正尝试均计数，包括失败和 RAG 内层请求。
            self.state["model_steps"] += 1
            # (70) 只有真正启动额外尝试才记一次重试。
            self.state["model_retries"] += int(retry_index > 0)
            # (69) 内层 LLM 挂在当前 RAG 步骤下，外层挂在模型节点下。
            parent_id = self.rag_stage["span_id"] if self.rag_stage is not None else self.parent_id
            # (69) 一次实际请求只产生一条完成用量记录。
            span = self.trace.start("llm", scope, parent_id=parent_id, attempt=self.state["model_steps"], retry=retry_index)
            # (70) 请求异常时用量未知，由预算函数使用保守预留。
            usage, error, value = {}, None, None
            # (70) 这里只包住模型请求与协议校验，不包住 interrupt。
            try:
                # (70) 外层使用原 Tool Calling 适配，不重写接口协议。
                if tools is not None:
                    # (70) SDK 内部重试原本就是零，预算直接控制每次实际请求。
                    response = model.request_with_tools(messages, tools, timeout=timeout, max_tokens=self.state["limits"]["max_output_tokens"])
                    # (69) 即使响应被截断，也先保留接口报告的用量。
                    usage = response.get("usage", {})
                    # (70) 不执行半截工具调用或未知结束类型。
                    if response.get("finish_reason") not in ("stop", "tool_calls"):
                        # (70) 协议错误不自动重试。
                        raise ValueError("模型响应不完整。")
                    # (70) 继续使用之前的 assistant 与调用 ID 校验。
                    validate_model_message(response["message"])
                    # (70) 只把模型消息交回模型节点，不混入追踪信息。
                    value = response["message"]
                    # (70) 有效响应先保留证据；若实际用量超限，finish 仍可配齐未执行调用。
                    self.state["messages"].append(value)
                    # (70) 这里仅保存模型请求，业务 Tool 尚未执行。
                    self.state["pending_tool_calls"] = value.get("tool_calls", [])
                # (70) RAG 内层沿用原客户端，只读取完整响应与用量。
                else:
                    # (70) 关闭 SDK 隐藏重试，和外层共享总请求预算。
                    response = model.request(messages, timeout=timeout, max_tokens=self.state["limits"]["max_output_tokens"], max_retries=0)
                    # (69) 内层的 usage 也单独记录，避免从 Tool 父事件重复统计。
                    usage = response.get("usage", {})
                    # (70) RAG 需要完整文字，不接收截断或工具调用响应。
                    if response.get("finish_reason") != "stop" or not isinstance(response.get("content"), str):
                        # (70) 格式错误仍记账，但不交给引用校验伪装成功。
                        raise ValueError("RAG 模型响应不完整。")
                    # (70) 原 RAG 校验仍读取字符串，不需要修改其业务结果格式。
                    value = response["content"]
            # (70) 保存异常对象只用于当次分类，不写进 State 或 Console。
            except Exception as caught:
                # (70) 错误原文可能含密钥、请求体或数据库连接信息。
                error = caught
            # (70) 每次请求尝试都记账，缺失 usage 使用第 63 课的保守预留。
            recovery.charge_usage(self.state, usage, reserved_input, self.state["limits"]["max_output_tokens"])
            # (69) 用固定作用域区分 Agent 与 RAG 内层，不记录模型名称或配置。
            self.state["usage_history"][-1]["scope"] = scope
            # (69) Tracing 记录真实 usage；预算预留另存，不能冒充实测。
            self.trace.finish(span, "error" if error else "success", error=error, usage=usage, reserved_input=reserved_input, reserved_output=self.state["limits"]["max_output_tokens"], estimated_cost=self.state["usage_history"][-1]["estimated_cost"])
            # (70) 实际用量可能高于保护性估计，因此请求后再次检查。
            reason = recovery.check_used_budget(self.state)
            # (70) 已超预算时不继续运行工具或为失败再调用模型。
            if reason:
                # (70) 本次请求已经发生，用量不能撤销。
                self.stop(reason)
            # (70) 只在显式启用时执行耗时限制，Debug 不会因断点失败。
            if recovery.overall_timeout_reached(self.state, self.clock):
                # (70) 已保存的用量和错误分类仍然保留。
                self.stop("overall_timeout")
            # (70) 请求返回后的单次超时只控制后续调度，不声称远端请求已取消。
            if timeout is not None and self.clock() - span["started_at"] >= timeout and error is None:
                # (70) 迟到的响应不继续执行业务操作。
                self.stop("model_timeout")
            # (70) 没有异常时交回完整响应，后续由节点选择工具或回答。
            if error is None:
                # (70) 不额外生成一次总结模型调用。
                return value
            # (70) 只有之前课程列出的临时异常可以自动重试。
            if not recovery.is_temporary_error(error):
                # (70) 配置、认证与协议错误直接结束。
                self.stop("model_error")
            # (70) 单次决策重试用尽后停止，不无限循环。
            if retry_index >= self.state["limits"]["max_retries"]:
                # (70) 失败原因由程序确定，不读取原始异常字符串。
                self.stop("model_retry_exhausted")
            # (70) 总请求次数已用完时不做无意义等待。
            if self.state["model_steps"] >= self.state["max_steps"]:
                # (70) 失败请求同样已经消耗额度。
                self.stop("max_steps")
            # (69) 重试等待单独记录，不把它当作另一条模型用量。
            wait_span = self.trace.start("node", "model_retry_wait", parent_id=parent_id, retry=retry_index + 1)
            # (70) 沿用原有限退避与 Retry-After 规则。
            can_retry = recovery.wait_to_retry(self.state, error, retry_index, self.clock, self.sleep, "model")
            # (69) 只记录等待状态与耗时，不记录异常原文。
            self.trace.finish(wait_span, "success" if can_retry else "error")
            # (70) 等待不被允许时使用预算函数已设置的结束原因。
            if not can_retry:
                # (70) 不越过等待限制继续发出请求。
                self.stop(self.state["stop_reason"])

    # (70) RAGPipeline.ask 使用这个普通方法，把内层请求纳入同一轮预算。
    def chat(self, model, messages: list) -> str:
        # (70) tools=None 表示 RAG 文本生成，不是另一个工具选择循环。
        return self.request(model, messages)
