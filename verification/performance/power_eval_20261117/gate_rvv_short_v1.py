#!/usr/bin/env python3
"""Short real-compute RVV captures; same netlist, checked startup, then SAIF/DC.

Never waits for firmware completion or converts a rejected/X-control window.
"""
import argparse
from collections import Counter
import csv
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


e = load(HERE / 'gate_rvv_env_v1.py', 'short_scoped_startup')
b, d, s = e.b, e.d, e.s
OUT = b.OUT
PREPARED = e.DEFAULT
DEFAULT = OUT / 'power_gls_20261117_baseline_rvv_short_01'
DCROOT = OUT / 'power_dc_20261117_baseline_rvv_short_01'


def short_window(trace, entry):
    started = first = None
    retires = []
    with Path(trace).open() as stream:
        for row in csv.DictReader(stream):
            cycle = int(row['cycle'])
            if started is None and row['event'] == 'retire' and int(row['pc'], 16) == entry:
                started = cycle
            if started is None:
                continue
            if first is None and row['event'] == 'uop_alloc':
                first = cycle + 1
            if first is not None and cycle > first + 1024:
                break
            if first is not None and row['event'] == 'retire' and int(row['insn'], 16) & 127 == 0x57:
                retires.append(hex(int(row['pc'], 16)))
    b.require(started is not None and first is not None and retires, 'Actual first compute/vector phase missing')
    anchor = Counter(retires).most_common(1)[0][0]
    return dict(first_cycle=first, last_cycle=first + 1024, cycles=1024, anchor_pc=anchor,
                kernel_entry_cycle=started, kernel_entry_pc=hex(entry), trace=str(trace), trace_sha256=b.sha(trace),
                basis='First 1024-cycle real vector-compute prefix in the original kernel; not a full command/task',
                gate_phase_checked=False, whole_task_energy=False)


def prepare(out):
    b.require(out == DEFAULT and not out.exists(), 'Fresh short successor required')
    b.verify(b.read(PREPARED / 'source-pins.json'))
    out.mkdir()
    for folder in ('inputs', 'image', 'cases'):
        shutil.copytree(PREPARED / folder, out / folder)
    for name in ('gate_rvv_short_v1.py', 'test_gate_rvv_short_v1.py', 'gate_rvv_short_power_v1.py', 'dc_power.py', 'convert.py'):
        shutil.copyfile(HERE / name, out / 'inputs' / name)
    plan = b.read(PREPARED / 'plan.json')
    image = out / 'image'
    plan['image'] = str(image)
    plan['compile_command'] = [x.replace(str(PREPARED), str(out)) for x in plan['compile_command']]
    (image / 'sources.f').write_text((image / 'sources.f').read_text().replace(str(PREPARED), str(out)))
    (image / 'inputs').mkdir()
    shutil.copyfile(e.PARENT / 'inputs/ara_soc_dc.ddc', image / 'inputs/ara_soc_dc.ddc')
    shutil.copyfile(e.PARENT / 'gate-receipt.json', image / 'gate-receipt.json')
    receipt = b.read(image / 'gate-receipt.json')
    receipt.update(schema='same-baseline-netlist-scoped-startup-environment-v1',
        parent_receipt=str(e.PARENT / 'gate-receipt.json'), parent_receipt_sha256=b.sha(e.PARENT / 'gate-receipt.json'),
        environment_delta='Reset-only 512 VRF data words; opposite seeds required before compute capture',
        controls_initialized=False, runtime_force=False, full_gate_task_pass=False)
    b.save(image / 'gate-receipt.json', receipt)
    plan.update(schema='rvv-first-compute-short-window-v1', long_predecessor_cancelled=True,
                predecessor=str(PREPARED), no_full_firmware_wait=True, no_UART_completion_wait=True)
    windows = {}
    for entry in plan['cases']:
        key = entry['key']
        case = out / 'cases' / key
        entry['path'] = str(case)
        p = b.read(case / 'plan.json')
        p['command'] = [x.replace(str(PREPARED), str(out)) for x in p['command']]
        p.update(image=str(image), cwd=str(case / 'run'), elf=str(case / 'inputs/program.elf'))
        if not p['diagnostic_only']:
            audit = b.read(p['rtl_admission'])
            kernel = dict(m1=0x80001bfe, m4=0x80001fdc, attention=0x80000100)[key]
            w = short_window(Path(audit['run']) / 'commit.csv', kernel)
            windows[key] = w
            p.update(first_cycle=w['first_cycle'], last_cycle=w['last_cycle'], max_cycles=w['last_cycle'] + 64,
                     window_basis=w)
            p['command'] = ['+GATE_ROI_FIRST=' + str(p['first_cycle']) if x.startswith('+GATE_ROI_FIRST=') else
                            '+GATE_ROI_LAST=' + str(p['last_cycle']) if x.startswith('+GATE_ROI_LAST=') else
                            '+GATE_MAX_CYCLES=' + str(p['max_cycles']) if x.startswith('+GATE_MAX_CYCLES=') else x
                            for x in p['command']]
        b.save(case / 'plan.json', p)
    b.save(out / 'plan.json', plan, True)
    b.save(out / 'selected-windows.json', windows, True)
    with (out / 'host-tests.log').open('x') as log:
        subprocess.run([sys.executable, '-B', str(out / 'inputs/test_gate_rvv_short_v1.py'), '-v'],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    pins = {str(p): b.sha(p) for p in out.rglob('*') if p.is_file()}
    pins.update({str(p): b.sha(p) for p in (PREPARED / 'source-pins.json', d.DEFAULT / 'source-pins.json')})
    for w in windows.values():
        pins[w['trace']] = w['trace_sha256']
    # Reuse the already compiled baseline leaf discriminator; do not rebuild it.
    probe = PREPARED / 'mapped-probe'
    for name in ('simv', 'probe.sv', 'mapped_alu.v', 'compile.log'):
        pins[str(probe / name)] = b.sha(probe / name)
    for p in (probe / 'simv.daidir').rglob('*'):
        if p.is_file():
            pins[str(p)] = b.sha(p)
    b.save(out / 'source-pins.json', pins, True)
    unit = out.name.replace('_', '-') + '.service'
    worker = ['/usr/bin/python3', '-B', str(out / 'inputs/gate_rvv_short_v1.py'), 'execute', '--output', str(out),
              '--plan-sha256', b.sha(out / 'plan.json')]
    service = ['systemd-run', '--user', '--unit=' + unit, '--property=Type=exec', '--property=KillMode=control-group',
               '--property=RuntimeMaxSec=86400', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
               '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    b.save(out / 'ready-command.json', dict(service=service), True)


def reuse_probe(out, witness, env):
    previous = PREPARED / 'mapped-probe'
    text = (previous / 'probe.sv').read_text()
    b.require("a=64'h" + witness['a'][2:] in text, 'Compiled discriminator does not match actual captured A')
    net = (e.PARENT / 'source/ara_soc_dc.v').read_text()
    module = re.search(r'^module simd_alu_1_0_ara_soc\b.*?^endmodule\b', net, re.M | re.S)
    b.require(module and (previous / 'mapped_alu.v').read_text() == module[0] + '\n', 'Mapped leaf identity drift')
    work = out / 'mapped-probe'
    work.mkdir()
    deadline = time.monotonic() + 14400
    while True:
        with b.shared_launch_locks():
            cap = b.capacity(b.g.process_snapshot())
            if cap['launch_allowed'] and not s.q8_gls_units():
                with (work / 'run.log').open('x') as log:
                    proc = subprocess.Popen([str(previous / 'simv'), '-no_save'], cwd=work, env=env,
                                            stdout=log, stderr=subprocess.STDOUT)
                break
        b.require(time.monotonic() < deadline, 'Probe shared-slot wait expired')
        time.sleep(60)
    try:
        b.require(proc.wait(timeout=300) == 0, 'Mapped discriminator failed')
    finally:
        b.g.stop_process(proc)
    b.require('BASELINE_MAPPED_MERGE_X_PESSIMISM_PROVED concrete_B_vectors=1024' in
              (work / 'run.log').read_text(), 'Missing real mapped discriminator proof')
    return dict(witness=witness, binary=str(previous / 'simv'), binary_sha256=b.sha(previous / 'simv'),
                log=str(work / 'run.log'), log_sha256=b.sha(work / 'run.log'), concrete_B_vectors=1024)


def prepare_power(out, key):
    dc = load(out / 'inputs/dc_power.py', 'short_dc_prepare_' + key)
    pair = DCROOT / key
    role = pair / 'rvv'
    (role / 'inputs').mkdir(parents=True)
    (role / 'reports').mkdir()
    oldpair = OUT / 'power_dc_20261117_activity_follow_02' / ('akv' if key == 'attention' else key)
    libraries = dc.read(oldpair / 'pair-plan.json')['library_sha256']
    limitations = ['Relative short compute-window average power only; not full-task energy or GLS task PASS',
                   'Original strict numerical/protocol FAIL remains unchanged; separate RTL power eligibility',
                   'Same mapped baseline netlist, reset-only VRF data startup validated by opposite seeds',
                   'Control/phase activity independently checked; unknown idle SRAM reported, never forced',
                   'Native/RVV operation mixes and phase comparability are not claimed identical',
                   'Reconstructed historical baseline source byte identity remains UNPROVEN']
    # No synthetic paired result or ratio: native result is deliberately absent.
    dc.save(pair / 'pair-plan.json', dict(runs=dict(native=str(pair / 'native-not-collected'), rvv=str(role)),
        library_sha256=libraries, limitations=limitations))
    job = dc.read(oldpair / 'rvv/chain-plan.json')
    unit = 'power-dc-20261117-baseline-rvv-short-' + key + '-01.service'
    job.update(capture_run=str(out / 'cases' / key), pair=str(pair), service_unit=unit,
        conversion_output=str(OUT / ('power_saif_20261117_baseline_rvv_short_' + key + '_01')),
        library_sha256=libraries, limitations=limitations, wait_seconds=86400)
    dc.save(role / 'chain-plan.json', job)
    pins = {str(role / 'chain-plan.json'): dc.sha(role / 'chain-plan.json'),
            str(pair / 'pair-plan.json'): dc.sha(pair / 'pair-plan.json')}
    for name in ('dc_power.py', 'convert.py', 'gate_rvv_short_power_v1.py'):
        dest = role / 'inputs' / name
        shutil.copyfile(out / 'inputs' / name, dest)
        pins[str(dest)] = dc.sha(dest)
    dc.save(role / 'chain-pins.json', pins)
    service = ['systemd-run', '--user', '--unit=' + unit, '--property=Type=exec', '--property=KillMode=control-group',
        '--property=RuntimeMaxSec=86400', '--property=StandardOutput=append:' + str(role / 'service.stdout.log'),
        '--property=StandardError=append:' + str(role / 'service.stderr.log'), '/usr/bin/python3', '-B',
        str(role / 'inputs/gate_rvv_short_power_v1.py'), '--output', str(role), '--authorize-dc']
    dc.save(role / 'ready-command.json', dict(service=service))
    subprocess.run(service, check=True, timeout=30)


def execute(out, plan_sha):
    b.require(out == DEFAULT and Path(__file__).resolve() == out / 'inputs/gate_rvv_short_v1.py', 'Frozen short worker required')
    unit = out.name.replace('_', '-') + '.service'
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    b.require(owner == str(os.getpid()) and unit in Path('/proc/self/cgroup').read_text(), 'Direct service owner required')
    b.require(b.sha(out / 'plan.json') == plan_sha, 'Short plan drift')
    pins, plan = b.read(out / 'source-pins.json'), b.read(out / 'plan.json')
    b.verify(pins)
    b.save(out / 'attempt.json', dict(pid=os.getpid(), started_ns=time.time_ns()), True)
    def interrupted(signum, frame):
        raise InterruptedError(signum)
    signal.signal(signal.SIGTERM, interrupted)
    results = []
    try:
        b.q8_units = s.q8_gls_units
        original = b.read(d.DEFAULT / 'result.json')
        b.verify(b.read(d.DEFAULT / 'source-pins.json'))
        b.verify({original['capture']['vcd']: original['capture']['vcd_sha256'],
                  str(d.DEFAULT / 'cases/m1/run/run.vcs.log'): original['capture']['log_sha256']})
        env = b.read(out / 'cases/diag0/inputs/rtl-plan.json')['environment']
        proof = reuse_probe(out, e.firstx_witness(original), env)
        b.save(out / 'root-cause.json', dict(state='MAPPED_UNUSED_B_X_PESSIMISM_PROVED', mapped_proof=proof,
            original_reductions=original['wave']['reductions'], warnings=original['warnings'],
            original_diagnostic=str(d.DEFAULT / 'result.json'), original_sha256=b.sha(d.DEFAULT / 'result.json'),
            startup_candidate_still_requires_opposite_seeds=True), True)
        image = Path(plan['image'])
        b.save(out / 'status.json', dict(state='COMPILING_UNCHANGED_NETLIST_STARTUP_ENVIRONMENT'))
        with (image / 'logs/compile-console.log').open('x') as log:
            subprocess.run(plan['compile_command'], cwd=image / 'sim', env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=7200)
        b.verify(pins)
        b.require(b.sha(image / 'source/ara_soc_dc.v') == e.NET_SHA, 'Netlist drift')
        images = {str(p): b.sha(p) for p in [image / 'sim/simv',
                  *(p for p in (image / 'sim/simv.daidir').rglob('*') if p.is_file())]}
        b.save(image / 'image-pins.json', images, True)
        build = dict(image_pins=images, baseline_context=b.read(e.PARENT / 'build.json')['baseline_context'],
                     state='SAME_BASELINE_NETLIST_RESET_ONLY_VRF_STARTUP_BUILT', full_task_validated=False)
        b.save(image / 'build.json', build, True)
        gpins = {str(p): b.sha(p) for p in image.rglob('*') if p.is_file() and 'sim' not in p.relative_to(image).parts and 'logs' not in p.relative_to(image).parts}
        b.save(image / 'source-pins.json', gpins, True)
        binding = b.read(e.OLD / 'image-binding.json')
        binding.update(image_pins=images, simv_sha256=images[str(image / 'sim/simv')],
            gate_source_pins_sha256=b.sha(image / 'source-pins.json'), gate_build_sha256=b.sha(image / 'build.json'),
            initialization='Reset-only VRF data, 512 words; no controls, no runtime forcing')
        b.save(out / 'image-binding.json', binding, True)
        dc = load(out / 'inputs/dc_power.py', 'short_control_phase_audit')
        for entry in plan['cases']:
            case = Path(entry['path'])
            p = b.read(case / 'plan.json')
            run = b.run_capture(out, case, p, dict(pins, **images))
            result = b.finish_capture(case, p, binding, run)
            wave = d.inspect(case / 'run/window.vcd')
            warnings = d.log_evidence(case / 'run/run.vcs.log')
            e.clean_quality(wave, warnings)
            marks = re.findall(r'^GATE_RVV_VRF_INIT seed=([01]) words=512 reset=0 force=0$',
                               (case / 'run/run.vcs.log').read_text(), re.M)
            b.require(marks == [str(p['init_seed'])], 'Actual startup evidence missing')
            if p['diagnostic_only']:
                b.require(wave['reductions'] == e.EXPECTED, 'Opposite seed exact original reductions mismatch')
                result['state'] = 'EXACT_REDUCTION_DIAGNOSTIC_PASS_NOT_TASK_PASS'
            else:
                ev = result['vcd_evidence']
                report = dc.scan_activity_vcd(case / 'run/window.vcd', 1024, ev['first_tick'], ev['last_tick'], p['window_basis']['anchor_pc'])
                report.update(dc.activity_policy(report, 'rvv', 'akv' if entry['key'] == 'attention' else entry['key'], p['window_basis']['anchor_pc']))
                b.save(case / 'activity-audit.json', report, True)
                b.require(report['state'] == 'ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS', 'Control/compute-phase audit rejected window: ' + str(report['reasons']))
            result.update(wave_quality=wave, log=str(case / 'run/run.vcs.log'),
                first_cycle=p['first_cycle'], last_cycle=p['last_cycle'], clock_period_ns=1,
                initialization='Reset-only VRF data startup; opposite seeds checked before compute captures',
                original_strict_FAIL_preserved=True, power_acceptance=False)
            b.verify(pins)
            b.verify(images)
            b.save(case / 'result.json', result, True)
            results.append(dict(key=entry['key'], state=result['state']))
            if entry['key'] == 'diag1':
                b.save(image / 'environment-validation.json', dict(state='OPPOSITE_VRF_SEEDS_EXACT_REDUCTIONS_PASS',
                    seeds=[0, 1], reductions=e.EXPECTED, runtime_force=False, controls_initialized=False,
                    full_task_pass=False, power_acceptance=False), True)
            if not p['diagnostic_only']:
                prepare_power(out, entry['key'])
        result = dict(state='SHORT_CAPTURE_CHAIN_COMPLETE_POWER_WORKERS_LAUNCHED', cases=results,
                      full_task_pass=False, power_acceptance=False)
    except BaseException as exc:
        result = dict(state='FAIL_STOP_NO_RETRY', error=repr(exc), completed_cases=results,
                      power_acceptance=False, original_strict_FAILs_preserved=True)
    b.save(out / 'result.json', result, True)
    b.save(out / 'status.json', dict(state=result['state']))
    return int(result['state'] == 'FAIL_STOP_NO_RETRY')


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'execute'))
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--plan-sha256')
    a = p.parse_args()
    if a.action == 'prepare':
        prepare(a.output)
        return 0
    return execute(a.output, a.plan_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
