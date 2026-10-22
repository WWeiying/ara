import json
from unittest import TestCase,main
from unittest.mock import patch
import collect_sv39_fault_alternating771_completed as q

class DesignBindingTests(TestCase):
    def test_actual_design_not_test(self):
        actual=q.design_vdb()
        bits=json.loads((q.csr.old.p.BASE/'combined-bits.json').read_bytes())
        self.assertNotIn(actual,bits['tests'])
        self.assertTrue(actual.endswith('/simv.vdb'))
    def test_ledger_drift(self):
        with patch.object(q.life,'digest',return_value='0'*64):
            with self.assertRaises(ValueError):q.design_vdb()

if __name__=='__main__':main()
