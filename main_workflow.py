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

# 导入第 61 课多步订单工作流；第 60 课 business_tool.py 保留作对照。
from agent_learning.workflows.order_flow import build_graph


# 参数在这个入口直接修改；本课数据完全来自本地 JSON。
DATA_FILE = BASE_DIR / "data" / "business_demo.json"
# 租户来自可信入口；改为 other 可对照同号订单的隔离效果。
TENANT_ID = "acme"


# 方法功能：从 Console 读取订单号，按业务结果查询订单、支付、退款并总结。
# Debug 入口就是本文件；先在 graph.invoke() 打断点，再进入各个节点。
def main():
    # 先创建图；此时只绑定文件路径，还没有查询任何业务数据。
    graph = build_graph(DATA_FILE)
    # 本课直接输入订单号，先观察参数如何从 State 进入 Tool。
    question = input("请输入订单号（A1001 未支付 / A1002 有退款 / A1003 无退款 / A1004 无支付记录 / A1005 支付失败）：")
    # 创建完整的初始 State，便于在调用前观察各字段。
    initial_state = {
        # 保留 Console 原始输入，之后由 prepare 整理。
        "question": question,
        # 租户身份来自入口配置，不来自用户输入。
        "tenant_id": TENANT_ID,
        # 订单号由 prepare 节点写入。
        "order_id": "",
        # 单独保留订单结果，不被后续节点覆盖。
        "order_result": {},
        # {} 表示没有查询，成功的 data=[] 才表示查过但没有记录。
        "payment_result": {},
        # 单独保留退款结果，提前结束时仍然是 {}。
        "refund_result": {},
        # 只记录实际调用的 Tool，用来观察哪些查询被跳过。
        "executed_tools": [],
        # 业务结束分支由总结节点写入。
        "branch": "",
        # 最终回答由总结节点写入。
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
    print("实际调用 Tool：", " → ".join(result["executed_tools"]))
    # 展示订单结果，确认后续查询没有覆盖它。
    print("订单 Tool 返回：", json.dumps(result["order_result"], ensure_ascii=False, indent=2))
    # 展示支付结果，包括提前结束时的 {}。
    print("支付 Tool 返回：", json.dumps(result["payment_result"], ensure_ascii=False, indent=2))
    # 展示退款结果，区别 {}、成功空列表和失败信息。
    print("退款 Tool 返回：", json.dumps(result["refund_result"], ensure_ascii=False, indent=2))
    # 显示最后选择的业务结束原因。
    print("执行分支：", result["branch"])
    # 显示最后一个节点生成的回答。
    print("输出：", result["answer"])


# 在 IDE 点击 Run / Debug，或直接运行本文件时才调用 main()。
if __name__ == "__main__":
    # 启动第 61 课离线多步订单演示。
    main()
