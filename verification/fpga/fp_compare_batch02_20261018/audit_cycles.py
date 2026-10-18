#!/usr/bin/env python3
"""Check the measured source-layout cause and corrected operand stream."""
import csv
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
INPUTS=[0,0x80000000,0x3f800000,0xbf800000,0x3f000000,0x40000000,0x40400000,0x33800000,
        1,0x7fffff,0x800000,0x7f7fffff,0x7f800000,0xff800000,0x7fc12345,0x7f812345]


def load(name):return json.loads((HERE/name/'events.json').read_text())


def target(rows):
    return [r for r in rows if r['backend_req_arch_insn']==0x72805457 and r['backend_req_op']==95 and
            r['d_backend_valid']==r['d_ara_req_ready_i']==1]


def operands(rows):
    return [r for r in rows if all(r[f'l{i}_vfpu_in_valid']==r[f'l{i}_vfpu_in_ready']==1 for i in range(4))]


def main():
    before,after=load('cycle_before02'),load('cycle_fixed01')
    a,b=target(before),target(after)
    assert len(a)==len(b)==1
    assert a[0]['eew_v8']==0 and a[0]['backend_req_eew_vs2']==2 and a[0]['d_reshuffle_req_d']==0
    assert b[0]['eew_v8']==2 and b[0]['backend_req_eew_vs2']==2
    old,new=operands(before),operands(after)
    assert len(old)==len(new)==8
    mismatches=0
    for beat,(previous,current) in enumerate(zip(old,new)):
        for lane in range(4):
            index=8*beat+lane
            wanted=INPUTS[index%16] | INPUTS[(index+4)%16]<<32
            assert current[f'l{lane}_operand_a']==wanted,(beat,lane,hex(wanted),current)
            assert current[f'l{lane}_operand_b']==0
            mismatches += previous[f'l{lane}_operand_a']!=wanted
    assert mismatches>0
    assert not any(r['m_fflags_valid_o']==1 and r['m_fflags_o']==16 for r in before)
    assert any(r['m_fflags_valid_o']==1 and r['m_fflags_o']==16 for r in after)
    converted=[dict(time_ns=r['time_ns'],op=r['backend_req_op'],reg=r['backend_req_vd']) for r in after
               if r['d_backend_valid']==r['d_ara_req_ready_i']==1 and r['backend_req_arch_insn']==0x72805457 and r['backend_req_op']!=95]
    result=dict(status='PASS_CAUSE_AND_CORRECTED_SOURCE_STREAM',
        before_issue_ns=a[0]['time_ns'],after_issue_ns=b[0]['time_ns'],
        conversion_delay_cycles=b[0]['time_ns']-a[0]['time_ns'],
        source_beats=8,lane_words_checked=32,old_mismatching_lane_words=mismatches,
        normalization_requests=converted,
        source_sha256={str(HERE/n/'comparison.vcd'):hashlib.sha256((HERE/n/'comparison.vcd').read_bytes()).hexdigest()
                       for n in ('cycle_before02','cycle_fixed01')},
        scope='One deterministic Linux-layout derivative; not proof of the exact interruption point in archived board execution')
    (HERE/'cycle_cause.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
