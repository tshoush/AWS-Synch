#!/bin/bash

# Production startup script for DDI Sync Manager

set -e

echo "Starting DDI Sync Manager in production mode..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found. Please copy .env.example to .env and configure it."
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Check Redis connection
echo "Checking Redis connection..."
redis-cli -u $REDIS_URL ping > /dev/null 2>&1 || {
    echo "Error: Cannot connect to Redis. Please ensure Redis is running."
    echo "You can start Redis with: docker-compose up -d redis"
    exit 1
}

# Create necessary directories
mkdir -p uploads logs

# Run database migrations (if any)
# python manage.py migrate

# Start Celery worker in background
echo "Starting Celery worker..."
celery -A app.tasks worker --loglevel=info --concurrency=4 --detach

# Start Celery beat in background
echo "Starting Celery beat..."
celery -A app.tasks beat --loglevel=info --detach

# Start the application with Hypercorn
echo "Starting application server..."
hypercorn app:app \
    --bind 0.0.0.0:8000 \
    --workers ${MAX_WORKERS:-4} \
    --worker-class uvloop \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    --log-level ${LOG_LEVEL:-info}