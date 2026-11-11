#!/usr/bin/env python3
"""One-shot unchanged ELF execution and same-image four-gate aggregation."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('native_execution_check', HERE / 'check.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
ROOT, OUT, require, sha, read = c.ROOT, c.OUT, c.require, c.sha, c.read
ORIGINAL = ROOT / 'verification/performance/next_mechanism/stage5/qemu/execution'
GATE_SHA = 'd1fb58bcb73ce264004f822b3c1daf5cd91e4ba6bdd8573951c7550d4e91cfe8'
BUILD = OUT / 'stage5_qemu_build_20261110_06'
BUILD_SHA = '93506639dda6fc22dc66733ca2160c5ba7b799787e8fb8f5e4d067ed37d3c3d6'
BINARY_SHA = '1deb41c75cc507030994765971d5a3d91f17e958c195bf60b4fb5563eb880a6f'
OWN = ('run.py', 'check.py', 'test_run.py')
KINDS = ('qbs', 'perf', 'functional')
GATES = ['directed-native-lifecycle-fault-flags', 'unchanged-stage4-perf02',
         'unchanged-stage4-functional01', 'native-qbs-successor-smoke']
GUEST_SECONDS, CHECK_SECONDS, SERVICE_SECONDS = 300, 120, 3000
CPU = 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true,xaraakv=true,xaraakv-resident=true'


def shared():
    path = HERE / 'shared/run_v9.py' if HERE != ORIGINAL else ORIGINAL.parent / 'gates/run_v9.py'
    return c.load(path, GATE_SHA, 'native_execution_directed_v9')


def output_path(path, aggregate=False):
    path = Path(path).absolute()
    prefix = 'stage5_qemu_four_gates_' if aggregate else 'stage5_qemu_execution_'
    require(path == path.resolve() and path.parent == OUT and
            re.fullmatch(prefix + r'[A-Za-z0-9_]+', path.name), 'Direct owned output required')
    return path


def collect_firmware(g):
    pins, reports = {}, {}
    for kind in ('perf', 'functional'):
        path, report, _, _ = c.stage4(kind)
        reports[kind] = report
        g.merge(pins, read(path / 'source-pins.json'))
        g.merge(pins, report['artifacts'])
        g.merge(pins, {path / 'build.json': c.FIRMWARE[kind][1]})
    g.merge(pins, {c.QBS_ELF: c.QBS_SHA})
    g.merge(pins, {ROOT / 'verification/qbs/qemu' / name: h for name, h in c.QBS_SOURCES.items()})
    g.verify(pins)
    return reports, pins


def recipes(out, qemu, reports, python):
    result = []
    for kind in KINDS:
        work = out / 'work' / kind
        bound = c.binding(kind, reports.get(kind))
        elf = c.QBS_ELF if kind == 'qbs' else OUT / c.FIRMWARE[kind][0] / 'attention_features.elf'
        args = [qemu['executable'], '-M', 'virt' if kind == 'qbs' else 'virt,x-ara-stage4=on',
                '-accel', 'tcg,one-insn-per-tb=on', '-cpu', CPU, '-smp', '1', '-m',
                '128M' if kind == 'qbs' else '16M', '-bios', 'none', '-kernel', str(elf),
                '-display', 'none', '-monitor', 'none', '-serial', 'none']
        if kind != 'qbs':
            args += ['-chardev', 'stdio,id=ara-stage4']
        args += ['-d', 'exec,nochain,int', '-dfilter', ','.join(hex(p) + '+1' for p in bound['points']),
                 '-trace', 'enable=akv_arch_*', '-D', str(work / 'trace.log')]
        result.append(dict(kind=kind, elf=str(elf), elf_sha256=sha(elf), guest=args,
                           checker=[python, '-B', str(out / 'inputs/check.py'), '--kind', kind,
                                    '--log', str(work / 'guest.log'), '--trace', str(work / 'trace.log')]))
    return result


def selection(out, qemu, reports, g, python=None):
    python = str(Path(python or sys.executable).resolve())
    require(qemu['build'] == str(BUILD) and qemu['build_sha256'] == BUILD_SHA and
            qemu['executable_sha256'] == BINARY_SHA, 'Only the accepted BUILD06 image is admitted')
    return dict(schema='stage5-qemu-unchanged-execution-v1', qemu=qemu, shared_reader_sha256=GATE_SHA,
                environment=g.environment(), python=python, commands=recipes(out, qemu, reports, python),
                guest_seconds=GUEST_SECONDS, checker_seconds=CHECK_SECONDS, service_seconds=SERVICE_SECONDS,
                automatic_retry=False, guest_executed=False)


def layout(g, v):
    paths = {n: ORIGINAL / n for n in OWN}
    paths.update({'shared/' + name: p for name, p in g.layout(v).items()})
    return paths


def unit(out):
    return 'stage5-qemu-execution-' + out.name + '.service'


def owner(out):
    inv = os.environ.get('INVOCATION_ID', '')
    require(re.fullmatch('[0-9a-f]{32}', inv), 'Direct systemd invocation required')
    group = Path('/proc/self/cgroup').read_text()
    require(any(row.split(':', 2)[-1].endswith('/' + unit(out)) for row in group.splitlines()), 'Wrong cgroup')
    main = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit(out),
                                    '--property=MainPID', '--value'], text=True, timeout=10).strip()
    require(main == str(os.getpid()), 'Worker must be direct service MainPID')
    return dict(unit=unit(out), main_pid=os.getpid(), owner_pid=os.getpid(), invocation_id=inv, cgroup=group)


def service_argv(out, s, review):
    return ['/usr/bin/systemd-run', '--user', '--unit=' + unit(out), '--property=Type=exec',
            '--property=KillMode=control-group', '--property=RuntimeMaxSec=' + str(SERVICE_SECONDS),
            '--property=MemoryMax=8G', '--property=TimeoutStopSec=20',
            '--property=WorkingDirectory=' + str(out / 'work'),
            '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
            '--property=StandardError=append:' + str(out / 'service.stderr.log'),
            *['--setenv=' + k + '=' + v for k, v in sorted(s['environment'].items())],
            s['python'], '-B', '-u', str(out / 'inputs/run.py'), 'run', '--output', str(out),
            '--review-sha256', review]


def prepare(out):
    require(HERE == ORIGINAL, 'Prepare from reviewed source')
    out = output_path(out)
    require(not out.exists(), 'Fresh output required; do not retry')
    out.mkdir()
    (out / 'inputs').mkdir()
    (out / 'work').mkdir()
    g = shared()
    report = dict(state='FAIL', guest_executed=False)
    try:
        v = g.validator()
        qemu, pins = g.collect_qemu(BUILD, BUILD_SHA, v)
        fw, fpins = collect_firmware(g)
        g.merge(pins, fpins)
        for name, source in layout(g, v).items():
            target = out / 'inputs' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            g.merge(pins, {source: sha(source)})
        inventory = g.files(out / 'inputs')
        g.save(out / 'runner-inventory.json', inventory)
        g.merge(pins, inventory)
        s = selection(out, qemu, fw, g)
        g.save(out / 'selection.json', s)
        g.save(out / 'launch-receipt.json', dict(service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}')))
        for label, argv, seconds in (
            ('host-tests', [s['python'], '-B', str(out / 'inputs/test_run.py'), '-v'], 180),
            ('runtime-link', ['/usr/bin/ldd', qemu['executable']], 30)):
            with (out / (label + '.log')).open('x') as log:
                result = subprocess.run(argv, cwd=out, env=s['environment'], stdout=log,
                                        stderr=subprocess.STDOUT, timeout=seconds)
            g.save(out / (label + '.command.json'), dict(argv=argv, cwd=str(out),
                   timeout_seconds=seconds, returncode=result.returncode))
            require(result.returncode == 0, 'Preparation failed: ' + label)
        text = (out / 'runtime-link.log').read_text()
        require('not found' not in text, 'Missing runtime library')
        libs = re.findall(r'(?:=>\s+|^\s*)(/[^\s()]+)', text, re.M)
        require(libs, 'Missing runtime loader evidence')
        runtime = {str(p): sha(p) for item in libs for p in (Path(item), Path(item).resolve())}
        g.save(out / 'runtime-pins.json', runtime)
        g.merge(pins, runtime)
        for p in (s['python'], '/usr/bin/systemd-run', '/usr/bin/systemctl', '/usr/bin/ldd'):
            g.merge(pins, {p: sha(p)})
        g.merge(pins, g.files(out, exclude=()))
        g.verify(pins)
        g.save(out / 'source-pins.json', pins)
        report.update(state='PREPARED_NOT_EXECUTED', source_pins_sha256=sha(out / 'source-pins.json'))
    except BaseException as exc:
        report['error'] = repr(exc)
    g.save(out / 'prepared.json', report)
    require(report['state'] == 'PREPARED_NOT_EXECUTED', 'Preparation failed; preserve ' + str(out))
    return report


def verify_prepared(out):
    g = shared()
    out = output_path(out)
    prepared, s, pins = read(out / 'prepared.json'), read(out / 'selection.json'), read(out / 'source-pins.json')
    require(prepared == dict(state='PREPARED_NOT_EXECUTED', guest_executed=False,
            source_pins_sha256=sha(out / 'source-pins.json')), 'Invalid prepared receipt')
    g.verify(pins)
    v = g.validator(out / 'inputs/shared/validator')
    qemu, needed = g.collect_qemu(BUILD, BUILD_SHA, v)
    fw, fpins = collect_firmware(g)
    g.merge(needed, fpins)
    require(s == selection(out, qemu, fw, g, s['python']), 'Recipe/configuration changed')
    wanted = {str(out / 'inputs' / name): sha(source) for name, source in layout(g, v).items()}
    require(wanted == read(out / 'runner-inventory.json') == g.files(out / 'inputs'), 'Runner copy membership changed')
    g.merge(needed, wanted)
    g.merge(needed, read(out / 'runtime-pins.json'))
    for name in ('selection.json', 'runner-inventory.json', 'launch-receipt.json', 'host-tests.log',
                 'host-tests.command.json', 'runtime-link.log', 'runtime-link.command.json', 'runtime-pins.json'):
        g.merge(needed, {out / name: sha(out / name)})
    require(all(pins.get(p) == h for p, h in needed.items()), 'Mandatory dependency pin missing')
    require(read(out / 'launch-receipt.json') ==
            dict(service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}')), 'Service recipe changed')
    return s, pins, g


def checked_gate(proof, kind):
    expected_sha = c.QBS_SHA if kind == 'qbs' else c.FIRMWARE[kind][2]
    require(proof['state'] == 'NATIVE_ELF_ARCHITECTURE_CHECKED' and proof['kind'] == kind and
            proof['elf_sha256'] == expected_sha and proof['rtl_timing'] is False and
            proof['rtl_protocol_checked'] is False and proof['performance_acceptance'] is False and
            proof['qemu_image_checked'] is proof['service_owner_checked'] is False, 'Invalid gate checker result')
    if kind == 'qbs':
        require(proof['work']['native_instructions'] == 190 and proof['work']['traps'] == {'2': 49, '5': 20} and
                proof['work']['firmware_selfchecks'] is True and proof['work']['reused_unchanged_elf'] is True,
                'Incomplete QBS contract execution')
    else:
        calls, outputs, legacy, resident = (4, 1024, 482, 12) if kind == 'perf' else (18, 2816, 713, 30)
        n, w = proof['numerical'], proof['work']
        require(n['calls'] == w['calls'] == calls and n['output_values'] == outputs and
                n['bitexact'] is n['fflags_checked'] is n['vcsr_vstart_checked'] is True and 'timing' not in n and
                n['non_rne_pair_checked'] is (kind == 'functional') and
                w['legacy_commands'] == legacy and w['resident_commands'] == resident and
                w['info_records'] == 4 * calls and w['ram_reads'] > 0 and
                w['local_flags_checked'] is w['snapshot_lifecycle_checked'] is True and
                proof['original_numerical_checker_sha256'] == c.CHECK_SHA and
                proof['original_fixture_sha256'] == c.FIXTURE_SHA and proof['target_libm_sha256'] == c.LIBM_SHA,
                'Incomplete original numerical/native work contract')


def run(out, review):
    out = output_path(out)
    require(HERE == out / 'inputs' and review == sha(out / 'source-pins.json') and
            not any((out / n).exists() for n in ('attempt.json', 'owner.json', 'result.json')),
            'Fresh reviewed frozen worker required')
    g, ownership = shared(), owner(out)
    g.save(out / 'owner.json', ownership)
    g.save(out / 'attempt.json', dict(review_sha256=review, **ownership))
    result = dict(state='FAIL', gates=[], service_owner=ownership, automatic_retry=False,
                  rtl_timing=False, performance_acceptance=False, deployment_approved=False)
    status = dict(state='PREFLIGHT', child_pid=None, **ownership)
    g.status_save(out / 'status.json', status)
    try:
        require(not any((out / 'work').iterdir()), 'Stale work; no retry')
        s, pins, g = verify_prepared(out)
        env = s['environment'] | {'INVOCATION_ID': ownership['invocation_id']}
        os.environ.clear()
        os.environ.update(env)
        for job in s['commands']:
            kind = job['kind']
            work = out / 'work' / kind
            work.mkdir()
            g.verify({s['qemu']['executable']: BINARY_SHA, job['elf']: job['elf_sha256']})
            guest = g.execute(job['guest'], work, work / 'guest.log', GUEST_SECONDS, env,
                              status, out / 'status.json', kind + '_GUEST')
            io = {str(p): sha(p) for p in (work / 'guest.log', work / 'trace.log', Path(job['elf']))}
            checker = g.execute(job['checker'], work, work / 'checked.json', CHECK_SECONDS, env,
                                status, out / 'status.json', kind + '_CHECK')
            g.verify(io)
            proof = read(work / 'checked.json')
            checked_gate(proof, kind)
            require(proof['log_sha256'] == sha(work / 'guest.log') and
                    proof['trace_sha256'] == sha(work / 'trace.log'), 'Checker log/trace mismatch')
            result['gates'].append(dict(kind=kind, state='PASS', returncode=guest['returncode'],
                guest_command=guest, checker_command=checker, checked=proof))
        verify_prepared(out)
        require(owner(out) == ownership, 'Direct service owner changed')
        result.update(state='NATIVE_QEMU_THREE_GATES_CHECKED', post_service_owner=ownership,
                      post_pins_match=True, post_image_match=True, source_pins_sha256=review,
                      qemu_build=str(BUILD), qemu_build_receipt_sha256=BUILD_SHA,
                      qemu_prepare=s['qemu']['prepared'], qemu_prepare_receipt_sha256=s['qemu']['prepare_sha256'],
                      executable=s['qemu']['executable'], executable_sha256=BINARY_SHA)
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
    result['artifacts'] = g.files(out, exclude=('status.json', 'service.stdout.log', 'service.stderr.log'))
    g.save(out / 'result.json', result)
    status.update(state=result['state'], child_pid=None)
    g.status_save(out / 'status.json', status)
    print(json.dumps(dict(state=result['state'], output=str(out))), flush=True)
    return int(result['state'] != 'NATIVE_QEMU_THREE_GATES_CHECKED')


def validate_commands(rows, s, out, ownership):
    require([r['kind'] for r in rows] == list(KINDS), 'Three actual gates required')
    previous = 0
    for row, job in zip(rows, s['commands']):
        work = out / 'work' / row['kind']
        require(row['state'] == 'PASS' and type(row['returncode']) is int and row['returncode'] == 0,
                'Unsuccessful guest')
        checked_gate(row['checked'], row['kind'])
        require(read(work / 'checked.json') == row['checked'] and
                row['checked']['log_sha256'] == sha(work / 'guest.log') and
                row['checked']['trace_sha256'] == sha(work / 'trace.log'), 'Gate evidence drift')
        for key, name, filename, seconds in (('guest', 'guest', 'guest.log', GUEST_SECONDS),
                                              ('checker', 'checked', 'checked.json', CHECK_SECONDS)):
            r = read(work / (name + '.command.json'))
            require(r == row[key + '_command'] and r['argv'] == job[key] and r['cwd'] == str(work) and
                    r['timeout_seconds'] == seconds and r['state'] == 'EXITED' and
                    type(r['returncode']) is int and r['returncode'] == 0 and r['pid'] > 1 and
                    r['started_ns'] >= previous and r['ended_ns'] > r['started_ns'] and
                    r['log_sha256'] == sha(work / filename), 'Executed command receipt differs')
            previous = r['ended_ns']
    require(ownership['unit'] == unit(out) and ownership['owner_pid'] == ownership['main_pid'] > 1 and
            re.fullmatch('[0-9a-f]{32}', ownership['invocation_id']) and
            any(x.split(':', 2)[-1].endswith('/' + unit(out)) for x in ownership['cgroup'].splitlines()),
            'Invalid direct service owner')


def checked_execution(out, digest):
    out = output_path(out)
    require(sha(out / 'result.json') == digest, 'Unreviewed execution receipt')
    report = read(out / 'result.json')
    s, pins, g = verify_prepared(out)
    require(report['state'] == 'NATIVE_QEMU_THREE_GATES_CHECKED' and
            report['post_pins_match'] is report['post_image_match'] is True and
            report['source_pins_sha256'] == sha(out / 'source-pins.json') and
            report['service_owner'] == report['post_service_owner'] == read(out / 'owner.json') and
            read(out / 'attempt.json') == dict(review_sha256=report['source_pins_sha256'], **report['service_owner']),
            'Incomplete actual execution receipt')
    expected = dict(qemu_build=str(BUILD), qemu_build_receipt_sha256=BUILD_SHA,
                    executable=s['qemu']['executable'], executable_sha256=BINARY_SHA,
                    qemu_prepare=s['qemu']['prepared'], qemu_prepare_receipt_sha256=s['qemu']['prepare_sha256'])
    require(all(report[k] == v for k, v in expected.items()), 'Execution image identity differs')
    require(g.files(out, exclude=('result.json', 'status.json', 'service.stdout.log', 'service.stderr.log')) ==
            report['artifacts'], 'Execution artifact membership/hash changed')
    validate_commands(report['gates'], s, out, report['service_owner'])
    return report, pins | report['artifacts'] | {str(out / 'result.json'): digest}


def combined(three, directed):
    require(three['state'] == 'NATIVE_QEMU_THREE_GATES_CHECKED' and
            directed['state'] == 'DIRECTED_NATIVE_AKV_CHECKED', 'All actual gates required')
    require(directed.get('rom_probe', {}).get('state') == 'PASS' and
            directed['rom_probe']['checked']['state'] == 'ROM_RAM_ONLY_FAULT_CHECKED',
            'Actual same-image ROM negative required')
    keys = ('qemu_build', 'qemu_build_receipt_sha256', 'qemu_prepare', 'qemu_prepare_receipt_sha256',
            'executable', 'executable_sha256')
    require(all(three[k] == directed[k] for k in keys) and three['executable_sha256'] == BINARY_SHA and
            three['qemu_build_receipt_sha256'] == BUILD_SHA, 'Mixed execution images')
    return {k: three[k] for k in keys}


def aggregate(out, execution, execution_sha, directed, directed_sha):
    out = output_path(out, aggregate=True)
    require(not out.exists(), 'Fresh aggregate output required')
    out.mkdir()
    g = shared()
    report = dict(state='FAIL', performance_acceptance=False, deployment_approved=False, rtl_timing=False)
    try:
        three, pins = checked_execution(execution, execution_sha)
        native, npins = g.checked_result(directed, directed_sha)
        g.merge(pins, npins)
        images = combined(three, native)
        g.merge(pins, {HERE / n: sha(HERE / n) for n in OWN})
        g.verify(pins)
        g.save(out / 'source-pins.json', pins)
        report.update(state='NATIVE_QEMU_FOUR_GATES_CHECKED', completed_gates=GATES, **images,
                      execution=str(Path(execution).resolve()), execution_result_sha256=execution_sha,
                      directed=str(Path(directed).resolve()), directed_result_sha256=directed_sha,
                      source_pins_sha256=sha(out / 'source-pins.json'), shared_reader_sha256=GATE_SHA)
    except BaseException as exc:
        report['error'] = repr(exc)
    g.save(out / 'result.json', report)
    require(report['state'] == 'NATIVE_QEMU_FOUR_GATES_CHECKED', 'Aggregate failed; preserve output')
    return report


def checked_result(out, reviewed_result_sha256):
    """Read-only four-gate admission; replays receipts, never re-executes guests."""
    out = output_path(out, aggregate=True)
    require(sha(out / 'result.json') == reviewed_result_sha256, 'Unreviewed four-gate receipt')
    report = read(out / 'result.json')
    require(report['state'] == 'NATIVE_QEMU_FOUR_GATES_CHECKED' and report['completed_gates'] == GATES and
            report['shared_reader_sha256'] == GATE_SHA and report['performance_acceptance'] is False and
            report['deployment_approved'] is False and report['rtl_timing'] is False and
            sha(out / 'source-pins.json') == report['source_pins_sha256'], 'Incomplete aggregate')
    three, pins = checked_execution(report['execution'], report['execution_result_sha256'])
    g = shared()
    directed, dpins = g.checked_result(report['directed'], report['directed_result_sha256'])
    g.merge(pins, dpins)
    require(all(report[k] == v for k, v in combined(three, directed).items()), 'Aggregate image identity differs')
    g.merge(pins, {HERE / n: sha(HERE / n) for n in OWN})
    require(read(out / 'source-pins.json') == pins, 'Aggregate dependency closure differs')
    g.verify(pins)
    require(set(p.name for p in out.iterdir()) == {'result.json', 'source-pins.json'}, 'Aggregate membership drift')
    return report, pins | {str(out / 'result.json'): reviewed_result_sha256,
                           str(out / 'source-pins.json'): report['source_pins_sha256']}


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = p.add_subparsers(dest='action', required=True)
    for action in ('prepare', 'service-command', 'run', 'aggregate'):
        a = sub.add_parser(action)
        a.add_argument('--output', type=Path, required=True)
        if action in ('service-command', 'run'):
            a.add_argument('--review-sha256', required=True)
        if action == 'aggregate':
            for key in ('execution', 'directed'):
                a.add_argument('--' + key, type=Path, required=True)
                a.add_argument('--' + key + '-sha256', required=True)
    a = p.parse_args()
    if a.action == 'prepare':
        print(json.dumps(prepare(a.output), indent=2))
    elif a.action == 'aggregate':
        print(json.dumps(aggregate(a.output, a.execution, a.execution_sha256, a.directed, a.directed_sha256), indent=2))
    elif a.action == 'service-command':
        s, _, _ = verify_prepared(a.output)
        require(a.review_sha256 == sha(a.output / 'source-pins.json') and
                not any((a.output / n).exists() for n in ('attempt.json', 'result.json')), 'Existing attempt/wrong review')
        print(shlex.join(service_argv(a.output, s, a.review_sha256)))
    else:
        return run(a.output, a.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig, frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    raise SystemExit(main())
