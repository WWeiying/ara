#!/usr/bin/env python3
"""Capture exactly 50 signals for 400 ns using the unchanged final02 image."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
from adapter import HERE, IMAGE, checked, inside, prepare

ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
CORE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane'


def profile():
    names = ['ara_tb.clk', CORE + '.csr_regfile_i.cycle_q']
    names += [ARA + '.' + n for n in (
        'mfpu_reduction_any_active', 'mfpu_reduction_global_any_active',
        'ara_req', 'ara_req_valid', 'ara_req_ready',
        'i_sequencer.pe_req_valid_o', 'i_sldu.state_q', 'i_sldu.sldu_red_valid_o')]
    for lane in (0, 1):
        prefix = ARA + f'.gen_lanes[{lane}].i_lane.i_vfus.i_vmfpu.'
        names += [prefix + n for n in (
            'mfpu_state_q', 'mfpu_state_d', 'vinsn_issue_q', 'first_op_q',
            'vfpu_in_valid', 'vfpu_in_ready', 'vfpu_out_valid', 'vfpu_out_ready',
            'vfpu_ex_flag', 'fpu_gen.reduction_fflags_q', 'reduction_any_active_q',
            'sldu_transactions_cnt_q', 'sldu_mfpu_valid_q', 'sldu_mfpu_ready_d',
            'mfpu_red_valid_o', 'mfpu_red_ready_i', 'mfpu_vinsn_done_o',
            'mfpu_result_req_o', 'mfpu_result_gnt_i', 'mfpu_result_wdata_o')]
    assert len(names) == 50
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--start-ns', type=int, required=True)
    args = parser.parse_args()
    build, out = inside(args.build), inside(args.out)
    out.mkdir(parents=True, exist_ok=False)
    base = dict(image=IMAGE, programs=build / 'soc', case=['all'], jobs=1,
                timeout=90, execute=False)
    checked.run_programs(SimpleNamespace(out=out / 'validate_before', **base))
    ledger = json.loads((IMAGE / 'image.json').read_text())
    elf = out / 'input.elf'
    shutil.copyfile(build / 'soc/all.elf', elf)
    signals = profile()
    prepare.save(out / 'signals.json', signals)
    start, end = args.start_ns, args.start_ns + 400
    tcl = ['onerror {quit}', 'set fid [dump -file epoch.fsdb -type FSDB]']
    tcl += ['dump -add {' + n + '} -aggregates -fid $fid' for n in signals]
    tcl += ['dump -disable -fid $fid', f'run -absolute {start}ns',
            'dump -enable -fid $fid', f'run -absolute {end}ns',
            'dump -disable -fid $fid', 'dump -flush $fid', 'run', 'quit']
    (out / 'capture.tcl').write_text('\n'.join(tcl) + '\n')
    command = [ledger['simv'], '-no_save', '-ucli', '-do', str(out / 'capture.tcl'),
               '-l', 'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD=' + str(elf),
               '+TESTCASE=epoch_capture', '+NO_FSDB',
               '+COMMIT_TRACE=' + str(out / 'commit_trace.csv')]
    prepare.save(out / 'command.json', dict(command=command, cwd=str(out),
        elf_sha256=prepare.sha(elf), image_ledger_sha256=prepare.sha(IMAGE / 'image.json'),
        script_sha256=prepare.sha(Path(__file__)), window_ns=[start, end]))
    began = time.monotonic()
    with (out / 'console.log').open('w') as log:
        result = subprocess.run(command, cwd=out, env=checked.environment(),
                                stdout=log, stderr=subprocess.STDOUT, timeout=90)
    elapsed = time.monotonic() - began
    checked.run_programs(SimpleNamespace(out=out / 'validate_after', **base))
    log = (out / 'console.log').read_text()
    status = dict(simulator_exit=result.returncode, elapsed_s=elapsed,
                  measurement=[n for n in log.splitlines() if n.startswith('EPOCH_RESULT')],
                  signal_count=len(signals), no_rtl_edits=True, no_build=True)
    prepare.save(out / 'status.json', status)
    if not (out / 'epoch.fsdb').is_file():
        raise ValueError('missing bounded FSDB')
    command = [str(checked.VERDI / 'platform/linux64/bin/fsdb2vcd'), 'epoch.fsdb',
               '-o', 'selected.vcd', '-bt', f'{start}ns', '-et', f'{end}ns',
               '-compacttree', '-s']
    command += ['/' + name.replace('.', '/') for name in signals]
    prepare.save(out / 'convert_command.json', command)
    env = dict(os.environ, LD_LIBRARY_PATH=str(checked.VERDI / 'etc/lib/libstdc++/linux64'))
    with (out / 'convert.log').open('w') as log:
        subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=90)
    print(json.dumps(status, indent=2))


if __name__ == '__main__':
    main()
