"""Replace one API image by digest; restore the previous healthy template on failure.

No database migrations, namespace creation or cloud provisioning are performed.
Use an explicit kubeconfig/context and namespace; evidence contains no Pod config.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import urllib.request
from uuid import uuid4


class ReleaseError(RuntimeError):
    pass


def digest_image(image):
    return bool(re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}', image))


def healthy(deployment):
    spec, status = deployment['spec'], deployment.get('status', {})
    desired = spec.get('replicas', 1)
    return (desired > 0 and status.get('observedGeneration', 0) >= deployment['metadata']['generation']
            and all(status.get(field, 0) == desired for field in
                    ('updatedReplicas', 'readyReplicas', 'availableReplicas')))


class Kubernetes:
    def __init__(self, kubeconfig, context, namespace, deployment, timeout):
        self.command = ['kubectl', '--kubeconfig', str(kubeconfig), '--context', context,
                        '--namespace', namespace, '--request-timeout=30s']
        self.deployment, self.timeout = deployment, timeout

    def call(self, *args, data=None):
        result = subprocess.run([*self.command, *args], input=data, text=True, capture_output=True)
        if result.returncode:
            # Preserve diagnostics privately; only safe reasons enter public evidence.
            directory = Path('.local/ci/diagnostics')
            directory.mkdir(parents=True, exist_ok=True)
            diagnostic = directory / f'kubectl-{uuid4().hex}.log'
            diagnostic.write_text(result.stdout + '\n' + result.stderr)
            diagnostic.chmod(0o600)
            reason = re.search(r'Error from server \(([A-Za-z0-9]+)\)', result.stderr)
            detail = reason.group(1) if reason else 'See private diagnostic'
            if args[0] == 'rollout':
                # Rollout status prints progress, not resource bodies or credentials.
                detail = (result.stdout + result.stderr).strip()[-2000:]
            raise ReleaseError(f'kubectl {args[0]} failed (exit {result.returncode}): {detail}; diagnostic={diagnostic}')
        return result.stdout

    def read(self):
        return json.loads(self.call('get', 'deployment', self.deployment, '-o', 'json'))

    def replace_template(self, current, template):
        patch = [{'op': 'test', 'path': '/metadata/resourceVersion',
                  'value': current['metadata']['resourceVersion']},
                 {'op': 'replace', 'path': '/spec/template', 'value': template}]
        # stdin prevents Pod configuration from entering process arguments.
        self.call('patch', 'deployment', self.deployment, '--type=json', '--patch-file=/dev/stdin',
                  data=json.dumps(patch))

    def wait(self):
        self.call('rollout', 'status', 'deployment/' + self.deployment,
                  f'--timeout={self.timeout}s')
        if not healthy(self.read()):
            raise ReleaseError('Deployment has not reached full readiness')


def release(client, image, commit, smoke):
    if not digest_image(image) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ReleaseError('Require an immutable sha256 image and full Git commit')
    current = client.read()
    if not healthy(current):
        raise ReleaseError('Previous deployment is not healthy; refusing an unsafe rollback baseline')
    original = deepcopy(current['spec']['template'])
    containers = original['spec']['containers']
    api = next((c for c in containers if c['name'] == 'api'), None)
    if api is None or not digest_image(api['image']):
        raise ReleaseError('Previous API image must also be pinned by digest')
    smoke()
    candidate = deepcopy(original)
    next(c for c in candidate['spec']['containers'] if c['name'] == 'api')['image'] = image
    candidate.setdefault('metadata', {}).setdefault('annotations', {})['alex.dev/commit'] = commit
    evidence = {'commit': commit, 'image': image, 'previous_image': api['image'],
                'started_at': datetime.now(timezone.utc).isoformat()}
    client.replace_template(current, candidate)
    try:
        client.wait()
        smoke()
        if client.read()['spec']['template'] != candidate:
            raise ReleaseError('Concurrent release replaced the candidate template')
        evidence['status'] = 'succeeded'
    except (ReleaseError, OSError) as exc:
        evidence['failure'] = str(exc)
        try:
            observed = client.read()
            if observed['spec']['template'] != candidate:
                raise ReleaseError('Concurrent template change: refusing to overwrite another release')
            client.replace_template(observed, original)
            client.wait()
            smoke()
            if client.read()['spec']['template'] != original:
                raise ReleaseError('Concurrent release replaced the rollback template')
            evidence['status'] = 'rolled_back'
        except (ReleaseError, OSError) as rollback:
            evidence.update(status='rollback_failed', rollback_failure=str(rollback))
    evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubeconfig', required=True, type=Path)
    parser.add_argument('--context', required=True)
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--deployment', default='api')
    parser.add_argument('--image', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--url', required=True, help='Reachable API base URL for liveness/readiness checks')
    parser.add_argument('--timeout', type=int, default=180, choices=range(30, 601))
    parser.add_argument('--evidence', required=True, type=Path)
    args = parser.parse_args()

    def smoke():
        for endpoint in ('/health', '/ready'):
            with urllib.request.urlopen(args.url.rstrip('/') + endpoint, timeout=15) as response:
                if response.status != 200:
                    raise ReleaseError(f'{endpoint} did not return 200')

    evidence = {'commit': args.commit, 'image': args.image,
                'target': {'context': args.context, 'namespace': args.namespace, 'deployment': args.deployment}}
    try:
        client = Kubernetes(args.kubeconfig, args.context, args.namespace, args.deployment, args.timeout)
        evidence.update(release(client, args.image, args.commit, smoke))
    except (ReleaseError, OSError) as exc:
        evidence.update(status='rejected', failure=str(exc))
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))
    return 0 if evidence['status'] == 'succeeded' else 1


if __name__ == '__main__':
    raise SystemExit(main())
