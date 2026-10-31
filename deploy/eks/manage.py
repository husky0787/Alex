"""Task-owned AWS/Kubernetes helpers. Run using uv from repository root.

AWS CLI manages temporary browser credentials; secret results stay in process
memory. kubeconfig is isolated under ignored .local/eks/task09/.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import re
import zipfile
import time

from manifests import manifests, manual_job, NS

ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/'.local/eks/task09'
TF=ROOT/'terraform/9_eks'
PROFILE='alex-task09'


def aws(service, operation, *, profile=PROFILE, **kwargs):
    # Keep secret payloads out of process arguments; remove the private input even
    # when the AWS invocation fails. mkstemp creates an owner-only file on POSIX.
    STATE.mkdir(parents=True,exist_ok=True)
    descriptor, path = tempfile.mkstemp(prefix='aws-input-',suffix='.json',dir=STATE)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(kwargs,stream)
        result=subprocess.run(['aws',service,operation,'--profile',profile,'--region','us-east-1',
                               '--cli-input-json','file://'+path,'--output','json','--no-cli-pager'],
                              capture_output=True,text=True)
    finally:
        Path(path).unlink(missing_ok=True)
    if result.returncode:
        # AWS errors can include supplied secret parameters; don't echo them.
        code=re.search(r'An error occurred \(([A-Za-z0-9_.-]+)\)',result.stderr)
        reason=code.group(1) if code else f'CLI exit {result.returncode}'
        raise RuntimeError(f'AWS {service}.{operation} failed: {reason}')
    return json.loads(result.stdout) if result.stdout.strip() else {}


def kube(*args, data=None):
    command=[os.getenv('KUBECTL','kubectl'),'--kubeconfig',str(STATE/'kubeconfig'),'-n',NS,*args]
    return subprocess.run(command,input=data,text=True,capture_output=True,check=True).stdout


def config():
    return json.loads((STATE/'deployment.json').read_text())


def apply(value):
    return kube('apply','-f','-',data=json.dumps(value))


def wait_job(name,timeout=240):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        status=json.loads(kube('get','job',name,'-o','json')).get('status',{})
        if status.get('succeeded'):
            return
        if status.get('failed'):
            raise RuntimeError(f'Job {name} failed; diagnostic log saved under the private state directory')
        time.sleep(3)
    raise TimeoutError(f'Job {name} exceeded {timeout} seconds')


def prepare_secrets():
    from dotenv import dotenv_values
    cfg=config()
    cluster=aws('rds','describe-db-clusters',DBClusterIdentifier=cfg['aurora_cluster_arn'])['DBClusters'][0]
    local=dotenv_values(ROOT/'.env')
    api_key=local.get('MASSIVE_API_KEY') or local.get('POLYGON_API_KEY')
    if not api_key:
        raise ValueError('Configure the local market API key before writing secrets')
    for role in ('api','etl'):
        secret_arn=cfg[role+'_secret_arn']
        current=aws('secretsmanager','describe-secret',SecretId=secret_arn)
        if current.get('VersionIdsToStages'):
            raise ValueError('Secret already initialized; do not silently rotate database credentials')
    for role in ('api','etl'):
        value={'username':'alex_task09_'+role,'password':secrets.token_urlsafe(32),
               'host':cluster['Endpoint'],'dbname':'alex_task09'}
        if role=='etl':
            value['MASSIVE_API_KEY']=api_key
        aws('secretsmanager','put-secret-value',SecretId=cfg[role+'_secret_arn'],SecretString=json.dumps(value))
    print('Initialized two Secrets Manager values; no credentials written to manifests or stdout.')


def prepare_reporter(source,expected):
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
        raise ValueError('Verified Reporter source ZIP hash differs; rebuild and verify before use')
    target=STATE/'reporter-sqs.zip'
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as output:
        for item in original.infolist():
            output.writestr(item,original.read(item.filename))
        output.write(ROOT/'deploy/eks/sqs_handler.py','sqs_handler.py')
    print(json.dumps({'artifact':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))


def prepare_jwks():
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key_path=STATE/'signing.pem'
    if key_path.exists():
        raise ValueError('Signing key already exists; reuse the existing acceptance identity')
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    key_path.chmod(0o600)
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid='task09',alg='RS256',use='sig')
    (STATE/'jwks.json').write_text(json.dumps({'keys':[public]}))
    print('Created local acceptance signer and public JWKS; private key excluded from manifests.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['reporter','secrets','jwks','render','bootstrap','database-cleanup','backfill','daily','monitor'])
    parser.add_argument('--image')
    parser.add_argument('--source',type=Path,default=ROOT/'.local/research/task-06/reporter-linux-local.zip')
    parser.add_argument('--sha256',default='277c02fd119381a2c6a2c3b305815563fa7d546494daf0c1ed522499c5067d3d')
    parser.add_argument('--from',dest='start')
    parser.add_argument('--to',dest='end')
    parser.add_argument('--symbols',nargs='+')
    args=parser.parse_args()
    STATE.mkdir(parents=True,exist_ok=True)
    if args.action=='reporter':
        prepare_reporter(args.source,args.sha256);return
    if args.action=='secrets':
        prepare_secrets();return
    if args.action=='jwks':
        prepare_jwks();return
    cfg=config()
    if args.action=='render':
        value=manifests(cfg,args.image,(STATE/'jwks.json').read_text())
        (STATE/'manifests.json').write_text(json.dumps(value,indent=2))
        print('Rendered credential-free deployment manifests; inspect then kubectl apply.')
    elif args.action in ('bootstrap','database-cleanup'):
        script='bootstrap_database.py' if args.action=='bootstrap' else 'cleanup_database.py'
        documents=json.loads((STATE/'manifests.json').read_text())
        apply(documents['items'][0])
        job=manual_job(next(x for x in documents['items'] if x['kind']=='CronJob'),'database-bootstrap',[])
        spec=job['spec']['template']['spec']
        spec['serviceAccountName']='bootstrap'
        container=spec['containers'][0]
        container.update(command=['python','/bootstrap/'+script],args=[])
        container['env']=[{'name':k,'value':v} for k,v in {
            'AWS_REGION':'us-east-1','AWS_DEFAULT_REGION':'us-east-1',
            'ADMIN_SECRET_ARN':cfg['aurora_admin_secret_arn'],'API_SECRET_ARN':cfg['api_secret_arn'],
            'ETL_SECRET_ARN':cfg['etl_secret_arn']}.items()]
        container['volumeMounts'].append({'name':'bootstrap','mountPath':'/bootstrap','readOnly':True})
        spec['volumes'].append({'name':'bootstrap','configMap':{'name':'database-bootstrap'}})
        failure=None
        try:
            apply({'apiVersion':'v1','kind':'ServiceAccount','metadata':{'name':'bootstrap','namespace':NS},'automountServiceAccountToken':False})
            apply({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'database-bootstrap','namespace':NS},
                   'data':{script:(ROOT/'deploy/eks'/script).read_text()}})
            apply(job)
            wait_job('database-bootstrap')
            print(kube('logs','job/database-bootstrap'))
        except Exception as exc:
            failure=exc
            try:
                (STATE/'bootstrap-failure.log').write_text(kube('logs','job/database-bootstrap'))
            except subprocess.CalledProcessError:
                pass
            raise
        finally:
            try:
                print(kube('delete','job/database-bootstrap','serviceaccount/bootstrap','configmap/database-bootstrap','--ignore-not-found','--wait=true','--timeout=60s'))
            except subprocess.CalledProcessError:
                if failure is None:
                    raise
                print('Bootstrap cleanup failed; inspect and delete the task-owned bootstrap resources.')
    else:
        cron=json.loads(kube('get','cronjob','market-daily','-o','json'))
        command=[args.action]
        if args.action=='backfill':
            if not args.start or not args.end:
                parser.error('backfill needs explicit --from and --to')
            command += ['--from',args.start,'--to',args.end]
        command += ['--raw-bucket',cfg['bucket']]
        if args.symbols:
            command += ['--symbols',*args.symbols]
        name='market-'+args.action+'-'+secrets.token_hex(4)
        print(apply(manual_job(cron,name,command)))
        print(name)


if __name__=='__main__':
    main()
