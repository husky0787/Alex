"""Run bounded one-off workload permission probes in the isolated cluster."""
import json
from pathlib import Path

from manage import STATE, NS, apply, config, kube
from manifests import manual_job


def main():
    cfg=config()
    cron=json.loads(kube('get','cronjob','market-daily','-o','json'))
    results={}
    apply({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'permission-probe','namespace':NS},
           'data':{'verify_workload.py':Path(__file__).with_name('verify_workload.py').read_text()}})
    try:
        for role,other in [('api','etl'),('etl','api')]:
            name='permission-probe-'+role
            job=manual_job(cron,name,[])
            spec=job['spec']['template']['spec']
            spec['serviceAccountName']=role
            job['spec']['activeDeadlineSeconds']=180
            container=spec['containers'][0]
            container['command']=['python','/verify/verify_workload.py',role]
            container['env']=[{'name':key,'value':value} for key,value in {
                'AWS_REGION':'us-east-1','AWS_DEFAULT_REGION':'us-east-1',
                'WORKLOAD_SECRET_ARN':cfg[role+'_secret_arn'],
                'TEST_OTHER_SECRET_ARN':cfg[other+'_secret_arn'],
                'TEST_ADMIN_SECRET_ARN':cfg['aurora_admin_secret_arn'],'TEST_BUCKET':cfg['bucket']}.items()]
            container['volumeMounts'].append({'name':'verify','mountPath':'/verify','readOnly':True})
            spec['volumes'].append({'name':'verify','configMap':{'name':'permission-probe'}})
            try:
                apply(job)
                print(kube('wait','--for=condition=complete','job/'+name,'--timeout=150s'))
                log=kube('logs','job/'+name)
                (STATE/(name+'.log')).write_text(log)
                results[role]=json.loads(log.strip().splitlines()[-1])
                print(json.dumps({'role':role,'verified':True}))
            finally:
                kube('delete','job/'+name,'--ignore-not-found','--wait=true','--timeout=45s')
    finally:
        kube('delete','configmap/permission-probe','--ignore-not-found')
    (STATE/'permission-evidence.json').write_text(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
