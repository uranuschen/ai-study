def check_price(price):
    if price<0:
        raise ValueError("订单价格必须大于0")

    print(f"价格合法：{price}")


try:
    check_price(8000)
    check_price(-100)

except ValueError as e:
    print(e)