from order_file import save_orders

#新增
def add_order(orders):
    order_id= input("输入orderid")
    for order in orders:
        if order["order_id"]==order_id:
            print("订单号已存在")
            return
    try:
        amount = float(input("输入金额"))
    except ValueError:
        print("金额格式错误")
        return

    new_order={
        "order_id":order_id,
        "amount": amount,
        "status": input("请输入状态")
    }
    orders.append(new_order)
    save_orders(orders)


#查询
def query_order(orders):
    order_id= input("输入orderid")

    for item in orders:
        if item["order_id"]==order_id:
            print(item)
            return
    print("订单不存在")

# 删除
def del_order(orders):
    order_id = input("输入删除订单号：")
    for item in orders:
        if item["order_id"] == order_id:
            orders.remove(item)
            save_orders(orders)
            return

    print("订单不存在")

# 修改
def update_order(orders):
    order_id=input("修改的订单号：")
    for order in orders:
        if order["order_id"]==order_id:
            order["amount"] = float(input("请输入新金额："))
            order["status"] = input("请输入新状态：")
            save_orders(orders)
            return

    print("订单不存在")