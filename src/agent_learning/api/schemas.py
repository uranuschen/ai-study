from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


# API 参数统一拒绝未知字段，避免客户端修改内部状态。
class RequestModel(BaseModel):
    # 去掉字符串首尾空白，字段仍按各自类型校验。
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# 预览和入库只接收 data 目录内的相对文件名。
class FileRequest(RequestModel):
    # 文件路径范围由 Service 再次校验。
    file_name: str = Field(min_length=1, max_length=255)


# 基础演示与会话提问共用简单问题参数。
class QuestionRequest(RequestModel):
    # 不接收空白问题或无限长输入。
    question: str = Field(min_length=1, max_length=4000)


# 知识库问答允许缩小资料范围，不接受租户或权限参数。
class RagQuestionRequest(QuestionRequest):
    # 可选业务模块。
    business_module: str | None = Field(default=None, max_length=100)
    # 可选资料类型。
    doc_type: str | None = Field(default=None, max_length=100)
    # 标签只作为资料筛选条件。
    tags: list[str] = Field(default_factory=list)


# 固定订单流程和业务 Tool 示例接收结构化订单号。
class OrderRequest(RequestModel):
    # 租户始终由服务端提供。
    order_id: str = Field(min_length=1, max_length=64)


# 新会话可以开启工具前暂停，演示第 65 课。
class SessionRequest(RequestModel):
    # 默认连续执行普通工具。
    pause_before_tools: bool = False


# 人工只提交当前审批编号和明确决定。
class ApprovalRequest(RequestModel):
    # 旧审批编号不能用于新目标。
    approval_id: str = Field(min_length=1, max_length=64)
    # 不接受模型自由生成的确认文字。
    decision: Literal["approve", "reject"]


# 普通恢复只需要路径中的会话编号，请求体固定为 {}。
class ResumeRequest(RequestModel):
    # 不允许通过恢复接口补交新问题或修改图状态。
    pass
