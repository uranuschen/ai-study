# 导入包路径处理所需的标准库。
import sys
# 根据启动文件定位项目根目录。
from pathlib import Path
# 导入 HTTP 服务启动器，与 main_api.py 使用同一种启动方式。
import uvicorn


# 根目录直接 Run / Debug 时，也能找到 src 下的业务代码。
BASE_DIR = Path(__file__).resolve().parent
# 与现有 main_api.py 使用相同的包定位方式。
sys.path.insert(0, str(BASE_DIR / "src"))

# 导入已经注册 hello、greet、get_order 的 MCP Server。
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
