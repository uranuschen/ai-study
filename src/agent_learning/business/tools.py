# 导入标准库，用于读取本地 JSON 模拟业务数据。
import json
# 导入路径类，让数据文件位置不受 IDE 工作目录影响。
from pathlib import Path


# 根据当前文件位置找到项目根目录下的模拟业务数据。
DEFAULT_DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "business_demo.json"


# 方法功能：让成功、业务失败和文件读取失败使用同一份返回结构。
def tool_result(success: bool, data=None, error=None) -> dict:
    # success 表示是否成功，data 保存业务数据，error 保存失败说明。
    return {"success": success, "data": data, "error": error}


# 方法功能：根据可信入口提供的租户和订单号，只读查询本地模拟订单。
def get_order(order_id: str, tenant_id: str, data_file: Path = DEFAULT_DATA_FILE) -> dict:
    # 先检查订单号，避免空输入进入文件查询。
    if not isinstance(order_id, str) or not order_id.strip():
        # 参数不完整时仍然返回统一 Tool 结果。
        return tool_result(False, error="请输入非空订单号。")
    # 租户由入口提供，不能从用户问题中猜测或提高权限。
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        # 没有租户身份时拒绝查询。
        return tool_result(False, error="缺少租户身份，无法查询订单。")
    # 本课样例订单号统一使用大写，允许输入两端空格和小写字母。
    clean_order_id = order_id.strip().upper()
    # 只去掉租户两端空格，保留租户本身的大小写。
    clean_tenant_id = tenant_id.strip()
    # 文件读取异常转换为 Tool 失败结果，交给工作流选择失败分支。
    try:
        # 每次查询读取最新文件内容，退出 with 时自动关闭文件。
        with Path(data_file).open("r", encoding="utf-8") as file:
            # 把 JSON 对象还原为普通 Python 字典。
            business_data = json.load(file)
    # 文件不存在或不能读取时，不让异常中断整个工作流。
    except OSError as error:
        # 在这一行打断点可查看 error；返回路径或权限的排查提示。
        return tool_result(False, error="读取业务数据文件失败，请检查文件路径或权限。")
    # 编码错误或 JSON 语法错误也属于数据读取失败。
    except (UnicodeError, json.JSONDecodeError) as error:
        # 在这一行打断点可查看 error；不把格式错误误报成订单不存在。
        return tool_result(False, error="业务数据文件不是有效的 UTF-8 JSON。")
    # 本课文件必须是包含 orders 列表的 JSON 对象。
    if not isinstance(business_data, dict) or not isinstance(business_data.get("orders"), list):
        # 结构不符合约定时明确进入失败分支。
        return tool_result(False, error="业务数据格式错误：需要 orders 列表。")
    # 逐条检查订单，查询条件同时包含租户和订单号。
    for order in business_data["orders"]:
        # 每一条订单必须是普通字典。
        if not isinstance(order, dict):
            # 不允许用错误类型继续访问订单字段。
            return tool_result(False, error="业务数据格式错误：每条订单必须是对象。")
        # 本课金额以字符串保存，避免转成 float 后产生精度误差。
        for field in ("tenant_id", "order_id", "status", "amount", "currency", "updated_at"):
            # 检查必要字段存在，且内容是非空字符串。
            if not isinstance(order.get(field), str) or not order[field].strip():
                # 指出具体缺失或格式错误的字段。
                return tool_result(False, error=f"业务数据格式错误：订单字段 {field} 必须是非空字符串。")
        # 同号订单只有租户也一致时才可以返回。
        if order["tenant_id"] == clean_tenant_id and order["order_id"] == clean_order_id:
            # 复制业务结果，不向原始读取字典追加展示字段。
            data = dict(order)
            # 标注这是本地 JSON 数据，不能称为真实订单的实时状态。
            data["source"] = "json"
            # 查询成功时 error 保持为 None。
            return tool_result(True, data=data)
    # 未找到与当前租户匹配的订单时，返回正常的业务失败结果。
    return tool_result(False, error="订单不存在或当前租户不可读取。")


# 方法功能：按租户和订单号读取支付或退款列表，供两个只读 Tool 共用。
def read_order_records(order_id: str, tenant_id: str, collection_name: str, required_fields: tuple, data_file: Path) -> dict:
    # 空订单号不进入文件查询。
    if not isinstance(order_id, str) or not order_id.strip():
        # 参数错误保持统一返回格式。
        return tool_result(False, error="请输入非空订单号。")
    # 租户仍然必须由可信入口提供。
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        # 没有租户身份就拒绝读取。
        return tool_result(False, error="缺少租户身份，无法查询业务记录。")
    # 与订单 Tool 使用相同的订单号整理规则。
    clean_order_id = order_id.strip().upper()
    # 去掉租户两端空格，不改变租户大小写。
    clean_tenant_id = tenant_id.strip()
    # 将文件读取问题转换为可保存在 State 中的失败结果。
    try:
        # 以只读方式打开 JSON 文件。
        with Path(data_file).open("r", encoding="utf-8") as file:
            # 读取普通字典和列表，不连接数据库。
            business_data = json.load(file)
    # 文件不存在或没有读取权限时进入这个分支。
    except OSError as error:
        # Debug 时可以在这里查看原始异常，但不向用户暴露文件详情。
        return tool_result(False, error="读取业务数据文件失败，请检查文件路径或权限。")
    # 文件编码或 JSON 语法错误时进入这个分支。
    except (UnicodeError, json.JSONDecodeError) as error:
        # 数据损坏不能被当作没有业务记录。
        return tool_result(False, error="业务数据文件不是有效的 UTF-8 JSON。")
    # 所查询的集合必须明确存在，并且是列表。
    if not isinstance(business_data, dict) or not isinstance(business_data.get(collection_name), list):
        # 缺少列表属于格式错误，区别于存在但为空的列表。
        return tool_result(False, error=f"业务数据格式错误：需要 {collection_name} 列表。")
    # 一个订单可能有多条记录，因此先准备结果列表。
    records = []
    # 遍历当前 Tool 对应的支付或退款集合。
    for record in business_data[collection_name]:
        # 每条业务记录必须是字典。
        if not isinstance(record, dict):
            # 不让错误类型进入后续字段读取。
            return tool_result(False, error=f"业务数据格式错误：{collection_name} 中每条记录必须是对象。")
        # 检查这个 Tool 所要求的必要字段。
        for field in required_fields:
            # 金额也保持非空字符串，不转换成浮点数。
            if not isinstance(record.get(field), str) or not record[field].strip():
                # 返回具体的格式错误字段。
                return tool_result(False, error=f"业务数据格式错误：{collection_name} 字段 {field} 必须是非空字符串。")
        # 租户和订单号必须同时匹配，不能混入其他租户的同号记录。
        if record["tenant_id"] == clean_tenant_id and record["order_id"] == clean_order_id:
            # 复制匹配记录，保留原来的业务字段和更新时间。
            data = dict(record)
            # 标记当前查询的数据来源。
            data["source"] = "json"
            # 收集所有匹配记录，而不是只返回第一条。
            records.append(data)
    # 没有匹配记录时也算查询成功，data 为 []，不是 Tool 执行失败。
    return tool_result(True, data=records)


# 方法功能：只读查询当前租户的订单支付记录，不执行支付。
def get_payment(order_id: str, tenant_id: str, data_file: Path = DEFAULT_DATA_FILE) -> dict:
    # 规定支付记录需要的字段，金额保持字符串。
    required_fields = ("tenant_id", "order_id", "payment_id", "status", "amount", "currency", "method", "updated_at")
    # 复用普通函数读取 payments 列表，返回统一 Tool 结果。
    return read_order_records(order_id, tenant_id, "payments", required_fields, data_file)


# 方法功能：只读查询当前租户的订单退款记录，不发起退款。
def get_refund(order_id: str, tenant_id: str, data_file: Path = DEFAULT_DATA_FILE) -> dict:
    # payment_id 可以没有，但退款本身的标识、金额、原因和时间必须存在。
    required_fields = ("tenant_id", "order_id", "refund_id", "status", "amount", "currency", "reason", "updated_at")
    # 复用普通函数读取 refunds 列表；无退款记录返回成功的空列表。
    return read_order_records(order_id, tenant_id, "refunds", required_fields, data_file)
