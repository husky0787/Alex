"""Exercise the shared release runner in a disposable hosted-runner Kubernetes cluster.

Normal CI uses a local registry. Controlled release mode publishes the exact tested
archives to ECR with the job's short-lived OIDC identity, then pulls ECR digests.
Only public summaries are saved in evidence; private fixture data stays in .local.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from build import OUT, ROOT, run, sha256
sys.path.insert(0, str(ROOT / 'deploy/local'))
import run as local

EVIDENCE = ROOT / '.local/ci/evidence'
REGISTRY = 'k3d-alex-ci-registry:5000'


def command(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, text=True, **kwargs)


def load_artifacts():
    manifest = json.loads((OUT / 'manifest.json').read_text())
    if manifest['commit'] != os.environ['GITHUB_SHA']:
        raise RuntimeError('Artifact commit differs from workflow commit')
    for name in ('baseline', 'candidate'):
        entry = manifest['images'][name]
        archive = OUT / (name + '.tar')
        if sha256(archive) != entry['sha256']:
            raise RuntimeError('Container archive checksum mismatch')
        command('docker', 'load', '-i', archive)
        image = json.loads(run('docker', 'image', 'inspect', entry['tag']))[0]
        if image['Id'] != entry['id'] or image['Config']['Labels']['org.opencontainers.image.revision'] != entry['commit']:
            raise RuntimeError('Container identity or revision label mismatch')
    return manifest


def push_image(tag, destination):
    command('docker', 'tag', tag, destination)
    command('docker', 'push', destination)
    repository = destination.rsplit(':', 1)[0]
    matches = [ref for ref in json.loads(run('docker', 'image', 'inspect', destination))[0]['RepoDigests']
               if ref.startswith(repository + '@sha256:')]
    if len(matches) != 1:
        raise RuntimeError('Expected one pushed repository digest')
    return matches[0]


def schema_signature():
    sql = "SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position"
    return local.kube('exec', 'deployment/postgres', '--', 'psql', '-U', 'alex', '-d', 'alex', '-Atc', sql, output=True)


def invoke_release(image, commit, filename):
    path = EVIDENCE / filename
    result = subprocess.run([sys.executable, str(ROOT / 'deploy/ci/release.py'),
        '--kubeconfig', str(EVIDENCE.parent / 'kubeconfig'), '--context', 'k3d-' + local.CLUSTER,
        '--namespace', local.NS, '--image', image, '--commit', commit,
        '--url', 'http://127.0.0.1:18080', '--timeout', '100', '--evidence', str(path)])
    return result.returncode, json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ecr', help='Operator-configured ECR repository URL, not a workflow input')
    args = parser.parse_args()
    manifest = load_artifacts()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    clusters = json.loads(run('k3d', 'cluster', 'list', '-o', 'json'))
    if any(c['name'] == local.CLUSTER for c in clusters):
        raise RuntimeError('Refusing to reuse an existing Kubernetes cluster')
    password = None
    if args.ecr:
        # Never put the registry password in a process argument or evidence file.
        password = run('aws', 'ecr', 'get-login-password', '--region', 'us-east-1')
        command('docker', 'login', '--username', 'AWS', '--password-stdin', args.ecr.split('/')[0], input=password)
    registry_created = False
    cluster_attempted = False
    try:
        command('k3d', 'registry', 'create', 'alex-ci-registry', '--port', '5000')
        registry_created = True
        images = {}
        for name, entry in manifest['images'].items():
            release_tag = entry['commit'] + '-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
            destination = (args.ecr or 'localhost:5000/alex-api') + ':' + release_tag
            images[name] = push_image(entry['tag'], destination)
            if not args.ecr:
                images[name] = images[name].replace('localhost:5000/', REGISTRY + '/')
        for image in ('postgres:17.6', *local.SYSTEM_IMAGES):
            command('docker', 'pull', image)
        cluster_attempted = True
        local.up(SimpleNamespace(k3d='k3d', image=manifest['images']['baseline']['tag'],
                                 postgres_image='postgres:17.6', registry=REGISTRY))
        kubeconfig = run('k3d', 'kubeconfig', 'get', local.CLUSTER)
        (EVIDENCE.parent / 'kubeconfig').write_text(kubeconfig)
        # Bootstrap is local-only. All releases below start and end with digests.
        template = json.loads(local.kube('get', 'deployment', 'api', '-o', 'json', output=True))['spec']['template']
        api = next(c for c in template['spec']['containers'] if c['name'] == 'api')
        api.update(image=images['baseline'], imagePullPolicy='IfNotPresent')
        if args.ecr:
            import base64
            registry = args.ecr.split('/')[0]
            auth = base64.b64encode(('AWS:' + password).encode()).decode()
            secret = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'release-pull'},
                      'type': 'kubernetes.io/dockerconfigjson',
                      'stringData': {'.dockerconfigjson': json.dumps({'auths': {registry: {'auth': auth}}})}}
            local.kube('apply', '-f', '-', data=json.dumps(secret))
            template['spec']['imagePullSecrets'] = [{'name': 'release-pull'}]
        local.kube('patch', 'deployment', 'api', '--type=merge', '--patch-file=/dev/stdin',
                   data=json.dumps({'spec': {'template': template}}))
        local.wait('api')
        before = schema_signature()
        code, success = invoke_release(images['candidate'], manifest['commit'], 'release-success.json')
        if code != 0 or success['status'] != 'succeeded':
            raise RuntimeError('Healthy release did not succeed')
        local.image_script(manifest['images']['candidate']['tag'], 'smoke.py')
        bad_image = images['candidate'].split('@')[0] + '@sha256:' + '0' * 64
        code, failure = invoke_release(bad_image, manifest['commit'], 'release-rollback.json')
        if code == 0 or failure['status'] != 'rolled_back' or failure['previous_image'] != images['candidate']:
            raise RuntimeError('Failed candidate did not restore the exact healthy digest')
        local.image_script(manifest['images']['candidate']['tag'], 'smoke.py')
        if before != schema_signature():
            raise RuntimeError('Release unexpectedly changed the database schema')
        summary = {'commit': manifest['commit'], 'previous_commit': manifest['previous_commit'],
                   'run_url': f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
                   'environment': 'hosted-runner-k3d', 'registry': 'ECR' if args.ecr else 'local',
                   'images': images, 'healthy_release': True, 'failed_release_rolled_back': True,
                   'authenticated_smoke_after_each': True, 'database_schema_unchanged': True,
                   'finished_at': datetime.now(timezone.utc).isoformat()}
        (EVIDENCE / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    finally:
        if cluster_attempted:
            command('k3d', 'cluster', 'delete', local.CLUSTER)
        if registry_created:
            command('k3d', 'registry', 'delete', 'alex-ci-registry')
        if args.ecr:
            command('docker', 'logout', args.ecr.split('/')[0])


if __name__ == '__main__':
    main()
