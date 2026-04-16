import os
from celery import Celery

redis_url = os.getenv("REDIS_URI", "redis://localhost:6379")

celery_app = Celery(
    "qa_chat_tester",
    broker=f"{redis_url}/0",
    backend=f"{redis_url}/1",   # separate DB from broker
    include=["celery_queue.jobs.tasks"],
)

WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", 1))

celery_app.conf.update(
    # ── Serialization ─────────────────────────────────────────────────────────
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # ── Reliability ────────────────────────────────────────────────────────────
    # Ack AFTER the task completes — if the worker dies mid-conversation the
    # task goes back to the queue instead of being lost.
    task_acks_late=True,
    # Don't prefetch more than 1 task per worker slot — each case takes minutes,
    # so prefetching would starve other workers.
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,

    # ── Timeouts ───────────────────────────────────────────────────────────────
    # Soft: raises SoftTimeLimitExceeded (catchable) at 12 min
    # Hard: SIGKILL at 15 min — adjust if your conversations can run longer
    task_soft_time_limit=720,
    task_time_limit=900,

    # ── Result backend (needed for group/chord status tracking) ────────────────
    result_expires=7200,          # keep results 2h

    # ── Concurrency ────────────────────────────────────────────────────────────
    worker_concurrency=WORKER_CONCURRENCY,
)
