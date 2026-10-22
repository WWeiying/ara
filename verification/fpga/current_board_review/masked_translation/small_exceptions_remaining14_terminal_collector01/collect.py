"""One bounded terminal collector service; no simulation or CSV semantic pass."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import audit as a
UNIT='ara-small-exceptions14-m9-collector01.service'

def main():
    started=time.monotonic()
    active=None
    def cancelled(sig,frame):raise RuntimeError('Collector interrupted '+str(sig))
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    result=dict(status='NOT_ACCEPTED',accepted=False,CSV_semantic_reparsed=False,new_DUT_or_reference=False)
    try:
        a.verify(a.BINDING['collector_pins'])
        props=dict(l.split('=',1) for l in subprocess.check_output(
            ['systemctl','--user','show',UNIT,'-p','MainPID','-p','ControlGroup',
             '-p','RuntimeMaxUSec','-p','KillMode','-p','Restart'],text=True,timeout=10).splitlines())
        a.need(props['MainPID']==str(os.getpid()) and props['RuntimeMaxUSec']=='2h'
               and props['KillMode']=='control-group' and props['Restart']=='no'
               and Path('/proc/self/cgroup').read_text().strip()=='0::'+props['ControlGroup'],
               'Direct bounded collector service ownership')
        a.save(a.H/'started.json',dict(actual_pid=os.getpid(),service=UNIT,properties=props,time=time.time()))
        waiter=Path(__file__).resolve().parents[2]/'wait_terminal.py'
        a.need(a.sha(waiter)==a.BINDING['waiter_sha256'],'Frozen event waiter')
        command=[sys.executable,'-B',str(waiter),str(a.P/'service_exit.json'),'--timeout','7000']
        with (a.H/'event_wait.log').open('x') as stream:
            active=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT)
            rc=active.wait(timeout=7010)
        active=None
        a.save(a.H/'event_wait_exit.json',dict(command=command,actual_wait_returncode=rc))
        a.need(a.zero(rc),'Bounded event wait failed; no retry')
        a.need((a.P/'complete.json').is_file(),'Service exit without complete.json')
        plan,done,service,ledger=a.admission()
        envelope=a.read(a.P/'service_launch.json')
        inputs=dict(plan['pins'])
        for p,h in envelope['pins'].items():
            a.need(p not in inputs or inputs[p]==h,'Conflicting launch pin');inputs[p]=h
        review=Path(a.BINDING['review_path'])
        inputs[str(review)]=a.REVIEW
        inputs[str(a.P/'plan.json')]=a.PLAN
        inputs[str(a.P/'service_launch.json')]=a.ENVELOPE
        outputs=dict(done['evidence_pins'])
        for p in (a.P/'complete.json',a.P/'service_exit.json',a.P/'launch_command_takeover.json',
                  a.P/'systemd_run_takeover.json'):
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
        for n in range(1,15):
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
        a.verify(a.BINDING['collector_pins'])
        pins=dict(inputs)
        for p,h in outputs.items():
            a.need(p not in pins or pins[p]==h,'Conflicting terminal pin');pins[p]=h
        for p in (a.H/'audit.py',Path(__file__),a.H/'binding.json',waiter):
            pins[str(p)]=a.sha(p)
        a.save(a.H/'verified_pins.json',pins)
        result.update(status=a.PASS,accepted=True,service_exit=service,case_results=case_results,
            independent_case_audit_returncodes=[0]*14,producer_numeric_child_returncodes=[0]*14,
            producer_checker_execution='All14 in-process checks returned PASS; no separate wait status exists',
            original_scope='Exactly14 source-derived e8/e16/e32 exception singles; not Linux/full parent',
            input_pin_count=len(inputs),output_pin_count=len(outputs),unique_pin_count=len(pins),
            pins_pre_post_unchanged=True,CSV_hash_only=True,checks=sum(v['checks'] for v in case_results),
            rows=sum(v['generic']['rows'] for v in case_results),
            original_members=14,memory_owners=56,raw_logs_checked=28,
            plan_sha256=a.PLAN,image_sha256=a.IMAGE,complete_sha256=outputs[str(a.P/'complete.json')],
            verified_pins_sha256=a.sha(a.H/'verified_pins.json'))
    except BaseException as error:
        if active is not None and active.poll() is None:
            active.kill();active.wait()
        result.update(status='NOT_ACCEPTED_NO_RETRY',accepted=False,firstcause=repr(error))
    result['audit_elapsed_s']=time.monotonic()-started
    a.save(a.H/'result.json',result)
    lines=['# Independent M9 Remaining14 Terminal Audit','',result['status'],'',
           'No DUT/reference rerun; no CSV semantic reparse. Frozen checker outputs and full byte hashes audited.',
           'Producer checker executes in-process: no invented checker wait0. Each independent metadata case audit has its own actual numeric wait receipt.']
    if result['accepted']:
        lines += [f"Actual producer systemd: exited/0/success. Checks {result['checks']}; rows {result['rows']}; owners56.",
                  f"Pins: {result['input_pin_count']} input, {result['output_pin_count']} output; {result['unique_pin_count']} unique.",
                  'Original8 results, guards, output130, mask16, full8KiB data/12KiB PT, CSR and ABI gates retained; only sc0 final slots5..8 undefined.',
                  'Exact14 M9 singles accepted; not Linux/full-family closure; no claim of zero physical MMU traffic.']
    else:lines += [result['firstcause']]
    lines += ['',f"Result SHA: {a.sha(a.H/'result.json')}"]
    with (a.H/'REVIEW.md').open('x') as f:f.write('\n'.join(lines)+'\n')
    print(result['status'],flush=True)
    return 0 if result['accepted'] else 1

if __name__=='__main__':raise SystemExit(main())
