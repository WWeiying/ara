import unittest
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from early_guard import failure, EarlyGuard


class GuardTest(unittest.TestCase):
    def test_response(self):
        normal='[ARA_CONTRACT_TRACE] cycle=1 req=1/1 fire=1 resp=1/1 fire=1 exc=0 errors=0000000'
        self.assertIsNone(failure(normal))
        self.assertEqual(failure(normal.replace('exc=0','exc=1')),'unexpected_architectural_exception')
        self.assertEqual(failure(normal.replace('errors=0000000','errors=0000010')),'contract_monitor_error')
        self.assertIsNone(failure(normal.replace('resp=1/1 fire=1','resp=0/1 fire=0').replace('exc=0','exc=1')))
        self.assertIsNone(failure('PREFILL_RESULT errors=0'))

    def test_owned_child_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);log=out/'console.log'
            child=subprocess.Popen(['/usr/bin/sleep','30'])
            owner=SimpleNamespace(out=out,state=dict(child_pid=child.pid,state='RUNNING'))
            try:
                with EarlyGuard(owner,log,lambda p,v:p.write_text(json.dumps(v))):
                    log.write_text('[ARA_CONTRACT_TRACE] resp=1/1 fire=1 exc=1 errors=0000000\n')
                    self.assertEqual(child.wait(timeout=5),-15)
                self.assertEqual(json.loads((out/'early-failure.json').read_text())['reason'],
                                 'unexpected_architectural_exception')
            finally:
                if child.poll() is None: child.kill();child.wait()


if __name__=='__main__':unittest.main()
