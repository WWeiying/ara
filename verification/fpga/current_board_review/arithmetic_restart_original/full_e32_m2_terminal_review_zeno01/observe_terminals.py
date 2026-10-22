"""Two ordered bounded inotify observers; no simulated job control."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
A=HERE.parent
WAITER=A.parent/'wait_terminal.py'
ITEMS=[(HERE,A/'full_e32_m2_block_vcs_m9_plan01/prepared01'),
    (A/'full_e64_m2_terminal_review_zeno01',A/'full_e64_m2_vcs_m9_plan01/prepared01')]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def child_wait(command,out,limit):
    start=time.monotonic();timed=False
    with out.with_suffix('.log').open('x') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=limit)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        record=dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,
            timed_out=timed,command=command,retries=0)
        save(out,record)
    return record
binding=json.loads((HERE/'OBSERVER_READY.json').read_text())
for p,d in binding['pins'].items():
    if sha(Path(p))!=d:raise ValueError('Observer input drift: '+p)
for directory,prepared in ITEMS:
    started=time.monotonic();target=prepared/'collector_result.json';present=target.is_file()
    save(directory/'watch01.json',dict(target=str(target),target_already_present=present,
        observation_bound_s=6000,observer_only_no_simulation_extension=True,pid=os.getpid(),started=time.time(),
        waiter=str(WAITER),waiter_sha256=sha(WAITER),no_CPU_or_active_CSV_queries=True))
    status='ALREADY_PRESENT'
    if not present:
        result=child_wait([sys.executable,'-B',str(WAITER),str(target),'--timeout','6000'],
            directory/'wait_result01.json',6010)
        status='FILE_EVENT' if result['actual_wait_returncode']==0 and not result['timed_out'] else 'OBSERVATION_TIMEOUT_OR_ERROR_NOT_JOB_TERMINAL'
    if status=='OBSERVATION_TIMEOUT_OR_ERROR_NOT_JOB_TERMINAL':
        save(directory/'OBSERVATION.json',dict(status=status,DUT_terminal_inferred=False,restart=False))
        continue
    # The result is published just before collector wait is saved. Wait for the
    # close-write of that receipt, without CPU/CSV reads or timed stat polling.
    receipt=prepared/'collector_exit.json'
    if not receipt.is_file():
        remaining=6000-(time.monotonic()-started)
        if remaining<=0:
            save(directory/'OBSERVATION.json',dict(status='OBSERVATION_TIMEOUT_NOT_JOB_TERMINAL',DUT_terminal_inferred=False,restart=False))
            continue
        result=child_wait([sys.executable,'-B',str(WAITER),str(receipt),'--timeout',str(remaining)],
            directory/'collector_receipt_wait01.json',remaining+10)
        if result['actual_wait_returncode']!=0 or result['timed_out']:
            save(directory/'OBSERVATION.json',dict(status='OBSERVATION_TIMEOUT_NOT_JOB_TERMINAL',DUT_terminal_inferred=False,restart=False))
            continue
    review=directory/'review_metadata.py'
    if sha(review)!=binding['pins'][str(review)]:raise ValueError('Review code drift')
    result=child_wait([sys.executable,'-B',str(review)],directory/'review_execution01.json',300)
    save(directory/'OBSERVATION.json',dict(status='TERMINAL_METADATA_REVIEW_COMPLETED' if result['actual_wait_returncode']==0 else 'TERMINAL_METADATA_REVIEW_NOT_ACCEPTED',
        event=status,review_returncode=result['actual_wait_returncode'],review_timeout=result['timed_out'],
        DUT_terminal_inferred_only_from_actual_terminal_metadata=True,restart=False,no_auto_retry=True))
save(HERE/'OBSERVER_COMPLETE.json',dict(status='TWO_ORDERED_OBSERVATIONS_FINISHED',finished=time.time(),
    no_new_DUT_or_reference=True,no_CPU_or_active_CSV_queries=True))

