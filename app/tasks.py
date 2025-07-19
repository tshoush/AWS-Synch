"""Celery background tasks for DDI Sync Manager"""
from celery import Task
from app import celery
from app.services.infoblox_wapi import InfobloxWAPI
from app.services.aws_import import AWSImporter
from app.services.attribute_mapper import AttributeMapper
from app.services.ddi_service import DDIService
import json
import redis
import time

# Redis client for task status updates
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

class CallbackTask(Task):
    """Task with progress callback support"""
    def on_success(self, retval, task_id, args, kwargs):
        """Success callback"""
        pass
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Failure callback"""
        pass

def update_task_progress(task_id, current, total, status):
    """Update task progress in Redis"""
    progress_data = {
        'current': current,
        'total': total,
        'status': status,
        'timestamp': time.time()
    }
    redis_client.setex(f"task_progress:{task_id}", 3600, json.dumps(progress_data))

@celery.task(bind=True, base=CallbackTask)
def sync_infoblox_task(self, data):
    """Background task for InfoBlox synchronization"""
    try:
        ddi_service = DDIService()
        result = ddi_service.sync_infoblox(data)
        return {'status': 'success', 'data': result}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@celery.task(bind=True, base=CallbackTask)
def compare_data_task(self, data):
    """Background task for data comparison"""
    try:
        ddi_service = DDIService()
        comparison = ddi_service.compare_sources(data)
        return {'status': 'success', 'data': comparison}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@celery.task(bind=True, base=CallbackTask)
def sync_data_task(self, data):
    """Background task for data synchronization"""
    try:
        ddi_service = DDIService()
        result = ddi_service.sync_data(data)
        return {'status': 'success', 'data': result}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@celery.task(bind=True, base=CallbackTask)
def import_networks_task(self, data):
    """Background task for importing networks to InfoBlox"""
    try:
        networks = data.get('networks', [])
        network_view = data.get('network_view', 'default')
        attribute_mappings = data.get('attribute_mappings', {})
        
        # Get InfoBlox config from Redis
        config_str = redis_client.get('infoblox_config')
        if not config_str:
            raise Exception('InfoBlox not configured')
        
        config = json.loads(config_str)
        client = InfobloxWAPI(config['host'], config['username'], config['password'])
        
        # Apply attribute mappings
        mapper = AttributeMapper()
        networks = mapper.apply_mappings(networks, attribute_mappings)
        
        results = {
            'created': 0,
            'updated': 0,
            'failed': 0,
            'errors': []
        }
        
        total = len(networks)
        
        for i, network in enumerate(networks):
            try:
                # Update progress
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': i + 1,
                        'total': total,
                        'status': f'Processing network {network["subnet"]}'
                    }
                )
                
                subnet = network['subnet']
                extattrs = network.get('mapped_extattrs', {})
                comment = f"AWS Account: {network['account']}, Region: {network['region']}"
                
                # Check if network exists
                existing = client.get_network_by_subnet(subnet, network_view)
                
                if existing:
                    # Update existing network
                    success = client.update_network(existing['_ref'], extattrs=extattrs)
                    if success:
                        results['updated'] += 1
                    else:
                        results['failed'] += 1
                        results['errors'].append(f"Failed to update {subnet}")
                else:
                    # Create new network
                    success = client.create_network(subnet, network_view, comment, extattrs)
                    if success:
                        results['created'] += 1
                    else:
                        results['failed'] += 1
                        results['errors'].append(f"Failed to create {subnet}")
                
                # Rate limiting to avoid overwhelming InfoBlox
                time.sleep(0.1)
                
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"Error processing {network.get('subnet', 'unknown')}: {str(e)}")
        
        return results
        
    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={'error': str(e)}
        )
        raise

@celery.task(bind=True)
def process_large_file_task(self, filepath, file_type):
    """Background task for processing large files"""
    try:
        import pandas as pd
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': 'Reading file...'}
        )
        
        if file_type == 'csv':
            # Process CSV in chunks
            chunk_size = 10000
            chunks = []
            
            for i, chunk in enumerate(pd.read_csv(filepath, chunksize=chunk_size)):
                chunks.append(chunk)
                progress = min(50 + (i * 10), 90)
                self.update_state(
                    state='PROGRESS',
                    meta={'current': progress, 'total': 100, 'status': f'Processing chunk {i+1}...'}
                )
            
            df = pd.concat(chunks, ignore_index=True)
        else:
            df = pd.read_excel(filepath)
        
        self.update_state(
            state='PROGRESS',
            meta={'current': 95, 'total': 100, 'status': 'Finalizing...'}
        )
        
        data = df.to_dict(orient='records')
        
        return {'status': 'success', 'data': data, 'rows': len(data)}
        
    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={'error': str(e)}
        )
        raise

# Periodic tasks
@celery.task
def cleanup_old_files():
    """Periodic task to clean up old upload files"""
    import os
    from datetime import datetime, timedelta
    
    upload_dir = 'uploads'
    if not os.path.exists(upload_dir):
        return
    
    # Remove files older than 24 hours
    cutoff_time = datetime.now() - timedelta(hours=24)
    
    for filename in os.listdir(upload_dir):
        filepath = os.path.join(upload_dir, filename)
        if os.path.isfile(filepath):
            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            if file_time < cutoff_time:
                os.remove(filepath)

@celery.task
def sync_infoblox_cache():
    """Periodic task to refresh InfoBlox cache"""
    try:
        # Get InfoBlox config
        config_str = redis_client.get('infoblox_config')
        if not config_str:
            return
        
        config = json.loads(config_str)
        client = InfobloxWAPI(config['host'], config['username'], config['password'])
        
        # Refresh network views
        views = client.get_network_views()
        redis_client.setex('cache:network_views', 600, json.dumps(views))
        
        # Refresh extensible attributes
        attrs = client.get_extensible_attributes()
        redis_client.setex('cache:extensible_attributes', 600, json.dumps(attrs))
        
    except Exception as e:
        print(f"Cache sync error: {e}")

# Configure periodic tasks
from celery.schedules import crontab

celery.conf.beat_schedule = {
    'cleanup-old-files': {
        'task': 'app.tasks.cleanup_old_files',
        'schedule': crontab(hour=2, minute=0),  # Run at 2 AM daily
    },
    'sync-infoblox-cache': {
        'task': 'app.tasks.sync_infoblox_cache',
        'schedule': crontab(minute='*/15'),  # Run every 15 minutes
    },
}