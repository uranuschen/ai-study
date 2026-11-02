from openai import APIConnectionError, APIStatusError, APITimeoutError


# 判断是否属于可以有限重试的临时错误，不记录错误内容。
def is_temporary_error(error: Exception) -> bool:
    # 连接失败和超时允许重试。
    if isinstance(error, (ConnectionError, TimeoutError, APIConnectionError, APITimeoutError)):
        # 交给调用方决定是否还有重试机会。
        return True
    # HTTP 只对限流、暂时不可用等情况重试。
    if isinstance(error, APIStatusError):
        # 服务端错误通常是临时错误。
        if error.status_code >= 500:
            # 返回判断结果，不保存状态码记录。
            return True
        # 其他列出的状态也允许有限重试。
        return error.status_code in (408, 409, 429)
    # 参数、认证和其他错误不自动重试。
    return False
