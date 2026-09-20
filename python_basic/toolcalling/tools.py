from db import get_connection
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import time
import logging

#log 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger(__name__)


def tool_result(success: bool, data=None, error=None):
    return {
        "success": success,
        "data": data,
        "error": error
    }

# 查询订单
def get_order(order_id: str):

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            sql = """
            SELECT order_id, amount, status
            FROM orders
            WHERE order_id = %s
            """

            cursor.execute(
                sql,
                (order_id,)
            )

            row = cursor.fetchone()

            if row is None:
                return tool_result(
                    success=False,
                    error="订单不存在"
                )

            return tool_result(
                success=True,
                data={
                    "order_id": row[0],
                    "amount": float(row[1]),
                    "status": row[2]
                }
            )
    except Exception as e:
        return tool_result(
            success=False,
            error=str(e)
        )
    
    finally:
        conn.close()


# 取消订单
def cancel_order(order_id: str):

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            # 先查订单
            cursor.execute(
                """
                SELECT order_id, amount, status
                FROM orders
                WHERE order_id = %s
                """,
                (order_id,)
            )

            row = cursor.fetchone()

            if row is None:
                return tool_result(
                success=False,
                error="订单不存在"
                )

            # 已发货不能取消
            if row[2] == "已发货":
                return tool_result(
                    success=False,
                    error="订单已发货，不能直接取消"
                )

            # 更新订单状态
            cursor.execute(
                """
                UPDATE orders
                SET status = '已取消'
                WHERE order_id = %s
                """,
                (order_id,)
            )

            conn.commit()

            return tool_result(
                success=True,
                data={
                    "order_id": order_id,
                    "message": "订单取消成功"
                }
            )

    except Exception as e:

        conn.rollback()

        return tool_result(
            success=False,
            error=str(e)
        )

    finally:
        conn.close()


# 查询用户
def get_user(user_id: str):

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            sql = """
            SELECT user_id, name, phone, level
            FROM users
            WHERE user_id = %s
            """

            cursor.execute(
                sql,
                (user_id,)
            )

            row = cursor.fetchone()

            if row is None:
                return {
                    "success": False,
                    "message": "用户不存在"
                }

            return tool_result(
                success=True,
                data={
                    "user_id": row[0],
                    "name": row[1],
                    "phone": row[2],
                    "level": row[3]
                }
            )

    except Exception as e:

        return tool_result(
            success=False,
            error=str(e)
        )

    finally:
        conn.close()

# 查询支付信息
def get_payment(order_id: str):

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            sql = """
            SELECT payment_id, order_id, amount, status, pay_method
            FROM payments
            WHERE order_id = %s
            """

            cursor.execute(
                sql,
                (order_id,)
            )

            row = cursor.fetchone()

            if row is None:
                return tool_result(
                    success=False,
                    error="支付信息不存在"
            )

            return tool_result(
                success=True,
                data={
                    "payment_id": row[0],
                    "order_id": row[1],
                    "amount": float(row[2]),
                    "status": row[3],
                    "pay_method": row[4]
                }
            )

    except Exception as e:

        return tool_result(
            success=False,
            error=str(e)
        )

    finally:
        conn.close()

# 查询退款信息
def get_refund(order_id: str):

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            sql = """
            SELECT
                refund_id,
                order_id,
                payment_id,
                amount,
                status,
                reason
            FROM refunds
            WHERE order_id = %s
            """

            cursor.execute(
                sql,
                (order_id,)
            )

            row = cursor.fetchone()

            if row is None:
                return tool_result(
                    success=False,
                    error="退款信息不存在"
                )

            return tool_result(
                success=True,
                data={
                    "refund_id": row[0],
                    "order_id": row[1],
                    "payment_id": row[2],
                    "amount": float(row[3]),
                    "status": row[4],
                    "reason": row[5]
                }
            )

    except Exception as e:

        return tool_result(
            success=False,
            error=str(e)
        )

    finally:
        conn.close()

# 工具集
TOOL_REGISTRY = {
    "get_order": get_order,
    "cancel_order": cancel_order,
    "get_user": get_user,
    "get_payment": get_payment,
    "get_refund": get_refund
}

# 禁止工具名
FORBIDDEN_TOOLS = {
    "execute_sql",
    "query_sql",
    "run_sql",
    "raw_sql",
    "query_database"
}

#分发 注意**arguments方式，自动匹配的参数
def dispatch_tool(tool_name: str, arguments: dict, timeout=3):
    if tool_name in FORBIDDEN_TOOLS:
        return tool_result(
            success=False,
            error=f"禁止执行高风险工具: {tool_name}"
        )
     
    if tool_name not in TOOL_REGISTRY:
        return tool_result(
            success=False,
            error=f"工具不允许执行: {tool_name}"
        )
    
    tool_func = TOOL_REGISTRY.get(tool_name)

    if tool_func is None:
        return tool_result(
            success=False,
            error=f"未知工具: {tool_name}"
        )
    # 加了with 要等主线程。
    executor = ThreadPoolExecutor(max_workers=1)

    start_time = time.time()

    logger.info(
        "开始执行工具 tool=%s args=%s",
        tool_name,
        arguments
    )

    try:
        future = executor.submit(
            tool_func,
            **arguments
        )

        result = future.result(timeout=timeout)

        cost = time.time() - start_time

        logger.info(
            "工具执行完成 tool=%s cost=%.3fs status=%s",
            tool_name,
            cost,
            "success" if result["success"] else "failed"
        )

        return result

    except TimeoutError:
        future.cancel()

        cost = time.time() - start_time

        logger.warning(
            "工具执行超时 tool=%s cost=%.3fs",
            tool_name,
            cost
        )

        return tool_result(
            success=False,
            error=f"工具执行超时: {tool_name}"
        )
    
    except TypeError as e:
        cost = time.time() - start_time

        logger.exception(
            "工具执行异常 tool=%s cost=%.3fs",
            tool_name,
            cost
        )

        return tool_result(
            success=False,
            error=f"工具参数错误: {str(e)}"
        )

    except Exception as e:
         
        cost = time.time() - start_time

        print(f"工具执行异常: {tool_name}")
        print(f"执行耗时: {cost:.3f} 秒")
        print("执行状态: error")
    
        return tool_result(
            success=False,
            error=f"工具执行异常: {str(e)}"
        )
    
    finally:
        # 主线程不要等线程池里的任务执行结束
        executor.shutdown(wait=False)


