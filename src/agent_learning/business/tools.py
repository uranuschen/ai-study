# 导入时间解析类，用于按真实时间点对 JSON 支付与退款列表稳定排序。
from datetime import datetime
# 导入标准库，用于读取本地 JSON 模拟业务数据。
import json
# 导入路径类，让数据文件位置不受 IDE 工作目录影响。
from pathlib import Path
# 导入只读 PostgreSQL 业务存储、固定错误常量及统一的金额/时间格式化函数。
from agent_learning.business.postgres_store import (
    ORDER_NOT_FOUND_ERROR,
    PERMISSION_DENIED_ERROR,
    QUERY_TIMEOUT_ERROR,
    PostgresBusinessStore,
    format_amount,
    format_updated_at,
)
# 导入统一配置类与加载函数，用于按 BUSINESS_DATA_SOURCE 切换数据源。
from agent_learning.core.config import Settings, load_settings


# 根据当前文件位置找到项目根目录下的模拟业务数据。
DEFAULT_DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "business_demo.json"


# 方法功能：让成功、业务失败和读取失败使用同一份三字段返回结构。
def tool_result(success: bool, data=None, error=None) -> dict:
    # success 表示是否成功，data 保存业务数据，error 保存失败说明。
    return {"success": success, "data": data, "error": error}


# 类职责：从本地 JSON 文件只读查询订单、支付和退款样例数据。
class JsonBusinessStore:
    # 方法功能：保存本地 JSON 样例文件路径，构造时不读取文件。
    def __init__(self, data_file: Path = DEFAULT_DATA_FILE) -> None:
        # 标明当前存储实现的数据来源名称。
        self.source: str = "json"
        # 统一转为 Path，兼容字符串和 Path 参数。
        self.data_file: Path = Path(data_file)

    # 方法功能：按可信入口提供的租户和订单号，只读查询本地模拟订单。
    def get_order(self, order_id: str, tenant_id: str) -> dict:
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
            with self.data_file.open("r", encoding="utf-8") as file:
                # 把 JSON 对象还原为普通 Python 字典。
                business_data = json.load(file)
        # 文件不存在或不能读取时，不让异常中断整个工作流。
        except OSError:
            # 返回路径或权限的排查提示，不暴露内部路径详情。
            return tool_result(False, error="读取业务数据文件失败，请检查文件路径或权限。")
        # 编码错误或 JSON 语法错误也属于数据读取失败。
        except (UnicodeError, json.JSONDecodeError):
            # 不把格式错误误报成订单不存在。
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
            # 使用与 PostgreSQL 相同的规则校验并统一金额与带时区时间格式。
            try:
                # 统一转换为两位小数金额字符串，保证自定义 JSON 与数据库格式一致。
                normalized_amount = format_amount(order["amount"])
                # 统一转换为 +08:00 秒级 ISO 时间字符串，消除时区与精度差异。
                normalized_updated_at = format_updated_at(order["updated_at"])
            # 金额或时间格式不合法时直接返回格式错误。
            except ValueError:
                # 避免非法数值或无时区时间混入业务结果。
                return tool_result(False, error="业务数据格式错误：订单金额或更新时间格式无效。")
            # 同号订单只有租户也一致时才可以返回。
            if order["tenant_id"] == clean_tenant_id and order["order_id"] == clean_order_id:
                # 复制业务结果，不向原始读取字典追加展示字段。
                data = dict(order)
                # 写入统一格式后的两位小数金额。
                data["amount"] = normalized_amount
                # 写入统一格式后的带时区更新时间。
                data["updated_at"] = normalized_updated_at
                # 标注这是本地 JSON 数据，不能称为真实订单的实时状态。
                data["source"] = "json"
                # 查询成功时 error 保持为 None。
                return tool_result(True, data=data)
        # 未找到与当前租户匹配的订单时，返回正常的业务失败结果。
        return tool_result(False, error=ORDER_NOT_FOUND_ERROR)

    # 方法功能：按租户和订单号读取支付或退款列表，并按与 PostgreSQL 一致的规则格式化与排序。
    def read_order_records(
        self,
        order_id: str,
        tenant_id: str,
        collection_name: str,
        required_fields: tuple,
        id_field: str,
        optional_fields: tuple = (),
    ) -> dict:
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
            with self.data_file.open("r", encoding="utf-8") as file:
                # 读取普通字典和列表，不连接数据库。
                business_data = json.load(file)
        # 文件不存在或没有读取权限时进入这个分支。
        except OSError:
            # 不向用户暴露文件路径详情。
            return tool_result(False, error="读取业务数据文件失败，请检查文件路径或权限。")
        # 文件编码或 JSON 语法错误时进入这个分支。
        except (UnicodeError, json.JSONDecodeError):
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
            # 检查可选字段：缺失或 None 均合法，有值时必须是非空字符串。
            for field in optional_fields:
                # 读取当前可选字段的值。
                optional_value = record.get(field)
                # 有值时校验类型和空白，保证与数据库列约束一致。
                if optional_value is not None and (not isinstance(optional_value, str) or not optional_value.strip()):
                    # 明确指出无效的可选字段。
                    return tool_result(False, error=f"业务数据格式错误：{collection_name} 可选字段 {field} 必须是非空字符串或空值。")
            # 使用与 PostgreSQL 相同的规则校验并统一金额与时间格式。
            try:
                # 金额统一格式化为两位小数字符串。
                normalized_amount = format_amount(record["amount"])
                # 更新时间统一格式化为 +08:00 秒级 ISO 字符串。
                normalized_updated_at = format_updated_at(record["updated_at"])
            # 金额或时间不合法时直接报错，不把脏数据当成合法记录。
            except ValueError:
                # 指出当前集合的金额或时间格式问题。
                return tool_result(False, error=f"业务数据格式错误：{collection_name} 金额或更新时间格式无效。")
            # 租户和订单号必须同时匹配，不能混入其他租户的同号记录。
            if record["tenant_id"] == clean_tenant_id and record["order_id"] == clean_order_id:
                # 复制匹配记录，保留原来的业务字段。
                data = dict(record)
                # 写入与 PostgreSQL 一致的两位小数金额字符串。
                data["amount"] = normalized_amount
                # 写入与 PostgreSQL 一致的 +08:00 更新时间字符串。
                data["updated_at"] = normalized_updated_at
                # 可选字段缺失时统一补 None，与 PostgreSQL 返回结构保持一致。
                for field in optional_fields:
                    # 原记录不含该键时显式写入 None。
                    if field not in data:
                        # 保证两种数据源的退款字典键集合一致。
                        data[field] = None
                # 标记当前查询的数据来源。
                data["source"] = "json"
                # 收集所有匹配记录，而不是只返回第一条。
                records.append(data)
        # 按实际时间点与记录编号升序排列，与 PostgreSQL ORDER BY 保持严格一致。
        records.sort(key=lambda item: (datetime.fromisoformat(item["updated_at"]), item[id_field]))
        # 没有匹配记录时也算查询成功，data 为 []，不是 Tool 执行失败。
        return tool_result(True, data=records)

    # 方法功能：只读查询当前租户的订单支付记录，不执行支付。
    def get_payment(self, order_id: str, tenant_id: str) -> dict:
        # 规定支付记录需要的字段，金额保持字符串。
        required_fields = ("tenant_id", "order_id", "payment_id", "status", "amount", "currency", "method", "updated_at")
        # 复用普通函数读取 payments 列表，按更新时间和 payment_id 升序返回。
        return self.read_order_records(order_id, tenant_id, "payments", required_fields, id_field="payment_id")

    # 方法功能：只读查询当前租户的订单退款记录，不发起退款。
    def get_refund(self, order_id: str, tenant_id: str) -> dict:
        # payment_id 可以没有，但退款本身的标识、金额、原因和时间必须存在。
        required_fields = ("tenant_id", "order_id", "refund_id", "status", "amount", "currency", "reason", "updated_at")
        # 复用普通函数读取 refunds 列表，按更新时间和 refund_id 升序返回；可选 payment_id 缺失时统一为 None。
        return self.read_order_records(
            order_id, tenant_id, "refunds", required_fields, id_field="refund_id", optional_fields=("payment_id",),
        )


# 方法功能：按 BUSINESS_DATA_SOURCE 显式创建 JSON 或 PostgreSQL 业务存储对象，不连接数据库。
def create_business_store(settings: Settings | None = None, data_file: Path | None = None):
    # 未显式传入配置时，从环境变量、.env.db 与 .env 读取配置。
    if settings is None:
        # 只加载配置，不建表、不连库。
        settings = load_settings()
    # JSON 模式继续读取本地模拟文件。
    if settings.business_data_source == "json":
        # 优先使用调用方显式指定的文件路径。
        if data_file is not None:
            # 显式传入的路径用于离线调试或自定义样例。
            target_file = Path(data_file)
        # 其次使用配置中的 BUSINESS_DATA_FILE。
        elif settings.business_data_file.strip():
            # 支持通过环境变量覆盖样例文件路径。
            target_file = Path(settings.business_data_file.strip())
        # 默认读取项目 data/business_demo.json。
        else:
            # 保持既有课程默认路径不变。
            target_file = DEFAULT_DATA_FILE
        # 返回本地 JSON 只读查询器。
        return JsonBusinessStore(target_file)
    # PostgreSQL 模式使用独立的业务只读连接串，不复用 RAG 的 DATABASE_URL。
    if settings.business_data_source == "postgres":
        # 构造只读数据库查询器，此时不主动连接数据库。
        return PostgresBusinessStore(settings.business_database_url)
    # 明确拒绝未知数据源，防止配置拼写错误时悄悄回退。
    raise ValueError("BUSINESS_DATA_SOURCE 只能是 json 或 postgres")


# 方法功能：解析本次查询应使用的业务存储，兼容旧的 data_file 参数和新的配置开关。
def resolve_business_store(data_file: Path | None = None, store=None):
    # 调用方已经显式传入存储对象时直接使用。
    if store is not None:
        # 服务层与离线替身可直接注入同一个存储实例。
        return store
    # 调用方显式指定了 JSON 文件路径时，按指定文件读取。
    if data_file is not None:
        # 兼容既有工作流与离线文件测试调用方式。
        return JsonBusinessStore(Path(data_file))
    # 默认按当前 BUSINESS_DATA_SOURCE=json|postgres 选择数据源。
    return create_business_store()


# 方法功能：根据可信入口提供的租户和订单号，只读查询订单；支持 json 与 postgres 两种数据源。
def get_order(order_id: str, tenant_id: str, data_file: Path | None = None, store=None) -> dict:
    # 选中当前配置或调用方指定的只读数据源。
    business_store = resolve_business_store(data_file=data_file, store=store)
    # 保持参数与返回格式在两种数据源中一致。
    return business_store.get_order(order_id, tenant_id)


# 方法功能：只读查询当前租户的订单支付记录列表，不执行支付；支持 json 与 postgres 两种数据源。
def get_payment(order_id: str, tenant_id: str, data_file: Path | None = None, store=None) -> dict:
    # 选中当前配置或调用方指定的只读数据源。
    business_store = resolve_business_store(data_file=data_file, store=store)
    # 保持列表语义、空列表成功约定和字段格式一致。
    return business_store.get_payment(order_id, tenant_id)


# 方法功能：只读查询当前租户的订单退款记录列表，不发起退款；支持 json 与 postgres 两种数据源。
def get_refund(order_id: str, tenant_id: str, data_file: Path | None = None, store=None) -> dict:
    # 选中当前配置或调用方指定的只读数据源。
    business_store = resolve_business_store(data_file=data_file, store=store)
    # 保持列表语义、可选 payment_id 与字段格式一致。
    return business_store.get_refund(order_id, tenant_id)
