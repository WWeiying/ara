#!/usr/bin/env python3
"""Host-only negative and field-partial validity checks; never starts a simulator."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import reference as ref


def main():
    geometry=ref.load_geometry()
    symbols=json.loads((ref.HERE/'reference01/group00/spike.symbols.json').read_text())
    cases=geometry['cases']
    negative=[]
    for trial in (0,1,4,24,25,48,72,73,92,93):
        negative.extend((trial,name) for name in ref.negatives(symbols,[cases[trial]]))
    # Partial fields are permitted only in the fault-phase oracle, not final state.
    for trial in (1,25,49,73):
        c=cases[trial]; start=c['expected_vstart']
        fault=ref.expected(symbols,c,1); final=ref.expected(symbols,c,2)
        for f in range(7):
            a=symbols['ix_fault']+64+(f+2)*128+start*4
            if c['store']:
                assert a in fault, 'Store source register must remain exact'
            else:
                assert a not in fault, 'Do not assert fault-element load atomicity'
            a=symbols['ix_result']+64+(f+2)*128+start*4
            assert a in final, 'Final field cannot become unspecified'
            for i in c['completed_active_prefix']:
                assert symbols['ix_fault']+64+(f+2)*128+i*4 in fault
            a=symbols['ix_pages']+c['field_offsets'][start][f]
            assert (a in fault) == (not c['store'] or c['field_offsets'][start][f]>=4096)
    for c in cases:
        phase=2; want=ref.expected(symbols,c,phase)
        assert len(c['index_offsets'])==8 and len(set(c['index_offsets']))==8
        for f in range(7):
            for i in range(8,32):
                assert symbols['ix_result']+64+(f+2)*128+i*4 in want
        if c['expected_cause'] is None:
            for i in range(1408):
                assert symbols['ix_fault']+i in want
    path=ref.HERE/'host_tests01.json'
    assert not path.exists(), 'Preserve prior host evidence'
    ref.base.save(path,dict(status='HOST_NEGATIVES_AND_PARTIAL_RULES_PASS_NOT_DUT',
        rejected=negative,trials_checked=96,partial_rule_trials=[1,25,49,73],
        pins={str(p):ref.base.sha(p) for p in [Path(__file__),Path(ref.__file__),ref.GEOMETRY]},
        VCS_launched=False))
    print('HOST_NEGATIVES_AND_PARTIAL_RULES_PASS_NOT_DUT',len(negative))


if __name__=='__main__':
    main()
