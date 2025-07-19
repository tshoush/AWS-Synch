import requests
import urllib3
from typing import Dict, List, Any, Optional
import json
from requests.auth import HTTPBasicAuth

# Disable SSL warnings for development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class InfobloxWAPI:
    """InfoBlox WAPI v2.13.1 Client"""
    
    def __init__(self, host: str, username: str, password: str, wapi_version: str = "v2.13.1"):
        self.host = host.rstrip('/')
        self.username = username
        self.password = password
        self.wapi_version = wapi_version
        self.base_url = f"{self.host}/wapi/{wapi_version}"
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(username, password)
        self.session.verify = False  # For development, in production use proper SSL
        
    def test_connection(self) -> bool:
        """Test connection to InfoBlox"""
        try:
            response = self.session.get(f"{self.base_url}/grid")
            return response.status_code == 200
        except Exception:
            return False
    
    def get_network_views(self) -> List[Dict[str, Any]]:
        """Get all network views"""
        try:
            response = self.session.get(
                f"{self.base_url}/networkview",
                params={'_return_fields': 'name,comment'}
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"Error getting network views: {e}")
            return []
    
    def get_networks(self, network_view: str = "default") -> List[Dict[str, Any]]:
        """Get all networks in a network view"""
        try:
            response = self.session.get(
                f"{self.base_url}/network",
                params={
                    'network_view': network_view,
                    '_return_fields': 'network,comment,extattrs',
                    '_max_results': 10000
                }
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"Error getting networks: {e}")
            return []
    
    def get_extensible_attributes(self) -> List[Dict[str, Any]]:
        """Get all extensible attribute definitions"""
        try:
            response = self.session.get(
                f"{self.base_url}/extensibleattributedef",
                params={'_return_fields': 'name,type,flags,comment,user_type'}
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"Error getting extensible attributes: {e}")
            return []
    
    def create_extensible_attribute(self, name: str, type: str = "STRING", comment: str = "") -> bool:
        """Create a new extensible attribute definition"""
        try:
            data = {
                "name": name,
                "type": type,
                "comment": comment
            }
            response = self.session.post(
                f"{self.base_url}/extensibleattributedef",
                json=data
            )
            return response.status_code == 201
        except Exception as e:
            print(f"Error creating extensible attribute: {e}")
            return False
    
    def get_network_by_subnet(self, subnet: str, network_view: str = "default") -> Optional[Dict[str, Any]]:
        """Get network by subnet CIDR"""
        try:
            response = self.session.get(
                f"{self.base_url}/network",
                params={
                    'network': subnet,
                    'network_view': network_view,
                    '_return_fields': 'network,comment,extattrs'
                }
            )
            if response.status_code == 200:
                results = response.json()
                return results[0] if results else None
            return None
        except Exception as e:
            print(f"Error getting network by subnet: {e}")
            return None
    
    def create_network(self, subnet: str, network_view: str = "default", 
                      comment: str = "", extattrs: Dict[str, Any] = None) -> bool:
        """Create a new network"""
        try:
            data = {
                "network": subnet,
                "network_view": network_view,
                "comment": comment
            }
            if extattrs:
                data["extattrs"] = extattrs
            
            response = self.session.post(
                f"{self.base_url}/network",
                json=data
            )
            return response.status_code == 201
        except Exception as e:
            print(f"Error creating network: {e}")
            return False
    
    def update_network(self, ref: str, extattrs: Dict[str, Any] = None, comment: str = None) -> bool:
        """Update an existing network"""
        try:
            data = {}
            if extattrs is not None:
                data["extattrs"] = extattrs
            if comment is not None:
                data["comment"] = comment
            
            response = self.session.put(
                f"{self.host}/wapi/{self.wapi_version}/{ref}",
                json=data
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Error updating network: {e}")
            return False
    
    def search_networks_by_extattr(self, attr_name: str, attr_value: str, 
                                  network_view: str = "default") -> List[Dict[str, Any]]:
        """Search networks by extensible attribute"""
        try:
            response = self.session.get(
                f"{self.base_url}/network",
                params={
                    f'*{attr_name}': attr_value,
                    'network_view': network_view,
                    '_return_fields': 'network,comment,extattrs'
                }
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"Error searching networks: {e}")
            return []