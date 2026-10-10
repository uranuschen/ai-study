import json
import sys
from pathlib import Path
from langgraph.checkpoint.memory import InMemorySaver


# 当前文件所在目录是项目根目录。
BASE_DIR = Path(__file__).resolve().parent
# IDE 直接 Run / Debug 时也可以找到 src 包。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.cli import build_pipeline
from agent_learning.core.config import load_settings
from agent_learning.core.models import SearchFilter
from agent_learning.workflows.checkpoint_agent import build_graph
from agent_learning.workflows.tool_model import CompatibleToolModel


# 订单、支付、退款继续读取本地 JSON。
DATA_FILE = BASE_DIR / "data" / "business_demo.json"
# 业务 Tool 与 RAG 使用同一个入口租户。
TENANT_ID = "acme"
# 知识库可读级别由程序提供，不交给模型选择。
SECURITY_LEVEL = 1
# 本课先查制度；可改为 process 或 faq，不查询 record 订单快照。
DOC_TYPE = "policy"
# 这是逻辑会话编号，不是系统线程；不同编号保存各自的 State。
THREAD_ID = "lesson-65-order"
# False 使用已有在线配置；True 使用本机已有的 Ollama 模型。
USE_OLLAMA = False
# 程序不会下载这个模型，需要本机已经安装。
OLLAMA_MODEL = "qwen3:8b"


#-- 复用的--
# 方法功能：第 65 课原入口，保留内存存档、暂停和失败后手动继续。
# Debug 从 graph.invoke() 和 graph.get_state() 开始，查看 State 与待执行节点。
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
    # Checkpoint 只保存在内存，不用数据库存档，退出程序后消失。
    checkpointer = InMemorySaver()
    # 绑定上一课的业务逻辑，并在每次执行 tools 之前暂停。
    graph = build_graph(model, pipeline, filters, checkpointer, data_file=DATA_FILE)
    # 每次执行和恢复都使用同一个会话编号。
    config = {"configurable": {"thread_id": THREAD_ID}}
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
    # 只有第一次传入初始数据；后续恢复传 None，不重置 State。
    next_input = initial_state
    # 让 Console 显示本次模型和逻辑会话。
    print(f"开始 Agent 查询，模型：{settings.llm_model}，thread_id：{THREAD_ID}。内存存档仅本次进程有效。", flush=True)
    # 每次暂停或失败后都等待用户决定，不自动重试。
    while True:
        # 区分正常结束和没有可恢复节点的异常。
        failed = False
        # 异常交给 LangGraph 记录待执行节点，入口不输出异常中的连接信息。
        try:
            # 首次执行 prepare → model；传 None 时从该会话的待执行节点继续。
            graph.invoke(next_input, config=config)
        # Debug 可查看 error；继续前先确认异常原因已处理。
        except Exception as error:
            # 异常不代表图已正常完成。
            failed = True
            # 恢复是重新执行失败节点，不是从出错的那一行继续。
            print("节点执行失败，请先在 Debug 中检查异常原因；继续会重新执行失败节点，可能重复请求模型。")
        # 读取已保存的 State 和下一节点；读取本身不执行图。
        snapshot = graph.get_state(config)
        # 没有存档，或者异常后没有待执行节点，都不能当成正常 END。
        if not snapshot.values or (failed and not snapshot.next):
            # 本课不自动重新传入初始数据，避免把失败变成整轮重跑。
            print("没有可继续的 Checkpoint，请在 Debug 中检查；本次退出，不自动重新开始。")
            # 不读取不存在的最终答案。
            return
        # 没有待执行节点就是 END，不是暂停。
        if not snapshot.next:
            # 最终答案与原始 Tool 结果都从已保存的 State 读取。
            result = snapshot.values
            # 结束入口的恢复循环。
            break
        # tools 表示 Tool 前暂停；model 通常表示模型异常后等待继续。
        print("待执行节点：", snapshot.next)
        # 查看模型已选的工具；暂停时它们还没有执行。
        print("待执行 Tool：", json.dumps(snapshot.values["pending_tool_calls"], ensure_ascii=False, indent=2))
        # 已完成的工具结果保存在 State 中，失败恢复不会重跑已成功的前序节点。
        print("已保存 Tool 结果：", json.dumps(snapshot.values["tool_results"], ensure_ascii=False, indent=2))
        # 回车只表示教学继续执行；这里不是敏感业务操作审批。
        action = input("回车继续，输入 q 退出（退出后内存存档消失）：").strip().lower()
        # 用户退出就停止本次演示。
        if action == "q":
            # 明确提示当前使用的不是磁盘存档。
            print("已退出；本次内存 Checkpoint 不会在下次启动时恢复。")
            # 不再执行任何待执行节点。
            return
        # 静态断点与失败恢复都传 None，不再次传 initial_state。
        next_input = None
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
