# 第 63 课入口保留作对照；当前 RAG Tool 课程使用 main_workflow.py。
# 导入标准库，用于把 Tool 字典结果显示为易读的 JSON。
import json
# 导入系统模块，让 IDE 直接运行时可以找到 src 包。
import sys
# 导入路径类，让入口配置不依赖 IDE 工作目录。
from pathlib import Path


# 当前文件所在目录是项目根目录。
BASE_DIR = Path(__file__).resolve().parent
# 直接点击 Run / Debug 时，让 Python 找到 src 下的代码。
sys.path.insert(0, str(BASE_DIR / "src"))

# 导入现有配置读取函数；运行入口时才读取用户的模型配置。
from agent_learning.core.config import load_settings
# 导入第 63 课恢复流程；agent_loop.py 和 order_flow.py 保留作对照。
from agent_learning.workflows.recovery_agent import build_graph
# 导入支持 Tool Calling 的普通模型类。
from agent_learning.workflows.tool_model import CompatibleToolModel


# 业务 Tool 继续读取本地 JSON 模拟数据。
DATA_FILE = BASE_DIR / "data" / "business_demo.json"
# 租户来自可信入口；改为 other 可对照同号订单的隔离效果。
TENANT_ID = "acme"
# 最多尝试调用模型 5 次，失败、重试与最终回答都计入。
MAX_STEPS = 5
# Tool 总分发尝试上限，包括同批多个请求、被拒绝请求与额外重试。
MAX_TOOL_CALLS = 6
# 每次模型决策或每条只读 Tool 请求，最多额外重试两次。
MAX_RETRIES = 2
# 学习与 Debug 默认关闭全部超时限制；改为 True 才启用下面三项时间预算。
ENABLE_TIMEOUTS = False
# 开启时间限制时，单次模型请求超时秒数，SDK 自动重试已关闭。
MODEL_TIMEOUT = 30.0
# 开启时间限制时，本地同步 Tool 返回后的超时检测秒数，不是后台线程强杀。
TOOL_TIMEOUT = 2.0
# 开启时间限制时，整个任务的时间预算包含重试等待和 Debug 暂停。
OVERALL_TIMEOUT = 90.0
# 单次模型生成最多 1200 Token。
MAX_OUTPUT_TOKENS = 1200
# 累计 Token 预算，失败的未知用量也会按预留记账。
MAX_TOTAL_TOKENS = 30000
# 费用预算单位为下面的币种；这里控制的是估算费用。
MAX_COST = "0.50"
# 演示单价：每百万输入 Token 的费用，不是 DeepSeek 实时报价。
INPUT_PRICE_PER_MILLION = "10"
# 演示单价：每百万输出 Token 的费用，真实运行前按所选模型核对。
OUTPUT_PRICE_PER_MILLION = "20"
# 预算与两个单价使用同一种币种，不自动换算汇率。
COST_CURRENCY = "CNY"
# False 使用已有在线模型配置；True 改用本机支持 Tool Calling 的 Ollama 模型。
USE_OLLAMA = False
# 使用本机已有的模型名，程序不会下载模型。
OLLAMA_MODEL = "qwen3:8b"


# 方法功能：从 Console 接收自然语言问题，运行模型与 Tool 的受控循环。
# Debug 入口就是本文件；先在 graph.invoke() 打断点，再进入各个节点。
def main():
    # 本课直接输入问题，由模型提取订单号并选择必要工具。
    question = input("请输入问题（例如：查询 A1002 的退款记录）：")
    # 沿用已有模型配置；这里只读取配置，不创建数据库连接。
    settings = load_settings()
    # 可选使用本机已安装、支持工具调用的模型。
    if USE_OLLAMA:
        # Ollama 提供兼容的本地 Chat Completions 接口。
        settings.llm_base_url = "http://127.0.0.1:11434/v1"
        # 本机模型名称直接从入口常量读取。
        settings.llm_model = OLLAMA_MODEL
        # 兼容客户端需要非空值，本地服务使用这个占位值。
        settings.llm_api_key = "ollama"
        # 本地模型加载可能需要较长时间。
        settings.llm_timeout = 180
    # 创建普通模型对象，此时还没有调用模型。
    model = CompatibleToolModel(settings)
    # 用普通字典集中传入可信预算，不从问题或模型回复获取上限。
    limits = {"max_steps": MAX_STEPS, "max_tool_calls": MAX_TOOL_CALLS, "max_retries": MAX_RETRIES, "enable_timeouts": ENABLE_TIMEOUTS, "model_timeout": MODEL_TIMEOUT, "tool_timeout": TOOL_TIMEOUT, "overall_timeout": OVERALL_TIMEOUT, "max_output_tokens": MAX_OUTPUT_TOKENS, "max_total_tokens": MAX_TOTAL_TOKENS, "max_cost": MAX_COST, "input_price_per_million": INPUT_PRICE_PER_MILLION, "output_price_per_million": OUTPUT_PRICE_PER_MILLION, "currency": COST_CURRENCY}
    # 本地免费模型不套用在线费用单价，Token 和次数上限仍生效。
    if USE_OLLAMA:
        # 免费只是本例预算配置，不代表本机运行没有资源成本。
        limits.update({"input_price_per_million": "0", "output_price_per_million": "0"})
    # 绑定模型、只读数据文件和预算；构图本身不执行它们。
    graph = build_graph(model, DATA_FILE, limits=limits)
    # 创建完整的初始 State，便于在调用前观察各字段。
    initial_state = {
        # 保留完整自然语言问题，交给模型理解。
        "question": question,
        # 租户身份来自入口配置，不来自用户输入。
        "tenant_id": TENANT_ID,
        # prepare 会加入 system 和 user；后面逐轮追加 assistant 和 tool。
        "messages": [],
        # 模型本轮提出的工具调用请求。
        "pending_tool_calls": [],
        # 保存全部已执行工具的结果，不限制为某一种固定查询顺序。
        "tool_results": [],
        # 每次真正尝试调用模型才增加，包括额外重试。
        "model_steps": 0,
        # prepare 会使用建图参数写入可信上限。
        "max_steps": MAX_STEPS,
        # 最终说明自然回答、达到上限或调用异常等退出原因。
        "stop_reason": "",
        # 模型最后的回答或程序的结束说明。
        "answer": "",
    # 结束初始 State 字典定义。
    }
    # 让 Console 明确显示将进入模型请求阶段。
    print(f"开始 Agent 查询，模型：{settings.llm_model}，最多调用 {MAX_STEPS} 次。", flush=True)
    # 显示当前时间开关，默认关闭时断点暂停不会导致超时失败。
    print("超时限制：", "开启" if ENABLE_TIMEOUTS else "关闭（可逐步 Debug）", flush=True)
    # 在这一行打断点；prepare 会补齐预算、重试和用量，关闭超时时 deadline 为 None。
    result = graph.invoke(initial_state)
    # 显示本次查询使用的可信租户。
    print("当前租户：", result["tenant_id"])
    # 模型生成最终回答也会占用一次决策次数。
    print("模型调用次数：", result["model_steps"], "/", result["max_steps"])
    # 同批多工具和重试均计入 Tool 上限。
    print("Tool 尝试次数：", result["tool_calls"], "/", result["limits"]["max_tool_calls"])
    # 恢复成功也能看到实际发生过多少次重试。
    print("重试次数：模型", result["model_retries"], "，Tool", result["tool_retries"])
    # 未知用量使用保守预留，具体来源可查看下方 usage_history。
    print("累计 Token：", result["total_tokens"], "/", result["limits"]["max_total_tokens"])
    # 强调这是按入口演示单价计算的估算，不是 DeepSeek 账单。
    print("估算费用：", result["estimated_cost"], result["limits"]["currency"], "；预算：", result["limits"]["max_cost"], "；请核对单价。")
    # 实际总耗时包含等待与断点暂停。
    print("总耗时（秒）：", round(result["elapsed_seconds"], 3))
    # 区分正常回答、达到上限与模型异常。
    print("结束原因：", result["stop_reason"])
    # 展示最终回答；中间消息不当作最终答案。
    print("输出：", result["answer"])
    # 保留每轮调用名称、参数、调用 ID 和完整业务结果，方便 Debug 对照。
    print("已保留的 Tool 结果：", json.dumps(result["tool_results"], ensure_ascii=False, indent=2))
    # 每次请求的真实 usage 或预留估算来源都可逐条对照。
    print("模型用量记录：", json.dumps(result["usage_history"], ensure_ascii=False, indent=2))
    # 事件不包含原始异常正文、配置对象或密钥。
    print("恢复事件：", json.dumps(result["events"], ensure_ascii=False, indent=2))


# 在 IDE 点击 Run / Debug，或直接运行本文件时才调用 main()。
if __name__ == "__main__":
    # 用户运行本入口时会实际访问所配置的模型，业务数据仍来自本地 JSON。
    main()
