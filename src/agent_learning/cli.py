from agent_learning.core.config import Settings
from agent_learning.core.providers import CompatibleChatModel, CrossEncoderReranker, LocalEmbedder
from agent_learning.rag.answering import AnswerValidator, ContextBuilder, PromptBuilder, RAGPipeline
from agent_learning.rag.chunking import DocumentChunker
from agent_learning.rag.ingestion import IngestionPipeline
from agent_learning.rag.loaders import DocumentLoader
from agent_learning.rag.repository import PostgresRepository
from agent_learning.rag.retrieval import HybridRetriever, QueryProcessor


# 方法功能：按顺序创建入库用到的对象，返回入库主流程。
# 输入：配置和是否写库；输出：IngestionPipeline。
# 只是把几步创建对象的代码放在一起。
def build_ingestion_pipeline(settings, write=False):
    # 创建文件加载器。
    loader = DocumentLoader()
    # 创建切分器。
    chunker = DocumentChunker(settings.chunk_size, settings.chunk_overlap, settings.parent_size)
    # 预览时不需要向量模型。
    embedder = None
    # 预览时不需要数据库。
    repository = None
    # 用户在入口中明确打开写入开关。
    if write:
        # 保存模型配置，真正编码时才加载。
        embedder = LocalEmbedder(settings)
        # 保存连接配置，此处不连接。
        repository = PostgresRepository(settings.database_url, settings.embedding_dim)
    # 返回入库对象。
    return IngestionPipeline(loader, chunker, embedder, repository)


# 方法功能：逐个创建问答需要的对象，再交给问答主流程。
# 输入：Settings；输出：可调用 ask 的 RAGPipeline。
# 展开每一步，方便打断点。
def build_pipeline(settings: Settings) -> RAGPipeline:
    # 创建数据库操作对象。
    repository = PostgresRepository(settings.database_url, settings.embedding_dim)
    # 创建向量模型对象。
    embedder = LocalEmbedder(settings)
    # 创建查询改写对象。
    query_processor = QueryProcessor()
    # 创建混合检索对象。
    retriever = HybridRetriever(repository, embedder, settings)
    # 创建精排对象。
    reranker = CrossEncoderReranker(settings)
    # 创建上下文整理对象。
    context_builder = ContextBuilder(settings)
    # 创建提示词对象。
    prompt_builder = PromptBuilder()
    # 创建 DeepSeek 调用对象。
    llm = CompatibleChatModel(settings)
    # 创建回答与引用检查对象。
    validator = AnswerValidator()
    # 将上面的普通对象交给主流程逐个调用。
    return RAGPipeline(
        query_processor, retriever, reranker, context_builder,
        prompt_builder, llm, validator, settings,
    )


# 方法功能：旧模块入口只显示新的直接运行方式，不访问数据库或模型。
# 不再解析 ingest / ask 命令参数。
def main():
    # 提示入库入口。
    print("资料入库：直接运行根目录 main_ingest.py，默认只预览。")
    # 提示问答入口。
    print("用户问答：直接运行根目录 main_ask.py，在文件顶部修改 QUESTION。")
