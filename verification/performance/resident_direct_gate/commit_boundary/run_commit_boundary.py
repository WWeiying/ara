#!/usr/bin/env python3
"""Prepare only until reviewed; bounded host VCS execution in a direct systemd worker."""
import argparse
import csv
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
SIGNOFF = ROOT.parent / 'ara_dsa_signoff_integration'
HERE = SIGNOFF / 'verification/performance/resident_direct_gate/commit_boundary'
OUT = SIGNOFF / 'verification/out'
CORE = 'hardware/deps/cva6/core/'
COMMON = 'hardware/deps/common_cells/'
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
BASELINE = OUT / 'resident_direct_rtl_gate_unit_20261114_01/source-pins.json'
SOURCES = [COMMON + 'src/cf_math_pkg.sv', CORE + 'include/config_pkg.sv',
           CORE + 'include/cv64a6_imafdcv_sv39_config_pkg.sv', CORE + 'include/riscv_pkg.sv',
           CORE + 'include/ariane_pkg.sv', CORE + 'include/build_config_pkg.sv',
           'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/rvv_pkg.sv',
           'hardware/include/qbs_pkg.sv', 'hardware/include/akv_pkg.sv',
           COMMON + 'src/delta_counter.sv', COMMON + 'src/counter.sv',
           COMMON + 'src/spill_register_flushable.sv', COMMON + 'src/spill_register.sv',
           COMMON + 'src/fifo_v3.sv', 'hardware/src/common_cells_compat/fall_through_register_v1.sv',
           CORE + 'cva6_fifo_v3.sv', 'hardware/src/cva6_accel_first_pass_decoder.sv',
           CORE + 'csr_regfile.sv', CORE + 'decoder.sv', CORE + 'controller.sv', CORE + 'acc_dispatcher.sv',
           CORE + 'compressed_decoder.sv', CORE + 'id_stage.sv', CORE + 'scoreboard.sv',
           CORE + 'csr_buffer.sv', CORE + 'commit_stage.sv']
EXTRA = [CORE + 'cva6.sv', CORE + 'issue_stage.sv', CORE + 'include/rvfi_types.svh',
         'hardware/include/ara/intf_typedef.svh', COMMON + 'include/common_cells/registers.svh',
         COMMON + 'include/common_cells/assertions.svh',
         'verification/performance/resident_deployment/direct_cost/rtl_gate/run_integrated.py',
         'verification/performance/resident_deployment/direct_cost/rtl_gate/akv_gate_integrated_tb.sv',
         'verification/performance/resident_rvv/soc_boundary/commit_dirty/commit_dirty_tb.sv']
TYPES = ['branchpredict_sbe_t', 'exception_t', 'jvt_t', 'scoreboard_entry_t', 'irq_ctrl_t',
         'fu_data_t', 'dcache_req_i_t', 'dcache_req_o_t', 'bp_resolve_t', 'interrupts_t',
         'fetch_entry_t', 'writeback_t']
FIELDS = ['checks', 'requests', 'rejects', 'flushes', 'replays', 'pops', 'retires', 'races', 'waits']
MARK = ' '.join(key + r'=(\d+)' for key in FIELDS)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Input drift: ' + path)


def unit(out):
    return out.name.replace('_', '-') + '.service'


def prepare(out):
    require(not out.exists(), 'Output must be fresh; no overwrite/retry')
    spec = read(HERE / 'case_plan.json')
    baseline = read(BASELINE)
    # Check the original baseline inputs only; never change its frozen consumer.
    verify({p: h for p, h in baseline.items() if Path(p).is_relative_to(ROOT)})
    out.mkdir()
    inputs = out / 'inputs'
    pins = {}

    def freeze(source, destination):
        before = sha(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        require(before == sha(source) == sha(destination), 'Copy-time drift: ' + str(source))
        if str(source) in baseline:
            require(before == baseline[str(source)], 'Not the reviewed baseline: ' + str(source))
        pins[str(source)] = before
        pins[str(destination)] = before

    for relative in SOURCES + EXTRA:
        freeze(ROOT / relative, inputs / relative)
    for name in ('commit_boundary_tb.sv', 'case_plan.json', 'run_commit_boundary.py'):
        freeze(HERE / name, inputs / name)
    freeze(BASELINE, inputs / 'baseline-source-pins.json')
    text = (inputs / CORE / 'cva6.sv').read_text()
    definitions = []
    for name in TYPES:
        matches = re.findall(r'(?:localparam|parameter)\s+type\s+' + name +
                             r'\s*=\s*(struct\s+packed\s*\{[^{}]*\})\s*[,;]', text)
        require(len(matches) == 1, 'Ambiguous production type: ' + name)
        definitions.append('typedef ' + matches[0] + ' ' + name + ';')
    generated = inputs / 'gate_types.svh'
    with generated.open('x') as stream:
        stream.write('\n'.join(definitions) + '\n')
    pins[str(generated)] = sha(generated)
    pins[str(VCS)] = sha(VCS)
    build = out / 'build'
    command = [str(VCS), '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
               '+define+ARIANE_ACCELERATOR_PORT=1', '+define+ARA_QBS_ENABLE', '+define+ARA_AKV_ENABLE',
               '+define+ARA_AKV_V2_ENABLE', '+define+ARA_AKV_RESIDENT_PV_ENABLE', '+define+ARA_AKV_RESIDENT_QK_ENABLE',
               '-top', 'commit_boundary_tb', '-o', str(build / 'simv'), '-Mdir=' + str(build / 'csrc')]
    command += ['+incdir+' + str(inputs / p) for p in
                (COMMON + 'include', CORE + 'include', 'hardware/include', '.')]
    command += [str(inputs / p) for p in SOURCES] + [str(inputs / 'commit_boundary_tb.sv')]
    environment = {k: os.environ[k] for k in ('PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG',
                    'LD_LIBRARY_PATH', 'VCS_ARCH_OVERRIDE', 'CC', 'CXX') if k in os.environ}
    environment.update(VCS_HOME=str(VCS.parent.parent),
                       SNPSLMD_LICENSE_FILE=os.environ.get('SNPSLMD_LICENSE_FILE', '27000@t7920'),
                       PYTHONDONTWRITEBYTECODE='1')
    save(out / 'plan.json', dict(spec=spec, compile=command, simulate=[str(build / 'simv')],
                                environment=environment, compile_timeout_seconds=180,
                                simulate_timeout_seconds=30, source_root=str(ROOT),
                                source_branch=subprocess.check_output(['git', '-C', str(ROOT), 'branch', '--show-current'], text=True).strip(),
                                source_head=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()))
    pins[str(out / 'plan.json')] = sha(out / 'plan.json')
    verify(pins)
    save(out / 'source-pins.json', pins)
    review = sha(out / 'source-pins.json')
    launch = ['systemd-run', '--user', '--unit=' + unit(out), '--property=Type=exec',
              '--property=KillMode=control-group', '--property=RuntimeMaxSec=270', '--property=TimeoutStopSec=10',
              '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
              '--property=StandardError=append:' + str(out / 'service.stderr.log'),
              sys.executable, '-B', '-u', str(inputs / 'run_commit_boundary.py'), 'execute',
              '--output', str(out), '--review-sha256', review]
    save(out / 'launch-command.json', launch)
    print(json.dumps(dict(state='PREPARED_NOT_LAUNCHED', output=str(out),
                          source_pins_sha256=review, launch=launch), indent=2))


def parse_cases(text):
    return [dict(name=m[0], **dict(zip(FIELDS, map(int, m[1:]))))
            for m in re.findall(r'^COMMIT_BOUNDARY_CASE_PASS name=(\w+) ' + MARK + '$', text, re.M)]


def check_results(out, plan, text):
    require(not re.search(r'COMMIT_BOUNDARY_FAIL|Error-|\bError\b|\bFatal\b', text), 'Simulation failure marker')
    cases = parse_cases(text)
    require([c['name'] for c in cases] == [c['name'] for c in plan['spec']['cases']], 'Missing/duplicate/out-of-order cases')
    for actual, expected in zip(cases, plan['spec']['cases']):
        require(actual['checks'] > 0, 'Empty checks: ' + actual['name'])
        for key, count in expected['expected'].items():
            require(actual[key] == count, actual['name'] + ': wrong ' + key)
    match = re.findall(r'^COMMIT_BOUNDARY_PASS cases=(\d+) ' + MARK + '$', text, re.M)
    require(len(match) == 1 and int(match[0][0]) == len(cases), 'Missing unique total PASS')
    totals = dict(zip(FIELDS, map(int, match[0][1:])))
    require(all(totals[k] == sum(c[k] for c in cases) for k in FIELDS), 'Total/case count mismatch')
    with (out / 'simulation/events.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    require(rows and all(None not in row and None not in row.values() for row in rows), 'Malformed/empty CSV')
    require([int(row['cycle']) for row in rows] == list(range(1, len(rows)+1)), 'CSV cycle gap')
    for case in cases:
        active = [r for r in rows if r['case'] == case['name'] and r['rst_n'] == '1']
        counts = dict(requests=sum(r['req_valid'] == '1' and r['req_ready'] == '1' for r in active),
                      pops=sum(r['queue_pop'] == '1' for r in active),
                      retires=sum(r['acc_retire'] == '1' for r in active))
        require(all(case[k] == v for k, v in counts.items()), 'CSV/mark mismatch: ' + case['name'])
    return cases, totals, len(rows)


def execute(out, review):
    require(Path(__file__).resolve() == out / 'inputs/run_commit_boundary.py', 'Frozen runner only')
    require(sha(out / 'source-pins.json') == review, 'Reviewed pin inventory mismatch')
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit(out), '-p', 'MainPID', '--value'], text=True).strip()
    require(owner == str(os.getpid()), 'Worker must be directly owned by systemd service')
    save(out / 'attempt.json', dict(pid=os.getpid(), cgroup=Path('/proc/self/cgroup').read_text(), host=os.uname().nodename))
    pins, plan = read(out / 'source-pins.json'), read(out / 'plan.json')
    result = dict(schema_version=1, state='FAIL', scope=plan['spec']['scope'], config=plan['spec']['config'],
                  cases=[], totals={}, artifacts={}, pins=dict(source_pins_sha256=review, pre_match=False, post_match=False),
                  whole_core_tested=False, board_tested=False, automatic_retry=False)

    def run(name, command, seconds):
        directory = out / name
        directory.mkdir()
        status, timed_out = None, False
        with (directory / 'console.log').open('x') as log:
            child = subprocess.Popen(command, cwd=directory, env=plan['environment'], stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            save(directory / 'process.json', dict(pid=child.pid, command=command))
            try:
                status = child.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(child.pid, sig)
                    except ProcessLookupError:
                        pass
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                child.wait()
        save(directory / 'command.json', dict(command=command, returncode=status, timed_out=timed_out))
        require(not timed_out and status == 0, 'Failed/timed out: ' + name)
        return (directory / 'console.log').read_text()

    try:
        verify(pins)
        result['pins']['pre_match'] = True
        compile_log = run('build', plan['compile'], plan['compile_timeout_seconds'])
        require(not re.search(r'Error-|\bFatal\b', compile_log), 'Compiler failure marker')
        verify(pins)
        text = run('simulation', plan['simulate'], plan['simulate_timeout_seconds'])
        cases, totals, rows = check_results(out, plan, text)
        result.update(cases=cases, totals=totals, event_rows=rows)
        verify(pins)
        result['pins']['post_match'] = True
        result['state'] = 'REAL_COMMIT_BOUNDARY_CHECKED'
    except BaseException as error:
        result['error'] = repr(error)
        log = out / 'simulation/console.log'
        if log.exists():
            result['cases'] = parse_cases(log.read_text())
        try:
            verify(pins)
            result['pins']['post_match'] = True
        except Exception as drift:
            result['pin_error'] = repr(drift)
    for name, relative in dict(simv='build/simv', compile_log='build/console.log',
                               simulation_log='simulation/console.log', events_csv='simulation/events.csv').items():
        path = out / relative
        if path.is_file():
            result['artifacts'][name] = dict(path=str(path), sha256=sha(path))
    save(out / 'result.json', result)
    print(json.dumps(result), flush=True)
    return int(result['state'] == 'FAIL')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.parent == OUT and out.name.startswith('resident_gate_commit_'), 'Unexpected output directory')
    if args.action == 'prepare':
        prepare(out)
        return 0
    return execute(out, args.review_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
