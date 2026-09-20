class product:

    def __init__(self,product_id,name,price):
        self.product_id = product_id
        self.name = name
        self.price = price

    def show(self):
        print(self.product_id,self.name,self.price)

    def to_dic(self):
        return{
              "product_id":self.product_id,
              "name": self.name,
              "price": self.price
        }


p1 = product("P1001", "MacBook", 9999)
p1.show()
print(p1.to_dic())
