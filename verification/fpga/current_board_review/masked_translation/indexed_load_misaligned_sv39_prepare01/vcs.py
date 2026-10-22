#!/usr/bin/env python3
"""One M8 LOAD recovery after the sealed20 campaign, using event-only waiting."""
import argparse
import ctypes
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import signal
import struct
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('m8_recovery',HERE.parents[1]/'memory_candidate08_recovery19/worker.py')
m8=importlib.util.module_from_spec(spec);spec.loader.exec_module(m8)
import dut_check
read,sha,save,require=m8.read,m8.sha,m8.save,m8.require
IMAGE_SHA='bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0'
PREDECESSOR=m8.HERE/'prepared01'
PREDECESSOR_SHA='62f4e876969ab8389c43171917ee85c4c3e2b0fc4c86a4c7423ee926578b58fa'
UNIT='ara-indexed-load-m8-01.service'
OUT=HERE/'vcs_m8_load01'


def prepare():
    ref=HERE/'reference_load01';ready=read(ref/'READY.json')
    require(ready['status']=='HOST_SPIKE_PASS_NOT_DUT' and read(ref/'reference_exit.json')['returncode']==0,
            'Actual successful reference required')
    require(read(ref/'status.json')['checks']==962,'Full reference scope')
    bridge=read(HERE/'host_actual_reference_bridge02/result.json')
    require(bridge['status']=='HOST_ADAPTER_PASS_NOT_DUT' and bridge['members'][0]['checks']==962 and
            bridge['checker_sha256']==sha(HERE/'dut_check.py'),'Actual raw-to-checker bridge required')
    pins=dict(ready['input_pins']);pins.update({str(ref/p):h for p,h in ready['outputs'].items()})
    require(sha(PREDECESSOR/'plan.json')==PREDECESSOR_SHA,'Predecessor plan drift')
    pins.update(read(PREDECESSOR/'plan.json')['pins'])
    ledger,repo,_=m8.image_context(IMAGE_SHA)
    pins.update(m8.m7.image_pins(m8.IMAGE,ledger,repo))
    for path in (ref/'READY.json',HERE/'checker_reference_bridge02.py',HERE/'host_actual_reference_bridge02/result.json',
                 Path(__file__),Path(m8.__file__),PREDECESSOR/'plan.json'):
        pins[str(path)]=sha(path)
    require(pins[str(PREDECESSOR/'plan.json')]==PREDECESSOR_SHA,'Predecessor plan changed')
    m8.m7.base.verify_pins(pins)
    OUT.mkdir(exist_ok=False)
    case=dict(id='indexed_load_misaligned_vl5',original_name='indexed_load_misaligned_vl5',
        elf=str(ref/'soc.elf'),sha256=ready['outputs']['soc.elf'],timeout_s=900,pass_markers=['INDEXED_LOAD_SV39_PASS'])
    save(OUT/'plan.json',dict(case=case,pins=pins,image_sha256=IMAGE_SHA,predecessor_plan_sha256=PREDECESSOR_SHA,
         jobs=1,wait_bound_s=6600,service_outer_s=8000,retries=0,no_build=True,no_wave=True))
    print('PREPARED',sha(OUT/'plan.json'),flush=True)


def wait_predecessor(abort):
    path=PREDECESSOR/'complete.json'
    libc=ctypes.CDLL(None,use_errno=True)
    fd=libc.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
    require(fd>=0,'inotify unavailable; do not poll')
    try:
        require(libc.inotify_add_watch(fd,os.fsencode(PREDECESSOR),0x8|0x80)>=0,'inotify watch failed')
        stop=time.monotonic()+6600
        save(OUT/'wait_started.json',dict(pid=os.getpid(),path=str(path),event_only=True,bound_s=6600,time=time.time()))
        closed=path.exists()
        while not closed:
            remaining=stop-time.monotonic()
            require(remaining>0 and not abort.is_set(),'Predecessor deadline/cancellation')
            ready,_,_=select.select([fd],[],[],remaining)
            require(ready,'Predecessor event deadline')
            events=os.read(fd,65536);offset=0
            while offset<len(events):
                _,mask,_,length=struct.unpack_from('iIII',events,offset)
                name=events[offset+16:offset+16+length].split(b'\0',1)[0]
                if name==b'complete.json' and mask&(0x8|0x80):closed=True
                offset+=16+length
        terminal=read(path);plan=read(PREDECESSOR/'plan.json')
        require(sha(PREDECESSOR/'plan.json')==PREDECESSOR_SHA and
                terminal['plan_sha256']==PREDECESSOR_SHA and terminal['image_sha256']==IMAGE_SHA,
                'Predecessor identity mismatch')
        require(terminal['status']=='PASS_M8_RECOVERY3_CONTROLS16_RESIDENT1' and terminal['aborted'] is False
                and terminal['pins_unchanged'] is True and terminal['retries']==0 and
                not terminal.get('firstfailure'),'Predecessor not full PASS')
        require(len(terminal['results'])==20 and {r['name'] for r in terminal['results']}==
                {c['id'] for c in plan['cases']},'Predecessor partial scope')
        for r in terminal['results']:
            require(r['status']=='PASS' and type(r['returncode']) is int and r['returncode']==0,'Predecessor child failed')
            receipt=Path(r['artifact_dir'])/'child_exit.json'
            require(terminal['evidence_pins'][str(receipt)]==sha(receipt),'Predecessor receipt drift')
            c=next(c for c in plan['cases'] if c['id']==r['name'])
            m8.check_receipt(read(receipt),c['timeout_s'])
        m8.m7.base.verify_pins(plan['pins'])
        save(OUT/'predecessor_admission.json',dict(complete_sha256=sha(path),plan_sha256=PREDECESSOR_SHA,
             status=terminal['status'],actual_children=20,scope='Receipt/pin check only, no CSV reparse'))
    finally:os.close(fd)


def observe_startup(root):
    try:
        time.sleep(45)
        found=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                if (proc/'comm').read_text().strip()!='simv':continue
                argv=(proc/'cmdline').read_bytes().decode().strip('\0').split('\0')
                if '+COMMIT_TRACE='+str(root/'commit_trace.csv') not in argv:continue
                def sample():
                    ticks=(proc/'stat').read_text().split(') ',1)[1].split()
                    return dict(time=time.time(),cpu_ticks=int(ticks[11])+int(ticks[12]),
                                trace_bytes=(root/'commit_trace.csv').stat().st_size)
                first=sample();time.sleep(10);second=sample()
                found.append(dict(pid=int(proc.name),argv=argv,cgroup=(proc/'cgroup').read_text(),first=first,second=second,
                                  growing=second['cpu_ticks']>first['cpu_ticks'] and second['trace_bytes']>first['trace_bytes']))
            except (FileNotFoundError,ProcessLookupError):continue
        save(OUT/'startup_observation.json',dict(simulators=found,no_pass_claim=True))
    except BaseException as error:
        save(OUT/'startup_observation_error.json',dict(error=repr(error),no_pass_claim=True))


def run(approved):
    require(sha(OUT/'plan.json')==approved,'Plan drift')
    plan=read(OUT/'plan.json');m8.m7.base.verify_pins(plan['pins'])
    owner=dict(line.split('=',1) for line in subprocess.check_output(['systemctl','--user','show',UNIT,
        '-p','MainPID','-p','ControlGroup','-p','RuntimeMaxUSec','-p','KillMode','-p','Restart'],text=True,timeout=15).splitlines())
    require(owner['MainPID']==str(os.getpid()) and owner['KillMode']=='control-group' and owner['Restart']=='no' and
            owner['RuntimeMaxUSec']=='2h 13min 20s' and Path('/proc/self/cgroup').read_text().strip()=='0::'+owner['ControlGroup'],
            'Actual direct bounded owner required')
    abort=threading.Event();start=time.monotonic()
    terminal=dict(status='NOT_PASS',results=[],pins_unchanged=False,retries=0,plan_sha256=approved,image_sha256=IMAGE_SHA)
    with m8.m7.abort_signals(abort):
        try:
            wait_predecessor(abort)
            admission=m8.m7.resources(OUT,1,0)
            prefix='+COMMIT_TRACE='+str(PREDECESSOR)+'/'
            require(not any(any(a.startswith(prefix) for a in p['argv']) for p in admission['live']),
                    'Predecessor simulator remains; no concurrent4th slot')
            m8.m7.base.verify_pins(plan['pins'])
            ledger,repo,(parent,options,testcase,_)=m8.image_context(IMAGE_SHA)
            save(OUT/'launch.json',dict(pid=os.getpid(),owner=owner,admission=admission,time=time.time(),plan_sha256=approved))
            import ara_verify.runner as engine
            original,original_re=engine._run_monitored,engine.FAIL_RE
            def monitored(command,cwd,console,timeout_s,cancel_event=None):
                watcher=threading.Thread(target=observe_startup,args=(Path(console).parent,),daemon=True)
                watcher.start()
                result=original(command,cwd,console,timeout_s,cancel_event)
                rc,elapsed,timed_out,failed=result
                save(Path(console).parent/'child_exit.json',dict(returncode=rc,elapsed_s=elapsed,timed_out=timed_out,
                    failure_seen=failed,abort_set=bool(cancel_event and cancel_event.is_set()),command=list(map(str,command)),cwd=str(cwd)))
                return result
            engine._run_monitored=monitored
            engine.FAIL_RE=re.compile(original_re.pattern+'|INDEXED_LOAD_SV39_FAIL',original_re.flags)
            try:
                class Runner(parent):
                    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.cancel_event=abort
                c=plan['case'];opts=options(repo,OUT/'run','default',1,1,False,False,True,Path(ledger['simv']),True,None)
                results=Runner(opts,[testcase(c['id'],'app','',Path(c['elf']),c['id'],c['timeout_s'])],sys.argv).run()
                terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
                m8.terminal_ok(results,[c],abort)
                r=results[0];root=r.artifact_dir
                m8.check_receipt(read(root/'child_exit.json'),900)
                m8.m7.check_artifacts(r,c,ledger)
                checked=dut_check.analyze(root/'commit_trace.csv',read(HERE/'reference_load01/soc.symbols.json'),0)
                require(checked['status']=='INDEXED_LOAD_CSV_PASS' and checked['checks']==962,'Full original LOAD checker')
                save(OUT/'csv.json',checked)
                m8.m7.base.verify_pins(plan['pins']);m8.image_context(IMAGE_SHA)
                require(not abort.is_set() and time.monotonic()-start<7900,'Aborted/worker deadline')
                terminal.update(status='M8_INDEXED_LOAD_MISALIGNED_PASS',pins_unchanged=True,csv=checked,
                                evidence_pins={str(p):sha(p) for p in root.rglob('*') if p.is_file()})
            finally:engine._run_monitored,engine.FAIL_RE=original,original_re
        except BaseException as error:
            abort.set();terminal['firstfailure']=f'{type(error).__name__}: {error}'
        finally:
            old=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            try:
                terminal['aborted']=abort.is_set() or bool(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
                if terminal['aborted']:terminal['status']='NOT_PASS'
                terminal['elapsed_s']=time.monotonic()-start;save(OUT/'complete.json',terminal)
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,old)
    print(terminal['status'],flush=True)
    return int(terminal['status']=='NOT_PASS')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run']);p.add_argument('--plan-sha256');a=p.parse_args()
    env=m8.m7.base.shared.environment();env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
        DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus');os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':prepare()
    else:sys.exit(run(a.plan_sha256))
