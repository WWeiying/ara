#!/usr/bin/env python3
"""First complete timed-call activity windows, minimum 20000 cycles, no RTL edits."""
import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('vrf_environment', HERE / 'gate_vrf_env_v2.py')
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
b, g = e.b, e.g
IMAGE = e.BUILD
e.configure(IMAGE)
CRITICAL = re.compile(r'input (?:CLK|CEB/CEBM|WEB/WEBM|A/AM|BWEB/BWEBM) unknown/high-Z')
CASES = {
    'q8': dict(id=b.Q8, first=1446, last=44479, maximum=45000,
        queue='power_precheck_20261117_native_q8_successor_01', release='q8',
        stages='Quantize + all eight QBS commands and real waits; prebuilt descriptor outside timer',
        anchors={'start_pc': '80001854', 'end_pc': '80001884', 'start_csr': 1446, 'end_csr': 44479}),
    'm1': dict(id='qwen3_real_decode_attn_q_m1_n64_native', first=12858, last=40099, maximum=41000,
        queue='power_precheck_20261117_native_projection_01', release='m1',
        stages='First trial t0..t5: quantize + packing/descriptor + both QBS commands + waits/CSR',
        anchors={'t0': 12858, 't1': 24426, 't2': 24437, 't3': 31949, 't4': 40066, 't5': 40099}),
    'm4': dict(id='qwen3_attn_q_q4k_m4_n64_direct_native', first=121568, last=213045, maximum=214000,
        queue='power_precheck_20261117_native_projection_01', release='m4',
        stages='First trial t0..t5: quantize + packing/descriptor + both QBS commands + waits/CSR',
        anchors={'t0': 121568, 't1': 167185, 't2': 185049, 't3': 192518, 't4': 213010, 't5': 213045}),
    'akv_diag': dict(id='power_attention_akv', first=28000, last=35500, maximum=36000,
        queue='power_precheck_20261117_native_attention_02', release='akv', diagnostic=True,
        stages='Diagnostic only: first VRF data X at 28380.5 ns through first cache-control X at 35482.5 ns',
        anchors={'formal_pending_first': 15603, 'formal_pending_last': 57014,
                 'formal_pending_cycles': 41411, 'critical_X_ns': 35482.5}),
}


def limits(mode, first, last, cycles, wall, byte_limit, slot_seconds):
    b.require(mode == 'capture' and type(first) is int and type(last) is int and
        0 < first < last < cycles <= 5000000 and 2 <= last-first <= 120000,
        'Finite bounded successor window required')
    b.require(1 <= wall <= 14400 and 1 <= slot_seconds <= 14400, 'Finite wall/slot limits required')
    b.require(1024 <= byte_limit <= 64*1024**3, 'Successor VCD cap is 64 GiB')


b.validate_limits = limits
base_run = b.run_simulator
base_slot_lock = b.slot_lock


@contextmanager
def slot_lock():
    with base_slot_lock():
        modern = b.OUT / 'power_shared_slots_20261117_v4_01'
        if modern.exists():
            b.require(b.read(modern / 'policy.json')['paused'] is True and
                      all(b.read(p)['state'] == 'FINISHED' for p in (modern / 'leases').glob('*.json')),
                      'Modern shared scheduler is active/unreconciled; do not mix sealed protocols')
        yield


b.slot_lock = slot_lock


def run_simulator(out, plan):
    first_console = None
    def checked_clock():
        nonlocal first_console
        now = time.monotonic()
        console = out / 'run/console.log'
        if not plan['environment_diagnostic'] and console.exists():
            if first_console is None:
                first_console = now
            # The grace only ensures the base worker has entered its try/finally;
            # final validation still scans the entire immutable console.
            if now-first_console > 5:
                with console.open('rb') as stream:
                    stream.seek(max(0, console.stat().st_size-65536))
                    tail = stream.read().decode(errors='replace')
                b.require(not CRITICAL.search(tail), 'Critical mapped memory X; stopping owned formal capture')
        return now
    return base_run(out, plan, clock=checked_clock)


def final_check(out, plan, binding, run):
    if plan['environment_diagnostic']:
        result = g.final_check(out, plan, binding, run)
        result.update(state='AKV_X_DIAGNOSTIC_COMPLETE_NOT_POWER',
            init_evidence=e.init_evidence(out, IMAGE), representative_power_window=False,
            known_critical_X=True, formal_AKV_admission=False)
        return result
    b.require(plan['last_cycle']-plan['first_cycle'] >= 20000, 'Formal minimum 20000 cycles not met')
    result = e.final_check(out, plan, binding, run)
    result.update(window_policy='FIRST_COMPLETE_FIRMWARE_TIMED_CALL_GE_20000',
        minimum_cycles=20000, captured_cycles=plan['last_cycle']-plan['first_cycle'],
        window_selection=plan['window_selection'], UART_or_idle_padding=False,
        equal_work_across_different_shapes_claimed=False, paired_baseline_same_semantic_scope_required=True,
        scope='Complete-window activity receipt only; verify mapped workload phases and SAIF X/coverage before power acceptance')
    return result


def prepare(args, out):
    c = CASES[args.case]
    diagnostic = c.get('diagnostic', False)
    span = c['last']-c['first']
    b.require(diagnostic or span >= 20000, 'Short windows are not formal measurements')
    validation = b.read(IMAGE / 'environment-validation.json')
    b.require(validation['state'] == 'RESET_ONLY_VRF_INIT_DIAGNOSTICS_PASS_NOT_TASK_PASS' and
              validation['seeds'] == [0, 1], 'Actual opposite-seed environment validation required')
    if c['release'] == 'q8':
        release = b.OUT / 'power_gate_build_20261117_all_on_01/initial-release.json'
    else:
        release = b.OUT / ('power_native_release_20261117_activity_03/%s-release.json' % c['release'])
    config = argparse.Namespace(output=out, image=IMAGE, release=release, release_sha256=b.sha(release),
        case=c['id'], mode='capture', first_cycle=c['first'], last_cycle=c['last'],
        max_cycles=c['maximum'], wall_seconds=14400, slot_seconds=14400, max_vcd_bytes=48*1024**3)
    b.prepare(config)
    plan = b.read(out / 'plan.json')
    plan['command'].append('+GATE_VRF_INIT_SEED=0')
    plan.update(schema='native-long-window-capture-v3', init_seed=0, environment_diagnostic=diagnostic,
        minimum_formal_cycles=20000, max_log_bytes=32*1024**2,
        window_selection=dict(c, metric='DIAGNOSTIC_NOT_POWER' if diagnostic else 'FIRST_COMPLETE_TIMED_CALL_AVERAGE_POWER',
            gate_phase_verified=False, no_UART_padding=True, estimate_VCD_GiB=span*0.26/1024))
    b.save(out / 'plan.json', plan)
    pins = b.read(out / 'source-pins.json')
    for name in ('gate_long_window_v3.py', 'test_gate_long_window_v3.py', 'gate_vrf_env_v2.py',
                 'gate_activity_v3.py', 'test_gate_activity_v3.py', 'gate_native_v2.py', 'audit_gate_capture_eof.py'):
        source, dest = HERE / name, out / 'inputs' / name
        shutil.copyfile(source, dest)
        pins[str(source)] = b.sha(source)
        pins[str(dest)] = b.sha(dest)
    work = b.OUT / c['queue'] / 'runs' / c['id']
    for path in (out / 'plan.json', work / 'commit.csv', work / 'run.vcs.log',
                 IMAGE / 'environment-validation.json', IMAGE / 'source/power_vrf_init.sv'):
        pins[str(path)] = b.sha(path)
    b.save(out / 'source-pins.json', pins)


def bind(out):
    b.bind_image(out)
    ready = b.read(out / 'ready-command.json')
    for key in ('service', 'worker'):
        ready[key] = [str(out / 'inputs/gate_long_window_v3.py') if v == str(out / 'inputs/gate_run.py')
                      else v for v in ready[key]]
    ready['shell'] = b.shlex.join(ready['service'])
    b.save(out / 'ready-command.json', ready)


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'bind-image', 'execute'))
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--binding-sha256')
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args()
    out = b.scoped_output(args.output)
    if args.action == 'execute':
        b.require(Path(__file__).resolve() == out / 'inputs/gate_long_window_v3.py', 'Frozen own worker required')
        b.final_check, b.run_simulator = final_check, run_simulator
        return b.execute(out, args.plan_sha256, args.binding_sha256, args.authorize_run)
    b.require(not args.authorize_run, 'Authorization only for execute')
    if args.action == 'prepare':
        b.require(args.case, 'Explicit case required')
        prepare(args, out)
    else:
        bind(out)
    print(json.dumps(dict(action=args.action, output=str(out), launched=False)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
