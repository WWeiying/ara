#!/usr/bin/env python3
"""Extract a compact signal report from the already captured FSDB; no simulation."""
import argparse
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
VERDI = Path('/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1')
ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    out = args.capture.resolve()
    if not out.is_relative_to(HERE):
        raise ValueError('owned output only')
    lane = ARA + '.gen_lanes[1].i_lane.i_vfus.i_vmfpu'
    raw = lane + '.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice'
    signals = {'clk': 'ara_tb.clk'}
    signals.update({n.replace('.', '_'): lane + '.' + n for n in (
        'vfu_operation_i.vm', 'vfu_operation_i.id', 'vfu_operation_valid_i',
        'vinsn_issue_q.vm', 'vinsn_issue_q.id', 'vinsn_issue_q.vl', 'vinsn_issue_q_valid',
        'operand_a', 'operand_b', 'issue_be', 'vfpu_in_valid', 'vfpu_in_ready',
        'vfpu_out_valid', 'vfpu_out_ready', 'vfpu_tag_out.flag_mask',
        'vfpu_ex_flag_fn', 'fflags_ex_o', 'fflags_ex_valid_o')})
    signals.update({'raw_status': raw + '.lane_status', 'raw_masks': raw + '.lane_masks'})
    signals.update({'masku_' + n.replace('.', '_'): ARA + '.i_masku.' + n for n in (
        'vinsn_issue.vm', 'vinsn_issue.id', 'vinsn_issue.vstart', 'vinsn_issue.vl',
        'masku_operand_m_seq', 'result_queue_active_mask_seq', 'in_ready_cnt_en',
        'masku_operand_alu_valid', 'masku_operand_alu_ready', 'masku_operand_m_valid',
        'masku_operand_vd_valid', 'result_queue_full', 'vrf_pnt_q', 'vrf_pnt_d')})
    command = [str(VERDI / 'platform/linux64/bin/fsdbreport'), str(out / 'comparison.fsdb'),
               '-bt', '16200ns', '-et', '16600ns', '-csv', '-o', str(out / 'signals.csv'), '-s']
    for alias, path in signals.items():
        parts = path.split('.')
        if parts[-1] in ('vm', 'id', 'vl', 'vstart', 'flag_mask'):
            path = '/' + '/'.join(parts[:-1]) + '.' + parts[-1]
        else:
            path = '/' + '/'.join(parts)
        command += [path, '-a', alias, '-of', 'h']
    env = dict(os.environ, LD_LIBRARY_PATH=str(VERDI / 'etc/lib/libstdc++/linux64'))
    (out / 'report_command.json').write_text(json.dumps(command, indent=2) + '\n')
    with (out / 'report.log').open('w') as log:
        subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    if not (out / 'signals.csv').stat().st_size:
        raise ValueError('empty FSDB report')
    print(out / 'signals.csv')


if __name__ == '__main__':
    main()
