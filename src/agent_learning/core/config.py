import os
from pathlib import Path


# 类职责：用普通属性集中保存配置，方便在断点处查看和修改。
# 不使用数据类装饰器或字段反射。
class Settings:
    # 方法功能：保存配置并检查切分、Top-K 和阈值是否合理。
    def __init__(
        # 当前配置对象。
        self,
        # 从 .env.db 加载账号密码，打印配置时隐藏连接串。
        database_url='',
        # 兼容 Chat Completions 的服务地址。
        llm_base_url='https://api.deepseek.com',
        # 不输出到日志或配置对象的 repr。
        llm_api_key='',
        # 回答模型。
        llm_model='deepseek-chat',
        # 与旧项目一致的中文模型。
        embedding_model='BAAI/bge-small-zh-v1.5',
        # SQL 固定为 vector(512)。
        embedding_dim=512,
        # 中文 CrossEncoder。
        rerank_model='BAAI/bge-reranker-base',
        # 默认不下载模型。
        local_files_only=True,
        # 按字符切分。
        chunk_size=400,
        # 相邻子块重叠字符。
        chunk_overlap=80,
        # 父块字符上限。
        parent_size=1200,
        # 每路召回数量。
        recall_k=20,
        # 融合后进入精排的数量。
        candidate_k=20,
        # 最终上下文块数。
        top_k=5,
        # rrf 或 linear。
        fusion='rrf',
        # 线性融合权重。
        vector_weight=0.5,
        # 向量召回最低相似度。
        min_vector_score=0.35,
        # 拒答门槛，需要评测校准。
        min_rerank_score=0.35,
        # 上下文总字符预算。
        context_chars=3500,
        # 单块字符预算。
        per_chunk_chars=700,
        # 小规模学习语料上限，超限明确报错。
        bm25_max_chunks=10000,
    ):
        # 从 .env.db 加载账号密码，打印配置时隐藏连接串。
        self.database_url = database_url
        # 兼容 Chat Completions 的服务地址。
        self.llm_base_url = llm_base_url
        # 不输出到日志或配置对象的 repr。
        self.llm_api_key = llm_api_key
        # 回答模型。
        self.llm_model = llm_model
        # 与旧项目一致的中文模型。
        self.embedding_model = embedding_model
        # SQL 固定为 vector(512)。
        self.embedding_dim = embedding_dim
        # 中文 CrossEncoder。
        self.rerank_model = rerank_model
        # 默认不下载模型。
        self.local_files_only = local_files_only
        # 按字符切分。
        self.chunk_size = chunk_size
        # 相邻子块重叠字符。
        self.chunk_overlap = chunk_overlap
        # 父块字符上限。
        self.parent_size = parent_size
        # 每路召回数量。
        self.recall_k = recall_k
        # 融合后进入精排的数量。
        self.candidate_k = candidate_k
        # 最终上下文块数。
        self.top_k = top_k
        # rrf 或 linear。
        self.fusion = fusion
        # 线性融合权重。
        self.vector_weight = vector_weight
        # 向量召回最低相似度。
        self.min_vector_score = min_vector_score
        # 拒答门槛，需要评测校准。
        self.min_rerank_score = min_rerank_score
        # 上下文总字符预算。
        self.context_chars = context_chars
        # 单块字符预算。
        self.per_chunk_chars = per_chunk_chars
        # 小规模学习语料上限，超限明确报错。
        self.bm25_max_chunks = bm25_max_chunks
        # 初始化后检查参数。
        self.validate()

    # 方法功能：检查参数范围和相互关系，非法配置直接报错。
    # 检查配置之间的关系。
    def validate(self):
        # 防止切分死循环。
        if not 0 <= self.chunk_overlap < self.chunk_size <= self.parent_size:
            # 提示具体约束。
            raise ValueError("要求 0 <= overlap < chunk_size <= parent_size")
        # 检查 Top-K。
        if not 1 <= self.top_k <= self.candidate_k or self.recall_k < 1:
            # 拒绝非法配置。
            raise ValueError("要求 1 <= top_k <= candidate_k，recall_k >= 1")
        # 当前 DDL 的维度固定。
        if self.embedding_dim != 512:
            # 防止维度误配。
            raise ValueError("当前 SQL 使用 vector(512)，换维度需另行设计表和重建向量")
        # 限制可选算法。
        if self.fusion not in {"rrf", "linear"}:
            # 明确失败原因。
            raise ValueError("FUSION 只能是 rrf 或 linear")
        # 检查比例。
        if not all(0 <= x <= 1 for x in [self.vector_weight, self.min_rerank_score, self.min_vector_score]):
            # 阻止非法分数。
            raise ValueError("权重和阈值必须在 0..1")
        # 检查预算。
        if min(self.context_chars, self.per_chunk_chars, self.bm25_max_chunks) < 1:
            # 防止静默空结果。
            raise ValueError("上下文预算和 BM25 上限必须为正数")


# 方法功能：用 load_dotenv 和 os.getenv 明确读取每一个配置项。
# 输入：项目配置文件与环境变量；输出：Settings，不连接数据库、不加载模型。
# 延续旧代码的配置读取方式。
def load_settings():
    from dotenv import load_dotenv
    # 定位项目根目录。 __file__是特殊约定，当前模块路径
    project_root = Path(__file__).resolve().parents[3]
    # 读取数据库账号密码。
    # 会加载到临时环境变量里，新进程
    load_dotenv(project_root / ".env.db", override=False)
    # 读取 DeepSeek Key 和其他参数。
    load_dotenv(project_root / ".env", override=False)
    # 获取模型缓存开关。 
    # true就是只从本地加载模型；本地没有就报错，不自动下载。 env里没有LOCAL_FILES_ONLY 默认也是true
    local_only = os.getenv("LOCAL_FILES_ONLY", "true").lower()
    # 防止布尔值拼写错误。
    if local_only not in ["true", "false"]:
        # 提示正确写法。
        raise ValueError("LOCAL_FILES_ONLY 只能为 true/false")
    # 每个环境变量对应一个明确的配置参数。
    return Settings(
        # 从 .env.db 加载账号密码，打印配置时隐藏连接串。
        database_url=os.getenv("DATABASE_URL", ''),
        # 兼容 Chat Completions 的服务地址。
        llm_base_url=os.getenv("LLM_BASE_URL", 'https://api.deepseek.com'),
        # 不输出到日志或配置对象的 repr。
        llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY", ""),
        # 回答模型。
        llm_model=os.getenv("LLM_MODEL", 'deepseek-chat'),
        # 与旧项目一致的中文模型。
        embedding_model=os.getenv("EMBEDDING_MODEL", 'BAAI/bge-small-zh-v1.5'),
        # SQL 固定为 vector(512)。
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "512")),
        # 中文 CrossEncoder。
        rerank_model=os.getenv("RERANK_MODEL", 'BAAI/bge-reranker-base'),
        # 默认不下载模型。
        local_files_only=local_only == "true",
        # 按字符切分。
        chunk_size=int(os.getenv("CHUNK_SIZE", "400")),
        # 相邻子块重叠字符。
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "80")),
        # 父块字符上限。
        parent_size=int(os.getenv("PARENT_SIZE", "1200")),
        # 每路召回数量。
        recall_k=int(os.getenv("RECALL_K", "20")),
        # 融合后进入精排的数量。
        candidate_k=int(os.getenv("CANDIDATE_K", "20")),
        # 最终上下文块数。
        top_k=int(os.getenv("TOP_K", "5")),
        # rrf 或 linear。
        fusion=os.getenv("FUSION", 'rrf'),
        # 线性融合权重。
        vector_weight=float(os.getenv("VECTOR_WEIGHT", "0.5")),
        # 向量召回最低相似度。
        min_vector_score=float(os.getenv("MIN_VECTOR_SCORE", "0.35")),
        # 拒答门槛，需要评测校准。
        min_rerank_score=float(os.getenv("MIN_RERANK_SCORE", "0.35")),
        # 上下文总字符预算。
        context_chars=int(os.getenv("CONTEXT_CHARS", "3500")),
        # 单块字符预算。
        per_chunk_chars=int(os.getenv("PER_CHUNK_CHARS", "700")),
        # 小规模学习语料上限，超限明确报错。
        bm25_max_chunks=int(os.getenv("BM25_MAX_CHUNKS", "10000")),
    )
