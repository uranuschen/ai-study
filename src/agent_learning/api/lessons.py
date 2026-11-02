from fastapi import APIRouter, Depends
from agent_learning.api.dependencies import get_lesson_service
from agent_learning.api.schemas import OrderRequest, QuestionRequest
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
