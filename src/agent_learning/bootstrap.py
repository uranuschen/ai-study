from pathlib import Path
from agent_learning.core.config import Settings, load_settings
from agent_learning.core.models import SearchFilter
from agent_learning.services.agent_service import AgentService
from agent_learning.services.lesson_service import LessonService
from agent_learning.services.order_service import OrderService
from agent_learning.services.rag_service import RagService
from agent_learning.workflows.tool_model import CompatibleToolModel

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




# 学习阶段由服务端固定模拟身份，不接受请求覆盖租户或读取权限。
TENANT_ID = "acme"
# 所有接口统一使用当前用户的读取级别。
SECURITY_LEVEL = 1


# 启动时明确创建依赖；不连接数据库、不执行入库、不请求模型。
def build_services(settings=None):
    # 正常启动使用已有配置，离线核查可以显式传入 Settings()。
    if settings is None:
        # 只读取配置，不输出配置内容。
        settings = load_settings()
    # 只加载本机已有模型，不自动下载。
    settings.local_files_only = True
    # 定位项目根目录。
    base_dir = Path(__file__).resolve().parents[2]
    # 订单业务继续只读 JSON。
    data_file = base_dir / "data" / "business_demo.json"
    # RAG 组件延迟到实际请求时加载模型或建立数据库连接。
    pipeline = build_pipeline(settings)
    # 预览流程不创建数据库或向量模型对象。
    preview_pipeline = build_ingestion_pipeline(settings, write=False)
    # 入库对象在显式调用入库接口时才执行写入。
    ingestion_pipeline = build_ingestion_pipeline(settings, write=True)
    # Agent 只查规则资料，订单事实由业务 Tool 提供。
    filters = SearchFilter(
        tenant_id=TENANT_ID,
        max_security_level=SECURITY_LEVEL,
        doc_type="policy",
    )
    # 创建支持工具调用的模型客户端。
    model = CompatibleToolModel(settings)
    # 创建资料与知识库服务。
    rag = RagService(
        pipeline, preview_pipeline, ingestion_pipeline,
        base_dir / "data", TENANT_ID, SECURITY_LEVEL,
    )
    # 创建订单查询与固定流程服务。
    orders = OrderService(TENANT_ID, data_file)
    # 创建包含内存会话的综合 Agent 服务。
    agent = AgentService(model, pipeline, filters, data_file)
    # 创建独立基础课程演示服务。
    lessons = LessonService(TENANT_ID, data_file)
    # 使用普通字典保存应用需要的四个服务。
    return {"rag": rag, "orders": orders, "agent": agent, "lessons": lessons}
