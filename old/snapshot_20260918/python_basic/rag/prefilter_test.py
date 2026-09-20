import os
import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
from pgvector import Vector

example_docs = [
    {
        "content": "财务报销制度：员工差旅报销标准，住宿费一线城市不超过500元/晚，二线城市不超过400元/晚。",
        "business_module": "finance",
        "doc_type": "policy",
        "tenant_id": "acme",
        "security_level": 1,
    },
    {
        "content": "采购合同模板：甲方与乙方就采购货物达成如下协议，包含价格、交付、验收、付款条款。",
        "business_module": "procurement",
        "doc_type": "template",
        "tenant_id": "acme",
        "security_level": 1,
    },
    {
        "content": "销售流程：线索获取 -> 商机确认 -> 报价 -> 合同签署 -> 回款。",
        "business_module": "sales",
        "doc_type": "process",
        "tenant_id": "acme",
        "security_level": 1,
    },
    {
        "content": "HR入职FAQ：入职需要携带身份证、学历证明、离职证明，并完成背景调查。",
        "business_module": "hr",
        "doc_type": "faq",
        "tenant_id": "acme",
        "security_level": 1,
    },
]

# ========== 连接数据库 ==========
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="ragdb",
    user="rag",
    password="rag123456"
)
register_vector(conn)

QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# ========== 加载本地模型 ==========
model = SentenceTransformer( "BAAI/bge-small-zh-v1.5" , local_files_only=True)

# ========== 编码函数 ==========
def embed_passages(texts):
    vecs = model.encode(texts, normalize_embeddings=True)
    return [Vector(v.tolist()) for v in vecs]

def embed_query(query):
    v = model.encode(
        QUERY_INSTRUCTION + query,
        normalize_embeddings=True
    )
    return Vector(v.tolist())


def embed_passages(texts):
    """入库文档编码：不加指令，归一化"""
    return model.encode(texts, normalize_embeddings=True).tolist()

# ========== 插入文档 ==========
def insert_doc(
    content,
    business_module,
    doc_type,
    tenant_id="acme",
    security_level=1,
    version="1.0",
    is_latest=True,
):
    emb = embed_passages([content])[0]

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kb_documents (
                content, embedding,
                business_module, doc_type,
                tenant_id, security_level,
                version, is_latest
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                content, emb,
                business_module, doc_type,
                tenant_id, security_level,
                version, is_latest,
            ),
        )
    conn.commit()

# ========== 查询 ==========
def search(
    query,
    business_module,
    doc_type,
    tenant_id="acme",
    max_security_level=1,
    k=5,
):
    qvec = embed_query(query)

    with conn.cursor() as cur:
        # 可选：pgvector 0.8+ 开启迭代扫描，过滤太窄时避免召回不足
        # cur.execute("SET LOCAL hnsw.ef_search = 100")
        # cur.execute("SET LOCAL hnsw.iterative_scan = 'relaxed_order'")

        cur.execute(
    """
    SELECT
        id,
        content,
        1 - (embedding <=> %s::vector) AS cosine_similarity
    FROM kb_documents
    WHERE tenant_id = %s
      AND business_module = %s
      AND doc_type = %s
      AND is_latest = true
      AND security_level <= %s
    ORDER BY embedding <=> %s::vector
    LIMIT %s
    """,
    (
        qvec,
        tenant_id,
        business_module,
        doc_type,
        max_security_level,
        qvec,
        k,
    ),
)
        return cur.fetchall()

# ========== 主流程 ==========
if __name__ == "__main__":
    # 1. 插入示例数据（见下方单独部分）
    # for doc in example_docs:
    #     insert_doc(**doc)

    # 2. 查询：财务报销制度
    rows = search(
        query="报销标准是什么",
        business_module="finance",
        doc_type="policy",
    )
    print("=== finance / policy ===")
    for row in rows:
        print(row)

    # 3. 查询：采购合同模板
    rows = search(
        query="采购合同模板",
        business_module="procurement",
        doc_type="template",
    )
    print("=== procurement / template ===")
    for row in rows:
        print(row)

    conn.close()