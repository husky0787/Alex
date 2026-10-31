"""Manage only the dedicated alex-task07 k3d cluster. Run with uv run --no-project.

Requires Docker and k3d on the same host. Use --image with a unique build tag.
The API entry binds loopback only; forward port 18080 over SSH for remote use.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT/'.local/kubernetes/task07'
CLUSTER = 'alex-task07'
NODE = 'k3d-alex-task07-server-0'
NS = 'alex-local'


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, text=True, **kwargs)


def kube(*args, data=None, output=False):
    return run(['docker','exec','-i',NODE,'k3s','kubectl','-n',NS,*args],
               input=data, capture_output=output).stdout


def wait(name):
    kube('rollout','status','deployment/'+name,'--timeout=180s')


def load_image(image):
    # Avoid k3d's additional tools image. Import only into our named node.
    with subprocess.Popen(['docker','image','save',image],stdout=subprocess.PIPE) as source:
        result=subprocess.run(['docker','exec','-i',NODE,'k3s','ctr','images','import','-'],stdin=source.stdout)
        source.stdout.close()
        assert source.wait()==0 and result.returncode==0, 'Image import failed'


def image_script(image, script):
    user = ['--user',f'{os.getuid()}:{os.getgid()}'] if hasattr(os,'getuid') else []
    return run(['docker','run','--rm',*user,'--network','host',
        '-v',f'{ROOT / "deploy/local"}:/fixtures:ro','-v',f'{STATE}:/output',
        '-v',f'{STATE}:/evidence','--entrypoint','python',image,f'/fixtures/{script}'])


def up(args):
    STATE.mkdir(parents=True,exist_ok=True)
    marker=STATE/'owner.json'
    clusters=json.loads(run([args.k3d,'cluster','list','-o','json'],capture_output=True).stdout)
    exists=any(c['name']==CLUSTER for c in clusters)
    if exists and (not marker.exists() or json.loads(marker.read_text())['root'] != str(ROOT)):
        raise RuntimeError('Cluster name already exists without this checkout ownership marker')
    if not exists:
        run([args.k3d,'cluster','create',CLUSTER,'--image','rancher/k3s:v1.35.5-k3s1',
            '--no-lb','--no-image-volume','--servers-memory','4g','--api-port','127.0.0.1:16443',
            '-p','127.0.0.1:18080:30080@server:0','--kubeconfig-update-default=false',
            '--kubeconfig-switch-context=false','--k3s-arg','--disable=traefik,metrics-server,local-storage@server:0',
            '--timeout','180s'])
        marker.write_text(json.dumps({'cluster':CLUSTER,'root':str(ROOT)}))
    load_image(args.image)
    load_image(args.postgres_image)
    kube('apply','-f','-',data=json.dumps({'apiVersion':'v1','kind':'Namespace','metadata':{'name':NS}}))
    if not (STATE/'config-private.json').exists():
        image_script(args.image,'prepare.py')
    kube('apply','-f','-',data=(STATE/'config-private.json').read_text())
    fixture={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'fixture-code'},'data':{
        'fixtures.py':(ROOT/'deploy/local/fixtures.py').read_text(),
        'schema.sql':(ROOT/'backend/database/migrations/001_schema.sql').read_text()}}
    kube('apply','-f','-',data=json.dumps(fixture))
    deps=(ROOT/'deploy/local/dependencies.yaml').read_text().replace('alex-api:task07',args.image).replace('postgres:17.6',args.postgres_image)
    kube('apply','-f','-',data=deps)
    wait('postgres')
    wait('fixtures')
    kube('apply','-f','-',data=(ROOT/'deploy/local/api.yaml').read_text().replace('alex-api:task07',args.image))
    wait('api')
    image_script(args.image,'smoke.py')
    (STATE/'deployment.json').write_text(kube('get','deployment','api','-o','json',output=True))
    (STATE/'images.json').write_text(run(['docker','image','inspect',args.image,args.postgres_image],capture_output=True).stdout)


def recovery(args):
    assert (STATE/'owner.json').exists(), 'Missing cluster ownership marker'
    before=json.loads(kube('get','pods','-l','app=alex-api','-o','json',output=True))['items']
    victim=before[0]['metadata']['name']
    kube('delete','pod',victim,'--wait=true')
    wait('api')
    kube('wait','--for=condition=Ready','pod','-l','app=alex-api','--timeout=120s')
    after=json.loads(kube('get','pods','-l','app=alex-api','-o','json',output=True))['items']
    assert len(after)==2 and victim not in [p['metadata']['name'] for p in after]
    image_script(args.image,'smoke.py')
    # A syntactically valid image update that cannot start; old replicas remain ready.
    kube('set','image','deployment/api','api=alex-api:task07-intentionally-missing')
    try:
        run(['docker','exec',NODE,'k3s','kubectl','-n',NS,'rollout','status','deployment/api','--timeout=90s'],capture_output=True)
        raise AssertionError('Deliberately broken rollout unexpectedly succeeded')
    except subprocess.CalledProcessError as exc:
        failed_text=exc.stdout+exc.stderr
        (STATE/'failed-rollout.txt').write_text(failed_text)
        deployment=json.loads(kube('get','deployment','api','-o','json',output=True))
        assert any(c['reason']=='ProgressDeadlineExceeded' for c in deployment['status']['conditions']), deployment['status']
        assert deployment['status'].get('availableReplicas',0)==2
    finally:
        kube('rollout','undo','deployment/api')
        wait('api')
    image_script(args.image,'smoke.py')
    restored=json.loads(kube('get','deployment','api','-o','json',output=True))
    assert restored['spec']['template']['spec']['containers'][0]['image']==args.image
    # Dependency outage makes API unready, without treating it as a liveness failure.
    restarts=sum(c['restartCount'] for p in json.loads(kube('get','pods','-l','app=alex-api','-o','json',output=True))['items'] for c in p['status']['containerStatuses'])
    kube('scale','deployment/fixtures','--replicas=0')
    try:
        for _ in range(30):
            pods=json.loads(kube('get','pods','-l','app=alex-api','-o','json',output=True))['items']
            if all(not c['ready'] for p in pods for c in p['status']['containerStatuses']):
                break
            time.sleep(2)
        else:
            raise AssertionError('API stayed ready during database transport outage')
        assert sum(c['restartCount'] for p in pods for c in p['status']['containerStatuses'])==restarts
    finally:
        kube('scale','deployment/fixtures','--replicas=1')
        wait('fixtures')
        kube('wait','--for=condition=Ready','pod','-l','app=alex-api','--timeout=120s')
    image_script(args.image,'smoke.py')
    (STATE/'recovery.json').write_text(json.dumps({'pod_replaced':True,'bad_rollout_detected':True,
        'old_replicas_available':True,'rollback_restored':True,'dependency_outage_unready_without_restart':True}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['up','smoke','recovery','down'])
    parser.add_argument('--k3d',default='k3d')
    parser.add_argument('--image',default='alex-api:task07')
    parser.add_argument('--postgres-image',default='postgres:17.6')
    args=parser.parse_args()
    if args.action=='up':
        up(args)
    elif args.action=='smoke':
        image_script(args.image,'smoke.py')
    elif args.action=='recovery':
        recovery(args)
    else:
        marker=STATE/'owner.json'
        assert marker.exists() and json.loads(marker.read_text())['root']==str(ROOT), 'Missing cluster ownership marker'
        run([args.k3d,'cluster','delete',CLUSTER])
        marker.unlink()


if __name__=='__main__':
    main()
