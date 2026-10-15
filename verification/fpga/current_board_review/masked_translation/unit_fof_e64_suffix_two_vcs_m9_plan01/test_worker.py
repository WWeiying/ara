"""Focused worker-only Host gates. No source/Spike replay or DUT execution."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
sys.dont_write_bytecode=True
import checker as c
import replay as w
import source_owners as owners

def owner_rows(spec):
    rows=[]
    for seq,site in enumerate(owners.recipe(spec)):
        for offset,event in enumerate(('arch_start','uop_alloc','cvx_req','cvx_resp','uop_done','retire')):
            rows.append(dict(event=event,insn=f'{site["insn"]:x}',pc=f'{site["pc"]:x}',
                order=str(seq),trans_id=str(seq%2),port='0',cycle=str(seq*10+offset),trap='0'))
    return rows

def check_owners(spec,rows,vl=8,start=0,mask=15):
    q=owners.MemoryOwners(spec)
    mem={spec['symbols']['fx_mask']+i:mask if i==0 else 0 for i in range(16)}
    for row in rows:q.row(row,{10:0x40000fe0},{0xc20:vl,0xc21:24,8:start},mem)
    return q.finish()

def main():
    out=c.HERE/'host02'
    c.require(not out.exists(),'Fresh Host output')
    out.mkdir()
    results=[]
    def reject(name,fn):
        try:fn()
        except (ValueError,KeyError,TypeError,OSError):
            results.append(dict(name=name,rejected=True));return
        raise AssertionError('Accepted '+name)
    cases=c.scope()
    c.require(len(cases)==2 and [x['scenario'] for x in cases]==[1,2] and all(x['sew']==64 for x in cases),'Exact source membership')
    for case in cases:
        s=c.specification(case['scenario'])
        c.require('tohost' not in s['symbols'] and s['backend']=='soc','Actual CTRL-only spec')
        c.require(c.runtime_case(case)['original_name']==case['id'],'Runtime label separated from archive name')
    results.append(dict(name='exact_source_two_ELFs_CTRL_only_specs',positive=True))
    for case in cases:
        spec=c.specification(case['scenario']);rows=owner_rows(spec)
        c.require(check_owners(spec,rows)['memory_owner_count']==4,'Positive source lifecycle')
        results.append(dict(name=f'scenario{case["scenario"]}_four_source_owners',positive=True))
        reject('isolated_done',lambda:check_owners(spec,[rows[4]]+rows))
        for seq in range(4):
            bad=[r for r in rows if not (int(r['order'])==seq and r['event'] in ('uop_alloc','uop_done'))]
            reject('delete_full_alloc_done_pair_'+str(seq),lambda bad=bad:check_owners(spec,bad))
        bad=copy.deepcopy(rows);bad[4]['trans_id']='7'
        reject('done_wrong_owner',lambda:check_owners(spec,bad))
        reject('empty_VL',lambda:check_owners(spec,rows,vl=0))
        reject('start_equals_VL',lambda:check_owners(spec,rows,start=8))
        reject('target_wrong_alloff_mask',lambda:check_owners(spec,rows,mask=0))
    text='UNIT_FOF_E64_SUFFIX_PASS\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
    c.console_gate(text)
    reject('missing_oracle',lambda:c.console_gate(text.replace('UNIT_FOF_E64_SUFFIX_PASS\n','')))
    reject('duplicate_oracle',lambda:c.console_gate(text+'UNIT_FOF_E64_SUFFIX_PASS\n'))
    for token in ('UNIT_FOF_E64_SUFFIX_FAIL','BOARD_REPLAY_MISMATCH','BOARD_REPLAY_TRAP','Fatal: failure'):
        reject('PASS_plus_'+token,lambda token=token:c.console_gate(text+token))
    candidate=dict(status='PREPARED_NOT_RUN',image=str(w.IMAGE),image_sha256=c.IMAGE_SHA,cases=cases,
        jobs=2,timeout_s=1800,worker_timeout_s=3900,service_timeout_s=4200,unit=w.UNIT,
        no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True)
    for key,value in (('jobs',3),('timeout_s',1801),('service_timeout_s',4201),
                      ('image_sha256','0'*64),('cases',cases[:1]),('no_retry',False)):
        reject(key+'_drift',lambda key=key,value=value:w.validate(dict(candidate,**{key:value}),w.IMAGE))
    bad=copy.deepcopy(candidate);bad['cases'][0]['sha256']='0'*64
    reject('ELF_drift',lambda:w.validate(bad,w.IMAGE))
    group='/user.slice/'+w.UNIT
    owner=dict(Id=w.UNIT,LoadState='loaded',ActiveState='active',SubState='running',
               MainPID='123',ControlGroup=group,RuntimeMaxUSec='1h 10min',KillMode='control-group',Restart='no')
    w.owner_gate(owner,'0::'+group,123)
    reject('not_direct_service',lambda:w.owner_gate(owner,'0::'+group,456))
    reject('wrong_service_bound',lambda:w.owner_gate(dict(owner,RuntimeMaxUSec='1h'),'0::'+group,123))
    c.common.resource_math([],64*1024**3,out,2,0)
    reject('resource_cap',lambda:c.common.resource_math([dict(argv=[]) for _ in range(23)],64*1024**3,out,2,0))
    reject('memory_floor',lambda:c.common.resource_math([],31*1024**3,out,2,0))
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        root=Path(tmp)
        for rc in (0,17):
            folder=root/str(rc);folder.mkdir()
            c.common.save(folder/'command.json',dict(command=['simv'],cwd=str(folder)))
            abort=threading.Event()
            actual=w.durable_monitor(lambda *a:(rc,0.25,False,False),abort)
            actual(['simv'],folder,folder/'console.log',1800,abort)
            m=c.read(folder/'monitor_outcome.unvalidated.json')
            c.require(type(m['returncode']) is int and m['returncode']==rc,'Durable real numeric result')
            c.require(abort.is_set()==(rc!=0),'Immediate numeric failure cancellation')
            result=SimpleNamespace(name='test',status='PASS' if rc==0 else 'FAIL',returncode=rc,
                elapsed_s=.25,reason='',artifact_dir=folder)
            class Parent:
                def __init__(self):pass
                def _run_test(self,*a):return result
            def broken(_):raise ValueError('Host postcheck injection')
            abort.clear()
            returned=w.checked_runner(Parent,abort,broken,lambda _:None)()._run_test(SimpleNamespace(name='test'),None)
            stored=c.read(folder/'child_outcome.unvalidated.json')
            c.require(stored['returncode']==rc and returned.returncode==rc and abort.is_set()
                      and returned.status=='FAIL','Preserve original child0/17 through postcheck failure')
            results.append(dict(name=f'numeric_first_child{rc}_postcheck_sticky',positive=True))
        abort=threading.Event()
        def io_error(*a):raise OSError('Host logread error')
        reject('monitor_logread_exception',lambda:w.durable_monitor(io_error,abort)([],root,root/'missing',1,abort))
        c.require(abort.is_set(),'Logread exception must cancel peers')
        f=root/'plan.json';c.common.save(f,dict(value=1));digest=c.sha(f);c.common.save(f,dict(value=2))
        reject('late_disk_plan_hash',lambda:w.terminal_plan_gate(root,digest,w.IMAGE))
        terminal=root/'terminal';terminal.mkdir()
        abort=w.terminal_publish.TerminalAbort();abort.set()
        state=dict(status=w.PASS)
        w.terminal_publish.publish(terminal,state,abort,time.monotonic()+60)
        c.require(c.read(terminal/'complete.json')['aborted'] is True and state['status']!=w.PASS,'Late abort cannot publish PASS')
        results.append(dict(name='late_abort_terminal',positive=True))
    # Actual tiny host process, not simv: prove partial marker stops before timeout.
    c.common.image_context(w.IMAGE)
    import ara_verify.runner as engine
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        root=Path(tmp);command=[sys.executable,'-B','-c',
          "import time; print('UNIT_FOF_E64_SUFFIX_FAIL',end='',flush=True); time.sleep(8)"]
        c.common.save(root/'command.json',dict(command=command,cwd=str(root)))
        abort=threading.Event()
        with patch.object(engine,'FAIL_RE',c.VETO):
            rc,elapsed,timed,failed=w.durable_monitor(engine._run_monitored,abort)(
                command,root,root/'console.log',5,abort)
        c.require(type(rc) is int and failed and not timed and elapsed<5 and abort.is_set(),'Partial raw failure firstfail stop')
        results.append(dict(name='actual_host_partial_FAIL_monitor',positive=True,actual_rc=rc,elapsed_s=elapsed))
    pins={str(p):c.sha(p) for p in (Path(__file__),Path(c.__file__),Path(w.__file__),
                                  c.REF/'READY.json',Path(c.csv_source.__file__),w.TERM)}
    c.common.save(out/'status.json',dict(status='PASS_HOST_ONLY_NOT_DUT',failures=0,tests=len(results),cases=results,pins=pins))
    print('PASS_HOST_ONLY_NOT_DUT',len(results),flush=True)

if __name__=='__main__':main()
