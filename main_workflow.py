import json
import sys
from pathlib import Path
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command


# 当前文件所在目录是项目根目录。
BASE_DIR = Path(__file__).resolve().parent
# IDE 直接 Run / Debug 时也可以找到 src 包。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.cli import build_pipeline
from agent_learning.core.config import load_settings
from agent_learning.core.models import SearchFilter
from agent_learning.workflows.human_approval_agent import build_graph
from agent_learning.workflows.tool_model import CompatibleToolModel


# 业务 Tool 仍只读本地订单、支付和退款 JSON。
DATA_FILE = BASE_DIR / "data" / "business_demo.json"
# 业务查询与知识库始终使用同一个可信租户。
TENANT_ID = "acme"
# 查询权限仍由入口提供，不交给模型选择。
SECURITY_LEVEL = 1
# 默认只查规则资料；也可以使用 process 或 faq。
DOC_TYPE = "policy"
#（67课调整）审批恢复仍使用同一个会话编号；/new 只能在一轮结束后使用。
THREAD_ID = "lesson-67-order"
# 最多保留两个旧问答轮次，另外始终保留当前轮与 system。
MAX_HISTORY_TURNS = 2
# 以 messages + Tool schemas 的 JSON 字符数控制输入，不是精确 Token 上限。
MAX_CONTEXT_CHARS = 12000
# False 使用已有在线配置；True 使用本机已有的 Ollama 模型。
USE_OLLAMA = False
# 程序不下载模型，需要本机已经安装。
OLLAMA_MODEL = "qwen3:8b"


#（67课新加）只在动态暂停时询问人工决定；不允许在待审批状态提交新问题。
def resume_approvals(graph: CompiledStateGraph, result: dict, config: dict) -> dict | None:
    #（67课新加）一个批次可能有多个敏感请求，逐个审批，不一次批准全部工具。
    while result.get("__interrupt__"):
        #（67课新加）这里是实际工具请求生成的审批参数，不是从用户回复重新提取目标。
        request = result["__interrupt__"][0].value
        #（67课新加）先展示将要模拟的操作、订单、租户和调用 ID。
        print("等待人工审批：", json.dumps(request, ensure_ascii=False, indent=2))
        #（67课新加）不接受模糊输入；无效输入继续等待，不默认批准。
        while True:
            #（67课新加）y/approve 确认，n/reject 拒绝，q 退出但不执行取消。
            choice = input("模拟取消：y/approve 确认，n/reject 拒绝，q 退出：").strip().lower()
            #（67课新加）退出时保留当前进程的暂停状态，不自动恢复。
            if choice == "q":
                #（67课新加）告知用户没有执行该操作；进程退出后内存存档会丢失。
                print("已退出，待审批操作未执行；内存存档不会跨进程保留。")
                #（67课新加）用 None 告知 main 停止交互。
                return None
            #（67课新加）只有这四个明确输入可以产生审批决定。
            if choice in ("y", "approve", "n", "reject"):
                #（67课新加）离开输入循环，继续构造审批响应。
                break
            #（67课新加）包括空输入和 /new 在内，都不能绕过当前审批。
            print("请输入 y/approve 或 n/reject；待审批时不能切换会话或提交新问题。")
        #（67课新加）保留本次所有目标字段，人工输入只决定确认或拒绝。
        decision = {**request, "decision": "approve" if choice in ("y", "approve") else "reject"}
        #（67课新加）与第 65 课不同：动态 interrupt 要用 Command 传回决定，不能用 None 代替审批。
        result = graph.invoke(Command(resume=decision), config=config)
    #（67课新加）没有待审批请求时，返回本轮最终结果。
    return result


#（67课调整）保留会话与 RAG 初始化，在原模型工具循环中加入人工审批。
def main():
    # 只有用户运行入口时才读取真实配置。
    settings = load_settings()
    # 保留 Debug 无客户端超时，外层 Agent 与内层 RAG 共用配置。
    settings.llm_timeout = None
    # 只使用本地已有的向量与精排模型，不自动下载。
    settings.local_files_only = True
    # 沿用本机已有模型的可选开关。
    if USE_OLLAMA:
        # 使用本地 OpenAI 兼容接口。
        settings.llm_base_url = "http://127.0.0.1:11434/v1"
        # 读取入口指定的模型名称。
        settings.llm_model = OLLAMA_MODEL
        # 本地兼容接口使用非空占位值。
        settings.llm_api_key = "ollama"
    # 创建原来的模型客户端，不重写 Tool Calling 协议。
    model = CompatibleToolModel(settings)
    # 创建原来的 RAG 管道，不改检索、精排与引用校验。
    pipeline = build_pipeline(settings)
    # 租户、权限与资料类型仍由可信入口固定。
    filters = SearchFilter(tenant_id=TENANT_ID, max_security_level=SECURITY_LEVEL, doc_type=DOC_TYPE)
    # 所有问答共用这个内存存档器，不能放进提问循环重新创建。
    checkpointer = InMemorySaver()
    #（67课调整）只建图一次，取消请求进入审批分支，普通业务查询与 RAG 不暂停。
    graph = build_graph(model, pipeline, filters, checkpointer, data_file=DATA_FILE, max_history_turns=MAX_HISTORY_TURNS, max_context_chars=MAX_CONTEXT_CHARS)
    # 固定配置结构，通过 thread_id 找到本会话 State。
    config = {"configurable": {"thread_id": THREAD_ID}}
    # 新会话只换编号，不删除已经存在的存档。
    session_number = 1
    #（67课调整）展示示例和审批规则；所有取消仅模拟，不写业务 JSON。
    print("第 67 课：可输入‘请取消订单 A1001’练习审批；仅模拟取消待支付订单。/new 新会话，q 退出。")
    # 多轮问答共用模型、管道、图和存档器。
    while True:
        #（67课调整）普通查询沿用之前的流程；取消 A1001 时才等待人工确认。
        question = input(f"[{config['configurable']['thread_id']}] 请输入问题：").strip()
        # 退出后当前进程中的内存存档不再保留。
        if question.lower() == "q":
            # 不再调用图或模型。
            return
        # 切换新编号会从没有历史的会话开始。
        if question.lower() == "/new":
            # 每次生成当前进程内不同的新编号。
            session_number += 1
            # 只换会话配置，不重建图和存档器。
            config = {"configurable": {"thread_id": f"{THREAD_ID}-{session_number}"}}
            # 告知用户此后的问题不会带上旧会话消息。
            print("已切换新会话：", config["configurable"]["thread_id"])
            # 下一次输入再提交问题。
            continue
        # 空输入不进入图，也不清空已经保留的消息。
        if not question:
            # 提示后允许继续追问。
            print("请输入非空问题。")
            # 不请求模型。
            continue
        # 新问题开始时清空显示用的上次 usage，避免误报旧 Token 数。
        model.last_usage = {}
        #（67课调整）首次调用与审批恢复统一处理异常，不输出凭证或自动重试。
        try:
            # 只更新问题与可信身份；不能传 messages=[]，否则会覆盖会话历史。
            result = graph.invoke({"question": question, "tenant_id": TENANT_ID}, config=config)
            #（67课新加）有 interrupt 就等待人工决定；普通查询直接返回结果。
            result = resume_approvals(graph, result, config)
        # Debug 可查看 error，不输出异常中的连接信息或密钥。
        except Exception as error:
            # 本课不自动重试，也不在未完成节点上强行提交新问题。
            print("图执行失败，请在 Debug 中检查；本次退出，不自动重试。")
            # 停止当前入口。
            return
        #（67课新加）审批时输入 q，直接退出，不提交新问题覆盖暂停状态。
        if result is None:
            #（67课新加）没有执行待审批操作。
            return
        # 输出本轮综合回答。
        print("输出：", result["answer"])
        # 预算不足或模型错误也会受控结束，不继续死循环。
        print("结束原因：", result["stop_reason"])
        #（67课新加）这份列表是同会话的模拟记录，不是 JSON 中的真实取消状态。
        print("本会话已模拟取消：", result["simulated_cancellations"])
        # 观察多轮追加和裁剪后的消息数量。
        print("当前会话消息数：", len(result["messages"]))
        # 接口未提供 usage 时显示不可用，不能把未知值当成零。
        print("最后一次外层调用输入 Token（接口 usage，不含 RAG 内层）：", model.last_usage.get("prompt_tokens", "未返回"))
        # 本轮 Tool 结果与来源仍按工具调用分组，旧轮消息保留在 messages。
        print("本轮 Tool 结果与来源：", json.dumps(result["tool_results"], ensure_ascii=False, indent=2))


# IDE 点击 Run / Debug 时才启动真实交互。
if __name__ == "__main__":
    # 用户运行会请求模型；模型选择 RAG 时才查询现有知识库。
    main()
