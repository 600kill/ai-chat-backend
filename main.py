"""
这份文件是整个项目的【主入口文件】
作用：启动整个FastAPI服务、挂载接口、管理项目生命周期
"""

# 导入异步上下文管理器（用于管理项目启动/关闭）
from contextlib import asynccontextmanager
# 导入时间模块（用于健康检查返回时间戳）
from datetime import datetime
# 导入类型注解工具（规范函数参数/返回值类型）
from typing import (
    Any,
    Dict,
)

# Windows平台修复：psycopg3 async需要SelectorEventLoop
import sys
import asyncio
if sys.platform == "win32":
    from asyncio import WindowsSelectorEventLoopPolicy
    asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())

# ==================== 第三方库导入 ====================
# 加载.env环境变量文件（数据库地址、密钥等配置）
from dotenv import load_dotenv
# FastAPI核心：应用对象、请求对象、状态码
from fastapi import (
    FastAPI,
    Request,
    status,
)
# FastAPI自带的：请求参数验证错误异常
from fastapi.exceptions import RequestValidationError
# FastAPI自带的：跨域中间件（解决前端访问后端的跨域问题）
from fastapi.middleware.cors import CORSMiddleware
# FastAPI自带的：JSON格式响应体
from fastapi.responses import JSONResponse
# 接口限流库：处理请求超限的异常

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
# ==================== 【观测层/可删除】导入 开始 ====================
# 请求唯一ID（日志追踪用，可删）
from asgi_correlation_id import CorrelationIdMiddleware
# ==================== 【观测层/可删除】导入 结束 ====================

# ==================== 项目内部模块导入 ====================
# 导入项目所有接口的路由集合
from app.api.v1.router import api_router
# 导入LangGraph智能体核心
from app.api.v1.chatbot import agent
# 导入缓存服务（Valkey/Redis）
from app.core.cache import cache_service
# 导入项目全局配置
from app.core.config import settings
# 导入接口限流工具
from app.core.limiter import limiter
# Langfuse 可观测性（trace 上报客户端）
from app.core.observability import init_langfuse, shutdown_langfuse



# 导入数据库服务
from app.services.database import database_service
# 导入记忆服务
from app.services.memory import memory_service

# ==================== 初始化配置 ====================
# 加载 .env 文件中的环境变量（配置不写死在代码里）
load_dotenv()
# 【观测层/可删除】初始化LLM监控工具
#langfuse_init()

# ==================== 项目生命周期函数（核心！） ====================
# 装饰器：标记这是一个异步的生命周期管理函数
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    【项目启动/关闭 管理函数】
    1. yield 上方的代码：项目【启动时】执行
    2. yield 下方的代码：项目【关闭时】执行
    """
    # 【观测层/可删除】打印启动日志
    '''logger.info(
        "application_startup",
        project_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        api_prefix=settings.API_V1_STR,
    )'''

    # ==================== 启动时执行：初始化 Langfuse trace 客户端 ====================
    init_langfuse()

    # ==================== 启动时执行：初始化缓存服务 ====================
    try:
        # 连接Valkey/Redis缓存
        await cache_service.initialize()
    except Exception as e:
        # 【观测层/可删除】缓存连接失败打印日志
        #logger.exception("cache_initialization_failed", error=str(e))
        pass


    # ==================== 启动时执行：预加载LangGraph智能体 ====================
    # 作用：项目启动时就初始化AI智能体，避免第一次访问卡顿
    try:
        await agent.create_graph()
        # 【观测层/可删除】打印日志
        #logger.info("graph_pre_warmed")
    except Exception as e:
        # 【观测层/可删除】初始化失败打印日志
        #logger.exception("graph_pre_warm_failed", error=str(e))
        pass


    # ==================== 启动时执行：预加载记忆服务 ====================
    # 作用：提前连接向量数据库，优化首次请求速度
    try:
        await memory_service.initialize()
    except Exception as e:
        # 【观测层/可删除】初始化失败打印日志
        #logger.exception("memory_service_pre_warm_failed", error=str(e))
        pass

    # 暂停在这里，等待项目运行
    yield

    # ==================== 关闭时执行：资源释放 ====================
    # 关闭缓存连接
    await cache_service.close()
    # 关闭 Langfuse 客户端（flush 残余事件）
    shutdown_langfuse()
    # 关闭智能体的数据库连接池
    if agent._connection_pool:
        await agent._connection_pool.close()
        # 【观测层/可删除】打印关闭日志
        #logger.info("connection_pool_closed")
    # 【观测层/可删除】打印项目关闭日志
    #logger.info("application_shutdown")

# ==================== 创建FastAPI应用实例（核心！） ====================
app = FastAPI(
    # 项目名称（从配置文件读取）
    title=settings.PROJECT_NAME,
    # 项目版本
    version=settings.VERSION,
    # 项目描述
    description=settings.DESCRIPTION,
    # OpenAPI文档地址（/swagger 接口文档）
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    # 绑定上面的生命周期函数
    lifespan=lifespan,
)



# ==================== 接口限流配置（核心！） ====================
# 绑定限流工具
app.state.limiter = limiter
# 注册限流异常处理器（请求太频繁时返回友好提示）
app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
    status_code=429,
    content={"detail": "请求过于频繁，请稍后重试"}
))

# ==================== 全局异常处理：参数验证错误（核心！） ====================
# 装饰器：捕获所有请求参数错误
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    作用：前端传错参数时，不返回系统默认的乱码错误
    而是返回【友好、清晰的中文错误提示】
    """
    # 【观测层/可删除】打印错误日志
    '''logger.error(
        "validation_error",
        client_host=request.client.host if request.client else "unknown",
        path=request.url.path,
        errors=str(exc.errors()),
    )'''

    # 格式化错误信息，让前端更容易看懂
    formatted_errors = []
    for error in exc.errors():
        # 拼接错误的字段位置
        loc = " -> ".join([str(loc_part) for loc_part in error["loc"] if loc_part != "body"])
        formatted_errors.append({"field": loc, "message": error["msg"]})

    # 返回422状态码 + 格式化错误
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "参数校验错误", "errors": formatted_errors},
    )

# ==================== 跨域配置（核心！） ====================
# 解决前端（浏览器/APP）访问后端接口的跨域问题
app.add_middleware(
    CORSMiddleware,
    # 允许访问的前端地址
    allow_origins=settings.ALLOWED_ORIGINS,
    # 允许携带cookie/凭证
    allow_credentials=True,
    # 允许所有请求方式（GET/POST/PUT等）
    allow_methods=["*"],
    # 允许所有请求头
    allow_headers=["*"],
)

# ==================== 挂载所有接口（核心！） ====================
# 把项目所有接口注册到FastAPI中
# 访问前缀：/api/v1
app.include_router(api_router, prefix=settings.API_V1_STR)

# ==================== 根接口（首页接口） ====================
@app.get("/")
# 接口限流：限制访问频率
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["root"][0])
async def root(request: Request):
    """
    访问地址：http://127.0.0.1:8000/
    作用：返回项目基础信息
    """
    # 【观测层/可删除】打印日志
    #logger.info("root_endpoint_called")
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "运行正常",
        "环境": settings.ENVIRONMENT.value,
        "接口文档地址": "/docs",
        "官方文档地址": "/redoc",
    }

# ==================== 健康检查接口（核心！） ====================
@app.get("/health")
# 接口限流
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["health"][0])
async def health_check(request: Request) -> Dict[str, Any]:
    """
    访问地址：http://127.0.0.1:8000/health
    作用：检查项目+数据库是否正常运行
    """
    # 【观测层/可删除】打印日志
    #logger.info("health_check_called")

    # 检查数据库是否能正常连接
    db_healthy = await database_service.health_check()

    # 组装响应结果
    response = {
        "status": "正常" if db_healthy else "服务异常",
        "版本": settings.VERSION,
        "环境": settings.ENVIRONMENT.value,
        "组件状态": {
            "接口服务": "正常",
            "数据库": "正常" if db_healthy else "异常"
        },
        "当前时间": datetime.now().isoformat(),
    }

    # 数据库正常返回200，异常返回503
    status_code = status.HTTP_200_OK if db_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(content=response, status_code=status_code)