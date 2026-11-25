#!/usr/bin/env python3
"""Freeze and run a bounded real CSR/decoder/controller/dispatcher VCS unit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
HERE = ROOT / 'verification/performance/resident_deployment/direct_cost/rtl_gate'
CORE = 'hardware/deps/cva6/core/'
COMMON = 'hardware/deps/common_cells/'
SOURCES = [COMMON + 'src/cf_math_pkg.sv', CORE + 'include/config_pkg.sv',
           CORE + 'include/cv64a6_imafdcv_sv39_config_pkg.sv', CORE + 'include/riscv_pkg.sv',
           CORE + 'include/ariane_pkg.sv', CORE + 'include/build_config_pkg.sv',
           'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/rvv_pkg.sv',
           'hardware/include/qbs_pkg.sv', 'hardware/include/akv_pkg.sv',
           COMMON + 'src/delta_counter.sv', COMMON + 'src/counter.sv',
           COMMON + 'src/spill_register_flushable.sv', COMMON + 'src/spill_register.sv',
           'hardware/src/common_cells_compat/fall_through_register_v1.sv',
           CORE + 'cva6_fifo_v3.sv', 'hardware/src/cva6_accel_first_pass_decoder.sv',
           CORE + 'csr_regfile.sv', CORE + 'decoder.sv', CORE + 'controller.sv', CORE + 'acc_dispatcher.sv',
           str((HERE / 'akv_gate_tb.sv').relative_to(ROOT))]
EXTRA = [CORE + 'cva6.sv', CORE + 'include/rvfi_types.svh', 'hardware/include/ara/intf_typedef.svh',
         COMMON + 'include/common_cells/registers.svh', COMMON + 'include/common_cells/assertions.svh',
         str(Path(__file__).resolve().relative_to(ROOT))] if Path(__file__).resolve().is_relative_to(ROOT) else []
TYPES = ['branchpredict_sbe_t', 'exception_t', 'jvt_t', 'scoreboard_entry_t', 'irq_ctrl_t',
         'fu_data_t', 'dcache_req_i_t', 'dcache_req_o_t', 'bp_resolve_t', 'interrupts_t']


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def save(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2); stream.write('\n')
def require(ok, message):
    if not ok: raise ValueError(message)
def verify(pins):
    for p, h in pins.items(): require(sha(p) == h, 'Input drift: ' + p)
def unit(out): return 'resident-direct-gate-' + out.name + '.service'


def prepare(out):
    require(out.parent == OUT and out.name.startswith('resident_direct_rtl_gate_unit_') and not out.exists(),
            'Fresh direct signoff output required')
    out.mkdir(); inputs = out / 'inputs'; inputs.mkdir()
    pins = {}
    for relative in SOURCES + EXTRA:
        source = ROOT / relative
        destination = inputs / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        pins[str(source)], pins[str(destination)] = sha(source), sha(destination)
    generated = inputs / 'generated'; generated.mkdir()
    text = (inputs / CORE / 'cva6.sv').read_text()
    definitions = []
    for name in TYPES:
        matches = re.findall(r'(?:localparam|parameter)\s+type\s+' + name +
                             r'\s*=\s*(struct\s+packed\s*\{[^{}]*\})\s*[,;]', text)
        require(len(matches) == 1, 'Ambiguous real CVA6 type: ' + name)
        definitions.append('typedef ' + matches[0] + ' ' + name + ';')
    with (generated / 'gate_types.svh').open('x') as stream: stream.write('\n'.join(definitions) + '\n')
    pins[str(generated / 'gate_types.svh')] = sha(generated / 'gate_types.svh')
    shutil.copyfile(__file__, inputs / 'run.py')
    pins[str(inputs / 'run.py')] = sha(inputs / 'run.py')
    vcs = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
    pins[str(vcs)] = sha(vcs)
    build = out / 'build'
    command = [str(vcs), '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
               '+define+ARIANE_ACCELERATOR_PORT=1', '+define+ARA_QBS_ENABLE', '+define+ARA_AKV_ENABLE',
               '+define+ARA_AKV_V2_ENABLE', '+define+ARA_AKV_RESIDENT_PV_ENABLE', '+define+ARA_AKV_RESIDENT_QK_ENABLE',
               '-top', 'akv_gate_tb', '-o', str(build / 'simv'), '-Mdir=' + str(build / 'csrc')]
    command += ['+incdir+' + str(inputs / p) for p in
                (COMMON + 'include', CORE + 'include', 'hardware/include', 'generated')]
    command += [str(inputs / p) for p in SOURCES]
    environment = {k: os.environ[k] for k in ('PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG',
                    'LD_LIBRARY_PATH', 'VCS_ARCH_OVERRIDE', 'CC', 'CXX') if k in os.environ}
    environment.update(VCS_HOME=str(vcs.parent.parent),
                       SNPSLMD_LICENSE_FILE=os.environ.get('SNPSLMD_LICENSE_FILE', '27000@t7920'),
                       PYTHONDONTWRITEBYTECODE='1')
    save(out / 'plan.json', dict(compile=command, simulate=[str(build / 'simv')], environment=environment,
                                scope='actual RV64 no-H CSR, decoder, first-pass decoder, controller and dispatcher; no whole-core/SoC/FPGA claim',
                                compile_timeout_seconds=180, simulate_timeout_seconds=30))
    pins[str(out / 'plan.json')] = sha(out / 'plan.json'); verify(pins)
    save(out / 'source-pins.json', pins)
    review = sha(out / 'source-pins.json')
    launch = ['systemd-run', '--user', '--unit=' + unit(out), '--property=Type=exec', '--property=KillMode=control-group',
              '--property=RuntimeMaxSec=300', '--property=TimeoutStopSec=20',
              '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
              '--property=StandardError=append:' + str(out / 'service.stderr.log'),
              sys.executable, '-B', '-u', str(inputs / 'run.py'), 'execute', '--output', str(out), '--review-sha256', review]
    save(out / 'launch-command.json', launch)
    print(json.dumps(dict(state='PREPARED_NOT_LAUNCHED', output=str(out), review_sha256=review, launch=launch)))


def execute(out, review):
    require(Path(__file__).resolve() == out / 'inputs/run.py' and sha(out / 'source-pins.json') == review, 'Frozen reviewed runner only')
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit(out), '-p', 'MainPID', '--value'], text=True).strip()
    require(owner == str(os.getpid()), 'Worker must be directly owned by service')
    save(out / 'attempt.json', dict(pid=os.getpid(), cgroup=Path('/proc/self/cgroup').read_text()))
    pins, plan = read(out / 'source-pins.json'), read(out / 'plan.json')
    result = dict(state='FAIL', whole_core_tested=False, soc_tested=False, board_tested=False, automatic_retry=False)
    def run(name, command, seconds):
        directory = out / name; directory.mkdir()
        with (directory / 'console.log').open('x') as log:
            child = subprocess.Popen(command, cwd=directory, env=plan['environment'], stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            save(directory / 'process.json', dict(pid=child.pid, command=command))
            try: status = child.wait(timeout=seconds)
            finally:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try: os.killpg(child.pid, sig)
                    except ProcessLookupError: pass
                    try: child.wait(timeout=2)
                    except subprocess.TimeoutExpired: pass
                child.wait()
        save(directory / 'command.json', dict(command=command, returncode=status))
        require(status == 0, 'Failed ' + name)
        return (directory / 'console.log').read_text()
    try:
        verify(pins)
        run('build', plan['compile'], plan['compile_timeout_seconds'])
        text = run('simulation', plan['simulate'], plan['simulate_timeout_seconds'])
        require('GATE_FAIL' not in text and 'Error-' not in text and 'Fatal' not in text, 'RTL error/failure marker')
        matches = re.findall(r'^GATE_PASS decode=(\d+) blocked=(\d+) noissue=(\d+) csr=(\d+) flush=(\d+) requests=(\d+) checks=(\d+)$', text, re.M)
        require(len(matches) == 1, 'Exactly one completion required')
        counts = list(map(int, matches[0]))
        require(counts[:3] == [24672, 3072, 25] and counts[4:6] == [2, 1] and counts[6] > 50000, 'Coverage cardinality')
        verify(pins)
        result.update(state='REAL_MODULE_GATE_CHECKED', decode_cases=counts[0], blocked_cases=counts[1],
                      noissue_cases=counts[2], csr_cases=counts[3], flush_cases=counts[4], requests=counts[5], checks=counts[6],
                      post_pins_match=True, simv_sha256=sha(out / 'build/simv'), log_sha256=sha(out / 'simulation/console.log'))
    except BaseException as error: result['error'] = repr(error)
    save(out / 'result.json', result); print(json.dumps(result), flush=True)
    return int(result['state'] == 'FAIL')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-sha256')
    args = parser.parse_args(); out = args.output.resolve()
    require(out.parent == OUT and out.name.startswith('resident_direct_rtl_gate_unit_'), 'Unexpected output')
    if args.action == 'prepare': prepare(out); return 0
    return execute(out, args.review_sha256)


if __name__ == '__main__': raise SystemExit(main())
