import sys
from pathlib import Path


# 当前文件所在目录是项目根目录。
BASE_DIR = Path(__file__).resolve().parent
# 直接点击 Run / Debug 时，让 Python 找到 src 下的代码。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.workflows.state_flow import build_graph


# 方法功能：从 Console 读取一句话，执行两个节点并显示 State 传值结果。
# 可以在 graph.invoke()、prepare_node() 或 answer_node() 处打断点查看 State。
def main():
    # 创建固定的 START → prepare → answer → END 工作流。
    graph = build_graph()
    # 从终端读取原始文字，留给第一个节点去除首尾空格。
    question = input("请输入一句话：")
    # 全空白输入没有可处理的内容，直接提示并结束。
    if not question.strip():
        # 在 Console 显示输入要求。
        print("请输入非空内容。")
        # 结束本次运行。
        return
    # invoke 的字典是初始 State；后两个字段先留空，分别由两个节点写入。
    result = graph.invoke({"question": question, "clean_question": "", "answer": ""})
    # 显示第一个节点写入 State 的结果。
    print("第一个节点写入 State：", result["clean_question"])
    # 显示第二个节点读取 State 后生成的结果。
    print("第二个节点输出：", result["answer"])


# 在 IDE 点击 Run / Debug，或直接运行本文件时才调用 main()。
if __name__ == "__main__":
    # 启动两个节点传递 State 的 Console 演示。
    main()
