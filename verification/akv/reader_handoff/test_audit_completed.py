from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_completed as a


class CompletedAuditTest(unittest.TestCase):
    def test_cannot_reclassify_other_failures_or_unfinished_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'run').mkdir()
            (root/'replay').mkdir()
            for i,row in enumerate(({},dict(state='RUNNING'),dict(state='PASS'),
                                    dict(state='FAIL',child_pid=None,running_exit_code=0,error='different bug'))):
                with patch.object(a.s,'read_json',return_value=row),self.assertRaises(ValueError):
                    a.audit(root/'run',root/'replay',root/('audit'+str(i)))

    def test_preserves_original_failure_and_checks_actual_inputs(self):
        text=Path(a.__file__).read_text()
        for item in ("original_worker_state='FAIL'","clean_original_worker_pass=False",'new_simulation=False',
                     'original_checker.check_log(',"s.check_result(protocol",'waves=check_cycles(',
                     "s.verify_pins(pins)","metadata['fsdb']",'successful_commit_words=4,fault_commit_words=0'):
            self.assertIn(item,text)


if __name__=='__main__':
    unittest.main()
