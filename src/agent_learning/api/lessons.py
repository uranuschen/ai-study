from fastapi import APIRouter, Depends, Path
from agent_learning.api.dependencies import get_agent_service, get_lesson_service
from agent_learning.api.schemas import OrderRequest, QuestionRequest, ResumeRequest
from agent_learning.services.agent_service import AgentService
from agent_learning.services.lesson_service import LessonService


# 保留基础图的独立学习入口。
router = APIRouter(prefix="/api/lessons", tags=["基础 LangGraph"])


# JSON 入参示例：{"question": "你好，LangGraph"}
# 单节点回显，不调用模型。
@router.post("/single-node")
def single_node(body: QuestionRequest, service: LessonService = Depends(get_lesson_service)) -> dict:
    # 查看一个节点如何读写 State。
    return service.run_single_node(body.question)


# JSON 入参示例：{"question": "  两个节点传值  "}
# 第一节点清理文字，第二节点读取清理后的字段。
@router.post("/state-flow")
def state_flow(body: QuestionRequest, service: LessonService = Depends(get_lesson_service)) -> dict:
    # 展示节点间 State 传值。
    return service.run_state_flow(body.question)


# JSON 入参示例：{"question": "统计字数：你好世界"}
# 普通文字走回显分支，固定前缀走本地字符数工具。
@router.post("/conditional-route")
def conditional_route(body: QuestionRequest, service: LessonService = Depends(get_lesson_service)) -> dict:
    # 条件边选择互斥分支。
    return service.run_conditional_route(body.question)


# JSON 入参示例：{"order_id": "A1002"}
# 换成不存在的订单号，可以观察业务失败回答。
@router.post("/business-tool")
def business_tool(body: OrderRequest, service: LessonService = Depends(get_lesson_service)) -> dict:
    # 只读 JSON，保留业务成功与失败分支。
    return service.run_business_tool(body.order_id)


# JSON 入参示例：{"question": "你好，暂停演示"}
# 内部通过 create_session 生成 ID，执行第一步后固定暂停，不调用模型。
@router.post("/pause-demo")
def start_pause_demo(body: QuestionRequest, service: AgentService = Depends(get_agent_service)) -> dict:
    # 返回新 session_id 和 paused，供第二个接口使用。
    return service.start_pause_demo(body.question)


# JSON 入参示例：{}；session_id 使用上一个演示接口返回的编号。
# 继续同一个演示会话，只执行剩下的第二步。
@router.post("/pause-demo/{session_id}/resume")
def resume_pause_demo(
    body: ResumeRequest,
    session_id: str = Path(min_length=1, max_length=64),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    # 复用现有恢复方法，它会使用 invoke(None, config=原配置)。
    return service.resume_pause_demo(session_id)


# JSON 入参示例：{"order_id": "A1001"}
# 自动创建会话并申请模拟取消；不调用 LLM，不读取或修改业务数据。
@router.post("/approval-demo")
def start_approval_demo(body: OrderRequest, service: AgentService = Depends(get_agent_service)) -> dict:
    # 返回 waiting_approval、session_id 和 approval_id，接着调用原 approvals 接口批准。
    return service.start_approval_demo(body.order_id)
