"""
【文件功能总结】全接口通用基础响应Schema文件
定义所有API接口统一继承的基础响应模型
自动携带请求唯一标识（request_id），实现全链路请求追踪
所有业务接口的响应模型都必须继承此类
"""

# UUID相关工具，用于生成唯一标识
from uuid import UUID, uuid4

# 从中间件获取请求追踪ID
from asgi_correlation_id import correlation_id
# Pydantic基础模型，用于数据校验
from pydantic import BaseModel, Field


def _get_request_id() -> UUID:
    """
    获取当前请求的追踪ID，无ID则自动生成新UUID作为备用
    返回：请求唯一标识UUID
    """
    # 获取当前请求的关联ID
    value = correlation_id.get()
    # 有ID则转换为UUID，无ID则生成新UUID
    return UUID(value) if value else uuid4()


class BaseResponse(BaseModel):
    """
    所有接口响应模型的基础父类
    request_id 自动从中间件上下文填充，接口无需手动传参
    """

    # 请求唯一标识，自动生成/获取
    request_id: UUID = Field(default_factory=_get_request_id, description="请求唯一标识符")