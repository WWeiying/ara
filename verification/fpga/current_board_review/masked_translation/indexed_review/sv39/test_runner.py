#!/usr/bin/env python3
"""Host-only negative gates, event-reader and fail-fast scheduling tests."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest import mock
sys.dont_write_bytecode=True
import vcs_adapter as a
import scheduler
import live_tail
from support import save


def main():
    negatives=[]
    def reject(name,fn,exceptions=(ValueError,FileNotFoundError)):
        try: fn()
        except exceptions: negatives.append(name)
        else: raise AssertionError('Invalid input accepted: '+name)
    plan=dict(status='NF7_FULL96_PREFLIGHT_PASS_NOT_LAUNCHED',groups=list(range(24)),
              trials=list(range(96)),group_timeout_s=2400,group_outer_s=2700,max_jobs=4,image_sha256=a.IMAGE_SHA)
    a.validate_plan(plan)
    for key,value in [('groups',[0]),('trials',list(range(95))),('group_timeout_s',2401),
                      ('group_outer_s',2400),('max_jobs',5),('image_sha256','different'),('status','RUNNING')]:
        reject(key,lambda: a.validate_plan({**plan,key:value}))
    reject('missing_authorization',lambda: a.worker(a.HERE/'not-created',False,None,None,4))
    for jobs in (0,5):
        reject('invalid_jobs_'+str(jobs),lambda: scheduler.run_groups(range(24),jobs,lambda *x:None,scheduler.Abort()))
    for execute in (False,True):
        command=a.command(a.HERE/'not-created',0,execute)
        assert command[command.index('--timeout')+1]=='2400'
        assert command[command.index('--jobs')+1]==('1' if execute else '4')
        assert ('--execute' in command)==execute
        assert command.count('--case')==(1 if execute else 24)
    with tempfile.TemporaryDirectory(prefix='runner-host-',dir=a.HERE) as tmp:
        root=Path(tmp)
        with mock.patch.object(a,'accepted_references',side_effect=FileNotFoundError('not terminal')):
            reject('reference_not_terminal',lambda: a.preflight(root/'refused'))
            assert not (root/'refused').exists()
        nf2=dict(LoadState='loaded',ActiveState='active',MainPID='123',ControlGroup='/nf2',Result='success')
        arithmetic=dict(LoadState='loaded',ActiveState='active',MainPID='456',ControlGroup='/arithmetic',Result='success')
        with mock.patch.object(a,'unit_state',side_effect=[nf2,arithmetic]):
            reject('NF2_still_active',lambda: a.capacity_gate('ara-nf2.service','ara-arithmetic.service',4))
        nf2.update(ActiveState='inactive',MainPID='0')
        with mock.patch.object(a,'unit_state',side_effect=[nf2,arithmetic]),mock.patch.object(a,'Path',return_value=root):
            assert a.capacity_gate('ara-nf2.service','ara-arithmetic.service',4)['total_reserved_max_jobs']==8
        reject('same_capacity_unit',lambda: a.capacity_gate('ara-x.service','ara-x.service',4))
        reject('bad_unit_name',lambda: a.unit_state('not-a-service'))
        marker=root/'exclusive.json'; save(marker,{'owner':1})
        reject('duplicate_owner',lambda: save(marker,{'owner':2}),(FileExistsError,))
        reject('hash_drift',lambda: a.verify({str(marker):'wrong'}))
        # A real host child exercises nested-directory creation and split append lines.
        script="""import pathlib,sys,time
p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True)
with p.open('w') as f:
 f.write('header\\npar'); f.flush(); time.sleep(.03)
 f.write('tial\\nbad\\n'); f.flush(); time.sleep(5)
 f.write('after\\n'); f.flush()
"""
        observed=[]; failures=[]; events=live_tail.DirectoryEvents(root)
        target=root/'run/tests/fake/commit_trace.csv'
        process=subprocess.Popen([sys.executable,'-c',script,str(target)])
        def consume(line):
            observed.append(line)
            if line=='bad': raise ValueError('intentional firsterror')
        reject('live_firstfailure',lambda: live_tail.wait_append(process,events,target,consume,lambda e:failures.append(str(e))))
        assert observed==['header','partial','bad'] and len(failures)==1 and process.returncode!=0
    abort=scheduler.Abort(); barrier=threading.Barrier(4); failed=threading.Event(); launched=[]
    lock=threading.Lock(); active=0; maximum=0
    def fail_one(g,control):
        nonlocal active,maximum
        with lock:
            launched.append(g); active+=1; maximum=max(maximum,active)
        barrier.wait(timeout=5)
        if g==1:
            control.stop({'group':1,'error':'synthetic'}); failed.set()
        else:
            assert failed.wait(timeout=5)
        with lock: active-=1
        return dict(status='FAIL' if g==1 else 'PASS')
    results=scheduler.run_groups(range(24),4,fail_one,abort)
    assert sorted(launched)==[0,1,2,3] and maximum==4
    assert all(results[g]['status']=='CANCELLED_NOT_LAUNCHED' for g in range(4,24))
    assert abort.reason['group']==1
    reject('launch_after_firstfailure',lambda: abort.launch(99,lambda:None))
    completed=scheduler.run_groups(range(24),4,lambda g,control:dict(status='PASS'),scheduler.Abort())
    assert set(completed)==set(range(24)) and all(x['status']=='PASS' for x in completed.values())
    files=[Path(__file__),Path(a.__file__),a.HERE/'scheduler.py',a.HERE/'live_tail.py',a.HERE/'support.py',a.HERE/'ledger.py']
    save(a.HERE/'runner_host01.json',dict(status='HOST_RUNNER_NEGATIVES_PASS_NOT_DUT',negative_rejections=negatives,
        fake_child_only=True,VCS_started=False,cancelled_queue=list(range(4,24)),max_observed_workers=maximum,
        full24_success_scheduler=True,pins={str(p):a.ref.base.sha(p) for p in files}))
    print('HOST_RUNNER_NEGATIVES_PASS_NOT_DUT',len(negatives))


if __name__=='__main__': main()
