import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


# 根目录直接 Run / Debug 时可以导入 src 包。
BASE_DIR = Path(__file__).resolve().parent
# 保留项目已有的包定位方式。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.api import agent, lessons, orders, rag
from agent_learning.bootstrap import build_services
from agent_learning.core.errors import ServiceError


# 创建应用；离线核查可以传入纯内存服务，不读取真实配置。
def create_app(services=None) -> FastAPI:
    # lifespan 只在启动和关闭时执行，普通业务仍使用同步函数。
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 正常启动只构造对象，不进行数据库操作或模型请求。
        if services is None:
            # 应用中的请求共用同一套服务和内存会话。
            app.state.services = build_services()
        # 离线核查使用显式提供的替身。
        else:
            # 不访问真实模型或数据库。
            app.state.services = services
        # 将控制权交回 FastAPI 处理请求。
        yield
        # 关闭时释放服务引用，不删除目录或文件。
        app.state.services = None

    # 使用 FastAPI 自带的 Swagger 文档。
    app = FastAPI(title="AI 学习 API：截至第 70 课", lifespan=lifespan)

    # 业务错误只返回明确的简短说明。
    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
        # 不附带执行记录或异常堆栈。
        return JSONResponse(status_code=error.status_code, content={"detail": error.message})

    # 参数校验失败不回显提交的整份输入。
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # Swagger 中可以查看字段与类型要求。
        return JSONResponse(status_code=422, content={"detail": "请求参数无效，请检查字段与类型。"})

    # 未处理异常不转换成运行日志或对外暴露内部配置。
    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        # 调试时可以在原方法设置断点。
        return JSONResponse(status_code=500, content={"detail": "处理失败，请检查服务配置或输入。"})

    # JSON 入参示例：{}；实际为 GET /health，无 JSON 请求体。
    # 只检查 HTTP 应用，不探测数据库或模型。
    @app.get("/health", tags=["服务检查"])
    def health() -> dict:
        # 返回固定的服务就绪结果。
        return {"status": "ok"}

    # 注册资料接口。
    app.include_router(rag.router)
    # 注册订单接口。
    app.include_router(orders.router)
    # 注册 Agent 会话接口。
    app.include_router(agent.router)
    # 注册基础课程接口。
    app.include_router(lessons.router)
    # 导入模块时只创建应用，不执行启动逻辑。
    return app


# Uvicorn 和 IDE 都使用同一个应用。
app = create_app()


# 直接运行时启动一个进程，内存会话不跨进程共享。
if __name__ == "__main__":
    import uvicorn
    # 关闭访问日志和框架日志，业务代码也不生成执行日志。
    uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False, log_config=None, log_level="critical")
