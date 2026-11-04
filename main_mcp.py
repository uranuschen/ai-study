# 导入 HTTP 服务启动器，与 main_api.py 使用同一种启动方式。
import uvicorn
# 导入已经注册 hello、greet 的 MCP Server。
from mcp_server.server import mcp


# SDK 生成 Streamable HTTP 应用和 /mcp 地址，生命周期也由 SDK 管理。
# json_response=True 让调用结果直接返回 JSON，方便在 Postman 中查看。
app = mcp.streamable_http_app(json_response=True)


# 直接 Run / Debug 本文件时才监听端口。
if __name__ == "__main__":
    # 在本机 8001 端口启动，关闭访问日志和框架日志。
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8001,
        access_log=False,
        log_config=None,
        log_level="critical",
    )
