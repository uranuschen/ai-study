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
        for order in self.orders:
            if order.order_id == order_id:
                return order

        return None

    def delete_order(self, order_id):
        for order in self.orders:
            if order.order_id == order_id:
                self.orders.remove(order)
                return True

        return False

    def get_total_price(self):
        total = 0

        for order in self.orders:
            total += order.price

        return total

    def update_order(self, order_id, name, price):
         for order in self.orders:
            if order.order_id == order_id:
                 order.name = name
                 order.price = price
                 return True
         return False


service = OrderService()

service.add_order(Order(1001, "MacBook", 8000))
service.add_order(Order(1002, "iPhone", 5000))
service.add_order(Order(1003, "AirPods", 1500))

result = service.update_order(1002, "iPhone Pro", 6500)

print(result)

order = service.find_order(1002)

print(order.order_id, order.name, order.price)