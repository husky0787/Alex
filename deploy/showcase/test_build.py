import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_workers import AGENTS, build


class WorkerPackaging(unittest.TestCase):
    def test_every_archive_retains_runtime_and_uses_current_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'runtime.zip'
            with zipfile.ZipFile(runtime, 'w') as archive:
                archive.writestr('agents/__init__.py', b'runtime sentinel')
                archive.writestr('agent.py', b'obsolete reporter')
                archive.writestr('src/obsolete.py', b'obsolete shared module')
            digest = hashlib.sha256(runtime.read_bytes()).hexdigest()
            build(runtime, digest, root / 'out')
            self.assertEqual(hashlib.sha256(runtime.read_bytes()).hexdigest(), digest)
            for name in AGENTS:
                with zipfile.ZipFile(root / 'out' / f'{name}.zip') as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(archive.read('agents/__init__.py'), b'runtime sentinel')
                    self.assertNotEqual(archive.read('agent.py'), b'obsolete reporter')
                    self.assertNotIn('src/obsolete.py', archive.namelist())
                    self.assertIn('src/snapshots.py', archive.namelist())
                    self.assertEqual('planner_queue.py' in archive.namelist(), name == 'planner')

    def test_runtime_checksum_required_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'runtime.zip'
            runtime.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                build(runtime, '0' * 64, root / 'out')
            self.assertFalse((root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
