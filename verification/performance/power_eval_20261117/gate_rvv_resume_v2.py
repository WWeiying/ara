#!/usr/bin/env python3
"""Resume only unexecuted wide cases; preserve the rejected M1 and all gates."""
import argparse
import csv
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('resume_frozen_wide', HERE / 'gate_rvv_wide_v1.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
b, d, s = w.b, w.d, w.s
PARENT = w.DEFAULT
DEFAULT = w.OUT / 'power_gls_20261117_baseline_rvv_resume_01'
POWER = w.OUT / 'power_dc_20261117_baseline_rvv_resume_01'
CORE = w.OUT / 'power_rtl_20261117_baseline_01/source/hardware/deps/cva6/core/commit_stage.sv'


def pairing(trace):
    pairs, previous = [], None
    with Path(trace).open() as stream:
        for row in csv.DictReader(stream):
            if row['event'] != 'retire':
                continue
            if int(row['pc'], 16) == 0x800022f8:
                b.require(int(row['port']) == 1 and previous is not None and
                          previous['cycle'] == row['cycle'] and int(previous['port']) == 0 and
                          int(previous['pc'], 16) == 0x800022f4, 'M1 companion is not same-cycle slot0')
                pairs.append(dict(cycle=int(row['cycle']), slot0='0x800022f4', slot1='0x800022f8'))
            previous = row
    b.require(len(pairs) >= 5, 'Repeated exact pairing required')
    return pairs


def unit(key):
    return 'power-gls-20261117-baseline-rvv-resume-' + key + '-01.service'


def prepare(out):
    b.require(out == DEFAULT and not out.exists() and not POWER.exists(), 'Fresh resume outputs required')
    b.verify(b.read(PARENT / 'source-pins.json'))
    b.require(b.read(PARENT / 'result.json')['state'] == 'FAIL_STOP_NO_RETRY', 'Preserve terminal parent failure')
    source = CORE.read_text()
    b.require('assign pc_o = commit_instr_i[0].pc;' in source, 'Port0-only PC source contract changed')
    p = b.read(PARENT / 'cases/m1/plan.json')
    pairs = pairing(Path(p['window_basis']['trace']))
    old = b.read(PARENT / 'cases/m1/activity-audit.json')
    b.require(old['reasons'] == ['RTL loop anchor not observed retiring in mapped gate window'] and
              all(v['unknown_ticks'] == 0 for v in old['signals'].values()) and
              old['pc_unknown_when_committing'] == old['active_payload_unknown_samples'] == 0,
              'Not the scoped missing-port1-anchor failure; do not resume blindly')
    out.mkdir()
    shutil.copytree(PARENT / 'inputs', out / 'inputs')
    for name in ('gate_rvv_resume_v2.py', 'test_gate_rvv_resume_v2.py'):
        shutil.copyfile(HERE / name, out / 'inputs' / name)
    shutil.copyfile(PARENT / 'image-binding.json', out / 'image-binding.json')
    proof = dict(state='STATIC_PORT_SELECTOR_MISMATCH_PROVED_NOT_GLS_PASS',
        original_failure=str(PARENT / 'result.json'), original_audit=str(PARENT / 'cases/m1/activity-audit.json'),
        pc_source=str(CORE), pc_source_sha256=b.sha(CORE), expression='pc_o = commit_instr_i[0].pc',
        original_anchor='0x800022f8', original_anchor_port=1, same_cycle_companion='0x800022f4',
        pairs=pairs, simulation_rerun_required_for_m1=False, offline_wave_proof_still_required=True,
        original_FAIL_unchanged=True)
    b.save(out / 'port-selector-diagnosis.json', proof, True)
    cases = []
    for key in ('m4', 'attention'):
        oldcase, case = PARENT / 'cases' / key, out / 'cases' / key
        b.require(not (oldcase / 'dispatch.json').exists(), 'Do not rerun an already dispatched case')
        shutil.copytree(oldcase / 'inputs', case / 'inputs')
        (case / 'run').mkdir()
        plan = b.read(oldcase / 'plan.json')
        plan['command'] = [x.replace(str(oldcase), str(case)) for x in plan['command']]
        plan.update(elf=str(case / 'inputs/program.elf'), cwd=str(case / 'run'))
        b.require(plan['last_cycle'] - plan['first_cycle'] >= 20000, 'Preserve wide duration')
        trace = Path(plan['window_basis']['trace'])
        selected = set(plan['window_basis']['anchor_cycles'])
        found = []
        with trace.open() as stream:
            for row in csv.DictReader(stream):
                if row['event'] == 'retire' and int(row['cycle']) in selected and int(row['pc'], 16) == int(plan['window_basis']['anchor_pc'], 16):
                    b.require(int(row['port']) == 0, 'Pending case has an unobservable port1 anchor')
                    found.append(int(row['cycle']))
        b.require(set(found) == selected, 'Missing port0 window boundaries')
        b.save(case / 'plan.json', plan, True)
        cases.append(dict(key=key, path=str(case)))
    b.save(out / 'plan.json', dict(schema='unexecuted-rvv-wide-resume-v2', cases=cases,
        own_parallelism=2, shared_global_simv_limit=4, image_reused=True, no_compile=True,
        old_FAIL_unchanged=True, original_checkers_unchanged=True, automatic_retry=False), True)
    with (out / 'host-tests.log').open('x') as log:
        subprocess.run([sys.executable, '-B', str(out / 'inputs/test_gate_rvv_resume_v2.py'), '-v'],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    pins = b.read(PARENT / 'source-pins.json')
    pins.update({str(p): b.sha(p) for p in out.rglob('*') if p.is_file()})
    for path in (PARENT / 'source-pins.json', PARENT / 'result.json', PARENT / 'cases/m1/activity-audit.json', CORE):
        pins[str(path)] = b.sha(path)
    b.save(out / 'source-pins.json', pins, True)
    services = []
    for entry in cases:
        key, case = entry['key'], Path(entry['path'])
        worker = ['/usr/bin/python3', '-B', str(out / 'inputs/gate_rvv_resume_v2.py'), 'execute',
                  '--output', str(out), '--case', key, '--plan-sha256', b.sha(out / 'plan.json')]
        services.append(['systemd-run', '--user', '--unit=' + unit(key), '--property=Type=exec',
            '--property=KillMode=control-group', '--property=RuntimeMaxSec=86400',
            '--property=StandardOutput=append:' + str(case / 'service.stdout.log'),
            '--property=StandardError=append:' + str(case / 'service.stderr.log'), *worker])
    b.save(out / 'ready-command.json', dict(services=services), True)


def execute(out, key, plan_sha):
    b.require(out == DEFAULT and Path(__file__).resolve() == out / 'inputs/gate_rvv_resume_v2.py', 'Frozen resume worker')
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit(key), '-p', 'MainPID', '--value'], text=True).strip()
    b.require(owner == str(os.getpid()) and unit(key) in Path('/proc/self/cgroup').read_text(), 'Direct service owner required')
    b.require(b.sha(out / 'plan.json') == plan_sha, 'Resume plan drift')
    entry = next(x for x in b.read(out / 'plan.json')['cases'] if x['key'] == key)
    case = Path(entry['path'])
    pins = b.read(out / 'source-pins.json')
    b.verify(pins)
    b.save(case / 'attempt.json', dict(pid=os.getpid(), started_ns=time.time_ns()), True)
    def interrupted(signum, frame):
        raise InterruptedError(signum)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        b.q8_units = s.q8_gls_units
        w.disk_check(shutil.disk_usage(out).free, 2)
        plan = b.read(case / 'plan.json')
        run = b.run_capture(case, case, plan, pins)
        result = b.finish_capture(case, plan, b.read(out / 'image-binding.json'), run)
        warnings = d.log_evidence(case / 'run/run.vcs.log')
        b.require(not warnings['counts'], 'Enabled SRAM X remains')
        dc = w.load(out / 'inputs/dc_power.py', 'resume_phase_checker_' + key)
        ev = result['vcd_evidence']
        report = dc.scan_activity_vcd(case / 'run/window.vcd', plan['last_cycle'] - plan['first_cycle'],
            ev['first_tick'], ev['last_tick'], plan['window_basis']['anchor_pc'])
        report.update(dc.activity_policy(report, 'rvv', 'akv' if key == 'attention' else key, plan['window_basis']['anchor_pc']))
        b.save(case / 'activity-audit.json', report, True)
        b.require(report['state'] == 'ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS', 'Control/phase rejected: ' + str(report['reasons']))
        result.update(log=str(case / 'run/run.vcs.log'), first_cycle=plan['first_cycle'], last_cycle=plan['last_cycle'],
            clock_period_ns=1, phase_contract=plan['phase_contract'], minimum_formal_cycles=20000,
            original_strict_FAIL_preserved=True, paired_ratio_publishable=False, power_acceptance=False)
        b.verify(pins)
        b.save(case / 'result.json', result, True)
        w.POWER = POWER
        w.power_worker(out, key)
        b.save(case / 'status.json', dict(state='WIDE_CAPTURE_COMPLETE_POWER_CHAIN_LAUNCHED'))
        return 0
    except BaseException as exc:
        if not (case / 'result.json').exists():
            b.save(case / 'result.json', dict(state='FAIL_STOP_NO_RETRY', error=repr(exc), power_acceptance=False), True)
        b.save(case / 'status.json', dict(state='FAIL_STOP_NO_RETRY', error=repr(exc)))
        return 1


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'execute'))
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--case', choices=('m4', 'attention'))
    p.add_argument('--plan-sha256')
    a = p.parse_args()
    if a.action == 'prepare':
        prepare(a.output)
        return 0
    return execute(a.output, a.case, a.plan_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
