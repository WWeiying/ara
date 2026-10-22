"""One bounded terminal collector service; no simulation or CSV semantic pass."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import audit as a
UNIT='ara-fof-original-two-m9-collector01.service'

def main():
    started=time.monotonic()
    active=None
    def cancelled(sig,frame):raise RuntimeError('Collector interrupted '+str(sig))
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    result=dict(status='NOT_ACCEPTED',accepted=False,CSV_semantic_reparsed=False,new_DUT_or_reference=False)
    try:
        props=dict(l.split('=',1) for l in subprocess.check_output(
            ['systemctl','--user','show',UNIT,'-p','MainPID','-p','ControlGroup',
             '-p','RuntimeMaxUSec','-p','KillMode','-p','Restart'],text=True,timeout=10).splitlines())
        a.need(props['MainPID']==str(os.getpid()) and props['RuntimeMaxUSec']=='1h 15min'
               and props['KillMode']=='control-group' and props['Restart']=='no'
               and Path('/proc/self/cgroup').read_text().strip()=='0::'+props['ControlGroup'],
               'Direct bounded collector service ownership')
        a.save(a.H/'started.json',dict(actual_pid=os.getpid(),service=UNIT,properties=props,time=time.time()))
        a.verify(a.read(a.H/'READY.json')['pins'])
        from events import wait_terminal
        wait_terminal(a.P,4200)
        plan,done,service,ledger=a.admission()
        envelope=a.read(a.P/'service_launch.json')
        inputs=dict(plan['pins'])
        for p,h in envelope['pins'].items():
            a.need(p not in inputs or inputs[p]==h,'Conflicting launch pin');inputs[p]=h
        review=a.H.parent/'fof_two_singles_m9_entry_review01/result.json'
        inputs[str(review)]=a.REVIEW
        inputs[str(a.P/'plan.json')]=a.PLAN
        inputs[str(a.P/'service_launch.json')]=a.ENVELOPE
        outputs=dict(done['evidence_pins'])
        for p in (a.P/'complete.json',a.P/'service_exit.json',a.P/'launch_command.json',
                  a.P/'systemd_run_receipt.json'):
            outputs[str(p)]=a.sha(p)
        required=[a.P/'launch.json',a.P/'replay/run.json',a.P/'replay/summary.json']
        for name in a.NAMES:
            root=a.P/'replay/tests'/name
            required += [root/n for n in ('input.elf','inputs.json','command.json','console.log',
                'work/run.vcs.log','commit_trace.csv','trace_summary.json','monitor_outcome.unvalidated.json',
                'child_outcome.unvalidated.json','strict_csv.json','strict_original.json')]
        a.need(set(done['evidence_pins'])==set(map(str,required)),'Complete exact output pin inventory')
        a.verify(inputs);a.verify(outputs)
        stamps={p:(Path(p).stat().st_size,Path(p).stat().st_mtime_ns) for p in outputs}
        case_results=[]
        for n in (1,2):
            command=[sys.executable,'-B',str(a.H/'audit.py'),str(n)]
            begin=time.monotonic()
            with (a.H/f'case{n}.log').open('x') as stream:
                active=subprocess.Popen(command,cwd=a.H,stdout=stream,stderr=subprocess.STDOUT)
                try:rc=active.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    active.kill();rc=active.wait()
                    a.save(a.H/f'case{n}_audit_exit.json',dict(actual_wait_returncode=rc,timed_out=True,command=command))
                    raise
            a.save(a.H/f'case{n}_audit_exit.json',dict(actual_wait_returncode=rc,timed_out=False,
                command=command,elapsed_s=time.monotonic()-begin,
                evidence='Actual independent metadata-audit Popen.wait, not producer checker wait'))
            active=None
            a.need(a.zero(rc),'Independent case metadata checker first failure')
            v=a.read(a.H/f'case{n}.json')
            a.need(v['status']=='PASS_CASE_METADATA_AND_PINS_NOT_CSV_REPARSE','Independent case result')
            case_results.append(v)
        a.verify(inputs)
        a.need(all((Path(p).stat().st_size,Path(p).stat().st_mtime_ns)==v for p,v in stamps.items()),
               'Terminal artifact changed during audit')
        a.admission()
        a.verify(a.read(a.H/'READY.json')['pins'])
        pins=dict(inputs)
        for p,h in outputs.items():
            a.need(p not in pins or pins[p]==h,'Conflicting terminal pin');pins[p]=h
        for p in (a.H/'audit.py',a.H/'events.py',a.H/'READY.json',Path(__file__)):
            pins[str(p)]=a.sha(p)
        a.save(a.H/'verified_pins.json',pins)
        result.update(status=a.PASS,accepted=True,service_exit=service,case_results=case_results,
            independent_case_audit_returncodes=[0,0],producer_numeric_child_returncodes=[0,0],
            producer_checker_execution='Both in-process checks returned PASS; no separate wait status exists',
            original_scope='Exactly original e8/sc0 and e64/sc5 source-derived singles; not Linux/full parent',
            input_pin_count=len(inputs),output_pin_count=len(outputs),unique_pin_count=len(pins),
            pins_pre_post_unchanged=True,CSV_hash_only=True,checks=sum(v['checks'] for v in case_results),
            rows=sum(v['generic']['rows'] for v in case_results),
            original_members=2,memory_owners=8,raw_logs_checked=4,
            plan_sha256=a.PLAN,image_sha256=a.IMAGE,complete_sha256=outputs[str(a.P/'complete.json')],
            verified_pins_sha256=a.sha(a.H/'verified_pins.json'))
    except BaseException as error:
        if active is not None and active.poll() is None:
            active.kill();active.wait()
        result.update(status='NOT_ACCEPTED_NO_RETRY',accepted=False,firstcause=repr(error))
    # Preserve observed failure/exit evidence even when the PASS gate rejects.
    for name in ('complete.json','service_exit.json','firstfailure.json'):
        p=a.P/name
        if p.exists():
            try:result['observed_'+name]=dict(path=str(p),sha256=a.sha(p),payload=a.read(p))
            except Exception as error:result['unreadable_'+name]=repr(error)
    result['audit_elapsed_s']=time.monotonic()-started
    a.save(a.H/'result.json',result)
    lines=['# Independent M9 Unit/FOF Terminal Audit','',result['status'],'',
           'No DUT/reference rerun; no CSV semantic reparse. Frozen checker outputs and full byte hashes audited.',
           'Producer checker executes in-process: no invented checker wait0. Each independent metadata case audit has its own actual numeric wait receipt.']
    if result['accepted']:
        lines += [f"Actual producer systemd: exited/0/success. Checks {result['checks']}; rows {result['rows']}; owners8.",
                  f"Pins: {result['input_pin_count']} input, {result['output_pin_count']} output; {result['unique_pin_count']} unique.",
                  'e8/sc0 returnsVL4 with only original final output5..8 undefined; e64/sc5 alloff returnsVL8/full8 strict. Guards, output130, mask16, full8KiB data/12KiB PT and original CSR gates retained.',
                  'Exact two M9 singles accepted; not Linux/full-family closure; no claim of zero physical MMU traffic.']
    else:lines += [result['firstcause']]
    lines += ['',f"Result SHA: {a.sha(a.H/'result.json')}"]
    with (a.H/'REVIEW.md').open('x') as f:f.write('\n'.join(lines)+'\n')
    print(result['status'],flush=True)
    return 0 if result['accepted'] else 1

if __name__=='__main__':raise SystemExit(main())
