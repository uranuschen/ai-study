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

    def find_order(self, order_id):
        for so in self.orders:
            if order_id==so.order_id:
                return so

        return None


service = OrderService()
service.add_order(Order(1001, "MacBook", 8000))
service.add_order(Order(1002, "iPhone", 5000))
service.add_order(Order(1003, "AirPods", 1500))


order = service.find_order(1002)

if order is not None:
    print(order.order_id, order.name, order.price)
else:
    print("订单不存在")