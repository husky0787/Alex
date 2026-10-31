"""Run one explicit Terraform operation with temporary CLI credentials in memory.

Plans/logs may contain secrets; output is saved privately. This wrapper neither
reviews a plan nor authorizes apply/destroy. Follow the ownership runbook first.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def run(directory, operation, arguments, profile):
    credentials = json.loads(subprocess.check_output(
        ['aws', 'configure', 'export-credentials', '--profile', profile, '--region', 'us-east-1', '--format', 'process'],
        text=True, encoding='utf-8'))
    environment = dict(os.environ)
    environment.pop('AWS_PROFILE', None)
    environment.pop('AWS_SESSION_TOKEN', None)
    environment.update(AWS_ACCESS_KEY_ID=credentials['AccessKeyId'], AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],
                       AWS_DEFAULT_REGION='us-east-1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    if credentials.get('SessionToken'):
        environment['AWS_SESSION_TOKEN'] = credentials['SessionToken']
    path = ROOT / '.local/showcase' / f'{directory}-{operation}-private.log'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as stream:
        result = subprocess.run(['terraform', f'-chdir={ROOT / "terraform" / directory}', operation, *arguments],
                                env=environment, stdout=stream, stderr=subprocess.STDOUT)
    print(json.dumps({'directory': directory, 'operation': operation, 'exit_code': result.returncode,
                      'private_log': str(path)}))
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='alex-task09')
    parser.add_argument('directory', choices=['2_sagemaker', '3_ingestion', '11_showcase'])
    parser.add_argument('operation', choices=['init', 'validate', 'plan', 'apply', 'destroy'])
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    raise SystemExit(run(args.directory, args.operation, args.arguments, args.profile))
