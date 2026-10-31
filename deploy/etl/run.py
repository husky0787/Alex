"""Install suspended ETL CronJobs into the owned local lab, or create a backfill Job.

Run with uv run --no-project. Credentials are read from a local JSON file and
sent to kubectl stdin, never command arguments. Fixture mode uses dummy keys.
"""
import argparse
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4

from resources import resources

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('local_cluster', ROOT/'deploy/local/run.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


def apply(objects):
    local.kube('apply','-f','-',data=json.dumps({'apiVersion':'v1','kind':'List','items':objects}))


def install(image, fixture, secret_file):
    local.require_owner()
    # Provision only this owned node's named raw directory; no host/global volumes.
    local.run(['docker','exec',local.NODE,'mkdir','-p','/var/lib/alex-market-raw'])
    local.run(['docker','exec',local.NODE,'chown','10001:10001','/var/lib/alex-market-raw'])
    if fixture:
        config = json.loads((local.STATE/'config-private.json').read_text())
        values = next(x['stringData'] for x in config['items'] if x['metadata']['name']=='api-secrets')
        secrets = {'MARKET_DATABASE_URL':values['MARKET_DATABASE_URL']}
        apply([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'etl-fixture'},
                'data':{'etl_fixture.py':(ROOT/'deploy/etl/etl_fixture.py').read_text()}}])
    else:
        if secret_file is None:
            raise ValueError('Supply --secret-file with MARKET_DATABASE_URL and MASSIVE_API_KEY')
        secrets = json.loads(secret_file.read_text())
        if not all(secrets.get(key) for key in ('MARKET_DATABASE_URL','MASSIVE_API_KEY')):
            raise ValueError('Both MARKET_DATABASE_URL and MASSIVE_API_KEY are required')
    apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'etl-secrets'},'stringData':secrets}])
    objects = resources(image,fixture=fixture)
    apply(objects)
    migration = deepcopy(objects[2]['spec']['jobTemplate']['spec'])
    container = migration['template']['spec']['containers'][0]
    container['command'] = ['python','-m','market_data']
    container['args'] = ['migrate']
    name = 'market-migrate-' + uuid4().hex[:8]
    apply([{'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name},'spec':migration}])
    local.kube('wait','--for=condition=complete','job/'+name,'--timeout=120s')
    print('Installed suspended CronJobs and migrated market schema. No schedules enabled yet.')


def job(name, mode, *, start=None, end=None, symbols=None, env=None):
    local.require_owner()
    parent = json.loads(local.kube('get','cronjob','market-daily','-o','json',output=True))
    spec = deepcopy(parent['spec']['jobTemplate']['spec'])
    container = spec['template']['spec']['containers'][0]
    container['args'] = [mode]
    if start:
        container['args'] += ['--from',str(start),'--to',str(end)]
    if symbols:
        container['args'] += ['--symbols',*symbols]
    if env:
        container['env'] = [{'name':k,'value':str(v)} for k,v in env.items()]
    value = {'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name},'spec':spec}
    local.kube('create','-f','-',data=json.dumps(value))
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','backfill','enable','suspend'])
    parser.add_argument('--image',default='alex-api:task08')
    parser.add_argument('--fixture',action='store_true')
    parser.add_argument('--secret-file',type=Path)
    parser.add_argument('--from',dest='start',type=date.fromisoformat)
    parser.add_argument('--to',dest='end',type=date.fromisoformat)
    parser.add_argument('--symbols',nargs='+')
    args = parser.parse_args()
    local.require_owner()
    if args.action=='install':
        install(args.image,args.fixture,args.secret_file)
    elif args.action=='backfill':
        if not args.start or not args.end:
            parser.error('backfill requires --from and --to')
        print(job('market-backfill-'+uuid4().hex[:8],'backfill',start=args.start,end=args.end,symbols=args.symbols))
    else:
        for name in ('market-daily','market-monitor'):
            local.kube('patch','cronjob',name,'--type=merge','-p',json.dumps({'spec':{'suspend':args.action=='suspend'}}))


if __name__=='__main__':
    main()
