import unittest
from unittest.mock import patch

from agent_learning.workflows.conditional_route import build_graph as build_conditional_route
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


# 类职责：通过真实 LangGraph 图验证两个分支互斥，且 Tool 只在需要时调用。
class ConditionalRouteTests(unittest.TestCase):
    # 方法功能：普通问题只经过普通分支，不调用统计 Tool。
    def test_normal_question_skips_tool(self):
        # 创建本课的条件路由图。
        graph = build_conditional_route()
        # 给 Tool 打桩，以便检查普通分支不会误调用它。
        with patch("agent_learning.workflows.conditional_route.count_characters") as tool:
            # 从初始 State 执行完整工作流。
            result = graph.invoke({"question": "  你好  ", "clean_question": "", "branch": "", "answer": ""})
        # prepare 节点先整理问题，普通分支再生成演示输出。
        self.assertEqual(result["clean_question"], "你好")
        # 记录普通分支确实被选中。
        self.assertEqual(result["branch"], "normal")
        # 回显输出表明执行了普通节点。
        self.assertEqual(result["answer"], "普通问答分支收到：你好")
        # 普通分支不应调用统计 Tool。
        tool.assert_not_called()

    # 方法功能：带指定前缀的问题只走 Tool 分支，并统计前缀后的文字。
    def test_prefixed_question_calls_tool(self):
        # 创建本课的条件路由图。
        graph = build_conditional_route()
        # 固定 Tool 返回值，明确检查它收到的文字。
        with patch("agent_learning.workflows.conditional_route.count_characters", return_value=4) as tool:
            # 前后空格应先由 prepare 节点处理，然后才能判断前缀。
            result = graph.invoke({"question": "  统计字数：人工智能  ", "clean_question": "", "branch": "", "answer": ""})
        # 保留整理后的问题，便于在 State 中检查。
        self.assertEqual(result["clean_question"], "统计字数：人工智能")
        # 记录 Tool 分支确实被选中。
        self.assertEqual(result["branch"], "tool")
        # Tool 返回值进入最终输出。
        self.assertEqual(result["answer"], "Tool 统计结果：人工智能，共 4 个字符。")
        # 只传待统计的正文，不把指令前缀送给 Tool。
        tool.assert_called_once_with("人工智能")


# 允许单独运行这个离线测试文件。
if __name__ == "__main__":
    # 使用项目现有的标准库测试框架。
    unittest.main()
