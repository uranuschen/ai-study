from fastapi import APIRouter, Depends, Path
from agent_learning.api.dependencies import get_agent_service
from agent_learning.api.schemas import ApprovalRequest, QuestionRequest, ResumeRequest, SessionRequest
from agent_learning.services.agent_service import AgentService


# 会话相关接口使用同一个资源前缀。
router = APIRouter(prefix="/api/agent/sessions", tags=["Agent 会话"])


# JSON 入参示例：{"pause_before_tools": false}；传 {} 也可以。
# 改为 true 可以演示工具执行前暂停和恢复。
@router.post("", status_code=201)
def create_session(body: SessionRequest, service: AgentService = Depends(get_agent_service)) -> dict:
    # 新会话不会调用模型。
    return service.create_session(body.pause_before_tools)


# JSON 入参示例：{"question": "检查 A1002 的订单、支付和退款情况"}
# session_id 使用创建会话接口返回的值。
@router.post("/{session_id}/messages")
def ask(
    body: QuestionRequest,
    session_id: str = Path(min_length=1, max_length=64),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    # 相同编号用于多轮追问，模型按需选择业务或知识库工具。
    return service.ask(session_id, body.question)


# 参数 JSON 示意：{"session_id": "创建会话返回的编号"}；实际为 GET 路径参数，无 JSON 请求体。
# 返回对话和待办，不返回整份图状态。
@router.get("/{session_id}")
def get_session(
    session_id: str = Path(min_length=1, max_length=64),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    # 只读取已经保存的会话。
    return service.get_session(session_id)


# JSON 入参示例：{}；session_id 写在 URL 路径中。
# 只恢复普通暂停或仍有待执行节点的任务，不能绕过人工审批。
@router.post("/{session_id}/resume")
def resume(
    body: ResumeRequest,
    session_id: str = Path(min_length=1, max_length=64),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    # 服务层使用同一 Checkpoint 继续执行。
    return service.resume(session_id)


# JSON 入参示例：{"approval_id": "待审批响应中的编号", "decision": "approve"}
# decision 改为 reject 表示拒绝；客户端不能补交订单、租户或工具参数。
@router.post("/{session_id}/approvals")
def approve(
    body: ApprovalRequest,
    session_id: str = Path(min_length=1, max_length=64),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    # 只审批当前编号绑定的模拟操作。
    return service.approve(session_id, body.approval_id, body.decision)
