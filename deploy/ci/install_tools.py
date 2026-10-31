"""Install the versioned k3d Linux binary after checking its release checksum."""
import hashlib
import os
from pathlib import Path
import urllib.request

VERSION = 'v5.9.0'
BASE = f'https://github.com/k3d-io/k3d/releases/download/{VERSION}/'
target = Path(os.environ['RUNNER_TEMP']) / 'alex-tools'
target.mkdir(parents=True, exist_ok=True)
checksums = urllib.request.urlopen(BASE + 'checksums.txt', timeout=60).read().decode()
expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip('*') == 'k3d-linux-amd64')
data = urllib.request.urlopen(BASE + 'k3d-linux-amd64', timeout=60).read()
if hashlib.sha256(data).hexdigest() != expected:
    raise SystemExit('k3d release checksum mismatch')
binary = target / 'k3d'
binary.write_bytes(data)
binary.chmod(0o755)
with open(os.environ['GITHUB_PATH'], 'a') as stream:
    stream.write(str(target) + '\n')
