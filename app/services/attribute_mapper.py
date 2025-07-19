from typing import Dict, List, Tuple
import difflib
import re

class AttributeMapper:
    """Map AWS tags to InfoBlox extended attributes with similarity detection"""
    
    def __init__(self):
        # Common variations we want to detect
        self.common_variations = [
            ['created_by', 'createdby', 'created-by', 'creator', 'created_user'],
            ['created_date', 'createddate', 'created-date', 'creation_date', 'created_at'],
            ['modified_by', 'modifiedby', 'modified-by', 'updated_by', 'updatedby'],
            ['modified_date', 'modifieddate', 'modified-date', 'updated_date', 'updated_at'],
            ['environment', 'env', 'Environment', 'ENV'],
            ['application', 'app', 'Application', 'APP'],
            ['owner', 'Owner', 'owned_by', 'ownedby'],
            ['cost_center', 'costcenter', 'cost-center', 'cc'],
            ['project', 'Project', 'project_name', 'projectname'],
            ['department', 'dept', 'Department', 'DEPT']
        ]
        
        # Build reverse mapping for quick lookup
        self.variation_map = {}
        for group in self.common_variations:
            canonical = group[0]  # First item is the canonical form
            for variant in group:
                self.variation_map[variant.lower()] = canonical
    
    def normalize_attribute_name(self, name: str) -> str:
        """Normalize attribute name for comparison"""
        # Convert to lowercase and replace common separators with underscore
        normalized = name.lower()
        normalized = re.sub(r'[-\s]+', '_', normalized)
        return normalized
    
    def find_similar_attributes(self, aws_tag: str, infoblox_attrs: List[str], 
                               threshold: float = 0.8) -> List[Tuple[str, float]]:
        """Find similar InfoBlox attributes for an AWS tag"""
        aws_normalized = self.normalize_attribute_name(aws_tag)
        matches = []
        
        # Check if it's a known variation
        if aws_normalized in self.variation_map:
            canonical = self.variation_map[aws_normalized]
            # Look for the canonical form in InfoBlox attributes
            for ib_attr in infoblox_attrs:
                if self.normalize_attribute_name(ib_attr) in self.variation_map:
                    if self.variation_map[self.normalize_attribute_name(ib_attr)] == canonical:
                        matches.append((ib_attr, 0.95))  # High confidence for known variations
        
        # Use string similarity for other cases
        for ib_attr in infoblox_attrs:
            ib_normalized = self.normalize_attribute_name(ib_attr)
            
            # Calculate similarity
            similarity = difflib.SequenceMatcher(None, aws_normalized, ib_normalized).ratio()
            
            # Check for substring matches
            if aws_normalized in ib_normalized or ib_normalized in aws_normalized:
                similarity = max(similarity, 0.85)
            
            # Check for common prefixes/suffixes
            if (aws_normalized.startswith(ib_normalized[:3]) or 
                ib_normalized.startswith(aws_normalized[:3])):
                similarity = max(similarity, 0.7)
            
            if similarity >= threshold:
                matches.append((ib_attr, similarity))
        
        # Sort by similarity score
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
    
    def create_mapping_suggestions(self, aws_tags: List[str], 
                                  infoblox_attrs: List[str]) -> Dict[str, List[Dict]]:
        """Create mapping suggestions for AWS tags to InfoBlox attributes"""
        mappings = {}
        
        for tag in aws_tags:
            suggestions = []
            similar = self.find_similar_attributes(tag, infoblox_attrs)
            
            for ib_attr, score in similar[:3]:  # Top 3 suggestions
                suggestions.append({
                    'infoblox_attribute': ib_attr,
                    'confidence': round(score * 100, 1),
                    'is_exact_match': score == 1.0
                })
            
            # Always include option to create new attribute
            mappings[tag] = {
                'suggestions': suggestions,
                'can_create_new': True
            }
        
        return mappings
    
    def validate_attribute_value(self, value: str, attr_type: str = "STRING") -> Tuple[bool, str]:
        """Validate attribute value based on InfoBlox attribute type"""
        if attr_type == "INTEGER":
            try:
                int(value)
                return True, ""
            except ValueError:
                return False, f"Value '{value}' is not a valid integer"
        
        elif attr_type == "ENUM":
            # For ENUM types, we'd need to check against allowed values
            # This would be configured per attribute
            return True, ""
        
        elif attr_type == "EMAIL":
            email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
            if re.match(email_pattern, value):
                return True, ""
            return False, f"Value '{value}' is not a valid email address"
        
        elif attr_type == "URL":
            url_pattern = r'^https?://[\w\.-]+'
            if re.match(url_pattern, value):
                return True, ""
            return False, f"Value '{value}' is not a valid URL"
        
        # Default STRING type - always valid
        return True, ""
    
    def apply_mappings(self, aws_networks: List[Dict], 
                      attribute_mappings: Dict[str, str]) -> List[Dict]:
        """Apply attribute mappings to AWS networks"""
        for network in aws_networks:
            mapped_extattrs = {}
            
            for aws_tag, tag_value in network.get('tags', {}).items():
                if aws_tag in attribute_mappings:
                    ib_attr = attribute_mappings[aws_tag]
                    if ib_attr:  # If mapped (not skipped)
                        # InfoBlox expects extattrs in {'value': actual_value} format
                        mapped_extattrs[ib_attr] = {'value': str(tag_value)}
            
            network['mapped_extattrs'] = mapped_extattrs
        
        return aws_networks