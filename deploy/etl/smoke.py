"""Real CronJob/manual Job acceptance using synthetic quotes in the owned local lab.

Run via uv run --no-project deploy/etl/smoke.py --image alex-api:<revision>.
Requires deploy/local/run.py up and deploy/etl/run.py install --fixture first.
All altered schedules are restored suspended even if an assertion fails.
"""
import argparse
import json
import time
from uuid import uuid4

import run as etl

local = etl.local


def probe(*args):
    return json.loads(local.kube('exec','-i','deployment/api','--','python','-',*args,
                      data=(etl.ROOT/'deploy/etl/probe.py').read_text(),output=True))


def wait_job(name, succeeded=True):
    for _ in range(100):
        status = json.loads(local.kube('get','job',name,'-o','json',output=True)).get('status',{})
        done = next((c for c in status.get('conditions',[]) if c['type'] in ('Complete','Failed') and c['status']=='True'),None)
        if done:
            logs = local.kube('logs','job/'+name,output=True)
            (local.STATE/(name+'.log')).write_text(logs)
            assert (done['type']=='Complete')==succeeded, (name,done,logs)
            return json.loads(logs.strip().splitlines()[-1])
        time.sleep(2)
    raise AssertionError('Job timed out: '+name)


def manual(mode, *, succeed=True, **kwargs):
    name = etl.job('market-test-'+uuid4().hex[:8],mode,**kwargs)
    return wait_job(name,succeed)


def patch_cron(value):
    local.kube('patch','cronjob','market-daily','--type=merge','-p',json.dumps({'spec':value}))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',required=True)
    args=parser.parse_args()
    local.require_owner()
    original=json.loads(local.kube('get','cronjob','market-daily','-o','json',output=True))['spec']
    assert original['jobTemplate']['spec']['template']['spec']['containers'][0]['command']==['python','/fixtures/etl_fixture.py'], 'Fixture-only test'
    try:
        baseline=probe('status')
        manual('backfill',start=baseline['start'],end=baseline['end'])
        assert probe('status')['health']['healthy']
        gap=probe('gap','middle')['date']
        warning=manual('monitor',succeed=False)
        assert any(e['code']=='missing_session' and e['details']['trade_date']==gap for e in warning['emitted_alerts'])
        manual('backfill',start=gap,end=gap,symbols=['AAPL'])
        assert probe('status')['health']['healthy']
        probe('gap','latest')
        failed=manual('daily',symbols=['AAPL'],env={'FIXTURE_QUALITY_FAILURE':'true'},succeed=False)
        assert failed['status']=='partial' and failed['error_code']=='quality_rejected'
        assert failed['accepted_count']==1 and failed['rejected_count']==1
        # Force the real CronJob controller to fetch while a simultaneous manual Job competes.
        probe('gap','latest')
        template=original['jobTemplate']
        container=template['spec']['template']['spec']['containers'][0]
        container['args']=['daily','--symbols','AAPL']
        container['env']=[{'name':'FIXTURE_DELAY_SECONDS','value':'20'}]
        patch_cron({'schedule':'* * * * *','suspend':False,'jobTemplate':template})
        cron_job=None
        for _ in range(65):
            jobs=json.loads(local.kube('get','jobs','-o','json',output=True))['items']
            active=[j for j in jobs if any(o['kind']=='CronJob' and o['name']=='market-daily' for o in j['metadata'].get('ownerReferences',[])) and j.get('status',{}).get('active')]
            state=probe('status')
            if active and any(e['status']=='running' for e in state['executions']):
                cron_job=active[-1]['metadata']['name']
                break
            time.sleep(2)
        assert cron_job, 'CronJob controller did not start the scheduled execution'
        patch_cron({'suspend':True})
        blocked=manual('backfill',start=baseline['end'],end=baseline['end'],symbols=['AAPL'],succeed=False)
        assert blocked['status']=='blocked' and blocked['error_code']=='batch_busy'
        scheduled=wait_job(cron_job)
        assert scheduled['status']=='succeeded'
        before=probe('status')
        retry=manual('backfill',start=baseline['end'],end=baseline['end'],symbols=['AAPL'])
        after=probe('status')
        assert retry['accepted_count']==0
        assert (after['price_count'],after['observation_count'])==(before['price_count'],before['observation_count'])
        assert after['health']['healthy']
        # Raw files must outlive their completed Pods on the shared volume.
        local.kube('delete','pod','-l','app=market-etl','--field-selector=status.phase=Succeeded')
        files=local.run(['docker','exec',local.NODE,'find','/var/lib/alex-market-raw','-type','f'],capture_output=True).stdout.splitlines()
        assert len(files)>=20
        local.run(['docker','run','--rm','--network','host',
                   '-v',f'{etl.ROOT / "deploy/etl"}:/fixtures:ro','-v',f'{local.STATE}:/evidence',
                   '--entrypoint','python',args.image,'/fixtures/api_smoke.py'])
        evidence={'synthetic_quotes':True,'controller_job':cron_job,'missed_date':gap,
                  'manual_recovery':True,'quality_failure_job_nonzero':True,
                  'concurrent_manual_blocked':True,'retry_idempotent':True,'raw_survives_pod_deletion':True,
                  'raw_files':len(files),'price_count':after['price_count'],'api_authenticated':True,
                  'cron_execution_id':scheduled['id'],'blocked_execution_id':blocked['id']}
        (local.STATE/'task08-evidence.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence),flush=True)
    finally:
        # Restore canonical daily schedule, args and suspension after accelerated test.
        original['suspend']=True
        original['schedule']='15 0 * * *'
        original['jobTemplate']['spec']['template']['spec']['containers'][0]['args']=['daily']
        original['jobTemplate']['spec']['template']['spec']['containers'][0]['env']=[]
        patch_cron(original)


if __name__=='__main__':
    main()
