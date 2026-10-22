"""Offline launch-gate negatives. No image build, reference, or DUT launch."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import replay as r


class Gates(unittest.TestCase):
    def test_exact_ten_source_groups(self):
        cases=r.scope()
        self.assertEqual(len(cases),10)
        self.assertEqual([len(c['source_names']) for c in cases],[4]*9+[2])
        self.assertTrue(all(c['timeout_s']==10800 for c in cases))
        self.assertTrue(all(c['id']==c['original_name'] for c in cases))
        self.assertEqual(len({n for c in cases for n in c['source_names']}),38)

    def test_console_positive(self):
        r.console_gate('NEGATIVE_STRIDE_BATCH_PASS\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n')

    def test_console_contradictions(self):
        good='NEGATIVE_STRIDE_BATCH_PASS\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
        for bad in ('NEGATIVE_STRIDE_BATCH_FAIL','BOARD_REPLAY_MISMATCH','RVV_NEGATIVE_FAIL','FATAL','ABORT'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):r.console_gate(good+bad)

    def test_missing_duplicate_oracle(self):
        for s in ('Core Test *** SUCCESS *** (tohost = 0)\n$finish',
                  'NEGATIVE_STRIDE_BATCH_PASS\nNEGATIVE_STRIDE_BATCH_PASS\nCore Test *** SUCCESS *** (tohost = 0)\n$finish',
                  'NEGATIVE_STRIDE_BATCH_PASS\n'):
            with self.assertRaises(ValueError):r.console_gate(s)

    def test_numeric_child_positive_and_negatives(self):
        good=dict(returncode=0,status='PASS',reason=None)
        r.outcome_gate(good)
        for k,v in [('returncode',True),('returncode',False),('returncode',17),('returncode',None),
                    ('status','FAIL'),('status','CANCELLED'),('reason','postcheck error')]:
            bad=dict(good);bad[k]=v
            with self.assertRaises(ValueError):r.outcome_gate(bad)

    def test_preserved_numeric_outcome_before_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            for rc in (17,0):
                path=Path(d)/f'raw{rc}.json'
                raw=dict(returncode=rc,status='FAIL' if rc else 'PASS',reason=None,architectural_acceptance=False)
                r.save(path,raw)
                try:
                    r.outcome_gate(raw)
                    raise ValueError('deliberate postcheck failure')
                except ValueError:pass
                self.assertEqual(json.loads(path.read_text()),raw)
                with self.assertRaises(FileExistsError):r.save(path,dict(returncode=1))

    def test_late_abort(self):
        abort=threading.Event();r.aftercheck_gate(abort);abort.set()
        with self.assertRaises(ValueError):r.aftercheck_gate(abort)

    def test_exact_scope_gate(self):
        out=Path('/synthetic/owned')
        cases=[dict(id='one',sha256='elf')]
        good=dict(status='PREPARED_NOT_RUN',cases=cases,jobs=2,image=str(r.IMAGE),image_sha256=r.IMAGE_SHA,
                  timeout_s=10800,check_timeout_s=900,worker_bound_s=58500,service_bound_s=59400,
                  unit=r.UNIT,no_retry=True,no_build=True,no_fsdb=True,reserved_slots=0,pins={})
        def digest(path):return 'plan' if Path(path)==out/'plan.json' else r.IMAGE_SHA
        with patch.object(r,'scope',return_value=cases),patch.object(r,'sha',side_effect=digest),patch.object(r.common.base,'verify_pins'):
            r.validate(good,'plan',out)
            for k,v in [('jobs',4),('timeout_s',10801),('image','M7'),('image_sha256','wrong'),
                        ('no_retry',False),('reserved_slots',True),('cases',[])]:
                bad=copy.deepcopy(good);bad[k]=v
                with self.subTest(k=k),self.assertRaises(ValueError):r.validate(bad,'plan',out)
            with self.assertRaises(ValueError):r.validate(good,'stale',out)


if __name__=='__main__':unittest.main(verbosity=2)
