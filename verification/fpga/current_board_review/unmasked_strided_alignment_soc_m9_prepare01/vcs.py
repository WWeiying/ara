#!/usr/bin/env python3
"""M9 four directed tests then exact M8 controls16; bounded direct owner, no retry."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
G=HERE.parent
spec=importlib.util.spec_from_file_location('accepted_controls_helpers',G/'memory_candidate07_controls16/regression.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
require,read,sha=m.require,m.read,m.sha
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
IMAGE_SHA='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
M8=Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/campaign/image')
M8_SHA='bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0'
AG='hardware/src/vlsu/addrgen.sv'
AG_SHA='3736b64136ebbf5629dadb0037457279f9bb91307356c468c9677d321c8c51c5'
UNIT='ara-strided-alignment-m9-01.service'
MEMBERS=('load_m','store_m','load_sv39','store_sv39')
STAGES=('alignment4','controls16')
OUTER=4200

def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def receipt_ok(v,budget):
    require(type(v.get('returncode')) is int and v['returncode']==0,'Actual numeric child0')
    require(all(v.get(k) is False for k in ('timed_out','failure_seen','abort_set')),'Abort/failure/unknown')
    t=v.get('elapsed_s');require(type(t) in (float,int) and math.isfinite(t) and 0<=t<=budget,'Child budget')
def image_context():
    require(sha(IMAGE/'image.json')==IMAGE_SHA and sha(M8/'image.json')==M8_SHA,'Exact image')
    m.base.IMAGE=IMAGE
    ledger,repo,framework=m.base.image_context()
    require(ledger['configuration_sha256']==m.CONFIGURATION_SHA,'Configuration equivalence')
    oldledger=read(M8/'image.json');oldroot=Path(oldledger['snapshot'])/'sources'
    old=read(Path(oldledger['snapshot'])/'snapshot.json')['files']
    new=read(Path(ledger['snapshot'])/'snapshot.json')['files']
    require(set(old)==set(new) and len(new)==539,'539 source membership')
    changed={p for p in old if old[p]!=new[p]}
    for p in ('frozen.filelist','hardware/bender'):
        require((oldroot/p).read_bytes().replace(str(oldroot).encode(),str(repo).encode())==(repo/p).read_bytes(),'Root relocation only')
    require(changed=={AG,'frozen.filelist','hardware/bender'} and new[AG]==AG_SHA,'Only reviewed AddrGen delta')
    return ledger,repo,framework

def scope():
    cases=[];pins={}
    for member in MEMBERS:
        ref=HERE/('reference_'+member+'01');ready=read(ref/'READY.json');status=read(ref/'status.json')
        require(ready['status']==status['status']=='HOST_SPIKE_PASS_NOT_DUT' and ready['member']==member,'Reference member')
        require(type(status['receipt']['returncode']) is int and status['receipt']['returncode']==0 and
                status['checks']==(698 if member.startswith('store') else 697),'Full reference')
        pins.update(ready['input_pins']);pins.update({str(ref/p):h for p,h in ready['outputs'].items()})
        pins[str(ref/'READY.json')]=sha(ref/'READY.json')
        name='strided_alignment_'+member
        require(b'STRIDED_ALIGNMENT_PASS\n' in (ref/'soc.elf').read_bytes(),'Actual ELF pass marker')
        cases.append(dict(id=name,original_name=name,member=member,kind='directed',stage='alignment4',
             elf=str(ref/'soc.elf'),sha256=ready['outputs']['soc.elf'],spec=str(ref/'soc.spec.json'),
             timeout_s=900,pass_markers=['STRIDED_ALIGNMENT_PASS']))
    prior=G/'memory_candidate08_recovery19/prepared01'
    terminal=read(prior/'complete.json');plan=read(prior/'plan.json')
    require(terminal['status']=='PASS_M8_RECOVERY3_CONTROLS16_RESIDENT1' and terminal['aborted'] is False
            and terminal['pins_unchanged'] is True and terminal['retries']==0,'M8 real terminal baseline')
    for p in (prior/'complete.json',prior/'plan.json'):pins[str(p)]=sha(p)
    controls=[c for c in plan['cases'] if c['kind']=='control'];require(len(controls)==16,'Exact controls16')
    for original in controls:
        c=dict(original,stage='controls16')
        r=next(r for r in terminal['results'] if r['name']==c['id']);root=Path(r['artifact_dir'])
        require(r['status']=='PASS' and type(r['returncode']) is int and r['returncode']==0 and c['timeout_s']==180,'M8 control outcome/budget')
        receipt_ok(read(root/'child_exit.json'),180)
        for name in ('child_exit.json','commit_trace.csv','input.elf','inputs.json','command.json','console.log'):
            p=root/name;require(sha(p)==terminal['evidence_pins'][str(p)],'M8 evidence drift');pins[str(p)]=sha(p)
        require(sha(root/'input.elf')==c['sha256'],'M8 private ELF')
        c['baseline_csv']=str(root/'commit_trace.csv')
        pins[c['elf']]=c['sha256'];cases.append(c)
    return cases,pins

def prepare():
    out=HERE/'vcs_m9_prepared01';require(not out.exists(),'No overwrite')
    host=read(HERE/'host_dut01/result.json');unit=read(HERE/'host_worker01.json')
    require(host['status']=='HOST_FOUR_BRIDGES_PASS_NOT_DUT' and host['checker_sha256']==sha(HERE/'dut_check.py')
            and host['oracle_sha256']==sha(HERE/'check.py'),'Actual reference bridge binding')
    require(unit['passed'] and unit['worker_sha256']==sha(Path(__file__)) and unit['checker_sha256']==sha(HERE/'dut_check.py'),'Host negatives gate')
    cases,pins=scope();ledger,repo,_=image_context();pins.update(m.image_pins(IMAGE,ledger,repo))
    build=IMAGE.parents[1]/'BUILD_ACCEPTED.json'
    require(sha(build)=='348aefdc9e2112f939e5456c94a0e454a45f45e7de118b54d47178a5a70c2368','Accepted build')
    review=G/'unmasked_strided_alignment_repair_zeno01/M9_SOC_CONTRACT_REVIEW01.md'
    text=review.read_text()
    require(sha(HERE/'fixture.c') in text and sha(HERE/'fixture.S') in text,'Reviewed source identity')
    for p in [build,review,HERE/'host_dut01/result.json',HERE/'host_worker01.json',HERE/'test_worker.py',
              HERE/'dut_check.py',HERE/'check_case.py',HERE/'vcs.py',Path(m.__file__),Path(m.base.__file__),Path(m.base.shared.__file__)]:
        pins[str(p)]=sha(p)
    m.base.verify_pins(pins);out.mkdir()
    save(out/'plan.json',dict(status='PREPARED_NOT_RUN',image=str(IMAGE),image_sha256=IMAGE_SHA,cases=cases,pins=pins,
         unit=UNIT,jobs=2,unused_reservation_margin=2,outer_s=OUTER,stages=list(STAGES),
         no_build=True,retries=0,firstfail=True,scope='New alignment4 plus separate exact M8 controls16'))
    print(str(out/'plan.json')+' '+sha(out/'plan.json'),flush=True)

def run(approved):
    out=HERE/'vcs_m9_prepared01';require(sha(out/'plan.json')==approved,'Plan hash')
    p=read(out/'plan.json');m.base.verify_pins(p['pins'])
    cases,_=scope();require(cases==p['cases'] and p['jobs']==2 and p['outer_s']==4200,'Plan membership/budget')
    ledger,repo,(parent,options,testcase,_)=image_context()
    owner=dict(line.split('=',1) for line in subprocess.check_output(['systemctl','--user','show',UNIT,
        '-p','MainPID','-p','ControlGroup','-p','KillMode','-p','Restart','-p','RuntimeMaxUSec'],text=True,timeout=15).splitlines())
    require(owner['MainPID']==str(os.getpid()) and owner['KillMode']=='control-group' and owner['Restart']=='no'
            and owner['RuntimeMaxUSec']=='1h 10min' and Path('/proc/self/cgroup').read_text().strip()=='0::'+owner['ControlGroup'],'Direct bounded owner')
    admission=m.resources(out,2,p['unused_reservation_margin'])
    save(out/'launch.json',dict(pid=os.getpid(),owner=owner,admission=admission,plan_sha256=approved))
    abort=threading.Event();started=time.monotonic()
    terminal=dict(status='NOT_PASS',results=[],aborted=False,retries=0,pins_unchanged=False,firstfailure=None,
                  plan_sha256=approved,image_sha256=IMAGE_SHA)
    import ara_verify.runner as engine
    original,original_re=engine._run_monitored,engine.FAIL_RE
    def monitored(command,cwd,console,timeout_s,cancel_event=None):
        rc,elapsed,timed_out,failed=original(command,cwd,console,timeout_s,cancel_event)
        save(Path(console).parent/'child_exit.json',dict(returncode=rc,elapsed_s=elapsed,timed_out=timed_out,
             failure_seen=failed,abort_set=bool(cancel_event and cancel_event.is_set()),command=list(map(str,command)),cwd=str(cwd)))
        return rc,elapsed,timed_out,failed
    engine._run_monitored=monitored
    engine.FAIL_RE=re.compile(original_re.pattern+'|STRIDED_ALIGNMENT_FAIL|'+m.BAD.pattern,original_re.flags)
    entries={c['id']:c for c in cases}
    class Runner(parent):
        def __init__(self,*args,**kw):super().__init__(*args,**kw);self.cancel_event=abort
        def _run_test(self,test,image):
            try:
                r=super()._run_test(test,image);c=entries[test.name];root=r.artifact_dir
                receipt_ok(read(root/'child_exit.json'),c['timeout_s'])
                require(r.status=='PASS' and type(r.returncode) is int and r.returncode==0 and not abort.is_set(),'Runner outcome')
                m.check_artifacts(r,c,ledger)
                if c['kind']=='directed':
                    cmd=[sys.executable,str(HERE/'check_case.py'),c['member'],str(root/'commit_trace.csv'),c['spec'],str(root/'csv.json')]
                    save(root/'checker_invocation.json',dict(command=cmd))
                    with (root/'checker.log').open('x') as f: child=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=60)
                    save(root/'checker_exit.json',dict(returncode=child.returncode))
                    require(child.returncode==0 and read(root/'csv.json')['status']=='STRIDED_ALIGNMENT_DUT_CSV_PASS','Full CSV oracle')
                else:
                    perf=m.compare_cycles(Path(c['baseline_csv']),root/'commit_trace.csv',root/'cycle_differences.csv')
                    save(root/'performance.json',perf)
                    require(perf['cycle_changed_rows']==0,'Aligned control cycle regression')
                require(not abort.is_set() and time.monotonic()-started<4000,'Abort/deadline during postcheck')
                return r
            except BaseException:
                abort.set();raise
    with m.abort_signals(abort):
        try:
            for stage in STAGES:
                require(not abort.is_set(),'No launch after failure')
                subset=[c for c in cases if c['stage']==stage]
                opts=options(repo,out/stage,'default',2,1,False,False,True,Path(ledger['simv']),True,None)
                results=Runner(opts,[testcase(c['id'],'app','',Path(c['elf']),c['original_name'],c['timeout_s']) for c in subset],sys.argv).run()
                terminal['results'].extend(dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results)
                require(len(results)==len(subset) and {r.name for r in results}=={c['id'] for c in subset} and
                        all(r.status=='PASS' and type(r.returncode) is int and r.returncode==0 for r in results) and not abort.is_set(),'Stage incomplete/failed')
            m.base.verify_pins(p['pins']);image_context()
            require(not abort.is_set() and time.monotonic()-started<4000,'Campaign acceptance deadline')
            evidence={str(f):sha(f) for stage in STAGES for f in (out/stage).rglob('*') if f.is_file()}
            terminal.update(status='PASS_M9_ALIGNMENT4_CONTROLS16',pins_unchanged=True,evidence_pins=evidence)
        except BaseException as e:
            abort.set();terminal['firstfailure']=f'{type(e).__name__}: {e}'
        finally:
            engine._run_monitored,engine.FAIL_RE=original,original_re
            prior=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            try:
                terminal['aborted']=abort.is_set() or bool(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
                if terminal['aborted']:terminal['status']='NOT_PASS'
                terminal['elapsed_s']=time.monotonic()-started;save(out/'complete.json',terminal)
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,prior)
    print(terminal['status'],flush=True);return int(terminal['status']=='NOT_PASS')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','run']);ap.add_argument('--plan-sha256');a=ap.parse_args()
    env=m.base.shared.environment();env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':prepare()
    else:raise SystemExit(run(a.plan_sha256))
