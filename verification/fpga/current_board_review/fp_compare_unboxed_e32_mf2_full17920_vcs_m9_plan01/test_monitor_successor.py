"""Only the two reviewed monitor defects; synthetic run, no simulator."""
from contextlib import ExitStack
import tempfile
import threading
import unittest
from unittest.mock import patch
from scope import *
import replay_successor02 as r

LINE='RVV_FP_COMPARE_DETAIL op=4 seed=1 vl=16 mask=3 sticky=1 expected_flags=17 actual_flags=1 errors=2\n'

class Tests(unittest.TestCase):
    def test_actual_run_selects_local_hook(self):
        r.common.image_context(IMAGE)
        engine=sys.modules['ara_verify.runner']
        baseline=engine.FAIL_RE
        seen=[]
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);root=out/'replay/tests'/NAME
            class FakeRunner:
                def run(inner):
                    seen.append('actual_run_entered_runner')
                    self.assertIsNone(engine.FAIL_RE.search(LINE[:-1]))
                    self.assertIsNone(engine.FAIL_RE.search(LINE.replace('errors=2','errors=0')))
                    for split in range(1,len(LINE)):
                        self.assertIsNone(engine.FAIL_RE.search(LINE[:split]))
                        self.assertIsNotNone(engine.FAIL_RE.search(LINE[:split][-256:]+LINE[split:]))
                    self.assertIsNotNone(engine.FAIL_RE.search('Fatal: base failure'))
                    (root/'work').mkdir(parents=True)
                    cmd=r.monitor_command(root,'/HOST_ONLY_NO_SIMV',NAME)
                    r.durable(root/'command.json',dict(command=cmd,cwd=str(root/'work')))
                    (root/'console.log').write_text(LINE)
                    outcome=engine._run_monitored(cmd,root/'work',root/'console.log',TIMEOUT)
                    self.assertEqual(outcome,(-15,0.2,False,True))
                    raise RuntimeError('HOST_EXPECTED_STOP_AFTER_REAL_RUN_HOOK')
            with ExitStack() as stack:
                stack.enter_context(patch.object(r,'disk_gate',lambda *a:None))
                stack.enter_context(patch.object(r,'approval_gate',lambda *a:{}))
                stack.enter_context(patch.object(r,'service_identity',lambda:{'HOST_only':True}))
                stack.enter_context(patch.object(r.common,'resources',lambda *a:{}))
                stack.enter_context(patch.object(r.common,'image_context',
                    lambda *a:({'simv':'/HOST_ONLY_NO_SIMV'},Path(tmp),(object,object,lambda *a:None,None))))
                stack.enter_context(patch.object(r.worker,'build_options',lambda *a:None))
                stack.enter_context(patch.object(r.worker,'checked_runner',lambda *a:lambda *b:FakeRunner()))
                stack.enter_context(patch.object(r.worker,'engine_hooks',
                    side_effect=AssertionError('Old template hook must never execute')))
                stack.enter_context(patch.object(engine,'_run_monitored',lambda *a:(-15,0.2,False,True)))
                rc=r.run(out,'HOST_ONLY',None,None,None,None)
            self.assertEqual(rc,1)
            self.assertEqual(seen,['actual_run_entered_runner'])
            self.assertIs(engine.FAIL_RE,baseline)
            self.assertEqual(read(root/'child_outcome.unvalidated.json')['returncode'],-15)
            self.assertEqual(read(root/'detail_firstfailure.json')['line'],LINE)
            done=read(out/'complete.json')
            self.assertEqual(done['status'],'NOT_PASS');self.assertIs(done['aborted'],True)
            self.assertIn('HOST_EXPECTED_STOP_AFTER_REAL_RUN_HOOK',done['error'])

    def fixture(self,root):
        (root/'work').mkdir()
        cmd=r.monitor_command(root,'/HOST_ONLY_NO_SIMV',NAME)
        r.durable(root/'command.json',dict(command=cmd,cwd=str(root/'work')))
        abort=threading.Event()
        call=r.monitored(lambda *a:(0,0.1,False,True),abort,{NAME:root},'/HOST_ONLY_NO_SIMV')
        return cmd,abort,call

    def test_missing_console_preserves_numeric_and_abort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cmd,abort,call=self.fixture(root)
            with self.assertRaises(FileNotFoundError):
                call(cmd,root/'work',root/'console.log',TIMEOUT)
            numeric=read(root/'child_outcome.unvalidated.json')
            self.assertIs(type(numeric['returncode']),int);self.assertEqual(numeric['returncode'],0)
            self.assertIs(numeric['failure_seen'],True);self.assertTrue(abort.is_set())
            self.assertIs(numeric['architectural_acceptance'],False)

    def test_detail_write_io_failure_preserves_numeric(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cmd,abort,call=self.fixture(root)
            (root/'console.log').write_text(LINE)
            original=r.durable;order=[]
            def save(path,value):
                order.append(path.name)
                if path.name=='detail_firstfailure.json':raise OSError('HOST_INJECTED_DETAIL_IO')
                return original(path,value)
            with patch.object(r,'durable',save),self.assertRaisesRegex(OSError,'HOST_INJECTED_DETAIL_IO'):
                call(cmd,root/'work',root/'console.log',TIMEOUT)
            self.assertEqual(order,['child_outcome.unvalidated.json','detail_firstfailure.json'])
            self.assertEqual(read(root/'child_outcome.unvalidated.json')['returncode'],0)
            self.assertTrue(abort.is_set())

def main():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    r.durable(HERE/'monitor_host01.json',dict(status='PASS_MONITOR_SUCCESSOR_HOST_NOT_DUT' if result.wasSuccessful() else 'NOT_PASS',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        worker_sha256=sha(HERE/'replay_successor02.py'),test_sha256=sha(Path(__file__)),
        actual_run_hook_exercised=True,old_template_hook_forbidden=True,
        real_filesystem_numeric_first=True,DUT_started=False))
    return int(not result.wasSuccessful())
if __name__=='__main__':raise SystemExit(main())
