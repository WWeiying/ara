"""One closed-CSV full-original16 independent successor acceptance."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
WORKER=HERE.parent/'zero_stride_e64_m2_original16_vcs_m7_plan01'
sys.path.insert(0,str(WORKER))
import checker as c
import replay as app
import csv_check_successor as cc
def main():
    out=WORKER/'prepared01';plan=c.read(out/'plan.json');root=out/'replay/tests'/c.NAME
    app.disk_gate(out,c.sha(out/'plan.json'),c.IMAGE)
    c.require(c.read(HERE.parent/'zero_stride_e64_m2_original16_offline_recovery01/execution.json')['actual_wait_exit']==1,'Preserve prior incomplete offline attempt')
    old=c.read(out/'complete.json');num=c.read(root/'monitor_numeric.unvalidated.json');child=c.read(root/'child_outcome.unvalidated.json')
    c.require(old['status']=='NOT_PASS' and old['aborted'] and old['results'][0]['status']=='ERROR','Retain actual old terminal')
    c.require(num['returncode']==0 and not any(num[k] for k in ('timed_out','failure_seen','abort_set')) and child['status']=='PASS' and child['returncode']==0,'Actual numeric/child gates')
    for n in ('console.log','work/run.vcs.log'):c.console_gate((root/n).read_text())
    generic=c.read(root/'trace_summary.json')
    c.require(generic['status']=='VALID' and generic['cvx_exception_count']==12 and generic['backend_uop_alloc_count']==generic['backend_uop_done_count'],'Old frozen complete protocol')
    pins=dict(plan['pins'])
    files=[out/'plan.json',out/'complete.json',out/'replay/run.json',out/'replay/summary.json',HERE/'host.json']
    files+=[root/n for n in ('monitor_numeric.unvalidated.json','monitor_outcome.unvalidated.json','child_outcome.unvalidated.json','command.json','inputs.json','input.elf','console.log','work/run.vcs.log','commit_trace.csv','trace_summary.json','terminal_original16.json')]
    files+=list(HERE.glob('*.py'))
    pins.update({str(p):c.sha(p) for p in files});c.common.base.verify_pins(pins);c.common.save(HERE/'input_pins.json',pins)
    result=cc.analyze(root/'commit_trace.csv',plan['spec'])
    c.common.save(HERE/'full_oracle.json',result)
    c.common.base.verify_pins(pins)
    c.require(result['status']=='PASS_ORIGINAL16_FULL_ORACLE',str(result))
    c.require((result['rows'],result['retired'],result['last_cycle'])==(generic['rows'],generic['retire_count'],generic['last_cycle']),'Closed CSV/generic exact counts')
    c.common.save(HERE/'terminal.json',dict(status='ARCHITECTURAL_DATA_ACCEPTED_OFFLINE_OLD_PRODUCER_NOT_PASS',
      source_cases=16,outputs=512,guards=32,memory_words=16384,checks=18188,faults=12,ecalls=16,
      actual_dut_returncode=0,actual_dut_seconds=num['elapsed_s'],raw_csv_parses=1,retries=0,
      old_terminal_sha256=pins[str(out/'complete.json')],old_terminal_status='NOT_PASS',
      pins_pre_post_unchanged=True,full_oracle_sha256=c.sha(HERE/'full_oracle.json'),
      input_pins_sha256=c.sha(HERE/'input_pins.json'),historical_linux_stall_closed=False,new_DUT_execution=False))
    print('ARCHITECTURAL_DATA_ACCEPTED_OFFLINE_OLD_PRODUCER_NOT_PASS')
if __name__=='__main__':main()


