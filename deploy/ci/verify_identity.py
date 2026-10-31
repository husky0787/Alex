"""Verify the OIDC role can neither read application secrets nor other ECR repos."""
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    identity = json.loads(subprocess.check_output(['aws','sts','get-caller-identity','--output','json'], text=True))
    expected = ':assumed-role/alex-ci-release/alex-' + os.environ['GITHUB_RUN_ID']
    if not identity['Arn'].endswith(expected):
        raise RuntimeError('Expected the short-lived release role session')
    denied = {}
    probes = {
        'application_secrets': ['secretsmanager','get-secret-value','--secret-id',
            f"arn:aws:secretsmanager:us-east-1:{identity['Account']}:secret:outside-release-fixture"],
        'other_repository': ['ecr','batch-get-image','--repository-name','outside-release-fixture',
                             '--image-ids','imageTag=latest'],
    }
    for name, args in probes.items():
        result = subprocess.run(['aws',*args,'--region','us-east-1','--output','json'],capture_output=True,text=True)
        match = re.search(r'An error occurred \(([^)]+)\)', result.stderr)
        if result.returncode == 0 or not match or match.group(1) not in ('AccessDenied','AccessDeniedException'):
            raise RuntimeError(f'{name}: expected explicit AccessDenied')
        denied[name] = match.group(1)
    path = Path('.local/ci/evidence/identity.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'role_session':identity['Arn'],'denied':denied},indent=2)+'\n')
    print('Short-lived release role confirmed; application secrets and other repositories denied.')


if __name__ == '__main__':
    main()
