"""Build two source revisions and export only allowlisted immutable CI artifacts."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.local/ci/artifacts'
PYTHON_IMAGE = 'docker.io/library/python:3.12-slim@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b'


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    commit = run('git', 'rev-parse', 'HEAD')
    previous = run('git', 'rev-parse', 'HEAD^')
    if os.environ.get('GITHUB_SHA') != commit:
        raise SystemExit('Checkout must exactly match workflow commit')
    manifest = {'commit': commit, 'previous_commit': previous, 'base_image': PYTHON_IMAGE, 'images': {}}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        archive = root / 'parent.tar'
        subprocess.run(['git', 'archive', previous, 'backend', '-o', str(archive)], check=True)
        with tarfile.open(archive) as stream:
            stream.extractall(root, filter='data')
        for name, revision, source in [('baseline', previous, root / 'backend'),
                                       ('candidate', commit, ROOT / 'backend')]:
            tag = f'alex-api:{revision}'
            subprocess.run(['docker', 'build', '--platform=linux/amd64',
                            '--build-arg', 'PYTHON_IMAGE=' + PYTHON_IMAGE,
                            '--label', f'org.opencontainers.image.revision={revision}',
                            '-f', str(source / 'api/Dockerfile'), '-t', tag, str(source)], check=True)
            target = OUT / f'{name}.tar'
            subprocess.run(['docker', 'save', '-o', str(target), tag], check=True)
            manifest['images'][name] = {'tag': tag, 'commit': revision, 'file': target.name,
                                      'sha256': sha256(target),
                                      'id': run('docker', 'image', 'inspect', '--format={{.Id}}', tag)}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
