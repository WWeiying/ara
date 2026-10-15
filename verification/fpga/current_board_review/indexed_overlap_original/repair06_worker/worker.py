#!/usr/bin/env python3
"""Prepare, or explicitly authorized no-build run. Never invokes systemd-run itself."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OWNER = HERE.parent
sys.path.insert(0, str(HERE))
import checker
spec = importlib.util.spec_from_file_location('indexed_m6_shared', OWNER.parent / 'gather_repair05/regression.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
require, read = common.require, common.read
NAMES = ('d32m2_i64_fault_ov1', 'd32m2_i64_resident_ov1', 'd32m2_i64_fault_ov0')
STAGES = (('pilot', 1, NAMES[:1]), ('controls', 2, NAMES[1:]))
SERVICE_SECONDS = 9600
WORKER_SECONDS = 8800
BAD = re.compile(common.BAD.pattern + r'|\b(?:VECTOR_FAIL|INDEXED_ORIGINAL_FAIL|ABORT(?:ED)?|MISMATCH)\b', re.I)
DEBUG = '+ARA_DEBUG_SOURCE_SNAPSHOT'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
BASELINE = OWNER / 'vcs_candidate05_plan01'


def sha(path):
    return common.sha(Path(path))


def save(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def owned(path):
    path = path.resolve()
    require(path.parent == HERE and not path.is_symlink(), 'Output must be fresh direct owned child')
    return path


def marker(case):
    return ('VECTOR_PASS loops=50 overlap=%d data_bits=32 index_bits=64 fault_pages=' % case['overlap'] +
            ('1 minor_faults=1600' if case['fault'] else '0 mask_tail_vstart=checked'))


def console(case, text):
    require(not BAD.search(text), 'Raw failure veto')
    require(text.count(marker(case)) == 1 and text.count('VECTOR_PASS') == 1 and
            text.count('INDEXED_ORIGINAL_PASS') == 1, 'Missing/duplicate full original oracle')
    require(text.count(common.SUCCESS) == 1 and '$finish' in text, 'Missing normal CTRL0 simulator exit')


def reference_scope(reference):
    require(reference == OWNER / 'reference03', 'Only final reference03; never reference02')
    handoff = read(OWNER / 'REFERENCE_HANDOFF.json')
    require(read(reference / 'status.json') == handoff['status'] and
            handoff['status']['status'] == 'THREE_HOST_SPIKE_REFERENCES_PASS_NOT_DUT' and
            handoff['status']['cases'] == list(NAMES), 'Final reference status/membership')
    pins = dict(handoff['artifact_pins'])
    pins.update(read(reference / 'pins.json'))
    common.base.verify_pins(pins)
    identities = read(reference / 'identities.json')
    require([e['name'] for e in identities] == list(NAMES), 'Original identities membership')
    cases = []
    for identity in identities:
        name, meta = identity['name'], identity['metadata']
        work = reference / name
        status = read(work / 'status.json')
        require(identity['byte_identical'] is True and sha(work / 'original.elf') == meta['sha256'] ==
                status['original_elf_sha256'], 'Archive byte identity')
        require(status['status'] == 'HOST_SPIKE_PASS_NOT_DUT' and status['original_helper_instructions'] == 41,
                'Reference helper/oracle status')
        require(sha(work / 'soc.elf') == status['soc_elf_sha256'] and
                sha(work / 'spike.elf') == status['spike_elf_sha256'], 'Reference ELF identity')
        require(len(status['points']) == (50 if meta['fault'] else 51) and
                status['checks'] == (21595 if meta['fault'] else 5215), 'Reference full scope')
        symbols = read(work / 'soc.symbols.json')
        require('tohost' not in symbols and symbols['_start'] == 0x80000000 and
                symbols['__bss_end'] < 0x800e0000, 'Wrong ELF backend/address map')
        ops = checker.instructions((work / 'soc.dis').read_text())
        cc = Path(read(work / 'soc.compile.log.command.json')[0])
        for tool_name in ('nm', 'objdump', 'readelf'):
            tool = cc.with_name('riscv64-unknown-elf-' + tool_name)
            pins[str(tool)] = sha(tool)
        nm = subprocess.check_output([str(cc.with_name('riscv64-unknown-elf-nm')), '-n', str(work / 'soc.elf')],
                                     text=True, timeout=30)
        actual = {m[3]: int(m[1], 16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$', nm, re.M)}
        require(actual == symbols, 'nm map differs from actual ELF')
        objdump = cc.with_name('riscv64-unknown-elf-objdump')
        real_dis = subprocess.check_output([str(objdump), '-d', str(work / 'soc.elf')], text=True, timeout=30)
        require(checker.instructions(real_dis) == ops, 'Disassembly differs from actual ELF')
        original = checker.instructions(subprocess.check_output([str(objdump), '-d', str(work / 'original.elf')],
                                                                text=True, timeout=30))
        old = list(original.values())
        start = next(i for i in range(len(old) - 1) if old[i:i + 2] == [0x02000293, 0x0da2f357])
        require(old[start:] == [v for p, v in ops.items() if p >= symbols['gather32']][:41] and
                len(old[start:]) == 41, 'Original complete 41 helper encodings differ')
        readelf = cc.with_name('riscv64-unknown-elf-readelf')
        header = subprocess.check_output([str(readelf), '-h', str(work / 'soc.elf')], text=True, timeout=30)
        layout = subprocess.check_output([str(readelf), '-Wl', str(work / 'soc.elf')], text=True, timeout=30)
        require('ELF64' in header and 'RISC-V' in header and '0x80000000' in header, 'Wrong ELF ABI/entry')
        loads = re.findall(r'^\s*LOAD\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)', layout, re.M)
        require(loads and all(int(v, 16) == int(p, 16) and 0x80000000 <= int(p, 16) and
                             int(p, 16) + int(n, 16) <= 0x80200000 for v, p, n in loads), 'ELF exceeds M6 L2')
        checker.Checker(symbols, ops, meta['fault'], meta['overlap'])
        case = dict(id=name, original_name=name, elf=str(work / 'soc.elf'),
                    sha256=status['soc_elf_sha256'], fault=meta['fault'], overlap=meta['overlap'],
                    original_sha256=meta['sha256'], timeout_s=4200 if meta['fault'] else 2400,
                    spike_retired=status['commits'], checks=status['checks'], rounds=50,
                    pass_markers=[marker(meta), 'INDEXED_ORIGINAL_PASS', common.SUCCESS])
        cases.append(case)
    require([c['id'] for c in cases] == list(NAMES) and
            all(c['original_name'] == c['id'] == Path(c['elf']).parent.name for c in cases),
            'Exact source case membership before publishing plan')
    # Includes raw Host/Spike traces, commands, source copies, disassembly and ELF maps.
    for path in reference.rglob('*'):
        if path.is_file():
            pins[str(path)] = sha(path)
    for name in ('REFERENCE_HANDOFF.json', 'REFERENCE_REPORT.md', 'VCS_CHECKER_BOUNDARY.md'):
        path = OWNER / name
        pins[str(path)] = sha(path)
    return cases, pins


def bus_environment():
    runtime = Path('/run/user') / str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid == os.getuid() and
            (runtime / 'bus').is_socket(), 'Trusted user bus unavailable')
    return dict(common.base.shared.environment(), XDG_RUNTIME_DIR=str(runtime),
                DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(runtime / 'bus'))


def service_owner(unit):
    require(re.fullmatch(r'ara-indexed-overlap-m6-[a-z0-9-]+\.service', unit) is not None, 'Unit namespace')
    fields = ['Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlGroup']
    proc = subprocess.run(['systemctl', '--user', 'show', unit, '--property=' + ','.join(fields)],
                          capture_output=True, text=True, env=bus_environment(), timeout=15)
    require(proc.returncode == 0 and not proc.stderr.strip(), 'User manager query failed')
    props = dict(line.split('=', 1) for line in proc.stdout.splitlines())
    require(set(props) == set(fields) and props['Id'] == unit and props['LoadState'] == 'loaded' and
            props['ActiveState'] == 'active' and props['SubState'] == 'running' and
            props['MainPID'] == str(os.getpid()), 'Worker is not direct service MainPID')
    cgroup = next(x.split(':', 2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
    require(cgroup == props['ControlGroup'] and cgroup.endswith('/' + unit), 'Wrong owned cgroup')
    return props


def profile_sources(repo):
    text = (HERE / 'capture.tcl').read_text()
    mapping = {'$ara.i_dispatcher.$p': 'ara_dispatcher.sv',
               '$ara.i_vlsu.i_addrgen.$p': 'vlsu/addrgen.sv',
               '$ara.i_vlsu.i_vldu.$p': 'vlsu/vldu.sv',
               '$ara.i_sequencer.$p': 'ara_sequencer.sv',
               '$lane.$p': 'lane/lane.sv',
               '$lane.i_operand_requester.$p': 'lane/operand_requester.sv'}
    groups = re.findall(r'foreach p \{([^}]+)\} \{\s*dump -add ([^ ]+) ', text)
    require(len(groups) == 6, 'Profile scope drift')
    for tokens, prefix in groups:
        source = (repo / 'hardware/src' / mapping[prefix]).read_text()
        for token in tokens.split():
            require(re.search(r'\b' + token + r'\b', source), 'Missing frozen capture signal: ' + token)
    require('run -absolute 1000000ns' in text and 'dump -add /' not in text,
            'Capture duration/scope drift')


def image_context(image):
    require(image == IMAGE and not image.is_symlink(), 'Only exact candidate06 image')
    ledger, repo, framework = common.image_context(image)
    require(Path(ledger['snapshot']).parent.name == 'current_board_memory_candidate06',
            'Not candidate06 frozen inputs')
    profile_sources(repo)
    return ledger, repo, framework


def prepare(image, reference, out, reserve):
    require(not out.exists() and 0 <= reserve <= 24, 'Fresh plan and explicit unused reservations required')
    host = read(HERE / 'host_successor_final.json')
    require(host['status'] == 'HOST_PASS_NOT_DUT' and host['VCS_launched'] is False, 'Final host tests required')
    common.base.verify_pins(host['pins'])
    cases, pins = reference_scope(reference)
    pins.update(host['pins'])
    pins[str(HERE / 'host_successor_final.json')] = sha(HERE / 'host_successor_final.json')
    ledger, repo, _ = image_context(image)
    require(sha(HERE / 'checker.py') == sha(BASELINE / 'checker.py') and
            sha(HERE / 'test_host.py') == sha(BASELINE / 'test_host.py'), 'Sealed checker/test copy drift')
    pins.update(common.image_pins(image, ledger, repo))
    for p in (Path(__file__), HERE / 'checker.py', HERE / 'test_host.py', HERE / 'test_successor.py', BASELINE / 'worker_successor.py', BASELINE / 'checker.py', BASELINE / 'test_host.py', HERE / 'README.md', HERE / 'capture.tcl',
              Path(common.__file__), Path(common.base.__file__), Path(common.base.shared.__file__),
              OWNER.parent / 'integration/prepare.py', checker.ROOT / 'verification/coverage/scoped_rv64c_memory.py'):
        pins[str(p.resolve())] = sha(p)
    common.base.verify_pins(pins)
    resource_snapshot = common.resources(out, 2, reserve)
    out.mkdir()
    plan = dict(status='PREPARED_NOT_RUN', reference=str(reference), image=str(image),
                image_sha256=sha(image / 'image.json'), snapshot_sha256=ledger['snapshot_sha256'],
                cases=cases, stages=[dict(name=n, jobs=j, cases=list(cs)) for n, j, cs in STAGES],
                pins=pins, unused_external_reservations=reserve, service_seconds=SERVICE_SECONDS,
                worker_deadline_s=WORKER_SECONDS, pilot_capture=str(HERE / 'capture.tcl'),
                preparation_resources=resource_snapshot,
                no_build=True, retries=0, stop_first_fail=True, debug_plusarg=DEBUG,
                budget_basis='1595309/723=2206.5s fault;840319/723=1162.3s resident; bounds4200/2400; '
                             'two phases max8400; shared8800 worker deadline leaves800 service headroom; '
                             'deadline overrides per-case budget, no retry/partial acceptance', created=time.time())
    save(out / 'plan.json', plan)
    # No launch is performed, and this is deliberately not a shell wrapper service.
    cmd = ['systemd-run', '--user', '--unit=ara-indexed-overlap-m6-01.service',
           '--property=Type=exec', '--property=RuntimeMaxSec=9600', '--property=TimeoutStopSec=60',
           '--property=KillMode=control-group', '--property=Restart=no',
           '--property=StandardOutput=append:' + str(out / 'service.log'),
           '--property=StandardError=append:' + str(out / 'service.log'), '/usr/bin/python3', '-B', str(Path(__file__).resolve()),
           'run', '--out', str(out), '--image', str(image), '--plan-sha256', sha(out / 'plan.json'),
           '--unit', 'ara-indexed-overlap-m6-01.service', '--authorize-run']
    save(out / 'service_command.NOT_EXECUTED.json', cmd)
    print(json.dumps(dict(status='PREPARED_NOT_RUN', plan=str(out / 'plan.json'), sha256=sha(out / 'plan.json'))))


def validate_plan(plan, image):
    require(image == IMAGE and plan['reference'] == str(OWNER / 'reference03') and
            plan['pilot_capture'] == str(HERE / 'capture.tcl'), 'M6/reference/profile selection drift')
    require(plan['status'] == 'PREPARED_NOT_RUN' and plan['image'] == str(image) and
            sha(image / 'image.json') == plan['image_sha256'], 'Plan/image identity')
    require(plan['no_build'] is True and plan['retries'] == 0 and plan['stop_first_fail'] is True and
            plan['service_seconds'] == SERVICE_SECONDS and plan['worker_deadline_s'] == WORKER_SECONDS and
            plan['debug_plusarg'] == DEBUG and
            plan['stages'] == [dict(name=n, jobs=j, cases=list(cs)) for n, j, cs in STAGES], 'Execution contract drift')
    common.base.verify_pins(plan['pins'])
    require(plan['pins'][str(Path(__file__).resolve())] == sha(Path(__file__)), 'Worker drift')
    require([c['id'] for c in plan['cases']] == list(NAMES), 'Exact three cases required')
    for c in plan['cases']:
        identity = next(x for x in read(OWNER / 'reference03/identities.json') if x['name'] == c['id'])
        meta = identity['metadata']
        require(c['original_name'] == c['id'] and
                c['elf'] == str(OWNER / 'reference03' / c['id'] / 'soc.elf') and
                c['fault'] == meta['fault'] and c['overlap'] == meta['overlap'] and
                c['original_sha256'] == meta['sha256'] and
                c['checks'] == (21595 if meta['fault'] else 5215) and
                c['pass_markers'] == [marker(meta), 'INDEXED_ORIGINAL_PASS', common.SUCCESS],
                'Original case/oracle selection drift')
        require(c['sha256'] == sha(c['elf']) and c['rounds'] == 50 and
                c['timeout_s'] == (4200 if c['fault'] else 2400), 'ELF/scope/budget drift')


def artifacts(result, case, ledger, reference, abort):
    root = result.artifact_dir
    require(result.returncode == 0 and 0 <= result.elapsed_s <= case['timeout_s'], 'Process exit/budget')
    console(case, (root / 'console.log').read_text())
    console(case, (root / 'work/run.vcs.log').read_text())
    require(sha(root / 'input.elf') == case['sha256'], 'Private ELF changed')
    require(read(root / 'inputs.json') == dict(
        binary=dict(source=case['elf'], path=str(root / 'input.elf'), sha256=case['sha256']),
        simv=dict(path=ledger['simv'], image_sha256=ledger['files'])), 'Execution input/image provenance')
    expected = [ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
                '+PRELOAD=' + str(root / 'input.elf'), '+TESTCASE=' + case['original_name'],
                '+NO_FSDB', '+COMMIT_TRACE=' + str(root / 'commit_trace.csv'), DEBUG]
    if case['id'] == NAMES[0]:
        expected += ['-ucli', '-do', str(HERE / 'capture.tcl')]
    require(read(root / 'command.json') == dict(command=expected, cwd=str(root / 'work')), 'Actual command differs')
    require(read(root / 'trace_summary.json')['status'] == 'VALID', 'Generic RVFI/CVX trace checker failed')
    analysis = checker.analyze(root / 'commit_trace.csv', reference / case['id'], case, abort)
    save(root / 'indexed_analysis.json', analysis)
    require(analysis['status'] == 'CSV_FULL_ORACLE_PASS', 'Indexed CSV oracle: ' + analysis.get('error', ''))
    if case['id'] == NAMES[0]:
        require((root / 'work/indexed_first_round.fsdb').stat().st_size > 1024 and
                'INDEXED_PROFILE_CLOSED_AT_1000000NS' in (root / 'console.log').read_text() and
                analysis['points'][0]['cycle'] < 950000, 'Bounded profile incomplete for first round; no automatic retry')
    require(not abort.is_set(), 'Cancelled during expensive checker')


def checked_runner(parent, cases, ledger, reference, abort, admit):
    class Runner(parent):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.cancel_event = abort

        def _run_test(self, test, image):
            try:
                if not abort.is_set():
                    admit(test.name)
                result = super()._run_test(test, image)
                if result.status == 'PASS':
                    artifacts(result, cases[test.name], ledger, reference, abort)
                if abort.is_set():
                    result.status, result.reason = 'CANCELLED', 'Sticky abort during simulation/checking'
                if result.status != 'PASS':
                    abort.set()
                return result
            except BaseException:
                abort.set()
                raise
    return Runner


class TerminalAbort(threading.Event):
    def __init__(self):
        super().__init__()
        self.lock = threading.RLock()
        self.closed = False

    def set(self):
        with self.lock:
            if not self.closed:
                super().set()


def publish_terminal(out, terminal, abort, expires):
    signals = {signal.SIGINT, signal.SIGTERM}
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
    temporary = out / 'complete.pending.json'
    try:
        require(not (out / 'complete.json').exists(), 'No terminal overwrite')
        terminal['aborted'] = abort.is_set()
        save(temporary, terminal)
        # The final decision and timer latch are mutually exclusive. Slow JSON
        # writing precedes the decision; a delayed timer cannot hide expiry.
        with abort.lock:
            if abort.is_set() or signal.sigpending() & signals or time.monotonic() >= expires:
                abort.set()
                terminal.update(status='NOT_PASS', aborted=True)
                with temporary.open('w') as stream:
                    json.dump(terminal, stream, indent=2)
                    stream.write('\n')
            os.replace(temporary, out / 'complete.json')
            abort.closed = True
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def run(image, out, digest, unit, authorized):
    require(authorized and digest == sha(out / 'plan.json'), 'Parent explicit --authorize-run + pinned plan required')
    require(not (out / 'launch.json').exists(), 'No retry/overwriting prior launch')
    plan = read(out / 'plan.json')
    validate_plan(plan, image)
    ledger, repo, (parent, options_type, testcase, _) = image_context(image)
    require(ledger['snapshot_sha256'] == plan['snapshot_sha256'], 'Snapshot identity drift')
    owner = service_owner(unit)
    reserve = plan['unused_external_reservations']
    admission = common.resources(out, 1, reserve)
    save(out / 'launch.json', dict(pid=os.getpid(), started=time.time(), service=owner,
                                  resources=admission, plan_sha256=digest))
    abort = TerminalAbort()
    terminal = dict(status='NOT_PASS', results=[], plan_sha256=digest, image_sha256=plan['image_sha256'])
    import ara_verify.runner as engine
    old_fail, old_monitor = engine.FAIL_RE, engine._run_monitored
    engine.FAIL_RE = re.compile(old_fail.pattern + '|' + BAD.pattern, old_fail.flags)

    def monitor(command, cwd, log, timeout, cancel):
        command = list(command) + [DEBUG]
        if '+TESTCASE=' + NAMES[0] in command:
            command += ['-ucli', '-do', str(HERE / 'capture.tcl')]
        # Record the actual extended invocation, not the frozen runner's template.
        common.save(Path(cwd).parent / 'command.json', dict(command=command, cwd=str(cwd)))
        return old_monitor(command, cwd, log, timeout, cancel)

    engine._run_monitored = monitor
    started = time.monotonic()
    deadline = threading.Timer(WORKER_SECONDS, abort.set)
    deadline.daemon = True
    deadline.start()
    with common.abort_signals(abort):
        try:
            (out / 'admission').mkdir()
            for stage, jobs, names in STAGES:
                require(not abort.is_set() and time.monotonic() - started < WORKER_SECONDS,
                        'Next stage NOT_RUN: aborted/shared deadline reached')
                validate_plan(plan, image)
                entries = {c['id']: c for c in plan['cases'] if c['id'] in names}
                stage_out = out / stage
                require(not stage_out.exists(), 'No stage retries')

                def admit(name):
                    require(not abort.is_set() and time.monotonic() - started < WORKER_SECONDS and
                            sha(entries[name]['elf']) == entries[name]['sha256'], 'NOT_RUN: abort/deadline/ELF drift')
                    save(out / 'admission' / (name + '.json'), common.resources(out, jobs, reserve))

                options = options_type(repo, stage_out, 'default', jobs, 1, False, False, True,
                                       Path(ledger['simv']), True, None)
                tests = [testcase(c['id'], 'app', '', Path(c['elf']), c['original_name'], c['timeout_s'])
                         for c in entries.values()]
                runner = checked_runner(parent, entries, ledger, Path(plan['reference']), abort, admit)(options, tests, sys.argv)
                results = runner.run()
                serialized = [dict(asdict(r), artifact_dir=str(r.artifact_dir)) for r in results]
                terminal['results'].extend(serialized)
                common.check_stage(results, read(stage_out / 'run.json'), list(entries.values()), abort)
                require(read(stage_out / 'summary.json') == serialized, 'Raw stage summary differs')
            validate_plan(plan, image)
            image_context(image)
            evidence = {}
            for stage, _, names in STAGES:
                for name in names:
                    root = out / stage / 'tests' / name
                    for filename in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log',
                                     'commit_trace.csv', 'trace_summary.json', 'indexed_analysis.json'):
                        evidence[str(root / filename)] = sha(root / filename)
                    if name == NAMES[0]:
                        evidence[str(root / 'work/indexed_first_round.fsdb')] = sha(root / 'work/indexed_first_round.fsdb')
                for filename in ('run.json', 'summary.json'):
                    evidence[str(out / stage / filename)] = sha(out / stage / filename)
            require(time.monotonic() - started < WORKER_SECONDS and not abort.is_set(), 'Shared deadline/abort veto')
            terminal.update(status='PASS_3_REFERENCE03_FULL50_M6', pins_unchanged=True, evidence_pins=evidence,
                            scope='Three source-faithful Sv39 fixtures; not original Linux fault scheduling closure')
        except BaseException as error:
            abort.set()
            terminal.update(status='NOT_PASS', error=f'{type(error).__name__}: {error}')
        finally:
            engine.FAIL_RE, engine._run_monitored = old_fail, old_monitor
            terminal.update(elapsed_s=time.monotonic() - started, finished=time.time())
            try:
                publish_terminal(out, terminal, abort, started + WORKER_SECONDS)
            finally:
                deadline.cancel()
                deadline.join()
    print(terminal['status'], flush=True)
    return int(terminal['status'] != 'PASS_3_REFERENCE03_FULL50_M6')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run'))
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--reference', type=Path, default=OWNER / 'reference03')
    p.add_argument('--unused-reserved-slots', type=int, default=0)
    p.add_argument('--plan-sha256')
    p.add_argument('--unit')
    p.add_argument('--authorize-run', action='store_true')
    a = p.parse_args()
    image, out = a.image.resolve(), owned(a.out)
    env = common.base.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    if a.mode == 'prepare':
        prepare(image, a.reference.resolve(), out, a.unused_reserved_slots)
        return 0
    return run(image, out, a.plan_sha256, a.unit, a.authorize_run)


if __name__ == '__main__':
    raise SystemExit(main())
