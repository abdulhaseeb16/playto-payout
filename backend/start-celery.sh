#!/bin/bash
# Start both celery worker and beat in the same container

# Start beat in background
celery -A config beat --loglevel=info &

# Start worker in foreground
celery -A config worker --loglevel=info --concurrency=4
