#!/usr/bin/env python3
"""Replay ledger positions 600..797, never inherit historical PASS or coverage.

No build, Spike, URG, service creation, or retry. Unknown semantic/probe auditors
are CHECKER_REQUIRED even after a clean simulation. --prepare-only freezes and
describes all commands without starting a simulator. The parent owns scheduling.
complete.json and pass-vdbs.txt are the coverage interface; only status PASS is
eligible, and COMPLETE describes traversal, NOT acceptance of all 198 members.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / 'verification/out/gather-war-offline-admitted798-v2-parent-20261008-01/elf-ledger-dedup.json'
LEDGER_SHA = 'b2820b1db622fe81608afca6c0314cde25995e2fdc604ca0fc3a22a5565ddcd9'
RECOVER_727 = ROOT / 'verification/out/fence-t-u-padding-linked-agent-727-20261006-01/review.json'
RECOVER_727_SHA = 'f43c5b5374b60779359772babbb88359f9640ec410d8817b3951f61754857292'
CHECKER_TIMEOUT = 1800
STOP = threading.Event()
PLUSARGS = {'+AKV_PERF', '+ARA_CONTRACT_TRACE_LIMIT', '+ARA_UVM_RESET_ON_AXI',
            '+ARA_UVM_RESET_READ_INDEX', '+ARA_UVM_TRACE_AXI_WRITE', '+ARA_UVM_TRACE_LIMIT',
            '+COMMIT_TOHOST', '+COMMIT_TRACE', '+NO_FSDB', '+PRELOAD', '+QBS_PERF',
            '+TESTCASE', '+VECTOR_TRACE', '+ntb_random_seed'}
ABS_TCL = re.compile(r'/[A-Za-z0-9_./-]+\.tcl')
RAW_FAIL = re.compile(r'\b(?:RVV_\w*FAIL|BOARD_REPLAY_TRAP)\b|'
                      r'\[ARA_CONTRACT_ERROR\]|\bUVM_ERROR\b(?![ \t]*:[ \t]*0\b)|'
                      r'\b(?:Error:|Error-\[|Fatal-\[)|^\s*FATAL\b|\b\w*PROBE_(?:ERROR|REJECT)\b', re.M)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, f'input pin drift: {path}')


def option(command, key):
    require(command.count(key) == 1, f'one {key} required')
    return command[command.index(key) + 1]


def plus(command, key):
    values = [x[len(key) + 1:] for x in command if x.startswith(key + '=')]
    require(len(values) == 1, f'one {key} required')
    return values[0]


def select_members(ledger):
    require(ledger.get('ledger_members') == 798 and len(ledger['members']) == 798,
            'exact 798-member ledger required')
    members = ledger['members']
    require(len({m['vdb'] for m in members}) == 798, 'duplicate VDB member')
    # Fourteen original600 timeout closures have different directory prefixes.
    # The pinned ledger order, not directory-name subtraction, defines the split.
    for i, member in enumerate(members[:600]):
        require(f'c{i:04d}-' in member['vdb'], f'original600 boundary mismatch {i}')
    return list(enumerate(members[600:], 600))


def original_command(index, member):
    matches = []
    for source in member['command_sources']:
        obj = read(source)
        cmd = obj.get('command')
        if not isinstance(cmd, list) or not all(isinstance(x, str) for x in cmd):
            continue
        if '-cm_dir' in cmd and option(cmd, '-cm_dir') == member['vdb']:
            matches.append((source, obj, cmd))
    if not matches and index == 727:
        require(sha(RECOVER_727) == RECOVER_727_SHA, 'fence727 recovery identity differs')
        obj = read(RECOVER_727)
        argv = obj['run']['argv']
        require(argv[:4] == ['timeout', '--signal=TERM', '--kill-after=10s', '600s'],
                'fence727 recovered timeout wrapper differs')
        cmd = argv[4:]
        require(option(cmd, '-cm_dir') == member['vdb'], 'fence727 command not member')
        matches.append((str(RECOVER_727), dict(command=cmd, timeout_s=600,
                        identity_recovery='pinned linked review; ledger ELF candidates belong to unrelated members',
                        recovered_elf_sha256=obj['ELF_sha256']), cmd))
    require(matches, 'BLOCKED_COMMAND: no original command bound to member VDB')
    require(len({tuple(item[2]) for item in matches}) == 1, 'conflicting archived commands')
    source, obj, cmd = matches[0]
    elf = Path(plus(cmd, '+PRELOAD'))
    expected = member['ELF_candidates'].get(str(elf))
    if index == 727 and source == str(RECOVER_727):
        require(expected is None, 'fence727 ledger recovery assumptions changed')
        expected = obj['recovered_elf_sha256']
        require(expected == read(RECOVER_727)['pins'].get(str(elf)), 'fence727 linked ELF pin disagreement')
    require(expected is not None and sha(elf) == expected, 'ELF not pinned by ledger')
    return Path(source), obj, cmd, elf


def freeze_tcl(source, directory, pins, cache=None):
    """Freeze literal Tcl dependencies; all observed writes are relative to cwd.

    Absolute Tcl paths are immutable script inputs (including file-copy selection
    scripts); substitute private copies. Reject other absolute filesystem paths,
    shell execution, and parent traversal rather than risk an old-output write.
    """
    cache = {} if cache is None else cache
    source = Path(source).resolve(strict=True)
    if source in cache:
        return cache[source]
    body = source.read_text()
    pins[str(source)] = sha(source)
    target = directory / f'{len(cache):02d}-{source.name}'
    cache[source] = target
    for literal in sorted(set(ABS_TCL.findall(body)), key=len, reverse=True):
        replacement = freeze_tcl(Path(literal), directory, pins, cache)
        body = body.replace(literal, str(replacement))
    checked = ABS_TCL.sub('FROZEN_SCRIPT', body)
    require(not re.search(r'(?:^|[\s{"\[])/(?:[A-Za-z]|tmp)', checked, re.M),
            f'unclassified absolute Tcl path: {source}')
    require(not re.search(r'(^|[;\n])\s*exec\b|\.\./', checked), f'unsafe Tcl command: {source}')
    target.write_text(body)
    pins[str(target)] = sha(target)
    return target


def rewrite(command, simv, work, elf, tcl=None):
    result = [str(simv)]
    value_flags = {'-l': str(work / 'run.vcs.log'), '-cm_dir': str(work / 'code.vdb'),
                   '-cm': None, '-cm_name': None, '-do': str(tcl) if tcl else None}
    outputs = {'+PRELOAD': str(elf), '+COMMIT_TRACE': str(work / 'commit_trace.csv'),
               '+VECTOR_TRACE': str(work / 'vector_trace.csv')}
    i = 1
    while i < len(command):
        arg = command[i]
        if arg in value_flags:
            require(i + 1 < len(command), f'missing argument: {arg}')
            require(command.count(arg) == 1, f'duplicate argument: {arg}')
            if arg == '-do':
                require(tcl is not None, 'unfrozen Tcl')
            result.extend([arg, value_flags[arg] or command[i + 1]])
            i += 2
        elif arg in ('-ucli', '-no_save'):
            result.append(arg)
            i += 1
        elif arg.startswith('+') and arg.split('=', 1)[0] in PLUSARGS:
            key = arg.split('=', 1)[0]
            require('/' not in arg or key in outputs, f'unclassified plusarg path: {arg}')
            result.append(key + '=' + outputs[key] if key in outputs else arg)
            i += 1
        else:
            raise ValueError(f'unreviewed VCS argument: {arg}')
    for key in ('-l', '-cm', '-cm_dir', '-cm_name'):
        option(result, key)
    require(option(result, '-cm') == 'line+cond+fsm+tgl+branch', 'coverage metrics differ')
    require(re.fullmatch(r'[A-Za-z0-9_]+', option(result, '-cm_name')), 'unsafe coverage name')
    plus(result, '+COMMIT_TRACE')
    return result


def checker_recipe(index, old_source, command, member, pins):
    if '-do' in command or any('RESET' in x for x in command):
        return dict(kind='CHECKER_REQUIRED', reason='original UCLI/probe/reset-specific audit required')
    if old_source.name == 'coverage.command.json':
        run = Path(member['vdb']).parent.parent.parent.parent / 'run.json'
        if run.is_file():
            meta = read(run)
            pins[str(run)] = sha(run)
            if meta.get('commit_trace') is True and not meta.get('probe_kinds'):
                return dict(kind='ORIGINAL_SELF_CHECK_TRACE', original_runner='ara_verify.runner',
                            original_run=str(run), contract_required=bool(meta.get('contract_monitor')),
                            scope='original firmware self-check + fresh generic trace/protocol validation; not differential')
    # This producer's original checker compares the complete Spike scalar/vector
    # reference. red32 has a documented native-bit/sign-zero qualification hold.
    if 654 <= index <= 686 and plus(command, '+TESTCASE') != 'vgap76_red32':
        golden = Path(member['vdb']).parent / 'spike.trace'
        if golden.is_file() and '+VECTOR_TRACE=' in ' '.join(command):
            pins[str(golden)] = sha(golden)
            return dict(kind='FULL_SCALAR_VECTOR', reference=str(golden),
                        tohost=int(plus(command, '+COMMIT_TOHOST'), 16),
                        scope='fresh full scalar/vector comparison using original reference and checker APIs')
    return dict(kind='CHECKER_REQUIRED', reason='specialized original semantic audit not safely ported; old PASS never reused')


def prepare_case(index, member, output, simv):
    case = output / f'e{index:04d}'
    case.mkdir()
    row = dict(index=index, directory=str(case), original_vdb=member['vdb'],
               status='PREPARING', executed=False, returncode=None)
    try:
        source, meta, old, elf = original_command(index, member)
        work = case / 'work'
        work.mkdir()
        pins = {str(source): sha(source), str(elf): sha(elf)}
        private = case / 'input.elf'
        shutil.copyfile(elf, private)
        pins[str(private)] = sha(private)
        tcl = None
        if '-do' in old:
            scripts = case / 'ucli'
            scripts.mkdir()
            tcl = freeze_tcl(option(old, '-do'), scripts, pins)
        checker = checker_recipe(index, source, old, member, pins)
        timeout = meta.get('timeout_s', meta.get('budget_s', 1800))
        require(type(timeout) in (int, float) and 0 < timeout <= 10800, 'invalid archived timeout')
        row.update(status='PREPARED', command=rewrite(old, simv, work, private, tcl),
                   original_command=old, command_source=str(source), elf_sha256=sha(private),
                   identity_recovery=meta.get('identity_recovery'),
                   timeout_s=timeout, timeout_origin='archived' if 'timeout_s' in meta or 'budget_s' in meta else 'bounded_default_1800',
                   checker=checker, pins=pins, work=str(work), vdb=str(work / 'code.vdb'))
        verify(pins)
    except Exception as error:
        row.update(status='BLOCKED', reason=f'{type(error).__name__}: {error}')
    save(case / 'plan.json', row)
    return row


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def child(command, cwd, log, timeout, receipt, on_start=None):
    started = time.time()
    record = dict(command=command, cwd=str(cwd), started=started, returncode=None,
                  timed_out=False, cancelled=False, executed=False)
    try:
        with Path(log).open('x') as stream:
            process = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            record.update(pid=process.pid, executed=True)
            save(receipt, record)
            if on_start:
                on_start(process.pid)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    process.wait(timeout=min(1, max(0.01, deadline - time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    if STOP.is_set() or time.monotonic() >= deadline:
                        record.update(cancelled=STOP.is_set(), timed_out=not STOP.is_set())
                        stop_group(process)
                        break
            record['returncode'] = process.returncode
    except Exception as error:
        if 'process' in locals() and process.poll() is None:
            stop_group(process)
            record['returncode'] = process.returncode
        record['error'] = f'{type(error).__name__}: {error}'
    record.update(finished=time.time(), elapsed_s=time.time() - started)
    # Persist the actual numeric wait BEFORE any semantic checker can throw.
    save(receipt, record)
    return record


def check_case(plan):
    sys.path.insert(0, str(ROOT / 'verification'))
    from ara_verify.runner import FAIL_RE, SUCCESS_RE, _contract_evidence
    from ara_verify.contract import check_contract_log
    from ara_verify.trace import validate_trace
    work = Path(plan['work'])
    verify(plan['pins'])
    logs = [Path(plan['directory']) / 'console.log', work / 'run.vcs.log']
    recipe = plan['checker']
    success = False
    for path in logs:
        require(path.is_file(), f'missing actual raw log: {path}')
        # Streaming raw veto avoids loading very large runtime logs.
        with path.open(errors='replace') as stream:
            for line in stream:
                require(not FAIL_RE.search(line) and not RAW_FAIL.search(line),
                        f'raw failure veto {path.name}: {line[:300].strip()}')
                success |= bool(SUCCESS_RE.search(line))
        if recipe['kind'] == 'FULL_SCALAR_VECTOR' or recipe.get('contract_required'):
            issues = check_contract_log(path)
            require(not issues, f'original required protocol checker {path}: {issues}')
    if recipe['kind'] == 'CHECKER_REQUIRED':
        return dict(status='CHECKER_REQUIRED', reason=recipe['reason'], selfcheck_success_seen=success)
    require(success, 'actual firmware SUCCESS absent')
    generic = validate_trace(work / 'commit_trace.csv')
    report = dict(status='PASS', kind=recipe['kind'], trace=generic, scope=recipe['scope'])
    if recipe.get('contract_required'):
        evidence = _contract_evidence(logs[0], logs[1])
        require(evidence['status'] == 'PASS', f'original required contract: {evidence}')
        report['contract'] = evidence
    if recipe['kind'] == 'FULL_SCALAR_VECTOR':
        from ara_verify.spike_trace import compare_commit_prefix
        from ara_verify.vector_commit import compare_vector_commits
        from ara_verify.plan import _full_architecture_match, _full_vector_match
        reference = Path(recipe['reference'])
        scalar = compare_commit_prefix(reference, work / 'commit_trace.csv', 0x80000000,
                                       terminal_tohost_address=recipe['tohost'], rvfi_store_data_layout='unshifted')
        vector = compare_vector_commits(reference, work / 'commit_trace.csv', work / 'vector_trace.csv', 0x80000000)
        report.update(scalar=scalar, vector=vector)
        save(Path(plan['directory']) / 'comparisons.json', report)
        require(_full_architecture_match(scalar) and _full_vector_match(vector), 'incomplete/mismatched scalar/vector reference')
    db = work / 'code.vdb/snps/coverage/db/testdata' / option(plan['command'], '-cm_name') / 'siminfo.xml'
    require(db.is_file(), 'fresh VCS test coverage missing')
    verify(plan['pins'])
    return report


def run_case(plan, update):
    row = dict(plan)
    if row['status'] == 'BLOCKED':
        return row
    case = Path(row['directory'])
    try:
        require(not STOP.is_set(), 'parent cancelled before launch')
        verify(row['pins'])
        actual = child(row['command'], row['work'], case / 'console.log', row['timeout_s'],
                       case / 'simulation-exit.json',
                       lambda pid: update(dict(row, status='RUNNING', pid=pid, executed=True)))
        row.update(executed=actual['executed'], returncode=actual['returncode'], elapsed_s=actual['elapsed_s'])
        if actual['timed_out']:
            row.update(status='TIMEOUT', reason='bounded simulator timeout; no retry')
        elif actual['cancelled']:
            row.update(status='CANCELLED', reason='parent cancellation')
        elif type(actual['returncode']) is not int or actual['returncode'] != 0:
            row.update(status='FAIL', reason=f'actual simulator exit: {actual}')
        else:
            update(dict(row, status='CHECKING'))
            receipt = child([sys.executable, '-B', str(Path(__file__).resolve()), '--check-case', str(case / 'plan.json')],
                            ROOT, case / 'checker.log', CHECKER_TIMEOUT, case / 'checker-exit.json')
            if type(receipt['returncode']) is not int or receipt['returncode'] != 0 or receipt['timed_out'] or receipt['cancelled']:
                detail = read(case / 'checker.json') if (case / 'checker.json').exists() else {}
                row.update(status='FAIL', reason='fresh checker failed', checker_result=detail, checker_exit=receipt)
            else:
                result = read(case / 'checker.json')
                require(result['status'] in ('PASS', 'CHECKER_REQUIRED'), 'invalid checker terminal status')
                row.update(status=result['status'], checker_result=result)
    except Exception as error:
        row.update(status='FAIL', reason=f'{type(error).__name__}: {error}')
    save(case / 'result.json', row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simv', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--jobs', type=int, default=8, choices=range(1, 9))
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--check-case', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_case:
        try:
            result = check_case(read(args.check_case))
        except Exception as error:
            result = dict(status='FAIL', reason=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
        save(args.check_case.parent / 'checker.json', result)
        return int(result['status'] == 'FAIL')
    require(args.simv and args.output, '--simv and --output required')
    simv = args.simv.resolve(strict=True)
    require(os.access(simv, os.X_OK), 'simv not executable')
    require(sha(LEDGER) == LEDGER_SHA, 'frozen798 ledger identity differs')
    members = select_members(read(LEDGER))
    out = args.output.resolve()
    require(not out.exists(), 'output must be fresh; never resume/retry over old evidence')
    out.mkdir(parents=True)
    sys.path.insert(0, str(ROOT / 'verification'))
    from ara_verify.artifacts import simulation_image
    image = simulation_image(simv)
    modules = [Path(__file__).resolve(), Path(__file__).with_name('test_replay_historical_extensions_20261015.py'),
               *sorted((ROOT / 'verification/ara_verify').glob('*.py'))]
    shared = {str(p): sha(p) for p in modules}
    shared[str(LEDGER)] = LEDGER_SHA
    shared.update(image)
    save(out / 'input-pins.json', shared)
    state = dict(schema='HISTORICAL_EXTENSION_REPLAY_V1', status='PREPARING', total=198,
                 jobs=args.jobs, simv=str(simv), image=image, started=time.time(), cases={},
                 scope='198 extensions only; no inherited historical PASS; no Linux/board closure')
    lock = threading.Lock()

    def update(row):
        with lock:
            state['cases'][str(row['index'])] = row
            state['counts'] = dict(Counter(r['status'] for r in state['cases'].values()))
            state['updated'] = time.time()
            save(out / 'progress.json', state)

    save(out / 'progress.json', state)
    plans = []
    for index, member in members:
        plan = prepare_case(index, member, out, simv)
        plans.append(plan)
        plan_path = Path(plan['directory']) / 'plan.json'
        shared[str(plan_path)] = sha(plan_path)
        update(plan)
    save(out / 'input-pins.json', shared)
    save(out / 'plan.json', dict(total=198, jobs=args.jobs, cases=plans, pins=shared,
                                checker_timeout_s=CHECKER_TIMEOUT, retries=0))
    if args.prepare_only:
        verify(shared)
        state['status'] = 'PREPARED_NOT_EXECUTED'
        save(out / 'progress.json', state)
        print(json.dumps(dict(status=state['status'], counts=state['counts'], output=str(out))))
        return 0
    verify(shared)
    state['status'] = 'RUNNING'
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: STOP.set())
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_case, plan, update) for plan in plans]
        for future in as_completed(futures):
            update(future.result())
    try:
        verify(shared)
        require(simulation_image(simv) == image, 'image library membership changed')
        state['input_pins_unchanged'] = True
    except Exception as error:
        state.update(input_pins_unchanged=False, pin_error=str(error))
        for row in state['cases'].values():
            if row['status'] == 'PASS':
                row.update(status='FAIL', reason='global input pin drift', previous_status='PASS')
                save(Path(row['directory']) / 'result.json', row)
    state['counts'] = dict(Counter(r['status'] for r in state['cases'].values()))
    passed = [r['vdb'] for _, r in sorted(state['cases'].items(), key=lambda item: int(item[0])) if r['status'] == 'PASS']
    (out / 'pass-vdbs.txt').write_text(''.join(p + '\n' for p in passed))
    state.update(status='CANCELLED' if STOP.is_set() else 'COMPLETE', finished=time.time(),
                 passed=len(passed), executed=sum(r['executed'] for r in state['cases'].values()),
                 all_198_passed=len(passed) == 198, pass_vdbs=passed,
                 pass_vdbs_sha256=sha(out / 'pass-vdbs.txt'))
    save(out / 'progress.json', state)
    save(out / 'complete.json', state)
    print(json.dumps(dict(status=state['status'], counts=state['counts'], executed=state['executed'], passed=len(passed))))
    return 0 if len(passed) == 198 else 1


if __name__ == '__main__':
    raise SystemExit(main())
