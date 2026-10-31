"""Render cloud manifests from Terraform outputs; never put secret values here."""
from copy import deepcopy
import re

NS='alex-cloud'


def manifests(config, image, jwks):
    if not re.fullmatch(r'[0-9]+\.dkr\.ecr\.us-east-1\.amazonaws\.com/alex-task09@sha256:[a-f0-9]{64}',image):
        raise ValueError('Use the immutable task09 ECR image digest')
    def obj(kind,name,spec=None,api='v1',**extra):
        value={'apiVersion':api,'kind':kind,'metadata':{'name':name,'namespace':NS},**extra}
        if spec is not None:
            value['spec']=spec
        return value
    security={'runAsNonRoot':True,'runAsUser':10001,'runAsGroup':10001,'fsGroup':10001,
              'seccompProfile':{'type':'RuntimeDefault'}}
    container_security={'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}
    common={'AWS_REGION':'us-east-1','AWS_DEFAULT_REGION':'us-east-1','DEFAULT_AWS_REGION':'us-east-1',
            'AWS_EC2_METADATA_DISABLED':'true','AURORA_CLUSTER_ARN':config['aurora_cluster_arn'],
            'AURORA_DATABASE':config['database'],'ALERT_TOPIC_ARN':config['alerts_topic_arn']}
    def pod(mode):
        account='api' if mode=='api' else 'etl'
        env={**common,'WORKLOAD_SECRET_ARN':config[account+'_secret_arn']}
        if account=='api':
            env.update(AURORA_SECRET_ARN=config['api_secret_arn'],SQS_QUEUE_URL=config['jobs_queue_url'],
                       CLERK_JWKS_URL='http://acceptance-jwks:8080/jwks.json',CORS_ORIGINS=config['endpoint'])
        args=[mode] if account=='api' or mode=='monitor' else [mode,'--raw-bucket',config['bucket']]
        container={'name':account,'image':image,'imagePullPolicy':'IfNotPresent',
                   'command':['python','-m','market_data.cloud'],'args':args,
                   'env':[{'name':k,'value':v} for k,v in env.items()]+[
                       {'name':'POD_NAME','valueFrom':{'fieldRef':{'fieldPath':'metadata.name'}}}],
                   'securityContext':container_security,
                   'resources':{'requests':{'cpu':'100m','memory':'256Mi'},'limits':{'cpu':'1','memory':'512Mi'}},
                   'volumeMounts':[{'name':'tmp','mountPath':'/tmp'}]}
        return {'serviceAccountName':account,'securityContext':security,
                'containers':[container],'volumes':[{'name':'tmp','emptyDir':{'sizeLimit':'64Mi'}}]}
    api_pod=pod('api')
    api_container=api_pod['containers'][0]
    api_container.update(ports=[{'containerPort':8000,'name':'http'}],
        readinessProbe={'httpGet':{'path':'/ready','port':'http'},'periodSeconds':5,'timeoutSeconds':4},
        livenessProbe={'httpGet':{'path':'/health','port':'http'},'periodSeconds':10},
        startupProbe={'httpGet':{'path':'/health','port':'http'},'periodSeconds':5,'failureThreshold':36})
    objects=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':NS}},
        *[obj('ServiceAccount',name,automountServiceAccountToken=False) for name in ('api','etl')],
        obj('ConfigMap','acceptance-jwks',data={'jwks.json':jwks}),
        obj('Deployment','acceptance-jwks',{'replicas':1,'selector':{'matchLabels':{'app':'acceptance-jwks'}},
            'template':{'metadata':{'labels':{'app':'acceptance-jwks'}},'spec':{
                'automountServiceAccountToken':False,'securityContext':security,
                'containers':[{'name':'jwks','image':image,'command':['python','-m','http.server','8080','--directory','/keys'],
                    'securityContext':container_security,'resources':{'requests':{'cpu':'10m','memory':'32Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},
                    'volumeMounts':[{'name':'keys','mountPath':'/keys','readOnly':True}]}],
                'volumes':[{'name':'keys','configMap':{'name':'acceptance-jwks'}}]}}},api='apps/v1'),
        obj('Service','acceptance-jwks',{'selector':{'app':'acceptance-jwks'},'ports':[{'port':8080}]}),
        obj('Deployment','api',{'replicas':2,'revisionHistoryLimit':3,'progressDeadlineSeconds':180,
            'strategy':{'type':'RollingUpdate','rollingUpdate':{'maxUnavailable':0,'maxSurge':1}},
            'selector':{'matchLabels':{'app':'alex-api'}},'template':{'metadata':{'labels':{'app':'alex-api'}},'spec':api_pod}},api='apps/v1'),
        obj('Service','api',{'type':'NodePort','selector':{'app':'alex-api'},
            'ports':[{'port':8000,'targetPort':8000,'nodePort':30080}]}),
        obj('HorizontalPodAutoscaler','api',{'scaleTargetRef':{'apiVersion':'apps/v1','kind':'Deployment','name':'api'},
            'minReplicas':2,'maxReplicas':3,'metrics':[{'type':'Resource','resource':{'name':'cpu',
                'target':{'type':'Utilization','averageUtilization':60}}}]},api='autoscaling/v2')]
    for mode,schedule in [('daily','15 0 * * *'),('monitor','45 * * * *')]:
        job_pod=pod(mode);job_pod['restartPolicy']='Never'
        objects.append(obj('CronJob','market-'+mode,{'schedule':schedule,'timeZone':'America/New_York',
            'suspend':True,'concurrencyPolicy':'Forbid','startingDeadlineSeconds':900,
            'successfulJobsHistoryLimit':2,'failedJobsHistoryLimit':3,'jobTemplate':{'spec':{
                'backoffLimit':0,'activeDeadlineSeconds':1800,'ttlSecondsAfterFinished':86400,
                'template':{'metadata':{'labels':{'app':'market-etl'}},'spec':job_pod}}}},api='batch/v1'))
    return {'apiVersion':'v1','kind':'List','items':objects}


def manual_job(cronjob, name, args):
    spec=deepcopy(cronjob['spec']['jobTemplate']['spec'])
    spec['template']['spec']['containers'][0]['args']=args
    return {'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':NS},'spec':spec}
