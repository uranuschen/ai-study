from sentence_transformers import SentenceTransformer
import numpy as np


# 1. 加载模型
model = SentenceTransformer(
    "BAAI/bge-small-zh-v1.5"
)


# 2. 原始文本
text = """
退款失败可能是由于支付渠道异常导致。
订单取消成功后，系统会自动触发退款流程。
如果退款状态为处理中，需要等待支付平台返回结果。
如果银行卡已经扣款但退款未到账，需要联系支付渠道确认。
退款完成后，金额通常会原路返回。
"""


# 3. 切分函数
def split_text(text, chunk_size, overlap):

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk = text[start:end]

        chunks.append(chunk)

        start = end - overlap

    return chunks


# 4. 三组实验参数
experiments = [
    (30, 0),
    (30, 5),
    (50, 10)
]


# 5. 用户问题
question = "退款为什么失败？"

# 把问题转成向量
question_embedding = model.encode(question)


# 6. 开始不同参数实验
for chunk_size, overlap in experiments:

    print()
    print("=" * 60)
    print(
        f"chunk_size={chunk_size}, overlap={overlap}"
    )
    print("=" * 60)

    # 切分文本
    chunks = split_text(
        text,
        chunk_size,
        overlap
    )

    # 把所有 Chunk 一次性转成向量
    chunk_embeddings = model.encode(chunks)

    results = []

    # 计算每个 Chunk 和问题的余弦相似度 zip是链接 
    # np.dot= 向量点积 比如[3,4]就是5,3的平方+4的平法 开根号=5
    # np.linalg.norm= 向量长度  下面就是问题向量长度 × Chunk向量长度
    # 这是余弦相似度公式
    for chunk, chunk_embedding in zip(
        chunks,
        chunk_embeddings
    ):

        similarity = np.dot(
            question_embedding,
            chunk_embedding
        ) / (
            np.linalg.norm(question_embedding)
            * np.linalg.norm(chunk_embedding)
        )

        results.append(
            (chunk, similarity)
        )

    # 按相似度从高到低排序
    results.sort(
        key=lambda x: x[1],
        reverse=True
    )

    # 取 Top-3 enumerate加序号
    top_k = results[:3]

    for i, result in enumerate(top_k):

        print(f"Top {i + 1}")
        print("content:", result[0])
        print("similarity:", result[1])
        print("--------------------")