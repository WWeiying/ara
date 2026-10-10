"""First unchanged-v3 rejection and complete raw event-pattern census, no qualification."""
import argparse
from collections import Counter
import sys
from pathlib import Path
from types import FunctionType
import collect_scalar_c910_pattern795_v3 as v3

c=v3.c


def diagnose(wave):
    implementation=v3.owner_implementation();proof=c.runner.source_contract()
    pre=c.life.read_bound(c.runner.PRE/'preflight.json',c.runner.PRE_SHA)
    expected=c.expected_requests(pre);first={};events=[]
    parse=c.frozen.original.oracle.prior.wave.vcd
    parser=FunctionType(parse.__code__,dict(parse.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    stream=iter(parser(wave));_,decl=next(stream)
    def raw(state,path):
        bits=state.get(decl[path]['code'],'x');width=decl[path]['width']
        return bits.rjust(width,bits[0] if bits[0] in 'xz' else '0')
    def number(state,path,left=None,right=0):
        bits=raw(state,path);left=decl[path]['width']-1 if left is None else left
        part=bits[len(bits)-1-left:len(bits)-right]
        return int(part,2) if set(part)<=set('01') else part
    def fields(state,path,layout):return {name:number(state,path,left,right) for name,(left,right) in layout.items()}
    def record(time,before,after):
        roots={n:number(before,c.SCOPE+'.'+n) for n in ('flush_i','state_q','fpu_valid_i','fpu_valid_o','fpu_trans_id_o')}
        issue=number(before,c.ISSUE+'.fpu_valid_n')
        if issue or roots['flush_i'] or roots['fpu_valid_i'] or roots['fpu_valid_o']:
            row=dict(time=time,root=roots,issue_valid=issue,
                gen={n:number(before,c.SCOPE+'.fpu_gen.'+n) for n in ('fpu_in_valid','fpu_in_ready','hold_inputs','use_hold')})
            if issue:
                row['issue']=fields(before,c.ISSUE+'.issue_instr_i',proof['issue_layout']['fields'])
                row['fu_issue']=fields(before,c.ISSUE+'.fu_data_n',proof['fu_layout']['fields'])
                row['issue_raw']=raw(before,c.ISSUE+'.issue_instr_i');row['fu_issue_raw']=raw(before,c.ISSUE+'.fu_data_n')
            if roots['fpu_valid_i']:
                row['fu_input']=fields(before,c.SCOPE+'.fu_data_i',proof['fu_layout']['fields'])
            if roots['fpu_valid_o']:row['result']=number(before,c.SCOPE+'.result_o')
            events.append(row)
    def edges():
        for time,before,after in stream:
            if before.get(decl['ara_tb.clk']['code'])=='0' and after.get(decl['ara_tb.clk']['code'])=='1':
                if before.get(decl['ara_tb.rst_n']['code'])=='0':continue
                record(time,before,after);yield time,before,after
    def trace(frame,event,arg):
        if frame.f_code is not implementation.__code__:return None
        frame.f_trace_lines=False
        if event=='exception' and isinstance(arg[1],ValueError) and not first:
            local=frame.f_locals
            names=('time','issued','schedule_count','scheduled','pending','live','pc','tid','fu','e','output_consumed')
            first.update(reason=str(arg[1]),locals={n:local[n] for n in names if n in local},
                completed=local['completed'][-8:],prior_events=events[-12:])
        return trace
    source=edges();old=sys.gettrace();sys.settrace(trace)
    try:implementation(decl,source,expected,proof)
    except ValueError:
        if not first:raise
    finally:sys.settrace(old)
    # No further checker execution or permissive acceptance: raw-only census of remaining edges.
    for _ in source:pass
    patterns=Counter((r['root']['flush_i'],r['issue_valid'],r['root']['fpu_valid_i'],r['root']['fpu_valid_o'],
        r['gen']['hold_inputs'],r['gen']['use_hold']) for r in events)
    return dict(first_rejection=first,raw_event_patterns=[dict(pattern=list(k),count=v) for k,v in patterns.items()],
        pattern_fields=['flush','issue_valid','input_valid','output_valid','hold_inputs','use_hold'],
        raw_events=events,expected_PC_counts=dict(Counter(str(e['pc']) for e in expected)),
        no_remaining_events_qualified=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--wave',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=diagnose(a.wave)
    c.life.save(a.output,dict(status='RAW_EVENT_CENSUS_AND_FIRST_REJECTION_ONLY_NOT_QUALIFIED',audit=result,
        wave_sha256=c.life.digest(a.wave),source_sha256=c.life.digest(Path(__file__)),coverage_admitted=False,new_simulation=False))
    import json
    print(json.dumps(dict(first=result['first_rejection'],patterns=result['raw_event_patterns']),indent=2))
