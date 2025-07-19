import pandas as pd
from typing import Dict, List, Any, Tuple
import json
import re

class AWSImporter:
    """Handle AWS network export file import and parsing"""
    
    def __init__(self):
        self.required_columns = ['subnet', 'account', 'region']
        self.tag_column = 'TAG'  # or 'TAGS' depending on the file
        
    def parse_file(self, filepath: str) -> pd.DataFrame:
        """Parse AWS export file (CSV or Excel)"""
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        
        # Standardize column names (handle case variations)
        df.columns = [col.strip() for col in df.columns]
        
        # Find the tag column (could be TAG, TAGS, Tags, etc.)
        tag_columns = [col for col in df.columns if col.upper() in ['TAG', 'TAGS']]
        if tag_columns:
            self.tag_column = tag_columns[0]
        
        return df
    
    def validate_file(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """Validate that the file has required columns"""
        errors = []
        
        # Check for required columns (case-insensitive)
        df_columns_lower = [col.lower() for col in df.columns]
        for required in self.required_columns:
            if required.lower() not in df_columns_lower:
                errors.append(f"Missing required column: {required}")
        
        # Check if we have a tag column
        if self.tag_column not in df.columns:
            errors.append("Missing TAG column for extended attributes")
        
        return len(errors) == 0, errors
    
    def parse_tags(self, tag_string: str) -> Dict[str, str]:
        """Parse AWS tags from string format to dictionary"""
        if pd.isna(tag_string) or not tag_string:
            return {}
        
        tags = {}
        
        # Handle different tag formats
        # Format 1: "key1=value1,key2=value2"
        # Format 2: "key1:value1;key2:value2"
        # Format 3: JSON format
        
        tag_string = str(tag_string).strip()
        
        # Try JSON format first
        if tag_string.startswith('{'):
            try:
                return json.loads(tag_string)
            except:
                pass
        
        # Try comma-separated key=value pairs
        if '=' in tag_string:
            pairs = re.split('[,;]', tag_string)
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    tags[key.strip()] = value.strip()
        
        # Try colon-separated key:value pairs
        elif ':' in tag_string:
            pairs = re.split('[,;]', tag_string)
            for pair in pairs:
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    tags[key.strip()] = value.strip()
        
        return tags
    
    def process_aws_data(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Process AWS data into a format suitable for InfoBlox import"""
        networks = []
        
        for _, row in df.iterrows():
            # Get subnet (handle different column name cases)
            subnet_col = next((col for col in df.columns if col.lower() == 'subnet'), 'subnet')
            subnet = row.get(subnet_col, '')
            
            if not subnet or pd.isna(subnet):
                continue
            
            # Get other fields
            account_col = next((col for col in df.columns if col.lower() == 'account'), 'account')
            region_col = next((col for col in df.columns if col.lower() == 'region'), 'region')
            
            network_data = {
                'subnet': str(subnet).strip(),
                'account': str(row.get(account_col, '')).strip(),
                'region': str(row.get(region_col, '')).strip(),
                'tags': self.parse_tags(row.get(self.tag_column, '')),
                'raw_data': row.to_dict()
            }
            
            networks.append(network_data)
        
        return networks
    
    def compare_with_infoblox(self, aws_networks: List[Dict[str, Any]], 
                             infoblox_networks: List[Dict[str, Any]]) -> Dict[str, List]:
        """Compare AWS networks with InfoBlox networks"""
        comparison = {
            'new': [],          # Networks in AWS but not in InfoBlox
            'existing': [],     # Networks in both
            'conflicts': []     # Networks with conflicting attributes
        }
        
        # Create a map of InfoBlox networks by subnet
        ib_map = {net['network']: net for net in infoblox_networks}
        
        for aws_net in aws_networks:
            subnet = aws_net['subnet']
            
            if subnet in ib_map:
                # Network exists in InfoBlox
                ib_net = ib_map[subnet]
                aws_net['infoblox_ref'] = ib_net.get('_ref')
                aws_net['infoblox_extattrs'] = ib_net.get('extattrs', {})
                
                # Check for conflicts in extended attributes
                conflicts = self.find_attribute_conflicts(
                    aws_net['tags'], 
                    ib_net.get('extattrs', {})
                )
                
                if conflicts:
                    aws_net['conflicts'] = conflicts
                    comparison['conflicts'].append(aws_net)
                else:
                    comparison['existing'].append(aws_net)
            else:
                # New network
                comparison['new'].append(aws_net)
        
        return comparison
    
    def find_attribute_conflicts(self, aws_tags: Dict[str, str], 
                                ib_extattrs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find conflicts between AWS tags and InfoBlox extended attributes"""
        conflicts = []
        
        for tag_key, tag_value in aws_tags.items():
            if tag_key in ib_extattrs:
                ib_value = ib_extattrs[tag_key]
                # InfoBlox extattrs might have value in {'value': actual_value} format
                if isinstance(ib_value, dict) and 'value' in ib_value:
                    ib_value = ib_value['value']
                
                if str(tag_value) != str(ib_value):
                    conflicts.append({
                        'attribute': tag_key,
                        'aws_value': tag_value,
                        'infoblox_value': ib_value
                    })
        
        return conflicts