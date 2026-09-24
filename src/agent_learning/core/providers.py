import math
from agent_learning.core.config import Settings
from agent_learning.core.models import Hit


# 方法功能：检查向量数量、维度、有限数值与非零范数，防止错误向量进入数据库。
# 输入：向量列表、预期数量和维度；输出：合法时无返回，不合法时抛出 ValueError。
# 编码和入库共用校验。
def validate_vectors(vectors, count, dimension):
    # 数量必须对应所有输入。
    if len(vectors) != count:
        # 防止 zip 静默截断。
        raise ValueError("Embedding 返回数量不匹配")
    # 逐向量校验。
    for vector in vectors:
        # 检查维度及 NaN。
        # 遍历 vector → 每次取出一个 value → 执行 math.isfinite(value)。
        # math.isfinite(value)是检查是否有限数，不是无穷大/小和无效数字
        # 比较len是否512维度；然后看512个向量里是否是正常数字，查看边界
        if len(vector) != dimension or not all(math.isfinite(value) for value in vector):
            # 拒绝无效向量。
            raise ValueError("Embedding 维度不符或包含非有限值")
        # 余弦距离要求非零向量。 
        # 这里2个乘法 负数也会是整数，这里防止的是0，因为0没有角度
        if sum(value * value for value in vector) <= 0:
            # 不使用占位向量。
            raise ValueError("Embedding 不能是全零向量")


# 类职责：调用本地 SentenceTransformer，把文档或问题编码成同一空间的数值向量。
# 延迟加载本地 SentenceTransformer。
class LocalEmbedder:
    # 方法功能：保存模型名、维度和本地缓存选项，初始化时不加载模型。
    # 输入：Settings 配置；输出：完成初始化的实例。
    # 仅保存配置。
    def __init__(self, settings: Settings) -> None:
        # 记录向量身份。
        self.model_name, self.dimension = settings.embedding_model, settings.embedding_dim
        # 首次编码时才加载。
        self.local_only, self._model = settings.local_files_only, None

    # 方法功能：延迟加载文档向量模型，批量编码文本并校验输出。
    # 输入：文本字符串列表；输出：与输入一一对应的浮点向量列表。
    # 文档不添加 query 指令。
    def passages(self, texts: list[str]) -> list[list[float]]:
        # 模型只加载一次。
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            # 默认仅使用缓存。
            self._model = SentenceTransformer(self.model_name, local_files_only=self.local_only, trust_remote_code=False)
        # 输出普通列表。
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
        # 校验模型输出。
        validate_vectors(vectors, len(texts), self.dimension)
        # 返回可序列化向量。
        return vectors

    # 方法功能：按模型要求添加查询前缀，复用文档编码能力生成问题向量。
    # 输入：用户问题字符串；输出：一个查询向量。
    # BGE 中文检索建议使用查询指令。
    def query(self, text: str) -> list[float]:
        # 不向其他模型强加指令。
        prefix = "为这个句子生成表示以用于检索相关文章：" if "bge-small-zh" in self.model_name else ""
        # 复用编码与校验。
        return self.passages([prefix + text])[0]


# 类职责：将问题和每个候选成对送入 CrossEncoder，生成相关分并重新排序。
# 真正对 query/document 成对精排。
class CrossEncoderReranker:
    # 方法功能：保存精排模型配置，实际预测时再加载模型。
    # 输入：Settings 配置；输出：完成初始化的实例。
    # 延迟加载模型。
    def __init__(self, settings):
        # 保存配置。
        self.settings, self._model = settings, None

    # 给每条候选资料重新打相关性分数，再按分数排序返回
    def rank(self, query: str, hits: list[Hit]) -> list[Hit]:
        # 空结果不加载模型。
        if not hits:
            # 保持空结果。
            return []
        import torch
        from sentence_transformers import CrossEncoder
        # 首次精排加载一次。
        if self._model is None:
            # 使用旧环境的 sentence-transformers 3.x 写法，分数范围 0..1。
            self._model = CrossEncoder(self.settings.rerank_model, max_length=512, local_files_only=self.settings.local_files_only, default_activation_function=torch.nn.Sigmoid())
        # 像旧代码一样先准备问题和文档对。
        pairs = [(query, hit.content) for hit in hits]
        # 直接调用模型预测，精排打分 核心。
        scores = self._model.predict(pairs, show_progress_bar=False)
        # 检查预测数量。
        if len(scores) != len(hits):
            # 不丢弃候选。
            raise ValueError("重排模型输出数量不匹配")
        # 回填分数。
        for hit, score in zip(hits, scores):
            # 转换 NumPy 标量。
            hit.rerank_score = float(score)
            # 拒绝异常预测。
            if not math.isfinite(hit.rerank_score):
                # 不吞掉模型错误。
                raise ValueError("重排分数无效")
        # 稳定排序。
        return sorted(hits, key=lambda hit: (-hit.rerank_score, hit.id))


# 类职责：统一封装兼容 Chat Completions 的模型调用，负责凭证、超时、重试和响应读取。
# 复用 OpenAI 兼容客户端接入 DeepSeek 等服务。
class CompatibleChatModel:
    # 方法功能：保存调用模型所需配置，此时不创建网络请求。
    # 输入：Settings 配置；输出：完成初始化的实例。
    # 在调用时才读取实际凭证。
    def __init__(self, settings):
        # 不创建网络连接。
        self.settings = settings

    # 方法功能：检查凭证后调用兼容模型 API，读取第一条回答并关闭客户端。
    # 输入：role/content 消息列表；输出：模型原始字符串，后续交给 AnswerValidator 校验。
    # 统一超时、模型和温度。
    def chat(self, messages):
        from openai import OpenAI
        # 防止缺少凭证时发送请求。
        if not self.settings.llm_api_key:
            # 不输出密钥。
            raise ValueError("请设置 LLM_API_KEY 或 DEEPSEEK_API_KEY")
        # 本地模型加载和生成可能较慢，明确提示当前已经进入回答阶段。
        if self.settings.llm_base_url.startswith("http://127.0.0.1:11434/"):
            # 立即显示状态，避免终端长时间空白。
            print(f"正在等待本地模型 {self.settings.llm_model} 生成回答...", flush=True)
        # 关闭客户端连接。
        with OpenAI(api_key=self.settings.llm_api_key, base_url=self.settings.llm_base_url, timeout=self.settings.llm_timeout, max_retries=1) as client:
            # 要求稳定的结构化回答。
            result = client.chat.completions.create(model=self.settings.llm_model, messages=messages, temperature=0, max_tokens=1200)
        # 空响应交给拒答校验。
        return result.choices[0].message.content or ""
