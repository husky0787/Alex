"""Bounded fault drills against only the task09 API Deployment."""
import argparse
from datetime import datetime,timezone
import json
import os
import subprocess
import time
import secrets

from manage import STATE,NS,apply,aws,config,kube
from manifests import manual_job


def now():
    return datetime.now(timezone.utc).isoformat()


def wait_for(read,predicate,seconds):
    deadline=time.monotonic()+seconds
    while True:
        value=read()
        if predicate(value):
            return value
        if time.monotonic()>deadline:
            raise TimeoutError('Acceptance condition was not reached before the bounded deadline')
        time.sleep(5)


def read(kind,name):
    return json.loads(kube('get',kind,name,'-o','json'))


def rollout():
    return kube('rollout','status','deployment/api','--timeout=180s')


def replacement_ready(pods,original_uids,desired):
    active=[p for p in pods if not p['metadata'].get('deletionTimestamp')]
    return (len(active)==desired and desired>0
        and bool({p['metadata']['uid'] for p in active}-original_uids)
        and all(any(c['type']=='Ready' and c['status']=='True' for c in p.get('status',{}).get('conditions',[])) for p in active))


def recovery():
    start=now()
    pods=json.loads(kube('get','pods','-l','app=alex-api','-o','json'))['items']
    victim=pods[0]['metadata']['name']
    original_uids={p['metadata']['uid'] for p in pods}
    kube('delete','pod',victim,'--wait=true','--timeout=60s')
    rollout()
    def observed():
        return (json.loads(kube('get','pods','-l','app=alex-api','-o','json'))['items'],read('deployment','api')['spec']['replicas'])
    new,desired=wait_for(observed,lambda value:replacement_ready(value[0],original_uids,value[1]),180)
    assert all(p['metadata']['name']!=victim for p in new)
    return {'start':start,'finish':now(),'deleted_pod':victim,'replacement_ready':True,
            'desired_replicas':desired,'ready_uids':[p['metadata']['uid'] for p in new if not p['metadata'].get('deletionTimestamp')]}


def rollback():
    before=read('deployment','api')['spec']['template']['spec']['containers'][0]['image']
    invalid=before.split('@')[0]+'@sha256:'+'0'*64
    start=now()
    try:
        kube('set','image','deployment/api','api='+invalid)
        def failing():
            pods=json.loads(kube('get','pods','-l','app=alex-api','-o','json'))['items']
            return [s['state']['waiting']['reason'] for p in pods for s in p.get('status',{}).get('containerStatuses',[])
                    if s.get('state',{}).get('waiting',{}).get('reason') in ('ErrImagePull','ImagePullBackOff')]
        reasons=wait_for(failing,bool,120)
    finally:
        kube('rollout','undo','deployment/api')
        rollout()
    assert read('deployment','api')['spec']['template']['spec']['containers'][0]['image']==before
    return {'start':start,'finish':now(),'failure_observed':reasons,'original_digest_restored':True}


def scaling():
    wait_for(lambda:read('hpa','api'),lambda h:bool(h.get('status',{}).get('currentMetrics')),180)
    metrics=kube('top','pods','-l','app=alex-api')
    pod=json.loads(kube('get','pods','-l','app=alex-api','-o','json'))['items'][0]['metadata']['name']
    start=now()
    code='import time\nend=time.monotonic()+90\nwhile time.monotonic()<end: sum(i*i for i in range(10000))'
    command=[os.getenv('KUBECTL','kubectl'),'--kubeconfig',str(STATE/'kubeconfig'),'-n',NS,
             'exec',pod,'--','python','-c',code]
    process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        hpa=wait_for(lambda:read('hpa','api'),lambda h:h.get('status',{}).get('currentReplicas',0)==3,150)
        rollout()
    finally:
        process.wait(timeout=110)
    return {'start':start,'finish':now(),'metrics':metrics,'scaled_to':3,'hpa_status':hpa['status']}


def receive_alerts(cfg):
    messages=aws('sqs','receive-message',QueueUrl=cfg['alerts_queue_url'],MaxNumberOfMessages=10,WaitTimeSeconds=1).get('Messages',[])
    events=[]
    for message in messages:
        event=json.loads(message['Body'])
        events.append(event)
        with (STATE/'received-alerts.jsonl').open('a') as stream:
            stream.write(json.dumps({'received_at':now(),'event':event})+'\n')
        aws('sqs','delete-message',QueueUrl=cfg['alerts_queue_url'],ReceiptHandle=message['ReceiptHandle'])
    return events


def alarm():
    cfg=config()
    def state():
        return aws('cloudwatch','describe-alarms',AlarmNames=[cfg['alarm_name']])['MetricAlarms'][0]['StateValue']
    wait_for(state,lambda s:s=='OK',600)
    hpa=read('hpa','api')
    # Recreate only the desired resource, not server-generated metadata/status.
    hpa={'apiVersion':hpa['apiVersion'],'kind':hpa['kind'],
         'metadata':{'name':'api','namespace':NS},'spec':hpa['spec']}
    received=[]
    while receive_alerts(cfg):
        pass
    start=now()
    try:
        kube('delete','hpa','api')
        kube('scale','deployment/api','--replicas=0')
        # The observed AWS service datapoints arrived several minutes late.
        # Preserve the two-period alarm; allow bounded time for delivery latency.
        wait_for(state,lambda s:s=='ALARM',600)
        def delivered():
            received.extend(receive_alerts(cfg))
            return any(e.get('AlarmName')==cfg['alarm_name'] and e.get('NewStateValue')=='ALARM'
                and datetime.fromisoformat(e['StateChangeTime'])>=datetime.fromisoformat(start) for e in received)
        wait_for(delivered,bool,120)
    finally:
        kube('scale','deployment/api','--replicas=2')
        apply(hpa)
        rollout()
    wait_for(state,lambda s:s=='OK',600)
    return {'start':start,'finish':now(),'alarm_delivered_to_sqs':True,'recovered_to_ok':True,'received':received}


def etl_alert():
    cfg=config()
    cron=read('cronjob','market-daily')
    name='market-alert-probe-'+secrets.token_hex(3)
    job=manual_job(cron,name,['daily','--raw-bucket',cfg['bucket']])
    job['spec']['activeDeadlineSeconds']=90
    for env in job['spec']['template']['spec']['containers'][0]['env']:
        if env['name']=='WORKLOAD_SECRET_ARN':
            # ETL must fail to read the API secret, before any database mutation.
            env['value']=cfg['api_secret_arn']
    start=now()
    received=[]
    try:
        apply(job)
        wait_for(lambda:read('job',name),lambda j:bool(j.get('status',{}).get('failed')),100)
        log=kube('logs','job/'+name)
        (STATE/'etl-alert-probe.log').write_text(log)
        assert 'cloud_entry_failed' in log and 'AccessDenied' in log
        def delivered():
            received.extend(receive_alerts(cfg))
            return any(e.get('event')=='market_etl_failed' and e.get('pod','').startswith(name+'-') for e in received)
        wait_for(delivered,bool,90)
    finally:
        kube('delete','job/'+name,'--ignore-not-found','--timeout=45s')
    return {'start':start,'finish':now(),'expected_failure':'AccessDeniedException',
            'etl_failure_delivered_to_sqs':True,'received':received}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['recovery','rollback','scaling','alarm','etl-alert','receive-alerts'])
    action=parser.parse_args().action
    if action=='receive-alerts':
        result=receive_alerts(config())
    else:
        result={'recovery':recovery,'rollback':rollback,'scaling':scaling,'alarm':alarm,'etl-alert':etl_alert}[action]()
    (STATE/(action+'-evidence.json')).write_text(json.dumps(result,indent=2))
    print(json.dumps({'action':action,'passed':True,'finished_at':now()}))


if __name__=='__main__':
    main()
