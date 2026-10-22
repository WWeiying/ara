"""Reuse already-reviewed runtime negatives with this actual case identity."""
import copy
import sys
import types
import unittest
from pathlib import Path
sys.dont_write_bytecode=True
import replay as app
c=app.checker
prior=c.load('zero16_prior_runtime_tests',app.HERE.parent/'negative_stride_store_vcs_m6_plan01/test_host.py')
bridge=types.SimpleNamespace(**vars(app))
bridge.checked_runner=app.checked_runner
bridge.durable_monitor=app.durable_monitor
bridge.quiesce_deadline=app.frozen.quiesce_deadline
bridge.worker=app.frozen.worker
prior.app=bridge

class Runtime(prior.Host):
    def test_parent_early_postcheck_preserves_rc0_and17(self):
        import ara_verify.runner as engine
        import threading
        from unittest.mock import patch
        for rc in (0,17):
            for name in ('monitor_numeric.unvalidated.json','monitor_outcome.unvalidated.json'):
                p=self.root/name
                if p.exists():p.unlink()
            root=self.root
            class Parent:
                def _run_test(self,*args):
                    engine._run_monitored(['fake'],root/'work',root/'console.log',app.TIMEOUT)
                    raise ValueError('actual parent early postcheck')
            abort=threading.Event()
            with patch.object(engine,'_run_monitored',return_value=(rc,1.25,False,False)):
                with self.assertRaisesRegex(ValueError,'early postcheck'):
                    app.checked_runner(Parent,abort,lambda _:None)()._run_test(None,None)
            self.assertEqual(c.read(root/'monitor_numeric.unvalidated.json')['returncode'],rc)
            self.assertFalse(c.read(root/'monitor_numeric.unvalidated.json')['architectural_acceptance'])
            self.assertTrue(abort.is_set())

    def setUp(self):
        super().setUp()
        (self.root/'console.log').write_text('ZERO_STRIDE_ORIGINAL16_PASS cases=16 faults=12 errors=0\n'+c.common.SUCCESS+'\n$finish\n')
    def test_full16_plan_budget_and_fresh_disk(self):
        c.reference_pins()
        case,spec=app.scope();pins=dict(c.read(c.REF/'evidence_pins02.json'))
        pins[str(app.HERE/'replay.py')]=c.sha(app.HERE/'replay.py')
        p=dict(image=str(app.IMAGE),image_sha256=app.IMAGE_SHA,case=case,spec=spec,jobs=1,
               timeout_s=10800,worker_timeout_s=12000,service_timeout_s=12600,unit=app.UNIT,
               no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
               reference_ready_sha256=app.READY_SHA,review_pins=app.review(),pins=pins)
        app.validate(p,app.IMAGE)
        for k,v in (('timeout_s',10801),('jobs',2),('worker_timeout_s',14000),('no_fsdb',False),('image_sha256','0'*64)):
            bad=copy.deepcopy(p);bad[k]=v
            with self.assertRaises(ValueError):app.validate(bad,app.IMAGE)
        self.write('plan.json',p)
        with self.assertRaisesRegex(ValueError,'Fresh disk plan SHA'):app.disk_gate(self.root,'0'*64,app.IMAGE)

if __name__=='__main__':
    names=['test_runtime_history','test_wrong_seed_preload_testcase_cwd','test_missing_oracle_rawfail_elf',
      'test_durable_monitor_before_parent_checker_throw','test_durable_timeout_numeric','test_abort_during_check_sticky',
      'test_actual_partial_marker_monitor','test_worker_deadline_sticky_publication','test_full16_plan_budget_and_fresh_disk','test_parent_early_postcheck_preserves_rc0_and17']
    suite=unittest.TestSuite(Runtime(n) for n in names)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    pins={str(p):c.sha(p) for p in (Path(__file__),Path(prior.__file__),Path(app.__file__),Path(c.__file__),Path(app.frozen.__file__))}
    c.common.save(app.HERE/'runtime_host02.json',dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST_ONLY',
      tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),pins=pins))
    raise SystemExit(not result.wasSuccessful())

