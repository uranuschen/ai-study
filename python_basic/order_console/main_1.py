from order_exception import OrderException


def create_order(order_id, amount):
    if amount<=0:
        raise OrderException("订单金额必须大于0")

    return f"订单{order_id} 创建成功，金额：{amount}"


try:
    result = create_order("A1001", 99.9)
    print(result)

    result = create_order("A1002", 0)
    print(result)

except OrderException as e:
    print(f"订单异常：{e}")
