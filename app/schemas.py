"""Validation schemas for DDI Sync Manager"""
from marshmallow import Schema, fields, validate, validates, ValidationError
import ipaddress
import re

class NetworkSchema(Schema):
    """Schema for validating network data"""
    subnet = fields.Str(required=True, validate=validate.Regexp(
        r'^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$',
        error='Invalid subnet format. Expected: x.x.x.x/y'
    ))
    account = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    region = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    tags = fields.Dict(keys=fields.Str(), values=fields.Str())
    comment = fields.Str(missing='', validate=validate.Length(max=500))
    
    @validates('subnet')
    def validate_subnet(self, value):
        """Validate subnet is a valid IP network"""
        try:
            network = ipaddress.ip_network(value, strict=False)
            # Check for valid subnet ranges
            if network.prefixlen < 8 or network.prefixlen > 32:
                raise ValidationError('Subnet prefix must be between /8 and /32')
            # Check for reserved networks
            if network.is_reserved or network.is_multicast:
                raise ValidationError('Cannot use reserved or multicast networks')
        except ValueError as e:
            raise ValidationError(f'Invalid subnet: {str(e)}')

class AWSFileSchema(Schema):
    """Schema for validating AWS export file structure"""
    subnet = fields.Str(required=True)
    account = fields.Str(required=True)
    region = fields.Str(required=True)
    TAG = fields.Str(allow_none=True)  # TAG column might be empty

class InfobloxConfigSchema(Schema):
    """Schema for InfoBlox configuration"""
    host = fields.Url(required=True, require_tld=False)
    username = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    password = fields.Str(required=True, validate=validate.Length(min=1))

class AttributeMappingSchema(Schema):
    """Schema for attribute mapping configuration"""
    aws_tag = fields.Str(required=True)
    infoblox_attribute = fields.Str(required=True)
    transform = fields.Str(missing='none', validate=validate.OneOf([
        'none', 'uppercase', 'lowercase', 'capitalize'
    ]))

class ImportRequestSchema(Schema):
    """Schema for network import request"""
    networks = fields.List(fields.Nested(NetworkSchema), required=True)
    network_view = fields.Str(missing='default', validate=validate.Length(min=1, max=100))
    attribute_mappings = fields.Dict(
        keys=fields.Str(),
        values=fields.Str(),
        missing={}
    )
    
    @validates('networks')
    def validate_networks_limit(self, value):
        """Limit batch size for safety"""
        if len(value) > 10000:
            raise ValidationError('Cannot import more than 10000 networks at once')

class ExtensibleAttributeSchema(Schema):
    """Schema for creating extensible attributes"""
    name = fields.Str(required=True, validate=[
        validate.Length(min=1, max=64),
        validate.Regexp(r'^[a-zA-Z][a-zA-Z0-9_]*$', 
                       error='Name must start with letter and contain only letters, numbers, and underscores')
    ])
    type = fields.Str(missing='STRING', validate=validate.OneOf([
        'STRING', 'INTEGER', 'EMAIL', 'URL', 'DATE', 'ENUM'
    ]))
    comment = fields.Str(missing='', validate=validate.Length(max=500))
    min_value = fields.Int(missing=None)
    max_value = fields.Int(missing=None)
    
    @validates('name')
    def validate_reserved_names(self, value):
        """Check for reserved attribute names"""
        reserved = ['network', 'network_view', 'comment', '_ref']
        if value.lower() in reserved:
            raise ValidationError(f'{value} is a reserved attribute name')

class FileUploadSchema(Schema):
    """Schema for file upload validation"""
    filename = fields.Str(required=True)
    content_type = fields.Str(required=True)
    size = fields.Int(required=True)
    
    @validates('filename')
    def validate_filename(self, value):
        """Validate filename safety"""
        # Check for path traversal attempts
        if '..' in value or '/' in value or '\\' in value:
            raise ValidationError('Invalid filename')
        
        # Check extension
        allowed_extensions = {'.csv', '.xlsx', '.xls'}
        ext = value.lower().rsplit('.', 1)[-1] if '.' in value else ''
        if f'.{ext}' not in allowed_extensions:
            raise ValidationError(f'File type not allowed. Allowed types: {", ".join(allowed_extensions)}')
    
    @validates('size')
    def validate_size(self, value):
        """Validate file size"""
        max_size = 16 * 1024 * 1024  # 16MB
        if value > max_size:
            raise ValidationError(f'File too large. Maximum size: {max_size // (1024*1024)}MB')

class CloudProviderSchema(Schema):
    """Schema for cloud provider data"""
    provider = fields.Str(required=True, validate=validate.OneOf([
        'aws', 'azure', 'gcp', 'alibaba'
    ]))
    credentials = fields.Dict(required=False)
    regions = fields.List(fields.Str(), missing=[])

class SearchSchema(Schema):
    """Schema for search/filter operations"""
    query = fields.Str(missing='', validate=validate.Length(max=200))
    filters = fields.Dict(missing={})
    page = fields.Int(missing=1, validate=validate.Range(min=1))
    per_page = fields.Int(missing=100, validate=validate.Range(min=1, max=1000))
    sort_by = fields.Str(missing='subnet')
    sort_order = fields.Str(missing='asc', validate=validate.OneOf(['asc', 'desc']))

class TaskStatusSchema(Schema):
    """Schema for task status responses"""
    task_id = fields.Str(required=True)
    state = fields.Str(required=True)
    current = fields.Int(missing=0)
    total = fields.Int(missing=0)
    status = fields.Str(missing='')
    result = fields.Dict(missing={})
    error = fields.Str(missing='')

# Helper functions for validation
def validate_ip_address(ip_str):
    """Validate IP address"""
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False

def validate_cidr(cidr_str):
    """Validate CIDR notation"""
    try:
        ipaddress.ip_network(cidr_str, strict=False)
        return True
    except ValueError:
        return False

def sanitize_string(value, max_length=None):
    """Sanitize string input"""
    if not isinstance(value, str):
        return str(value)
    
    # Remove control characters
    value = re.sub(r'[\x00-\x1F\x7F]', '', value)
    
    # Trim whitespace
    value = value.strip()
    
    # Limit length
    if max_length:
        value = value[:max_length]
    
    return value

def validate_aws_tags(tags_dict):
    """Validate AWS tags format"""
    if not isinstance(tags_dict, dict):
        raise ValidationError('Tags must be a dictionary')
    
    for key, value in tags_dict.items():
        # AWS tag key constraints
        if not re.match(r'^[\w\s\-\.:/+=@]*$', key):
            raise ValidationError(f'Invalid tag key: {key}')
        if len(key) > 128:
            raise ValidationError(f'Tag key too long: {key}')
        
        # AWS tag value constraints
        if not isinstance(value, str):
            raise ValidationError(f'Tag value must be string: {key}={value}')
        if len(value) > 256:
            raise ValidationError(f'Tag value too long: {key}={value}')