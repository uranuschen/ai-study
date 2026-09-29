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

# 导入第 60 课工作流；前几课的文件保留，可继续打开对照。
from agent_learning.workflows.business_tool import build_graph


# 参数在这个入口直接修改；本课数据完全来自本地 JSON。
DATA_FILE = BASE_DIR / "data" / "business_demo.json"
# 租户来自可信入口；改为 other 可对照同号订单的隔离效果。
TENANT_ID = "acme"


# 方法功能：从 Console 读取订单号，通过工作流调用 get_order 并显示结果。
# Debug 入口就是本文件；先在 graph.invoke() 打断点，再进入各个节点。
def main():
    # 先创建图；此时只绑定文件路径，还没有查询任何业务数据。
    graph = build_graph(DATA_FILE)
    # 本课直接输入订单号，先观察参数如何从 State 进入 Tool。
    question = input("请输入订单号（A1001 / A1002 / A1003）：")
    # 创建完整的初始 State，便于在调用前观察各字段。
    initial_state = {
        # 保留 Console 原始输入，之后由 prepare 整理。
        "question": question,
        # 租户身份来自入口配置，不来自用户输入。
        "tenant_id": TENANT_ID,
        # 订单号由 prepare 节点写入。
        "order_id": "",
        # Tool 名称由 get_order 节点写入。
        "tool_name": "",
        # 业务结果由 get_order 节点写入。
        "tool_result": {},
        # 分支标签由选中的回答节点写入。
        "branch": "",
        # 最终回答由选中的回答节点写入。
        "answer": "",
    # 结束初始 State 字典定义。
    }
    # 在这一行打断点；invoke 按图的连线执行节点并合并 State。
    result = graph.invoke(initial_state)
    # 显示本次查询使用的可信租户。
    print("当前租户：", result["tenant_id"])
    # 显示 prepare 节点整理后的 Tool 参数。
    print("整理后的订单号：", result["order_id"])
    # 显示真正调用的业务函数名称。
    print("调用 Tool：", result["tool_name"])
    # 展示 success、data 和 error，便于与路由函数对照。
    print("Tool 返回：", json.dumps(result["tool_result"], ensure_ascii=False, indent=2))
    # 显示 Tool 结果最终选择的成功或失败分支。
    print("执行分支：", result["branch"])
    # 显示最后一个节点生成的回答。
    print("输出：", result["answer"])


# 在 IDE 点击 Run / Debug，或直接运行本文件时才调用 main()。
if __name__ == "__main__":
    # 启动第 60 课离线订单 Tool 演示。
    main()
