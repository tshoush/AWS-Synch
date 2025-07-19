"""Middleware for error handling and request validation"""
from quart import jsonify, request
from marshmallow import ValidationError
import time
import logging
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

class ErrorHandlerMiddleware:
    """Global error handler middleware"""
    
    def __init__(self, app):
        self.app = app
        self.register_handlers()
    
    def register_handlers(self):
        """Register error handlers"""
        
        @self.app.errorhandler(ValidationError)
        async def handle_validation_error(error):
            """Handle marshmallow validation errors"""
            return jsonify({
                'status': 'error',
                'message': 'Validation error',
                'errors': error.messages
            }), 400
        
        @self.app.errorhandler(404)
        async def handle_not_found(error):
            """Handle 404 errors"""
            return jsonify({
                'status': 'error',
                'message': 'Resource not found'
            }), 404
        
        @self.app.errorhandler(500)
        async def handle_internal_error(error):
            """Handle internal server errors"""
            logger.error(f"Internal error: {error}")
            return jsonify({
                'status': 'error',
                'message': 'Internal server error'
            }), 500
        
        @self.app.errorhandler(Exception)
        async def handle_unexpected_error(error):
            """Handle unexpected errors"""
            logger.error(f"Unexpected error: {error}", exc_info=True)
            return jsonify({
                'status': 'error',
                'message': 'An unexpected error occurred'
            }), 500

def validate_request(schema_class):
    """Decorator for request validation"""
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            schema = schema_class()
            
            try:
                # Get request data
                if request.method in ['POST', 'PUT', 'PATCH']:
                    data = await request.get_json()
                else:
                    data = request.args.to_dict()
                
                # Validate data
                validated_data = schema.load(data)
                
                # Add validated data to kwargs
                kwargs['validated_data'] = validated_data
                
                return await f(*args, **kwargs)
            except ValidationError as e:
                return jsonify({
                    'status': 'error',
                    'message': 'Validation error',
                    'errors': e.messages
                }), 400
            except Exception as e:
                logger.error(f"Request validation error: {e}")
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid request'
                }), 400
        
        return decorated_function
    return decorator

def rate_limit(max_requests=100, window=60):
    """Rate limiting decorator"""
    def decorator(f):
        # Simple in-memory rate limiting (use Redis in production)
        request_counts = {}
        
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            # Get client identifier (IP address)
            client_id = request.remote_addr
            current_time = time.time()
            
            # Clean old entries
            request_counts[client_id] = [
                timestamp for timestamp in request_counts.get(client_id, [])
                if current_time - timestamp < window
            ]
            
            # Check rate limit
            if len(request_counts.get(client_id, [])) >= max_requests:
                return jsonify({
                    'status': 'error',
                    'message': 'Rate limit exceeded'
                }), 429
            
            # Record request
            request_counts.setdefault(client_id, []).append(current_time)
            
            return await f(*args, **kwargs)
        
        return decorated_function
    return decorator

def async_timeout(seconds=30):
    """Timeout decorator for async functions"""
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    f(*args, **kwargs),
                    timeout=seconds
                )
            except asyncio.TimeoutError:
                return jsonify({
                    'status': 'error',
                    'message': f'Request timeout after {seconds} seconds'
                }), 504
        
        return decorated_function
    return decorator

def require_infoblox_connection(f):
    """Decorator to require InfoBlox connection"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        from app.routes import get_infoblox_client
        
        client = await get_infoblox_client()
        if not client:
            return jsonify({
                'status': 'error',
                'message': 'InfoBlox not configured. Please configure connection first.'
            }), 400
        
        kwargs['infoblox_client'] = client
        return await f(*args, **kwargs)
    
    return decorated_function

class RequestLoggingMiddleware:
    """Request/Response logging middleware"""
    
    def __init__(self, app):
        self.app = app
        self.setup_logging()
    
    def setup_logging(self):
        """Setup request/response logging"""
        
        @self.app.before_request
        async def log_request():
            """Log incoming requests"""
            request.start_time = time.time()
            logger.info(f"Request: {request.method} {request.path}")
        
        @self.app.after_request
        async def log_response(response):
            """Log responses"""
            duration = time.time() - request.start_time
            logger.info(
                f"Response: {request.method} {request.path} - "
                f"Status: {response.status_code} - "
                f"Duration: {duration:.3f}s"
            )
            
            # Add performance headers
            response.headers['X-Response-Time'] = f"{duration:.3f}"
            return response

class SecurityMiddleware:
    """Security headers middleware"""
    
    def __init__(self, app):
        self.app = app
        self.setup_security()
    
    def setup_security(self):
        """Setup security headers"""
        
        @self.app.after_request
        async def add_security_headers(response):
            """Add security headers to response"""
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            response.headers['Content-Security-Policy'] = "default-src 'self'"
            return response