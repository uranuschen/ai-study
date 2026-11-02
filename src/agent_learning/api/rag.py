from fastapi import APIRouter, Depends
from agent_learning.api.dependencies import get_rag_service
from agent_learning.api.schemas import FileRequest, RagQuestionRequest
from agent_learning.services.rag_service import RagService


# RAG 的三个接口使用相同前缀。
router = APIRouter(prefix="/api/rag", tags=["资料与知识库"])


# JSON 入参示例：{"file_name": "enterprise_documents.json"}
# 预览只加载和切分，不写数据库，不调用模型。
@router.post("/preview")
def preview(body: FileRequest, service: RagService = Depends(get_rag_service)) -> dict:
    # 接口层只传递经过校验的参数。
    return service.preview(body.file_name)


# JSON 入参示例：{"file_name": "enterprise_documents.json"}
# 显式调用才执行向量入库；不会自动建表或初始化。
@router.post("/ingest")
def ingest(body: FileRequest, service: RagService = Depends(get_rag_service)) -> dict:
    # 入库过程继续复用现有 IngestionPipeline。
    return service.ingest(body.file_name)


# JSON 入参示例：{"question": "退款通常多久到账？", "doc_type": "policy", "tags": []}
# business_module 和 doc_type 可省略，租户与读取权限由服务端提供。
@router.post("/ask")
def ask(body: RagQuestionRequest, service: RagService = Depends(get_rag_service)) -> dict:
    # 返回答案、引用和资料是否足够等业务结果。
    return service.ask(body.question, body.business_module, body.doc_type, body.tags)
