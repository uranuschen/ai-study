class Order:
    def __init__(self, order_id, name, price):
        self.order_id = order_id
        self.name = name
        self.price = price


class OrderService:

    def __init__(self):
        self.orders = []

    def add_order(self, order):
        self.orders.append(order)


service = OrderService()

order1 = Order(1001, "MacBook", 8000)
order2 = Order(1002, "iPhone", 5000)

service.add_order(order1)
service.add_order(order2)

print(len(service.orders))