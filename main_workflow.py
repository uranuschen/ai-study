import json
import sys
from pathlib import Path
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command


# (70) 根目录入口可直接 Run / Debug，不需要命令行参数。
BASE_DIR = Path(__file__).resolve().parent
# (70) 保留原来的 src 包定位方式。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.cli import build_pipeline
from agent_learning.core.config import load_settings
from agent_learning.core.models import SearchFilter
from agent_learning.workflows.diagnosis_agent import build_graph
from agent_learning.workflows.tracing import TraceRecorder
from agent_learning.workflows.tool_model import CompatibleToolModel


# (70) 业务数据仍只读本地 JSON，不修改或初始化数据库。
DATA_FILE = BASE_DIR / "data" / "business_demo.json"
# (70) 身份、权限与资料范围由可信入口提供。
TENANT_ID = "acme"
# (70) 不允许模型修改可读权限。
SECURITY_LEVEL = 1
# (70) 规则资料不代替订单当前事实。
DOC_TYPE = "policy"
# (70) 同一会话保留消息，新问题生成新 run_id。
THREAD_ID = "lesson-70-order"
# (70) 沿用整轮历史裁剪，不新增摘要模型。
MAX_HISTORY_TURNS = 2
# (70) 字符预算不是精确 Token 数。
MAX_CONTEXT_CHARS = 12000
# (70) 次数包含外层 Agent、RAG 内层模型与实际失败重试。
MAX_STEPS = 10
# (70) 只读 Tool 重试也消耗总工具次数，人工等待不算执行。
MAX_TOOL_CALLS = 12
# (70) 临时系统错误最多额外尝试一次，业务失败不重试。
MAX_RETRIES = 1
# (70) 未知用量使用保守预留，不能声称精确账单硬上限。
MAX_TOTAL_TOKENS = 100000
# (70) 单位与下面教学单价一致，默认 CNY。
MAX_COST = "1.00"
# (69) 这两个单价仅作教学估算，不是 DeepSeek 当前报价，不含缓存折扣。
INPUT_PRICE_PER_MILLION = "10"
# (69) 输入与输出分开估算，不读取或查询账号账单。
OUTPUT_PRICE_PER_MILLION = "20"
# (70) 默认只记录耗时，不因 Debug 或人工等待而触发超时。
ENABLE_TIMEOUTS = False
# (69) True 逐行显示脱敏完成事件；完整起止事件始终保存在 State。
SHOW_TRACE_EVENTS = True
# (70) 默认沿用已有在线兼容接口，也可选择本机已有模型。
USE_OLLAMA = False
# (70) 只使用本机已安装的模型，不自动下载。
OLLAMA_MODEL = "qwen3:8b"


# (69) Console 只显示运行元数据，不打印完整 messages、Tool 结果或原始异常。
def show_trace(result: dict, details: bool = True) -> None:
    # (69) 汇总只计实际 LLM 事件，不对父节点和 Tool 再次记费。
    summary = TraceRecorder(result).summary()
    # (69) 明确未知用量次数，不能将未知值当成零。
    print("Tracing 汇总：", json.dumps(summary, ensure_ascii=False))
    # (69) 详细日志可关闭，不影响 State 中保存的执行记录。
    if SHOW_TRACE_EVENTS and details:
        # (69) 每次完成的节点、Tool、LLM 都输出一条安全事件。
        for event in result.get("trace_events", []):
            # (69) 起止事件都在 State；Console 只展示完成事件以减少重复输出。
            if event["phase"] == "end":
                # (69) 事件已按白名单脱敏，不输出业务上下文。
                print("[trace]", json.dumps(event, ensure_ascii=False))


# (70) 保留第 67 课的人工交互，只为当前中断补充决定。
def resume_approvals(graph: CompiledStateGraph, result: dict, config: dict) -> dict | None:
    # (70) 一个批次可以逐个审批多个敏感请求，不一次批准后面全部操作。
    while result.get("__interrupt__"):
        # (70) 恢复时必须原样绑定实际请求，不让人重新填写工具目标。
        request = result["__interrupt__"][0].value
        # (69) 暂停时只展示截至当前的汇总，避免恢复后重复输出同一条完成事件。
        show_trace(result, details=False)
        # (70) 仅展示人工必须确认的目标；不显示模型自由生成的调用 ID。
        visible = {key: request[key] for key in ("action", "order_id", "tenant_id", "mode")}
        # (70) 这是人工审批界面，不是包含完整请求的运行日志。
        print("等待人工审批：", json.dumps(visible, ensure_ascii=False))
        # (70) 没有明确决定就继续等输入，空值不能默认批准。
        while True:
            # (70) 交互规则仍是确认、拒绝或退出，不接受新问题覆盖暂停任务。
            choice = input("模拟取消：y/approve 确认，n/reject 拒绝，q 退出：").strip().lower()
            # (70) 退出不执行待审批操作；本课内存存档不跨进程保留。
            if choice == "q":
                # (70) 不声称已经回滚或执行了业务操作。
                print("已退出，待审批操作未执行；内存存档不跨进程保留。")
                # (70) 通知 main 停止当前交互。
                return None
            # (70) 只接受明确的人工决定。
            if choice in ("y", "approve", "n", "reject"):
                # (70) 结束本次输入等待。
                break
            # (70) 审批时不能切换 thread_id 或覆盖当前问题。
            print("请输入 y/approve 或 n/reject；待审批时不能切换会话。")
        # (70) 决定与操作、订单、租户和原调用 ID 绑定。
        decision = {**request, "decision": "approve" if choice in ("y", "approve") else "reject"}
        # (70) 恢复保留同一 run_id、预算与会话，不重新执行 prepare。
        result = graph.invoke(Command(resume=decision), config=config)
    # (70) 没有新的动态暂停时，交回最终 State。
    return result


# (70) 综合入口只初始化一次对象，再接受同会话连续提问。
def main():
    # (70) 仅用户运行本入口时才读取已有配置，不打印密钥或连接信息。
    settings = load_settings()
    # (70) Debug 不设置客户端超时；开启时间预算时由执行器传入显式限制。
    settings.llm_timeout = None
    # (70) 使用本地已有向量与精排模型，不自动下载。
    settings.local_files_only = True
    # (70) 保留之前的本地兼容模型开关。
    if USE_OLLAMA:
        # (70) 使用本机已启动的兼容服务。
        settings.llm_base_url = "http://127.0.0.1:11434/v1"
        # (70) 模型名称直接在本文件顶部修改。
        settings.llm_model = OLLAMA_MODEL
        # (70) 本地服务占位值不是在线密钥。
        settings.llm_api_key = "ollama"
    # (70) 原模型适配与 RAG 构造器保持原来的调用方式。
    model = CompatibleToolModel(settings)
    # (70) 构造管道不自动建表、入库或下载模型。
    pipeline = build_pipeline(settings)
    # (70) 不从自然语言或模型参数提取权限。
    filters = SearchFilter(tenant_id=TENANT_ID, max_security_level=SECURITY_LEVEL, doc_type=DOC_TYPE)
    # (70) 内存存档保留图进度与会话历史，退出进程后丢失。
    checkpointer = InMemorySaver()
    # (70) 原第 63 课预算函数检查这些可信配置。
    limits = {"max_steps": MAX_STEPS, "max_tool_calls": MAX_TOOL_CALLS, "max_retries": MAX_RETRIES, "max_total_tokens": MAX_TOTAL_TOKENS, "max_cost": MAX_COST, "input_price_per_million": INPUT_PRICE_PER_MILLION, "output_price_per_million": OUTPUT_PRICE_PER_MILLION, "currency": "CNY", "enable_timeouts": ENABLE_TIMEOUTS}
    # (69) 本机模型不计在线 API 费用，不估算硬件成本。
    if USE_OLLAMA:
        # (69) 零单价仍保留实际接口报告的 Token。
        limits.update({"input_price_per_million": "0", "output_price_per_million": "0"})
    # (70) 业务、RAG、会话、恢复、预算和审批编译为同一张图。
    graph = build_graph(model, pipeline, filters, checkpointer, data_file=DATA_FILE, limits=limits, max_history_turns=MAX_HISTORY_TURNS, max_context_chars=MAX_CONTEXT_CHARS)
    # (70) 固定配置结构，相同 thread_id 对应同一份会话存档。
    config = {"configurable": {"thread_id": THREAD_ID}}
    # (70) 新会话只换编号，不删除旧存档。
    session_number = 1
    # (70) 保持直接 Console 交互，不添加命令行参数。
    print("第 69/70 课：订单诊断与 Tracing；/new 新会话，q 退出。取消 A1001 仅模拟。")
    # (70) 每个新问题独立预算，暂停恢复不从这里重新开始。
    while True:
        # (70) 可以先查 A1002 退款，再追问规则；取消用待支付 A1001 演示。
        question = input(f"[{config['configurable']['thread_id']}] 请输入问题：").strip()
        # (70) 退出不会保留内存 Checkpoint 到下次进程。
        if question.lower() == "q":
            # (70) 不再发出任何请求。
            return
        # (70) 会话切换仍沿用第 66 课的编号方式。
        if question.lower() == "/new":
            # (70) 生成当前进程内新的逻辑会话编号。
            session_number += 1
            # (70) 不把旧会话消息、审批决定或模拟记录带入新会话。
            config = {"configurable": {"thread_id": f"{THREAD_ID}-{session_number}"}}
            # (70) 提示当前编号，便于与 trace 对照。
            print("已切换新会话：", config["configurable"]["thread_id"])
            # (70) 下一次输入再启动新任务。
            continue
        # (70) 空输入不清空会话，也不调用模型。
        if not question:
            # (70) 原有历史保持不变。
            print("请输入非空问题。")
            # (70) 不产生一个无意义的 run_id。
            continue
        # (70) 业务失败由图内失败节点处理；未处理异常不输出原始文本。
        try:
            # (70) 只传新问题与可信租户，不能覆盖 messages 或预算计数。
            result = graph.invoke({"question": question, "tenant_id": TENANT_ID}, config=config)
            # (70) 只有实际取消请求才进入人工审批。
            result = resume_approvals(graph, result, config)
        # (69) 原始异常可能含请求或凭证，Console 只提示固定排查说明。
        except Exception as error:
            # (70) 不在失败节点上强行提交新问题或无限自动重试。
            print("图执行异常，请在 Debug 检查；本次退出，不输出原始异常。")
            # (70) 停止当前入口，避免覆盖未完成状态。
            return
        # (70) 审批中 q 表示直接退出，不提交下一轮。
        if result is None:
            # (70) 未执行待审批操作。
            return
        # (70) 回答仍由原模型或受控失败模板提供。
        print("输出：", result["answer"])
        # (70) 预算不足、拒绝、资料不足与系统失败不混同。
        print("结束原因：", result["stop_reason"])
        # (70) 含 RAG 内层和实际失败重试，不仅是外层决策次数。
        print("LLM 尝试 / Tool 尝试：", result["model_steps"], "/", result["tool_calls"])
        # (70) 用量未知时这两个数可能包含保守预算预留。
        print("预算记账 Token / 估算费用：", result["total_tokens"], "/", result["estimated_cost"], limits["currency"])
        # (69) 整轮时间包含人工等待和 Debug 停顿，不用父子耗时相加。
        print("本轮耗时（秒）：", round(result["elapsed_seconds"], 3))
        # (69) 日志只输出安全元数据与汇总，不打印完整 Tool 结果。
        show_trace(result)


# (70) 用户明确 Run / Debug 时才启动真实模型与可选 RAG 查询。
if __name__ == "__main__":
    # (70) 本次开发验证只运行离线测试，不自动启动真实入口。
    main()
