from typing import Literal
import io
import uuid
import time
from collections import OrderedDict
from langchain_core.tools import tool
import matplotlib.pyplot as plt
# ======================
# LRU 缓存（全局唯一）
# ======================
MAX_CACHE_SIZE = 100
GLOBAL_LRU_CACHE = OrderedDict()


def _save_to_lru(img_bytes: bytes) -> str:
    """存图，超上限自动删最久未用的"""
    img_id = str(uuid.uuid4())

    GLOBAL_LRU_CACHE[img_id] = {
        "data": img_bytes,
        "last_use": time.time()
    }

    # 淘汰逻辑
    if len(GLOBAL_LRU_CACHE) > MAX_CACHE_SIZE:
        GLOBAL_LRU_CACHE.popitem(last=False)

    return img_id


def _get_from_lru(img_id: str) -> bytes:
    """取图，并更新访问时间（供接口用）"""
    if img_id not in GLOBAL_LRU_CACHE:
        raise KeyError("Image not found or expired")

    item = GLOBAL_LRU_CACHE.pop(img_id)
    item["last_use"] = time.time()
    GLOBAL_LRU_CACHE[img_id] = item

    return item["data"]


# ======================
# 工具函数
# ======================
@tool
def generate_chart(
        chart_type: Literal["line", "bar", "pie"],
        x: str | None = None,
        y: str | None = None,
        categories: str | None = None,
        values: str | None = None,
        title: str = "",
) -> str:
    """
    生成图表并存入LRU缓存，返回图片ID。

    参数说明：
    - chart_type: 图表类型，"line"(折线图)、"bar"(柱状图)、"pie"(饼图)
    - x: 折线图X轴数据，逗号分隔，如 "1月,2月,3月,4月,5月,6月"
    - y: 折线图Y轴数据，逗号分隔，如 "100,200,150,300,250,400"
    - categories: 柱状图/饼图的分类标签，逗号分隔
    - values: 柱状图/饼图的数值，逗号分隔
    - title: 图表标题

    调用示例：
    - 折线图: generate_chart(chart_type="line", x="1月,2月,3月", y="100,200,150", title="销售趋势")
    - 柱状图: generate_chart(chart_type="bar", categories="A,B,C", values="10,20,30", title="柱状图")
    - 饼图: generate_chart(chart_type="pie", categories="A,B,C", values="30,40,30", title="占比图")
    """
    if not x and not categories:
        return "错误：请提供数据。折线图需要 x,y 参数；柱状图/饼图需要 categories,values 参数。"

    plt.rcParams["font.family"] = ["SimHei", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(10, 6))

    # 1. 画图
    try:
        if chart_type == "line":
            if not x or not y:
                return "错误：折线图需要 x 和 y 参数，请用逗号分隔数据，如 x=\"1月,2月,3月\", y=\"100,200,150\""
            xs = list(map(float, x.split(","))) if not _is_chinese(x) else [s.strip() for s in x.split(",")]
            ys = list(map(float, y.split(",")))
            ax.plot(xs, ys, marker="o", linewidth=2)
        elif chart_type == "bar":
            if not categories or not values:
                return "错误：柱状图需要 categories 和 values 参数"
            ax.bar(categories.split(","), list(map(float, values.split(","))))
        elif chart_type == "pie":
            if not values:
                return "错误：饼图需要 values 参数"
            ax.pie(list(map(float, values.split(","))),
                   labels=categories.split(",") if categories else None,
                   autopct="%1.1f%%")
            ax.axis("equal")
    except ValueError as e:
        return f"错误：数据格式不正确，请确保数值用逗号分隔。详情：{e}"

    ax.set_title(title, loc="left", fontsize=14)
    ax.grid(True, linestyle="--", alpha=0.5)

    # 2. 转字节
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    # 3. 存LRU，返回ID
    return _save_to_lru(buf.read())


def _is_chinese(s: str) -> bool:
    """检查字符串是否包含中文"""
    return any('\u4e00' <= c <= '\u9fff' for c in s)
