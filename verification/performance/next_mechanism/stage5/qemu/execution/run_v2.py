#!/usr/bin/env python3
"""Scoped QBS receipt replay, only unexecuted Stage4 guests, explicit four-gate proof."""
import argparse
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
spec = importlib.util.spec_from_file_location('execution_scoped_check', HERE / 'check_v2.py')
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
c = q.c
BASE_SHA = '54ea1bd95d894dc9bd2d7e688658e687893acfaa67be772707d8e0ab971027fe'
b = c.load(HERE / 'run.py', BASE_SHA, 'execution_sealed_original')
OUT, require, sha, read = b.OUT, b.require, b.sha, b.read
ORIGINAL = b.ORIGINAL
ORIGIN = OUT / 'stage5_qemu_execution_20261110_01'
ORIGIN_SHA = '2db44e35049e78526923b9a13f753f80768b70a93fe7cb320c06a197d79a1f8c'
ORIGIN_PINS = '9ba3b59a2a020546a01ecdb4536e89cbae2dd2ff9976e3f038f9c04ea0830b37'
OWN = ('run_v2.py', 'check_v2.py', 'test_run_v2.py')
KINDS = ('perf', 'functional')


def audit_path(path):
    path = Path(path).absolute()
    require(path == path.resolve() and path.parent == OUT and
            re.fullmatch(r'stage5_qemu_qbs_correction_[A-Za-z0-9_]+', path.name), 'Owned audit output required')
    return path


def command(receipt, argv, work, log, seconds, expected_rc=0):
    require(receipt['argv'] == argv and receipt['cwd'] == str(work) and receipt['timeout_seconds'] == seconds and
            receipt['state'] == 'EXITED' and type(receipt['returncode']) is int and
            receipt['returncode'] == expected_rc and receipt['pid'] > 1 and
            receipt['ended_ns'] > receipt['started_ns'] and receipt['log_sha256'] == sha(log),
            'Actual command receipt differs')


def origin(g):
    require(sha(ORIGIN / 'result.json') == ORIGIN_SHA and sha(ORIGIN / 'source-pins.json') == ORIGIN_PINS,
            'Original first-failure evidence drift')
    report = read(ORIGIN / 'result.json')
    s = read(ORIGIN / 'selection.json')
    require(report['state'] == 'FAIL' and report['gates'] == [] and
            report['error'] == "ValueError('Command exit failure: " + str(ORIGIN / 'work/qbs/checked.json') + "')",
            'Unexpected original failure')
    require(g.files(ORIGIN, exclude=('result.json', 'status.json', 'service.stdout.log', 'service.stderr.log')) ==
            report['artifacts'], 'Original artifact membership/hash differs')
    own = read(ORIGIN / 'owner.json')
    require(report['service_owner'] == own and own['unit'] == b.unit(ORIGIN) and
            own['main_pid'] == own['owner_pid'] > 1 and re.fullmatch('[0-9a-f]{32}', own['invocation_id']) and
            any(x.split(':', 2)[-1].endswith('/' + b.unit(ORIGIN)) for x in own['cgroup'].splitlines()) and
            read(ORIGIN / 'attempt.json') == dict(review_sha256=ORIGIN_PINS, **own), 'Original service owner differs')
    require(set(p.name for p in (ORIGIN / 'work').iterdir()) == {'qbs'}, 'An unexecuted Stage4 guest was already run')
    work = ORIGIN / 'work/qbs'
    guest, failed = read(work / 'guest.command.json'), read(work / 'checked.command.json')
    command(guest, s['commands'][0]['guest'], work, work / 'guest.log', b.GUEST_SECONDS)
    command(failed, s['commands'][0]['checker'], work, work / 'checked.json', b.CHECK_SECONDS, 1)
    require(guest['ended_ns'] <= failed['started_ns'], 'Original command order differs')
    return s, report, own, guest, failed


def audit(output):
    output = audit_path(output)
    require(HERE == ORIGINAL and not output.exists(), 'Fresh original-source audit required')
    output.mkdir()
    g = b.shared()
    report = dict(state='FAIL', original_execution=str(ORIGIN), original_result_sha256=ORIGIN_SHA,
                  guest_reexecuted=False, original_failure_relabelled=False, started_ns=time.time_ns())
    try:
        s, pins, _ = b.verify_prepared(ORIGIN)
        _, failed, own, guest, check_command = origin(g)
        work = ORIGIN / 'work/qbs'
        proof = q.check(work / 'guest.log', work / 'trace.log')
        b.checked_gate(proof, 'qbs')
        g.merge(pins, failed['artifacts'])
        g.merge(pins, {ORIGIN / 'result.json': ORIGIN_SHA})
        g.merge(pins, {q.SOURCE / n: h for n, h in q.SOURCES.items()})
        g.merge(pins, {HERE / n: sha(HERE / n) for n in (*OWN, *b.OWN)})
        g.save(output / 'source-pins.json', pins)
        report.update(state='QBS_SCOPED_CHECKER_CORRECTION_CHECKED', checked=proof,
                      original_source_pins_sha256=ORIGIN_PINS, service_owner=own,
                      original_guest_command=guest, original_failed_checker_command=check_command,
                      qemu=s['qemu'], source_pins_sha256=sha(output / 'source-pins.json'),
                      correction_checker_sha256=sha(HERE / 'check_v2.py'),
                      scope='46 helper illegal mtval=0; 3 decoder illegal mtval=opcode; 20 exact load addresses',
                      source_proof=dict(helper='qbs_helper.c:18-22 sets bins from the complete instruction',
                          forwarding='trans_xaraqbs.c:42 forwards ctx->opcode',
                          unwind='op_helper.c:46-57 calls cpu_loop_exit_restore',
                          metadata='translate.c:1360 initializes insn_start(pc,0,0)',
                          restoration='tcg/tcg-cpu.c:237 overwrites bins=data[1]',
                          front_cases_zero_based=q.FRONT))
    except BaseException as exc:
        report['error'] = repr(exc)
    report['ended_ns'] = time.time_ns()
    g.save(output / 'result.json', report)
    require(report['state'] == 'QBS_SCOPED_CHECKER_CORRECTION_CHECKED', 'Scoped audit failed; preserve output')
    return report


def checked_audit(path, digest, verify=True):
    path = audit_path(path)
    require(sha(path / 'result.json') == digest, 'Unreviewed scoped audit')
    report = read(path / 'result.json')
    require(report['state'] == 'QBS_SCOPED_CHECKER_CORRECTION_CHECKED' and
            report['original_execution'] == str(ORIGIN) and report['original_result_sha256'] == ORIGIN_SHA and
            report['original_source_pins_sha256'] == ORIGIN_PINS and
            report['guest_reexecuted'] is report['original_failure_relabelled'] is False and
            report['correction_checker_sha256'] == sha(HERE / 'check_v2.py') and
            sha(path / 'source-pins.json') == report['source_pins_sha256'], 'Invalid scoped correction')
    g = b.shared()
    s, _, own, guest, failed = origin(g)
    require(report['qemu'] == s['qemu'] and report['service_owner'] == own and
            report['original_guest_command'] == guest and report['original_failed_checker_command'] == failed,
            'Scoped audit original identity differs')
    b.checked_gate(report['checked'], 'qbs')
    require(report['checked']['work']['trap_layers'] == {'helper': 46, 'decode': 3, 'access': 20} and
            report['checked']['log_sha256'] == sha(ORIGIN / 'work/qbs/guest.log') and
            report['checked']['trace_sha256'] == sha(ORIGIN / 'work/qbs/trace.log') and
            report['checked']['correction'] == 'qemu10.2-exact-helper-decode-tval', 'Scoped check coverage differs')
    pins = read(path / 'source-pins.json')
    required = read(ORIGIN / 'source-pins.json') | {str(ORIGINAL / n): sha(HERE / n) for n in (*OWN, *b.OWN)}
    require(all(pins.get(p) == h for p, h in required.items()), 'Scoped mandatory identity pin missing')
    if verify:
        g.verify(pins)
    require(set(p.name for p in path.iterdir()) == {'source-pins.json', 'result.json'}, 'Audit membership differs')
    return report, pins | {str(path / 'result.json'): digest, str(path / 'source-pins.json'): report['source_pins_sha256']}


def selection(out, scoped, path, digest):
    original = read(ORIGIN / 'selection.json')
    reports = {kind: c.read(c.OUT / c.FIRMWARE[kind][0] / 'build.json') for kind in KINDS}
    s = b.selection(out, scoped['qemu'], reports, b.shared(), original['python'])
    s.update(schema='stage5-qemu-remaining-execution-v2', qbs_audit=str(Path(path).resolve()),
             qbs_audit_sha256=digest, commands=[j for j in s['commands'] if j['kind'] in KINDS])
    return s


def service_argv(out, s, review):
    args = b.service_argv(out, s, review)
    return [str(out / 'inputs/run_v2.py') if x == str(out / 'inputs/run.py') else x for x in args]


def layout(g):
    v = g.validator()
    return b.layout(g, v) | {n: ORIGINAL / n for n in OWN}


def prepare(out, audit_dir, digest):
    out = b.output_path(out)
    require(HERE == ORIGINAL and not out.exists(), 'Fresh original-source remaining-gate preparation required')
    out.mkdir()
    (out / 'inputs').mkdir()
    (out / 'work').mkdir()
    g = b.shared()
    report = dict(state='FAIL', guest_executed=False)
    try:
        scoped, pins = checked_audit(audit_dir, digest)
        for name, source in layout(g).items():
            target = out / 'inputs' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            g.merge(pins, {source: sha(source)})
        inventory = g.files(out / 'inputs')
        g.save(out / 'runner-inventory.json', inventory)
        g.merge(pins, inventory)
        s = selection(out, scoped, audit_dir, digest)
        g.save(out / 'selection.json', s)
        g.save(out / 'launch-receipt.json', dict(service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}')))
        with (out / 'host.log').open('x') as log:
            result = subprocess.run([s['python'], '-B', str(out / 'inputs/test_run_v2.py'), '-v'],
                                    cwd=out, env=s['environment'], stdout=log, stderr=subprocess.STDOUT, timeout=180)
        require(result.returncode == 0, 'Successor host checks failed')
        g.merge(pins, g.files(out))
        g.save(out / 'source-pins.json', pins)
        report.update(state='PREPARED_NOT_EXECUTED', source_pins_sha256=sha(out / 'source-pins.json'))
    except BaseException as exc:
        report['error'] = repr(exc)
    g.save(out / 'prepared.json', report)
    require(report['state'] == 'PREPARED_NOT_EXECUTED', 'Remaining-gate prepare failed; preserve output')
    return report


def verify_prepared(out):
    out = b.output_path(out)
    g = b.shared()
    s, pins = read(out / 'selection.json'), read(out / 'source-pins.json')
    require(read(out / 'prepared.json') == dict(state='PREPARED_NOT_EXECUTED', guest_executed=False,
            source_pins_sha256=sha(out / 'source-pins.json')), 'Prepared identity differs')
    g.verify(pins)
    scoped, required = checked_audit(s['qbs_audit'], s['qbs_audit_sha256'], verify=False)
    require(s == selection(out, scoped, s['qbs_audit'], s['qbs_audit_sha256']), 'Remaining-gate recipe differs')
    wanted = {str(out / 'inputs' / n): sha(p) for n, p in layout(g).items()}
    require(wanted == g.files(out / 'inputs') == read(out / 'runner-inventory.json'), 'Successor copy membership differs')
    g.merge(required, wanted)
    for n in ('selection.json', 'runner-inventory.json', 'launch-receipt.json', 'host.log'):
        g.merge(required, {out / n: sha(out / n)})
    require(all(pins.get(p) == h for p, h in required.items()), 'Mandatory successor pin missing')
    require(read(out / 'launch-receipt.json') == dict(service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}')),
            'Direct service recipe differs')
    return s, pins, g


def image_fields(s):
    return dict(qemu_build=s['qemu']['build'], qemu_build_receipt_sha256=s['qemu']['build_sha256'],
                qemu_prepare=s['qemu']['prepared'], qemu_prepare_receipt_sha256=s['qemu']['prepare_sha256'],
                executable=s['qemu']['executable'], executable_sha256=s['qemu']['executable_sha256'])


def run(out, review):
    out = b.output_path(out)
    require(HERE == out / 'inputs' and review == sha(out / 'source-pins.json') and
            not any((out / n).exists() for n in ('attempt.json', 'owner.json', 'result.json')), 'Fresh frozen worker required')
    g, own = b.shared(), b.owner(out)
    g.save(out / 'owner.json', own)
    g.save(out / 'attempt.json', dict(review_sha256=review, **own))
    report = dict(state='FAIL', gates=[], service_owner=own, guest_qbs_reexecuted=False,
                  performance_acceptance=False, deployment_approved=False, rtl_timing=False, automatic_retry=False)
    status = dict(state='PREFLIGHT', child_pid=None, **own)
    g.status_save(out / 'status.json', status)
    try:
        require(not any((out / 'work').iterdir()), 'Stale work; do not retry')
        s, pins, g = verify_prepared(out)
        env = s['environment'] | {'INVOCATION_ID': own['invocation_id']}
        os.environ.clear()
        os.environ.update(env)
        for job in s['commands']:
            work = out / 'work' / job['kind']
            work.mkdir()
            g.verify({s['qemu']['executable']: b.BINARY_SHA, job['elf']: job['elf_sha256']})
            guest = g.execute(job['guest'], work, work / 'guest.log', b.GUEST_SECONDS, env,
                              status, out / 'status.json', job['kind'] + '_GUEST')
            io = {str(p): sha(p) for p in (work / 'guest.log', work / 'trace.log', Path(job['elf']))}
            check = g.execute(job['checker'], work, work / 'checked.json', b.CHECK_SECONDS, env,
                              status, out / 'status.json', job['kind'] + '_CHECK')
            g.verify(io)
            proof = read(work / 'checked.json')
            b.checked_gate(proof, job['kind'])
            require(proof['log_sha256'] == sha(work / 'guest.log') and proof['trace_sha256'] == sha(work / 'trace.log'),
                    'Original checker consumed wrong evidence')
            report['gates'].append(dict(kind=job['kind'], state='PASS', returncode=guest['returncode'],
                                       guest_command=guest, checker_command=check, checked=proof))
        verify_prepared(out)
        require(b.owner(out) == own, 'Direct service owner changed')
        report.update(state='NATIVE_QEMU_REMAINING_TWO_GATES_CHECKED', source_pins_sha256=review,
                      post_pins_match=True, post_image_match=True, post_service_owner=own,
                      qbs_audit=s['qbs_audit'], qbs_audit_sha256=s['qbs_audit_sha256'], **image_fields(s))
    except BaseException as exc:
        report['error'] = repr(exc)
    report['artifacts'] = g.files(out, exclude=('status.json', 'service.stdout.log', 'service.stderr.log'))
    g.save(out / 'result.json', report)
    status.update(state=report['state'], child_pid=None)
    g.status_save(out / 'status.json', status)
    print(json.dumps(dict(state=report['state'], output=str(out))), flush=True)
    return int(report['state'] != 'NATIVE_QEMU_REMAINING_TWO_GATES_CHECKED')


def checked_execution(out, digest):
    out = b.output_path(out)
    require(sha(out / 'result.json') == digest, 'Unreviewed remaining-gate receipt')
    report = read(out / 'result.json')
    s, pins, g = verify_prepared(out)
    own = read(out / 'owner.json')
    require(report['state'] == 'NATIVE_QEMU_REMAINING_TWO_GATES_CHECKED' and
            report['post_pins_match'] is report['post_image_match'] is True and report['guest_qbs_reexecuted'] is False and
            report['source_pins_sha256'] == sha(out / 'source-pins.json') and
            report['service_owner'] == report['post_service_owner'] == own and own['unit'] == b.unit(out) and
            own['main_pid'] == own['owner_pid'] > 1 and re.fullmatch('[0-9a-f]{32}', own['invocation_id']) and
            any(x.split(':', 2)[-1].endswith('/' + b.unit(out)) for x in own['cgroup'].splitlines()) and
            read(out / 'attempt.json') == dict(review_sha256=report['source_pins_sha256'], **own), 'Incomplete execution/owner')
    require(all(report[k] == v for k, v in image_fields(s).items()) and
            report['qbs_audit'] == s['qbs_audit'] and report['qbs_audit_sha256'] == s['qbs_audit_sha256'], 'Image/audit changed')
    require(report['artifacts'] == g.files(out, exclude=('result.json', 'status.json', 'service.stdout.log', 'service.stderr.log')),
            'Remaining-gate artifact membership/hash differs')
    require([x['kind'] for x in report['gates']] == list(KINDS), 'Both actual Stage4 guests required')
    last = 0
    for row, job in zip(report['gates'], s['commands']):
        work = out / 'work' / row['kind']
        require(row['state'] == 'PASS' and type(row['returncode']) is int and row['returncode'] == 0 and
                read(work / 'checked.json') == row['checked'], 'Wrong actual guest/checker result')
        b.checked_gate(row['checked'], row['kind'])
        require(row['checked']['log_sha256'] == sha(work / 'guest.log') and
                row['checked']['trace_sha256'] == sha(work / 'trace.log'), 'Checker evidence differs')
        for key, name, file, seconds in (('guest', 'guest', 'guest.log', b.GUEST_SECONDS),
                                         ('checker', 'checked', 'checked.json', b.CHECK_SECONDS)):
            record = read(work / (name + '.command.json'))
            require(record == row[key + '_command'] and record['started_ns'] >= last, 'Command order/content differs')
            command(record, job[key], work, work / file, seconds)
            last = record['ended_ns']
    return report, pins | report['artifacts'] | {str(out / 'result.json'): digest}


def combined(two, native, scoped):
    require(two['state'] == 'NATIVE_QEMU_REMAINING_TWO_GATES_CHECKED' and
            native['state'] == 'DIRECTED_NATIVE_AKV_CHECKED' and
            native.get('rom_probe', {}).get('state') == 'PASS' and
            native['rom_probe']['checked']['state'] == 'ROM_RAM_ONLY_FAULT_CHECKED', 'Actual directed/ROM gates absent')
    keys = ('qemu_build', 'qemu_build_receipt_sha256', 'qemu_prepare', 'qemu_prepare_receipt_sha256',
            'executable', 'executable_sha256')
    require(all(two[k] == native[k] for k in keys) and two['executable_sha256'] == b.BINARY_SHA and
            two['qemu_build_receipt_sha256'] == b.BUILD_SHA, 'Different actual images')
    identities = {k: two[k] for k in keys}
    require(identities == image_fields(dict(qemu=scoped['qemu'])), 'Scoped QBS used another image')
    return identities


def aggregate(out, execution, execution_sha, directed, directed_sha):
    out = b.output_path(out, aggregate=True)
    require(not out.exists(), 'Fresh aggregate required')
    out.mkdir()
    g = b.shared()
    report = dict(state='FAIL', rtl_timing=False, performance_acceptance=False, deployment_approved=False)
    try:
        two, pins = checked_execution(execution, execution_sha)
        scoped, apins = checked_audit(two['qbs_audit'], two['qbs_audit_sha256'], verify=False)
        native, npins = g.checked_result(directed, directed_sha)
        g.merge(pins, apins)
        g.merge(pins, npins)
        g.merge(pins, {HERE / n: sha(HERE / n) for n in (*OWN, *b.OWN)})
        fields = combined(two, native, scoped)
        g.save(out / 'source-pins.json', pins)
        report.update(state='NATIVE_QEMU_FOUR_GATES_CHECKED', completed_gates=b.GATES, **fields,
                      execution=str(Path(execution).resolve()), execution_result_sha256=execution_sha,
                      directed=str(Path(directed).resolve()), directed_result_sha256=directed_sha,
                      scoped_qbs_audit=two['qbs_audit'], scoped_qbs_audit_sha256=two['qbs_audit_sha256'],
                      original_qbs_execution=str(ORIGIN), original_qbs_execution_state='FAIL',
                      original_qbs_result_sha256=ORIGIN_SHA, original_qbs_guest_returncode=0,
                      checker_correction_explicit=True, original_failure_relabelled=False, qbs_guest_reexecuted=False,
                      source_pins_sha256=sha(out / 'source-pins.json'), shared_reader_sha256=b.GATE_SHA)
    except BaseException as exc:
        report['error'] = repr(exc)
    g.save(out / 'result.json', report)
    require(report['state'] == 'NATIVE_QEMU_FOUR_GATES_CHECKED', 'Four-gate aggregate failed; preserve result')
    return report


def checked_result(out, reviewed_result_sha256):
    out = b.output_path(out, aggregate=True)
    require(sha(out / 'result.json') == reviewed_result_sha256, 'Unreviewed four-gate result')
    report = read(out / 'result.json')
    require(report['state'] == 'NATIVE_QEMU_FOUR_GATES_CHECKED' and report['completed_gates'] == b.GATES and
            report['checker_correction_explicit'] is True and report['original_failure_relabelled'] is False and
            report['qbs_guest_reexecuted'] is False and report['original_qbs_execution_state'] == 'FAIL' and
            report['original_qbs_execution'] == str(ORIGIN) and report['original_qbs_result_sha256'] == ORIGIN_SHA and
            type(report['original_qbs_guest_returncode']) is int and report['original_qbs_guest_returncode'] == 0 and
            report['rtl_timing'] is report['performance_acceptance'] is report['deployment_approved'] is False and
            report['shared_reader_sha256'] == b.GATE_SHA and sha(out / 'source-pins.json') == report['source_pins_sha256'],
            'Invalid scoped four-gate aggregate')
    two, pins = checked_execution(report['execution'], report['execution_result_sha256'])
    scoped, apins = checked_audit(report['scoped_qbs_audit'], report['scoped_qbs_audit_sha256'], verify=False)
    require(two['qbs_audit'] == report['scoped_qbs_audit'] and
            two['qbs_audit_sha256'] == report['scoped_qbs_audit_sha256'], 'Different scoped audit')
    g = b.shared()
    native, npins = g.checked_result(report['directed'], report['directed_result_sha256'])
    require(all(report[k] == v for k, v in combined(two, native, scoped).items()), 'Mixed aggregate image')
    for extra in (apins, npins, {HERE / n: sha(HERE / n) for n in (*OWN, *b.OWN)}):
        g.merge(pins, extra)
    require(read(out / 'source-pins.json') == pins and
            set(p.name for p in out.iterdir()) == {'result.json', 'source-pins.json'}, 'Aggregate closure differs')
    return report, pins | {str(out / 'result.json'): reviewed_result_sha256,
                           str(out / 'source-pins.json'): report['source_pins_sha256']}


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = p.add_subparsers(dest='action', required=True)
    for action in ('audit', 'prepare', 'run', 'aggregate'):
        a = sub.add_parser(action)
        a.add_argument('--output', type=Path, required=True)
        if action == 'prepare':
            a.add_argument('--audit', type=Path, required=True)
            a.add_argument('--audit-sha256', required=True)
        elif action == 'run':
            a.add_argument('--review-sha256', required=True)
        elif action == 'aggregate':
            for key in ('execution', 'directed'):
                a.add_argument('--' + key, type=Path, required=True)
                a.add_argument('--' + key + '-sha256', required=True)
    a = p.parse_args()
    if a.action == 'audit':
        result = audit(a.output)
    elif a.action == 'prepare':
        result = prepare(a.output, a.audit, a.audit_sha256)
    elif a.action == 'aggregate':
        result = aggregate(a.output, a.execution, a.execution_sha256, a.directed, a.directed_sha256)
    else:
        return run(a.output, a.review_sha256)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    def interrupted(sig, frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    raise SystemExit(main())
