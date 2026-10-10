"""Physical event census only: distinguish speculative outputs from architectural retirement."""
import json
from collections import Counter
from pathlib import Path
import collect_scalar_c910_pattern795 as c


def summarize(document):
    events=document['audit']['raw_events'];scheduled=None;live={};completed=[];canceled=[];flushes=[]
    for row in events:
        root=row['root'];time=row['time']
        if root['fpu_valid_o']:
            tid=root['fpu_trans_id_o'];c.require(tid in live,'Raw output needs physical owner')
            owner=live.pop(tid);completed.append(dict(owner,output_time=time,result=row['result']))
        if root['flush_i']:
            c.require(not live and not row['issue_valid'] and not row['gen']['hold_inputs'] and not row['gen']['use_hold'],
                'Raw flush cannot conceal remaining physical owner')
            if root['fpu_valid_i']:
                c.require(scheduled is not None and row['fu_input']['trans_id']==scheduled['tid'] and
                    row['fu_input']['operation']==scheduled['op'],'Exact same-edge canceled owner')
                canceled.append(dict(scheduled,cancel_time=time))
            else:c.require(scheduled is None,'No unseen registered input')
            scheduled=None;flushes.append(time);continue
        if root['fpu_valid_i']:
            c.require(scheduled is not None and row['gen']['fpu_in_ready']==1,'Registered physical issue/input')
            fu=row['fu_input'];tid=fu['trans_id']
            c.require(tid==scheduled['tid'] and fu['operation']==scheduled['op'] and tid not in live,
                'Physical opcode/TID conservation')
            live[tid]=dict(scheduled,input_time=time);scheduled=None
        if row['issue_valid']:
            c.require(scheduled is None,'One next-edge physical schedule')
            s=row['issue'];fu=row['fu_issue']
            c.require(s['trans_id']==fu['trans_id'] and s['op']==fu['operation'],'Raw PC/TID/op bound')
            scheduled=dict(pc=s['pc'],tid=s['trans_id'],op=s['op'],issue_time=time)
    c.require(not live and scheduled is None,'Raw physical owner census closes')
    def counts(items):return {hex(pc):n for pc,n in Counter(r['pc'] for r in items).items()}
    expected=c.expected_requests(c.life.read_bound(c.runner.PRE/'preflight.json',c.runner.PRE_SHA))
    return dict(status='PHYSICAL_CENSUS_NOT_GOLD_OR_RETIREMENT_QUALIFICATION',
        physical_issues=len(completed)+len(canceled),physical_completed=len(completed),
        same_edge_flush_input_cancellations=len(canceled),flush_count=len(flushes),
        completed_PC_counts=counts(completed),canceled_PC_counts=counts(canceled),
        architectural_PC_counts=counts(expected),same_edge_flush_input_ready_count=sum(
            r['root']['flush_i']==1 and r['root']['fpu_valid_i']==1 and r['gen']['fpu_in_ready']==1 for r in events),
        same_edge_flush_output_count=sum(r['root']['flush_i']==1 and r['root']['fpu_valid_o']==1 for r in events),
        physical_remaining_live=0,held_edges=0,completed=completed,canceled=canceled)


if __name__=='__main__':
    path=c.life.OUT/'scalar-c910-pattern795-schedule-diagnostic-agent-20261008-01.json'
    doc=json.loads(path.read_text());result=summarize(doc)
    out=c.life.OUT/'scalar-c910-pattern795-physical-census-agent-20261008-01.json'
    c.life.save(out,dict(audit=result,input_sha256=c.life.digest(path),
        source_sha256=c.life.digest(Path(__file__)),new_simulation=False,coverage_admitted=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ('completed','canceled')},indent=2))
