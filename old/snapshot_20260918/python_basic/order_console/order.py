class Order:

    def __init__(self, order_id, amount, status):
        self.order_id = order_id
        self.amount = amount
        self.status = status

    def show_info(self):
        print(self.order_id,self.amount,self.status)

    
    def to_dict(self):
        return{
            "order_id":self.order_id,
            "amount": self.amount,
            "status": self.status
        }

order1 = Order("A1001", 99.9, "已创建")
order1.show_info()
print(order1.to_dict())