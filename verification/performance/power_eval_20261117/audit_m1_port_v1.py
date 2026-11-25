#!/usr/bin/env python3
"""Independent offline port0-companion audit; never runs or relabels old GLS."""
import argparse
from collections import Counter, defaultdict
import hashlib
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
spec = importlib.util.spec_from_file_location('offline_port_diagnosis', HERE / 'gate_rvv_resume_v2.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
w, b = r.w, r.b
PARENT = r.PARENT
DEFAULT = w.OUT / 'power_gls_20261117_rvv_m1_port_audit_01'
UNIT = 'power-audit-20261117-rvv-m1-port-01.service'


def scan(path, dc):
    """Same settled-interval control statistics as sealed scanner, plus raw SHA/events."""
    h = hashlib.sha256()
    codes, widths, scopes, states, declared, initial_ids = {}, {}, [], {}, set(), set()
    dwell, edges = defaultdict(Counter), Counter()
    current = first = None
    snapshot = definitions = False
    initial_count = initial_unknown = retire = pc_unknown = 0
    pcs = Counter()
    anchor_ticks, mac_ticks, active = [], [], False
    first_scale, scale_lines = False, []
    deadline = time.monotonic() + 2400

    def known(value):
        return bool(value) and set(value) <= set(b'01')

    def flush(tick):
        nonlocal retire, pc_unknown, active
        if current is None or tick == current:
            return
        for name, value in states.items():
            dwell[name][value.decode()] += tick - current
        ack, pc = states.get('ack'), states.get('pc')
        hit = False
        if known(ack) and int(ack, 2) & 1:
            if known(pc):
                retire += 1
                number = int(pc, 2)
                pcs[hex(number)] += 1
                hit = number == 0x800022f4
                if number in (0x80001e3e, 0x800022ec):
                    if not mac_ticks or mac_ticks[-1][0] != number or current - mac_ticks[-1][1] > 10000:
                        mac_ticks.append((number, current))
            else:
                pc_unknown += 1
        if hit and not active:
            anchor_ticks.append(current)
        active = hit

    before = Path(path).stat()
    with Path(path).open('rb') as stream:
        for index, raw in enumerate(stream):
            h.update(raw)
            if index % 1000000 == 0:
                b.require(time.monotonic() < deadline, 'Bounded offline VCD audit expired')
            if not definitions:
                fields = raw.split()
                if not fields:
                    continue
                if fields[0] == b'$timescale':
                    first_scale = True
                if first_scale:
                    scale_lines.append(raw)
                    if b'$end' in raw:
                        first_scale = False
                if fields[0] == b'$scope':
                    scopes.append(fields[2])
                elif fields[0] == b'$upscope':
                    scopes.pop()
                elif fields[0] == b'$var':
                    declared.add(fields[3])
                    if fields[4] in (b'clk_i', b'rst_ni', b'pc_o', b'commit_ack_o', b'state_q', b'ara_req_valid_i'):
                        label = dc.activity_label(b'/'.join(scopes + [fields[4]]).decode())
                        if label:
                            codes.setdefault(fields[3], []).append(label)
                            widths[label] = int(fields[2])
                elif fields[0] == b'$enddefinitions':
                    definitions = True
                continue
            if raw.startswith(b'#'):
                tick = int(raw[1:])
                b.require(current is None or tick >= current, 'VCD time reversal')
                flush(tick)
                first = tick if first is None else first
                current = tick
                continue
            if raw.startswith(b'$dumpvars'):
                snapshot = True
                continue
            if raw.startswith(b'$end'):
                snapshot = False
                continue
            if raw[:1] in (b'b', b'B', b'r', b'R'):
                fields = raw.split()
                value, code = fields[0][1:].lower(), fields[-1]
            elif raw[:1] in (b'0', b'1', b'x', b'X', b'z', b'Z'):
                value, code = raw[:1].lower(), raw[1:].rstrip()
            else:
                continue
            if snapshot:
                initial_ids.add(code)
                initial_count += 1
                initial_unknown += int(not known(value))
            for label in codes.get(code, ()):
                fill = value[:1] if value[:1] in (b'x', b'z') else b'0'
                normalized = value.rjust(widths[label], fill)
                if label in states and states[label] != normalized:
                    edges[label] += 1
                states[label] = normalized
    after = Path(path).stat()
    b.require((before.st_size, before.st_mtime_ns, before.st_ino) ==
              (after.st_size, after.st_mtime_ns, after.st_ino), 'Original VCD changed during audit')
    b.require(definitions and not snapshot and declared == initial_ids and
              re.search(rb'\$timescale\s+100\s*fs\s+\$end', b''.join(scale_lines)), 'Incomplete snapshot or wrong timebase')
    signals = {name: dict(width=widths[name], values=dict(counts),
        unknown_ticks=sum(ticks for value, ticks in counts.items() if set(value) - set('01')),
        transitions=edges[name]) for name, counts in dwell.items()}
    return dict(signals=signals, first_tick=first, last_tick=current, duration_ticks=current-first,
        clock_edges=edges['clock'], retire_samples=retire, pc_unknown_when_committing=pc_unknown,
        initial_value_records=initial_count, initial_unknown_value_records=initial_unknown,
        top_committing_pcs=pcs.most_common(24), active_payload_unknown_samples=0, pv_fpu_samples=0,
        anchor_retire_samples=pcs['0x800022f4'], anchor_episode_ticks=anchor_ticks,
        mac_episode_ticks=mac_ticks, vcd_sha256=h.hexdigest(), raw_bytes=after.st_size,
        complete_initial_state=True, whole_design_knownness_claim=False)


def validate(report, old, plan, pairs):
    for field in ('signals', 'first_tick', 'last_tick', 'duration_ticks', 'clock_edges', 'retire_samples',
                  'pc_unknown_when_committing', 'initial_value_records', 'initial_unknown_value_records',
                  'top_committing_pcs', 'active_payload_unknown_samples', 'pv_fpu_samples'):
        b.require(report[field] == old[field], 'Independent raw audit disagrees with original controls/statistics: ' + field)
    expected = [x['cycle'] for x in pairs if plan['first_cycle'] <= x['cycle'] <= plan['last_cycle']]
    observed = [(tick-report['first_tick']) / 10000 + plan['first_cycle'] for tick in report['anchor_episode_ticks']]
    b.require(len(expected) == len(observed) >= 4, 'Missing/extra outer-K loop companion episodes')
    offsets = [actual - reference for actual, reference in zip(observed, expected)]
    b.require(all(abs(delta) <= 2 for delta in offsets), 'Real loop phase displacement exceeds measured two-cycle bound')
    b.require(len(report['mac_episode_ticks']) >= 4, 'Actual vmacc/fmacc body evidence missing')
    return dict(expected_rtl_cycles=expected, observed_gate_cycles=observed,
                gate_minus_rtl_cycles=offsets, original_missing_anchor_port=1, measured_companion_port=0,
                companion_pc='0x800022f4', missing_branch_pc='0x800022f8',
                exact_instruction_equivalence_claimed=False)


def prepare(out):
    b.require(out == DEFAULT and not out.exists(), 'Fresh independent offline audit required')
    b.verify(b.read(PARENT / 'source-pins.json'))
    out.mkdir()
    shutil.copytree(r.DEFAULT / 'inputs', out / 'inputs')
    for name in ('audit_m1_port_v1.py', 'test_audit_m1_port_v1.py'):
        shutil.copyfile(HERE / name, out / 'inputs' / name)
    shutil.copyfile(PARENT / 'image-binding.json', out / 'image-binding.json')
    case = out / 'cases/m1'
    shutil.copytree(PARENT / 'cases/m1/inputs', case / 'inputs')
    (case / 'run').mkdir()
    for name in ('window.vcd', 'run.vcs.log', 'console.log'):
        (case / 'run' / name).symlink_to(PARENT / 'cases/m1/run' / name)
    plan = b.read(PARENT / 'cases/m1/plan.json')
    plan.update(offline_only=True, original_capture_plan=str(PARENT / 'cases/m1/plan.json'))
    plan['window_basis'] = dict(plan['window_basis'], anchor_pc='0x800022f4', anchor_port=0,
        original_branch_pc='0x800022f8', original_branch_port=1,
        basis='Same-cycle port0 vfsub companion; same original contiguous window and kernel')
    plan['phase_contract'] = dict(plan['phase_contract'], window=plan['window_basis'])
    b.save(case / 'plan.json', plan, True)
    pins = b.read(PARENT / 'source-pins.json')
    pins.update({str(p): b.sha(p) for p in out.rglob('*') if p.is_file() and not p.is_symlink()})
    for path in (PARENT / 'result.json', PARENT / 'cases/m1/activity-audit.json', r.CORE):
        pins[str(path)] = b.sha(path)
    b.save(out / 'audit-source-pins.json', pins, True)
    worker = ['/usr/bin/python3', '-B', str(out / 'inputs/audit_m1_port_v1.py'), 'execute', '--output', str(out)]
    service = ['systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec', '--property=KillMode=control-group',
        '--property=RuntimeMaxSec=7200', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    b.save(out / 'ready-command.json', dict(service=service), True)


def execute(out):
    b.require(out == DEFAULT and Path(__file__).resolve() == out / 'inputs/audit_m1_port_v1.py', 'Frozen offline auditor required')
    owner = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', 'MainPID', '--value'], text=True).strip()
    b.require(owner == str(os.getpid()) and UNIT in Path('/proc/self/cgroup').read_text(), 'Direct service owner required')
    pins = b.read(out / 'audit-source-pins.json')
    b.verify(pins)
    b.save(out / 'attempt.json', dict(pid=os.getpid(), started_ns=time.time_ns(), simulations_launched=0), True)
    case = out / 'cases/m1'
    try:
        dc = w.load(out / 'inputs/dc_power.py', 'offline_original_control_policy')
        plan = b.read(case / 'plan.json')
        old = b.read(PARENT / 'cases/m1/activity-audit.json')
        b.require(old['reasons'] == ['RTL loop anchor not observed retiring in mapped gate window'], 'Unexpected original failure scope')
        b.save(out / 'status.json', dict(state='STREAMING_ORIGINAL_VCD_NO_SIMULATION'))
        report = scan(case / 'run/window.vcd', dc)
        paired = r.pairing(Path(plan['window_basis']['trace']))
        alignment = validate(report, old, plan, paired)
        report.update(cycles=plan['last_cycle'] - plan['first_cycle'])
        report.update(dc.activity_policy(report, 'rvv', 'm1', '0x800022f4'))
        b.require(report['state'] == 'ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS', 'Independent control/phase policy rejection')
        text = (case / 'run/run.vcs.log').read_text()
        b.g.clean_log(text)
        begin, end = b.g.capture_markers(text, plan['first_cycle'], plan['last_cycle'])
        b.require((report['first_tick'], report['last_tick']) == (begin*10000, end*10000) and
                  report['duration_ticks'] == report['cycles']*10000 and
                  re.search(r'\$finish at simulation time\s+' + str(end) + r'\s*$', text, re.M), 'Original closed-window EOF mismatch')
        b.require(not w.d.log_evidence(case / 'run/run.vcs.log')['counts'], 'Actual enabled SRAM X warning')
        b.save(case / 'activity-audit.json', report, True)
        b.save(out / 'alignment-proof.json', alignment, True)
        pins[str(case / 'run/window.vcd')] = report['vcd_sha256']
        for path in (case / 'run/run.vcs.log', case / 'activity-audit.json', out / 'alignment-proof.json'):
            pins[str(path)] = b.sha(path)
        b.save(out / 'source-pins.json', pins, True)
        binding = b.read(out / 'image-binding.json')
        result = dict(state='CAPTURE_COMPLETE_NOT_TASK_PASS', kind='m1', offline_scoped_successor=True,
            original_failure=str(PARENT / 'result.json'), original_audit=str(PARENT / 'cases/m1/activity-audit.json'),
            original_FAIL_unchanged=True, simulations_launched=0,
            vcd=str(case / 'run/window.vcd'), log=str(case / 'run/run.vcs.log'),
            vcd_sha256=report['vcd_sha256'], log_sha256=b.sha(case / 'run/run.vcs.log'),
            elf_sha256=plan['elf_sha256'], simv_sha256=binding['simv_sha256'],
            first_cycle=plan['first_cycle'], last_cycle=plan['last_cycle'], clock_period_ns=1,
            phase_contract=plan['phase_contract'], strict_original_state='FAIL',
            full_gate_task_pass=False, gate_numeric_checked=False, paired_ratio_publishable=False, power_acceptance=False,
            vcd_evidence=dict(first_tick=report['first_tick'], last_tick=report['last_tick'], timescale_fs=100,
                complete_initial_state=True, eof_at_selected_end=True))
        b.save(case / 'result.json', result, True)
        w.POWER = w.OUT / 'power_dc_20261117_rvv_m1_port_audit_01'
        w.power_worker(out, 'm1')
        final = dict(state='OFFLINE_ACTIVITY_ELIGIBLE_PORT0_COMPANION_NOT_GLS_PASS',
                     original_FAIL_unchanged=True, simulations_launched=0, alignment=alignment, power_acceptance=False)
    except BaseException as exc:
        final = dict(state='FAIL', error=repr(exc), original_FAIL_unchanged=True, simulations_launched=0)
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
