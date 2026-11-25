#!/usr/bin/env python3
"""Read-only first-X evidence and one bounded baseline diagnostic, never power."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rvv_diag_frozen_scheduler', HERE / 'gate_rvv_activity_v2.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
b = s.b
OUT = b.OUT
OLD = OUT / 'power_gls_20261117_baseline_rvv_activity_02'
DEFAULT = OUT / 'power_gls_20261117_baseline_rvv_firstx_01'


def wanted(path):
    leaf = path.rsplit('.', 1)[-1]
    return (leaf in ('clk_i', 'rst_ni') and path.count('.') == 3 or
            '.i_ariane.' in path and leaf in
            ('pc_commit', 'commit_ack_commit_id', 'wdata_commit_id') or
            '.gen_lanes_0__i_lane.' in path and '.i_simd_alu.' in path and leaf in
            ('operand_a_i', 'operand_b_i', 'valid_i', 'vm_i', 'op_i', 'result_o', 'mask_i') or
            '.i_ara.i_dispatcher.' in path and leaf in ('state_q', 'state_d'))


def inspect(path):
    scope, selected, names, widths, values, stats = [], {}, {}, {}, {}, {}
    tick, falling, reductions, samples = None, False, {}, []

    def sample():
        if not falling:
            return
        row = {name: values.get(code, 'x') for name, code in names.items()}
        def leaf(name):
            return next((v for k, v in row.items() if k.endswith('.' + name)), 'x')
        pc, ack, data = leaf('pc_commit'), leaf('commit_ack_commit_id'), leaf('wdata_commit_id')
        if set(pc) <= {'0', '1'} and int(pc, 2) in (0x80001380, 0x80001384) and ack.endswith('1'):
            key = hex(int(pc, 2))
            bits = data.zfill(128)[-64:]
            reductions.setdefault(key, set()).add(hex(int(bits, 2)) if set(bits) <= {'0', '1'} else bits)
        # Keep discriminating ALU events, bounded independently of waveform size.
        op, valid = leaf('op_i'), leaf('valid_i')
        if valid == '1' and set(op) <= {'0', '1'} and int(op, 2) == 29 and len(samples) < 40:
            samples.append(dict(tick=tick, values=row))

    with Path(path).open() as stream:
        for raw in stream:
            line = raw.strip()
            fields = line.split()
            if line.startswith('$scope '):
                scope.append(fields[2])
            elif line.startswith('$upscope'):
                scope.pop()
            elif line.startswith('$var '):
                name = '.'.join(scope + [fields[4]])
                if wanted(name):
                    names[name] = fields[3]
                    selected.setdefault(fields[3], []).append(name)
                    widths[fields[3]] = int(fields[2])
            elif line.startswith('#'):
                sample()
                tick, falling = int(line[1:]), False
            elif line.startswith('b') and len(fields) == 2:
                value, code = fields[0][1:].lower(), fields[1]
                if code in selected:
                    update(stats, values, code, value, tick)
            elif line and line[0] in '01xXzZ' and line[1:] in selected:
                code, value = line[1:], line[0].lower()
                if any(n == 'ara_tb.dut.i_ara_soc.clk_i' for n in selected[code]) and value == '0':
                    falling = True
                update(stats, values, code, value, tick)
        sample()
    b.require(names and any(k.endswith('.pc_commit') for k in names), 'Missing diagnostic PC')
    return dict(signals={name: dict(width=widths[code], **stats.get(code, {})) for name, code in names.items()},
                reductions={k: sorted(v) for k, v in reductions.items()}, merge_samples=samples,
                gate_numeric_pass=False, power_acceptance=False)


def update(stats, values, code, value, tick):
    row = stats.setdefault(code, dict(initial=value, records=0, unknown_records=0))
    row['records'] += 1
    if 'x' in value or 'z' in value:
        row['unknown_records'] += 1
        row.setdefault('first_unknown_tick', tick)
    else:
        row.setdefault('first_known_tick', tick)
    row['final'] = value
    values[code] = value


def log_evidence(path):
    first, counts = {}, {}
    pattern = re.compile(r'Warning (\S+) : input (.+?) unknown/high-Z.*?simulation time ([\d.]+)')
    with Path(path).open() as stream:
        for number, line in enumerate(stream, 1):
            m = pattern.search(line)
            if m:
                category = m[2]
                counts[category] = counts.get(category, 0) + 1
                first.setdefault(category, dict(line=number, instance=m[1], ns=m[3]))
    return dict(first=first, counts=counts)


def prepare(out):
    b.require(out == DEFAULT and not out.exists(), 'Fresh diagnostic output required')
    b.verify(b.read(OLD / 'source-pins.json'))
    out.mkdir()
    (out / 'inputs').mkdir()
    pins = {}
    for name in ('gate_rvv_xdiag_v1.py', 'test_gate_rvv_xdiag_v1.py', 'gate_rvv_activity_v2.py',
                 'gate_rvv_activity.py', 'gate_run.py', 'audit_gate_capture_eof.py'):
        src, dst = HERE / name, out / 'inputs' / name
        shutil.copyfile(src, dst)
        pins[str(src)] = pins[str(dst)] = b.sha(src)
    case = out / 'cases/m1'
    shutil.copytree(OLD / 'cases/m1/inputs', case / 'inputs')
    (case / 'run').mkdir()
    plan = b.read(OLD / 'cases/m1/plan.json')
    plan.update(first_cycle=15170, last_cycle=15690, max_cycles=15750,
                diagnostic_only=True, window_basis='First merge X -> scalar reductions -> cache/clock corruption')
    argv = [v.replace(str(OLD / 'cases/m1'), str(case)) for v in plan['command']]
    argv = ['+GATE_ROI_FIRST=15170' if v.startswith('+GATE_ROI_FIRST=') else
            '+GATE_ROI_LAST=15690' if v.startswith('+GATE_ROI_LAST=') else
            '+GATE_MAX_CYCLES=15750' if v.startswith('+GATE_MAX_CYCLES=') else v for v in argv]
    plan.update(command=argv, cwd=str(case / 'run'), elf=str(case / 'inputs/program.elf'))
    b.save(case / 'plan.json', plan, True)
    for p in (case / 'plan.json', *list((case / 'inputs').iterdir()), OLD / 'source-pins.json'):
        pins[str(p)] = b.sha(p)
    binding = b.read(OLD / 'image-binding.json')
    b.verify(binding['image_pins'])
    pins.update(binding['image_pins'])
    b.save(out / 'image-binding.json', binding, True)
    pins[str(out / 'image-binding.json')] = b.sha(out / 'image-binding.json')
    b.save(out / 'source-pins.json', pins, True)
    unit = out.name.replace('_', '-') + '.service'
    worker = ['/usr/bin/python3', '-B', str(out / 'inputs/gate_rvv_xdiag_v1.py'), 'execute', '--output', str(out)]
    service = ['systemd-run', '--user', '--unit=' + unit, '--property=Type=exec',
               '--property=KillMode=control-group', '--property=RuntimeMaxSec=28800',
               '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
               '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    b.save(out / 'ready-command.json', dict(service=service), True)


def execute(out):
    b.require(out == DEFAULT and Path(__file__).resolve() == out / 'inputs/gate_rvv_xdiag_v1.py', 'Frozen diagnostic worker')
    unit = out.name.replace('_', '-') + '.service'
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    b.require(owner == str(__import__('os').getpid()), 'Direct service ownership required')
    pins = b.read(out / 'source-pins.json')
    b.verify(pins)
    b.save(out / 'attempt.json', dict(started_ns=time.time_ns()), True)
    def interrupted(signum, frame):
        raise InterruptedError(signum)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        b.q8_units = s.q8_gls_units
        case = out / 'cases/m1'
        plan = b.read(case / 'plan.json')
        run = b.run_capture(out, case, plan, pins)
        capture = b.finish_capture(case, plan, b.read(out / 'image-binding.json'), run)
        evidence = inspect(case / 'run/window.vcd')
        logs = log_evidence(case / 'run/run.vcs.log')
        b.verify(pins)
        result = dict(state='FIRST_X_DIAGNOSTIC_COMPLETE_NOT_POWER', capture=capture,
                      wave=evidence, warnings=logs, root_cause_proven=False, power_acceptance=False)
    except BaseException as exc:
        result = dict(state='FAIL', error=repr(exc), power_acceptance=False, automatic_retry=False)
    b.save(out / 'result.json', result, True)
    return int(result['state'] == 'FAIL')


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'execute', 'inspect'))
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--vcd', type=Path)
    a = p.parse_args()
    if a.action == 'inspect':
        print(json.dumps(inspect(a.vcd), indent=2))
    elif a.action == 'prepare':
        prepare(a.output)
    else:
        return execute(a.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
