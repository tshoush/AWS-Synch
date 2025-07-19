import boto3
from azure.identity import DefaultAzureCredential
from azure.mgmt.network import NetworkManagementClient
from google.cloud import compute_v1
import requests
import os

class AWSProvider:
    def __init__(self):
        self.ec2_client = boto3.client('ec2')
        self.route53_client = boto3.client('route53')
    
    def get_ddi_data(self):
        try:
            vpcs = self.ec2_client.describe_vpcs()
            subnets = self.ec2_client.describe_subnets()
            hosted_zones = self.route53_client.list_hosted_zones()
            
            return {
                'vpcs': vpcs.get('Vpcs', []),
                'subnets': subnets.get('Subnets', []),
                'dns_zones': hosted_zones.get('HostedZones', [])
            }
        except Exception as e:
            return {'error': str(e)}

class AzureProvider:
    def __init__(self):
        self.credential = DefaultAzureCredential()
        self.subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')
        self.network_client = NetworkManagementClient(
            self.credential, 
            self.subscription_id
        ) if self.subscription_id else None
    
    def get_ddi_data(self):
        if not self.network_client:
            return {'error': 'Azure subscription ID not configured'}
        
        try:
            vnets = list(self.network_client.virtual_networks.list_all())
            subnets = []
            dns_zones = list(self.network_client.dns_zones.list_all()) if hasattr(self.network_client, 'dns_zones') else []
            
            for vnet in vnets:
                for subnet in vnet.subnets:
                    subnets.append({
                        'name': subnet.name,
                        'address_prefix': subnet.address_prefix,
                        'vnet': vnet.name
                    })
            
            return {
                'vnets': [{'name': v.name, 'address_space': v.address_space.address_prefixes} for v in vnets],
                'subnets': subnets,
                'dns_zones': dns_zones
            }
        except Exception as e:
            return {'error': str(e)}

class GCPProvider:
    def __init__(self):
        self.project_id = os.environ.get('GCP_PROJECT_ID')
        self.networks_client = compute_v1.NetworksClient() if self.project_id else None
        self.subnetworks_client = compute_v1.SubnetworksClient() if self.project_id else None
    
    def get_ddi_data(self):
        if not self.project_id:
            return {'error': 'GCP project ID not configured'}
        
        try:
            networks = list(self.networks_client.list(project=self.project_id))
            subnets = []
            
            for zone in compute_v1.ZonesClient().list(project=self.project_id):
                zone_subnets = list(self.subnetworks_client.list(
                    project=self.project_id,
                    region=zone.region.split('/')[-1]
                ))
                subnets.extend(zone_subnets)
            
            return {
                'networks': [{'name': n.name, 'cidr': n.I_pv4_range} for n in networks],
                'subnets': [{'name': s.name, 'cidr': s.ip_cidr_range} for s in subnets],
                'dns_zones': []
            }
        except Exception as e:
            return {'error': str(e)}

class AlibabaProvider:
    def __init__(self):
        self.access_key = os.environ.get('ALIBABA_ACCESS_KEY')
        self.secret_key = os.environ.get('ALIBABA_SECRET_KEY')
        self.region = os.environ.get('ALIBABA_REGION', 'cn-hangzhou')
    
    def get_ddi_data(self):
        if not self.access_key or not self.secret_key:
            return {'error': 'Alibaba Cloud credentials not configured'}
        
        return {
            'vpcs': [],
            'subnets': [],
            'dns_zones': [],
            'note': 'Alibaba Cloud integration requires additional SDK setup'
        }