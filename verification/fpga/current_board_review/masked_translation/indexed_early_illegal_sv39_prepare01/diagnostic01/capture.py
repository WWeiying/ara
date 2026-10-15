#!/usr/bin/env python3
"""One bounded unchanged-M7 diagnostic; planned UCLI exit is not app PASS."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import vcs


def save(name, value):
    with (HERE / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def main():
    old = HERE.parent / 'vcs_m7_indexed01'
    plan = vcs.read(old / 'plan.json')
    assert vcs.sha(old / 'plan.json') == 'e83158226b6d59668069109b8e2b63b0e70dd197653c8b1131d50d0177778d4b'
    vcs.m7.base.verify_pins(plan['pins'])
    ledger, _, _ = vcs.m7.image_context(vcs.m7.M7)
    admission = vcs.m7.resources(HERE, 1, 0)
    elf = Path(plan['case']['elf'])
    assert vcs.sha(elf) == plan['case']['sha256']
    with (HERE / 'input.elf').open('xb') as f, elf.open('rb') as source:
        shutil.copyfileobj(source, f)
    top = 'ara_tb.dut.i_ara_soc.i_system'
    ara = top + '.i_ara'
    ag = ara + '.i_vlsu.i_addrgen'
    lsu = top + '.i_ariane.ex_stage_i.lsu_i'
    signals = ['ara_tb.clk', top + '.i_ara_commit_monitor.cycle_q']
    signals += [ag + '.' + s for s in (
        'state_q', 'axi_addrgen_state_q', 'idx_op_error_d', 'idx_op_error_q',
        'idx_final_vaddr_q', 'idx_vaddr_valid_q', 'mmu_req_o', 'mmu_req_d',
        'mmu_valid_i', 'addrgen_exception_o')]
    signals += [ara + '.' + s for s in (
        'ara_idle', 'store_pending', 'lsu_ex_flush_lane', 'lsu_ex_flush_done')]
    signals += [ara + '.i_dispatcher.lsu_ex_state_q']
    signals += [ara + '.i_vlsu.i_vstu.' + s for s in (
        'vinsn_queue_q', 'exception_pending_q', 'store_complete_o')]
    signals += [top + '.' + s for s in (
        'ara_axi_req', 'ara_axi_resp', 'ara_axi_req_delayed', 'ara_axi_resp_delayed',
        'ariane_axi_req', 'ariane_axi_resp', 'inval_valid', 'inval_ready')]
    commands = ['onerror {quit}', 'run -absolute 79000ns',
                'set fid [dump -file diagnostic.fsdb -type FSDB]']
    commands += ['dump -add {' + s + '} -aggregates -fid $fid' for s in signals]
    # The accelerator MMU arbiter is an unnamed generate inside this scope.
    commands += ['dump -add {' + lsu + '} -depth 2 -aggregates -fid $fid',
                 'run -absolute 83000ns', 'dump -disable -fid $fid',
                 'dump -flush $fid', 'run -absolute 85000ns',
                 'puts DIAGNOSTIC_COMPLETE_AT_85000NS', 'quit']
    with (HERE / 'capture.tcl').open('x') as f:
        f.write('\n'.join(commands) + '\n')
    save('profile.json', dict(signals=signals, lsu_scope=lsu, lsu_depth=2,
                              begin_ns=79000, end_ns=83000, stop_ns=85000))
    command = [ledger['simv'], '-no_save', '-ucli', '-do', str(HERE / 'capture.tcl'),
               '-l', 'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD=' + str(HERE / 'input.elf'),
               '+TESTCASE=indexed_prefix_vl3', '+NO_FSDB', '+COMMIT_TRACE=' + str(HERE / 'commit_trace.csv')]
    save('invocation.json', dict(command=command, cwd=str(HERE), admission=admission,
         original_plan_sha256=vcs.sha(old / 'plan.json'), original_complete_sha256=vcs.sha(old / 'complete.json'),
         image_sha256=vcs.sha(vcs.m7.M7 / 'image.json'), elf_sha256=vcs.sha(elf),
         script_sha256=vcs.sha(Path(__file__)), tcl_sha256=vcs.sha(HERE / 'capture.tcl'),
         input_pins=plan['pins'], host_bound_s=300, no_retry=True, architectural_acceptance=False))
    start = time.monotonic()
    timed_out = False
    with (HERE / 'console.log').open('x') as f:
        child = subprocess.Popen(command, cwd=HERE, env=vcs.m7.base.shared.environment(),
                                 stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        save('started.json', dict(worker_pid=os.getpid(), simv_pid=child.pid, wall_time=time.time()))
        print('simv_pid=' + str(child.pid), flush=True)
        try:
            rc = child.wait(timeout=300)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            rc = child.wait()
    vcs.m7.base.verify_pins(plan['pins'])
    vcs.m7.image_context(vcs.m7.M7)
    completed = 'DIAGNOSTIC_COMPLETE_AT_85000NS' in (HERE / 'console.log').read_text()
    save('complete.json', dict(returncode=rc, timed_out=timed_out, elapsed_s=time.monotonic()-start,
         planned_stop_observed=completed, pins_unchanged=True, architectural_acceptance=False,
         evidence={p.name:vcs.sha(p) for p in HERE.iterdir() if p.is_file() and p.name != 'complete.json'}))
    return int(rc != 0 or timed_out or not completed)


if __name__ == '__main__':
    sys.exit(main())
