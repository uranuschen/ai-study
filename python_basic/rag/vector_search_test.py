from sentence_transformers import SentenceTransformer, CrossEncoder
from openai import OpenAI
import psycopg2
import os
from dotenv import load_dotenv
import re

# PostgreSQL 配置
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "ragdb",
    "user": "rag",
    "password": "rag123456"
}


# 读取 .env 配置
load_dotenv()

# DeepSeek API
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)


# 加载 Embedding 模型
# 必须和文档入库时使用同一个模型
model = SentenceTransformer(
    "BAAI/bge-small-zh-v1.5"
)

# Rerank 模型：首次运行会下载
# 资源小用 base；要更强可换 "BAAI/bge-reranker-v2-m3"
reranker = CrossEncoder("BAAI/bge-reranker-base", max_length=512)

# 精确匹配 元数据里提取函数
def extract_order_id(query: str):

    match = re.search(r"A\d+", query)

    if match:
        return match.group()

    return None

# 精确匹配 元数据里提取函数
def extract_refund_id(query: str):

    match = re.search(r"R\d+", query)

    if match:
        return match.group()

    return None

#意图查询
def detect_intent(query: str):
    order_id = extract_order_id(query)
    refund_id = extract_refund_id(query)
    
    if order_id:
        return "order", order_id
    elif refund_id:
        return "refund", refund_id
    elif any(kw in query for kw in ["规则", "政策", "条款", "怎么办", "流程"]):
        return "rule", None
    else:
        return "general", None

#查询改写
def rewrite_query(query: str, intent: str, entity_id: str = None):
    # 如果有明确 ID，直接返回 ID（利用 content LIKE 精确匹配）
    if entity_id:
        return entity_id
        
    # 针对规则类问题，构造更贴近你数据表 content 的查询词
    if intent == "rule":
        # 提取关键词（这里可以简化为组合，或者调用一次 LLM）
        # 例如：“退款有什么规则？” -> “退款规则”
        if "退款" in query and "规则" in query:
            return "退款规则"
        elif "退款" in query:
            return "退款"
        elif "规则" in query:
            return "规则"
            
    # 默认情况返回原问题
    return query

# top_k 现在是召回数量，不是最终数量。
def search(query: str, top_k: int = 20,max_distance: float = 0.5):
    """
    top_k 现在是召回数量，不是最终数量。
    后面会交给 rerank 重排。
    """

    # 1. 意图识别 + 实体抽取
    intent, entity_id = detect_intent(query)

    # 2. 查询改写（用改写后的 query 去生成向量或做 LIKE）
    rewritten_query = rewrite_query(query, intent, entity_id)

    # 将用户问题转换成向量
    query_embedding = model.encode(rewritten_query, normalize_embeddings=True)
    # 转成 pgvector 可以识别的字符串格式
    query_vector = str(query_embedding.tolist())


    # 连接 PostgreSQL
    conn = psycopg2.connect(**DB_CONFIG)

    try:
        cursor = conn.cursor()

        # <=> 是 pgvector 的 cosine distance
        # distance 越小，语义越相似

        # 3. 根据意图构建 SQL
        if intent in ["order", "refund"]:
             # 有明确单号，优先使用 LIKE 精确过滤，再按向量距离排序
            sql = """
                SELECT id, content, source, metadata, embedding <=> %s::vector AS distance
                FROM rag_documents
                WHERE content LIKE %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            cursor.execute(sql, (query_vector, f"%{entity_id}%", query_vector, top_k))
        else:
            # 规则类或一般问答，直接走纯向量检索
            sql = """
                SELECT id, content, source, metadata, embedding <=> %s::vector AS distance
                FROM rag_documents
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            cursor.execute(sql, (query_vector, query_vector, top_k))
        
        rows = cursor.fetchall()

        results = []
        for row in rows:
            distance = float(row[4])

            # 只有普通语义检索才做距离阈值过滤
            if intent not in ["order", "refund"] and distance > max_distance:
                continue


            result = {
                "id": row[0],
                "content": row[1],
                "source": row[2],
                "metadata": row[3],
                "distance": float(row[4])
            }
            results.append(result)

        return results

    finally:
        conn.close()

#  Rerank 重排
def rerank_results(query: str, results: list, top_n: int = 5):
    """
    Rerank 重排：CrossEncoder 对 query 和每条文档打分。
    rerank_score 越大越相关。
    """
    if not results:
        return []
    # 把每个候选文档和用户问题拼成一对：[(用户问题, 文档1内容), (用户问题, 文档2内容), ...]
    pairs = [(query, r["content"]) for r in results]
    # 调用 CrossEncoder 模型，对每一对 (query, content) 打分。
    scores = reranker.predict(pairs)

    # 把分数写回每条文档字典里，字段名叫 rerank_score。
    for r, s in zip(results, scores):
        r["rerank_score"] = float(s)

    # 按 rerank_score 从大到小排序。
    results.sort(key=lambda x: x["rerank_score"], reverse=True)
    # 只返回前 top_n 条，默认前 5 条。
    return results[:top_n]

#轻量压缩：把长文档切成句子，优先保留和用户问题字符重叠多的句子，再按原文顺序拼起来，最后限制长度
def compress_content(query: str, content: str, max_chars: int = 600):
    """
    轻量压缩：按句子切分，优先保留和 query 字符重叠高的句子。
    生产环境也可以换成 LLM 摘要压缩。
    """
    content = content.strip()
    #如果这条文档本身就不长，没超过 max_chars，直接原样返回，不需要压缩
    if len(content) <= max_chars:
        return content
    #按句子切分。
    sentences = re.split(r'(?<=[。！？!?；;\n])', content)
    #去掉每个句子首尾空白，并过滤掉空字符串
    sentences = [s.strip() for s in sentences if s.strip()]

    #如果切完发现没有有效句子，直接硬截断到 max_chars，防止后面出错
    if not sentences:
        return content[:max_chars]

    #从用户问题里提取所有中文字符、英文字母、数字。
    query_chars = set(re.findall(r'[\u4e00-\u9fa5A-Za-z0-9]', query))

    scored = []
    for i, sent in enumerate(sentences):
        # 提取这个句子里的中英文数字字符集合。
        sent_chars = set(re.findall(r'[\u4e00-\u9fa5A-Za-z0-9]', sent))
        # 集合交集，计算问题和这个句子共有的字符数量。
        overlap = len(query_chars & sent_chars)
        # 计算重叠比例。
        score = overlap / max(len(query_chars), 1)
        # 把 (分数, 原句索引, 句子) 存起来。
        scored.append((score, i, sent))

    #问题字符重叠越多的句子，排越前面
    scored.sort(key=lambda x: x[0], reverse=True)

    selected_indices = []
    total = 0

    for _, i, sent in scored:
        # 如果加上这句会超过 max_chars，就跳过这句，继续看下一句。
        if total + len(sent) > max_chars:
            continue
        selected_indices.append(i)
        total += len(sent)

    selected_indices.sort()
    compressed = "".join(sentences[i] for i in selected_indices)

    return (compressed or content)[:max_chars]

# 将检索结果拼成 Context  加入引用编号。
#  每条用 compress_content 压缩到 max_chars_per_doc=600
#   总 Context 截断到 max_total_chars=2500
def build_context(
    query: str,
    results: list,
    max_docs: int = 3, #最多用几条文档
    max_chars_per_doc: int = 600, #每条文档最多多少字符
    max_total_chars: int = 2500 #整个 Context 最多多少字符
):
    """
    截断 + 压缩 Context：
    - max_docs：最多用几条文档
    - max_chars_per_doc：每条文档最多多少字符
    - max_total_chars：整个 Context 最多多少字符
    """
    context_list = []
    total_chars = 0

    for idx, result in enumerate(results[:max_docs], start=1):
        content = compress_content(
            query=query,
            content=result["content"],
            max_chars=max_chars_per_doc
        )
        source = result["source"]

        print(f"[{idx}] rerank_score: {result.get('rerank_score')}, distance: {result.get('distance')}")
        print(f"    content: {content}")

        piece = f"[{idx}] 内容：{content}\n来源：{source}"

        if total_chars + len(piece) > max_total_chars:
            remain = max_total_chars - total_chars
            if remain <= 0:
                break
            piece = piece[:remain] + "..."

        context_list.append(piece)
        total_chars += len(piece)

    return "\n\n".join(context_list)


# 生成最终 Prompt 要求引用编号
def build_prompt(query: str, context: str):
    if not context.strip():
        return None # 或者直接返回“知识库中暂无相关信息”，不调用 LLM
    
    prompt = f"""
请根据下面提供的知识库内容回答用户问题。

知识库内容：
{context}

用户问题：
{query}

要求：
1. 只根据知识库内容回答
2. 如果知识库内容中没有答案，请回答“知识库中暂无相关信息”
3. 不要自行编造知识库中没有的信息
4. 请在回答中的关键结论处标注引用编号，例如 [1]、[2]。
"""

    return prompt


# 调用 DeepSeek
def ask_llm(prompt: str):

    response = client.chat.completions.create(
        model="deepseek-chat",

        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],

        temperature=0.2
    )

    # 取出模型最终回答
    answer = response.choices[0].message.content

    return answer


# 测试问题
test_queries = [
    "A1002 的退款情况是什么？",   # 意图：order，触发 LIKE A1002
    "R1001 退款的进度如何？",     # 意图：refund，触发 LIKE R1001
    "退款有什么规则？",           # 意图：rule，查询改写为 "退款规则"，走纯向量检索
    "订单取消后会发生什么？"      # 意图：rule/general，走纯向量检索
]


# 逐个执行完整 RAG
for query in test_queries:

    print()
    print("问题:")
    print(query)

    # 1：向量召回：多召回一些
    results = search(
        query=query,
        top_k=20,
        max_distance=0.7
    )

    # 2. Rerank 重排：CrossEncoder 逐对打分，按 rerank_score 降序，取 top_n=5
    results = rerank_results(
        query=query,
        results=results,
        top_n=5
    )

    # 3. 截断 / 压缩 Context
    context = build_context(
        query=query,
        results=results,
        max_docs=3,
        max_chars_per_doc=600,
        max_total_chars=2500
    )

    # 4. 生成 Prompt
    prompt = build_prompt(
        query=query,
        context=context
    )

    print()
    print("最终 Prompt:")
    print(prompt)

    if prompt is None:
        print()
        print("最终回答:")
        print("知识库中暂无相关信息")
        print()
        print("=" * 50)
        continue

    # 5. 调用 LLM
    answer = ask_llm(
        prompt=prompt
    )

    print()
    print("最终回答:")
    print(answer)
    print()
    print("=" * 50)