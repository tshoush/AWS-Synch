# API Documentation

## Overview

The DDI Sync Manager provides a RESTful API for managing network synchronization between cloud providers and InfoBlox. All endpoints return JSON responses and support async operations.

## Base URL

```
http://localhost:8000/api
```

## Authentication

Currently, the API does not require authentication (alpha release). Authentication will be added in future versions.

## Common Response Format

All API responses follow this structure:

```json
{
  "status": "success|error",
  "data": {},
  "message": "Optional message",
  "errors": []
}
```

## Endpoints

### InfoBlox Configuration

#### Configure InfoBlox Connection
```http
POST /api/infoblox/configure
Content-Type: application/json

{
  "host": "https://infoblox.example.com",
  "username": "admin",
  "password": "password"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "InfoBlox configured successfully"
}
```

### Network Views

#### Get Network Views
```http
GET /api/infoblox/network-views
```

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "name": "default",
      "comment": "Default network view"
    }
  ]
}
```

### Extensible Attributes

#### Get Extensible Attributes
```http
GET /api/infoblox/extensible-attributes
```

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "name": "Environment",
      "type": "STRING",
      "comment": "Environment designation"
    }
  ]
}
```

#### Create Extensible Attribute
```http
POST /api/infoblox/create-attribute
Content-Type: application/json

{
  "name": "CostCenter",
  "type": "STRING",
  "comment": "Cost center for billing"
}
```

**Valid Types:** STRING, INTEGER, EMAIL, URL, DATE, ENUM

### AWS Import

#### Upload AWS File
```http
POST /api/aws/upload
Content-Type: multipart/form-data

file: <csv or xlsx file>
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "networks": [...],
    "total_count": 150,
    "unique_tags": ["Environment", "Owner", "Project"]
  }
}
```

#### Get Attribute Mappings
```http
POST /api/aws/attribute-mappings
Content-Type: application/json

{
  "tags": ["Environment", "Owner", "Project"]
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "Environment": {
      "suggestions": [
        {
          "infoblox_attribute": "Environment",
          "confidence": 100,
          "reason": "Exact match"
        }
      ]
    }
  }
}
```

#### Dry Run
```http
POST /api/aws/dry-run
Content-Type: application/json

{
  "networks": [...],
  "network_view": "default"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "new": [...],
    "existing": [...],
    "conflicts": [...]
  }
}
```

#### Import Networks (Async)
```http
POST /api/aws/import
Content-Type: application/json

{
  "networks": [...],
  "network_view": "default",
  "attribute_mappings": {
    "Environment": "Environment",
    "Owner": "Owner"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Import task queued",
  "task_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Task Management

#### Get Task Status
```http
GET /api/task/{task_id}
```

**Response (In Progress):**
```json
{
  "state": "PROGRESS",
  "current": 50,
  "total": 100,
  "status": "Processing network 10.0.1.0/24"
}
```

**Response (Success):**
```json
{
  "state": "SUCCESS",
  "result": {
    "created": 45,
    "updated": 5,
    "failed": 0,
    "errors": []
  }
}
```

### Cloud Provider Data

#### Get Cloud Provider Data
```http
GET /api/cloud/{provider}/data
```

**Providers:** aws, azure, gcp, alibaba

**Response:**
```json
{
  "status": "success",
  "data": {
    "networks": [...],
    "subnets": [...],
    "vpcs": [...]
  },
  "cached": true
}
```

## WebSocket-like Progress Tracking

For long-running operations, poll the task status endpoint:

```javascript
async function monitorTask(taskId) {
  const pollInterval = 1000; // 1 second
  
  while (true) {
    const response = await fetch(`/api/task/${taskId}`);
    const data = await response.json();
    
    if (data.state === 'SUCCESS') {
      console.log('Task completed:', data.result);
      break;
    } else if (data.state === 'FAILURE') {
      console.error('Task failed:', data.error);
      break;
    } else if (data.state === 'PROGRESS') {
      console.log(`Progress: ${data.current}/${data.total}`);
    }
    
    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }
}
```

## Rate Limiting

API endpoints are rate-limited:
- General API: 10 requests/second
- Upload endpoints: 1 request/second

Rate limit headers:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Time when limit resets

## Error Codes

| Code | Description |
|------|-------------|
| 400  | Bad Request - Invalid input |
| 404  | Not Found - Resource doesn't exist |
| 429  | Too Many Requests - Rate limit exceeded |
| 500  | Internal Server Error |
| 504  | Gateway Timeout - Operation took too long |

## Caching

Responses are cached with the following TTLs:
- Network Views: 10 minutes
- Extensible Attributes: 10 minutes
- Networks: 5 minutes
- Cloud Provider Data: 5 minutes

Force cache refresh by adding `?refresh=true` to GET requests.