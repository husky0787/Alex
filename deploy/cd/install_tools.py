"""Install the matching kubectl minor with the official published checksum."""
import hashlib
import os
from pathlib import Path
import urllib.request

base = 'https://dl.k8s.io/release/v1.35.9/bin/linux/amd64/kubectl'
with urllib.request.urlopen(base + '.sha256', timeout=60) as response:
    expected = response.read().decode().strip()
with urllib.request.urlopen(base, timeout=60) as response:
    data = response.read()
if hashlib.sha256(data).hexdigest() != expected:
    raise SystemExit('kubectl checksum mismatch')
target = Path(os.environ['RUNNER_TEMP']) / 'alex-cd-tools'
target.mkdir(exist_ok=True)
binary = target / 'kubectl'
binary.write_bytes(data)
binary.chmod(0o755)
with open(os.environ['GITHUB_PATH'], 'a', encoding='utf-8') as output:
    output.write(str(target) + '\n')
