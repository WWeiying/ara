#!/usr/bin/env python3
"""Check pre-edge handshakes and physical queue words in the retained VCD."""
import csv
import json
from pathlib import Path
import re
from analyze import ART, HERE, sha, save

frozen = Path('/home/wangwy/fpga_runs/current_board_memory_candidate05/frozen/sources/hardware')
pkg = frozen / 'include/ara_pkg.sv'
enum = re.search(r'typedef enum logic \[7:0\] \{(.*?)\} ara_op_e;', pkg.read_text(), re.S)[1]
op_names = [x.strip() for x in re.sub(r'//[^\n]*', '', enum).split(',') if x.strip()]
assert all(re.fullmatch('[A-Z0-9_]+', x) for x in op_names)
prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.'
declarations, codes, state, changes = {}, {}, {}, {}
scopes, accepted, ready_acks, decoded, pushes, mmu = [], [], [], [], [], []
lo, hi = 3676400000, 3677000000
allocs = [r for r in csv.DictReader((ART/'commit_trace.csv').open()) if r['event']=='uop_alloc']
alloc_cycles = {int(r['cycle']) for r in allocs}

def selected(n):
    if n == 'ara_tb.clk' or n.endswith('i_ara_commit_monitor.cycle_q'):
        return True
    if n.startswith('i_sequencer.'):
        return n.startswith('i_sequencer.ara_req_i.') or n in (
            'i_sequencer.ara_req_valid_i', 'i_sequencer.ara_req_ready_o')
    if n.startswith('i_dispatcher.'):
        return n.startswith('i_dispatcher.ara_req.') or n in (
            'i_dispatcher.ara_req_valid', 'i_dispatcher.ara_req_ready_i',
            'i_dispatcher.state_q', 'i_dispatcher.source_snapshot_valid_q',
            'i_dispatcher.eew_q[4]', 'i_dispatcher.eew_q[5]')
    if n.startswith('i_vlsu.i_addrgen.'):
        return True
    if '.i_lane.' in n:
        leaf = n.split('.i_lane.', 1)[1]
        return (leaf in ('operand_queue_input[8]', 'operand_queue_input_valid',
                'vrf_operand[8]', 'vrf_operand_valid', 'source_snapshot_replay_valid',
                'operand_request_valid', 'operand_request_ready',
                'i_operand_requester.operand_requester_gnt[8]') or
                leaf.startswith(('operand_request[8].',
                    'i_operand_requester.requester_metadata_q[8].',
                    'i_operand_requester.operand_queue_cmd_o[8].')))
    return False

def subset(values, p):
    return {k[len(p):]:v for k,v in values.items() if k.startswith(p)}

def edge(t):
    if t is None:
        return
    # Sample the preceding stable values, not the post-edge NBA assignments.
    if state.get('ara_tb.clk') == 0 and changes.get('ara_tb.clk') == 1:
        cycle = next(v for k,v in state.items() if k.endswith('i_ara_commit_monitor.cycle_q'))
        d = 'i_dispatcher.'
        if state.get(d+'ara_req_valid') == state.get(d+'ara_req_ready_i') == 1:
            req = subset(state, d+'ara_req.')
            decoded.append(dict(ns=t/10000, cycle=cycle, op_name=op_names[req['op']], req=req,
                                 state=state[d+'state_q'],
                                 snapshot_valid=state[d+'source_snapshot_valid_q'],
                                 eew_v4=state[d+'eew_q[4]'], eew_v5=state[d+'eew_q[5]']))
        q = 'i_sequencer.'
        if state.get(q+'ara_req_valid_i') == state.get(q+'ara_req_ready_o') == 1:
            req = subset(state, q+'ara_req_i.')
            ready_acks.append(dict(ns=t/10000, cycle=cycle, op_name=op_names[req['op']], req=req))
        if cycle in alloc_cycles:
            assert state[q+'ara_req_valid_i'] == 1
            req = subset(state, q+'ara_req_i.')
            accepted.append(dict(ns=t/10000, cycle=cycle, op_name=op_names[req['op']], req=req,
                                 state=state[d+'state_q'],
                                 snapshot_valid=state[d+'source_snapshot_valid_q'],
                                 eew_v4=state[d+'eew_q[4]'], eew_v5=state[d+'eew_q[5]']))
        if lo <= t <= hi:
            a = 'i_vlsu.i_addrgen.'
            if state.get(a+'mmu_req_o') == 1:
                mmu.append(dict(ns=t/10000, cycle=cycle, values=subset(state, a)))
            lanes = []
            for lane in range(4):
                p = f'gen_lanes[{lane}].i_lane.'
                valid = (state[p+'operand_queue_input_valid'] >> 8) & 1
                gnt = state[p+'i_operand_requester.operand_requester_gnt[8]']
                req = ((state[p+'operand_request_valid'] & state[p+'operand_request_ready']) >> 8) & 1
                lanes.append(dict(lane=lane, queue_push=valid, requester_bank_grant=gnt,
                                  request_handshake=req, values=subset(state,p)))
            if any(x['queue_push'] or x['requester_bank_grant'] or x['request_handshake'] for x in lanes):
                pushes.append(dict(ns=t/10000, cycle=cycle, lanes=lanes))
    state.update(changes)
    changes.clear()

with (HERE / 'compact.vcd').open() as stream:
    for line in stream:
        s = line.split()
        if not s:
            continue
        if s[0] == '$scope':
            scopes.append(s[2])
        elif s[0] == '$upscope':
            scopes.pop()
        elif s[0] == '$var':
            n = '.'.join(scopes+[s[4]]).removeprefix(prefix)
            if len(s) > 6:
                n += re.sub(r'\[\d+:\d+\]$', '', s[5])
            if selected(n):
                assert n not in declarations
                declarations[n] = dict(code=s[3], width=int(s[2]))
                codes.setdefault(s[3], []).append(n)
        elif s[0] == '$enddefinitions':
            break
    t = None
    for line in stream:
        s = line.strip()
        if not s:
            continue
        if s[0] == '#':
            edge(t)
            t = int(s[1:])
            if t > hi:
                break
        elif s[0] in 'bB':
            v, c = s[1:].split()
            for n in codes.get(c, []):
                changes[n] = int(v,2) if set(v) <= {'0','1'} else v
        elif s[0] in '01xXzZ':
            for n in codes.get(s[1:], []):
                changes[n] = int(s[0]) if s[0] in '01' else s[0]

physical = [e for e in pushes if all(x['queue_push'] for x in e['lanes'])]
word = next(e for e in physical if [x['values']['operand_queue_input[8]'] for x in e['lanes']]
            == [0x17000,0x4000,0x11000,0x1e000])
for x in word['lanes']:
    assert x['values']['vrf_operand[8]'] == x['values']['operand_queue_input[8]']
    assert (x['values']['source_snapshot_replay_valid'] >> 8) & 1 == 0

# Exact NrLanes=4 EW32 table from frozen ara_pkg, not an assumed shuffle.
table_text = pkg.read_text().split('      4: unique case (ew)',1)[1].split('rvv_pkg::EW32: begin',1)[1].split('end',1)[0]
table = {int(a):int(b) for a,b in re.findall(r'idx\[(\d+)\]\s*=\s*(\d+)',table_text)}
assert len(table) == 32
raw = b''.join(x['values']['operand_queue_input[8]'].to_bytes(8,'little') for x in word['lanes'])
reshaped = bytes(raw[table[i]] for i in range(32))
bad_offset = int.from_bytes(reshaped[:8], 'little')
assert bad_offset == 0x400000017000
assert any(e['values']['mmu_vaddr_o'] == bad_offset + 0x40000000 for e in mmu)
assert len(accepted) == 20
assert all(e['op_name'] == 'VLXE' for e in accepted if e['ns'] > 357500)
assert [e['cycle'] for e in accepted] == [int(r['cycle']) for r in allocs]
save(HERE/'handshakes.json', dict(
    sampling='Stable pre-rising-edge values from recorded VCD; clock period 1ns.',
    declarations=declarations, allocated_sequencer_requests=accepted,
    ready_acknowledgements_not_allocation=ready_acks,
    decoded_requests_not_backend_acceptance=decoded,
    late_lane_handshakes=pushes, late_mmu_requests=mmu, csv_allocations=allocs,
    physical_word_queue_push_ns=word['ns'], physical_word_lanes=[hex(int.from_bytes(raw[i:i+8],'little')) for i in range(0,32,8)],
    static_ew32_deshuffle_first_index=hex(bad_offset), static_expected_bad_va=hex(bad_offset+0x40000000),
    proof_boundary='Actual VRF/queue input + valid, requester grants, descriptors, MMU request. AddrGen input/dequeue/deshuffle nodes absent; transform computed from frozen RTL.',
    evidence_pins={str(p):sha(p) for p in (HERE/'compact.vcd', HERE/'handshakes.py',
          HERE/'operand_probe.json', ART/'commit_trace.csv', pkg,
          frozen/'src/lane/lane.sv', frozen/'src/lane/operand_queue.sv',
          frozen/'src/lane/lane_sequencer.sv', frozen/'src/ara_dispatcher.sv')},
))
print(json.dumps(dict(accepted=len(accepted), queue_push_ns=word['ns'], bad_offset=hex(bad_offset))))
