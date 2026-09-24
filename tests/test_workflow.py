import unittest

from agent_learning.workflows.single_node import build_graph
from agent_learning.workflows.state_flow import build_graph as build_state_flow


# 类职责：用真实 LangGraph 执行一次离线调用，验证 State 能经过节点并返回。
class SingleNodeWorkflowTests(unittest.TestCase):
    # 方法功能：验证单节点把输入问题写成可在 Console 显示的结果。
    def test_one_node_passes_state_to_output(self):
        # 创建图，确认测试走实际的 START → echo → END 连线。
        graph = build_graph()
        # 给图一个初始 State，不连接数据库或模型。
        result = graph.invoke({"question": "测试问题", "answer": ""})
        # 节点保留原问题并填入回答。
        self.assertEqual(result, {"question": "测试问题", "answer": "单节点收到：测试问题"})


# 类职责：验证第一个节点写入的 State 能被第二个节点读取。
class StateFlowTests(unittest.TestCase):
    # 方法功能：从完整图运行，检查原文、整理结果和最终输出。
    def test_second_node_reads_first_node_update(self):
        # 创建真实的两节点 LangGraph 图。
        graph = build_state_flow()
        # 保留原文中的空格，用于判断第一个节点确实写入了新字段。
        result = graph.invoke({"question": "  测试问题  ", "clean_question": "", "answer": ""})
        # 原始输入保持不变。
        self.assertEqual(result["question"], "  测试问题  ")
        # 第一个节点去掉首尾空格并写入 State。
        self.assertEqual(result["clean_question"], "测试问题")
        # 第二个节点读取第一个节点的结果，不沿用原始空格。
        self.assertEqual(result["answer"], "第二个节点收到：测试问题")


# 允许单独运行这个离线测试文件。
if __name__ == "__main__":
    # 使用项目现有的标准库测试框架。
    unittest.main()
