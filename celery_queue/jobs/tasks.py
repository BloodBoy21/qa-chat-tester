from celery_queue.config import celery_app
from loguru import logger
from lib.cache import get_cache


cache = get_cache()


@celery_app.task(bind=True, name="jobs.run_conversation_batch")
def run_conversation_batch(self, conversation_ids: list):
    logger.info(f"Running conversation batch for IDs: {conversation_ids}")
    pass
