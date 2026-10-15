#!/usr/bin/env python3
"""Reuse a built image: exact original38/jobs4, then ten smoke ELFs/jobs2.

No build, snapshot, service launch or retry exists in this script.
  regression.py prepare --image IMAGE --out NEW_DIR --reserved-slots N --authorize-prepare
  regression.py run --image IMAGE --out NEW_DIR --plan-sha256 SHA --authorize-run
N is the parent's unused external reservation, in addition to live simulators.
Use one independent service (suggested outer cap 9000s); case bounds are unchanged.
Cycle-only differences are reported for review, never called performance equivalence.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
import csv
from dataclasses import asdict
from itertools import zip_longest
import json
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "integration"))
import replay_memory_regression as base

INVENTORY = HERE / "preparation01.json"
INVENTORY_SHA = "2838de37c858c9b18bc6ca6a1a6cd3b59ca53cf48cc8373b3fd3003835542dcf"
CONFIGURATION_SHA = "6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785"
SUCCESS = "Core Test *** SUCCESS *** (tohost = 0)"
BAD = re.compile(r"\bRVV_[A-Z0-9_]*FAIL\b|BOARD_CASE_FAIL|"
                 r"BOARD_REPLAY_(?:TRAP|MISMATCH|SERVICE_FAIL|VLEN_FAIL)|"
                 r"\b(?:MATRIX_FAIL|EXTENSION_MATRIX_FAIL|EXTENDED_FAIL|EPOCH_FAIL)\b|"
                 r"Core Test \*\*\* FAIL|\bFAILED\b|Error-\[|Fatal[-:]|"
                 r"\bUVM_FATAL\b(?![ \t]*:[ \t]*0\b)|\bSKIP\b", re.IGNORECASE)
ORACLE_LINE = re.compile(r"Checking the results of the test case .*|PASSED\..*|PASSED:.*|.*smoke.*: PASS.*")
STAGES = (("original38", 4), ("smokes10", 2))
require, read, save, sha = base.require, base.read, base.save, base.sha


def oracle_lines(text):
    return [line.strip() for line in text.splitlines() if ORACLE_LINE.fullmatch(line.strip())]


def original_scope():
    require(sha(INVENTORY) == INVENTORY_SHA, "Original inventory drift")
    inventory = read(INVENTORY)
    cases = []
    for entry in inventory["regression38"]:
        case = {k: v for k, v in entry.items() if k != "m4_elapsed_s"}
        case["stage"] = "original38"
        cases.append(case)
    controls = []
    for entry in inventory["performance_controls16"]:
        case_id = entry["reuse_regression38_case"]
        if entry["stage"] == "smokes":
            case_id = "smoke__" + entry["id"]
            log = Path(entry["baseline_artifacts"]) / "console.log"
            require(sha(log) == inventory["reference_pins"][str(log)], "Baseline oracle drift")
            text = log.read_text()
            lines = oracle_lines(text)
            require(lines and SUCCESS in text and not BAD.search(text), "Baseline smoke oracle missing")
            cases.append(dict(id=case_id, original_name=entry["id"], stage="smokes10",
                              group="smoke", elf=entry["elf"], sha256=entry["sha256"],
                              timeout_s=entry["timeout_s"], pass_markers=[SUCCESS], oracle_lines=lines))
        controls.append(dict(id=case_id, name=entry["id"],
                             baseline_csv=str(Path(entry["baseline_artifacts"]) / "commit_trace.csv")))
        require(next(c for c in cases if c["id"] == case_id)["sha256"] == entry["sha256"],
                "Control not identical to reused ELF")
    require(len(cases) == len({c['id'] for c in cases}) == len({c['sha256'] for c in cases}) == 48,
            "Exact48 unique programs required")
    require(Counter(c['group'] for c in cases if c['stage'] == 'original38') == base.GROUPS,
            "Wrong original38 membership")
    require(len(controls) == 16 and sum(c['stage'] == 'smokes10' for c in cases) == 10,
            "Wrong control membership")
    require(all(c['pass_markers'] and c['timeout_s'] > 0 for c in cases), "Missing oracle/budget")
    return cases, controls, dict(inventory["reference_pins"])


def image_context(image):
    base.IMAGE = image.resolve()
    ledger, repo, framework = base.image_context()
    require(Path(ledger['simv']).is_file() and os.access(ledger['simv'], os.X_OK), "No executable simv")
    require(ledger['configuration_sha256'] == CONFIGURATION_SHA, "Image settings differ from M4")
    return ledger, repo, framework


def image_pins(image, ledger, repo):
    snapshot = Path(ledger['snapshot'])
    pins = dict(ledger['files'])
    pins.update({str(repo / p): h for p, h in read(snapshot / 'snapshot.json')['files'].items()})
    for path in (image / 'image.json', snapshot / 'snapshot.json',
                 Path(ledger['simv']).parent / 'simulator.conf',
                 Path(ledger['simv']).parent / 'vcs_source_manifest.json'):
        pins[str(path)] = sha(path)
    return pins


def resource_math(live, available, out, jobs, reserved):
    require(type(reserved) is int and 0 <= reserved <= 24, "Invalid unused reservation")
    own_prefix = '+COMMIT_TRACE=' + str(out.resolve()) + '/'
    external = [p for p in live if not any(a.startswith(own_prefix) for a in p['argv'])]
    total = len(external) + jobs + reserved
    require(total <= 24 and available >= 32 * 1024**3, "Resource cap/memory floor; no retry")
    return dict(time=time.time(), live=live, external=len(external), jobs=jobs,
                unused_external_reservation=reserved, total=total, available_bytes=available)


def is_simv(comm, argv):
    return comm == 'simv' or bool(argv and Path(argv[0]).name == 'simv')


def resources(out, jobs, reserved):
    live = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / 'comm').read_text().strip()
            argv = (proc / 'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            if is_simv(comm, argv):
                live.append(dict(pid=int(proc.name), comm=comm, argv=argv))
        except (FileNotFoundError, ProcessLookupError):
            continue
    available = int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines()
                         if s.startswith('MemAvailable:'))) * 1024
    return resource_math(live, available, out, jobs, reserved)


def prepare(image, out, reserved, authorized):
    require(authorized, "--authorize-prepare required (no DUT)")
    require(not out.exists(), "Output already exists; no overwrite")
    cases, controls, pins = original_scope()
    base.verify_pins(pins)
    ledger, repo, _ = image_context(image)
    pins.update(image_pins(image, ledger, repo))
    for path in (Path(__file__).resolve(), INVENTORY, Path(base.__file__),
                 Path(base.shared.__file__), HERE.parent / 'integration/prepare.py'):
        pins[str(path)] = sha(path)
    for case in cases:
        require(sha(Path(case['elf'])) == case['sha256'], 'ELF drift: ' + case['id'])
        pins[case['elf']] = case['sha256']
    out.mkdir(parents=True, exist_ok=False)
    data = dict(status='PREPARED_NOT_RUN', image=str(image), image_sha256=sha(image / 'image.json'),
                snapshot_sha256=ledger['snapshot_sha256'], cases=cases, controls=controls, pins=pins,
                stages=[dict(name=n, jobs=j) for n, j in STAGES], reserved_slots=reserved,
                no_build=True, stop_first_fail=True, created=time.time())
    save(out / 'plan.json', data)
    base.verify_pins(pins)
    print('PREPARED_NOT_RUN plan_sha256=' + sha(out / 'plan.json'), flush=True)


def validate_plan(data, image):
    cases, controls, _ = original_scope()
    require(data['image'] == str(image) and sha(image / 'image.json') == data['image_sha256'], 'Image drift')
    require(data['cases'] == cases and data['controls'] == controls, 'Scope/oracle/budget drift')
    require(data['no_build'] is True and data['stop_first_fail'] is True and
            data['stages'] == [dict(name=n, jobs=j) for n, j in STAGES], 'Run contract drift')
    require(data['pins'].get(str(Path(__file__).resolve())) == sha(Path(__file__)), 'Checker drift')
    base.verify_pins(data['pins'])
    for c in cases:
        require(sha(Path(c['elf'])) == c['sha256'], 'ELF drift: ' + c['id'])


def check_console(case, text):
    require(SUCCESS in text and '$finish' in text and not BAD.search(text), 'Raw failure/incomplete exit')
    require(base.shared.oracle_complete(case, text), 'Missing original oracle')
    if 'oracle_lines' in case:
        require(oracle_lines(text) == case['oracle_lines'], 'Incomplete/reordered smoke subcase oracle')


def compare_cycles(old, new, output):
    """Compare all events in order, writing every cycle-only difference."""
    rows = changed = 0
    with old.open(newline='') as left, new.open(newline='') as right, output.open('x', newline='') as dest:
        a, b = csv.DictReader(left), csv.DictReader(right)
        require(a.fieldnames == b.fieldnames and 'cycle' in (a.fieldnames or []), 'CSV schema mismatch')
        writer = csv.writer(dest)
        writer.writerow(['row', 'event', 'order', 'baseline_cycle', 'current_cycle', 'delta'])
        for x, y in zip_longest(a, b):
            rows += 1
            require(x is not None and y is not None, 'CSV event count mismatch')
            ac, bc = int(x.pop('cycle')), int(y.pop('cycle'))
            require(x == y, f'Noncycle event mismatch at CSV row {rows}')
            if ac != bc:
                changed += 1
                writer.writerow([rows, x['event'], x['order'], ac, bc, bc-ac])
        require(rows > 0, 'Empty performance CSV')
    return dict(rows=rows, cycle_changed_rows=changed, noncycle_equal=True,
                last_cycle_delta=bc-ac, differences=str(output))


def check_artifacts(result, case, ledger):
    require(result.returncode == 0 and 0 <= result.elapsed_s <= case['timeout_s'], 'Exit/budget violation')
    root = result.artifact_dir
    check_console(case, (root / 'console.log').read_text())
    require(not BAD.search((root / 'work/run.vcs.log').read_text()), 'Raw VCS log failure')
    require(sha(root / 'input.elf') == case['sha256'], 'Private ELF drift')
    inputs = read(root / 'inputs.json')
    require(inputs['binary']['sha256'] == case['sha256'] and
            inputs['binary']['source'] == case['elf'] and
            inputs['binary']['path'] == str(root / 'input.elf'), 'Private ELF provenance mismatch')
    require(inputs['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files']), 'Image provenance drift')
    command = read(root / 'command.json')
    require(command['cwd'] == str(root / 'work') and command['command'] == [
        ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
        '+PRELOAD=' + str(root / 'input.elf'), '+TESTCASE=' + case['original_name'],
        '+NO_FSDB', '+COMMIT_TRACE=' + str(root / 'commit_trace.csv')], 'Command provenance mismatch')
    require((root / 'commit_trace.csv').stat().st_size > 0 and
            read(root / 'trace_summary.json').get('status') == 'VALID', 'Missing/invalid complete trace')


def checked_runner(parent, entries, ledger, abort, admission, controls):
    class Runner(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cancel_event = abort

        def _run_test(self, test, image):
            try:
                if not abort.is_set():
                    admission(test.name)
                result = super()._run_test(test, image)
                if result.status == 'PASS':
                    check_artifacts(result, entries[test.name], ledger)
                    if test.name in controls:
                        finding = compare_cycles(Path(controls[test.name]['baseline_csv']),
                            result.artifact_dir / 'commit_trace.csv', result.artifact_dir / 'cycle_differences.csv')
                        save(result.artifact_dir / 'performance.json', finding)
                    if abort.is_set():
                        result.status, result.reason = 'CANCELLED', 'Abort during validation'
                if result.status != 'PASS':
                    abort.set()
                return result
            except BaseException:
                abort.set()
                raise
    return Runner


def check_stage(results, metadata, cases, abort):
    names = {c['id'] for c in cases}
    require(not abort.is_set(), 'Sticky abort')
    require(metadata['status'] == 'COMPLETE' and metadata['status_counts'] == {'PASS': len(cases)},
            'Runner not COMPLETE/PASS')
    require(len(results) == len(names) and {r.name for r in results} == names and
            all(r.status == 'PASS' and r.returncode == 0 for r in results), 'Incomplete stage membership')


@contextmanager
def abort_signals(abort):
    previous = {s: signal.signal(s, lambda *_: abort.set()) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def publish(out, terminal, abort):
    # Expensive checks stay outside this short terminal decision. Signals are
    # latched throughout both stages and post-run validation, never reset.
    signals = {signal.SIGINT, signal.SIGTERM}
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
    try:
        if abort.is_set() or signal.sigpending() & signals:
            abort.set()
            terminal['status'] = 'NOT_PASS'
        terminal['aborted'] = abort.is_set()
        temporary = out / 'complete.tmp'
        save(temporary, terminal)
        if abort.is_set() or signal.sigpending() & signals:
            abort.set()
            terminal.update(status='NOT_PASS', aborted=True)
            save(temporary, terminal)
        os.replace(temporary, out / 'complete.json')
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def run(image, out, approved, authorized):
    require(authorized and approved and sha(out / 'plan.json') == approved, 'Explicit run gate/plan SHA required')
    data = read(out / 'plan.json')
    validate_plan(data, image)
    ledger, repo, (parent, options_type, testcase, _) = image_context(image)
    require(ledger['snapshot_sha256'] == data['snapshot_sha256'], 'Snapshot drift')
    admission = resources(out, 4, data['reserved_slots'])
    with (out / 'launch.json').open('x') as stream:
        json.dump(dict(plan_sha256=approved, image=str(image), pid=os.getpid(),
                       started=time.time(), admission=admission), stream, indent=2)
    abort = threading.Event()
    terminal = dict(status='NOT_PASS', plan_sha256=approved, image=str(image),
                    image_sha256=data['image_sha256'], results=[], pins_unchanged=False)
    controls = {c['id']: c for c in data['controls']}
    # Extend the in-memory frozen runner's monitor, not its source files.
    import ara_verify.runner as engine
    original_fail_re = engine.FAIL_RE
    engine.FAIL_RE = re.compile(original_fail_re.pattern + '|' + BAD.pattern, original_fail_re.flags)
    with abort_signals(abort):
        try:
            (out / 'admission').mkdir(exist_ok=False)
            for stage, jobs in STAGES:
                require(not abort.is_set(), 'Aborted before stage')
                if stage != STAGES[0][0]:
                    validate_plan(data, image)
                    image_context(image)
                entries = {c['id']: c for c in data['cases'] if c['stage'] == stage}
                stage_out = out / stage
                require(not stage_out.exists(), 'Stage exists; no retry')
                def admit(name):
                    require(sha(Path(entries[name]['elf'])) == entries[name]['sha256'], 'ELF drift before launch')
                    save(out / 'admission' / (name + '.json'), resources(out, jobs, data['reserved_slots']))
                opts = options_type(repo, stage_out, 'default', jobs, 1, False,
                                    False, True, Path(ledger['simv']), True, None)
                tests = [testcase(c['id'], 'app', '', Path(c['elf']), c['original_name'], c['timeout_s'])
                         for c in entries.values()]
                runner = checked_runner(parent, entries, ledger, abort, admit, controls)(opts, tests, sys.argv)
                results = runner.run()
                terminal['results'].extend(dict(asdict(r), artifact_dir=str(r.artifact_dir)) for r in results)
                check_stage(results, read(stage_out / 'run.json'), list(entries.values()), abort)
                require(read(stage_out / 'summary.json') ==
                        [dict(asdict(r), artifact_dir=str(r.artifact_dir)) for r in results], 'Summary mismatch')
            validate_plan(data, image)
            image_context(image)
            performance = {c['id']: read(out / next(x['stage'] for x in data['cases'] if x['id'] == c['id']) /
                                        'tests' / c['id'] / 'performance.json') for c in data['controls']}
            evidence = {}
            for c in data['cases']:
                root = out / c['stage'] / 'tests' / c['id']
                for filename in ('input.elf', 'inputs.json', 'command.json', 'console.log',
                                 'work/run.vcs.log', 'commit_trace.csv', 'trace_summary.json'):
                    evidence[str(root / filename)] = sha(root / filename)
                if c['id'] in controls:
                    for filename in ('performance.json', 'cycle_differences.csv'):
                        evidence[str(root / filename)] = sha(root / filename)
            for stage, _ in STAGES:
                for name in ('run.json', 'summary.json'):
                    evidence[str(out / stage / name)] = sha(out / stage / name)
            terminal.update(status='PASS_48_ARCHITECTURAL', pins_unchanged=True, performance=performance,
                            performance_status=('REVIEW_CYCLE_DIFFERENCES' if any(
                                x['cycle_changed_rows'] for x in performance.values()) else 'EXACT_16_CSV'),
                            evidence_pins=evidence)
        except BaseException as error:
            abort.set()
            terminal.update(status='NOT_PASS', error=f'{type(error).__name__}: {error}')
        finally:
            engine.FAIL_RE = original_fail_re
            terminal['finished'] = time.time()
            publish(out, terminal, abort)
    print(terminal['status'], flush=True)
    return int(terminal['status'] != 'PASS_48_ARCHITECTURAL')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('prepare', 'run'))
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--reserved-slots', type=int)
    parser.add_argument('--authorize-prepare', action='store_true')
    parser.add_argument('--authorize-run', action='store_true')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    image, out = args.image.resolve(), args.out.resolve()
    require(out.is_relative_to(HERE) and out != HERE, 'Output must be a new gather_repair05 subdirectory')
    env = base.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    if args.mode == 'prepare':
        require(args.reserved_slots is not None and 0 <= args.reserved_slots <= 24, '--reserved-slots required')
        prepare(image, out, args.reserved_slots, args.authorize_prepare)
        return 0
    return run(image, out, args.plan_sha256, args.authorize_run)


if __name__ == '__main__':
    raise SystemExit(main())
