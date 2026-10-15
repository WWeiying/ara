#!/usr/bin/env python3
"""Sample selected slide signals immediately before each real clock edge."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'comparison'))
from decode_cycle import vcd

ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('capture', type=Path)
    out = cli.parse_args().capture.resolve()
    if not out.is_relative_to(HERE):
        cli.error('owned output only')
    path = out / 'selected.vcd'
    with path.open() as src:
        if '100fs' not in src.read(256):
            raise ValueError('Expected 100fs VCD precision')
    events = iter(vcd(path))
    tag, decl = next(events)
    assert tag == 'declarations'
    fields = {'clk': 'ara_tb.clk'}
    for unit, prefix, names in [
        ('i_sldu', 's_', ('state_q', 'vinsn_issue_valid_q', 'vinsn_issue_q.id',
            'vinsn_issue_q.op', 'vinsn_issue_q.vl', 'vinsn_issue_q.stride',
            'issue_cnt_q', 'commit_cnt_q', 'vrf_pnt_q', 'in_pnt_q', 'out_pnt_q',
            'output_limit_q', 'sldu_operand_valid', 'sldu_operand_ready',
            'mask_valid_i', 'mask_ready_o', 'mask_valid_q', 'mask_ready_d',
            'out_en_seq', 'out_en_flat', 'sldu_result_req_o', 'sldu_result_gnt_i')),
        ('i_masku', 'm_', ('vinsn_issue.id', 'vinsn_issue.vl', 'vinsn_issue.eew_vmask',
            'mask_pnt_q', 'read_cnt_q', 'masku_operand_m_valid', 'masku_operand_m_ready')),
    ]:
        fields.update({prefix + n: ARA + '.' + unit + '.' + n for n in names})
    for lane in range(4):
        for n in ('mask_q', 'out_en', 'sldu_operand', 'sld_op_dst',
                  'sldu_result_addr_o', 'sldu_result_be_o', 'sldu_result_wdata_o'):
            suffix = n + '[' + str(lane) + ']'
            fields['s_' + suffix] = ARA + '.i_sldu.' + suffix
        suffix = 'masku_operand_m[' + str(lane) + ']'
        fields['m_' + suffix] = ARA + '.i_masku.' + suffix
    missing = set(fields.values()) - set(decl)
    if missing:
        raise ValueError('Missing signals: ' + repr(missing))
    codes = {key: decl[name]['code'] for key, name in fields.items()}
    rows = []
    for t, before, after in events:
        if before.get(codes['clk']) != '0' or after.get(codes['clk']) != '1':
            continue
        row = {'time_ns': t / 10000}
        for key, code in codes.items():
            bits = before.get(code, 'x')
            row[key] = int(bits, 2) if set(bits) <= set('01') else None
        rows.append(row)
    if not rows:
        raise ValueError('No clock samples')
    (out / 'cycles.json').write_text(json.dumps(rows, indent=2) + '\n')
    with (out / 'cycles.csv').open('w') as dst:
        writer = csv.DictWriter(dst, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    useful = [r for r in rows if r['s_vinsn_issue_valid_q'] or r['s_sldu_result_req_o']]
    print(json.dumps(useful, indent=2))


if __name__ == '__main__':
    main()
