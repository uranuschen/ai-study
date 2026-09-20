from order import Order

class OrderService:

    def __init__(self):
        self.orders = []

    def add_order(self, order):
        self.orders.append(order)

    def create_order(self, order_id, name, price):
        self.orders.append(Order(order_id,name,price))
       
        
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