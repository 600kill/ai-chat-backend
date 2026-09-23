"""评测队列（RQ + Redis）与 worker 入口。

- API 进程通过 enqueue_evaluation_run() 入队。
- 生产（Linux/Docker）：`rq worker evaluations --url redis://redis:6379`，
  worker 启动脚本见 docker-compose.yml worker 服务；须先调 init_langfuse()。
- 本地开发（Windows 无 fork）：`python -m app.tasks.evaluation_worker`
  使用 SimpleWorker 同进程串行消费，功能一致。
"""

from redis import Redis
from rq import Queue, SimpleWorker

from app.core.config import settings
from app.core.logging import logger

QUEUE_NAME = "evaluations"


def get_redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL)


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=get_redis())


def enqueue_evaluation_run(run_id: str, only_pending: bool = False) -> str:
    """把评测 run 入队（API 层调用）。"""
    from app.services.evaluation.runner import execute_run_job

    queue = get_queue()
    job = queue.enqueue(
        execute_run_job,
        run_id,
        only_pending,
        job_timeout=3600,
        result_ttl=86400,
    )
    logger.info("eval_run_enqueued", run_id=run_id, job_id=job.id, only_pending=only_pending)
    return job.id


def run_worker_local() -> None:
    """本地 worker 入口（Windows 兼容：SimpleWorker 同进程串行执行）。

    与生产 rq worker 等价：先 init_langfuse() 保证评测 trace 上报。
    """
    from app.core.observability.langfuse_tracing import init_langfuse

    init_langfuse()
    queue = get_queue()
    logger.info("eval_worker_started", queue=QUEUE_NAME, url=settings.REDIS_URL, mode="simple")
    SimpleWorker([queue], connection=queue.connection).work(burst=False)


if __name__ == "__main__":
    run_worker_local()
