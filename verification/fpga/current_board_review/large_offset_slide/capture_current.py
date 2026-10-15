#!/usr/bin/env python3
"""Capture a bounded large-offset slide window without rebuilding RTL or ELF."""
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

IMAGE = Path('/home/wangwy/fpga_runs/current_board_integration_final03/campaign/image')
PROGRAMS = HERE / 'prepared01/soc'
ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'


def profile():
    names = ['ara_tb.clk', ARA + '.ara_req', ARA + '.ara_req_valid',
             ARA + '.sldu_addrgen_operand', ARA + '.sldu_operand_valid',
             ARA + '.sldu_operand_ready']
    for unit, signals in {
        'i_masku': ('vinsn_issue', 'vinsn_issue_valid', 'mask_pnt_q', 'read_cnt_q',
                    'masku_operand_m', 'masku_operand_m_valid', 'masku_operand_m_ready',
                    'mask_queue_q', 'mask_queue_valid_q', 'mask_queue_first_q',
                    'mask_queue_read_pnt_q', 'mask_queue_write_pnt_q', 'mask_queue_cnt_q'),
        'i_sldu': ('state_q', 'vinsn_issue_q', 'vinsn_issue_valid_q',
                   'issue_cnt_q', 'commit_cnt_q', 'vrf_pnt_q', 'in_pnt_q', 'out_pnt_q',
                   'output_limit_q', 'sldu_operand', 'sldu_operand_valid',
                   'sldu_operand_ready', 'sld_op_dst', 'mask_i', 'mask_valid_i',
                   'mask_ready_o', 'mask_q', 'mask_valid_q', 'mask_ready_d',
                   'out_en_seq', 'out_en_flat', 'out_en', 'result_queue_q',
                   'result_queue_valid_q', 'sldu_result_req_o', 'sldu_result_gnt_i',
                   'sldu_result_addr_o', 'sldu_result_wdata_o', 'sldu_result_be_o'),
        'gen_lanes[0].i_lane.i_lane_sequencer':
            ('operand_request', 'operand_request_push'),
    }.items():
        names += [ARA + '.' + unit + '.' + s for s in signals]
    return names


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE):
        p.error('output must remain under large_offset_slide/')
    out.mkdir(parents=True, exist_ok=False)
    base = dict(image=IMAGE, programs=PROGRAMS, case=['e8_m8_single'],
                jobs=1, timeout=420, execute=False)
    checked.run_programs(SimpleNamespace(out=out / 'validate_before', **base))
    ledger = json.loads((IMAGE / 'image.json').read_text())
    elf = out / 'input.elf'
    shutil.copyfile(PROGRAMS / 'e8_m8_single.elf', elf)
    expected = json.loads((PROGRAMS / 'programs.json').read_text())['programs']['e8_m8_single']['sha256']
    if sha(elf) != expected:
        raise ValueError('ELF drift')
    signals = profile()
    save(out / 'signals.json', signals)
    # Original scalar commit trace places the target at 103398 ns and its
    # completion-dependent vstart read at 103701 ns. Include setup and drain.
    window = [103200, 104000]
    tcl = ['onerror {quit}', 'set fid [dump -file slide.fsdb -type FSDB]']
    tcl += ['dump -add {' + n + '} -aggregates -fid $fid' for n in signals]
    tcl += ['dump -disable -fid $fid', f'run -absolute {window[0]}ns',
            'dump -enable -fid $fid', f'run -absolute {window[1]}ns',
            'dump -disable -fid $fid', 'dump -flush $fid', 'run', 'quit']
    (out / 'capture.tcl').write_text('\n'.join(tcl) + '\n')
    command = [ledger['simv'], '-no_save', '-ucli', '-do', str(out / 'capture.tcl'),
               '-l', 'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD=' + str(elf),
               '+TESTCASE=e8_m8_single', '+NO_FSDB',
               '+COMMIT_TRACE=' + str(out / 'commit_trace.csv')]
    save(out / 'command.json', dict(command=command, cwd=str(out),
        elf_sha256=sha(elf), image_ledger_sha256=sha(IMAGE / 'image.json'),
        window_ns=window, script_sha256=sha(Path(__file__))))
    status = dict(state='RUNNING', no_build=True, no_rtl_edits=True)
    save(out / 'status.json', status)
    try:
        with (out / 'console.log').open('w') as log:
            run = subprocess.run(command, cwd=out, env=checked.environment(),
                                 stdout=log, stderr=subprocess.STDOUT, timeout=420)
        status['simulator_exit'] = run.returncode
        checked.run_programs(SimpleNamespace(out=out / 'validate_after', **base))
        log = (out / 'console.log').read_text()
        status['measurement'] = [line for line in log.splitlines()
                                 if line.startswith('RVV_PERMUTE_')]
        status['architectural_status'] = ('FAIL' if 'BOARD_CASE_FAIL e8_m8_single' in log
            else 'PASS' if 'BOARD_CASE_PASS e8_m8_single' in log else 'UNKNOWN')
        dump = out / 'slide.fsdb'
        status['fsdb_bytes'] = dump.stat().st_size if dump.exists() else 0
        status['state'] = ('CAPTURED' if status['fsdb_bytes'] and
                           status['architectural_status'] != 'UNKNOWN' else 'ERROR')
    except Exception as error:
        status.update(state='ERROR', error=repr(error))
    save(out / 'status.json', status)
    print(json.dumps(status, indent=2))
    return int(status['state'] != 'CAPTURED')


if __name__ == '__main__':
    raise SystemExit(main())
