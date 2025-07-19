# Architecture Documentation

## System Overview

The DDI Sync Manager is built with an async-first architecture designed for high performance and scalability. The system uses a microservices-inspired design with clear separation of concerns.

## Architecture Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│   Web Browser   │────▶│  Nginx Proxy    │────▶│   Quart App     │
│   (Async JS)    │     │  (Rate Limit)   │     │   (ASGI)        │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                          │
                        ┌─────────────────────────────────┼─────────────────────────────────┐
                        │                                 │                                 │
                        ▼                                 ▼                                 ▼
                ┌───────────────┐                ┌───────────────┐                ┌───────────────┐
                │               │                │               │                │               │
                │  Redis Cache  │                │ Celery Worker │                │   InfoBlox    │
                │  (Session +   │                │  (Background  │                │   (WAPI)      │
                │   Data)       │                │   Tasks)      │                │               │
                │               │                │               │                └───────────────┘
                └───────────────┘                └───────────────┘
```

## Core Components

### 1. **Quart Application (Async Web Framework)**
- Handles all HTTP requests asynchronously
- Non-blocking I/O for maximum concurrency
- WebSocket-capable for future real-time features
- ASGI-compatible for production deployment

### 2. **Redis Cache Layer**
- Stores session data and API responses
- Implements distributed caching strategy
- Provides message broker for Celery
- Enables horizontal scaling

### 3. **Celery Task Queue**
- Processes long-running operations in background
- Prevents request timeouts
- Enables progress tracking
- Scheduled tasks for maintenance

### 4. **InfoBlox Async Client**
- Connection pooling for efficiency
- Rate limiting to prevent API overload
- Automatic retry with backoff
- Batch operations support

## Request Flow

### Synchronous Operations (< 1 second)
1. Client sends request to Nginx
2. Nginx applies rate limiting and forwards to Quart
3. Quart checks Redis cache
4. If cache miss, Quart queries InfoBlox asynchronously
5. Response cached in Redis
6. Response returned to client

### Asynchronous Operations (> 1 second)
1. Client sends request to Nginx
2. Quart validates request and creates Celery task
3. Task ID returned immediately to client
4. Client polls task status endpoint
5. Celery worker processes task in background
6. Progress updates stored in Redis
7. Final result retrieved by client

## Key Design Patterns

### 1. **Connection Pooling**
```python
# Reuse connections for efficiency
connector = aiohttp.TCPConnector(
    limit=100,
    limit_per_host=30,
    ttl_dns_cache=300
)
```

### 2. **Circuit Breaker**
- Prevents cascading failures
- Automatic retry with exponential backoff
- Fallback to cached data when available

### 3. **Repository Pattern**
- Services abstract data access
- Easy to swap implementations
- Testable business logic

### 4. **Async Context Managers**
```python
async with InfobloxWAPIAsync(...) as client:
    # Automatic connection management
    data = await client.get_networks()
```

## Performance Optimizations

### 1. **Parallel Processing**
- Multiple API calls executed concurrently
- Batch operations for bulk imports
- Thread pool for CPU-bound operations

### 2. **Caching Strategy**
- Multi-level caching (Redis + in-memory)
- Smart cache invalidation
- Configurable TTLs per data type

### 3. **Resource Pooling**
- HTTP connection reuse
- Database connection pooling
- Worker process pooling

### 4. **Lazy Loading**
- Data fetched only when needed
- Pagination for large datasets
- Streaming for file uploads

## Scalability Considerations

### Horizontal Scaling
- Stateless application design
- Session data in Redis
- Multiple worker processes
- Load balancer ready

### Vertical Scaling
- Configurable worker counts
- Adjustable connection pools
- Memory-efficient data structures
- Streaming for large files

## Security Architecture

### Input Validation
- Marshmallow schemas for all inputs
- Type checking and sanitization
- SQL injection prevention
- Path traversal protection

### Network Security
- Rate limiting per endpoint
- Security headers (HSTS, CSP)
- CORS configuration
- SSL/TLS termination at Nginx

### Error Handling
- No sensitive data in errors
- Graceful degradation
- Comprehensive logging
- Error boundaries

## Monitoring and Observability

### Metrics Collection
- Request/response times
- Task completion rates
- Cache hit ratios
- Error frequencies

### Logging Strategy
- Structured JSON logging
- Correlation IDs for tracing
- Different log levels per component
- Centralized log aggregation ready

### Health Checks
- `/health` endpoint for load balancers
- Redis connectivity check
- InfoBlox API availability
- Celery worker status

## Deployment Architecture

### Development
```bash
# Simple single-node setup
python run.py
```

### Production
```bash
# Multi-container deployment
docker-compose up -d
```

### High Availability
- Multiple app instances behind load balancer
- Redis sentinel for failover
- Celery worker autoscaling
- Database replication

## Technology Decisions

### Why Quart over Flask?
- Native async/await support
- Better performance for I/O-bound operations
- Compatible with Flask ecosystem
- WebSocket support

### Why Redis?
- Fast in-memory operations
- Pub/sub for real-time features
- Persistence options
- Wide language support

### Why Celery?
- Mature task queue system
- Flexible routing options
- Built-in retry mechanisms
- Excellent monitoring tools

### Why aiohttp?
- True async HTTP client
- Connection pooling built-in
- Streaming support
- Performance optimized