#!/usr/bin/env python3
"""Offline successor: exact JSON row types and lossless observed-control projection.

Projection is an audit acceleration only. SAIF/DC always consume the original VCD.
Every timestamp, selected control record, header and initial value is retained.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import importlib.util

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sealed_port_auditor_v1', HERE / 'audit_m1_port_v1.py')
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)
b, w, r = v1.b, v1.w, v1.r
PREVIOUS = v1.DEFAULT
DEFAULT = w.OUT / 'power_gls_20261117_rvv_m1_port_audit_02'
UNIT = 'power-audit-20261117-rvv-m1-port-02.service'


def top_pairs(rows):
    b.require(type(rows) is list, 'Top-PC table must be a list')
    result = []
    for row in rows:
        b.require(type(row) in (list, tuple) and len(row) == 2 and
                  type(row[0]) is str and re.fullmatch(r'0x[0-9a-f]+', row[0]) and
                  type(row[1]) is int and row[1] > 0, 'Malformed PC/count row')
        result.append((row[0], row[1]))
    b.require(len({pc for pc, _ in result}) == len(result), 'Duplicate top PC')
    return result


def compare_representation(live, persisted, old):
    actual, expected = top_pairs(persisted['top_committing_pcs']), top_pairs(old['top_committing_pcs'])
    proof = dict(live_row_types=sorted({type(x).__name__ for x in live['top_committing_pcs']}),
        original_JSON_row_types=sorted({type(x).__name__ for x in old['top_committing_pcs']}),
        raw_python_equality=live['top_committing_pcs'] == old['top_committing_pcs'],
        exact_ordered_PC_and_counts_equal=actual == expected,
        actual_rows=persisted['top_committing_pcs'], original_rows=old['top_committing_pcs'],
        counting_semantics='Same port0-only acknowledged settled intervals, not retired instruction counts',
        port1_samples_added=False, ordering_or_counts_relaxed=False)
    b.require(actual == expected, 'Actual ordered PC/count disagreement, not a representation-only failure')
    return proof


def projected_scan(raw, dc, output):
    before = raw.stat()
    projection = output / 'observed-controls.vcd'
    scopes, codes, selected = [], set(), {}
    snapshot = done = False
    prefix_bytes = 0
    with raw.open('rb') as source, projection.open('xb') as target:
        for line in source:
            target.write(line)
            prefix_bytes += len(line)
            fields = line.split()
            if fields:
                if fields[0] == b'$scope':
                    scopes.append(fields[2])
                elif fields[0] == b'$upscope':
                    scopes.pop()
                elif fields[0] == b'$var' and fields[4] in (
                        b'clk_i', b'rst_ni', b'pc_o', b'commit_ack_o', b'state_q', b'ara_req_valid_i'):
                    label = dc.activity_label(b'/'.join(scopes + [fields[4]]).decode())
                    if label:
                        codes.add(fields[3].decode())
                        selected[label] = dict(code=fields[3].decode(), width=int(fields[2]),
                                               path=b'/'.join(scopes+[fields[4]]).decode())
            if line.startswith(b'$dumpvars'):
                snapshot = True
            elif snapshot and line.strip() == b'$end':
                done = True
                break
    b.require(done and set(selected) == {'clock', 'reset', 'pc', 'ack', 'dispatcher', 'sequencer', 'vector_valid'},
              'Exact original baseline control inventory and complete initial snapshot required')
    alternatives = '(?:' + '|'.join(re.escape(code) for code in sorted(codes)) + ')'
    pattern = r'^(?:#|\$|[01xXzZ]' + alternatives + r'$|[bBrR][^ \t\r\n]+[ \t]+' + alternatives + r'[ \t]*$)'
    tail, rg = shutil.which('tail'), shutil.which('rg')
    b.require(tail and rg, 'Reviewed bounded control filtering requires tail and rg')
    command = [rg, '--text', '--no-heading', '--no-line-number', '--color=never', '-e', pattern]
    with projection.open('ab') as target:
        producer = subprocess.Popen([tail, '-c', '+' + str(prefix_bytes + 1), str(raw)], stdout=subprocess.PIPE)
        try:
            result = subprocess.run(command, stdin=producer.stdout, stdout=target, stderr=subprocess.PIPE, timeout=600)
            producer.stdout.close()
            b.require(producer.wait(timeout=30) == 0 and result.returncode == 0,
                      'Control projection tool failure: ' + result.stderr.decode(errors='replace'))
        finally:
            b.g.stop_process(producer)
    report = v1.scan(projection, dc)
    projection_sha = report['vcd_sha256']
    original_sha = b.sha(raw)
    after = raw.stat()
    b.require((before.st_size, before.st_mtime_ns, before.st_ino) ==
              (after.st_size, after.st_mtime_ns, after.st_ino), 'Original waveform changed during offline audit')
    report.update(vcd_sha256=original_sha, raw_bytes=after.st_size,
        projection=dict(path=str(projection), sha256=projection_sha, bytes=projection.stat().st_size,
            original=str(raw), original_sha256=original_sha, preserved_prefix_bytes=prefix_bytes,
            all_timestamps_preserved=True, all_observed_control_records_preserved=True,
            full_header_and_initial_snapshot_preserved=True, selected_controls=selected,
            filter_command=command, tools={tail: b.sha(tail), rg: b.sha(rg)},
            for_audit_only=True, used_for_power=False))
    return report


def prepare(out):
    b.require(out == DEFAULT and not out.exists(), 'Fresh independent successor required')
    previous = b.read(PREVIOUS / 'result.json')
    b.require(previous['state'] == 'FAIL' and previous['error'] ==
              "ValueError('Independent raw audit disagrees with original controls/statistics: top_committing_pcs')",
              'Only the exact persisted top-PC comparison failure is in scope')
    b.verify(b.read(PREVIOUS / 'audit-source-pins.json'))
    b.require(b.sha(HERE / 'audit_m1_port_v1.py') == b.sha(PREVIOUS / 'inputs/audit_m1_port_v1.py'), 'Sealed scan/validation source drift')
    out.mkdir()
    shutil.copytree(PREVIOUS / 'inputs', out / 'inputs')
    for name in ('audit_m1_port_v2.py', 'test_audit_m1_port_v2.py'):
        shutil.copyfile(HERE / name, out / 'inputs' / name)
    shutil.copyfile(PREVIOUS / 'image-binding.json', out / 'image-binding.json')
    case = out / 'cases/m1'
    shutil.copytree(PREVIOUS / 'cases/m1/inputs', case / 'inputs')
    (case / 'run').mkdir()
    for name in ('window.vcd', 'run.vcs.log', 'console.log'):
        (case / 'run' / name).symlink_to((PREVIOUS / 'cases/m1/run' / name).resolve())
    shutil.copyfile(PREVIOUS / 'cases/m1/plan.json', case / 'plan.json')
    with (out / 'host-tests.log').open('x') as log:
        subprocess.run([sys.executable, '-B', str(out / 'inputs/test_audit_m1_port_v2.py'), '-v'],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    pins = b.read(PREVIOUS / 'audit-source-pins.json')
    pins.update({str(p): b.sha(p) for p in out.rglob('*') if p.is_file() and not p.is_symlink()})
    pins[str(PREVIOUS / 'result.json')] = b.sha(PREVIOUS / 'result.json')
    b.save(out / 'audit-source-pins.json', pins, True)
    worker = ['/usr/bin/python3', '-B', str(out / 'inputs/audit_m1_port_v2.py'), 'execute', '--output', str(out)]
    service = ['systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec', '--property=KillMode=control-group',
        '--property=RuntimeMaxSec=7200', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    b.save(out / 'ready-command.json', dict(service=service), True)


def execute(out):
    b.require(out == DEFAULT and Path(__file__).resolve() == out / 'inputs/audit_m1_port_v2.py', 'Frozen JSON-type successor required')
    owner = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', 'MainPID', '--value'], text=True).strip()
    b.require(owner == str(os.getpid()) and UNIT in Path('/proc/self/cgroup').read_text(), 'Direct service owner required')
    pins = b.read(out / 'audit-source-pins.json')
    b.verify(pins)
    b.save(out / 'attempt.json', dict(pid=os.getpid(), started_ns=time.time_ns(), simulations_launched=0), True)
    case = out / 'cases/m1'
    try:
        dc = w.load(out / 'inputs/dc_power.py', 'unchanged_port0_policy_v2')
        plan = b.read(case / 'plan.json')
        old = b.read(v1.PARENT / 'cases/m1/activity-audit.json')
        b.require(old['reasons'] == ['RTL loop anchor not observed retiring in mapped gate window'], 'Original failure scope changed')
        b.save(out / 'status.json', dict(state='OFFLINE_ORIGINAL_CONTROL_PROJECTION_NO_VCS'))
        live = projected_scan(case / 'run/window.vcd', dc, out)
        # Persist BEFORE comparison, including on failures. JSON arrays now have identical types.
        b.save(out / 'raw-scan-report.json', live, True)
        report = b.read(out / 'raw-scan-report.json')
        proof = compare_representation(live, report, old)
        b.save(out / 'representation-proof.json', proof, True)
        pairs = r.pairing(Path(plan['window_basis']['trace']))
        alignment = v1.validate(report, old, plan, pairs)
        report.update(cycles=plan['last_cycle'] - plan['first_cycle'])
        report.update(dc.activity_policy(report, 'rvv', 'm1', '0x800022f4'))
        b.require(report['state'] == 'ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS', 'Independent original control/phase policy rejected')
        text = (case / 'run/run.vcs.log').read_text()
        b.g.clean_log(text)
        begin, end = b.g.capture_markers(text, plan['first_cycle'], plan['last_cycle'])
        b.require((report['first_tick'], report['last_tick']) == (begin*10000, end*10000) and
                  report['duration_ticks'] == report['cycles']*10000 and
                  re.search(r'\$finish at simulation time\s+' + str(end) + r'\s*$', text, re.M), 'Original EOF/window mismatch')
        b.require(not w.d.log_evidence(case / 'run/run.vcs.log')['counts'], 'Actual enabled SRAM X')
        b.save(case / 'activity-audit.json', report, True)
        b.save(out / 'alignment-proof.json', alignment, True)
        pins[str(case / 'run/window.vcd')] = report['vcd_sha256']
        for path in (case / 'run/run.vcs.log', case / 'activity-audit.json', out / 'raw-scan-report.json',
                     out / 'representation-proof.json', out / 'alignment-proof.json', out / 'observed-controls.vcd'):
            pins[str(path)] = b.sha(path)
        pins.update(report['projection']['tools'])
        b.save(out / 'source-pins.json', pins, True)
        binding = b.read(out / 'image-binding.json')
        result = dict(state='CAPTURE_COMPLETE_NOT_TASK_PASS', kind='m1', offline_scoped_successor=True,
            original_failure=str(v1.PARENT / 'result.json'), previous_audit_failure=str(PREVIOUS / 'result.json'),
            original_FAILs_unchanged=True, simulations_launched=0,
            vcd=str(case / 'run/window.vcd'), log=str(case / 'run/run.vcs.log'),
            vcd_sha256=report['vcd_sha256'], log_sha256=b.sha(case / 'run/run.vcs.log'),
            elf_sha256=plan['elf_sha256'], simv_sha256=binding['simv_sha256'],
            first_cycle=plan['first_cycle'], last_cycle=plan['last_cycle'], clock_period_ns=1,
            phase_contract=plan['phase_contract'], strict_original_state='FAIL',
            full_gate_task_pass=False, gate_numeric_checked=False, paired_ratio_publishable=False, power_acceptance=False,
            vcd_evidence=dict(first_tick=report['first_tick'], last_tick=report['last_tick'], timescale_fs=100,
                complete_initial_state=True, eof_at_selected_end=True),
            projection_used_for_power=False)
        b.save(case / 'result.json', result, True)
        w.POWER = w.OUT / 'power_dc_20261117_rvv_m1_port_audit_02'
        w.power_worker(out, 'm1')
        final = dict(state='OFFLINE_ACTIVITY_ELIGIBLE_PORT0_COMPANION_NOT_GLS_PASS',
            original_FAILs_unchanged=True, simulations_launched=0, representation_proof=proof,
            alignment=alignment, power_acceptance=False, power_uses_original_full_VCD=True)
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
