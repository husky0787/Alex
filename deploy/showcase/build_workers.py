"""Package showcase workers using a hash-verified Linux Reporter runtime.

The runtime is built with backend/reporter/package_docker.py and its locked
dependencies. Source overlays never copy .env, local environments or test data.
Each resulting worker must pass an actual Lambda import probe before use.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ('planner', 'tagger', 'reporter', 'charter', 'retirement')
MODULES = ('lambda_handler.py', 'agent.py', 'templates.py', 'observability.py', 'judge.py')


def build(runtime, digest, output):
    if hashlib.sha256(runtime.read_bytes()).hexdigest() != digest:
        raise ValueError('Runtime checksum mismatch')
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'runtime_sha256': digest, 'workers': {}}
    with zipfile.ZipFile(runtime) as original:
        for name in AGENTS:
            target = output / f'{name}.zip'
            with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
                for item in original.infolist():
                    path = Path(item.filename)
                    if item.filename in MODULES or path.parts[0] in ('src', 'research_chain'):
                        continue
                    archive.writestr(copy.copy(item), original.read(item.filename))
                for module in MODULES:
                    source = ROOT / 'backend' / name / module
                    if source.is_file():
                        archive.write(source, module)
                for source, prefix in ((ROOT / 'backend/database/src', 'src'),
                                       (ROOT / 'backend/research/research_chain', 'research_chain')):
                    for path in sorted(source.rglob('*.py')):
                        archive.write(path, str(Path(prefix) / path.relative_to(source)))
                if name == 'planner':
                    archive.write(ROOT / 'deploy/showcase/planner_queue.py', 'planner_queue.py')
            with zipfile.ZipFile(target) as archive:
                size = sum(item.file_size for item in archive.infolist())
            if size >= 250 * 1024 * 1024:
                raise ValueError(f'{name} exceeds Lambda uncompressed size limit')
            manifest['workers'][name] = {'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                                         'zip_bytes': target.stat().st_size, 'uncompressed_bytes': size}
            print(f'Packaged {name}', flush=True)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-zip', type=Path, required=True)
    parser.add_argument('--runtime-sha256', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.local/showcase/workers')
    args = parser.parse_args()
    build(args.runtime_zip, args.runtime_sha256, args.output)
