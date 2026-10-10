"""One sealed no-hold wave: input supply versus measured arbitration, no EDA."""
import argparse
from collections import Counter
from pathlib import Path
from types import FunctionType

import collect_scalar_fpu_fma_arbiter792 as c

life,require=c.life,c.require
QSHA='0b30ba04bd032c2311b67d9babfcadd43752e911623c0a31db23a96dc3f176a6'


def analyze(directory):
    q=life.read_bound(directory/'qualification.json',QSHA)
    require(q['status']=='FULL_ARCHITECTURE_FMA_HOLD_NOT_TRIGGERED_NO_RETRY_NOT_ADMITTED' and
        q['FMA_audit']['FMA_hold_count']==q['FMA_audit']['stall_cycles']==0,'Exact no-hold qualification')
    wave=directory/'probe.vcd';life.check(q['output_pins'])
    proof=c.runner.source_contract()
    book=life.read_bound(c.oracle.old.BUILD/'build-source-pins.json',c.oracle.old.SOURCE_SHA)
    source_pins={}
    anchors={
        'hardware/deps/fpnew/src/fpnew_top.sv':
            ['assign in_ready_o = in_valid_i & opgrp_in_ready[fpnew_pkg::get_opgroup(op_i)];',
             '.gnt_o  ( opgrp_out_ready )'],
        'hardware/deps/fpnew/src/fpnew_opgroup_block.sv':
            ['assign in_ready_o = in_valid_i & fmt_in_ready[dst_fmt_i];'],
        'hardware/deps/fpnew/src/fpnew_fma.sv':
            ['assign in_ready_o = inp_pipe_ready[0];',
             'assign out_pipe_ready[NUM_OUT_REGS] = out_ready_i;']}
    for rel,needles in anchors.items():
        p=life.ROOT/rel;require(life.digest(p)==book[str(p)],'Frozen ready/arbiter source')
        require(all(s in p.read_text() for s in needles),'Ready and arbitration source contract')
        source_pins[str(p)]=book[str(p)]
    parse=c.oracle.prior.wave.vcd
    parser=FunctionType(parse.__code__,dict(parse.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    stream=iter(parser(wave));_,decl=next(stream)
    def value(state,path):
        bits=state.get(decl[path]['code'],'x')
        require(set(bits)<=set('01'),'Unknown sampled control '+path)
        return int(bits,2)
    counts=Counter({n:0 for n in ('FP64_format_input_not_ready_cycles','state_STALL','hold_inputs',
        'use_hold','valid_and_input_not_ready','ADDMUL_output_denied_cycles',
        'ADDMUL_denied_with_other_group_valid','FP64_output_valid_denied')})
    intervals=Counter();requests=[];collisions=[];closed=[];last=None;cycle=0
    for time,before,after in stream:
        if before.get(decl['ara_tb.clk']['code'])!='0' or after.get(decl['ara_tb.clk']['code'])!='1':continue
        cycle+=1
        if before.get(decl['ara_tb.rst_n']['code'])!='1':continue
        root=lambda n:value(before,c.SCOPE+'.'+n)
        gen=lambda n:value(before,c.GEN+'.'+n)
        bulk=lambda n:value(before,c.BULK+'.'+n)
        ov,ready=bulk('opgrp_out_valid'),bulk('opgrp_out_ready')
        counts['sampled_cycles']+=1
        counts['state_STALL']+=root('state_q')
        counts['hold_inputs']+=gen('hold_inputs')
        counts['use_hold']+=gen('use_hold')
        if ov&1 and not ready&1:
            counts['ADDMUL_output_denied_cycles']+=1
            competing=ov&~1
            counts['ADDMUL_denied_with_other_group_valid']+=int(bool(competing))
            if len(collisions)<12:collisions.append(dict(time=time,cycle=cycle,valid_mask=ov,
                granted_mask=ready,request_valid=root('fpu_valid_i'),input_ready=gen('fpu_in_ready')))
        fmt=c.BULK+'.gen_operation_groups[0].i_opgroup_block.'
        fv,fr=value(before,fmt+'fmt_out_valid'),value(before,fmt+'fmt_out_ready')
        counts['FP64_output_valid_denied']+=int(bool(fv&2 and not fr&2))
        if not value(before,fmt+'fmt_in_ready')&2:
            counts['FP64_format_input_not_ready_cycles']+=1
            if len(closed)<12:closed.append(dict(time=time,cycle=cycle,request_valid=root('fpu_valid_i')))
        if root('fpu_valid_i'):
            op=gen('fpu_op_d');reverse={v:k for k,v in proof['fpnew_ops'].items()}
            require(op in reverse,'Unexpected input operation')
            name=reverse[op];counts['requests_'+name]+=1
            counts['valid_and_input_not_ready']+=int(not gen('fpu_in_ready'))
            require(gen('fpu_in_ready')==root('fpu_ready_o')==1,'No-hold input acceptance')
            if last is not None:intervals[cycle-last]+=1
            last=cycle
            requests.append(dict(time=time,cycle=cycle,op=name,tag=gen('fpu_tag_d'),
                output_valid_mask=ov,output_grant_mask=ready))
    require(len(requests)==50 and counts['requests_FMADD']==40 and counts['requests_DIV']==2 and
        counts['requests_CLASSIFY']==8 and counts['valid_and_input_not_ready']==counts['hold_inputs']==0,
        'Complete50 accepted requests and no holding')
    return dict(status='READONLY_MEASURED_FMA_NO_HOLD_DIAGNOSIS_NOT_ADMITTED',
        qualification_seal=QSHA,counts=dict(counts),request_gap_cycles=dict(sorted(intervals.items())),
        requests=requests,denied_output_examples=collisions,closed_input_examples=closed,
        conclusion='Two output arbitration denials did not close the FP64 input pipeline. All50 requests '
            'were accepted and FP64 fmt_in_ready[1] remained1 on every sampled nonreset edge; no valid&&!ready.',
        source_facts=anchors,cycle_numbering='Local rising-edge index including reset; not architectural commit cycle',
        attribution_limit='No internal stage occupancy or issue hazard probes: cannot uniquely attribute supply gaps '
            'to WAW/scoreboard versus instruction supply. No claim that hold is structurally unreachable.',
        FMA_hold_triggered=False,advertised_hold_coverage=False,retry=False,admission_prepared=False,
        pins=life.merge_pins(life.merge_pins(proof['pins'],source_pins),
            {str(directory/'qualification.json'):QSHA,str(wave):q['output_pins'][str(wave)],
             str(Path(__file__).resolve()):life.digest(Path(__file__))}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--qualification',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=analyze(a.qualification.resolve());life.check(result['pins']);life.save(a.output,result)
    print(result['counts']);print(result['request_gap_cycles']);print(life.digest(a.output))
