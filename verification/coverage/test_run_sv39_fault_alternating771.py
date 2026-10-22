"""Focused runner/lifecycle rejection tests; no live simulation access."""
import unittest
import run_sv39_fault_alternating771 as r

class RunnerTests(unittest.TestCase):
    def test_command(self):
        cmd=r.command(r.life.OUT/'unit-unused')
        self.assertIn('+NO_FSDB',cmd);self.assertNotIn('-ucli',cmd)
        self.assertEqual(cmd[0],str(r.life.IMAGE));self.assertEqual(r.BUDGET,600)
    def test_baseline(self):
        b=r.life.read_bound(r.p.BASE/'admission-manifest.json',r.p.BASE_SHA)
        self.assertTrue(b['coverage_admitted']);self.assertEqual(r.p.BASE_SHA,
          'ad9e01dcd0ea3ef442d7f28934bf1695dca61c7b6d1c7580bd2a49f0c2569860')
    def test_wrong_baseline_pin(self):
        with self.assertRaises(Exception):r.life.read_bound(r.p.BASE/'admission-manifest.json','a'*64)
    def fixture(self):
        result=[]
        for i in range(8):
            base=dict(trans_id='0',order=str(i),cycle=str(i*3),insn='%x'%(0x07 if i%2==0 else 0x27),trap='0')
            result.extend([dict(base,event='arch_start'),dict(base,event='cvx_req'),
              dict(base,event='cvx_resp',trap='1',order='-1')])
        return result
    def test_lifecycle(self):self.assertEqual(r.lifecycle(self.fixture(),[],[7,39])['requests'],8)
    def test_extra_response(self):
        x=self.fixture();x.append(x[-1])
        with self.assertRaises(ValueError):r.lifecycle(x,[],[7,39])
    def test_wrong_owner(self):
        x=self.fixture();x[1]['trans_id']='1'
        with self.assertRaises(ValueError):r.lifecycle(x,[],[7,39])
    def test_nonexception(self):
        x=self.fixture();x[-1]['trap']='0'
        with self.assertRaises(ValueError):r.lifecycle(x,[],[7,39])
    def test_wrong_opcode(self):
        x=self.fixture();x[0]['insn']='57';x[1]['insn']='57'
        with self.assertRaises(ValueError):r.lifecycle(x,[],[7,39])

if __name__=='__main__':unittest.main()
