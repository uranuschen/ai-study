import sys
from pathlib import Path


# 当前文件所在目录是项目根目录。
BASE_DIR = Path(__file__).resolve().parent
# 直接点击 Run / Debug 时，让 Python 找到 src 下的代码。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.workflows.conditional_route import build_graph


# 方法功能：从 Console 读取一句话，按条件执行普通问答或本地 Tool 分支。
# 可以在 graph.invoke()、choose_route() 或 tool_node() 处打断点查看 State。
def main():
    # 创建 START → prepare → 条件路由 → 一个分支 → END 工作流。
    graph = build_graph()
    # 输入普通问题，或输入以“统计字数：”开头的 Tool 指令。
    question = input("请输入问题或“统计字数：文字”：")
    # 全空白输入没有可处理的内容，直接提示并结束。
    if not question.strip():
        # 在 Console 显示输入要求。
        print("请输入非空内容。")
        # 结束本次运行。
        return
    # invoke 的字典是初始 State；其余字段由准备节点和选中的分支写入。
    result = graph.invoke({"question": question, "clean_question": "", "branch": "", "answer": ""})
    # 显示准备节点写入 State 的结果。
    print("整理后的问题：", result["clean_question"])
    # 显示条件路由最终选择的分支。
    print("执行分支：", result["branch"])
    # 显示被选中节点生成的回答。
    print("输出：", result["answer"])


# 在 IDE 点击 Run / Debug，或直接运行本文件时才调用 main()。
if __name__ == "__main__":
    # 启动条件路由的 Console 演示。
    main()
