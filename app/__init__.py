from quart import Quart
from quart_cors import cors
import os
import redis.asyncio as redis
from celery import Celery

# Initialize Redis client
redis_client = None

# Initialize Celery
celery = Celery('ddi_sync', broker='redis://localhost:6379/0')

def create_app():
    app = Quart(__name__)
    
    # Enable CORS
    app = cors(app, allow_origin="*")
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['UPLOAD_FOLDER'] = 'uploads'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    app.config['REDIS_URL'] = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # Celery configuration
    celery.conf.update(
        result_backend=app.config['REDIS_URL'],
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_time_limit=30 * 60,  # 30 minutes
        task_soft_time_limit=25 * 60,  # 25 minutes
    )
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize Redis connection
    @app.before_serving
    async def startup():
        global redis_client
        redis_client = await redis.from_url(
            app.config['REDIS_URL'],
            encoding="utf-8",
            decode_responses=True
        )
        app.redis_client = redis_client
    
    @app.after_serving
    async def shutdown():
        if redis_client:
            await redis_client.close()
    
    from app.routes import main_bp
    app.register_blueprint(main_bp)
    
    return app