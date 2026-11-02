from fastapi import Request


# 从应用中取得已经创建好的知识库服务。
def get_rag_service(request: Request):
    # 不在每个请求里重新创建模型与流程。
    return request.app.state.services["rag"]


# 从应用中取得订单业务服务。
def get_order_service(request: Request):
    # 身份和数据文件已经绑定在服务对象中。
    return request.app.state.services["orders"]


# 所有会话接口共用同一个 Agent 服务。
def get_agent_service(request: Request):
    # 避免请求结束后丢失 Checkpoint。
    return request.app.state.services["agent"]


# 取得独立课程演示服务。
def get_lesson_service(request: Request):
    # 小图已经在启动时编译。
    return request.app.state.services["lessons"]
