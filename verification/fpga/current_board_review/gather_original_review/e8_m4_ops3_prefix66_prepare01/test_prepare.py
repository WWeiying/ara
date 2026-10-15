#!/usr/bin/env python3
"""Bounded static/model checks; execution mutations live in the original-C host shim."""
import json
from pathlib import Path

from reference_check import model, prefix, require
from scope import *


def validate(source):
    tests = []
    def checked(name, condition):
        require(condition, name)
        tests.append(dict(name=name,status='PASS'))

    gold = model()
    checked('scope_units_and_distinct_ids', SOURCE_LABEL != RUNTIME_ID and
            (CAP,LMUL_REGS,VTYPE,SETUP_VALUES,RESULT_CHECKS,GUARD_CHECKS,
             ORACLE_LOADS,HELPER_INSTRUCTIONS)==(512,4,2,2178,33792,132,33924,858))
    expected = []
    for length in range(7):
        for mode in range(4):
            for trial in range(4):
                expected.append([0,3,0,length,mode,trial])
    checked('original_order_and65_predecessors',
            [r['tuple'] for r in gold['rows']]==expected[:66] and gold['rows'][-1]['tuple']==ENDPOINT)
    prior = Path(__file__).resolve().parent.parent/'stall_prefix2_03/gather_prefix_e8_m4_ops1.host_expected.json'
    saved = json.loads(prior.read_text())
    checked('archived_cap512_fixture_setup_identity', all(gold[k]==saved[k]
            for k in ('input','indices','indices16')))
    checked('physical128_clear_and_logical64',
            'static uint8_t predicate[128];' in source and
            'for(unsigned i=0;i<128;++i)predicate[i]=0;' in source and
            all(len(r['predicate'])==128 and r['predicate'][64:]==[0]*64 for r in gold['rows']))
    # Independent byte oracle reads mask bytes, not the model's selection branch.
    for row in gold['rows']:
        expected_bytes = bytearray([0x5b])*CAP
        for i in range(CAP):
            enabled = (row['predicate'][i//8] >> (i%8)) & 1
            if row['vstart'] <= i < row['vl'] and enabled:
                expected_bytes[i] = 177
        require(bytes(row['output'])==bytes(expected_bytes), 'Independent byte oracle differs')
    checked('independent_full33792_byte_oracle',gold['input'][31]==177 and gold['input'][0]==185)
    end=gold['rows'][-1]
    checked('endpoint_and_VL1_source31_valid',
            (end['vl'],end['vstart'])==(256,128) and
            end['output']==[91]*128+[177]*128+[91]*256 and
            gold['rows'][17]['vl']==1 and gold['rows'][17]['output'][0]==177)
    port=prefix(source,BOUND)
    anchor='            ++cases;\n'
    loop='    for(unsigned seed='
    checked('original_loop_body_unchanged', source[source.index(loop):source.index(anchor)+len(anchor)]==
            port[port.index(loop):port.index(anchor)+len(anchor)])
    checked('original_exit_and_stats_retained',
            'syscall3(94,errors ? 1:0,0,0);for(;;){}' in port and
            port.count('if(cases==66)goto prefix_done;')==1 and port.count('if(cases!=66)++errors;')==1)
    for wrong in (65,67,98):
        try:
            prefix(source,wrong)
        except ValueError:
            continue
        raise ValueError('Wrong boundary accepted')
    checked('negative_non66_boundary_rejected',True)
    return tests


if __name__=='__main__':
    source=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c')
    print(json.dumps(validate(source.read_text()),indent=2))
