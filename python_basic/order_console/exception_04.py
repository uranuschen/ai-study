from order_exception import OrderException


def check_price(price):

    if price <= 0:
        raise OrderException("订单价格必须大于0")

    print(f"价格合法：{price}")


try:
    check_price(-100)

except OrderException as e:
     print(e)
