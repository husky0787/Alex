"""Kubernetes resources for the local ETL lab; reuse the API's locked image.

Return ordinary Kubernetes objects; the runner serializes them as JSON manifests.
The static hostPath PV is deliberately limited to the disposable k3d node.
"""
from copy import deepcopy


def job_spec(image, args, *, fixture=False):
    container = {
        'name':'etl', 'image':image, 'imagePullPolicy':'Never',
        'command':['python', '/fixtures/etl_fixture.py'] if fixture else ['python','-m','market_data.scheduled'],
        'args':args,
        'envFrom':[{'secretRef':{'name':'etl-secrets'}}],
        'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,
                           'capabilities':{'drop':['ALL']}},
        'resources':{'requests':{'cpu':'100m','memory':'256Mi'},'limits':{'cpu':'1','memory':'512Mi'}},
        'volumeMounts':[{'name':'raw','mountPath':'/data'}, {'name':'tmp','mountPath':'/tmp'}],
    }
    volumes = [{'name':'raw','persistentVolumeClaim':{'claimName':'market-raw'}},
               {'name':'tmp','emptyDir':{'sizeLimit':'64Mi'}}]
    if fixture:
        container['volumeMounts'].append({'name':'fixture','mountPath':'/fixtures','readOnly':True})
        volumes.append({'name':'fixture','configMap':{'name':'etl-fixture'}})
    return {'backoffLimit':0, 'activeDeadlineSeconds':1800, 'ttlSecondsAfterFinished':86400,
            'template':{'metadata':{'labels':{'app':'market-etl'}}, 'spec':{
                'automountServiceAccountToken':False,'restartPolicy':'Never',
                'securityContext':{'runAsNonRoot':True,'runAsUser':10001,'runAsGroup':10001,
                                   'seccompProfile':{'type':'RuntimeDefault'}},
                'containers':[container], 'volumes':volumes}}}


def cron(name, schedule, spec):
    return {'apiVersion':'batch/v1','kind':'CronJob','metadata':{'name':name},'spec':{
        'schedule':schedule,'timeZone':'America/New_York','suspend':True,
        'concurrencyPolicy':'Forbid','startingDeadlineSeconds':900,
        'successfulJobsHistoryLimit':2,'failedJobsHistoryLimit':3,
        'jobTemplate':{'spec':deepcopy(spec)}}}


def resources(image, *, fixture=False):
    return [
        {'apiVersion':'v1','kind':'PersistentVolume','metadata':{'name':'alex-market-raw'},'spec':{
            'capacity':{'storage':'1Gi'}, 'accessModes':['ReadWriteOnce'],
            'storageClassName':'','persistentVolumeReclaimPolicy':'Retain',
            'claimRef':{'namespace':'alex-local','name':'market-raw'},
            'hostPath':{'path':'/var/lib/alex-market-raw','type':'Directory'}}},
        {'apiVersion':'v1','kind':'PersistentVolumeClaim','metadata':{'name':'market-raw'},'spec':{
            'accessModes':['ReadWriteOnce'],'storageClassName':'','volumeName':'alex-market-raw',
            'resources':{'requests':{'storage':'1Gi'}}}},
        cron('market-daily','15 0 * * *',job_spec(image,['daily'],fixture=fixture)),
        cron('market-monitor','45 * * * *',job_spec(image,['monitor'],fixture=fixture)),
    ]
