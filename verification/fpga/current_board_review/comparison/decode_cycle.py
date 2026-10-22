#!/usr/bin/env python3
"""Decode real captured handshakes, sampling values immediately before rising edges."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
LANE = ARA + '.gen_lanes[1].i_lane.i_vfus.i_vmfpu'
RAW = LANE + '.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice'


def vcd(path):
    scopes, declarations, widths, state, changes = [], {}, {}, {}, {}
    body, time = False, 0
    with path.open() as stream:
        for raw in stream:
            line = raw.strip()
            if not line:
                continue
            if not body:
                if line.startswith('$scope '):
                    scopes.append(line.split()[2].replace('\\sv_', ''))
                elif line.startswith('$upscope'):
                    scopes.pop()
                elif line.startswith('$var '):
                    p = line.split()
                    width, code, name = int(p[2]), p[3], p[4]
                    # fsdb2vcd separates unpacked indices from the reference name.
                    for suffix in p[5:-1]:
                        if suffix.startswith('[') and '][' in suffix:
                            name += suffix[:suffix.rfind('[')]
                        elif suffix.startswith('[') and ':' not in suffix:
                            name += suffix
                    name = '.'.join(scopes + [name])
                    if name in declarations:
                        raise ValueError('Duplicate VCD field: ' + name)
                    declarations[name] = dict(code=code, width=width)
                    widths[code] = width
                elif line.startswith('$enddefinitions'):
                    body = True
                    yield 'declarations', declarations
                continue
            if line.startswith('#'):
                before = dict(state)
                state.update(changes)
                if changes:
                    yield time, before, dict(state)
                changes = {}
                new_time = int(line[1:])
                if new_time < time:
                    raise ValueError('Nonmonotonic VCD')
                time = new_time
            elif line[0] in 'bB':
                bits, code = line[1:].split()
                changes[code] = bits.lower().rjust(widths[code], bits[0] if bits[0] in 'xz' else '0')
            elif line[0] in '01xXzZ':
                changes[line[1:]] = line[0].lower()
            elif not line.startswith('$'):
                raise ValueError('Unsupported VCD value: ' + line)
    if not body:
        raise ValueError('Incomplete VCD header')
    before = dict(state)
    state.update(changes)
    if changes:
        yield time, before, dict(state)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('capture', type=Path)
    cli.add_argument('--vcd', default='selected.vcd')
    args = cli.parse_args()
    out = args.capture.resolve()
    if not out.is_relative_to(HERE):
        raise ValueError('owned output only')
    if '100fs' not in (out / args.vcd).read_text()[:256]:
        raise ValueError('Expected 100fs VCD precision')
    it = iter(vcd(out / args.vcd))
    tag, decl = next(it)
    assert tag == 'declarations'
    decl = {k.replace('\\sv_', ''): v for k, v in decl.items()}
    fields = {'clk': 'ara_tb.clk'}
    fields.update({n.replace('.', '_'): LANE + '.' + n for n in (
        'vfu_operation_i.vm', 'vfu_operation_i.id', 'vfu_operation_valid_i',
        'vinsn_issue_q.vm', 'vinsn_issue_q.id', 'vinsn_issue_q.vl', 'vinsn_issue_q_valid',
        'operand_a', 'operand_b', 'issue_be', 'vfpu_in_valid', 'vfpu_in_ready',
        'vfpu_out_valid', 'vfpu_out_ready', 'vfpu_tag_out.flag_mask',
        'vfpu_ex_flag_fn.NV', 'fflags_ex_o', 'fflags_ex_valid_o')})
    fields.update({'raw_nv' + str(i): RAW + '.lane_status[' + str(i) + '].NV' for i in range(4)})
    fields['raw_masks'] = RAW + '.lane_masks'
    fields.update({'m_' + n.replace('.', '_'): ARA + '.i_masku.' + n for n in (
        'vinsn_issue.vm', 'vinsn_issue.id', 'vinsn_issue.vstart', 'vinsn_issue.vl',
        'masku_operand_m_seq', 'result_queue_active_mask_seq', 'in_ready_cnt_en',
        'masku_operand_alu_valid', 'masku_operand_alu_ready', 'masku_operand_m_valid',
        'masku_operand_vd_valid', 'result_queue_full', 'vrf_pnt_q', 'vrf_pnt_d')})
    missing = set(fields.values()) - set(decl)
    if missing:
        raise ValueError('missing fields: ' + repr(missing))
    codes = {n: decl[path]['code'] for n, path in fields.items()}

    def value(state, key, low_bits=None):
        bits = state.get(codes[key], 'x')
        if low_bits is not None:
            bits = bits[-low_bits:]
        return int(bits, 2) if set(bits) <= set('01') else None

    events = []
    for time, before, after in it:
        if before.get(codes['clk']) != '0' or after.get(codes['clk']) != '1':
            continue
        row = {k: value(before, k) for k in fields}
        row['m_predicate_low16'] = value(before, 'm_masku_operand_m_seq', 16)
        row['m_predicate_low8'] = value(before, 'm_masku_operand_m_seq', 8)
        row['time_ns'] = time / 10000
        row['fp_accept'] = row['vfpu_in_valid'] == row['vfpu_in_ready'] == 1
        row['fp_return'] = row['vfpu_out_valid'] == row['vfpu_out_ready'] == 1
        row['masku_accept'] = row['m_in_ready_cnt_en'] == 1
        if row['fp_accept'] or row['fp_return'] or row['masku_accept'] or row['fflags_ex_valid_o']:
            events.append(row)
    (out / 'cycles.json').write_text(json.dumps(events, indent=2) + '\n')
    with (out / 'cycles.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(events[0]))
        writer.writeheader()
        writer.writerows(events)
    for row in events:
        print(json.dumps(row))


if __name__ == '__main__':
    main()
