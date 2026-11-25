#!/usr/bin/env python3
"""Reuse pinned exact control scan; verify native %t/100fs EOF without rescaling.

Old failures stay unchanged. No RTL/GLS, no gate changes, no power from projection.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sealed_type_successor', HERE / 'audit_m1_port_v2.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)
v1, b, w, r = v2.v1, v2.b, v2.w, v2.r
PREVIOUS = v2.DEFAULT
DEFAULT = w.OUT / 'power_gls_20261117_rvv_m1_port_audit_03'
UNIT = 'power-audit-20261117-rvv-m1-port-03.service'


def check_eof(report, text, plan):
    begin, end = b.g.capture_markers(text, plan['first_cycle'], plan['last_cycle'])
    cycles = plan['last_cycle'] - plan['first_cycle']
    b.require(cycles >= 20000 and report['complete_initial_state'] is True, 'Formal window/snapshot required')
    b.require((report['first_tick'], report['last_tick']) == (begin, end),
              'Raw %t marker ticks differ from actual VCD timestamps')
    b.require(report['duration_ticks'] == end - begin and
              report['duration_ticks'] * 100 == cycles * 1000000,
              'Independent 100fs VCD / 1ns clock physical duration mismatch')
    b.require(re.search(r'\$finish at simulation time\s+' + str(end) + r'\s*$', text, re.M) and
              'V C S   S i m u l a t i o n   R e p o r t' in text and 'Core Test' not in text,
              'Missing selected-window native EOF or unexpected task completion')
    return dict(marker_first_raw_tick=begin, marker_last_raw_tick=end, timescale_fs=100,
        cycle_period_fs=1000000, cycles=cycles, duration_fs=report['duration_ticks']*100,
        semantics='%0t $realtime and native VCD use the same global 100fs precision ticks',
        timestamp_multiplier=1, no_waveform_rewrite=True)


def prepare(out):
    b.require(out == DEFAULT and not out.exists(), 'Fresh independent EOF successor required')
    failed = b.read(PREVIOUS / 'result.json')
    b.require(failed['state'] == 'FAIL' and failed['error'] == "ValueError('Original EOF/window mismatch')",
              'Only the proven EOF unit-conversion failure is in scope')
    b.verify(b.read(PREVIOUS / 'audit-source-pins.json'))
    b.require(b.sha(HERE / 'audit_m1_port_v2.py') == b.sha(PREVIOUS / 'inputs/audit_m1_port_v2.py'), 'Sealed upstream scan source drift')
    cached = b.read(PREVIOUS / 'raw-scan-report.json')
    raw = (PREVIOUS / 'cases/m1/run/window.vcd').resolve()
    projection = Path(cached['projection']['path'])
    b.verify({str(raw): cached['vcd_sha256'], str(projection): cached['projection']['sha256']})
    out.mkdir()
    shutil.copytree(PREVIOUS / 'inputs', out / 'inputs')
    for name in ('audit_m1_port_v3.py', 'test_audit_m1_port_v3.py'):
        shutil.copyfile(HERE / name, out / 'inputs' / name)
    shutil.copyfile(PREVIOUS / 'image-binding.json', out / 'image-binding.json')
    case = out / 'cases/m1'
    shutil.copytree(PREVIOUS / 'cases/m1/inputs', case / 'inputs')
    (case / 'run').mkdir()
    for name in ('window.vcd', 'run.vcs.log', 'console.log'):
        (case / 'run' / name).symlink_to((PREVIOUS / 'cases/m1/run' / name).resolve())
    shutil.copyfile(PREVIOUS / 'cases/m1/plan.json', case / 'plan.json')
    with (out / 'host-tests.log').open('x') as log:
        subprocess.run([sys.executable, '-B', str(out / 'inputs/test_audit_m1_port_v3.py'), '-v'],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    pins = b.read(PREVIOUS / 'audit-source-pins.json')
    pins.update({str(p): b.sha(p) for p in out.rglob('*') if p.is_file() and not p.is_symlink()})
    for path in (PREVIOUS / 'result.json', PREVIOUS / 'raw-scan-report.json', PREVIOUS / 'representation-proof.json'):
        pins[str(path)] = b.sha(path)
    pins.update({str(raw): cached['vcd_sha256'], str(projection): cached['projection']['sha256']})
    pins.update(cached['projection']['tools'])
    sv = Path(b.read(case / 'plan.json')['image']) / 'source/power_capture.sv'
    pins[str(sv)] = b.sha(sv)
    b.save(out / 'audit-source-pins.json', pins, True)
    service = ['systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec', '--property=KillMode=control-group',
        '--property=RuntimeMaxSec=7200', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), '/usr/bin/python3', '-B',
        str(out / 'inputs/audit_m1_port_v3.py'), 'execute', '--output', str(out)]
    b.save(out / 'ready-command.json', dict(service=service), True)


def execute(out):
    b.require(out == DEFAULT and Path(__file__).resolve() == out / 'inputs/audit_m1_port_v3.py', 'Frozen EOF successor required')
    owner = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', 'MainPID', '--value'], text=True).strip()
    b.require(owner == str(os.getpid()) and UNIT in Path('/proc/self/cgroup').read_text(), 'Direct service owner required')
    pins = b.read(out / 'audit-source-pins.json')
    b.verify(pins)
    b.save(out / 'attempt.json', dict(pid=os.getpid(), started_ns=time.time_ns(), simulations_launched=0), True)
    case = out / 'cases/m1'
    try:
        b.save(out / 'status.json', dict(state='VERIFYING_PINNED_SCAN_AND_NATIVE_TIMEBASE_NO_VCS'))
        dc = w.load(out / 'inputs/dc_power.py', 'unchanged_control_policy_v3')
        cached = b.read(PREVIOUS / 'raw-scan-report.json')
        fresh_live = v1.scan(Path(cached['projection']['path']), dc)
        fresh = json.loads(json.dumps(fresh_live))
        b.require(fresh['vcd_sha256'] == cached['projection']['sha256'], 'Projected evidence drift')
        for field in fresh:
            if field not in ('vcd_sha256', 'raw_bytes'):
                b.require(fresh[field] == cached[field], 'Pinned raw scan replay disagreement: ' + field)
        report = dict(cached)
        old = b.read(v1.PARENT / 'cases/m1/activity-audit.json')
        representation = v2.compare_representation(fresh_live, report, old)
        b.save(out / 'representation-proof.json', representation, True)
        plan = b.read(case / 'plan.json')
        alignment = v1.validate(report, old, plan, r.pairing(Path(plan['window_basis']['trace'])))
        b.save(out / 'alignment-proof.json', alignment, True)
        report['cycles'] = plan['last_cycle'] - plan['first_cycle']
        report.update(dc.activity_policy(report, 'rvv', 'm1', '0x800022f4'))
        b.require(report['state'] == 'ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS', 'Unchanged control/phase policy rejected')
        text = (case / 'run/run.vcs.log').read_text()
        eof = check_eof(report, text, plan)
        b.save(out / 'timebase-proof.json', eof, True)
        b.require(not w.d.log_evidence(case / 'run/run.vcs.log')['counts'], 'Actual enabled SRAM X warning')
        b.save(case / 'activity-audit.json', report, True)
        for path in (out / 'representation-proof.json', out / 'alignment-proof.json', out / 'timebase-proof.json',
                     case / 'activity-audit.json', case / 'run/run.vcs.log'):
            pins[str(path)] = b.sha(path)
        b.save(out / 'source-pins.json', pins, True)
        binding = b.read(out / 'image-binding.json')
        result = dict(state='CAPTURE_COMPLETE_NOT_TASK_PASS', kind='m1', offline_scoped_successor=True,
            original_failure=str(v1.PARENT / 'result.json'), previous_audit_failures=[str(v2.PREVIOUS / 'result.json'), str(PREVIOUS / 'result.json')],
            original_FAILs_unchanged=True, simulations_launched=0,
            vcd=str(case / 'run/window.vcd'), log=str(case / 'run/run.vcs.log'),
            vcd_sha256=report['vcd_sha256'], log_sha256=b.sha(case / 'run/run.vcs.log'),
            elf_sha256=plan['elf_sha256'], simv_sha256=binding['simv_sha256'],
            first_cycle=plan['first_cycle'], last_cycle=plan['last_cycle'], clock_period_ns=1,
            phase_contract=plan['phase_contract'], strict_original_state='FAIL',
            full_gate_task_pass=False, gate_numeric_checked=False, paired_ratio_publishable=False, power_acceptance=False,
            vcd_evidence=dict(first_tick=report['first_tick'], last_tick=report['last_tick'], timescale_fs=100,
                complete_initial_state=True, eof_at_selected_end=True), projection_used_for_power=False)
        b.save(case / 'result.json', result, True)
        w.POWER = w.OUT / 'power_dc_20261117_rvv_m1_port_audit_03'
        w.power_worker(out, 'm1')
        final = dict(state='OFFLINE_ACTIVITY_ELIGIBLE_PORT0_COMPANION_NOT_GLS_PASS',
            original_FAILs_unchanged=True, simulations_launched=0, alignment=alignment, timebase=eof,
            exact_ordered_PC_counts_equal=True, control_statistics_unchanged=True, power_acceptance=False,
            power_uses_original_full_VCD=True)
    except BaseException as exc:
        final = dict(state='FAIL', error=repr(exc), original_FAILs_unchanged=True, simulations_launched=0)
    b.save(out / 'result.json', final, True)
    b.save(out / 'status.json', dict(state=final['state']))
    return int(final['state'] == 'FAIL')


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'execute'))
    p.add_argument('--output', type=Path, default=DEFAULT)
    a = p.parse_args()
    if a.action == 'prepare':
        prepare(a.output)
        return 0
    return execute(a.output)


if __name__ == '__main__':
    raise SystemExit(main())
