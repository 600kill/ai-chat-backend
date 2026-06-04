"""
【文件功能总结】应用自定义中间件核心文件
包含三大核心中间件，处理全局横切关注点：
1. MetricsMiddleware：请求指标监控中间件，采集HTTP请求量、耗时等Prometheus指标
2. LoggingContextMiddleware：日志上下文中间件，自动绑定用户ID、会话ID到日志
3. ProfilingMiddleware：性能剖析中间件，DEBUG模式下自动分析慢请求，生成性能报告
"""

import json
import time
import tracemalloc
from typing import Callable

# 请求ID追踪
from asgi_correlation_id import correlation_id
# FastAPI请求对象
from fastapi import Request
# JWT认证相关
from jose import (
    JWTError,
    jwt,
)
# 基础中间件基类
from starlette.middleware.base import BaseHTTPMiddleware
# 响应对象
from starlette.responses import Response

# 全局配置
from app.core.config import settings
# 日志上下文工具
from app.core.logging import (
    bind_context,
    clear_context,
    logger,
)
# 监控指标
from app.core.metrics import (
    db_connections,
    http_request_duration_seconds,
    http_requests_total,
)

# 尝试导入性能分析库（可选依赖）
try:
    from pyinstrument import Profiler
    from pyinstrument.renderers import JSONRenderer

    PYINSTRUMENT_AVAILABLE = True
except ImportError:
    PYINSTRUMENT_AVAILABLE = False


class MetricsMiddleware(BaseHTTPMiddleware):
    """HTTP请求指标监控中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        拦截每个请求，采集监控指标
        Args:
            request: 客户端请求对象
            call_next: 调用下一个中间件/路由处理器
        Returns:
            服务端响应对象
        """
        # 记录请求开始时间
        start_time = time.time()

        try:
            # 执行后续请求处理流程
            response = await call_next(request)
            # 获取响应状态码
            status_code = response.status_code
        except Exception:
            # 发生异常，标记为500错误
            status_code = 500
            raise
        finally:
            # 计算请求总耗时
            duration = time.time() - start_time

            # 记录请求总数指标（标签：请求方法、接口、状态码）
            http_requests_total.labels(method=request.method, endpoint=request.url.path, status=status_code).inc()

            # 记录请求耗时分布指标
            http_request_duration_seconds.labels(method=request.method, endpoint=request.url.path).observe(duration)

        return response


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """日志上下文绑定中间件：自动添加用户ID、会话ID到日志"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        从请求中提取认证信息，绑定到日志上下文
        Args:
            request: 客户端请求对象
            call_next: 调用下一个中间件/路由处理器
        Returns:
            服务端响应对象
        """
        try:
            # 清除上一个请求残留的上下文
            clear_context()

            # 从请求头提取Authorization认证信息
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                # 拆分获取JWT令牌
                token = auth_header.split(" ")[1]

                try:
                    # 解析JWT令牌，获取会话ID（sub字段）
                    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
                    session_id = payload.get("sub")

                    if session_id:
                        # 将会话ID绑定到日志上下文
                        bind_context(session_id=session_id)

                except JWTError:
                    # JWT令牌无效，不拦截请求，由认证依赖处理
                    pass

            # 执行后续请求处理
            response = await call_next(request)

            # 请求处理完成后，检查是否绑定了用户ID
            if hasattr(request.state, "user_id"):
                bind_context(user_id=request.state.user_id)

            return response

        finally:
            # 请求结束后，强制清除上下文，防止上下文泄漏
            clear_context()


class ProfilingMiddleware(BaseHTTPMiddleware):
    """
    自动请求性能剖析中间件（仅DEBUG模式生效）
    使用pyinstrument分析慢请求，生成JSON性能报告，便于调试接口性能瓶颈
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        性能剖析核心逻辑：慢请求自动生成性能报告
        Args:
            request: 客户端请求对象
            call_next: 调用下一个中间件/路由处理器
        Returns:
            服务端响应对象
        """
        # 未安装性能库，直接跳过
        if not PYINSTRUMENT_AVAILABLE:
            return await call_next(request)

        # 启动内存追踪
        tracemalloc.start()
        # 记录CPU开始时间
        cpu_start = time.process_time()

        # 初始化异步性能剖析器
        profiler = Profiler(async_mode="enabled")
        with profiler:
            # 执行请求处理
            response = await call_next(request)

        # 采集性能数据
        cpu_ms = round((time.process_time() - cpu_start) * 1000, 2)
        mem_current_kb, mem_peak_kb = (v // 1024 for v in tracemalloc.get_traced_memory())
        snapshot = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # 计算请求总耗时
        wall_ms = round((profiler.last_session.duration if profiler.last_session else 0.0) * 1000, 2)

        # 判断是否超过性能阈值，超过则生成报告
        if wall_ms / 1000 >= settings.PROFILING_THRESHOLD_SECONDS:
            raw_id = correlation_id.get() or "unknown"
            # 格式化请求ID
            if len(raw_id) == 32 and "-" not in raw_id:
                raw_id = f"{raw_id[:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"

            # 创建性能报告目录
            settings.PROFILING_DIR.mkdir(parents=True, exist_ok=True)
            filepath = settings.PROFILING_DIR / f"{raw_id}.json"

            # 过滤内存占用统计（排除库自身干扰）
            _excluded = ("tracemalloc", "pyinstrument", "<frozen", "logging/__init__")
            top_allocs = [
                {
                    "file": str(stat.traceback[0].filename).replace(str(__file__).rsplit("/", 3)[0] + "/", ""),
                    "line": stat.traceback[0].lineno,
                    "size_kb": round(stat.size / 1024, 2),
                    "count": stat.count,
                }
                for stat in snapshot.statistics("lineno")
                if not any(ex in str(stat.traceback[0].filename) for ex in _excluded)
            ]

            # 生成完整性能报告
            call_tree = json.loads(profiler.output(renderer=JSONRenderer()))
            report = {
                "request_id": raw_id,
                "endpoint": f"{request.method} {request.url.path}",
                "wall_time_ms": wall_ms,
                "cpu_time_ms": cpu_ms,
                "io_wait_ms": round(wall_ms - cpu_ms, 2),
                "memory_peak_kb": mem_peak_kb,
                "memory_allocated_kb": mem_current_kb,
                "top_memory_allocators": top_allocs,
                "call_tree": call_tree,
            }
            filepath.write_text(json.dumps(report, indent=2))
            logger.debug(
                "slow_request_profile_saved",
                path=request.url.path,
                method=request.method,
                wall_time_ms=wall_ms,
                cpu_time_ms=cpu_ms,
                memory_peak_kb=mem_peak_kb,
                io_wait_ms=round(wall_ms - cpu_ms, 2),
                profile_file=str(filepath),
            )

        return response