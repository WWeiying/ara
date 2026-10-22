"""One actual worker-hook short test, synthetic monitor only; no simulator."""
from contextlib import ExitStack
import tempfile
import threading
import unittest
from unittest.mock import patch
from scope import *
import replay as r
LINE='RVV_FP_REDSPECIAL_DETAIL scenario=3 op=0 vl=8 mask=3 frm=0 flags=0 expected_flags=16\n'
class Test(unittest.TestCase):
    def test_actual_run_local_hook_numeric_first(self):
        r.common.image_context(IMAGE);engine=sys.modules['ara_verify.runner'];original_fail=engine.FAIL_RE
        seen=[]
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);root=out/'replay/tests'/NAME
            class FakeRunner:
                def run(self):
                    seen.append('actual_run_hook')
                    for split in range(1,len(LINE)):
                        assert engine.FAIL_RE.search(LINE[:split]) is None
                        assert engine.FAIL_RE.search(LINE[:split][-256:]+LINE[split:]) is not None
                    assert engine.FAIL_RE.search('Fatal: base failure') is not None
                    (root/'work').mkdir(parents=True);cmd=r.base.monitor_command(root,'/HOST_ONLY_NO_SIMV',NAME)
                    r.durable(root/'command.json',dict(command=cmd,cwd=str(root/'work')));(root/'console.log').write_text(LINE)
                    assert engine._run_monitored(cmd,root/'work',root/'console.log',TIMEOUT)==(-15,0.2,False,True)
                    assert read(root/'child_outcome.unvalidated.json')['returncode']==-15
                    assert read(root/'detail_firstfailure.json')['line']==LINE
                    raise RuntimeError('EXPECTED_HOST_STOP_AFTER_ACTUAL_LOCAL_HOOK')
            with ExitStack() as s:
                for obj,name,value in [(r.base,'disk_gate',lambda *a:None),(r.base,'approval_gate',lambda *a:{}),(r.base,'service_identity',lambda:dict(HOST_only=True)),
                    (r.common,'resources',lambda *a:{}),(r.common,'image_context',lambda *a:({'simv':'/HOST_ONLY_NO_SIMV'},Path(tmp),(object,object,lambda *a:None,None))),
                    (r.base.worker,'build_options',lambda *a:None),(r.base.worker,'checked_runner',lambda *a:lambda *b:FakeRunner()),
                    (engine,'_run_monitored',lambda *a:(-15,0.2,False,True))]:s.enter_context(patch.object(obj,name,value))
                self.assertEqual(r.base.run(out,'HOST_ONLY',None,None,None,None),1)
            self.assertEqual(seen,['actual_run_hook']);self.assertIs(engine.FAIL_RE,original_fail)
            self.assertIn('EXPECTED_HOST_STOP',read(out/'complete.json')['error'])
            # Same wrapper, read failure: numeric receipt and abort must preexist.
            missing=out/'missing';(missing/'work').mkdir(parents=True);cmd=r.base.monitor_command(missing,'/HOST_ONLY_NO_SIMV',NAME)
            r.durable(missing/'command.json',dict(command=cmd,cwd=str(missing/'work')));abort=threading.Event()
            call=r.monitored(lambda *a:(17,0.1,False,True),abort,{NAME:missing},'/HOST_ONLY_NO_SIMV')
            with self.assertRaises(FileNotFoundError):call(cmd,missing/'work',missing/'console.log',TIMEOUT)
            self.assertEqual(read(missing/'child_outcome.unvalidated.json')['returncode'],17);self.assertTrue(abort.is_set())
if __name__=='__main__':unittest.main()
