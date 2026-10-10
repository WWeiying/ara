#!/usr/bin/env python3
"""Bounded old-image probe: source beats, reduction counters and FP feedback."""
from pathlib import Path
import subprocess
import sys

import run_vcs_dve_checkpoint as base

ROOT = base.ROOT
OUT = ROOT / 'verification/out/gap76-red16-probe-20261006-01'
CASE = ROOT / 'verification/out/gap76-old-image-20261006-01/results/vgap76_red16'
IMAGE = ROOT / 'verification/out/repaired-aligned-build-20260930-01'


def main():
    base.check_service()
    OUT.mkdir(exist_ok=False)
    state = dict(status='RUNNING', scope='diagnostic only; not coverage admission',
                 hypothesis='final real source beat includes tail while neutral-fill credits remain')
    base.save(OUT / 'status.json', state)
    try:
        pins = base.read(IMAGE / 'build-image.json')
        pins.update(base.pins([CASE / 'input.elf', Path(__file__)]))
        base.check(pins)
        base.save(OUT / 'pins.json', pins)
        script = ['run 13.2us', 'dump -file reduction.fsdb -type FSDB',
                  'dump -add {ara_tb.clk}']
        profile = dict(clock='/ara_tb/clk', edge='posedge', raw_time_unit='100fs', signals=[])
        names = ['mfpu_state_q', 'mfpu_state_d', 'issue_cnt_q', 'issue_cnt_d',
                 'intra_op_rx_cnt_q', 'intra_op_rx_cnt_d', 'to_process_cnt_q',
                 'first_op_q', 'ntr_filling_q', 'intra_issued_op_cnt_q',
                 'mfpu_operand_i', 'mfpu_operand_valid_i', 'mfpu_operand_ready_o',
                 'mask_i', 'mask_valid_i', 'mask_ready_o', 'issue_be',
                 'operand_a', 'operand_b', 'operand_c', 'vfpu_control_in',
                 'vfpu_in_valid', 'vfpu_in_ready', 'vfpu_out_valid', 'vfpu_result',
                 'simd_red_cnt_q', 'simd_red_cnt_max_q', 'mfpu_result_wdata_o']
        for lane in range(4):
            scope = f'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[{lane}].i_lane.i_vfus.i_vmfpu'
            script.append('dump -add {' + scope + '} -depth 1 -aggregates')
            for name in names:
                profile['signals'].append(dict(alias=f'l{lane}_{name}',
                    path='/' + scope.replace('.', '/') + '/' + name,
                    format='h', required=True))
        script += ['run 0.35us', 'dump -close', 'quit']
        (OUT / 'probe.tcl').write_text('\n'.join(script) + '\n')
        base.save(OUT / 'profile.json', profile)
        command = [str(IMAGE / 'sim/simv'), '-ucli', '-do', str(OUT / 'probe.tcl'),
            '-l', 'probe.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(CASE / 'input.elf'), '+TESTCASE=gap76_red16_probe',
            '+VECTOR_TRACE=' + str(OUT / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(OUT / 'diagnostic.vdb')]
        base.save(OUT / 'command.json', dict(command=command, timeout_s=900))
        with (OUT / 'console.log').open('w') as log:
            subprocess.run(command, cwd=OUT, stdout=log, stderr=subprocess.STDOUT,
                           timeout=900, check=True)
        base.check(pins)
        command = [sys.executable, str(ROOT / 'hardware/scripts/fsdb_trace/extract_cycles.py'),
            '--fsdb', str(OUT / 'reduction.fsdb'), '--profile', str(OUT / 'profile.json'),
            '--begin', '13.2us', '--end', '13.55us', '--output', str(OUT / 'cycles'),
            '--fsdbreport', '/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1/bin/fsdbreport']
        with (OUT / 'extract.log').open('w') as log:
            subprocess.run(command, cwd=OUT, stdout=log, stderr=subprocess.STDOUT,
                           timeout=180, check=True)
        state.update(status='COMPLETE', phase='cycle evidence ready')
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
        raise
    finally:
        base.save(OUT / 'status.json', state)


if __name__ == '__main__':
    main()
