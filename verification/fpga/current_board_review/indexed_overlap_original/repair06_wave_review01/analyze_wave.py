#!/usr/bin/env python3
"""Stable pre-edge handshakes and settled combinational transitions, kept distinct."""
import csv
import json
from pathlib import Path
import re
from acquire import HERE, sha, save

FROZEN = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware')
pkg = (FROZEN/'include/ara_pkg.sv').read_text()
enum = re.search(r'typedef enum logic \[7:0\] \{(.*?)\} ara_op_e;', pkg, re.S)[1]
ops = [s.strip() for s in re.sub(r'//[^\n]*', '', enum).split(',') if s.strip()]
assert all(re.fullmatch('[A-Z0-9_]+', s) for s in ops)
enum = re.search(r'typedef enum logic \[3:0\] \{(.*?)\} state_e;', (FROZEN/'src/ara_dispatcher.sv').read_text(), re.S)[1]
states = [s.strip() for s in enum.split(',')]
prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.'
vcd = HERE/'recovered_focus.vcd'
decls, codes, scopes = {}, {}, []
state, changes = {}, {}
allocs, dones = {}, {}
with (HERE/'inputs/commit_through_cycle600000.csv').open() as f:
    for row in csv.DictReader(f):
        cycle = int(row['cycle'])
        if 367700 <= cycle <= 369300 and row['event'] in ('uop_alloc', 'uop_done'):
            (allocs if row['event']=='uop_alloc' else dones).setdefault(cycle, []).append(row)


def choose(n):
    if n == 'ara_tb.clk' or n.endswith('i_ara_commit_monitor.cycle_q'):
        return True
    if n.startswith('i_dispatcher.'):
        return (n.startswith(('i_dispatcher.ara_req.', 'i_dispatcher.source_snapshot_', 'i_dispatcher.acc_req_i.')) or
            n.split('.',1)[1] in ('state_q', 'csr_vstart_q', 'indexed_mixed_vs2_layout',
                'reshuffle_req_q', 'reshuffle_req_d', 'eew_q[4]', 'eew_q[5]', 'eew_d[4]', 'eew_d[5]',
                'ara_req_valid', 'ara_req_ready_i'))
    if n.startswith('i_sequencer.'):
        return n.startswith('i_sequencer.ara_req_i.') or n in (
            'i_sequencer.ara_req_valid_i', 'i_sequencer.ara_req_ready_o', 'i_sequencer.verify_vinsn_done')
    if n.startswith(('i_vlsu.i_addrgen.', 'i_vlsu.i_vldu.')):
        return True
    if '.i_lane.' in n:
        leaf = n.split('.i_lane.',1)[1]
        return (leaf in ('source_snapshot_capture_q', 'source_snapshot_capture_index_q',
            'source_snapshot_capture_last_q', 'source_snapshot_replay_valid', 'source_snapshot_replay_index[8]',
            'operand_request_valid', 'operand_request_ready', 'vrf_operand[8]', 'vrf_operand_valid',
            'operand_queue_input[8]', 'operand_queue_input_valid', 'i_operand_requester.operand_requester_gnt[8]') or
            re.fullmatch(r'source_snapshot_q\[[0-7]\]', leaf) is not None or
            leaf.startswith(('operand_request[8].', 'i_operand_requester.requester_metadata_q[8].',
                             'i_operand_requester.operand_queue_cmd_o[8].')))
    return False


def subset(values, p):
    return {k[len(p):]:v for k,v in values.items() if k.startswith(p)}


def desc(values, p):
    d = subset(values, p)
    if isinstance(d.get('op'), int):
        d['op_name'] = ops[d['op']]
    return d


def disp(values):
    d = subset(values, 'i_dispatcher.')
    result = {k:v for k,v in d.items() if '.' not in k}
    if isinstance(result.get('state_q'), int):
        result['state_name'] = states[result['state_q']]
    return result


edges, transitions, captured, replayed, mmu, writes, addrgen_window = [], [], [], [], [], [], []
clock_times = []
last_transition = None


def emit(t):
    global last_transition
    if t is None:
        return
    if state.get('ara_tb.clk') == 0 and changes.get('ara_tb.clk') == 1:
        clock_times.append(t)
        cycle, = [v for k,v in state.items() if k.endswith('i_ara_commit_monitor.cycle_q')]
        if cycle in allocs or cycle in dones:
            q = 'i_sequencer.'
            edges.append(dict(ns=t/10000, cycle=cycle, dispatcher=disp(state),
                seq_valid=state.get(q+'ara_req_valid_i'), seq_ready=state.get(q+'ara_req_ready_o'),
                req=desc(state,q+'ara_req_i.'), allocated=allocs.get(cycle,[]), done=dones.get(cycle,[])))
        for lane in range(4):
            p = f'gen_lanes[{lane}].i_lane.'
            cap = state.get(p+'source_snapshot_capture_q') == 1
            valid = state.get(p+'vrf_operand_valid',0)
            rep = state.get(p+'source_snapshot_replay_valid',0)
            if cap and isinstance(valid,int) and (valid >> 8) & 1:
                captured.append(dict(ns=t/10000, cycle=cycle, lane=lane,
                    index=state[p+'source_snapshot_capture_index_q'], last=state[p+'source_snapshot_capture_last_q'],
                    data=hex(state[p+'vrf_operand[8]']), dispatcher=disp(state)))
            if isinstance(rep,int) and (rep >> 8) & 1:
                replayed.append(dict(ns=t/10000, cycle=cycle, lane=lane,
                    index=state[p+'source_snapshot_replay_index[8]'],
                    snapshot_word4=hex(state[p+'source_snapshot_q[4]']),
                    data=hex(state[p+'operand_queue_input[8]']),
                    queue_valid=(state[p+'operand_queue_input_valid'] >> 8)&1,
                    vrf_valid=(state[p+'vrf_operand_valid'] >> 8)&1,
                    vrf_word=hex(state[p+'vrf_operand[8]']),
                    request=desc(state,p+'operand_request[8].'),
                    metadata=subset(state,p+'i_operand_requester.requester_metadata_q[8].'),
                    dispatcher=disp(state)))
        p = 'i_vlsu.i_addrgen.'
        if 368500 <= t/10000 <= 368650:
            addrgen_window.append(dict(ns=t/10000, cycle=cycle, values=subset(state,p)))
        if state.get(p+'mmu_req_o') == 1:
            mmu.append(dict(ns=t/10000, cycle=cycle, values=subset(state,p)))
        p = 'i_vlsu.i_vldu.'
        req, gnt = state.get(p+'ldu_result_req_o'), state.get(p+'ldu_result_gnt_i')
        if isinstance(req,int) and isinstance(gnt,int) and req & gnt:
            writes.append(dict(ns=t/10000, cycle=cycle, req=req, gnt=gnt, values=subset(state,p)))
    state.update(changes)
    changes.clear()
    d = disp(state)
    signature = json.dumps(d, sort_keys=True)
    if signature != last_transition:
        transitions.append(dict(ns=t/10000, settled=d, req=desc(state,'i_dispatcher.ara_req.')))
        last_transition = signature


with vcd.open() as stream:
    header = []
    for line in stream:
        header.append(line)
        s = line.split()
        if not s:
            continue
        if s[0] == '$scope':
            scopes.append(s[2])
        elif s[0] == '$upscope':
            scopes.pop()
        elif s[0] == '$var':
            n = '.'.join(scopes+[s[4]]).removeprefix(prefix)
            if len(s)>6:
                n += re.sub(r'\[\d+:\d+\]$', '', s[5])
            if choose(n):
                assert n not in decls, n
                decls[n] = dict(code=s[3], width=int(s[2]))
                codes.setdefault(s[3], []).append(n)
        elif s[0] == '$enddefinitions':
            break
    assert re.search(r'\$timescale\s+100fs\s+\$end', ''.join(header))
    t = None
    for line in stream:
        s = line.strip()
        if not s:
            continue
        if s[0] == '#':
            emit(t)
            t = int(s[1:])
        elif s[0] in 'bB':
            value, code = s[1:].split()
            for name in codes.get(code,[]):
                changes[name] = int(value,2) if set(value) <= {'0','1'} else value
        elif s[0] in '01xXzZ':
            for name in codes.get(s[1:],[]):
                changes[name] = int(s[0]) if s[0] in '01' else s[0]
    emit(t)
save(HERE/'wave_findings02.json', dict(sampling='Handshakes use stable values preceding rising edge; settled combinational transitions separately labelled.',
    scale='100fs', ns_per_tick=0.0001, clock_period_ticks=sorted(set(b-a for a,b in zip(clock_times,clock_times[1:]))),
    declarations=decls, settled_dispatcher_transitions=transitions, csv_tied_edges=edges,
    capture_edges=captured, replay_edges=replayed, mmu_edges=mmu, vldu_write_edges=writes,
    addrgen_window=addrgen_window,
    pins={str(p):sha(p) for p in (vcd, Path(__file__), FROZEN/'src/ara_dispatcher.sv',
                                 FROZEN/'src/lane/lane.sv', FROZEN/'src/vlsu/addrgen.sv')}))
print(json.dumps(dict(selected_signals=len(decls), clock_period_ticks=sorted(set(b-a for a,b in zip(clock_times,clock_times[1:]))),
    edges=len(edges), transitions=len(transitions), captures=len(captured), replays=len(replayed),
    mmu=len(mmu), writes=len(writes), addrgen_names=[k for k in decls if k.startswith('i_vlsu.i_addrgen.')]),indent=2))
