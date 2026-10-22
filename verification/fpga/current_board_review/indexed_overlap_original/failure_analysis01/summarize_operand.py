#!/usr/bin/env python3
"""Check both physical layouts against original indices; bind offline finding."""
import json
from analyze import HERE, sha, save

h = json.loads((HERE/'handshakes.json').read_text())
l = json.loads((HERE/'ledger.json').read_text())
indices = l['helpers'][0]['indices']
events = {e['ns']:e for e in h['late_lane_handshakes']}

def word(ns):
    e = events[ns]
    assert all(x['queue_push'] == 1 for x in e['lanes'])
    return [x['values']['operand_queue_input[8]'] for x in e['lanes']]

def ew32_unshuffle(words):
    halves = [part for w in words for part in (w & 0xffffffff, w >> 32)]
    ordered = halves[::2] + halves[1::2]
    return [ordered[i] | ordered[i+1] << 32 for i in range(0,8,2)]

first = word(367663.5)
second = word(367664.5)
assert ew32_unshuffle(first) == indices[12:16]
assert second == indices[16:20]
assert ew32_unshuffle(second)[0] == int(h['static_ew32_deshuffle_first_index'],16)
assert first != indices[12:16]
reqs = h['allocated_sequencer_requests']
assert [r['op_name'] for r in reqs[:4]] == ['VLE','VSLIDEDOWN','VSLIDEDOWN','VLXE']
assert len(reqs[4:]) == 16 and all(r['op_name']=='VLXE' for r in reqs[4:])
assert all(r['req']['source_snapshot_replay_vs2']==0 for r in reqs[4:])
last = reqs[-1]
assert last['req']['vstart']==15 and last['cycle']==367644
assert all(e['ns'] == e['cycle']+15.5 for e in reqs)
result = dict(
    status='MEASURED_MIXED_LAYOUT_QUEUE_WORDS_WITH_FIXED_EW32_DESCRIPTOR',
    actual_request_vstart=15, reported_fault_vstart=16,
    first_word=[hex(v) for v in first], first_word_ew32_decoded=[hex(v) for v in ew32_unshuffle(first)],
    next_word=[hex(v) for v in second], next_word_ew32_decoded=[hex(v) for v in ew32_unshuffle(second)],
    expected_indices_12_through_19=[hex(v) for v in indices[12:20]],
    queue_push_ns=[367663.5,367664.5], queue_push_csv_cycles=[367648,367649],
    last_request=last, no_retry_maintenance_allocations=True,
    no_late_snapshot_replay=True,
    missing_internal_reshuffle_bits=True, missing_addrgen_input_dequeue=True,
    architectural_failure_proven=True, dedup_boolean_path='STATIC_RECONSTRUCTION_NOT_DUMPED',
    no_rerun=True, no_rtl_change=True,
    evidence_pins={str(HERE/n):sha(HERE/n) for n in (
        'ledger.json','first_error.json','wave_fields.json','operand_probe.py','operand_probe.json',
        'handshakes.py','handshakes.json','OPERAND_FINDING.md','summarize_operand.py')},
)
save(HERE/'operand_finding.json',result)
print(json.dumps(dict(status=result['status'], output=str(HERE/'operand_finding.json'))))
