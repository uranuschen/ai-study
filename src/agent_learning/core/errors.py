# Service 使用固定业务说明，HTTP 层只负责转换为响应。
class ServiceError(Exception):
    # 保存 HTTP 状态码与可以对调用方展示的说明。
    def __init__(self, status_code: int, message: str):
        # 异常正文不包含底层连接信息。
        super().__init__(message)
        # 保存响应状态码。
        self.status_code = status_code
        # 保存简短业务说明。
        self.message = message
