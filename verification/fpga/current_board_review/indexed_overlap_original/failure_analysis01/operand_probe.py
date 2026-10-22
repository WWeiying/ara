#!/usr/bin/env python3
"""Offline queue-input and metadata extraction from the existing pilot VCD."""
import json
import re
from analyze import HERE, sha, save

vcd = HERE / 'compact.vcd'
prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.'
selected, declarations, state, changes = {}, {}, {}, {}
scopes, late, transitions, requests = [], [], [], []
lo, hi = 3676400000, 3676950000

def label(scopes, tokens):
    n = '.'.join(scopes + [tokens[4]])
    if len(tokens) > 6:
        n += re.sub(r'\[\d+:\d+\]$', '', tokens[5])
    return n.removeprefix(prefix)

def choose(n):
    if n.startswith('i_vlsu.i_addrgen.'):
        return True
    if n.startswith('i_dispatcher.'):
        return ('snapshot' in n or n in ('i_dispatcher.eew_q[4]', 'i_dispatcher.eew_q[5]'))
    if re.match(r'gen_lanes\[[0-3]\]\.i_lane\.', n):
        leaf = n.split('.i_lane.', 1)[1]
        return (leaf in ('operand_queue_input[8]', 'operand_queue_input_valid',
                         'vrf_operand[8]', 'vrf_operand_valid',
                         'operand_request_valid', 'operand_request_ready',
                         'source_snapshot_replay_valid', 'source_snapshot_replay_index[8]',
                         'source_snapshot_capture_q', 'source_snapshot_capture_index_q',
                         'source_snapshot_q[4]') or
                leaf.startswith(('operand_request[8].',
                    'i_operand_requester.requester_metadata_q[8].',
                    'i_operand_requester.operand_queue_cmd_o[8].')))
    return False

def number(v):
    return int(v, 2) if set(v) <= {'0', '1'} else v

def emit(t):
    if not changes or t is None:
        return
    if lo <= t <= hi:
        late.append(dict(ticks=t, ns=t / 10000, changed=dict(changes), values=dict(state)))
    if 3574000000 <= t <= hi:
        notable = {k:v for k,v in changes.items() if k.startswith('i_dispatcher.') or
                   k in ('i_vlsu.i_addrgen.pe_req_q.vstart',
                         'i_vlsu.i_addrgen.pe_req_q.old_eew_vs2',
                         'i_vlsu.i_addrgen.pe_req_q.source_snapshot_replay_vs2')}
        if notable:
            transitions.append(dict(ns=t / 10000, changed=notable))
    changes.clear()

with vcd.open() as stream:
    for line in stream:
        s = line.split()
        if not s:
            continue
        if s[0] == '$scope':
            scopes.append(s[2])
        elif s[0] == '$upscope':
            scopes.pop()
        elif s[0] == '$var':
            n = label(scopes, s)
            if choose(n):
                assert n not in declarations, n
                declarations[n] = dict(code=s[3], width=int(s[2]))
                selected.setdefault(s[3], []).append(n)
        elif s[0] == '$enddefinitions':
            break
    t = None
    for line in stream:
        s = line.strip()
        if not s:
            continue
        if s[0] == '#':
            emit(t)
            t = int(s[1:])
            if t > hi:
                break
        elif s[0] in 'bB':
            value, code = s[1:].split()
            for n in selected.get(code, []):
                state[n] = changes[n] = number(value)
        elif s[0] in '01xXzZ':
            for n in selected.get(s[1:], []):
                state[n] = changes[n] = number(s[0])

inputs = []
previous = None
for event in late:
    v = event['values']
    data = []
    for lane in range(4):
        p = f'gen_lanes[{lane}].i_lane.'
        data.append(dict(lane=lane, valid=(v[p+'operand_queue_input_valid'] >> 8) & 1,
                         word=hex(v[p+'operand_queue_input[8]']),
                         vrf_valid=(v[p+'vrf_operand_valid'] >> 8) & 1,
                         vrf_word=hex(v[p+'vrf_operand[8]']),
                         replay=(v[p+'source_snapshot_replay_valid'] >> 8) & 1,
                         request_valid=(v[p+'operand_request_valid'] >> 8) & 1,
                         request_ready=(v[p+'operand_request_ready'] >> 8) & 1,
                         request={k[len(p+'operand_request[8].'):]:value for k,value in v.items()
                                  if k.startswith(p+'operand_request[8].')},
                         metadata={k.split('requester_metadata_q[8].')[1]:value for k,value in v.items()
                                   if k.startswith(p+'i_operand_requester.requester_metadata_q[8].')}))
    signature = json.dumps(data, sort_keys=True)
    if signature != previous:
        inputs.append(dict(ns=event['ns'], lanes=data))
    previous = signature

missing = [n for n in ('addrgen_operand_i', 'addrgen_operand_valid_i', 'addrgen_operand_ready_o',
                       'deshuffled_word', 'shuffled_word', 'reduced_word', 'word_lane_ptr_q')
           if 'i_vlsu.i_addrgen.' + n not in declarations]
save(HERE / 'operand_probe.json', dict(
    units='100fs', declarations=declarations, late_events=late,
    compact_queue_inputs=inputs, descriptor_transitions=transitions,
    missing_addrgen_signals=missing,
    evidence_pins={str(p):sha(p) for p in (vcd, HERE / 'operand_probe.py', HERE / 'ledger.json')},
    note='Post-delta value-change snapshots, not a replacement for absent downstream handshakes.',
))
print(json.dumps(dict(events=len(late), queue_input_changes=len(inputs), missing=missing)))
