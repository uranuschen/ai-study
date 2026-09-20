from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
import json

# uvicorn main:app --reload Tomcat/内嵌服务器

# Spring Boot
app= FastAPI()

# dto
class Order(BaseModel):
    order_id: str
    amount: float
    status: str

#  @GetMapping("/")
@app.get("/")

#  Controller 方法  返回 JSON
def index():
    return {"msg": "running"}


def load_orders():
    with open("orders.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_orders(orders):
    with open("orders.json", "w", encoding="utf-8") as f:
        json.dump(
            orders,
            f,
            ensure_ascii=False,
            indent=2
        )

# 订单查询get
@app.get("/orders/{order_id}")
def query_order(order_id: str):
    orders = load_orders()

    for order in orders:
        if order["order_id"] == order_id:
            return order

    # throw     
    raise HTTPException(
        status_code=404,
        detail="订单不存在"
    )

# post PostMapping
@app.post("/orders")
def add_order(order: Order):

    orders = load_orders()

    for item in orders:
        if item["order_id"] == order.order_id:
            raise HTTPException(
                status_code=409,
                detail="订单已存在"
            )
        
    # DTO 转 Map/Dict
    orders.append(order.model_dump())

    save_orders(orders)

    return order


# 修改 put
@app.put("/orders/{order_id}")
def update_order(order_id: str, new_order: Order):

    orders = load_orders()

    for order in orders:
        if order["order_id"] == order_id:
            order["amount"] = new_order.amount
            order["status"] = new_order.status

            save_orders(orders)

            return order
    
    raise HTTPException(
        status_code=404,
        detail="订单不存在"
    )

# 删除
@app.delete("/orders/{order_id}")
def delete_order(order_id: str):

    orders = load_orders()

    for order in orders:
        if order["order_id"] == order_id:
            orders.remove(order)

            with open("orders.json", "w", encoding="utf-8") as f:
                # 写入文件  json数据，文件， ensure_ascii是中文  indent是缩进
                json.dump(orders, f, ensure_ascii=False, indent=2)

            return {"msg": "删除成功"}

        raise HTTPException(
        status_code=404,
        detail="订单不存在"
        )