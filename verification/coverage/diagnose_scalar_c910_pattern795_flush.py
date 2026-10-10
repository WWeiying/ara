"""Read-only first rejection evidence from the unchanged owner implementation."""
import argparse
import json
import sys
from pathlib import Path
from types import FunctionType
import collect_scalar_c910_pattern795 as c


def diagnose(wave):
    implementation=c.owner_implementation();evidence={};history=[]
    paths=[c.SCOPE+'.'+n for n in ('flush_i','state_q','fpu_valid_i','fpu_ready_o','fpu_valid_o','fpu_trans_id_o','result_o')]
    paths += [c.SCOPE+'.fpu_gen.'+n for n in ('fpu_in_valid','fpu_in_ready','hold_inputs','use_hold','fpu_tag_d','fpu_tag_q')]
    paths += [c.ISSUE+'.fpu_valid_n']
    def trace(frame,event,arg):
        if frame.f_code is not implementation.__code__:return None
        frame.f_trace_lines=False
        if event=='exception' and not evidence:
            local=frame.f_locals
            if isinstance(arg[1],ValueError):
                read=local['read'];before=local['before'];after=local['after']
                def values(state):
                    result={}
                    for path in paths:
                        try:result[path]=read(state,path)
                        except ValueError:result[path]='UNKNOWN'
                    return result
                evidence.update(reason=str(arg[1]),time=local['time'],live=local['live'],
                    pending=local['pending'],scheduled=local['scheduled'],issued=local['issued'],
                    schedule_count=local['schedule_count'],completed=local['completed'][-8:],
                    expected_next=local['expected'][local['issued']] if local['issued']<len(local['expected']) else None,
                    before=values(before),after=values(after),previous_edges=history[-8:])
        return trace
    def audit(decl,edges,expected,proof):
        def tracked():
            for time,before,after in edges:
                row={'time':time}
                for path in paths:
                    value=before.get(decl[path]['code'],'x')
                    row[path]=int(value,2) if set(value)<=set('01') else value
                history.append(row)
                if len(history)>16:history.pop(0)
                yield time,before,after
        previous=sys.gettrace();sys.settrace(trace)
        try:return implementation(decl,tracked(),expected,proof)
        finally:sys.settrace(previous)
    wave_fn=FunctionType(c.frozen.wave_audit.__code__,dict(c.frozen.wave_audit.__globals__,
        probe_widths=c.probe_widths,expected_requests=c.expected_requests,audit_edges=audit))
    pre=c.life.read_bound(c.runner.PRE/'preflight.json',c.runner.PRE_SHA)
    try:wave_fn(wave,c.runner.source_contract(),pre)
    except ValueError:
        if not evidence:raise
    return evidence


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--wave',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=diagnose(a.wave)
    c.require(result,'Actual first rejection required')
    c.life.save(a.output,dict(status='FIRST_REJECTION_DIAGNOSTIC_NOT_QUALIFICATION',evidence=result,
        wave=str(a.wave.resolve()),wave_sha256=c.life.digest(a.wave),source_sha256=c.life.digest(Path(__file__)),
        coverage_admitted=False,new_simulation=False))
    print(json.dumps(result,indent=2))
