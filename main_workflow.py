import sys
from pathlib import Path


# 当前文件所在目录是项目根目录。
BASE_DIR = Path(__file__).resolve().parent
# 直接点击 Run / Debug 时，让 Python 找到 src 下的代码。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.workflows.single_node import build_graph


# 方法功能：从 Console 读取一句话，执行一次单节点工作流并输出结果。
# 可以在 graph.invoke() 或 echo_node() 处打断点查看 State。
def main():
    # 先创建固定的 START → echo → END 工作流。
    graph = build_graph()
    # 从终端读取一条输入；这个输入就是本次工作流的 question。
    question = input("请输入一句话：").strip()
    # 空输入没有可处理的内容，直接提示并结束。
    if not question:
        # 在 Console 显示输入要求。
        print("请输入非空内容。")
        # 结束本次运行。
        return
    # invoke 是 LangGraph 的执行入口，字典是工作流的初始 State。
    result = graph.invoke({"question": question, "answer": ""})
    # 读取节点写回的 answer，显示在 Console。
    print(result["answer"])


# 在 IDE 点击 Run / Debug，或直接运行本文件时才调用 main()。
if __name__ == "__main__":
    # 启动单节点 Console 演示。
    main()
