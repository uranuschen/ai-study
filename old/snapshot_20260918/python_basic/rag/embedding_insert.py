from sentence_transformers import SentenceTransformer
from pgvector.psycopg2 import register_vector

from db import get_connection


documents = [
    "退款申请提交后，系统会检查订单是否已经支付。",
    "如果订单已经发货，部分商品可能无法直接退款。",
    "支付成功后，支付记录会保存支付渠道和支付金额。",
    "退款失败可能是由于支付渠道异常导致。",
    "用户可以通过订单号查询订单当前状态。",
    "订单取消成功后，系统会自动触发退款流程。",
    "退款记录包含退款金额、退款状态和退款时间。",
    "如果退款状态为处理中，需要等待支付平台返回结果。",
    "退款成功后，资金通常会原路退回用户账户。",
    "系统通过日志记录订单、支付和退款操作。"
]


# 加载 Embedding 模型
model = SentenceTransformer(
    "BAAI/bge-small-zh-v1.5"
)


# 一次性生成10个向量
embeddings = model.encode(documents)


conn = get_connection()

try:

    register_vector(conn)

    with conn.cursor() as cursor:

        for content, embedding in zip(documents, embeddings):

            sql = """
            INSERT INTO documents(content, embedding)
            VALUES (%s, %s)
            """

            cursor.execute(
                sql,
                (
                    content,
                    embedding
                )
            )

    conn.commit()

    print("10段文本向量化并入库成功")

finally:

    conn.close()