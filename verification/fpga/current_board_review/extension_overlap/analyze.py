#!/usr/bin/env python3
"""Decode pre-edge dispatcher handshakes from the bounded same-image capture."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from adapter import ARA, SYSTEM, HERE, inside, prepare
sys.path.insert(0, str(HERE.parent / 'comparison'))
from decode_cycle import vcd


def normalize_header(source, destination):
    """Remove only exact duplicate declarations; preserve all value changes."""
    scopes, seen, duplicates = [], {}, []
    body = False
    with source.open() as stream, destination.open('w') as output:
        for raw in stream:
            parts = raw.split()
            if not body and parts:
                if parts[0] == '$scope':
                    scopes.append(parts[2])
                elif parts[0] == '$upscope':
                    scopes.pop()
                elif parts[0] == '$var':
                    key = tuple(scopes), tuple(parts[4:-1])
                    declaration = tuple(parts)
                    if key in seen:
                        if seen[key] != declaration:
                            raise ValueError('nonidentical duplicate declaration: ' + repr(key))
                        duplicates.append('.'.join(scopes) + '.' + ' '.join(parts[4:-1]))
                        continue
                    seen[key] = declaration
                elif parts[0] == '$enddefinitions':
                    body = True
            output.write(raw)
    return duplicates


def analyze(capture, out):
    out.mkdir(parents=True, exist_ok=False)
    source = capture / 'selected_once.vcd'
    path = out / 'normalized.vcd'
    duplicates = normalize_header(source, path)
    prepare.save(out / 'vcd_normalization.json', dict(
        input_sha256=prepare.sha(source), output_sha256=prepare.sha(path),
        exact_duplicate_declarations_removed=duplicates,
        value_changes_preserved=True))
    with path.open() as stream:
        if '100fs' not in stream.read(256):
            raise ValueError('unexpected VCD timescale')
    samples = iter(vcd(path))
    tag, declarations = next(samples)
    assert tag == 'declarations'
    declarations = {k.replace('\\sv_', ''): v for k, v in declarations.items()}
    fields = dict(clk='ara_tb.clk', cycle=SYSTEM + '.i_ara_commit_monitor.cycle_q')
    for name in (
        'state_q', 'state_d', 'csr_vl_q', 'csr_vtype_q.vsew', 'csr_vstart_q',
        'verify_active_insn_q', 'verify_front_active_q',
        'acc_req_i.req_valid', 'acc_req_i.resp_ready', 'acc_req_i.insn', 'acc_resp_o.req_ready',
        'backend_valid', 'ara_req_ready_i', 'ara_req_valid_o',
        'backend_req.op', 'backend_req.vd', 'backend_req.vs2', 'backend_req.vl',
        'backend_req.eew_vs2', 'backend_req.vtype.vsew',
        'ara_req.op', 'ara_req.vl', 'ara_req.eew_vs2', 'ara_req.vtype.vsew',
        'ara_req.cvt_resize', 'ara_req.vm',
        'eew_q[24]', 'eew_q[25]', 'eew_valid_q', 'reshuffle_req_q',
        'reshuffle_req_d', 'legal_widen_overlap', 'masked_widen_layout_conflict',
        'source_snapshot_valid_q', 'source_snapshot_resolves_widen',
        'rs_lmul_cnt_q', 'rs_lmul_cnt_limit_q', 'vs_buffer_q',
        'eew_old_buffer_q', 'eew_new_buffer_q', 'ara_idle_i', 'sldu_idle_i'):
        fields[name] = ARA + '.i_dispatcher.' + name
    missing = set(fields.values()) - declarations.keys()
    if missing:
        raise ValueError('missing fields: ' + repr(sorted(missing)))
    codes = {k: declarations[v]['code'] for k, v in fields.items()}

    def value(state, key):
        bits = state.get(codes[key], 'x')
        return int(bits, 2) if set(bits) <= set('01') else None

    rows = []
    for time, before, after in samples:
        if value(before, 'clk') != 0 or value(after, 'clk') != 1:
            continue
        row = {k: value(before, k) for k in fields}
        row['time_ns'] = time / 10000
        row['eew25_after'] = value(after, 'eew_q[25]')
        row['eew24_after'] = value(after, 'eew_q[24]')
        row['backend_fire'] = row['backend_valid'] == 1 and row['ara_req_ready_i'] == 1
        row['front_fire'] = row['acc_req_i.req_valid'] == 1 and row['acc_resp_o.req_ready'] == 1
        rows.append(row)
    with (out / 'cycles.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    target = [r for r in rows if r['acc_req_i.req_valid'] == 1
              and r['acc_req_i.insn'] == 0x49932c57]
    # Match frozen ara_dispatcher.sv:1195,1660. WAIT_IDLE re-decodes directly
    # when the request register is empty and the backend is idle.
    decode = [r for r in target if r['acc_req_i.resp_ready'] == 1 and (
        r['state_q'] in (0, 8) or (r['state_q'] == 1
            and r['ara_req_valid_o'] == 0 and r['ara_idle_i'] == 1))]
    fires = [r for r in target if r['backend_fire']]
    maintenance = [r for r in fires if r['backend_req.op'] == 129]
    original = [r for r in fires if r['backend_req.op'] == 0]
    flips = [r for r in target if r['eew_q[25]'] != r['eew25_after']]
    transitions = [r for r in target if r['state_q'] != r['state_d']]
    finding = dict(status='MEASURED' if target else 'NO_TARGET_IN_WINDOW',
        target_cycles=[target[0]['cycle'], target[-1]['cycle']] if target else [],
        target_front_handshakes=sum(r['front_fire'] for r in target),
        backend_handshakes_while_target_held=len(fires),
        maintenance_VSLIDEDOWN_handshakes=len(maintenance),
        original_VADD_handshakes=len(original),
        other_backend_handshakes=len(fires)-len(maintenance)-len(original),
        decode_cycles=decode, first_backend_handshakes=fires[:12],
        v25_eew_transitions=flips, state_transitions=transitions,
        vcd_sha256=prepare.sha(path), decoder_sha256=prepare.sha(Path(__file__)),
        parser_sha256=prepare.sha(HERE.parent / 'comparison/decode_cycle.py'),
        input_capture=str(capture),
        supersedes='measurement01/capture/finding.json: NORMAL-only decode filter was incomplete')
    # Leave contradictory evidence visible instead of interpreting a timeout as a loop.
    finding['classifier_loop_proved'] = bool(
        len(decode) >= 3 and len(flips) >= 4 and len(fires) >= 4
        and len(maintenance) == len(fires) and not original
        and all(not r['front_fire'] for r in target)
        and all(r['legal_widen_overlap'] == 0 and r['masked_widen_layout_conflict'] == 0
                and r['csr_vl_q'] == 127 and r['ara_req.vtype.vsew'] == 1
                and r['csr_vtype_q.vsew'] == 1 and r['ara_req.eew_vs2'] == 0
                for r in decode)
        and {(r['eew_q[25]'], r['eew25_after']) for r in flips} == {(0, 1), (1, 0)})
    prepare.save(out / 'finding.json', finding)
    print(json.dumps({k: v for k, v in finding.items()
                      if k not in ('decode_cycles', 'first_backend_handshakes',
                                   'v25_eew_transitions', 'state_transitions')}, indent=2))
    for row in fires[:8]:
        print('cycle', row['cycle'], 'state', row['state_q'],
              'op', row['backend_req.op'], 'vd', row['backend_req.vd'],
              'vl', row['backend_req.vl'], 'eew', row['backend_req.eew_vs2'],
              '->', row['backend_req.vtype.vsew'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    analyze(inside(args.capture), inside(args.out))
