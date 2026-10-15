"""One closed-CSV pass per case; retain all old NOT_ACCEPTED evidence unchanged."""
import csv
import argparse
import hashlib
import json
from pathlib import Path
import time
import traceback
import sys
import successor as s
from successor_handler import Checker

c=s.frozen
H=s.HERE
OLD=s.WORKER/'prepared01'
OUT=H/'closed_audit01'
PLAN='11521664380ef491f6db4823b8ccd99865a25df2011fd6ed1f12b52ee0e995b1'
save=c.common.save

def closed_case(case):
    root=OLD/'replay/tests'/case['id']
    command=c.read(root/'command.json')
    expect=['/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image/_build/vcs/simv',
            '-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),
            '+TESTCASE='+case['id'],'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')]
    s.need(command==dict(command=expect,cwd=str(root/'work')),'Exact original runtime command/ELF, not Linux name')
    s.need(c.sha(root/'input.elf')==case['sha256']==c.sha(case['elf']),'Private and original source-port ELF')
    child=c.read(root/'child_outcome.unvalidated.json')
    monitor=c.read(root/'monitor_outcome.unvalidated.json')
    s.need(child['architectural_acceptance'] is False and child['status']=='PASS'
           and child['name']==case['id'] and child['reason']=='' and child['command']==command,
           'Durable unvalidated child identity')
    for r in (child,monitor):
        s.need(type(r['returncode']) is int and r['returncode']==0 and 0<r['elapsed_s']<1800
               and r['command_sha256']==c.sha(root/'command.json'),'Actual numeric child/monitor0 and command')
    s.need(monitor['command']==expect and monitor['cwd']==command['cwd']
           and monitor['elapsed_s']==child['elapsed_s']
           and all(monitor[k] is False for k in ('timed_out','failure_seen','abort_set')),'No simulator timeout/failure/abort')
    for name in ('console.log','work/run.vcs.log'):c.console_gate((root/name).read_text())
    prior=c.read(root/'strict_csv.json')
    s.need(prior['status']=='NOT_PASS_UNIT_FOF' and prior['error']=='8' and prior['rows']==12989
           and prior['checks']==0,'Preserved exact old checker failure')
    return root,child,monitor

def main(review,review_sha):
    s.need(c.sha(review)==review_sha,'Actual independent delta review identity')
    approval=c.read(review)
    s.need(approval['decision']=='NO_BLOCKER' and approval['blockers']==[], 'Independent delta review required')
    for name in ('successor.py','successor_handler.py','test_host.py','test_handler.py','audit.py'):
        p=H/name
        s.need(approval['pins'].get(str(p))==c.sha(p),'Exact reviewed successor code '+name)
    OUT.mkdir()
    started=time.monotonic();results=[];q=None
    try:
        s.need(c.sha(OLD/'plan.json')==PLAN,'Frozen original plan')
        plan=c.read(OLD/'plan.json');old=c.read(OLD/'complete.json')
        s.need(old['plan_sha256']==PLAN and old['image_sha256']==c.IMAGE_SHA
               and old['status']=='NOT_ACCEPTED_LATE_ABORT' and old['aborted'] is True
               and type(old['retries']) is int and old['retries']==0,'Preserve old batch error; no retry')
        service=c.read(OLD/'service_exit.json')
        s.need({k:service[k] for k in ('EXIT_CODE','EXIT_STATUS','SERVICE_RESULT')}==
               dict(EXIT_CODE='exited',EXIT_STATUS='1',SERVICE_RESULT='exit-code'),'Actual old worker failure exit')
        host=c.read(H/'host01/execution.json')
        s.need(type(host['actual_wait_returncode']) is int and host['actual_wait_returncode']==0,'Successor Host receipt')
        host2=c.read(H/'host_handler01/execution.json')
        s.need(type(host2['actual_wait_returncode']) is int and host2['actual_wait_returncode']==0,'Handler Host receipt')
        pins=dict(plan['pins'])
        pins[str(review)]=review_sha
        for f in H.iterdir():
            if f.is_file():pins[str(f)]=c.sha(f)
        for f in (H/'host01').iterdir():
            if f.is_file():pins[str(f)]=c.sha(f)
        for f in (H/'host_handler01').iterdir():
            if f.is_file():pins[str(f)]=c.sha(f)
        for name in ('plan.json','complete.json','firstfailure.json','service_exit.json','service.log',
                     'replay/run.json','replay/summary.json','launch.json','launch_command.json',
                     'systemd_run_receipt.json','service_launch.json'):
            p=OLD/name;pins[str(p)]=c.sha(p)
        cases=c.scope();s.need(plan['cases']==cases,'Two exact original scenario0/3 members')
        for case in cases:
            root,_,_=closed_case(case)
            for name in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log',
                         'commit_trace.csv','child_outcome.unvalidated.json','monitor_outcome.unvalidated.json',
                         'strict_csv.json','trace_summary.json'):
                p=root/name;pins[str(p)]=c.sha(p)
        c.common.base.verify_pins(pins);save(OUT/'pins_before.json',pins)
        save(OUT/'invocation.json',dict(authorized='User requested one offline full check of both closed CSVs',
             command=[sys.executable,*sys.argv],original_plan_sha256=PLAN,
             independent_review=str(review),independent_review_sha256=review_sha,
             original_complete_sha256=c.sha(OLD/'complete.json'),no_DUT_or_reference=True,
             checker_sha256=c.sha(H/'successor_handler.py'),main_checker_sha256=c.sha(H/'successor.py')))
        for case in cases:
            root,child,monitor=closed_case(case)
            q=Checker(c.specification(case['scenario']))
            digest=hashlib.sha256();rows=0
            with (root/'commit_trace.csv').open('rb') as stream:
                def lines():
                    for raw in stream:
                        digest.update(raw)
                        yield raw.decode('ascii')
                reader=csv.DictReader(lines())
                s.need(reader.fieldnames==s.old.FIELDS,'Exact original RVFI CSV schema')
                for row in reader:
                    original=dict(row);q.row(row);rows+=1
                    s.need(row==original,'Every original row passed unchanged to inherited checker')
            result=q.finish()
            generic=c.read(root/'trace_summary.json')
            s.need(generic['status']=='VALID' and generic['cvx_exception_count']==0
                   and generic['backend_uop_alloc_count']==generic['backend_uop_done_count']==4,
                   'Pinned original generic complete trace')
            s.need((rows,q.retired,q.last_cycle)==(generic['rows'],generic['retire_count'],generic['last_cycle'])
                   and rows==q.rows,'Full original CSV extent, not prefix-only')
            s.need(digest.hexdigest()==pins[str(root/'commit_trace.csv')],'Lossless CSV byte hash')
            result.update(actual_child_returncode=child['returncode'],actual_child_elapsed_s=child['elapsed_s'],
                          CSV_semantic_passes=1,unchanged_rows=rows,CSV_sha256=digest.hexdigest(),
                          old_checker_status='NOT_PASS_UNIT_FOF',old_worker_exit=service,
                          original_generic_summary_recomputed=False)
            save(OUT/f'scenario{case["scenario"]}.json',result)
            results.append(result)
        c.common.base.verify_pins(pins)
        result=dict(status='ARCHITECTURAL_RESULTS_ACCEPTED_OFFLINE_OLD_BATCH_NOT_ACCEPTED',
            cases=results,checks=sum(x['checks'] for x in results),rows=sum(x['rows'] for x in results),
            retired=sum(x['retired'] for x in results),memory_owners=sum(x['memory_owner_count'] for x in results),
            helper_owners=sum(x['helper_owner_count'] for x in results),checkpoints=sum(len(x['checkpoints']) for x in results),
            original_plan_pins=len(plan['pins']),verified_pins=len(pins),pins_pre_post_unchanged=True,
            old_batch_status=old['status'],old_batch_aborted=old['aborted'],old_pins_field=old['pins_unchanged'],
            actual_original_worker_exit=service,new_DUT=False,new_Spike=False,retry=False,
            elapsed_s=time.monotonic()-started,full_Linux_or_family_closure=False)
        save(OUT/'result.json',result)
        print(json.dumps({k:result[k] for k in ('status','checks','rows','retired','memory_owners','verified_pins','elapsed_s')}),flush=True)
        return 0
    except BaseException as e:
        save(OUT/'firstfailure.json',dict(error=f'{type(e).__name__}: {e}',traceback=traceback.format_exc(),
             completed_cases=len(results),row=q.rows if q else None,retired=q.retired if q else None,
             no_retry=True,elapsed_s=time.monotonic()-started))
        traceback.print_exc()
        return 1

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--review',type=Path,required=True)
    p.add_argument('--review-sha256',required=True)
    a=p.parse_args()
    raise SystemExit(main(a.review.resolve(),a.review_sha256))
