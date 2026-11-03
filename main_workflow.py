import json
import sys
from pathlib import Path


# 保留一个简短 Console 入口，和 API 共用同一套 Service。
BASE_DIR = Path(__file__).resolve().parent
# 根目录可直接运行。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.bootstrap import build_services
from agent_learning.services.agent_service import AgentService


# Console 只展示业务回答与审批，不输出执行统计。
def main():
    # 构造对象不会主动查询数据库或请求模型。
    service: AgentService = build_services()["agent"]
    # 创建默认会话。
    session_id = service.create_session()["session_id"]
    # 持续接收同会话的问题。
    while True:
        # 保留原来的新会话和退出操作。
        question = input("请输入问题，/new 新会话，q 退出：").strip()
        # 用户退出后不再发送请求。
        if question.lower() == "q":
            # 结束 Console。
            return
        # 新会话不会删除旧存档。
        if question.lower() == "/new":
            # 只切换当前会话编号。
            session_id = service.create_session()["session_id"]
            # 下一次输入再提问。
            continue
        # 空问题不调用模型。
        if not question:
            # 等待下一次输入。
            continue
        # 执行与 API 相同的提问流程。
        result = service.ask(session_id, question)
        # 每个敏感请求单独确认。
        while result["status"] == "waiting_approval":
            # 只展示人工需要确认的目标。
            print(json.dumps(result["approval"], ensure_ascii=False))
            # 人工必须明确批准或拒绝。
            choice = input("approve 确认，reject 拒绝，q 退出：").strip().lower()
            # 退出不会执行待审批操作。
            if choice == "q":
                # 内存会话随进程结束。
                return
            # 无效决定继续等待。
            if choice not in ("approve", "reject"):
                # 不默认批准。
                continue
            # 提交当前审批编号绑定的决定。
            result = service.approve(session_id, result["approval"]["approval_id"], choice)
        # 这里只输出业务回答。
        print(result["answer"])
        # 有知识库来源时展示原始引用。
        if result["citations"]:
            # 不附带 Token、费用、节点或耗时。
            print(json.dumps(result["citations"], ensure_ascii=False, indent=2))


# 用户显式运行时才进入 Console。
if __name__ == "__main__":
    # 正式 API 入口是 main_api.py。
    main()
