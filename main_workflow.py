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
# 导入第 62 课 Agent 循环；上一课 order_flow.py 保留作对照。
from agent_learning.workflows.agent_loop import build_graph
# 导入支持 Tool Calling 的普通模型类。
from agent_learning.workflows.tool_model import CompatibleToolModel


# 业务 Tool 继续读取本地 JSON 模拟数据。
DATA_FILE = BASE_DIR / "data" / "business_demo.json"
# 租户来自可信入口；改为 other 可对照同号订单的隔离效果。
TENANT_ID = "acme"
# 最多调用模型 5 次，最后生成回答的那次也计入；不是 Tool 条数。
MAX_STEPS = 5
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
    # 将模型、数据文件和最大调用次数绑定到工作流。
    graph = build_graph(model, DATA_FILE, max_steps=MAX_STEPS)
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
        # 每进入一次模型节点，这个值增加 1。
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
    # 在这一行打断点；model 与 tools 按条件边循环，直到 finish → END。
    result = graph.invoke(initial_state)
    # 显示本次查询使用的可信租户。
    print("当前租户：", result["tenant_id"])
    # 模型生成最终回答也会占用一次决策次数。
    print("模型调用次数：", result["model_steps"], "/", result["max_steps"])
    # 区分正常回答、达到上限与模型异常。
    print("结束原因：", result["stop_reason"])
    # 展示最终回答；中间消息不当作最终答案。
    print("输出：", result["answer"])
    # 保留每轮调用名称、参数、调用 ID 和完整业务结果，方便 Debug 对照。
    print("已保留的 Tool 结果：", json.dumps(result["tool_results"], ensure_ascii=False, indent=2))


# 在 IDE 点击 Run / Debug，或直接运行本文件时才调用 main()。
if __name__ == "__main__":
    # 用户运行本入口时会实际访问所配置的模型，业务数据仍来自本地 JSON。
    main()
