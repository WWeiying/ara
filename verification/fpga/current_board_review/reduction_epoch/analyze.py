#!/usr/bin/env python3
"""Decode bounded VCD using the existing reader, with pre-edge handshake values."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from adapter import HERE, inside, prepare
from capture import ARA, CORE
sys.path.insert(0, str(HERE.parent / 'comparison'))
from decode_cycle import vcd

STATES = ['NO_REDUCTION', 'INTRA_LANE_REDUCTION', 'INTER_LANES_REDUCTION_TX',
          'INTER_LANES_REDUCTION_RX', 'LN0_REDUCTION_COMMIT', 'SIMD_REDUCTION',
          'OSUM_REDUCTION', 'MFPU_WAIT']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    out = inside(args.capture)
    path = out / 'selected.vcd'
    if '100fs' not in path.read_text()[:256]:
        raise ValueError('unexpected VCD timescale')
    samples = iter(vcd(path))
    tag, declarations = next(samples)
    assert tag == 'declarations'
    declarations = {k.replace('\\sv_', ''): v for k, v in declarations.items()}
    fields = dict(clk='ara_tb.clk', cycle=CORE + '.csr_regfile_i.cycle_q',
                  activity=ARA + '.mfpu_reduction_any_active',
                  global_active=ARA + '.mfpu_reduction_global_any_active',
                  request_valid=ARA + '.ara_req_valid', request_ready=ARA + '.ara_req_ready',
                  request_op=ARA + '.ara_req.op', request_vl=ARA + '.ara_req.vl',
                  request_vd=ARA + '.ara_req.vd', request_seq=ARA + '.ara_req.verify_arch_seq',
                  pe_valid=ARA + '.i_sequencer.pe_req_valid_o',
                  slide_valid=ARA + '.i_sldu.sldu_red_valid_o')
    lane_fields = dict(state='mfpu_state_q', next_state='mfpu_state_d',
        id='vinsn_issue_q.id', op='vinsn_issue_q.op', vl='vinsn_issue_q.vl',
        vd='vinsn_issue_q.vd', first='first_op_q', in_valid='vfpu_in_valid',
        in_ready='vfpu_in_ready', out_valid='vfpu_out_valid', out_ready='vfpu_out_ready',
        nv='vfpu_ex_flag.NV', pending='fpu_gen.reduction_fflags_q',
        activity='reduction_any_active_q', rounds='sldu_transactions_cnt_q',
        rx_valid='sldu_mfpu_valid_q', rx_ready='sldu_mfpu_ready_d',
        tx_valid='mfpu_red_valid_o', tx_ready='mfpu_red_ready_i',
        done='mfpu_vinsn_done_o', result_req='mfpu_result_req_o',
        result_gnt='mfpu_result_gnt_i', result_data='mfpu_result_wdata_o')
    for lane in (0, 1):
        prefix = ARA + f'.gen_lanes[{lane}].i_lane.i_vfus.i_vmfpu.'
        fields.update({f'l{lane}_{k}': prefix + v for k, v in lane_fields.items()})
    missing = set(fields.values()) - declarations.keys()
    if missing:
        raise ValueError('missing fields: ' + repr(missing))
    codes = {key: declarations[name]['code'] for key, name in fields.items()}

    def value(state, key):
        bits = state.get(codes[key], 'x')
        return int(bits, 2) if set(bits) <= set('01') else None

    rows, events = [], []
    for time, before, after in samples:
        if value(before, 'clk') != 0 or value(after, 'clk') != 1:
            continue
        row = {key: value(before, key) for key in fields}
        row['time_ns'] = time / 10000
        row['activity_after'] = value(after, 'activity')
        row['global_after'] = value(after, 'global_active')
        reasons = []
        if row['request_valid'] and row['request_ready']:
            reasons.append('request')
        if row['activity'] != row['activity_after']:
            reasons.append('activity_change')
        for lane in (0, 1):
            p = f'l{lane}_'
            if row[p + 'in_valid'] and row[p + 'in_ready']:
                reasons.append(p + ('first_issue' if row[p + 'first'] else 'issue'))
            if row[p + 'out_valid'] and row[p + 'out_ready']:
                reasons.append(p + 'return')
            if row[p + 'state'] == 3 and row[p + 'rx_valid'] and row[p + 'rx_ready']:
                reasons.append(p + ('first_rx' if row[p + 'rounds'] == 3 else 'rx'))
            if row[p + 'state'] in (4, 5) and row[p + 'next_state'] == 7:
                reasons.append(p + 'publish')
            if row[p + 'result_req'] and row[p + 'result_gnt']:
                reasons.append(p + 'write')
            if row[p + 'done']:
                reasons.append(p + 'done')
        row['events'] = ','.join(reasons)
        rows.append(row)
        if reasons:
            events.append(row)
    prepare.save(out / 'cycles.json', rows)
    prepare.save(out / 'events.json', events)
    with (out / 'cycles.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    first_rx, = [r for r in events if 'l0_first_rx' in r['events'] and r['l0_vd'] == 8]
    overwrite, = [r for r in events if r['activity'] == 2 and r['activity_after'] == 0]
    publish, = [r for r in events if 'l0_publish' in r['events'] and r['l0_vd'] == 8]
    write, = [r for r in events if 'l0_write' in r['events'] and r['l0_vd'] == 8]
    assert first_rx['global_active'] == 1 and first_rx['l0_pending'] == 16
    assert overwrite['l1_vd'] == 9 and overwrite['l1_vl'] == 0
    assert 'l1_first_issue' in overwrite['events'] and overwrite['l0_state'] == 5
    assert publish['global_active'] == 0 and publish['l0_pending'] == 16
    assert write['l0_result_data'] & 0xffff == 0x7c01
    assert first_rx['cycle'] < overwrite['cycle'] < publish['cycle'] < write['cycle']
    prepare.save(out / 'finding.json', dict(status='MEASURED_EPOCH_OVERWRITE',
        first_returned_token_cycle=first_rx['cycle'], overwrite_cycle=overwrite['cycle'],
        publication_cycle=publish['cycle'], write_cycle=write['cycle'],
        pending_flags=publish['l0_pending'], publication_global_activity=publish['global_active'],
        actual_low16=write['l0_result_data'] & 0xffff, expected_low16=0x7e00,
        candidate_snapshot_flags=publish['l0_pending'] if first_rx['global_active'] else 0,
        candidate_status='offline counterfactual only; no RTL repair or verification',
        vcd_sha256=prepare.sha(path), decoder_sha256=prepare.sha(Path(__file__))))
    for row in events:
        print(f"{row['time_ns']:.1f}ns cycle={row['cycle']} {row['events']} "
              f"activity={row['activity']}->{row['activity_after']} "
              f"L0=id{row['l0_id']}/vd{row['l0_vd']}/{STATES[row['l0_state']]}"
              f"->{STATES[row['l0_next_state']]} pending={row['l0_pending']:02x} "
              f"L1=id{row['l1_id']}/vd{row['l1_vd']}/{STATES[row['l1_state']]}")


if __name__ == '__main__':
    main()
