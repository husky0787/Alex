"""Generate private non-secret tfvars and current official prices via AWS CLI."""
from datetime import datetime, timedelta, timezone
import ipaddress
import json
from pathlib import Path
import sys
import urllib.request

root=Path.cwd()
sys.path.insert(0,str(root/'deploy/eks'))
from manage import aws, STATE

cluster=aws('rds','describe-db-clusters',DBClusterIdentifier='alex-aurora-cluster')['DBClusters'][0]
groups=aws('ec2','describe-security-groups',GroupIds=[cluster['VpcSecurityGroups'][0]['VpcSecurityGroupId']])['SecurityGroups']
vpc=groups[0]['VpcId']
vpc_cidr=aws('ec2','describe-vpcs',VpcIds=[vpc])['Vpcs'][0]['CidrBlock']
assert any(p['IpProtocol']=='tcp' and p.get('FromPort',0)<=5432<=p.get('ToPort',0)
           and any(r.get('CidrIp')==vpc_cidr for r in p.get('IpRanges',[])) for p in groups[0]['IpPermissions']), 'Existing Aurora VPC TCP5432 rule missing'
(STATE/'aurora-network-preflight.json').write_text(json.dumps(groups,indent=2))
subnets=aws('ec2','describe-subnets',Filters=[{'Name':'vpc-id','Values':[vpc]}])['Subnets']
eligible=[s for s in subnets if s['MapPublicIpOnLaunch'] and s['AvailabilityZoneId']!='use1-az3']
chosen=[]
for subnet in sorted(eligible,key=lambda s:s['AvailabilityZone']):
    if not any(s['AvailabilityZone']==subnet['AvailabilityZone'] for s in chosen):
        chosen.append(subnet)
    if len(chosen)==2: break
assert len(chosen)==2
cidrs=['172.31.160.0/24','172.31.161.0/24']
for cidr in cidrs:
    assert ipaddress.ip_network(cidr).subnet_of(ipaddress.ip_network(vpc_cidr)), 'Origin subnet is outside the existing VPC'
    assert not any(ipaddress.ip_network(cidr).overlaps(ipaddress.ip_network(s['CidrBlock'])) for s in subnets)
secrets=aws('secretsmanager','list-secrets',Filters=[{'Key':'name','Values':['alex-aurora-credentials']}])['SecretList']
assert len(secrets)==1
identity=aws('sts','get-caller-identity',profile='default')
assert ':user/' in identity['Arn'], 'The default operator profile must identify the documented IAM user'
with urllib.request.urlopen('https://checkip.amazonaws.com',timeout=15) as response:
    operator_ip=str(ipaddress.ip_address(response.read().decode().strip()))
values={'vpc_id':vpc,'public_subnet_ids':[s['SubnetId'] for s in chosen],
    'private_subnets':{str(i):{'az':s['AvailabilityZone'],'cidr':cidrs[i]} for i,s in enumerate(chosen)},
    'operator_cidrs':[operator_ip+'/32'],'operator_principal_arn':identity['Arn'],
    'operator_user_name':identity['Arn'].split('/')[-1],
    'aurora_cluster_arn':cluster['DBClusterArn'],'aurora_admin_secret_arn':secrets[0]['ARN'],
    'aurora_security_group_id':groups[0]['GroupId'],
    'expires_at':(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat().replace('+00:00','Z'),
    'estimated_total_usd':20,'reporter_zip':(STATE/'reporter-sqs.zip').as_posix()}
(STATE/'acceptance.tfvars.json').write_text(json.dumps(values,indent=2))
filters=[{'Type':'TERM_MATCH','Field':k,'Value':v} for k,v in {
    'instanceType':'t3.medium','location':'US East (N. Virginia)','operatingSystem':'Linux',
    'tenancy':'Shared','preInstalledSw':'NA','capacitystatus':'Used'}.items()]
price=aws('pricing','get-products',ServiceCode='AmazonEC2',Filters=filters)
(STATE/'ec2-price.json').write_text(json.dumps(price,indent=2))
rates=[]
for text in price['PriceList']:
    item=json.loads(text)
    for term in item['terms']['OnDemand'].values():
        for rate in term['priceDimensions'].values():
            rates.append({'description':rate['description'],'unit':rate['unit'],'usd':rate['pricePerUnit']['USD']})
print(json.dumps({'tfvars':'prepared','hours':8,'nodes':2,'instance':'t3.medium','ec2_rates':rates}))
