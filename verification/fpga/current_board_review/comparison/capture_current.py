#!/usr/bin/env python3
"""Read-only selective UCLI capture of unchanged comparison ELFs and frozen image."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'integration'))
import run as checked
from prepare import sha, save

IMAGE = Path('/home/wangwy/fpga_runs/current_board_integration_final01/campaign/image')
ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'


def profile():
    names = ['ara_tb.clk', ARA + '.ara_req', ARA + '.ara_req_valid',
             ARA + '.fflags_ex', ARA + '.fflags_ex_valid']
    lane = ARA + '.gen_lanes[1].i_lane.i_vfus.i_vmfpu'
    names += [lane + '.' + n for n in (
        'vfu_operation_i', 'vfu_operation_valid_i', 'vinsn_issue_q', 'vinsn_issue_q_valid',
        'issue_cnt_q', 'issue_be', 'operand_a', 'operand_b', 'vfpu_in_valid', 'vfpu_in_ready',
        'vfpu_out_valid', 'vfpu_out_ready', 'vfpu_tag_in', 'vfpu_tag_out',
        'vfpu_ex_flag_fn', 'vfpu_ex_flag', 'fflags_ex_o', 'fflags_ex_valid_o',
        'mask_operand_o', 'mask_operand_valid_o', 'mask_operand_ready_i')]
    names += [lane + '.fpu_gen.vfpu_simd_mask']
    raw = lane + '.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice'
    names += [raw + '.' + n for n in ('lane_status', 'lane_masks', 'out_valid_o', 'out_ready_i')]
    names += [ARA + '.i_masku.' + n for n in (
        'vinsn_issue', 'vinsn_issue_valid', 'masku_operand_m_seq',
        'masku_operand_alu_valid', 'masku_operand_alu_ready',
        'masku_operand_m_valid', 'masku_operand_m_ready', 'masku_operand_vd_valid',
        'result_queue_full', 'result_queue_active_mask_seq', 'alu_result_compressed_seq',
        'in_ready_cnt_en', 'iteration_cnt_q', 'vrf_pnt_q', 'vrf_pnt_d', 'issue_cnt_q',
        'masku_result_req_o', 'masku_result_gnt_i', 'pe_resp_o')]
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', choices=['all_off', 'active_snan', 'no_snan'], default='all_off')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE):
        parser.error('output must stay under comparison/')
    out.mkdir(exist_ok=False, parents=True)
    if sha(HERE.parent / 'integration/run.py') != 'c1c3804dbe36fa981ea7b6cbcfa5d7b69fb793b2a14c37831fb96e866f2d2a78':
        raise ValueError('checked runner drift')
    base = dict(image=IMAGE, programs=HERE / 'soc', case=[args.case], jobs=1, timeout=120, execute=False)
    checked.run_programs(SimpleNamespace(out=out / 'validate_before', **base))
    ledger = json.loads((IMAGE / 'image.json').read_text())
    source = HERE / 'soc' / (args.case + '.elf')
    elf = out / 'input.elf'
    shutil.copyfile(source, elf)
    if sha(elf) != json.loads((HERE / 'soc/programs.json').read_text())['programs'][args.case]['sha256']:
        raise ValueError('ELF drift')
    signals = profile()
    save(out / 'signals.json', signals)
    tcl = ['onerror {quit}', 'set fid [dump -file comparison.fsdb -type FSDB]']
    tcl += ['dump -add {' + n + '} -aggregates -fid $fid' for n in signals]
    tcl += ['dump -disable -fid $fid', 'run -absolute 16200ns',
            'dump -enable -fid $fid', 'run -absolute 16600ns',
            'dump -disable -fid $fid', 'dump -flush $fid', 'run', 'quit']
    (out / 'capture.tcl').write_text('\n'.join(tcl) + '\n')
    command = [ledger['simv'], '-no_save', '-ucli', '-do', str(out / 'capture.tcl'), '-l', 'run.vcs.log',
               '+ntb_random_seed=1', '+PRELOAD=' + str(elf), '+TESTCASE=' + args.case, '+NO_FSDB',
               '+COMMIT_TRACE=' + str(out / 'commit_trace.csv')]
    save(out / 'command.json', dict(command=command, cwd=str(out), elf_sha256=sha(elf),
                                   image_ledger_sha256=sha(IMAGE / 'image.json'), window_ns=[16200,16600],
                                   script_sha256=sha(Path(__file__)), case=args.case))
    with (out / 'console.log').open('w') as log:
        result = subprocess.run(command, cwd=out, env=checked.environment(), stdout=log,
                                stderr=subprocess.STDOUT, timeout=120)
    checked.run_programs(SimpleNamespace(out=out / 'validate_after', **base))
    log = (out / 'console.log').read_text()
    measurement = [line for line in log.splitlines() if line.startswith('CMP_RESULT')]
    dump = out / 'comparison.fsdb'
    status = dict(simulator_exit=result.returncode, measurement=measurement,
                  architectural_status='FAIL' if 'BOARD_CASE_FAIL ' + args.case in log else
                  'PASS' if 'BOARD_CASE_PASS ' + args.case in log else 'UNKNOWN',
                  fsdb_bytes=dump.stat().st_size if dump.exists() else 0,
                  signal_count=len(signals), no_rtl_edits=True, no_build=True)
    save(out / 'status.json', status)
    print(json.dumps(status, indent=2))
    return int(status['architectural_status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
