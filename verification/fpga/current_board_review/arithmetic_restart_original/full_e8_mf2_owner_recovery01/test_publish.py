"""Actual small publication tests, including cancellation during report I/O."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import recovery as worker


class PublicationTests(unittest.TestCase):
    def test_abort_during_strict_write(self):
        abort = threading.Event()
        original = worker.save
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            def save(path, value):
                original(path, value)
                if path.name == 'strict.json':
                    abort.set()
            with patch.object(worker, 'save', save):
                with self.assertRaisesRegex(ValueError, 'strict report'):
                    worker.finalize(out, {'test': 1}, {'status': 'TEST'}, abort)
            self.assertTrue((out / 'strict.json').exists())
            self.assertFalse((out / 'result.json').exists())

    def test_abort_during_strict_hash(self):
        abort = threading.Event()
        original = worker.sha
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            def sha(path):
                value = original(path)
                abort.set()
                return value
            with patch.object(worker, 'sha', sha):
                with self.assertRaisesRegex(ValueError, 'strict report'):
                    worker.finalize(out, {'test': 1}, {'status': 'TEST'}, abort)
            self.assertFalse((out / 'result.json').exists())

    def test_pending_real_sigterm(self):
        # Subprocess exits with termination blocked; no test contaminates its parent mask.
        code = '''
import os,signal,threading
from pathlib import Path
import recovery as w
signal.pthread_sigmask(signal.SIG_BLOCK, w.SIGNALS)
os.kill(os.getpid(), signal.SIGTERM)
try:
    w.publish(Path('.'), {'status':'TEST'}, threading.Event())
except ValueError as error:
    assert 'Abort before terminal' in str(error)
    assert not Path('result.json').exists()
else:
    raise AssertionError('Pending real signal accepted')
'''
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPATH=str(worker.HERE), PYTHONDONTWRITEBYTECODE='1')
            child = subprocess.run([sys.executable, '-B', '-c', code], cwd=tmp, env=env, timeout=20,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(child.returncode, 0, child.stdout.decode())

    def test_normal_publication(self):
        code = '''
from pathlib import Path
import threading,json
import recovery as w
w.finalize(Path('.'), {'complete':True}, {'status':'TEST_ONLY'}, threading.Event())
assert json.loads(Path('result.json').read_text())['strict_sha256']==w.sha(Path('strict.json'))
'''
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPATH=str(worker.HERE), PYTHONDONTWRITEBYTECODE='1')
            child = subprocess.run([sys.executable, '-B', '-c', code], cwd=tmp, env=env, timeout=20,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(child.returncode, 0, child.stdout.decode())


if __name__ == '__main__':
    unittest.main(verbosity=2)

