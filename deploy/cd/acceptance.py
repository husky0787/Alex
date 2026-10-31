"""Deploy verified images to real EKS with disposable application dependencies."""
from contextlib import contextmanager
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from lifecycle import ROOT, STATE, EVIDENCE, STACK, evidence

sys.path.insert(0, str(ROOT / 'deploy/ci'))
import acceptance as ci_acceptance
from release import check_http

NS = 'alex-cd'


def command(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, text=True, **kwargs)


def kube(*args, data=None):
    return command('kubectl', '--kubeconfig', STATE / 'kubeconfig', '--context', STACK,
        '-n', NS, '--request-timeout=30s', *args, input=data, capture_output=True).stdout


def docker_script(image, script):
    command('docker', 'run', '--rm', '--network', 'host', '--user', f'{os.getuid()}:{os.getgid()}',
        '-v', f'{ROOT / "deploy/local"}:/fixtures:ro', '-v', f'{STATE}:/output',
        '-v', f'{STATE}:/evidence', '--entrypoint', 'python', image, f'/fixtures/{script}')


@contextmanager
def forward():
    """Reconnect after rolling replacement terminates the selected Service Pod."""
    stop = threading.Event()
    process = []

    def supervise():
        with (STATE / 'port-forward-private.log').open('a', encoding='utf-8') as log:
            while not stop.is_set():
                child = subprocess.Popen(['kubectl', '--kubeconfig', str(STATE / 'kubeconfig'),
                    '--context', STACK, '-n', NS, 'port-forward', 'service/api',
                    '18080:8000', '--address=127.0.0.1'], stdout=log, stderr=log)
                process[:] = [child]
                while child.poll() is None and not stop.wait(0.5):
                    pass
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
                stop.wait(1)

    thread = threading.Thread(target=supervise, daemon=True)
    thread.start()
    try:
        check_http('http://127.0.0.1:18080', [])
        yield
    finally:
        stop.set()
        thread.join(timeout=15)
        if thread.is_alive():
            raise RuntimeError('Port-forward supervisor did not stop')


def rollout(image, commit, filename):
    output = EVIDENCE / filename
    result = subprocess.run([sys.executable, str(ROOT / 'deploy/ci/release.py'),
        '--kubeconfig', str(STATE / 'kubeconfig'), '--context', STACK, '--namespace', NS,
        '--image', image, '--commit', commit, '--url', 'http://127.0.0.1:18080',
        '--timeout', '180', '--evidence', str(output)])
    return result.returncode, json.loads(output.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    manifest = ci_acceptance.load_artifacts()
    if args.verify_only:
        return
    STATE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    repository = os.environ['ALEX_CD_REPOSITORY']
    registry = repository.split('/')[0]
    password = command('aws', 'ecr', 'get-login-password', '--region', 'us-east-1', capture_output=True).stdout
    command('docker', 'login', '--username', 'AWS', '--password-stdin', registry, input=password)
    images = {}
    try:
        for name in ('baseline', 'candidate'):
            images[name] = ci_acceptance.push_image(manifest['images'][name]['tag'],
                f"{repository}:cd-{os.environ['RELEASE_ID']}-{name}")
    finally:
        command('docker', 'logout', registry)
    baseline = manifest['images']['baseline']['tag']
    candidate = manifest['images']['candidate']['tag']
    docker_script(baseline, 'prepare.py')
    kube('apply', '-f', '-', data=json.dumps({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': NS}}))
    kube('apply', '-f', '-', data=(STATE / 'config-private.json').read_text())
    kube('apply', '-f', '-', data=json.dumps({'apiVersion': 'v1', 'kind': 'ConfigMap',
        'metadata': {'name': 'fixture-code'}, 'data': {
            'fixtures.py': (ROOT / 'deploy/local/fixtures.py').read_text(),
            'schema.sql': (ROOT / 'backend/database/migrations/001_schema.sql').read_text()}}))
    dependencies = (ROOT / 'deploy/local/dependencies.yaml').read_text().replace(
        'alex-api:task07', images['baseline']).replace('imagePullPolicy: Never', 'imagePullPolicy: IfNotPresent')
    kube('apply', '-f', '-', data=dependencies)
    for name in ('postgres', 'fixtures'):
        kube('rollout', 'status', f'deployment/{name}', '--timeout=240s')
    api = (ROOT / 'deploy/local/api.yaml').read_text().replace('alex-api:task07', images['baseline']).replace(
        'imagePullPolicy: Never', 'imagePullPolicy: IfNotPresent').replace('type: NodePort', 'type: ClusterIP').replace(', nodePort: 30080', '')
    kube('apply', '-f', '-', data=api)
    kube('rollout', 'status', 'deployment/api', '--timeout=240s')
    with forward():
        docker_script(baseline, 'smoke.py')
        schema_query = "SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position"
        before = kube('exec', 'deployment/postgres', '--', 'psql', '-U', 'alex', '-d', 'alex', '-Atc', schema_query)
        code, result = rollout(images['candidate'], manifest['commit'], 'release.json')
        if code or result['status'] != 'succeeded':
            raise RuntimeError('Candidate release failed (see release evidence)')
        docker_script(candidate, 'smoke.py')
        missing = repository + '@sha256:' + '0' * 64
        code, result = rollout(missing, manifest['commit'], 'rollback.json')
        if code == 0 or result['status'] != 'rolled_back' or result['previous_image'] != images['candidate']:
            raise RuntimeError('Fault drill did not restore the exact candidate')
        docker_script(candidate, 'smoke.py')
        after = kube('exec', 'deployment/postgres', '--', 'psql', '-U', 'alex', '-d', 'alex', '-Atc', schema_query)
        if before != after:
            raise RuntimeError('Database schema changed during image release')
    evidence('summary.json', {'environment': 'AWS EKS', 'commit': manifest['commit'],
        'source_ci_run': os.environ['SOURCE_CI_RUN'], 'images': images, 'fixtures': True,
        'healthy_release': True, 'failed_release_rolled_back': True,
        'authenticated_smoke_after_each': True, 'database_schema_unchanged': True})


if __name__ == '__main__':
    main()
