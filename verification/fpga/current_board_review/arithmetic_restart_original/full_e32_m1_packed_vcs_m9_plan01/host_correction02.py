"""One short correction to a negative's expected diagnostic, no full replay."""
import json
import re
import checker as c
import replay as r
from host_records import Builder

FAILED='test_first_sd_stale_matching_shadow_still_rejected'

def original_gate():
    host=c.read(c.HERE/'host01.json');exit=c.read(c.HERE/'host01_process_exit.json')
    command=c.read(c.HERE/'host01_command.json')
    c.require(host['status']=='FAIL_HOST_ONLY' and host['tests']==33 and host['failures']==1 and
        exit['returncode']==1 and type(exit['returncode']) is int and exit['timed_out'] is False and
        exit['pins_unchanged'] is True and exit['retries']==0,'Preserved original actual Host failure')
    c.common.base.verify_pins(host['pins']);c.common.base.verify_pins(command['pins'])
    log=(c.HERE/'host01.log').read_text()
    starts=list(re.finditer(r'^(test_\w+) \(__main__\.Host\) \.\.\. ',log,re.M))
    statuses={}
    for i,start in enumerate(starts):
        block=log[start.end():starts[i+1].start() if i+1<len(starts) else len(log)]
        outcomes=re.findall(r'^(ok|FAIL|ERROR)$',block,re.M)
        c.require(len(outcomes)==1 and start[1] not in statuses,'Exact unique original unittest outcomes')
        statuses[start[1]]=outcomes[0]
    c.require(len(statuses)==33 and [name for name,status in statuses.items() if status!='ok']==[FAILED] and
        statuses[FAILED]=='FAIL','Only corrected diagnostic expectation failed')
    c.require('ValueError: Complete output fresh/prior reads' in log and
        'AssertionError: "Deleted fresh" does not match "Complete output fresh/prior reads"' in log and
        'Ran 33 tests' in log and 'FAILED (failures=1)' in log and
        'HOST_STAGE full_stream_complete' in log and "'calls': 5985" in log and
        statuses['test_full5985_complete_data']==statuses['test_actual_elf_abi']=='ok',
        'Original complete positive/ABI and sole diagnostic failure evidence')
    return statuses

def short_negative():
    original_gate()
    state=c.Strict(c.specification());builder=Builder(state.spec)
    for row in builder.records():
        state.consume(row)
        if state.init_index==1:break
    c.require(state.life.output_stores==state.init_index==1 and not state.calls,'Exact first SD prefix')
    for i,value in enumerate(c.lifecycle.words([91]*34)):state.memory[state.s['out']+i]=value
    builder=Builder(state.spec);builder.order=state.retired;builder.regs=state.regs.copy()
    for reg,value in enumerate([state.s['a'],state.s['b'],state.s['out']+4,0,32,state.s['mask'],0],10):
        state.consume(builder.setreg(reg,value))
    row=builder.row(state.helpers['op_0'][0]['pc'],5,32)
    try:state.consume(row)
    except ValueError as error:
        c.require(str(error)=='Complete output fresh/prior reads','Exact earlier strict lifecycle veto')
        return dict(status='CORRECTED_NEGATIVE_PASS_NO_CHECKER_CHANGE',firstcause=str(error),
            prefix_rows=state.rows,full_history_rerun=False,DUT_reference_compile_runs=0)
    raise ValueError('Missing initialization accepted')

if __name__=='__main__':
    report=short_negative()
    r.durable(c.HERE/'host02_result.json',report)
    print(json.dumps(report),flush=True)
