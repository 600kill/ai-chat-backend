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
    生成图表并存入LRU缓存，返回ID。
    """
    plt.rcParams["font.family"] = ["SimHei", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(10, 6))

    # 1. 画图
    if chart_type == "line":
        xs = list(map(float, x.split(",")))
        ys = list(map(float, y.split(",")))
        ax.plot(xs, ys, marker="o", linewidth=2)
    elif chart_type == "bar":
        ax.bar(categories.split(","), list(map(float, values.split(","))))
    elif chart_type == "pie":
        ax.pie(list(map(float, values.split(","))),
               labels=categories.split(","),
               autopct="%1.1f%%")
        ax.axis("equal")

    ax.set_title(title, loc="left", fontsize=14)
    ax.grid(True, linestyle="--", alpha=0.5)

    # 2. 转字节
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    # 3. 存LRU，返回ID
    return _save_to_lru(buf.read())
