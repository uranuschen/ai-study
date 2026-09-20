class Order:
    def __init__(self, order_id, name, price):
        self.order_id = order_id
        self.name = name
        self.price = price

    def get_info(self):
        print(f"订单号：{self.order_id} 商品：{self.name} 价格：{self.price}")


order1 = Order(1001, "MacBook", 8000)
order2 = Order(1002, "iPhone", 5000)
order3 = Order(1003, "AirPods", 1500)

orders = []
orders.append(order1)
orders.append(order2)
orders.append(order3)


for o in orders:
    o.get_info()

total = 0
for o in orders:
    total+=o.price

print(f"总金额：{total}")