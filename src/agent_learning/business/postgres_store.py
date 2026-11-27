# 导入带时区时间处理工具，将数据库时间统一转换为与 JSON 一致的 ISO 字符串。
from datetime import datetime, timedelta, timezone
# 导入精确十进制类型，避免把业务金额转成浮点数。
from decimal import Decimal, InvalidOperation


# 统一使用 +08:00 时区展示业务更新时间，与本地 JSON 样例保持一致。
DISPLAY_TIMEZONE = timezone(timedelta(hours=8))

# 订单不存在或跨租户不可读时使用固定提示，保持 JSON 与 PostgreSQL 一致。
ORDER_NOT_FOUND_ERROR = "订单不存在或当前租户不可读取。"
# 数据库账号权限不足时返回固定提示，供上层识别权限拒绝。
PERMISSION_DENIED_ERROR = "无权读取业务数据，请检查只读账号权限。"
# 数据库查询超过时限时返回固定提示，不回显底层驱动消息。
QUERY_TIMEOUT_ERROR = "业务数据查询超时，请稍后重试。"
# 切换到 postgres 但未配置独立只读连接串时给出明确配置提示。
MISSING_DB_URL_ERROR = "未配置业务只读数据库连接，请在 .env.db 设置 BUSINESS_DATABASE_URL。"
# 其他数据库连接或执行异常统一转为安全提示，不泄露 SQL、表名或账号信息。
DATABASE_QUERY_ERROR = "业务数据库查询失败，请检查只读连接配置或数据库状态。"

# 固定订单查询 SQL：仅按租户和订单号精确查询单条记录，不做任何 SQL 拼接。
ORDER_SQL = (
    "SELECT tenant_id, order_id, status, amount, currency, updated_at "
    "FROM biz.orders "
    "WHERE tenant_id = %s AND order_id = %s"
)

# 固定支付查询 SQL：按租户和订单号返回全部记录，并按更新时间和编号稳定排序。
PAYMENT_SQL = (
    "SELECT tenant_id, order_id, payment_id, status, amount, currency, method, updated_at "
    "FROM biz.payments "
    "WHERE tenant_id = %s AND order_id = %s "
    "ORDER BY updated_at ASC, payment_id ASC"
)

# 固定退款查询 SQL：按租户和订单号返回全部记录，payment_id 允许为空，按时间和编号稳定排序。
REFUND_SQL = (
    "SELECT tenant_id, order_id, payment_id, refund_id, status, amount, currency, reason, updated_at "
    "FROM biz.refunds "
    "WHERE tenant_id = %s AND order_id = %s "
    "ORDER BY updated_at ASC, refund_id ASC"
)


# 方法功能：构造与现有业务 Tool 完全一致的三字段返回字典。
def make_tool_result(success: bool, data=None, error=None) -> dict:
    # 保持 success、data、error 三个固定字段不变。
    return {"success": success, "data": data, "error": error}


# 方法功能：校验必填文本列为非空字符串。
def read_required_text(row: dict, field: str) -> str:
    # 取出数据库行中的对应字段值。
    value = row.get(field)
    # 字段缺失、类型不符或全为空白都视为异常数据。
    if not isinstance(value, str) or not value.strip():
        # 由上层统一转换为安全错误提示。
        raise ValueError("业务记录缺少有效的文本字段。")
    # 保留数据库中的原始业务文案。
    return value


# 方法功能：校验可选文本列，允许 None，非空时必须是有效字符串。
def read_optional_text(row: dict, field: str) -> str | None:
    # 取出可选字段的值。
    value = row.get(field)
    # 退款没有关联支付记录时统一返回 None。
    if value is None:
        # 明确保留空值，与 JSON 模式对齐。
        return None
    # 非空值必须是非空白字符串。
    if not isinstance(value, str) or not value.strip():
        # 拒绝错误类型或纯空白内容。
        raise ValueError("业务记录的可选文本字段无效。")
    # 返回原始业务编号。
    return value


# 方法功能：把数据库精确数值统一格式化为两位小数字符串，避免浮点误差与 JSON 序列化失败。
def format_amount(value) -> str:
    # 拒绝 None、布尔值和二进制浮点数。
    if value is None or isinstance(value, (bool, float)):
        # 防止金额精度丢失。
        raise ValueError("业务金额类型无效。")
    # 将 Decimal、整数或数字字符串解析为精确十进制数。
    try:
        # 先转为字符串再解析，确保 Decimal 与整型行为一致。
        number = Decimal(str(value).strip())
    # 无法解析为数字时视为无效记录。
    except InvalidOperation:
        # 交给边界转换为固定错误。
        raise ValueError("业务金额格式无效。") from None
    # 拒绝 NaN、无穷大或负数金额。
    if number.is_nan() or number.is_infinite() or number < 0:
        # 业务金额必须是非负有限值。
        raise ValueError("业务金额范围无效。")
    # 固定保留两位小数并转为字符串，与本地 JSON 格式保持一致。
    return f"{number.quantize(Decimal('0.01')):.2f}"


# 方法功能：把带时区的数据库时间统一格式化为 +08:00 秒级 ISO 字符串。
def format_updated_at(value) -> str:
    # 处理 psycopg2 返回的 datetime 对象。
    if isinstance(value, datetime):
        # 业务表使用 timestamptz，必须携带时区信息。
        if value.tzinfo is None:
            # 拒绝没有时区的时间值。
            raise ValueError("业务更新时间缺少时区。")
        # 统一转换为 +08:00 且精确到秒，便于与 JSON 样例逐字段对照。
        return value.astimezone(DISPLAY_TIMEZONE).isoformat(timespec="seconds")
    # 兼容替身连接返回的带时区 ISO 字符串。
    if isinstance(value, str) and value.strip():
        # 解析字符串并校验其时区信息。
        try:
            # 标准库解析 ISO 8601 时间文本。
            parsed = datetime.fromisoformat(value.strip())
        # 格式非法时报错。
        except ValueError:
            # 交给外层统一隐藏内部细节。
            raise ValueError("业务更新时间文本无效。") from None
        # 同样要求携带时区偏移。
        if parsed.tzinfo is None:
            # 避免无时区时间产生歧义。
            raise ValueError("业务更新时间缺少时区。")
        # 统一输出为 +08:00 秒级 ISO 文本。
        return parsed.astimezone(DISPLAY_TIMEZONE).isoformat(timespec="seconds")
    # 其他类型一律视为格式错误。
    raise ValueError("业务更新时间类型无效。")


# 方法功能：把订单数据库行转换为与 JSON 模式一致的业务字典。
def normalize_order_row(row: dict) -> dict:
    # 逐字段整理并标明数据来自只读 PostgreSQL。
    return {
        "tenant_id": read_required_text(row, "tenant_id"),
        "order_id": read_required_text(row, "order_id"),
        "status": read_required_text(row, "status"),
        "amount": format_amount(row.get("amount")),
        "currency": read_required_text(row, "currency"),
        "updated_at": format_updated_at(row.get("updated_at")),
        "source": "postgres",
    }


# 方法功能：把支付数据库行转换为与 JSON 模式一致的业务字典。
def normalize_payment_row(row: dict) -> dict:
    # 保留支付记录全部字段，金额与时间统一为字符串。
    return {
        "tenant_id": read_required_text(row, "tenant_id"),
        "order_id": read_required_text(row, "order_id"),
        "payment_id": read_required_text(row, "payment_id"),
        "status": read_required_text(row, "status"),
        "amount": format_amount(row.get("amount")),
        "currency": read_required_text(row, "currency"),
        "method": read_required_text(row, "method"),
        "updated_at": format_updated_at(row.get("updated_at")),
        "source": "postgres",
    }


# 方法功能：把退款数据库行转换为与 JSON 模式一致的业务字典。
def normalize_refund_row(row: dict) -> dict:
    # payment_id 为可选字段，缺失时统一为 None。
    return {
        "tenant_id": read_required_text(row, "tenant_id"),
        "order_id": read_required_text(row, "order_id"),
        "payment_id": read_optional_text(row, "payment_id"),
        "refund_id": read_required_text(row, "refund_id"),
        "status": read_required_text(row, "status"),
        "amount": format_amount(row.get("amount")),
        "currency": read_required_text(row, "currency"),
        "reason": read_required_text(row, "reason"),
        "updated_at": format_updated_at(row.get("updated_at")),
        "source": "postgres",
    }


# 方法功能：把数据库异常转换为固定业务错误提示，不暴露 SQL、表名或连接串。
def map_database_error(error: Exception) -> str:
    # 明确未配置业务只读连接串时返回配置提示。
    if isinstance(error, ValueError) and str(error) == MISSING_DB_URL_ERROR:
        # 提示在 .env.db 中设置独立业务连接串。
        return MISSING_DB_URL_ERROR
    # 捕获 PostgreSQL 权限不足错误码 42501 或显式 PermissionError。
    if isinstance(error, PermissionError) or getattr(error, "pgcode", None) == "42501":
        # 供 MCP 与上层明确区分权限拒绝。
        return PERMISSION_DENIED_ERROR
    # 捕获 PostgreSQL 语句超时错误码 57014 或显式 TimeoutError。
    if isinstance(error, TimeoutError) or getattr(error, "pgcode", None) == "57014":
        # 告知调用方本次查询超时，不自动重试。
        return QUERY_TIMEOUT_ERROR
    # 其他连接、查询或数据转换错误统一返回安全文案。
    return DATABASE_QUERY_ERROR


# 类职责：使用固定 SQL、参数绑定、租户过滤和只读事务查询 PostgreSQL 业务表；不自动建表或初始化。
class PostgresBusinessStore:
    # 方法功能：保存业务只读连接配置与超时参数，构造对象时不连接数据库。
    def __init__(
        self,
        database_url: str,
        connect_timeout: int = 3,
        statement_timeout_ms: int = 4000,
        connect_fn=None,
    ) -> None:
        # 校验建连超时为正整数，避免无效配置。
        if not isinstance(connect_timeout, int) or isinstance(connect_timeout, bool) or connect_timeout <= 0:
            # 拒绝非法建连超时设置。
            raise ValueError("connect_timeout 必须是正整数。")
        # 校验数据库语句超时为正整数，确保慢查询可在库端中止。
        if not isinstance(statement_timeout_ms, int) or isinstance(statement_timeout_ms, bool) or statement_timeout_ms <= 0:
            # 拒绝非法语句超时设置。
            raise ValueError("statement_timeout_ms 必须是正整数。")
        # 标明当前存储实现的数据来源名称。
        self.source: str = "postgres"
        # 保存独立业务只读连接串，打印对象时隐藏。
        self.database_url: str = database_url
        # 保存建连等待时间（秒）。
        self.connect_timeout: int = connect_timeout
        # 保存单次查询的数据库端超时时间（毫秒）。
        self.statement_timeout_ms: int = statement_timeout_ms
        # 可选自定义连接函数，供离线替身验证使用；正常运行时调用 psycopg2.connect。
        self.connect_fn = connect_fn

    # 方法功能：打印存储对象时隐藏数据库连接串，避免泄露密码。
    def __repr__(self) -> str:
        # 仅说明是否配置了连接串和超时参数。
        return (
            "PostgresBusinessStore("
            f"database_url={'<configured>' if self.database_url else '<empty>'}, "
            f"connect_timeout={self.connect_timeout}, "
            f"statement_timeout_ms={self.statement_timeout_ms}"
            ")"
        )

    # 方法功能：建立只读会话连接；设置失败时立即关闭连接避免泄漏。
    def open_connection(self):
        # 未配置业务只读连接串时不尝试连接，也不自动回退到 JSON。
        if not isinstance(self.database_url, str) or not self.database_url.strip():
            # 抛出明确的配置缺失错误，由调用方转为受控结果。
            raise ValueError(MISSING_DB_URL_ERROR)
        # 离线验证传入了自定义连接函数时直接使用它。
        if self.connect_fn is not None:
            # 仍传递连接串和超时参数，便于离线验证检查参数传递。
            connection = self.connect_fn(self.database_url, connect_timeout=self.connect_timeout)
        # 正常运行时按需导入 PostgreSQL 驱动。
        else:
            import psycopg2
            # 创建带连接超时的数据库连接。
            connection = psycopg2.connect(self.database_url, connect_timeout=self.connect_timeout)
        # 把会话设为只读模式，失败时确保关闭连接。
        try:
            # 在会话层阻止任何写入操作。
            connection.set_session(readonly=True)
            # 由调用方在 finally 中关闭连接。
            return connection
        # 会话设置失败时不遗留打开的连接。
        except Exception:
            # 立即释放已建立的连接。
            connection.close()
            # 把异常交给上层统一映射为固定提示。
            raise

    # 方法功能：在显式只读事务与语句超时保护下执行固定参数化查询。
    def run_readonly_query(self, sql: str, params: tuple, fetch_one: bool):
        # 每次查询按需建立只读连接。
        connection = self.open_connection()
        # 无论成功还是失败，退出时都显式关闭连接。
        try:
            # 使用连接事务上下文，结束时由驱动收尾事务。
            with connection:
                # 真实连接使用字典游标，离线替身直接使用默认游标。
                if self.connect_fn is None:
                    from psycopg2.extras import RealDictCursor
                    # RealDictCursor 直接按列名返回字典行。
                    cursor_context = connection.cursor(cursor_factory=RealDictCursor)
                # 离线替身游标直接返回模拟字典行。
                else:
                    # 避免离线环境硬依赖 psycopg2 内部游标类型。
                    cursor_context = connection.cursor()
                # 使用游标上下文自动关闭游标。
                with cursor_context as cursor:
                    # 在事务第一条语句显式声明只读事务。
                    cursor.execute("SET TRANSACTION READ ONLY")
                    # 为当前事务设置数据库端超时，避免超时后库端残留慢查询。
                    cursor.execute("SELECT set_config('statement_timeout', %s, true)", (f"{self.statement_timeout_ms}ms",))
                    # 执行固定 SQL 并绑定参数，不拼接用户输入。
                    cursor.execute(sql, params)
                    # 订单查询只取单条记录。
                    if fetch_one:
                        # 未命中时返回 None。
                        return cursor.fetchone()
                    # 支付和退款查询返回全部匹配记录列表。
                    return cursor.fetchall()
        # 始终关闭数据库连接，不残留连接或事务。
        finally:
            # 释放底层套接字资源。
            connection.close()

    # 方法功能：按可信租户和订单号只读查询单条订单。
    def get_order(self, order_id: str, tenant_id: str) -> dict:
        # 空订单号不进入数据库查询。
        if not isinstance(order_id, str) or not order_id.strip():
            # 与 JSON 模式保持完全一致的参数校验提示。
            return make_tool_result(False, error="请输入非空订单号。")
        # 租户必须由服务端可信入口提供。
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            # 缺少租户身份时直接拒绝查询。
            return make_tool_result(False, error="缺少租户身份，无法查询订单。")
        # 与 JSON 模式一致：订单号去空格并转大写。
        clean_order_id = order_id.strip().upper()
        # 与 JSON 模式一致：租户去两端空格并保留大小写。
        clean_tenant_id = tenant_id.strip()
        # 执行固定只读查询，并把数据库异常转换为固定安全提示。
        try:
            # 同时绑定租户和订单号两个条件。
            row = self.run_readonly_query(ORDER_SQL, (clean_tenant_id, clean_order_id), fetch_one=True)
            # 未命中或不属当前租户时返回统一业务失败，不区分两种原因。
            if row is None:
                # 与 JSON 模式返回同一句失败说明。
                return make_tool_result(False, error=ORDER_NOT_FOUND_ERROR)
            # 统一转换金额、时间并补充 source=postgres。
            data = normalize_order_row(dict(row))
            # 查询成功时 error 为 None。
            return make_tool_result(True, data=data)
        # 捕获数据库权限、超时、配置或数据格式异常。
        except Exception as error:
            # 不向调用方暴露 SQL、表名、账号或驱动堆栈。
            return make_tool_result(False, error=map_database_error(error))

    # 方法功能：按可信租户和订单号只读查询全部支付记录；无记录返回成功空列表。
    def get_payment(self, order_id: str, tenant_id: str) -> dict:
        # 空订单号不进入数据库查询。
        if not isinstance(order_id, str) or not order_id.strip():
            # 保持与 JSON 模式一致的参数错误文案。
            return make_tool_result(False, error="请输入非空订单号。")
        # 租户必须由服务端可信入口提供。
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            # 保持与 JSON 模式一致的租户校验文案。
            return make_tool_result(False, error="缺少租户身份，无法查询业务记录。")
        # 整理订单号与租户标识。
        clean_order_id = order_id.strip().upper()
        # 保留租户原始大小写。
        clean_tenant_id = tenant_id.strip()
        # 在只读事务中读取该租户下的全部匹配支付记录。
        try:
            # 固定 SQL 已按时间和支付编号升序排列。
            rows = self.run_readonly_query(PAYMENT_SQL, (clean_tenant_id, clean_order_id), fetch_one=False)
            # 逐条转换为统一字符串格式并标明 source=postgres。
            records = [normalize_payment_row(dict(row)) for row in rows]
            # 无匹配记录时返回成功的空列表，不是查询失败。
            return make_tool_result(True, data=records)
        # 数据库失败绝不能伪装成空列表。
        except Exception as error:
            # 返回安全的固定失败提示。
            return make_tool_result(False, error=map_database_error(error))

    # 方法功能：按可信租户和订单号只读查询全部退款记录；无记录返回成功空列表。
    def get_refund(self, order_id: str, tenant_id: str) -> dict:
        # 空订单号不进入数据库查询。
        if not isinstance(order_id, str) or not order_id.strip():
            # 保持与 JSON 模式一致的参数错误文案。
            return make_tool_result(False, error="请输入非空订单号。")
        # 租户必须由服务端可信入口提供。
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            # 保持与 JSON 模式一致的租户校验文案。
            return make_tool_result(False, error="缺少租户身份，无法查询业务记录。")
        # 整理订单号与租户标识。
        clean_order_id = order_id.strip().upper()
        # 保留租户原始大小写。
        clean_tenant_id = tenant_id.strip()
        # 在只读事务中读取该租户下的全部匹配退款记录。
        try:
            # 固定 SQL 已按时间和退款编号升序排列。
            rows = self.run_readonly_query(REFUND_SQL, (clean_tenant_id, clean_order_id), fetch_one=False)
            # 逐条转换字段并统一保留可选的 payment_id。
            records = [normalize_refund_row(dict(row)) for row in rows]
            # 无匹配退款记录属于正常查询成功。
            return make_tool_result(True, data=records)
        # 数据库失败时明确返回失败结果。
        except Exception as error:
            # 隐藏内部异常详情，返回安全提示。
            return make_tool_result(False, error=map_database_error(error))
