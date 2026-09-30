import json
import sys
from pathlib import Path


# 当前文件所在目录是项目根目录。
BASE_DIR = Path(__file__).resolve().parent
# IDE 直接 Run / Debug 时也可以找到 src 包。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.cli import build_pipeline
from agent_learning.core.config import load_settings
from agent_learning.core.models import SearchFilter
from agent_learning.workflows.rag_agent import build_graph
from agent_learning.workflows.tool_model import CompatibleToolModel


# 订单、支付、退款继续读取本地 JSON。
DATA_FILE = BASE_DIR / "data" / "business_demo.json"
# 业务 Tool 与 RAG 使用同一个入口租户。
TENANT_ID = "acme"
# 知识库可读级别由程序提供，不交给模型选择。
SECURITY_LEVEL = 1
# 本课先查制度；可改为 process 或 faq，不查询 record 订单快照。
DOC_TYPE = "policy"
# False 使用已有在线配置；True 使用本机已有的 Ollama 模型。
USE_OLLAMA = False
# 程序不会下载这个模型，需要本机已经安装。
OLLAMA_MODEL = "qwen3:8b"


# 方法功能：只准备模型、RAG 和工具循环，不加入计数、预算或重试代码。
# Debug 从 graph.invoke() 开始，再进入 model_node 和 tools_node。
def main():
    # 让模型按问题分别查询业务事实和知识库规则。
    question = input("请输入问题（例如：A1002 的退款状态是什么，按规定通常多久到账？）：")
    # 用户运行时才读取已有配置，测试会替换这个函数。
    settings = load_settings()
    # 本课保持 Debug 无客户端超时，外层 Agent 和内层 RAG 共用这个配置。
    settings.llm_timeout = None
    # 只使用本地已有的向量与精排模型，缺少文件时不自动下载。
    settings.local_files_only = True
    # 可选使用本机已有模型，外层选择工具、内层 RAG 回答都使用它。
    if USE_OLLAMA:
        # 使用兼容的本地模型接口。
        settings.llm_base_url = "http://127.0.0.1:11434/v1"
        # 模型名称从入口常量读取。
        settings.llm_model = OLLAMA_MODEL
        # 本地兼容接口只需要非空占位值。
        settings.llm_api_key = "ollama"
    # 创建外层模型对象，由它选择工具和综合回答。
    model = CompatibleToolModel(settings)
    # 复用 main_ask.py 使用的 RAG 创建函数，不重写检索流程。
    pipeline = build_pipeline(settings)
    # 查询身份、权限和资料类型来自入口，不接受模型提供的值。
    filters = SearchFilter(tenant_id=TENANT_ID, max_security_level=SECURITY_LEVEL, doc_type=DOC_TYPE)
    # 绑定模型、已有 RAG、可信过滤条件和 JSON 文件。
    graph = build_graph(model, pipeline, filters, data_file=DATA_FILE)
    # State 只保留本课核心字段。
    initial_state = {
        # 用户原始问题交给外层模型。
        "question": question,
        # 与知识库过滤条件使用同一个可信租户。
        "tenant_id": TENANT_ID,
        # prepare 会放入 system 和 user 消息。
        "messages": [],
        # 模型请求工具后再填入。
        "pending_tool_calls": [],
        # 业务结果和 RAG 原始答案、引用都保存在这里。
        "tool_results": [],
        # 模型自然回答或查询失败时由程序设置。
        "stop_reason": "",
        # 最终回答或者失败说明。
        "answer": "",
    # 结束初始 State。
    }
    # 让 Console 显示将进入实际模型请求。
    print(f"开始 Agent 查询，模型：{settings.llm_model}，知识库资料类型：{DOC_TYPE}。", flush=True)
    # Debug 在这一行打断点，随后进入 prepare → model → tools。
    result = graph.invoke(initial_state)
    # 展示外层模型的综合回答。
    print("输出：", result["answer"])
    # 仅显示结束原因，不加入日志和预算统计。
    print("结束原因：", result["stop_reason"])
    # 原始 Tool 结果包含业务 updated_at 和 RAG 引用，不让外层模型重新生成来源。
    print("原始 Tool 结果与来源（引用编号按 tool_call_id 分组）：", json.dumps(result["tool_results"], ensure_ascii=False, indent=2))


# 直接点击 IDE 的 Run / Debug 才运行主流程。
if __name__ == "__main__":
    # 实际运行会请求模型；模型选择 RAG 时会只读检索现有知识库。
    main()
