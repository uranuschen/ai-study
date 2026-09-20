import os
import pymysql
from dotenv import load_dotenv

load_dotenv()


# 获取数据库连接
def get_connection():
    return pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password=os.getenv("MYSQL_PASSWORD"),
        database="ai_study",
        charset="utf8mb4"
    )