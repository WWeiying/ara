import unittest
from pathlib import Path
import run_csr_cause_wlrl788 as r

class RunnerTests(unittest.TestCase):
    def test_command(self):
        command=r.command(r.life.OUT/'cause-unlaunched-test')
        self.assertIn('+PRELOAD='+str(r.ELF),command)
        self.assertIn('+TESTCASE='+r.NAME,command)
        self.assertEqual(command[-3:],['-ucli','-do',str(r.PROBE)])
        self.assertIn('+NO_FSDB',command)

    def test_reference(self):
        pre=r.life.read_bound(r.PRE/'preflight-manifest.json',r.PRE_SEAL)
        reference=r.reference(pre)
        self.assertEqual(r.oracle.validate(reference,pre['symbols']),pre['validation'])
        self.assertEqual(len(reference),664)

    def test_scope(self):
        with self.assertRaises(ValueError):r.manifest(Path('/tmp/not-approved'))

    def test_invalid_service(self):
        with self.assertRaises(ValueError):r.manifest(r.life.OUT/'unlaunched-test','x.service')

if __name__=='__main__':unittest.main()
