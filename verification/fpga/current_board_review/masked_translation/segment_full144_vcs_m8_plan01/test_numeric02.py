"""Exercise real run post-monitor boundary; fake monitor, never a DUT process."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import replay02 as s

def main():
    w=s.base; spec=w.c.specification(); ledger,repo,framework=w.common.image_context(w.IMAGE)
    import ara_verify.runner as engine
    results=[]; real_sha=w.sha
    for rc in (0,17):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td); plan=dict(spec=spec,pins={})
            w.save(out/'plan.json',plan)
            args=SimpleNamespace(out=out,image=w.IMAGE,plan_sha256=real_sha(out/'plan.json'),
                                 review=None,review_sha256=None,authorization=None,authorization_sha256=None)
            monitor_returned=False
            def fake_monitor(*args,**kwargs):
                nonlocal monitor_returned
                monitor_returned=True
                return rc,1.25,False,False
            def broken_metadata_hash(path):
                if monitor_returned and Path(path).name=='command.json':
                    raise OSError('Injected post-monitor command hash read failure')
                return real_sha(path)
            with patch.object(w,'validate',lambda *x:None),patch.object(w,'entry',lambda *x:{}),\
                 patch.object(w,'owner',lambda:dict(host_test=True)),\
                 patch.object(w.common,'resources',lambda *x:dict(host_test=True)),\
                 patch.object(w.common,'image_context',lambda *x:(ledger,repo,framework)),\
                 patch.object(engine,'_run_monitored',fake_monitor),patch.object(w,'sha',broken_metadata_hash):
                exitcode=s.run02(args)
            numeric=w.read(out/'replay'/w.NAME/'monitor_numeric.unvalidated.json')
            terminal=w.read(out/'complete.json')
            w.require(exitcode==1 and terminal['status']=='NOT_PASS' and terminal['aborted'] and
                      'Injected post-monitor command hash' in terminal['error'] and
                      numeric['returncode']==rc and type(numeric['returncode']) is int and
                      numeric['architectural_acceptance'] is False,'Actual boundary lost numeric outcome')
            results.append(dict(fake_monitor_rc=rc,persisted_numeric=numeric,actual_run_wrapper_exit=exitcode,
                                terminal=terminal))
    w.save(w.HERE/'numeric_host02.json',dict(status='PASS_REAL_RUN_BOUNDARY_HOST_ONLY',cases=results,
        no_simulator_process=True,pins={str(w.HERE/n):real_sha(w.HERE/n) for n in ('replay.py','replay02.py','test_numeric02.py')}))
    print('PASS_REAL_RUN_BOUNDARY_HOST_ONLY 2')

if __name__=='__main__':main()
