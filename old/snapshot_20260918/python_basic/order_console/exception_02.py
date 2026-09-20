try:
    total = int(input("请输入订单总金额："))
    count = int(input("请输入订单数量："))

    average = total / count

    print(f"平均金额：{average}")

except ValueError as e:
    print("数字格式错误")
    print(e)

except ZeroDivisionError as e:
    print("订单数量不能为0")
    print(e)
