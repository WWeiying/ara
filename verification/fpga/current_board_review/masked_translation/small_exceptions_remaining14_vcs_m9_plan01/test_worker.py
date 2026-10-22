"""Worker delta only: no replay of source Host suites, Spike or DUT."""
import copy
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
sys.dont_write_bytecode=True
import checker as c
import replay as w
import pinned_service_exit as hook

def main():
    out=c.HERE/'host01';c.require(out.exists() and not (out/'status.json').exists(),'Fresh externally recorded Host invocation')
    results=[]
    def reject(name,fn):
        try:fn()
        except (ValueError,KeyError,TypeError,OSError):results.append(dict(name=name,rejected=True));return
        raise AssertionError('Accepted '+name)
    cases=c.scope()
    c.require(len(cases)==len({x['id'] for x in cases})==14,'Exact fourteen members')
    for x in cases:c.require(c.runtime_case(x)['original_name']==x['id'],'Runtime/source label separation')
    results.append(dict(name='exact14_identity_runtime_labels',positive=True))
    text='SMALL_EXCEPTIONS_14_PASS\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
    c.console_gate(text)
    reject('missing_oracle',lambda:c.console_gate(text.replace('SMALL_EXCEPTIONS_14_PASS\n','')))
    reject('duplicate_oracle',lambda:c.console_gate(text+'SMALL_EXCEPTIONS_14_PASS\n'))
    for token in ('SMALL_EXCEPTIONS_14_FAIL','BOARD_REPLAY_MISMATCH','BOARD_REPLAY_TRAP','RVV_EXCEPTION_FAIL','Fatal: failure'):
        reject('PASS_plus_'+token,lambda token=token:c.console_gate(text+token))
    candidate=dict(status='PREPARED_NOT_RUN',image=str(w.IMAGE),image_sha256=c.IMAGE_SHA,cases=cases,
        jobs=8,timeout_s=1800,worker_timeout_s=6900,service_timeout_s=7200,unit=w.UNIT,
        reference_ready_sha256=c.READY_SHA,reserved_slots=0,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True)
    for name,value in (('jobs',9),('timeout_s',1801),('service_timeout_s',7201),('worker_timeout_s',6901),
                       ('image_sha256','0'*64),('cases',cases[:13]),('no_retry',False),('reference_ready_sha256','0'*64)):
        reject(name+'_drift',lambda name=name,value=value:w.validate(dict(candidate,**{name:value}),w.IMAGE))
    bad=copy.deepcopy(candidate);bad['cases'][0]['sha256']='0'*64
    reject('ELF_drift',lambda:w.validate(bad,w.IMAGE))
    bad=copy.deepcopy(candidate);bad['cases'][0]['id']='historical_name'
    reject('runtime_id_drift',lambda:w.validate(bad,w.IMAGE))
    group='/user.slice/'+w.UNIT
    owner=dict(Id=w.UNIT,LoadState='loaded',ActiveState='active',SubState='running',MainPID='123',
         ControlGroup=group,RuntimeMaxUSec='2h',KillMode='control-group',Restart='no')
    w.owner_gate(owner,'0::'+group,123)
    reject('not_direct_service',lambda:w.owner_gate(owner,'0::'+group,456))
    reject('wrong_service_bound',lambda:w.owner_gate(dict(owner,RuntimeMaxUSec='1h'),'0::'+group,123))
    c.common.resource_math([dict(argv=[]) for _ in range(16)],64*1024**3,out,8,0)
    reject('resource_cap',lambda:c.common.resource_math([dict(argv=[]) for _ in range(17)],64*1024**3,out,8,0))
    reject('memory_floor',lambda:c.common.resource_math([],31*1024**3,out,8,0))
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        root=Path(tmp)
        for rc in (0,17):
            folder=root/str(rc);folder.mkdir();c.common.save(folder/'command.json',dict(command=['simv'],cwd=str(folder)))
            abort=threading.Event();w.FIRST_FAILURE_PATH=folder/'firstfailure.json'
            w.durable_monitor(lambda *a:(rc,0.25,False,False),abort)(['simv'],folder,folder/'console.log',1800,abort)
            m=c.read(folder/'monitor_outcome.unvalidated.json')
            c.require(type(m['returncode']) is int and m['returncode']==rc and abort.is_set()==(rc!=0),'Durable numeric monitor')
            result=SimpleNamespace(name='host_member',status='PASS' if rc==0 else 'FAIL',returncode=rc,elapsed_s=.25,reason='',artifact_dir=folder)
            class Parent:
                def __init__(self):pass
                def _run_test(self,*a):return result
            def broken(_):raise KeyError(8)
            abort.clear()
            returned=w.checked_runner(Parent,abort,broken,lambda _:None)()._run_test(SimpleNamespace(name='host_member'),None)
            stored=c.read(folder/'child_outcome.unvalidated.json');first=c.read(w.FIRST_FAILURE_PATH)
            c.require(type(stored['returncode']) is int and stored['returncode']==rc and returned.returncode==rc and abort.is_set()
                      and returned.status=='FAIL','Child0/17 preserved across failed postcheck')
            if rc==0:c.require(first['error_type']=='KeyError' and first['message']=='8' and first['case']=='host_member'
                               and 'broken' in first['traceback'],'Precise first postcheck context')
            digest=c.sha(w.FIRST_FAILURE_PATH);w.first_failure(dict(error_type='StickyAbort',message='later'))
            c.require(c.sha(w.FIRST_FAILURE_PATH)==digest,'First cause must not be overwritten')
            results.append(dict(name=f'numeric_first_child{rc}_firstcause',positive=True))
        w.FIRST_FAILURE_PATH=root/'io_failure.json';abort=threading.Event()
        def brokenio(*a):raise OSError('actual logread fixture')
        reject('monitor_IO_failure',lambda:w.durable_monitor(brokenio,abort)([],root,root/'console',1,abort))
        c.require(abort.is_set() and c.read(w.FIRST_FAILURE_PATH)['error_type']=='OSError','IO failure cancellation and detail')
        f=root/'plan.json';c.common.save(f,dict(value=1));digest=c.sha(f);c.common.save(f,dict(value=2))
        reject('fresh_disk_plan',lambda:w.terminal_plan_gate(root,digest,w.IMAGE))
        terminal=root/'terminal';terminal.mkdir();abort=w.terminal_publish.TerminalAbort();abort.set();state=dict(status=w.PASS)
        w.terminal_publish.publish(terminal,state,abort,time.monotonic()+60)
        c.require(state['status']!=w.PASS and c.read(terminal/'complete.json')['aborted'] is True,'Late abort veto')
        results.append(dict(name='late_abort',positive=True))
        env=dict(EXIT_CODE='exited',EXIT_STATUS='0',SERVICE_RESULT='success',SECRET='notexported')
        data=hook.payload(env,123)
        c.require(set(data)==set(hook.FIELDS)|{'recorded_unix_s'} and data['EXIT_STATUS']=='0','Only real hook fields')
        for name in hook.FIELDS:
            bad=dict(env);bad.pop(name);reject('hook_missing_'+name,lambda bad=bad:hook.payload(bad,123))
        reject('hook_invalid_exit',lambda:hook.payload(dict(env,EXIT_STATUS='false'),123))
        path=root/'hook.json';hook.write(path,data);reject('exclusive_hook_output',lambda:hook.write(path,data))
        # No semantic reference rerun: one synthetic malformed row tests exact failure coordinates.
        spec=c.specification((8,1));path=root/'malformed.csv'
        path.write_text(','.join(c.csv_source.FIELDS)+'\n'+','.join(['0','retire','0','0','0','deadbeef','13','0','0','0','0','0','0','0'])+'\n')
        strict=c.strict_csv(path,spec)
        c.require(strict['status']=='NOT_ACCEPTED_FIRST_CHECKER_FAILURE' and strict['current']['row']==1
                  and strict['current']['pc']=='deadbeef' and strict['error_type']=='ValueError' and strict['traceback'],
                  'Source failure coordinates/type/traceback')
        results.append(dict(name='strict_first_row_context',positive=True))
    w.FIRST_FAILURE_PATH=None
    c.common.image_context(w.IMAGE)
    import ara_verify.runner as engine
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        root=Path(tmp);cmd=[sys.executable,'-B','-c',"import time; print('SMALL_EXCEPTIONS_14_FAIL',end='',flush=True); time.sleep(8)"]
        c.common.save(root/'command.json',dict(command=cmd,cwd=str(root)));abort=threading.Event()
        with patch.object(engine,'FAIL_RE',c.VETO):
            rc,elapsed,timed,failed=w.durable_monitor(engine._run_monitored,abort)(cmd,root,root/'console.log',5,abort)
        c.require(type(rc) is int and failed and not timed and elapsed<5 and abort.is_set(),'Real partial FAIL monitor')
        results.append(dict(name='actual_host_partial_FAIL_monitor',positive=True,actual_rc=rc,elapsed_s=elapsed))
    files=[Path(__file__),Path(c.__file__),Path(w.__file__),Path(hook.__file__),c.REF/'READY.json',Path(c.abi.__file__),w.TERM]
    c.common.save(out/'status.json',dict(status='PASS_HOST_ONLY_NOT_DUT',failures=0,tests=len(results),cases=results,pins={str(p):c.sha(p) for p in files}))
    print('PASS_HOST_ONLY_NOT_DUT',len(results))

if __name__=='__main__':main()
