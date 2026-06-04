"""
【文件功能总结】应用监控指标配置核心文件
基于 Prometheus 实现应用全维度监控，集成 FastAPI/Starlette 中间件
提供：HTTP请求监控、数据库连接监控、AI大模型推理性能监控、业务订单监控
暴露 /metrics 接口供 Prometheus 采集监控数据
"""
'''
# 导入Prometheus指标类型：计数器、直方图、仪表盘
from prometheus_client import Counter, Histogram, Gauge
# 导入FastAPI/Starlette Prometheus中间件和路由
from starlette_prometheus import metrics, PrometheusMiddleware

# -------------------------- HTTP请求监控指标 --------------------------
# 计数器：记录HTTP请求总次数，标签：请求方法、接口路径、响应状态码
http_requests_total = Counter("http_requests_total", "HTTP请求总数量", ["method", "endpoint", "status"])

# 直方图：记录HTTP请求耗时分布，标签：请求方法、接口路径
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP请求耗时(秒)", ["method", "endpoint"]
)

# -------------------------- 数据库监控指标 --------------------------
# 仪表盘：实时记录当前活跃的数据库连接数
db_connections = Gauge("db_connections", "活跃数据库连接数量")

# -------------------------- 自定义业务监控指标 --------------------------
# 计数器：记录订单处理总次数
orders_processed = Counter("orders_processed_total", "订单处理总数量")

# 直方图：记录LLM大模型推理耗时，标签：模型名称，自定义耗时区间
llm_inference_duration_seconds = Histogram(
    "llm_inference_duration_seconds",
    "大模型推理耗时(秒)",
    ["model"],
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0],
)

# 直方图：记录LLM流式推理耗时，标签：模型名称，自定义耗时区间
llm_stream_duration_seconds = Histogram(
    "llm_stream_duration_seconds",
    "大模型流式推理耗时(秒)",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# 计数器：记录会话名称生成总次数，标签：生成状态(成功/失败)
session_names_generated_total = Counter(
    "session_names_generated_total",
    "大模型生成会话名称总次数",
    ["status"],  # 状态：success(成功) | error(失败)
)


def setup_metrics(app):
    """
    配置Prometheus监控中间件和接口
    Args:
        app: FastAPI应用实例
    """
    # 为FastAPI添加Prometheus监控中间件（自动采集请求指标）
    app.add_middleware(PrometheusMiddleware)

    # 添加监控数据暴露接口：访问 /metrics 获取所有指标
    app.add_route("/metrics", metrics)'''