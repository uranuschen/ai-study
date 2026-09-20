from sentence_transformers import SentenceTransformer
from pgvector.psycopg2 import register_vector

from db import get_connection


# 1. 加载模型
model = SentenceTransformer(
    "BAAI/bge-small-zh-v1.5"
)


# 2. 用户问题
question = "退款为什么失败？"


# 3. 把问题转成向量
question_embedding = model.encode(question)


# 4. 连接数据库
conn = get_connection()

try:

    register_vector(conn)

    with conn.cursor() as cursor:

        sql = """
        SELECT
            id,
            content,
            embedding <=> %s AS distance
        FROM documents
        ORDER BY embedding <=> %s
        LIMIT 3
        """

        cursor.execute(
            sql,
            (
                question_embedding,
                question_embedding
            )
        )

        rows = cursor.fetchall()

        for row in rows:
            print("id:", row[0])
            print("content:", row[1])
            print("distance:", row[2])
            print("--------------------")

        # 把 Top-K 检索结果拼成上下文
        context = "\n".join(
            row[1]
            for row in rows
        )

        print("context:")
        print(context)

finally:
    conn.close()