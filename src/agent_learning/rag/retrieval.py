import re
from agent_learning.core.config import Settings
from agent_learning.core.models import Hit, SearchFilter
from agent_learning.core.providers import LocalEmbedder
from agent_learning.rag.repository import PostgresRepository


# 方法功能：BM25 与查询共用中文分词规则。
# BM25 与查询共用中文分词规则。
def tokenize(text):
    import jieba
    # 去空白和标点。
    return [word.lower() for word in jieba.lcut(text) if re.search(r"[\w\u4e00-\u9fff]", word)]


# 类职责：执行简单规则式意图识别、保守查询改写和业务编号提取，不修改调用者权限。
# 可替换为 LLM 改写，当前规则实现便于学习和复现。
class QueryProcessor:
    # 方法功能：清理原问题，识别意图和单个业务实体，进行保守的同义词扩展。
    # 输入：问题字符串；输出：original、query、intent、entity_id 字典。
    # 改写只补充同义词，不删除原问题。
    def process(self, question):
        # 清理首尾空白。
        query = question.strip()
        # 限制空输入和过长问题。
        if not query or len(query) > 4000:
            # 防止无效检索。
            raise ValueError("问题长度必须为 1..4000 字符")
        # 提取订单或退款编号。
        entities = re.findall(r"(?<![A-Za-z0-9])(?:A|R)\d{4,}(?![A-Za-z0-9])", query.upper())
        # 默认是一般问题。
        intent = "general"
        # 优先识别退款问题。
        if "退款" in query:
            # 标记退款意图。
            intent = "refund"
        # 再识别订单问题。
        elif "订单" in query:
            # 标记订单意图。
            intent = "order"
        # 识别制度类问题。
        elif any(word in query for word in ["规定", "政策", "规则", "标准"]):
            # 标记规则意图。
            intent = "policy"
        # 默认保留原问题。
        rewritten = query
        # 为明确的规则问题补充关键词。
        if query in ["退款有什么规则？", "退款有什么规则?"]:
            # 不丢掉用户原来的描述。
            rewritten = query + " 退款规则 退款政策"
        # 默认不限制具体单号。
        entity_id = None
        # 只有一个单号时才增加精确过滤。
        if len(set(entities)) == 1:
            # 取出业务编号。
            entity_id = entities[0]
        # 返回普通字典。
        return {"original": query, "query": rewritten, "intent": intent, "entity_id": entity_id}


# 类职责：对过滤后的语料进行中文分词并计算 BM25，召回关键词相关的候选块。
# 复用旧代码已经使用的 rank_bm25。
class BM25Retriever:
    # 方法功能：保存分词函数与 BM25 的词频饱和、文档长度归一化参数。
    # 输入：tokenizer、k1、b；输出：完成初始化的关键词检索器。
    # 分词函数支持测试注入。
    def __init__(self, tokenizer=tokenize, k1=1.5, b=0.75):
        # 保存算法参数。
        self.tokenizer, self.k1, self.b = tokenizer, k1, b

    # 方法功能：像 old/hybird_test.py 一样，使用 BM25Okapi 给文档打分。
    # 输入：问题、授权语料和 K；输出：按关键词分数排序的候选。
    # 不再手写 BM25 公式。
    def search(self, query: str, corpus: list[Hit], k: int) -> list[Hit]:
        from rank_bm25 import BM25Okapi
        # 空语料不建立索引。
        if not corpus:
            # 没有可召回的内容。
            return []
        # 分词并去掉重复查询词。
        query_words = list(set(self.tokenizer(query)))
        # 对每篇正文分词。
        document_words = [self.tokenizer(hit.content) for hit in corpus]
        # 空问题或空语料不能计算分数。
        if not query_words or not any(document_words):
            # 直接返回无匹配。
            return []
        # 沿用旧代码中的库。
        bm25 = BM25Okapi(document_words, k1=self.k1, b=self.b)
        # 一次计算所有候选的 BM25 分数。
        scores = bm25.get_scores(query_words)
        # 收集实际命中关键词的文档。
        results = []
        # 同步遍历正文、分词和得分。
        for hit, words, score in zip(corpus, document_words, scores):
            # 没有任何查询词匹配就跳过。 intersection是交集
            if not set(query_words).intersection(words):
                # 不能把无关的零分文档加入结果。
                continue
            # 创建结果副本。
            result = Hit(**hit.to_dict())
            # 保存库返回的原始分数；小语料中可能为零或负值。
            result.bm25_score = float(score)
            # 根据真实词命中保留，不简单按正负数过滤。
            results.append(result)
        # 取关键词 Top-K。 给每个 Hit 生成排序依据，先看 BM25 分数，分数相同时再看 id。 这里-hit 是改成负数来排，这样高分在前。
        # :k是取前几个，不足k就返回全部
        return sorted(results, key=lambda hit: (-hit.bm25_score, hit.id))[:k]


# 类职责：按子块 ID 合并两路候选，保留各路得分，并用 RRF 或线性加权得到统一排名。
# 去重后保留每一路排名并计算融合分。
class ResultFusion:
    # 方法功能：校验并保存融合算法、向量权重和 RRF 平滑常数。
    # 输入：method、vector_weight、rrf_k；输出：完成初始化的融合器。
    # RRF 常数与候选数量是不同概念。
    def __init__(self, method="rrf", vector_weight=0.5, rrf_k=60):
        # 校验算法配置。
        if method not in {"rrf", "linear"} or not 0 <= vector_weight <= 1 or rrf_k < 1:
            # 禁止错误权重。
            raise ValueError("融合参数无效")
        # 保存配置。
        self.method, self.weight, self.rrf_k = method, vector_weight, rrf_k

    #把向量检索和 BM25 关键词检索的结果合在一起，按子块 id 去重，算一个融合分，最后取前 k 个。
    def merge(self, vector_hits: list[Hit], keyword_hits: list[Hit], k: int) -> list[Hit]:
        # 建立一个字典，用 hit.id 当键。这样同一个子块不会出现两份。
        merged = {}
        # 循环两次，先处理向量结果，再处理关键词结果
        for route in ["vector", "keyword"]:
            # 当前处理向量结果。
            if route == "vector":
                # 取向量候选。
                hits = vector_hits
                # 使用向量权重。
                weight = self.weight
            # 当前处理关键词结果。
            else:
                # 取关键词候选。
                hits = keyword_hits
                # 使用关键词权重。
                weight = 1 - self.weight
            # 保留首次出现的真实排名。
            unique, seen = [], set()
            # 顺序去重，不能用倒序字典改变排名。
            for hit in hits:
                # 每路相同 ID 只计一次。
                if hit.id not in seen:
                    # 保存首次命中。
                    unique.append(hit)
                    # 记录已见子块。
                    seen.add(hit.id)
            # 记录当前一路的全部得分。
            route_scores = []
            # 线性融合需要先知道最大分。
            for hit in unique:
                # 读取对应分数。
                score = hit.vector_score if route == "vector" else hit.bm25_score
                # 后面用于和旧代码相同的 min-max 归一化。
                route_scores.append(score)
            # 最小原始分数。
            minimum = min(route_scores, default=0)
            # 最大原始分数。
            maximum = max(route_scores, default=0)
            # 逐个处理去重后的结果，rank 是排名，从 1 开始
            for rank, hit in enumerate(unique, 1):
                # 如果这个 id 还不在 merged 中。
                if hit.id not in merged:
                    # 复制候选内容和来源。
                    merged[hit.id] = Hit(**hit.to_dict())
                    # 融合分从零开始。
                    merged[hit.id].fusion_score = 0.0
                # 取出合并后的结果。
                target = merged[hit.id]
                # 保存向量一路的原始分数。
                if route == "vector":
                    # 回填语义得分。
                    target.vector_score = hit.vector_score
                    # 用于线性融合。
                    score = hit.vector_score
                # 保存关键词一路的原始分数。
                else:
                    # 回填关键词得分。
                    target.bm25_score = hit.bm25_score
                    # 用于线性融合。
                    score = hit.bm25_score
                # RRF 只使用排名。
                if self.method == "rrf":
                    # 累加当前排名贡献。
                    target.fusion_score += 1 / (self.rrf_k + rank)
                # 线性融合使用旧代码中的 min-max 思路。
                else:
                    # 只有一个结果或所有分数相等时，命中结果同分。
                    normalized = 1.0
                    # 有分差时再做除法。
                    if maximum > minimum:
                        # 缩放到 0..1，兼容负 BM25 分数。
                        normalized = (score - minimum) / (maximum - minimum)
                    # 累加当前一路的加权分数。
                    target.fusion_score += weight * normalized
        # 截取精排候选。
        return sorted(merged.values(), key=lambda hit: (-hit.fusion_score, hit.id))[:k]


# 类职责：协调问题向量化、向量召回、独立 BM25 和融合，输出进入精排的候选列表。
# 协调数据库向量召回和独立 BM25。
class HybridRetriever:
    # 方法功能：注入数据仓储和向量模型，并创建关键词检索与融合组件。
    # 输入：repository、embedder、settings 和可选 bm25；输出：完成初始化的混合检索器。
    # 标明组件类型，方便从调用处跳转到具体方法。
    def __init__(
        self,
        repository: PostgresRepository,
        embedder: LocalEmbedder,
        settings: Settings,
        bm25: BM25Retriever | None = None,
    ) -> None:
        # 保存数据库操作对象，可跳转到 vector_search 和 lexical_corpus。
        self.repository = repository
        # 保存向量模型对象，可跳转到 query。
        self.embedder = embedder
        # 保存召回数量、阈值和融合参数。
        self.settings = settings
        # 默认中文 BM25。
        self.bm25 = bm25 or BM25Retriever()
        # 构造融合器。
        self.fusion = ResultFusion(settings.fusion, settings.vector_weight)

    # 方法功能：用同一过滤器执行两路召回，再融合为供精排使用的候选。
    # 输入：改写后的问题和 SearchFilter；输出：候选 Hit 列表与召回数量统计。
    # 两路严格使用相同权限与元数据过滤。
    def retrieve(self, query: str, filters: SearchFilter) -> tuple[list[Hit], dict[str, int]]:
        # 编码改写后的问题。  
        # 1.可能加了前缀 2.把query向量化，这里是512维的 3.做了数值边界（无穷大小和非数字）和cos是0角度的验证
        vector = self.embedder.query(query)
        # 向量 Top-K。
        # 1.在校验了一次 2.把条件拼接在里面返回多个hits对象，就是cos后的数据，并且里面加了向量化近似检索来控制精度
        vector_hits = self.repository.vector_search(vector, filters, self.embedder.model_name, self.settings.recall_k)
        # 去掉弱语义命中。 低于0.35的数据不要
        vector_hits = [hit for hit in vector_hits if hit.vector_score >= self.settings.min_vector_score]
        # 读取完整过滤语料。
        corpus = self.repository.lexical_corpus(filters, self.embedder.model_name, self.settings.bm25_max_chunks)
        # 独立关键词召回。
        keyword_hits = self.bm25.search(query, corpus, self.settings.recall_k)
        # 向量检索和 BM25 关键词检索的结果合在一起，按子块 id 去重，算一个融合分，最后取前 k 个。 比较核心
        candidates = self.fusion.merge(vector_hits, keyword_hits, self.settings.candidate_k)
        # 返回阶段统计。
        return candidates, {"vector_hits": len(vector_hits), "bm25_hits": len(keyword_hits), "candidates": len(candidates)}
