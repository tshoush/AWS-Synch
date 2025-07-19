from quart import Blueprint, jsonify, request, render_template, current_app
import pandas as pd
import json
from werkzeug.utils import secure_filename
import os
import asyncio
import aiofiles
from concurrent.futures import ThreadPoolExecutor
from app.services.cloud_providers import AWSProvider, AzureProvider, GCPProvider, AlibabaProvider
from app.services.ddi_service import DDIService
from app.services.infoblox_wapi import InfobloxWAPI
from app.services.aws_import import AWSImporter
from app.services.attribute_mapper import AttributeMapper
from app import celery
import hashlib
import time

main_bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

# Thread pool for CPU-bound operations
executor = ThreadPoolExecutor(max_workers=4)

# Global InfoBlox client (will be initialized when configured)
infoblox_client = None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

async def get_infoblox_client():
    """Get or create InfoBlox client"""
    global infoblox_client
    if not infoblox_client:
        # Try to get from Redis cache first
        redis_client = current_app.redis_client
        config_str = await redis_client.get('infoblox_config')
        
        if config_str:
            config = json.loads(config_str)
            infoblox_client = InfobloxWAPI(
                config['host'],
                config['username'],
                config['password']
            )
    return infoblox_client

async def cache_key(prefix, *args):
    """Generate cache key"""
    key_data = f"{prefix}:{':'.join(str(arg) for arg in args)}"
    return hashlib.md5(key_data.encode()).hexdigest()

@main_bp.route('/')
async def index():
    return await render_template('index.html')

@main_bp.route('/api/infoblox/sync', methods=['POST'])
async def sync_infoblox():
    try:
        data = await request.json
        # Queue task for background processing
        task = celery.send_task('sync_infoblox_task', args=[data])
        
        return jsonify({
            'status': 'success', 
            'message': 'Sync task queued',
            'task_id': task.id
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/cloud/<provider>/data', methods=['GET'])
async def get_cloud_data(provider):
    try:
        providers = {
            'aws': AWSProvider,
            'azure': AzureProvider,
            'gcp': GCPProvider,
            'alibaba': AlibabaProvider
        }
        
        if provider not in providers:
            return jsonify({'status': 'error', 'message': 'Invalid provider'}), 400
        
        # Check cache first
        redis_client = current_app.redis_client
        cache_key_str = await cache_key('cloud_data', provider)
        cached_data = await redis_client.get(cache_key_str)
        
        if cached_data:
            return jsonify({'status': 'success', 'data': json.loads(cached_data), 'cached': True})
        
        # Get data in background thread (cloud SDKs are not async)
        loop = asyncio.get_event_loop()
        cloud_provider = providers[provider]()
        data = await loop.run_in_executor(executor, cloud_provider.get_ddi_data)
        
        # Cache for 5 minutes
        await redis_client.setex(cache_key_str, 300, json.dumps(data))
        
        return jsonify({'status': 'success', 'data': data})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/upload', methods=['POST'])
async def upload_file():
    try:
        files = await request.files
        if 'file' not in files:
            return jsonify({'status': 'error', 'message': 'No file part'}), 400
        
        file = files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No selected file'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join('uploads', filename)
            
            # Save file asynchronously
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(await file.read())
            
            # Process file in thread pool
            loop = asyncio.get_event_loop()
            if filename.endswith('.csv'):
                df = await loop.run_in_executor(executor, pd.read_csv, filepath)
            else:
                df = await loop.run_in_executor(executor, pd.read_excel, filepath)
            
            data = df.to_dict(orient='records')
            return jsonify({'status': 'success', 'data': data})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/compare', methods=['POST'])
async def compare_data():
    try:
        data = await request.json
        # Queue comparison task
        task = celery.send_task('compare_data_task', args=[data])
        
        return jsonify({
            'status': 'success',
            'message': 'Comparison task queued',
            'task_id': task.id
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/sync', methods=['POST'])
async def sync_data():
    try:
        data = await request.json
        # Queue sync task
        task = celery.send_task('sync_data_task', args=[data])
        
        return jsonify({
            'status': 'success',
            'message': 'Sync task queued',
            'task_id': task.id
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/infoblox/configure', methods=['POST'])
async def configure_infoblox():
    """Configure InfoBlox connection"""
    try:
        data = await request.json
        host = data.get('host')
        username = data.get('username')
        password = data.get('password')
        
        # Test connection asynchronously
        loop = asyncio.get_event_loop()
        test_client = InfobloxWAPI(host, username, password)
        connection_valid = await loop.run_in_executor(
            executor, 
            test_client.test_connection
        )
        
        if connection_valid:
            # Save to Redis
            config = {
                'host': host,
                'username': username,
                'password': password
            }
            redis_client = current_app.redis_client
            await redis_client.set('infoblox_config', json.dumps(config))
            
            global infoblox_client
            infoblox_client = test_client
            
            return jsonify({'status': 'success', 'message': 'InfoBlox configured successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to connect to InfoBlox'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/infoblox/network-views', methods=['GET'])
async def get_network_views():
    """Get InfoBlox network views"""
    try:
        client = await get_infoblox_client()
        if not client:
            return jsonify({'status': 'error', 'message': 'InfoBlox not configured'}), 400
        
        # Check cache
        redis_client = current_app.redis_client
        cache_key_str = await cache_key('network_views')
        cached_data = await redis_client.get(cache_key_str)
        
        if cached_data:
            return jsonify({'status': 'success', 'data': json.loads(cached_data)})
        
        # Get data in thread pool
        loop = asyncio.get_event_loop()
        views = await loop.run_in_executor(executor, client.get_network_views)
        
        # Cache for 10 minutes
        await redis_client.setex(cache_key_str, 600, json.dumps(views))
        
        return jsonify({'status': 'success', 'data': views})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/infoblox/extensible-attributes', methods=['GET'])
async def get_extensible_attributes():
    """Get InfoBlox extensible attributes"""
    try:
        client = await get_infoblox_client()
        if not client:
            return jsonify({'status': 'error', 'message': 'InfoBlox not configured'}), 400
        
        # Check cache
        redis_client = current_app.redis_client
        cache_key_str = await cache_key('extensible_attributes')
        cached_data = await redis_client.get(cache_key_str)
        
        if cached_data:
            return jsonify({'status': 'success', 'data': json.loads(cached_data)})
        
        # Get data in thread pool
        loop = asyncio.get_event_loop()
        attrs = await loop.run_in_executor(executor, client.get_extensible_attributes)
        
        # Cache for 10 minutes
        await redis_client.setex(cache_key_str, 600, json.dumps(attrs))
        
        return jsonify({'status': 'success', 'data': attrs})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/infoblox/networks', methods=['GET'])
async def get_infoblox_networks():
    """Get InfoBlox networks"""
    try:
        client = await get_infoblox_client()
        if not client:
            return jsonify({'status': 'error', 'message': 'InfoBlox not configured'}), 400
        
        network_view = request.args.get('network_view', 'default')
        
        # Check cache
        redis_client = current_app.redis_client
        cache_key_str = await cache_key('networks', network_view)
        cached_data = await redis_client.get(cache_key_str)
        
        if cached_data:
            return jsonify({'status': 'success', 'data': json.loads(cached_data)})
        
        # Get data in thread pool
        loop = asyncio.get_event_loop()
        networks = await loop.run_in_executor(
            executor, 
            client.get_networks, 
            network_view
        )
        
        # Cache for 5 minutes
        await redis_client.setex(cache_key_str, 300, json.dumps(networks))
        
        return jsonify({'status': 'success', 'data': networks})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/aws/upload', methods=['POST'])
async def upload_aws_file():
    """Upload and parse AWS network export file"""
    try:
        files = await request.files
        if 'file' not in files:
            return jsonify({'status': 'error', 'message': 'No file part'}), 400
        
        file = files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No selected file'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            
            # Save file asynchronously
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(await file.read())
            
            # Process in thread pool
            loop = asyncio.get_event_loop()
            importer = AWSImporter()
            
            # Parse file
            df = await loop.run_in_executor(executor, importer.parse_file, filepath)
            
            # Validate file
            is_valid, errors = await loop.run_in_executor(
                executor, 
                importer.validate_file, 
                df
            )
            
            if not is_valid:
                return jsonify({'status': 'error', 'message': 'Invalid file format', 'errors': errors}), 400
            
            # Process data
            networks = await loop.run_in_executor(
                executor, 
                importer.process_aws_data, 
                df
            )
            
            # Get unique tags for mapping
            all_tags = set()
            for net in networks:
                all_tags.update(net['tags'].keys())
            
            return jsonify({
                'status': 'success',
                'data': {
                    'networks': networks,
                    'total_count': len(networks),
                    'unique_tags': list(all_tags)
                }
            })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/aws/dry-run', methods=['POST'])
async def aws_dry_run():
    """Perform dry run comparison between AWS and InfoBlox"""
    try:
        data = await request.json
        aws_networks = data.get('networks', [])
        network_view = data.get('network_view', 'default')
        
        client = await get_infoblox_client()
        if not client:
            return jsonify({'status': 'error', 'message': 'InfoBlox not configured'}), 400
        
        # Get InfoBlox networks in thread pool
        loop = asyncio.get_event_loop()
        ib_networks = await loop.run_in_executor(
            executor, 
            client.get_networks, 
            network_view
        )
        
        # Compare in thread pool
        importer = AWSImporter()
        comparison = await loop.run_in_executor(
            executor,
            importer.compare_with_infoblox,
            aws_networks,
            ib_networks
        )
        
        return jsonify({'status': 'success', 'data': comparison})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/aws/attribute-mappings', methods=['POST'])
async def get_attribute_mappings():
    """Get attribute mapping suggestions"""
    try:
        data = await request.json
        aws_tags = data.get('tags', [])
        
        client = await get_infoblox_client()
        if not client:
            return jsonify({'status': 'error', 'message': 'InfoBlox not configured'}), 400
        
        # Get InfoBlox extensible attributes
        loop = asyncio.get_event_loop()
        ib_attrs = await loop.run_in_executor(
            executor, 
            client.get_extensible_attributes
        )
        ib_attr_names = [attr['name'] for attr in ib_attrs]
        
        # Get mapping suggestions in thread pool
        mapper = AttributeMapper()
        mappings = await loop.run_in_executor(
            executor,
            mapper.create_mapping_suggestions,
            aws_tags,
            ib_attr_names
        )
        
        return jsonify({'status': 'success', 'data': mappings})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/infoblox/create-attribute', methods=['POST'])
async def create_extensible_attribute():
    """Create new extensible attribute in InfoBlox"""
    try:
        data = await request.json
        name = data.get('name')
        attr_type = data.get('type', 'STRING')
        comment = data.get('comment', '')
        
        client = await get_infoblox_client()
        if not client:
            return jsonify({'status': 'error', 'message': 'InfoBlox not configured'}), 400
        
        # Create attribute in thread pool
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            executor,
            client.create_extensible_attribute,
            name,
            attr_type,
            comment
        )
        
        if success:
            # Clear cache
            redis_client = current_app.redis_client
            cache_key_str = await cache_key('extensible_attributes')
            await redis_client.delete(cache_key_str)
            
            return jsonify({'status': 'success', 'message': f'Attribute {name} created successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to create attribute'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/aws/import', methods=['POST'])
async def import_aws_networks():
    """Import AWS networks to InfoBlox"""
    try:
        data = await request.json
        
        # Queue import task for background processing
        task = celery.send_task('import_networks_task', args=[data])
        
        return jsonify({
            'status': 'success',
            'message': 'Import task queued',
            'task_id': task.id
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/task/<task_id>', methods=['GET'])
async def get_task_status(task_id):
    """Get status of a background task"""
    try:
        task = celery.AsyncResult(task_id)
        
        if task.state == 'PENDING':
            response = {
                'state': task.state,
                'status': 'Task is waiting to be processed...'
            }
        elif task.state == 'SUCCESS':
            response = {
                'state': task.state,
                'result': task.result
            }
        elif task.state == 'FAILURE':
            response = {
                'state': task.state,
                'error': str(task.info)
            }
        else:
            response = {
                'state': task.state,
                'current': task.info.get('current', 0),
                'total': task.info.get('total', 1),
                'status': task.info.get('status', '')
            }
        
        return jsonify(response)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500