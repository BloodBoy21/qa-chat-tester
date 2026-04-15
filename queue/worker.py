#!/usr/bin/env python
"""
Celery worker launcher script
Run this script to start a Celery worker:
    python celery_worker.py
"""

from dotenv import load_dotenv
from lib.cache import get_cache
from lib.mongo import client as mongo_client

# Load environment variables
load_dotenv()

# Import the Celery app and tasks
from .config import celery_app
from .jobs import tasks

if __name__ == "__main__":
    print("Starting Celery worker...")
    # The worker will be started using the CLI command
    # This file exists to ensure proper imports and env setup
