from order_file import load_orders,save_orders
from order_service import add_order,update_order,query_order,del_order


# 读取json数据
orders = load_orders()



while True:
    print("========== 订单管理 ==========")
    print("1. 查看订单")
    print("2. 新增订单")
    print("3. 查询订单")
    print("4. 修改订单")
    print("5. 删除订单")
    print("0. 退出")

    choice = input("请选择：")

    if choice == "1":
        for order in orders:
            print(order)

    elif choice == "2":
        add_order(orders)

    elif choice == "3":
        query_order(orders)

    elif choice == "4":
        update_order()

    elif choice == "5":
        del_order(orders)

    elif choice == "0":
        print("程序退出")
        break

    else:
        print("输入错误")
