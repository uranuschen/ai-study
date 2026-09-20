from order import Order
from order_service import OrderService

service = OrderService()

service.add_order(Order(1001, "MacBook", 8000))
service.add_order(Order(1002, "iPhone", 5000))

order = service.find_order(1002)

print(order.order_id, order.name, order.price)
