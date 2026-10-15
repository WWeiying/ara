#!/usr/bin/env python3
"""Read the single-row capture; distinguish held store maintenance from real VSE."""
import argparse
import csv
import sys

sys.dont_write_bytecode = True
from adapter import ARA, SYSTEM, HERE, inside, prepare
sys.path.insert(0, str(HERE.parent / 'comparison'))
from decode_cycle import vcd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    from pathlib import Path
    capture, out = inside(Path(args.capture)), inside(Path(args.out))
    out.mkdir(parents=True, exist_ok=False)
    source = capture / 'selected.vcd'
    assert '100fs' in source.read_text()[:256]
    events = iter(vcd(source))
    tag, declarations = next(events)
    assert tag == 'declarations'
    fields = {'cycle': SYSTEM + '.i_ara_commit_monitor.cycle_q'}
    fields.update({n: ARA + '.i_dispatcher.' + n for n in (
        'state_q', 'state_d', 'decode_blocked', 'arch_decode',
        'acc_req_i.req_valid', 'acc_req_i.insn', 'acc_resp_o.req_ready',
        'csr_vl_q', 'csr_vtype_q.vsew', 'csr_vtype_q.vlmul',
        'reshuffle_req_q', 'reshuffle_req_d', 'rs_lmul_cnt_q',
        'rs_lmul_cnt_limit_q', 'rs_lmul_cnt_limit_d', 'vs_buffer_q',
        'eew_new_buffer_q', 'eew_old_buffer_q', 'reshuffle_vs1_base_q',
        'reshuffle_vs1_limit_q', 'reshuffle_eew_vs1_q',
        'ara_req.eew_vs1', 'ara_req.vl', 'ara_req.emul',
        'ara_req_idle.eew_vs1', 'ara_req_idle.vl', 'ara_req_idle.vs1',
        'ara_req_valid_o', 'ara_req_ready_i', 'ara_store_accepted_i', 'ara_req_o.op',
        'ara_req_o.verify_arch_insn', 'ara_req_o.vl', 'ara_req_o.vtype.vsew',
        'ara_req_o.eew_vs1', 'ara_req_o.old_eew_vs1', 'ara_req_o.vs1',
        'ara_req_o.vs2', 'ara_req_o.vd', 'ara_req_o.emul',
        'backend_valid', 'backend_req.op', 'backend_req.vl',
        'backend_req.vd', 'backend_req.vs2', 'backend_req.vtype.vsew',
        'eew_q[24]', 'eew_q[25]', 'eew_q[26]', 'eew_q[27]')})
    missing = set(fields.values()) - declarations.keys()
    assert not missing, sorted(missing)
    codes = {k: declarations[v]['code'] for k, v in fields.items()}

    def values(state):
        return {k: int(state[c], 2) if c in state and set(state[c]) <= set('01') else None
                for k, c in codes.items()}

    rows, simultaneous = [], []
    for timestamp, before, after in events:
        b, a = values(before), values(after)
        if a['decode_blocked'] == 1 and a['reshuffle_req_q'] not in (0, None):
            simultaneous.append(dict(time_ns=timestamp / 10000, **a))
        # The captured monitor counter increments at every rising clock edge.
        # Use pre-increment values, matching the commit trace's cycle convention.
        if b['cycle'] is None or a['cycle'] != b['cycle'] + 1:
            continue
        rows.append(dict(time_ns=timestamp / 10000, **b))
    with (out / 'cycles.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    target = [r for r in rows if r['acc_req_i.req_valid'] == 1 and r['acc_req_i.insn'] == 0x62858c27]
    fires = [r for r in rows if r['ara_req_valid_o'] == 1 and r['ara_req_ready_i'] == 1
             and r['ara_req_o.verify_arch_insn'] == 0x62858c27]
    result = dict(status='MEASURED_SINGLE_ROW', full_matrix_proved=False,
        source_vcd_sha256=prepare.sha(source), analyzer_sha256=prepare.sha(Path(__file__)),
        target_cycles=[target[0]['cycle'], target[-1]['cycle']],
        target_blocked_cycles=sum(r['decode_blocked'] == 1 for r in target),
        all_capture_blocked_and_pending_states=simultaneous,
        registered_backend_handshakes=fires,
        store_accepts=[r for r in rows if r['ara_store_accepted_i'] == 1
                       and r['ara_req_o.verify_arch_insn'] == 0x62858c27],
        target_front_accepts=[r for r in target if r['acc_resp_o.req_ready'] == 1],
        target_state_changes=[r for r in target if r['state_q'] != r['state_d']])
    full_trace = Path('/home/wangwy/fpga_runs/current_board_integration_final04/campaign/'
                      'extension-matrix/tests/extension_e32_m4_vf4/commit_trace.csv')
    normalized = []
    for trace, start, end in ((full_trace, 538448, 538592),
                              (capture / 'commit_trace.csv', 19126, 19270)):
        with trace.open() as stream:
            records = list(csv.DictReader(stream))
        normalized.append([(int(r['cycle'])-start, r['event'], r['insn']) for r in records
            if start <= int(r['cycle']) <= end and r['insn'] in ('49b22c57', '62858c27')])
    result['matched_extension_store_prefix'] = dict(equal=normalized[0] == normalized[1],
        full_start=538448, single_start=19126, cycle_offset=519322,
        full_trace_sha256=prepare.sha(full_trace), full_events=normalized[0],
        single_events=normalized[1], original_matrix_still_timeout=True)
    assert normalized[0] == normalized[1], 'Full/single prefix differs; inspect before interpreting'
    prepare.save(out / 'finding.json', result)
    print('target', result['target_cycles'], 'blocked', result['target_blocked_cycles'],
          'blocked+pending', len(simultaneous), 'registered handshakes', len(fires))
    for row in fires:
        print('cycle', row['cycle'], 'op', row['ara_req_o.op'], 'vd', row['ara_req_o.vd'],
              'vs1', row['ara_req_o.vs1'], 'vl', row['ara_req_o.vl'],
              'eew', row['ara_req_o.vtype.vsew'], 'limit', row['rs_lmul_cnt_limit_q'])


if __name__ == '__main__':
    main()
