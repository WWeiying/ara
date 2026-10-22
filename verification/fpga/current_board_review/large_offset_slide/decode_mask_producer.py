#!/usr/bin/env python3
"""Correlate the mask read with actual VRF writes from the captured producer."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'comparison'))
from decode_cycle import vcd

ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
REQUESTER = ARA + '.gen_lanes[0].i_lane.i_operand_requester'


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('capture', type=Path)
    out = cli.parse_args().capture.resolve()
    if not out.is_relative_to(HERE):
        cli.error('owned output only')
    target = out / 'mask_producer_events.json'
    if target.exists():
        raise FileExistsError(target)
    events = iter(vcd(out / 'selected.vcd'))
    _, decl = next(events)
    fields = {'clk': 'ara_tb.clk'}
    for field in ('ldu_result_gnt', 'ldu_result_addr', 'ldu_result_wdata',
                  'ldu_result_be', 'ldu_result_id', 'stall',
                  'vinsn_result_written_q'):
        fields[field] = REQUESTER + '.' + field
    fields['mask_grant'] = REQUESTER + '.operand_requester_gnt[6]'
    for field in ('id', 'addr', 'len', 'hazard', 'hazard_wait_complete',
                  'hazard_source_lifetime'):
        fields['mask_' + field] = REQUESTER + '.requester_metadata_q[6].' + field
    codes = {key: decl[name]['code'] for key, name in fields.items()}
    rows = []
    for time, before, after in events:
        if before.get(codes['clk']) != '0' or after.get(codes['clk']) != '1':
            continue
        row = {'time_ns': time / 10000}
        for key, code in codes.items():
            bits = before.get(code, 'x')
            row[key] = int(bits, 2) if set(bits) <= set('01') else None
        row['mask_stall'] = ((row['stall'] or 0) >> 6) & 1
        if row['mask_grant'] or (row['ldu_result_gnt'] and row['ldu_result_id'] == 3):
            rows.append(row)
    target.write_text(json.dumps(rows, indent=2) + '\n')
    reads = [r for r in rows if r['mask_grant'] and r['mask_addr'] == 3]
    writes = [r for r in rows if r['ldu_result_gnt'] and r['ldu_result_id'] == 3
              and r['ldu_result_addr'] == 3]
    finding = dict(mask_word3_read_times_ns=[r['time_ns'] for r in reads],
                   producer_word3_write_times_ns=[r['time_ns'] for r in writes],
                   read_before_write=bool(reads and writes and
                       reads[0]['time_ns'] < writes[0]['time_ns']))
    (out / 'mask_producer_finding.json').write_text(json.dumps(finding, indent=2) + '\n')
    print(json.dumps(dict(events=rows, finding=finding), indent=2))


if __name__ == '__main__':
    main()
