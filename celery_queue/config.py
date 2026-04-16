import os
from celery import Celery

# Redis URL with fallback to localhost
redis_url = os.getenv("REDIS_URI", "redis://localhost:6379")

# Create Celery instance
celery_app = Celery(
    "qa_chat_tester",
    broker=f"{redis_url}/0",
    backend=f"{redis_url}/0",
    include=["celery_queue.jobs.tasks"],
)

WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", 1))

# Optional configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=WORKER_CONCURRENCY,  # Adjust based on your server capacity
    broker_connection_retry_on_startup=True,
)
