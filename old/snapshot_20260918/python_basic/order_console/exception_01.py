try:
    text = input("请输入订单价格：")
    price = int(text)
    print(f"订单价格：{price}")
except ValueError:
    print("格格式错误")
