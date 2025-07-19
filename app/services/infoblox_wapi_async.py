"""Async InfoBlox WAPI Client using aiohttp"""
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
import json
from urllib.parse import urljoin
import ssl
from asyncio_throttle import Throttler

class InfobloxWAPIAsync:
    """Async InfoBlox Web API Client with connection pooling and rate limiting"""
    
    def __init__(self, host: str, username: str, password: str, version: str = "2.13.1"):
        self.host = host.rstrip('/')
        self.username = username
        self.password = password
        self.version = version
        self.base_url = f"{self.host}/wapi/v{version}/"
        
        # Connection pool configuration
        self.connector = None
        self.session = None
        
        # Rate limiting (10 requests per second)
        self.throttler = Throttler(rate_limit=10, period=1)
        
        # SSL context (keeping verify=False for now as per requirements)
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def connect(self):
        """Initialize connection pool"""
        if not self.connector:
            self.connector = aiohttp.TCPConnector(
                limit=100,  # Total connection pool size
                limit_per_host=30,  # Per-host connection limit
                ttl_dns_cache=300,  # DNS cache timeout
                enable_cleanup_closed=True
            )
        
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                connector=self.connector,
                auth=aiohttp.BasicAuth(self.username, self.password),
                timeout=timeout,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )
    
    async def close(self):
        """Close connection pool"""
        if self.session:
            await self.session.close()
        if self.connector:
            await self.connector.close()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make async HTTP request with rate limiting and retries"""
        if not self.session:
            await self.connect()
        
        url = urljoin(self.base_url, endpoint)
        
        # Apply rate limiting
        async with self.throttler:
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    async with self.session.request(
                        method, 
                        url, 
                        ssl=self.ssl_context,
                        **kwargs
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 201:
                            return {'_ref': response.headers.get('Location', '')}
                        elif response.status == 401:
                            raise Exception("Authentication failed")
                        else:
                            error_text = await response.text()
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay * (attempt + 1))
                                continue
                            raise Exception(f"Request failed: {response.status} - {error_text}")
                            
                except aiohttp.ClientError as e:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                    raise Exception(f"Connection error: {str(e)}")
    
    async def test_connection(self) -> bool:
        """Test connection to InfoBlox"""
        try:
            await self._make_request('GET', 'grid')
            return True
        except:
            return False
    
    async def get_network_views(self) -> List[Dict]:
        """Get all network views"""
        try:
            response = await self._make_request(
                'GET', 
                'networkview',
                params={'_return_fields': 'name,comment'}
            )
            return response if isinstance(response, list) else []
        except Exception as e:
            print(f"Error getting network views: {e}")
            return []
    
    async def get_networks(self, network_view: str = "default") -> List[Dict]:
        """Get all networks in a network view"""
        try:
            response = await self._make_request(
                'GET',
                'network',
                params={
                    'network_view': network_view,
                    '_return_fields': 'network,comment,extattrs',
                    '_max_results': 10000
                }
            )
            return response if isinstance(response, list) else []
        except Exception as e:
            print(f"Error getting networks: {e}")
            return []
    
    async def get_networks_batch(self, network_view: str = "default", batch_size: int = 1000) -> List[Dict]:
        """Get networks in batches for large datasets"""
        all_networks = []
        paging_id = None
        
        while True:
            params = {
                'network_view': network_view,
                '_return_fields': 'network,comment,extattrs',
                '_max_results': batch_size
            }
            
            if paging_id:
                params['_page_id'] = paging_id
            
            try:
                response = await self._make_request('GET', 'network', params=params)
                
                if isinstance(response, dict) and 'next_page_id' in response:
                    all_networks.extend(response.get('result', []))
                    paging_id = response.get('next_page_id')
                    if not paging_id:
                        break
                else:
                    all_networks.extend(response if isinstance(response, list) else [])
                    break
                    
            except Exception as e:
                print(f"Error in batch retrieval: {e}")
                break
        
        return all_networks
    
    async def get_network_by_subnet(self, subnet: str, network_view: str = "default") -> Optional[Dict]:
        """Get network by subnet"""
        try:
            response = await self._make_request(
                'GET',
                'network',
                params={
                    'network': subnet,
                    'network_view': network_view,
                    '_return_fields': 'network,comment,extattrs'
                }
            )
            return response[0] if response else None
        except:
            return None
    
    async def create_network(self, subnet: str, network_view: str = "default", 
                           comment: str = "", extattrs: Dict = None) -> bool:
        """Create a new network"""
        try:
            data = {
                'network': subnet,
                'network_view': network_view,
                'comment': comment
            }
            if extattrs:
                data['extattrs'] = extattrs
            
            response = await self._make_request('POST', 'network', json=data)
            return '_ref' in response
        except Exception as e:
            print(f"Error creating network {subnet}: {e}")
            return False
    
    async def update_network(self, ref: str, comment: str = None, extattrs: Dict = None) -> bool:
        """Update network attributes"""
        try:
            data = {}
            if comment is not None:
                data['comment'] = comment
            if extattrs is not None:
                data['extattrs'] = extattrs
            
            ref = ref.split('/')[-1] if '/' in ref else ref
            await self._make_request('PUT', f'network/{ref}', json=data)
            return True
        except Exception as e:
            print(f"Error updating network: {e}")
            return False
    
    async def create_networks_batch(self, networks: List[Dict], network_view: str = "default") -> Dict:
        """Create multiple networks in parallel"""
        results = {
            'created': 0,
            'failed': 0,
            'errors': []
        }
        
        # Create tasks for parallel execution
        tasks = []
        for network in networks:
            task = self.create_network(
                network['subnet'],
                network_view,
                network.get('comment', ''),
                network.get('extattrs', {})
            )
            tasks.append(task)
        
        # Execute in batches to avoid overwhelming the server
        batch_size = 10
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    results['failed'] += 1
                    results['errors'].append(str(result))
                elif result:
                    results['created'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"Failed to create network {networks[i+j]['subnet']}")
            
            # Small delay between batches
            if i + batch_size < len(tasks):
                await asyncio.sleep(0.5)
        
        return results
    
    async def get_extensible_attributes(self) -> List[Dict]:
        """Get all extensible attribute definitions"""
        try:
            response = await self._make_request(
                'GET',
                'extensibleattributedef',
                params={'_return_fields': 'name,type,comment'}
            )
            return response if isinstance(response, list) else []
        except Exception as e:
            print(f"Error getting extensible attributes: {e}")
            return []
    
    async def create_extensible_attribute(self, name: str, attr_type: str = "STRING", 
                                        comment: str = "") -> bool:
        """Create new extensible attribute definition"""
        try:
            data = {
                'name': name,
                'type': attr_type,
                'comment': comment
            }
            response = await self._make_request('POST', 'extensibleattributedef', json=data)
            return '_ref' in response
        except Exception as e:
            print(f"Error creating extensible attribute {name}: {e}")
            return False
    
    async def search_networks_by_attribute(self, attr_name: str, attr_value: str, 
                                         network_view: str = "default") -> List[Dict]:
        """Search networks by extensible attribute value"""
        try:
            search_filter = {f"*{attr_name}": attr_value}
            response = await self._make_request(
                'GET',
                'network',
                params={
                    'network_view': network_view,
                    '_return_fields': 'network,comment,extattrs',
                    **{f"*{attr_name}": attr_value}
                }
            )
            return response if isinstance(response, list) else []
        except Exception as e:
            print(f"Error searching networks: {e}")
            return []