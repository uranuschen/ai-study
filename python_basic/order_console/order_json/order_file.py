import json
from pathlib import Path

FILE_PATH = Path(__file__).parent / "orders.json"

def load_orders():
    with open(FILE_PATH,"r") as file:
        orders = json.load(file)
    return orders

def save_orders(orders):
    with open(FILE_PATH,"w") as file:
        # 要保存的数据，保存到那个文件，中文存中文，缩进四格
        json.dump(orders,file,ensure_ascii=False,indent=4)

