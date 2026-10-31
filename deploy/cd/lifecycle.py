"""Durable ownership and bounded lifecycle for exactly one disposable EKS stack."""
import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.local/cd'
EVIDENCE = STATE / 'evidence'
STACK = 'alex-cd-window'
PURPOSE = 'manual-eks-cd'


class AwsError(RuntimeError):
    pass


def aws(service, operation, **kwargs):
    result = subprocess.run(['aws', service, operation, '--region', 'us-east-1',
        '--cli-input-json', json.dumps(kwargs), '--output', 'json', '--no-cli-pager'],
        text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise AwsError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


def stack():
    try:
        return aws('cloudformation', 'describe-stacks', StackName=STACK)['Stacks'][0]
    except AwsError as exc:
        if 'ValidationError' in str(exc) and f'Stack with id {STACK} does not exist' in str(exc):
            return None
        raise


def owner(value):
    tags = {t['Key']: t['Value'] for t in value.get('Tags', [])}
    if tags.get('Project') != 'alex' or tags.get('Purpose') != PURPOSE:
        raise ValueError('Refusing to operate on an unowned stack')
    if not re.fullmatch(r'[0-9]+-[0-9]+', tags.get('ReleaseId', '')):
        raise ValueError('Invalid stack release ownership')
    datetime.fromisoformat(tags['ExpiresAt']).astimezone(timezone.utc)
    return tags


def recoverable(value, completed_run=None, now=None):
    tags = owner(value)
    if completed_run is not None:
        return tags['ReleaseId'].split('-')[0] == str(completed_run)
    return datetime.fromisoformat(tags['ExpiresAt']) <= (now or datetime.now(timezone.utc))


def evidence(name, value):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def wait_terminal(timeout=3300):
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        value = stack()
        if value is None:
            return None
        status = value['StackStatus']
        if status != previous:
            print('Stack status:', status, flush=True)
            previous = status
        if not status.endswith('_IN_PROGRESS'):
            return value
        time.sleep(20)
    raise TimeoutError('Stack did not reach a terminal state; recovery must continue')


def preflight_roles():
    roles = [os.environ['ALEX_CD_NODE_ROLE'], os.environ['ALEX_CD_CLUSTER_ROLE']]
    actions = ['iam:GetRole', 'iam:ListAttachedRolePolicies']
    response = aws('iam', 'simulate-principal-policy',
        PolicySourceArn=os.environ['ALEX_CD_CF_ROLE_ARN'], ActionNames=actions, ResourceArns=roles)
    decisions = {}
    for item in response['EvaluationResults']:
        for resource in item.get('ResourceSpecificResults', [item]):
            decisions[(item['EvalActionName'], resource['EvalResourceName'])] = (
                resource.get('EvalResourceDecision', item['EvalDecision']) == 'allowed')
    missing = [f'{action} on {role.rsplit("/", 1)[-1]}' for action in actions for role in roles
               if not decisions.get((action, role), False)]
    if missing:
        raise RuntimeError('CloudFormation role prerequisites denied or missing before provisioning: ' + ', '.join(missing))
    if any(item['EvalDecision'] != 'allowed' for item in response['EvaluationResults']):
        raise RuntimeError('Aggregate IAM role-inspection authorization denied before provisioning')
    evidence('preflight.json', {'role_inspection_allowed': True, 'roles': ['node', 'cluster'],
        'actions': actions, 'limitation': 'IAM simulation; live provisioning still verifies service behavior'})
    print('IAM role-inspection prerequisites allowed for both dedicated roles', flush=True)


def create(release_id):
    if stack() is not None:
        raise RuntimeError('An earlier stack remains; recover it before releasing')
    if not re.fullmatch(r'[0-9]+-[0-9]+', release_id):
        raise ValueError('Invalid release ID')
    preflight_roles()
    with urllib.request.urlopen('https://checkip.amazonaws.com', timeout=20) as response:
        address = ipaddress.IPv4Address(response.read().decode().strip())
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    zones = sorted(z['ZoneName'] for z in aws('ec2', 'describe-availability-zones',
        Filters=[{'Name': 'state', 'Values': ['available']}, {'Name': 'zone-type', 'Values': ['availability-zone']}])['AvailabilityZones']
        if z['ZoneId'] != 'use1-az3')
    if len(zones) < 2:
        raise ValueError('Two supported EKS availability zones required')
    params = {'RunnerCidr': f'{address}/32', 'ClusterRole': os.environ['ALEX_CD_CLUSTER_ROLE'],
              'NodeRole': os.environ['ALEX_CD_NODE_ROLE'], 'ReleaseRole': os.environ['ALEX_CD_ROLE_ARN'],
              'ZoneA': zones[0], 'ZoneB': zones[1]}
    tags = {'Project': 'alex', 'Purpose': PURPOSE, 'ReleaseId': release_id,
            'ExpiresAt': expires.isoformat()}
    aws('cloudformation', 'create-stack', StackName=STACK,
        TemplateBody=(ROOT / 'deploy/cd/stack.yaml').read_text(encoding='utf-8'),
        RoleARN=os.environ['ALEX_CD_CF_ROLE_ARN'],
        Parameters=[{'ParameterKey': k, 'ParameterValue': v} for k, v in params.items()],
        Tags=[{'Key': k, 'Value': v} for k, v in tags.items()],
        TimeoutInMinutes=50, OnFailure='DELETE', ClientRequestToken='alex-' + release_id)
    value = wait_terminal()
    if value is None or value['StackStatus'] != 'CREATE_COMPLETE':
        raise RuntimeError('EKS creation failed; inspect CloudFormation events and cleanup')
    owner(value)
    STATE.mkdir(parents=True, exist_ok=True)
    subprocess.run(['aws', 'eks', 'update-kubeconfig', '--region', 'us-east-1', '--name', STACK,
        '--alias', STACK, '--kubeconfig', str(STATE / 'kubeconfig')], check=True)
    evidence('environment.json', {'environment': 'AWS EKS', 'release_id': release_id,
        'commit': os.environ['GITHUB_SHA'], 'source_ci_run': os.environ['SOURCE_CI_RUN'],
        'expires_at': expires.isoformat(), 'fixtures': True})


def delete_images(release_id):
    # This dedicated repository contains only release images; delete by owned tags,
    # never by digest (a digest can have tags belonging to multiple releases).
    repository = os.environ['ALEX_CD_REPOSITORY'].split('/')[-1]
    if repository != 'alex-cd-api':
        raise ValueError('Unexpected ECR repository')
    tags = [{'imageTag': f'cd-{release_id}-{name}'} for name in ('baseline', 'candidate')]
    result = aws('ecr', 'batch-delete-image', repositoryName=repository, imageIds=tags)
    failures = [f for f in result.get('failures', []) if f['failureCode'] != 'ImageNotFound']
    if failures:
        raise RuntimeError('Release image cleanup failed: ' + json.dumps(failures))


def cleanup(release_id=None, completed_run=None, completed_attempt=None, expired=False):
    value = stack()
    selected = release_id
    if completed_run is not None:
        if not re.fullmatch(r'[0-9]+', str(completed_run)) or not re.fullmatch(r'[0-9]+', str(completed_attempt)):
            raise ValueError('Recovery requires the completed run ID and attempt')
        selected = f'{completed_run}-{completed_attempt}'
    if value:
        tags = owner(value)
        if release_id and tags['ReleaseId'] != release_id:
            raise ValueError('Stack belongs to another release; refusing cleanup')
        if completed_run and tags['ReleaseId'] != selected:
            print('Stack belongs to a different run attempt; leaving it intact')
            delete_images(selected)
            return
        if not release_id and not recoverable(value, completed_run if not expired else None):
            print('No eligible interrupted/expired environment')
            return
        selected = tags['ReleaseId']
        # Do not race a CloudFormation create/rollback. Its state survives the runner.
        value = wait_terminal()
        if value and value['StackStatus'] != 'DELETE_COMPLETE':
            if owner(value)['ReleaseId'] != selected:
                raise ValueError('Stack ownership changed')
            aws('cloudformation', 'delete-stack', StackName=value['StackId'],
                RoleARN=os.environ['ALEX_CD_CF_ROLE_ARN'])
            final = wait_terminal()
            if final and final['StackStatus'] != 'DELETE_COMPLETE':
                raise RuntimeError('Cleanup incomplete; stack status ' + final['StackStatus'])
    if selected:
        delete_images(selected)
    # DescribeCluster is an independent check, including an orphaned cluster when
    # the expected CloudFormation stack is absent. Never delete an unowned orphan.
    try:
        aws('eks', 'describe-cluster', name=STACK)
    except AwsError as exc:
        if 'ResourceNotFoundException' not in str(exc):
            raise
    else:
        raise RuntimeError('EKS cluster still exists; cleanup is not complete')
    evidence('cleanup.json', {'release_id': selected, 'stack_absent': True,
        'cluster_absent': True, 'release_tags_removed': bool(selected),
        'checked_at': datetime.now(timezone.utc).isoformat()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'create', 'cleanup', 'recover'])
    parser.add_argument('--release-id')
    parser.add_argument('--completed-run')
    parser.add_argument('--completed-attempt')
    args = parser.parse_args()
    if args.action == 'preflight':
        preflight_roles()
    elif args.action == 'create':
        create(args.release_id)
    elif args.action == 'cleanup':
        if not args.release_id:
            parser.error('cleanup requires exact release ownership')
        cleanup(release_id=args.release_id)
    else:
        cleanup(completed_run=args.completed_run, completed_attempt=args.completed_attempt, expired=not args.completed_run)


if __name__ == '__main__':
    main()
