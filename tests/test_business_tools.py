# 使用标准库把合成订单写成真实 JSON 文件。
import json
# 使用标准库创建独立临时文件，保留文件以避免删除目录。
import tempfile
# 使用标准库运行离线单元测试。
import unittest
# 使用函数替身模拟业务 Tool 的未预期异常。
from unittest.mock import patch
# 使用路径对象传入本地业务数据文件。
from pathlib import Path

# 导入本课独立业务函数，测试不连接数据库或模型。
from agent_learning.business.tools import DEFAULT_DATA_FILE, get_order, tool_result
# 导入真实 LangGraph 构图函数，验证完整分支执行。
from agent_learning.workflows.business_tool import build_graph


# 方法功能：创建真实临时 JSON 文件供业务函数读取，不修改项目样例。
def create_data_file(content: str) -> Path:
    # 临时文件放在系统临时目录，关闭后保留文件。
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as file:
        # 写入测试需要的正常或损坏内容。
        file.write(content)
        # 保存临时文件路径，供调用方读取。
        data_file = Path(file.name)
    # 文件已经关闭，业务函数可以独立打开并读取。
    return data_file


# 类职责：通过真实 JSON 读取验证订单查询、租户隔离和失败返回。
class BusinessToolTests(unittest.TestCase):
    # 方法功能：准备有相同订单号和租户独有订单的离线数据。
    def setUp(self):
        # 两个租户拥有相同订单号，第三条记录只属于 other 租户。
        orders = [
            # acme 租户拥有已支付订单，金额保留原始字符串。
            {"order_id": "A1002", "tenant_id": "acme", "status": "已支付", "amount": "299.00", "currency": "CNY", "updated_at": "2026-09-28T08:00:00+08:00"},
            # other 租户的同号订单状态与金额不同。
            {"order_id": "A1002", "tenant_id": "other", "status": "已取消", "amount": "79.00", "currency": "CNY", "updated_at": "2026-09-28T08:00:00+08:00"},
            # 只有 other 租户能读取这个独有订单。
            {"order_id": "B9001", "tenant_id": "other", "status": "待支付", "amount": "19.90", "currency": "CNY", "updated_at": "2026-09-28T08:00:00+08:00"},
        # 结束离线测试订单列表。
        ]
        # 使用真实 JSON 文件，让测试覆盖文件读取和数据解析。
        self.data_file = create_data_file(json.dumps({"orders": orders}, ensure_ascii=False))

    # 方法功能：验证统一返回结构保留成功、数据和错误三个字段。
    def test_tool_result_has_stable_shape(self):
        # 成功结果保留业务数据，错误字段为空。
        self.assertEqual(tool_result(True, {"order_id": "A1002"}), {"success": True, "data": {"order_id": "A1002"}, "error": None})
        # 失败结果保留错误说明，数据字段为空。
        self.assertEqual(tool_result(False, error="订单不存在"), {"success": False, "data": None, "error": "订单不存在"})

    # 方法功能：验证订单号去空格并转为大写，金额仍保留两位小数字符串。
    def test_order_lookup_normalizes_id_and_keeps_amount(self):
        # 用带空格的小写订单号查询真实 JSON。
        result = get_order("  a1002  ", "acme", self.data_file)
        # 查询成功后进入统一成功结构。
        self.assertTrue(result["success"])
        # 返回真实匹配的规范订单号。
        self.assertEqual(result["data"]["order_id"], "A1002")
        # 返回调用入口指定的租户记录。
        self.assertEqual(result["data"]["tenant_id"], "acme")
        # 金额不转浮点数，保留原始精度和展示格式。
        self.assertEqual(result["data"]["amount"], "299.00")
        # 明确说明结果来自本地 JSON。
        self.assertEqual(result["data"]["source"], "json")
        # 成功结果不携带错误。
        self.assertIsNone(result["error"])

    # 方法功能：同一个订单号在不同租户下必须返回各自的数据。
    def test_same_order_id_is_isolated_by_tenant(self):
        # 查询 acme 租户的同号订单。
        acme_result = get_order("A1002", "acme", self.data_file)
        # 查询 other 租户的同号订单。
        other_result = get_order("A1002", "other", self.data_file)
        # acme 的金额保持自己的值。
        self.assertEqual(acme_result["data"]["amount"], "299.00")
        # other 的金额保持自己的值。
        self.assertEqual(other_result["data"]["amount"], "79.00")
        # other 的返回数据仍标明自己的租户。
        self.assertEqual(other_result["data"]["tenant_id"], "other")

    # 方法功能：不能通过订单号访问另一个租户的独有记录。
    def test_other_tenant_only_order_is_not_visible(self):
        # acme 尝试查询只属于 other 的订单。
        result = get_order("B9001", "acme", self.data_file)
        # 查不到是业务失败，不应抛异常。
        self.assertFalse(result["success"])
        # 失败结果不会泄露另一个租户的订单内容。
        self.assertIsNone(result["data"])
        # 错误说明应能交给工作流失败分支展示。
        self.assertTrue(result["error"])

    # 方法功能：不存在的订单和缺失输入都返回失败。
    def test_missing_order_or_required_input_returns_failure(self):
        # 分别覆盖不存在、空订单号和空租户。
        for order_id, tenant_id in [("A9999", "acme"), ("  ", "acme"), ("A1002", "  ")]:
            # 将每组输入标记为独立子测试，便于定位失败场景。
            with self.subTest(order_id=order_id, tenant_id=tenant_id):
                # 调用真实 Tool，任何场景都不应抛异常。
                result = get_order(order_id, tenant_id, self.data_file)
                # 输入或业务记录不满足要求时返回失败。
                self.assertFalse(result["success"])
                # 失败时不返回业务数据。
                self.assertIsNone(result["data"])
                # 失败时提供可读的错误说明。
                self.assertTrue(result["error"])

    # 方法功能：缺失文件要转成失败结果，工作流才能继续进入失败分支。
    def test_missing_file_returns_failure(self):
        # 在已存在的临时文件名后附加后缀，获得不存在的精确路径。
        missing_file = self.data_file.with_name(self.data_file.name + ".missing")
        # 用不存在的文件查询订单。
        result = get_order("A1002", "acme", missing_file)
        # 文件读取失败仍使用统一结果。
        self.assertFalse(result["success"])
        # 文件读取失败不携带订单数据。
        self.assertIsNone(result["data"])
        # 文件读取失败携带错误说明。
        self.assertTrue(result["error"])

    # 方法功能：JSON 损坏和 orders 结构错误必须返回失败。
    def test_invalid_json_or_structure_returns_failure(self):
        # 覆盖语法损坏、根对象错误、缺少 orders、列表类型错误和记录字段错误。
        for content in ["{broken", "[]", "{}", '{"orders": {}}', '{"orders": [1]}', '{"orders": [{}]}']:
            # 每种错误使用独立文件和子测试。
            with self.subTest(content=content):
                # 写入本场景的真实错误文件。
                data_file = create_data_file(content)
                # 业务函数读取损坏文件，不应把解析异常抛给工作流。
                result = get_order("A1002", "acme", data_file)
                # 解析或结构校验失败仍返回统一失败结构。
                self.assertFalse(result["success"])
                # 错误文件不能产生订单数据。
                self.assertIsNone(result["data"])
                # 错误说明必须保留。
                self.assertTrue(result["error"])

    # 方法功能：项目自带的演示数据可以由实际 Tool 读取。
    def test_default_demo_data_is_readable(self):
        # 用默认文件调用本课业务函数。
        result = get_order("A1002", "acme", DEFAULT_DATA_FILE)
        # 自带样例必须查询成功。
        self.assertTrue(result["success"])
        # 检查样例金额未被格式转换改变。
        self.assertEqual(result["data"]["amount"], "299.00")
        # 检查返回值标明本地 JSON 来源。
        self.assertEqual(result["data"]["source"], "json")


# 类职责：通过真实 LangGraph 执行，验证 Tool 结果能决定成功和失败路径。
class BusinessToolWorkflowTests(unittest.TestCase):
    # 方法功能：成功图执行先整理订单号，再把 Tool 结果写入 State 并生成回答。
    def test_successful_graph_uses_updated_state(self):
        # 创建真实的业务 Tool 图，不使用数据库或模型。
        graph = build_graph()
        # 可信入口传入租户，用户输入只提供订单号。
        result = graph.invoke({"question": "  a1002  ", "tenant_id": "acme"})
        # 保留原始输入以便断点观察。
        self.assertEqual(result["question"], "  a1002  ")
        # prepare 整理后的字段应传到 Tool 节点。
        self.assertEqual(result["order_id"], "A1002")
        # State 记录实际使用的业务 Tool。
        self.assertEqual(result["tool_name"], "get_order")
        # 业务 Tool 查询成功。
        self.assertTrue(result["tool_result"]["success"])
        # 条件边选择成功回答分支。
        self.assertEqual(result["branch"], "success")
        # 最终回答包含查询到的订单号。
        self.assertIn("A1002", result["answer"])
        # 最终回答包含查询到的原始金额。
        self.assertIn("299.00", result["answer"])

    # 方法功能：不存在的订单通过条件边进入失败回答，并正常结束。
    def test_missing_order_graph_uses_error_branch(self):
        # 创建默认本地数据图。
        graph = build_graph()
        # 提交不存在的订单号。
        result = graph.invoke({"question": "A9999", "tenant_id": "acme"})
        # Tool 结果在 State 中保存失败标志。
        self.assertFalse(result["tool_result"]["success"])
        # 条件边选择失败回答分支。
        self.assertEqual(result["branch"], "error")
        # 失败后仍生成可展示回答。
        self.assertTrue(result["answer"])
        # 回答包含 Tool 的错误信息，方便学习失败传递。
        self.assertIn(result["tool_result"]["error"], result["answer"])

    # 方法功能：文件损坏也能走完整失败分支，避免图运行崩溃。
    def test_broken_file_graph_uses_error_branch(self):
        # 创建一个 JSON 语法损坏的真实临时文件。
        data_file = create_data_file("{broken")
        # 把该文件注入真实 LangGraph 图。
        graph = build_graph(data_file)
        # 图内部真实调用 Tool，并接收失败结果。
        result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
        # 文件解析失败仍留在 Tool 的统一返回值中。
        self.assertFalse(result["tool_result"]["success"])
        # 失败条件边被选中。
        self.assertEqual(result["branch"], "error")
        # 最终回答带出文件错误信息。
        self.assertIn(result["tool_result"]["error"], result["answer"])

    # 方法功能：Tool 抛出未预期异常时，节点把异常转成失败结果并正常结束。
    def test_unexpected_tool_exception_uses_error_branch(self):
        # 创建默认本地数据图。
        graph = build_graph()
        # 只模拟调用边界的异常，保留真实节点和条件边执行。
        with patch("agent_learning.workflows.business_tool.get_order", side_effect=RuntimeError("模拟异常")):
            # 执行完整图，异常不应直接中断 graph.invoke。
            result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
        # Tool 调用异常转成统一失败标志。
        self.assertFalse(result["tool_result"]["success"])
        # 失败时不产生订单数据。
        self.assertIsNone(result["tool_result"]["data"])
        # 未预期异常也进入失败分支。
        self.assertEqual(result["branch"], "error")
        # 错误结果在最终回答中可见。
        self.assertIn(result["tool_result"]["error"], result["answer"])


# 允许从 IDE 或命令行单独执行本课离线测试。
if __name__ == "__main__":
    # 运行全部测试用例并输出失败位置。
    unittest.main()
