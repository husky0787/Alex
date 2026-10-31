"""Run manual daily and a controller-created CronJob against real saved prices."""
import json
import time
import secrets

from manage import STATE,apply,aws,config,kube,wait_job
from manifests import manual_job


def main():
    cfg=config()
    def counts():
        result=aws('rds-data','execute-statement',resourceArn=cfg['aurora_cluster_arn'],
            secretArn=cfg['api_secret_arn'],database=cfg['database'],
            sql='SELECT (SELECT count(*) FROM daily_prices),(SELECT count(*) FROM market_observations)')
        return [cell['longValue'] for cell in result['records'][0]]
    before=counts()
    cron=json.loads(kube('get','cronjob','market-daily','-o','json'))
    name='manual-daily-'+secrets.token_hex(4)
    apply(manual_job(cron,name,['daily','--raw-bucket',cfg['bucket']]))
    wait_job(name)
    manual_job_metadata=json.loads(kube('get','job',name,'-o','json'))['metadata']
    manual=json.loads(kube('logs','job/'+name).strip().splitlines()[-1])
    assert manual['status']=='succeeded'
    uid=cron['metadata']['uid']
    original={'spec':{'schedule':cron['spec']['schedule'],'suspend':cron['spec']['suspend']}}
    existing={j['metadata']['uid'] for j in json.loads(kube('get','jobs','-o','json'))['items']}
    try:
        kube('patch','cronjob','market-daily','--type=merge','-p',json.dumps({'spec':{'schedule':'* * * * *','suspend':False}}))
        deadline=time.monotonic()+130
        job=None
        while time.monotonic()<deadline:
            jobs=json.loads(kube('get','jobs','-o','json'))['items']
            job=next((j for j in jobs if j['metadata']['uid'] not in existing and
                any(o['uid']==uid for o in j['metadata'].get('ownerReferences',[]))),None)
            if job:
                break
            time.sleep(4)
        if job is None:
            raise TimeoutError('CronJob controller did not create a Job')
        name=job['metadata']['name']
        wait_job(name)
        scheduled=json.loads(kube('logs','job/'+name).strip().splitlines()[-1])
        assert scheduled['status']=='succeeded'
    finally:
        kube('patch','cronjob','market-daily','--type=merge','-p',json.dumps(original))
    after=counts()
    assert before==after
    result={'manual':manual,'manual_job':{'name':manual_job_metadata['name'],'uid':manual_job_metadata['uid']},
            'scheduled':scheduled,'controller_job':job,
            'counts_before':before,'counts_after':after,'no_duplicate_prices_or_observations':True}
    (STATE/'schedule-evidence.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'manual_daily':'succeeded','controller_daily':'succeeded','idempotent':True,'counts':after}))


if __name__=='__main__':
    main()
