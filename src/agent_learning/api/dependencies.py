from fastapi import Request
from agent_learning.services.agent_service import AgentService
from agent_learning.services.lesson_service import LessonService
from agent_learning.services.order_service import OrderService
from agent_learning.services.rag_service import RagService


# 从应用中取得已经创建好的知识库服务。
def get_rag_service(request: Request) -> RagService:
    # 不在每个请求里重新创建模型与流程。
    return request.app.state.services["rag"]


# 从应用中取得订单业务服务。
def get_order_service(request: Request) -> OrderService:
    # 身份和数据文件已经绑定在服务对象中。
    return request.app.state.services["orders"]


# 所有会话接口共用同一个 Agent 服务。
def get_agent_service(request: Request) -> AgentService:
    # 避免请求结束后丢失 Checkpoint。
    return request.app.state.services["agent"]


# 取得独立课程演示服务。
def get_lesson_service(request: Request) -> LessonService:
    # 小图已经在启动时编译。
    return request.app.state.services["lessons"]
