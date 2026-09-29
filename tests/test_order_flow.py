# 导入标准库，把合成业务资料写成真实 JSON 文件。
import json
# 导入标准库，创建不会自动删除目录的临时文件。
import tempfile
# 导入项目现有的离线测试框架。
import unittest
# 导入函数替身，用来模拟 Tool 的未预期异常。
from unittest.mock import patch
# 导入路径对象，向业务函数传入数据文件。
from pathlib import Path

# 导入本课新增的两个独立业务查询函数。
from agent_learning.business.tools import get_payment, get_refund
# 导入真实 LangGraph 图，测试节点、条件边和最终汇总。
from agent_learning.workflows.order_flow import build_graph


# 方法功能：保存独立临时文件，不修改项目演示资料。
def create_data_file(content: str) -> Path:
    # 文件放在系统临时目录，关闭后仍保留，避免删除目录。
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as file:
        # 写入正常 JSON 或本场景需要的错误内容。
        file.write(content)
        # 保存文件的精确位置。
        data_file = Path(file.name)
    # 文件关闭后交给真实业务函数打开。
    return data_file


# 方法功能：提供两个租户、同号订单、多次支付和多次退款的直观测试资料。
def business_data() -> dict:
    # 三种记录分别保存在自己的列表中。
    return {
        # 订单查询只返回当前租户的同号订单。
        "orders": [
            # acme 的目标订单已经支付。
            {"tenant_id": "acme", "order_id": "A1002", "status": "已支付", "amount": "299.00", "currency": "CNY", "updated_at": "2026-09-29T09:00:00+08:00"},
            # other 拥有相同订单号，但其金额和状态不同。
            {"tenant_id": "other", "order_id": "A1002", "status": "已取消", "amount": "79.00", "currency": "CNY", "updated_at": "2026-09-29T09:00:00+08:00"},
        # 结束订单列表。
        ],
        # 支付查询必须保留同一订单的全部记录。
        "payments": [
            # 首次支付失败，用于验证不能只取第一条记录。
            {"tenant_id": "acme", "order_id": "A1002", "payment_id": "P1001", "status": "支付失败", "amount": "299.00", "currency": "CNY", "method": "银行卡", "updated_at": "2026-09-29T09:01:00+08:00"},
            # 第二次支付成功，工作流因此可以继续查退款。
            {"tenant_id": "acme", "order_id": "A1002", "payment_id": "P1002", "status": "支付成功", "amount": "299.00", "currency": "CNY", "method": "银行卡", "updated_at": "2026-09-29T09:02:00+08:00"},
            # 同租户另一订单的记录不能混入结果。
            {"tenant_id": "acme", "order_id": "A9001", "payment_id": "P9001", "status": "支付成功", "amount": "9.90", "currency": "CNY", "method": "支付宝", "updated_at": "2026-09-29T09:02:00+08:00"},
            # 同号订单的其他租户记录也不能混入结果。
            {"tenant_id": "other", "order_id": "A1002", "payment_id": "PO1002", "status": "支付成功", "amount": "79.00", "currency": "CNY", "method": "微信", "updated_at": "2026-09-29T09:02:00+08:00"},
        # 结束支付列表。
        ],
        # 退款查询也要保留同一订单的多条记录。
        "refunds": [
            # 第一条退款只有退款自身字段，payment_id 是可选字段。
            {"tenant_id": "acme", "order_id": "A1002", "refund_id": "R1001", "status": "退款成功", "amount": "99.00", "currency": "CNY", "reason": "部分退货", "updated_at": "2026-09-29T09:03:00+08:00"},
            # 第二条退款额外保留所关联的支付号。
            {"tenant_id": "acme", "order_id": "A1002", "refund_id": "R1002", "payment_id": "P1002", "status": "退款处理中", "amount": "200.00", "currency": "CNY", "reason": "剩余退货", "updated_at": "2026-09-29T09:04:00+08:00"},
            # 同租户另一订单的退款不能混入结果。
            {"tenant_id": "acme", "order_id": "A9001", "refund_id": "R9001", "status": "退款成功", "amount": "9.90", "currency": "CNY", "reason": "退货", "updated_at": "2026-09-29T09:04:00+08:00"},
            # other 的同号退款不能泄露给 acme。
            {"tenant_id": "other", "order_id": "A1002", "refund_id": "RO1002", "status": "退款成功", "amount": "79.00", "currency": "CNY", "reason": "取消", "updated_at": "2026-09-29T09:04:00+08:00"},
        # 结束退款列表。
        ],
    # 结束整个测试资料字典。
    }


# 类职责：验证支付和退款 Tool 的全部记录、租户隔离及统一失败结果。
class OrderRecordToolTests(unittest.TestCase):
    # 方法功能：每个测试使用独立资料和真实 JSON 文件。
    def setUp(self):
        # 准备普通字典资料，避免依赖项目演示场景的细节。
        self.data = business_data()
        # 保存真实 JSON，覆盖文件读取和解析路径。
        self.data_file = create_data_file(json.dumps(self.data, ensure_ascii=False))

    # 方法功能：支付函数规范化订单号，保留全部匹配记录和字符串金额。
    def test_payment_returns_all_matching_records(self):
        # 用小写且带首尾空格的订单号查询 acme 支付。
        result = get_payment("  a1002  ", "acme", self.data_file)
        # 两条匹配记录均应成功返回。
        self.assertTrue(result["success"])
        # 保留支付失败和支付成功两个事件，不只返回第一条。
        self.assertEqual([record["payment_id"] for record in result["data"]], ["P1001", "P1002"])
        # 金额字符串保持原始精度和显示格式。
        self.assertEqual([record["amount"] for record in result["data"]], ["299.00", "299.00"])
        # 每条记录都标明本地 JSON 来源。
        self.assertTrue(all(record["source"] == "json" for record in result["data"]))
        # 成功结果没有错误说明。
        self.assertIsNone(result["error"])
        # other 的同号查询只返回 other 的记录。
        other_result = get_payment("A1002", "other", self.data_file)
        # 同号记录必须按租户区分。
        self.assertEqual([record["payment_id"] for record in other_result["data"]], ["PO1002"])

    # 方法功能：退款函数保留多条记录，且 payment_id 可以省略。
    def test_refund_returns_all_matching_records(self):
        # 查询 acme 的全部退款。
        result = get_refund(" a1002 ", "acme", self.data_file)
        # 第一条没有 payment_id 也能成功。
        self.assertTrue(result["success"])
        # 不能返回同租户其他订单或其他租户的退款。
        self.assertEqual([record["refund_id"] for record in result["data"]], ["R1001", "R1002"])
        # 退款金额保留原始字符串。
        self.assertEqual([record["amount"] for record in result["data"]], ["99.00", "200.00"])
        # 每条退款都包含来源字段。
        self.assertTrue(all(record["source"] == "json" for record in result["data"]))
        # 原有的可选支付号应保留。
        self.assertEqual(result["data"][1]["payment_id"], "P1002")
        # other 的同号查询只能看见自己的退款。
        other_result = get_refund("A1002", "other", self.data_file)
        # 按租户过滤后只有一条退款。
        self.assertEqual([record["refund_id"] for record in other_result["data"]], ["RO1002"])

    # 方法功能：没有匹配记录表示成功查询到空列表，不是查询失败。
    def test_no_matching_records_returns_successful_empty_list(self):
        # 支付和退款都使用同样的空记录约定。
        for tool in (get_payment, get_refund):
            # 标记当前测试的业务函数。
            with self.subTest(tool=tool.__name__):
                # 查询当前租户没有记录的订单号。
                result = tool("A9999", "acme", self.data_file)
                # 查询正常完成时 success 为真。
                self.assertTrue(result["success"])
                # 无业务记录必须是空列表。
                self.assertEqual(result["data"], [])
                # 无记录不携带系统错误。
                self.assertIsNone(result["error"])

    # 方法功能：没有订单号或租户时不得继续查询。
    def test_empty_input_returns_failure(self):
        # 两个 Tool 都需要订单号和可信租户。
        for tool in (get_payment, get_refund):
            # 分别覆盖空订单号和空租户。
            for order_id, tenant_id in [("  ", "acme"), ("A1002", "  ")]:
                # 为当前函数和输入组合建立独立子测试。
                with self.subTest(tool=tool.__name__, order_id=order_id, tenant_id=tenant_id):
                    # 真实调用业务函数，不模拟参数检查。
                    result = tool(order_id, tenant_id, self.data_file)
                    # 缺参数必须返回失败。
                    self.assertFalse(result["success"])
                    # 失败结果不包含记录列表。
                    self.assertIsNone(result["data"])
                    # 失败结果保留可读原因。
                    self.assertTrue(result["error"])

    # 方法功能：文件不存在时，两种查询都返回受控失败。
    def test_missing_file_returns_failure(self):
        # 使用独立文件名追加后缀，获得不存在的精确路径。
        missing_file = self.data_file.with_name(self.data_file.name + ".missing")
        # 分别调用支付和退款查询。
        for tool in (get_payment, get_refund):
            # 单独标记每种 Tool。
            with self.subTest(tool=tool.__name__):
                # 文件打开错误不应该向调用方抛出。
                result = tool("A1002", "acme", missing_file)
                # 文件错误返回统一失败结构。
                self.assertFalse(result["success"])
                # 文件错误不会生成业务记录。
                self.assertIsNone(result["data"])
                # 保留文件排查提示。
                self.assertTrue(result["error"])

    # 方法功能：JSON 损坏、根对象和记录格式错误均返回失败。
    def test_invalid_json_or_record_structure_returns_failure(self):
        # 逐一测试两个不同的记录列表。
        for tool, table_name in [(get_payment, "payments"), (get_refund, "refunds")]:
            # 错误场景涵盖语法、根对象、缺列表、列表类型和记录字段。
            contents = ["{broken", "[]", "{}", json.dumps({table_name: {}}), json.dumps({table_name: [1]}), json.dumps({table_name: [{}]})]
            # 每种错误文件都应受控失败。
            for content in contents:
                # 标记当前 Tool 和错误内容。
                with self.subTest(tool=tool.__name__, content=content):
                    # 写入实际错误文件，覆盖真实读取路径。
                    data_file = create_data_file(content)
                    # 调用真实 Tool 处理该文件。
                    result = tool("A1002", "acme", data_file)
                    # 错误文件不能被当作空记录成功。
                    self.assertFalse(result["success"])
                    # 失败后不携带记录数据。
                    self.assertIsNone(result["data"])
                    # 失败原因可供工作流汇总。
                    self.assertTrue(result["error"])


# 类职责：验证多步工作流按业务结果继续查询或提前汇总，并保留已取得的证据。
class OrderFlowTests(unittest.TestCase):
    # 方法功能：每个场景从同一份简单业务字典开始。
    def setUp(self):
        # 各测试只修改自己的字典，不触碰项目演示资料。
        self.data = business_data()

    # 方法功能：保存本场景资料并返回真实编译图。
    def create_graph(self):
        # 让每个图真实读取本场景的 JSON 文件。
        data_file = create_data_file(json.dumps(self.data, ensure_ascii=False))
        # 通过构图参数注入数据文件。
        return build_graph(data_file)

    # 方法功能：订单、支付和退款依次执行，任一成功支付允许继续查退款。
    def test_completed_flow_keeps_all_results_in_tool_order(self):
        # 创建真实多步图。
        graph = self.create_graph()
        # 使用最小初始 State，保留原始问题用于调试。
        result = graph.invoke({"question": "  a1002  ", "tenant_id": "acme"})
        # 原始问题保留输入时的空格和大小写。
        self.assertEqual(result["question"], "  a1002  ")
        # prepare 写入规范订单号。
        self.assertEqual(result["order_id"], "A1002")
        # 租户仍是可信入口传入的身份。
        self.assertEqual(result["tenant_id"], "acme")
        # 执行记录必须保持订单、支付、退款的真实先后次序。
        self.assertEqual(result["executed_tools"], ["get_order", "get_payment", "get_refund"])
        # 最终 State 仍保留订单金额。
        self.assertEqual(result["order_result"]["data"]["amount"], "299.00")
        # 支付历史完整保留，不覆盖为单条成功记录。
        self.assertEqual([record["payment_id"] for record in result["payment_result"]["data"]], ["P1001", "P1002"])
        # 两笔退款历史完整保留。
        self.assertEqual([record["refund_id"] for record in result["refund_result"]["data"]], ["R1001", "R1002"])
        # 有退款记录时标记完成链路。
        self.assertEqual(result["branch"], "completed")
        # 最终回答应能显示当前订单。
        self.assertIn("A1002", result["answer"])

    # 方法功能：待支付和未支付订单都只查询订单，然后提前汇总。
    def test_unpaid_order_skips_payment_and_refund(self):
        # 覆盖本课约定的两种未支付状态。
        for status in ("待支付", "未支付"):
            # 标记正在测试的订单状态。
            with self.subTest(status=status):
                # 修改本场景的目标订单状态。
                self.data["orders"][0]["status"] = status
                # 将该场景编译为真实图。
                graph = self.create_graph()
                # 记录两个后续 Tool，确认它们真正没有被调用。
                with patch("agent_learning.workflows.order_flow.get_payment") as payment_tool, patch("agent_learning.workflows.order_flow.get_refund") as refund_tool:
                    # 执行完整流程，应该在订单结果之后汇总。
                    result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
                # 只记录已执行的订单 Tool。
                self.assertEqual(result["executed_tools"], ["get_order"])
                # 未查询支付时保留空字典，区别于查到空列表。
                self.assertEqual(result["payment_result"], {})
                # 未查询退款时也保留空字典。
                self.assertEqual(result["refund_result"], {})
                # 最终分支说明是未支付。
                self.assertEqual(result["branch"], "unpaid")
                # 确认支付 Tool 没有执行。
                payment_tool.assert_not_called()
                # 确认退款 Tool 没有执行。
                refund_tool.assert_not_called()

    # 方法功能：订单不存在或空输入时直接汇总错误，不查询后续资料。
    def test_order_error_stops_after_order_tool(self):
        # 分别覆盖不存在的订单和空订单号。
        for question in ("A9999", "  "):
            # 标记当前订单输入。
            with self.subTest(question=question):
                # 建立真实业务图。
                graph = self.create_graph()
                # 记录后续 Tool，确认订单失败后确实没有调用它们。
                with patch("agent_learning.workflows.order_flow.get_payment") as payment_tool, patch("agent_learning.workflows.order_flow.get_refund") as refund_tool:
                    # 用最小 State 触发订单失败。
                    result = graph.invoke({"question": question, "tenant_id": "acme"})
                # 失败时也记录已经尝试的 Tool。
                self.assertEqual(result["executed_tools"], ["get_order"])
                # 订单失败结果仍保存在 State。
                self.assertFalse(result["order_result"]["success"])
                # 支付尚未查询。
                self.assertEqual(result["payment_result"], {})
                # 退款尚未查询。
                self.assertEqual(result["refund_result"], {})
                # 图通过订单错误分支正常结束。
                self.assertEqual(result["branch"], "order_error")
                # 汇总保留 Tool 的失败说明。
                self.assertIn(result["order_result"]["error"], result["answer"])
                # 订单失败后不得调用支付。
                payment_tool.assert_not_called()
                # 订单失败后不得调用退款。
                refund_tool.assert_not_called()

    # 方法功能：找不到支付记录时保留订单，并跳过退款。
    def test_empty_payments_stop_before_refund(self):
        # 仅删除测试字典中的支付记录，不删除任何文件或目录。
        self.data["payments"] = []
        # 建立当前场景的图。
        graph = self.create_graph()
        # 记录退款 Tool，确认空支付列表不会继续调用退款。
        with patch("agent_learning.workflows.order_flow.get_refund") as refund_tool:
            # 查询已支付订单，但此场景没有对应支付记录。
            result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
        # 支付查询成功后返回空列表。
        self.assertEqual(result["payment_result"], {"success": True, "data": [], "error": None})
        # 已获得的订单证据仍保留。
        self.assertTrue(result["order_result"]["success"])
        # 空支付记录不应该继续查询退款。
        self.assertEqual(result["refund_result"], {})
        # 实际只执行订单和支付。
        self.assertEqual(result["executed_tools"], ["get_order", "get_payment"])
        # 汇总明确标记缺支付记录。
        self.assertEqual(result["branch"], "payment_missing")
        # 提前结束也要产生可展示回答。
        self.assertTrue(result["answer"])
        # 验证退款函数确实没有执行，而不只检查 State。
        refund_tool.assert_not_called()

    # 方法功能：支付记录存在但没有支付成功时跳过退款。
    def test_failed_payments_stop_before_refund(self):
        # 将目标订单的唯一成功支付改为处理中。
        self.data["payments"][1]["status"] = "支付处理中"
        # 创建当前场景的真实图。
        graph = self.create_graph()
        # 记录退款 Tool，确认没有成功支付时不调用它。
        with patch("agent_learning.workflows.order_flow.get_refund") as refund_tool:
            # 订单存在，支付列表非空，但两条记录均未成功。
            result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
        # 不能把 other 或其他订单的成功支付算到当前订单。
        self.assertEqual(result["branch"], "payment_not_success")
        # 仍保留两个已读取的支付事件。
        self.assertEqual(len(result["payment_result"]["data"]), 2)
        # 当前订单没有成功支付时不查退款。
        self.assertEqual(result["refund_result"], {})
        # 实际执行到支付后结束。
        self.assertEqual(result["executed_tools"], ["get_order", "get_payment"])
        # 验证没有调用被跳过的退款函数。
        refund_tool.assert_not_called()

    # 方法功能：支付资料格式错误时，不丢弃之前已经成功的订单结果。
    def test_payment_error_keeps_order_result(self):
        # 将支付列表替换为错误结构。
        self.data["payments"] = {}
        # 创建真实的错误场景图。
        graph = self.create_graph()
        # 记录退款 Tool，确认支付读取失败后不调用它。
        with patch("agent_learning.workflows.order_flow.get_refund") as refund_tool:
            # 订单先成功，支付随后失败。
            result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
        # 已查询的订单保持成功。
        self.assertTrue(result["order_result"]["success"])
        # 支付错误结果保留在自己的字段中。
        self.assertFalse(result["payment_result"]["success"])
        # 支付失败后不查退款。
        self.assertEqual(result["refund_result"], {})
        # 最终分支指向支付失败。
        self.assertEqual(result["branch"], "payment_error")
        # 执行次序只包含实际尝试的两个 Tool。
        self.assertEqual(result["executed_tools"], ["get_order", "get_payment"])
        # 最终汇总保留支付错误说明。
        self.assertIn(result["payment_result"]["error"], result["answer"])
        # 验证退款函数确实没有执行。
        refund_tool.assert_not_called()

    # 方法功能：查到空退款列表时正常结束，并与尚未查询的空字典区分。
    def test_no_refund_keeps_successful_empty_result(self):
        # 本场景的退款列表有效但没有记录。
        self.data["refunds"] = []
        # 创建真实多步图。
        graph = self.create_graph()
        # 支付成功后继续查询退款。
        result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
        # 查无退款仍是成功查询。
        self.assertEqual(result["refund_result"], {"success": True, "data": [], "error": None})
        # 三个 Tool 都实际执行。
        self.assertEqual(result["executed_tools"], ["get_order", "get_payment", "get_refund"])
        # 汇总标记没有退款记录。
        self.assertEqual(result["branch"], "no_refund")
        # 没有退款也产生最终回答。
        self.assertTrue(result["answer"])

    # 方法功能：退款查询失败时保留订单和支付证据并正常汇总。
    def test_refund_error_keeps_previous_results(self):
        # 将退款列表设为错误结构，模拟该阶段资料失败。
        self.data["refunds"] = {}
        # 创建真实错误场景图。
        graph = self.create_graph()
        # 订单和支付先执行成功，退款再失败。
        result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
        # 订单结果保持成功。
        self.assertTrue(result["order_result"]["success"])
        # 支付结果保持成功。
        self.assertTrue(result["payment_result"]["success"])
        # 退款结果单独保存失败。
        self.assertFalse(result["refund_result"]["success"])
        # 最终分支说明失败发生在退款。
        self.assertEqual(result["branch"], "refund_error")
        # 已尝试的三种 Tool 保持次序。
        self.assertEqual(result["executed_tools"], ["get_order", "get_payment", "get_refund"])
        # 汇总包含退款阶段的错误说明。
        self.assertIn(result["refund_result"]["error"], result["answer"])

    # 方法功能：JSON 文件损坏时，图在第一个 Tool 后受控结束。
    def test_broken_file_ends_in_order_error(self):
        # 创建真实 JSON 语法损坏文件。
        data_file = create_data_file("{broken")
        # 把坏文件注入真实图。
        graph = build_graph(data_file)
        # 记录两个后续 Tool，确认坏文件在第一步就结束。
        with patch("agent_learning.workflows.order_flow.get_payment") as payment_tool, patch("agent_learning.workflows.order_flow.get_refund") as refund_tool:
            # 图应该接收统一失败结果，而不是让解析异常中断 invoke。
            result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
        # 失败发生在订单查询阶段。
        self.assertEqual(result["branch"], "order_error")
        # 只尝试订单 Tool。
        self.assertEqual(result["executed_tools"], ["get_order"])
        # 两个后续查询都保持未执行状态。
        self.assertEqual((result["payment_result"], result["refund_result"]), ({}, {}))
        # 最终总结仍包含错误说明。
        self.assertIn(result["order_result"]["error"], result["answer"])
        # 文件读取失败后不得查询支付。
        payment_tool.assert_not_called()
        # 文件读取失败后不得查询退款。
        refund_tool.assert_not_called()

    # 方法功能：任意一个 Tool 抛出意外异常时，都进入对应的受控失败汇总。
    def test_unexpected_tool_exceptions_end_in_error_summary(self):
        # 分别约定各阶段的失败分支和已执行 Tool 次序。
        scenarios = [
            # 订单抛异常后不能调用支付和退款。
            ("get_order", "order_error", ["get_order"]),
            # 支付抛异常后保留已经取得的订单结果。
            ("get_payment", "payment_error", ["get_order", "get_payment"]),
            # 退款抛异常后保留已经取得的订单和支付结果。
            ("get_refund", "refund_error", ["get_order", "get_payment", "get_refund"]),
        # 结束异常场景列表。
        ]
        # 每个场景使用真实图，只替换本次要抛异常的业务函数。
        for tool_name, branch, executed_tools in scenarios:
            # 标记当前抛异常的 Tool。
            with self.subTest(tool_name=tool_name):
                # 为本场景创建真实编译图。
                graph = self.create_graph()
                # 用未预期 RuntimeError 测试节点调用边界。
                with patch(f"agent_learning.workflows.order_flow.{tool_name}", side_effect=RuntimeError("模拟异常")):
                    # 完整图应正常返回最终状态。
                    result = graph.invoke({"question": "A1002", "tenant_id": "acme"})
                # 失败原因发生在哪个阶段就走哪个分支。
                self.assertEqual(result["branch"], branch)
                # 失败阶段本身也应计入实际尝试的 Tool。
                self.assertEqual(result["executed_tools"], executed_tools)
                # 最终汇总必须给出可展示的失败说明。
                self.assertTrue(result["answer"])


# 允许在 IDE 或命令行单独运行第 61 课离线测试。
if __name__ == "__main__":
    # 执行本文件全部场景并报告失败位置。
    unittest.main()
