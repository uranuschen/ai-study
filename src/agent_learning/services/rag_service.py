from pathlib import Path
from agent_learning.core.errors import ServiceError
from agent_learning.core.models import SearchFilter
from agent_learning.rag.answering import RAGPipeline
from agent_learning.rag.ingestion import IngestionPipeline


# 衔接文件入库与知识库问答，不包含 HTTP 或日志代码。
class RagService:
    # 接收已经构造好的流程和可信身份。
    def __init__(
        self,
        pipeline: RAGPipeline,
        preview_pipeline: IngestionPipeline,
        ingestion_pipeline: IngestionPipeline,
        data_dir: Path,
        tenant_id: str,
        security_level: int,
    ) -> None:
        # 明确问答流程类型，方便编辑器跳转到 ask 方法。
        self.pipeline: RAGPipeline = pipeline
        # 明确预览流程类型；预览没有数据库与向量模型。
        self.preview_pipeline: IngestionPipeline = preview_pipeline
        # 明确入库流程类型；只有显式调用 ingest 才运行。
        self.ingestion_pipeline: IngestionPipeline = ingestion_pipeline
        # 只允许读取项目资料目录。
        self.data_dir = Path(data_dir).resolve()
        # 租户和权限都由服务端提供。
        self.tenant_id = tenant_id
        # 请求参数不能提高这个读取级别。
        self.security_level = security_level

    # 将相对文件名定位到 data 目录，拒绝目录穿越和外部符号链接。
    def resolve_file(self, file_name: str) -> Path:
        # 接口只接受相对文件名，绝对路径不属于此接口约定。
        if Path(file_name).is_absolute():
            # 避免客户端依赖服务器的绝对目录结构。
            raise ServiceError(400, "请提供 data 目录内的相对文件名。")
        # 计算文件的真实路径。
        path = (self.data_dir / file_name).resolve()
        # 路径必须仍在 data 目录内。
        if not path.is_relative_to(self.data_dir):
            # 不允许读取任意服务端文件。
            raise ServiceError(400, "只能读取 data 目录内的资料文件。")
        # 目标必须是已经存在的文件。
        if not path.is_file():
            # 不返回服务端绝对路径。
            raise ServiceError(404, "资料文件不存在。")
        # 返回经过检查的路径。
        return path

    # 仅加载和切分，不访问数据库或模型。
    def preview(self, file_name: str) -> dict:
        # 先检查输入文件。
        path = self.resolve_file(file_name)
        # 明确关闭写入。
        documents = self.preview_pipeline.run(path, tenant_id=self.tenant_id, write=False)
        # 返回每篇资料的预览结果，块数量属于切分结果。
        return {"documents": documents}

    # 调用方显式请求此方法时，才向现有知识库写入。
    def ingest(self, file_name: str) -> dict:
        # 启动应用不会运行这里。
        path = self.resolve_file(file_name)
        # 只复用现有入库逻辑，不建表或迁移。
        documents = self.ingestion_pipeline.run(path, tenant_id=self.tenant_id, write=True)
        # 返回文档处理结果。
        return {"documents": documents}

    # 使用可信身份问答，请求只能缩小资料范围。
    def ask(
        self,
        question: str,
        business_module: str | None = None,
        doc_type: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        # 未提供标签时使用空列表。
        if tags is None:
            # 不把 None 交给标签筛选逻辑。
            tags = []
        # 可选筛选项不允许覆盖租户和读取级别。
        filters = SearchFilter(
            tenant_id=self.tenant_id,
            max_security_level=self.security_level,
            business_module=business_module,
            doc_type=doc_type,
            tags=tags,
        )
        # RAG 只返回回答、引用与业务结果。
        return self.pipeline.ask(question, filters)
