import os
import numpy as np
import jieba
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

# ---------- 1. 文档库 ----------
docs = [
    "RAG 是检索增强生成，先检索知识库再让大模型生成答案。",          # 0
    "文档编号 A-2026 规定第三章处理用户隐私数据。",                  # 1
    "BM25 是基于词频的统计检索算法，擅长精确关键词匹配。",            # 2
    "向量检索用 embedding 计算语义相似度，擅长近义召回。",            # 3
    "大语言模型在缺乏依据时容易编造不存在的事实。",                   # 4
    "混合检索结合稀疏与稠密表示，能同时兼顾精确与语义。",             # 5
    "用户数据在传输过程中必须使用 TLS 加密。",                      # 6
    "第三章描述了数据保留期限和删除流程。",                         # 7
    "倒排索引是关键词检索的底层数据结构。",                         # 8
    "余弦相似度常用于衡量两个向量的接近程度。",                      # 9
    "隐私政策规定用户有权要求删除个人数据。",                       # 10
    "检索系统的召回率和精确率需要权衡。",                          # 11
]

# ---------- 2. jieba 分词 + BM25 ----------
# 过滤掉空白词或空字符串。
def tokenize(text):
    return [w for w in jieba.lcut(text) if w.strip()]

# 用分词后的文档构建 BM25 索引
tokenized_docs = [tokenize(d) for d in docs]
bm25 = BM25Okapi(tokenized_docs)

# ---------- 3. 向量模型 ----------
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
doc_vectors = model.encode(docs, normalize_embeddings=True)

# ---------- 4. 两种融合方式 ----------
def linear_search(query, alpha=0.5, k=3):
    """线性加权融合"""
    #把 query 分词后，计算每条文档的 BM25 分数。
    bm25_scores = bm25.get_scores(tokenize(query))
    # 计算 BM25 分数的最大值和最小值之差，用于归一化。
    rng = bm25_scores.max() - bm25_scores.min()
    # 把 BM25 分数 min-max 归一化到 0 到 1 之间。
    bm25_norm = (bm25_scores - bm25_scores.min()) / rng if rng > 1e-9 else np.zeros_like(bm25_scores)

    #向量化，然后把 query 编码成归一化向量
    query_vec = model.encode([query], normalize_embeddings=True)[0]
    vector_scores = doc_vectors @ query_vec

    # 线性加权融合。
    # alpha 越大，越偏向向量语义检索；
    # alpha 越小，越偏向 BM25 关键词检索。
    fused = alpha * vector_scores + (1 - alpha) * bm25_norm
    # 对融合分数从高到低排序，取前 k 个文档索引。
    ranked = np.argsort(-fused)[:k]
    #返回结果列表，每项是 (文档编号, 融合分数)。分数保留 4 位小数。
    return [(int(i), round(float(fused[i]), 4)) for i in ranked]


def rrf_search(query, k=3, rrf_k=60):
    """
    RRF 融合：只看排名，不看分数。
    rrf_k 是平滑常数，通常取 60。
    """
    # 两路检索的原始分数
    # #把 query 分词后，计算每条文档的 BM25 分数。
    bm25_scores = bm25.get_scores(tokenize(query))
    # 计算 query 的归一化向量
    query_vec = model.encode([query], normalize_embeddings=True)[0]
    # 计算每条文档与 query 的向量相似度
    vector_scores = doc_vectors @ query_vec

    # 把分数转成排名（0-based 也行，只要一致）
    # 用 argsort(-scores) 得到"从高到低"的文档索引，再转成 rank
    bm25_order = np.argsort(-bm25_scores)      # 例如 [1, 7, 2, ...] 表示文档 1 排第一，文档 7 排第二。
    # 按向量相似度从高到低排序，得到文档索引顺序。
    vector_order = np.argsort(-vector_scores)

    # 构建 rank 数组：rank[doc_id] = 该文档在这路检索里的名次（从 0 开始）
    bm25_rank = np.empty(len(docs), dtype=int)
    vector_rank = np.empty(len(docs), dtype=int)
    # 把排序顺序转换成每个文档的名次。这里名次从 0 开始：第 1 名是 0，第 2 名是 1。
    bm25_rank[bm25_order] = np.arange(len(docs))
    vector_rank[vector_order] = np.arange(len(docs))

    # RRF 公式：score = 1/(rrf_k + rank_bm25) + 1/(rrf_k + rank_vector)
    rrf_scores = 1.0 / (rrf_k + bm25_rank) + 1.0 / (rrf_k + vector_rank)

    #按 RRF 分数从高到低排序，取前 k 条。
    ranked = np.argsort(-rrf_scores)[:k]
    #返回 (文档编号, RRF分数)，分数保留 6 位小数。
    return [(int(i), round(float(rrf_scores[i]), 6)) for i in ranked]


# ---------- 5. 评估集 ----------
test_cases = [
    ("A-2026 编号",              1, "关键词"),
    ("BM25 是什么",              2, "关键词"),
    ("TLS 加密",                 6, "关键词"),
    ("怎么减少模型胡编乱造",       4, "语义"),
    ("A2026 文件第三章讲了什么",   1, "语义-陷阱"),
    ("稀疏和稠密表示怎么结合",     5, "语义"),
    ("用户想把个人数据删掉",       10, "语义"),
    ("怎么评价检索效果好坏",       11, "语义"),
]

# ---------- 6. 评估函数 ----------
def evaluate(search_fn, **kwargs):
    top1, top3 = 0, 0
    details = []
    for query, gold, kind in test_cases:
        # 调用检索函数，取前 3 条结果。
        results = search_fn(query, k=3, **kwargs)
        # 从结果中提取文档编号列表。
        ids = [r[0] for r in results]
        # 判断第 1 条是否就是正确文档。
        hit1 = ids[0] == gold
        # 判断正确文档是否出现在 Top3 中。 累计命中数。
        hitk = gold in ids
        top1 += hit1
        top3 += hitk
        # 注意这里只保存了 hit1，没有保存 hitk。
        details.append((query, gold, ids, hit1, kind))
    # 返回 Top1 命中率、Top3 命中率和详细结果。
    n = len(test_cases)
    return top1 / n, top3 / n, details


# ---------- 7. 命中率对比 ----------
print("=" * 62)
print(f"{'方法':<22} | {'Top1':>8} | {'Top3':>8}")
print("-" * 62)

# 分别测试：
# alpha=0.0：纯 BM25；
# alpha=0.5：BM25 和向量等权；
# alpha=1.0：纯向量。
# 然后打印 Top1 / Top3 百分比。
for alpha in [0.0, 0.5, 1.0]:
    t1, t3, _ = evaluate(linear_search, alpha=alpha)
    print(f"{'线性加权 alpha=' + str(alpha):<22} | {t1:>7.2%} | {t3:>7.2%}")

# 分别测试 RRF 的 rrf_k=1, 10, 60。
# rrf_k 越小，排名靠前的文档优势越大；
# rrf_k 越大，排名差距被平滑，融合更温和。
for rrf_k in [1, 10, 60]:
    t1, t3, _ = evaluate(rrf_search, rrf_k=rrf_k)
    print(f"{'RRF rrf_k=' + str(rrf_k):<22} | {t1:>7.2%} | {t3:>7.2%}")

print("=" * 62)

# ---------- 8. 逐条对比：线性加权 vs RRF ----------
print("\n逐条对比（alpha=0.5  vs  RRF rrf_k=60）\n")
# 分别拿到线性融合和 RRF 的详细结果。
_, _, lin_details = evaluate(linear_search, alpha=0.5)
_, _, rrf_details = evaluate(rrf_search, rrf_k=60)

for (q, gold, lin_ids, lin_hit, kind), (_, _, rrf_ids, rrf_hit, _) in zip(lin_details, rrf_details):
      # 根据 Top1 是否命中，生成勾或叉。
    lin_mark = "✓" if lin_hit else "✗"
    rrf_mark = "✓" if rrf_hit else "✗"
    print(f"[{kind}] {q!r}  目标={gold}")
    print(f"    线性: {lin_mark} Top3={lin_ids}")
    print(f"    RRF : {rrf_mark} Top3={rrf_ids}")
    print()