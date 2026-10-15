#!/usr/bin/env python3
"""Fail-closed successor: unknown predecessor service exit requires manual HOLD."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REVIEW = HERE.parents[1]
PRE = HERE.parent / 'repair06_worker/prepared01'
REG = REVIEW / 'gather_repair05/repair06_regression48_prepared01'
HELPER = REVIEW / 'gather_repair05/regression.py'
WORKER = HERE.parent / 'repair06_worker/worker.py'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
PRE_SHA = 'd2053cb571e3df53a4ec846d440b0eb3eca72f61b4b048ecad196060ac7903b8'
REG_SHA = 'ac33642809800f58c5f4534bdb52622849335ee3872a2b4347da7b7588ff8929'
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
PRE_UNIT = 'ara-indexed-overlap-m6-01.service'
UNIT = 'ara-indexed-overlap-m6-followup-01.service'
WAIT_SECONDS, SLEEP_SECONDS, REG_SECONDS, SERVICE_SECONDS = 10800, 120, 21600, 33000


def require(ok, why):
    if not ok:
        raise ValueError(why)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def save(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Hash drift: ' + str(path))


def load_inputs():
    verify({PRE / 'plan.json': PRE_SHA, REG / 'plan.json': REG_SHA, IMAGE / 'image.json': IMAGE_SHA})
    pre, reg = read(PRE / 'plan.json'), read(REG / 'plan.json')
    verify(pre['pins']); verify(reg['pins'])
    require(pre['image'] == reg['image'] == str(IMAGE) and
            pre['image_sha256'] == reg['image_sha256'] == IMAGE_SHA and
            pre['snapshot_sha256'] == reg['snapshot_sha256'], 'Input image disagreement')
    require(pre['pins'][str(WORKER)] == sha(WORKER) and
            reg['pins'][str(HELPER)] == sha(HELPER), 'Unpinned executable helper')
    sys.path.insert(0, str(WORKER.parent))
    spec = importlib.util.spec_from_file_location('m6_followup_predecessor', WORKER)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    return pre, reg, worker


def shared_validation(pre, reg, worker):
    worker.validate_plan(pre, IMAGE)
    worker.common.validate_plan(reg, IMAGE)
    ledger, _, _ = worker.image_context(IMAGE)
    return ledger


def owner_proof(props, pid, cgroup):
    require(props.get('Id') == UNIT and props.get('LoadState') == 'loaded' and
            props.get('ActiveState') == 'active' and props.get('SubState') == 'running' and
            props.get('MainPID') == str(pid) and props.get('ControlGroup') == cgroup and
            cgroup.endswith('/' + UNIT), 'Foreign/non-direct service owner')


def service_owner(worker):
    fields = 'Id,LoadState,ActiveState,SubState,MainPID,ControlGroup'
    proc = subprocess.run(['systemctl', '--user', 'show', UNIT, '--property=' + fields],
                          capture_output=True, text=True, timeout=15, env=worker.bus_environment())
    require(proc.returncode == 0 and not proc.stderr.strip(), 'Service query failed')
    props = dict(line.split('=', 1) for line in proc.stdout.splitlines())
    cgroup = next(x.split(':', 2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines()
                  if x.startswith('0::'))
    owner_proof(props, os.getpid(), cgroup)
    return props


def processes():
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            comm = (path / 'comm').read_text().strip()
            argv = (path / 'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            cgroup = (path / 'cgroup').read_text()
            rows.append(dict(pid=int(path.name), comm=comm, argv=argv, cgroup=cgroup))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return rows


def owned_rows(rows, out, unit):
    result = []
    for row in rows:
        arg_owner = any(a == str(out) or a.startswith('+COMMIT_TRACE=' + str(out) + '/')
                        for a in row['argv'])
        group_owner = any(line.endswith('/' + unit) for line in row['cgroup'].splitlines())
        require(not arg_owner or group_owner, 'Owned output used by foreign cgroup')
        if arg_owner or group_owner:
            result.append(row)
    return result


def predecessor_state(worker):
    fields = 'Id,LoadState,ActiveState,SubState,MainPID,Result,ExecMainCode,ExecMainStatus,ExecMainExitTimestamp'
    proc = subprocess.run(['systemctl', '--user', 'show', PRE_UNIT, '--property=' + fields],
                          capture_output=True, text=True, timeout=15, env=worker.bus_environment())
    require(proc.returncode == 0 and not proc.stderr.strip(), 'Predecessor service query failed')
    props = dict(line.split('=', 1) for line in proc.stdout.splitlines())
    require(props['Id'] == PRE_UNIT, 'Wrong predecessor service')
    rows = owned_rows(processes(), PRE, PRE_UNIT)
    require(props['LoadState'] != 'not-found', 'HOLD: predecessor service GC; actual exit unknown')
    require(props['LoadState'] == 'loaded', 'Unknown predecessor unit state')
    if props['ActiveState'] in ('active', 'activating', 'deactivating'):
        return False, dict(properties=props, residual=rows, historical_service_exit_verified=False)
    require(props['ActiveState'] == 'inactive' and props['MainPID'] == '0' and
            props['Result'] == 'success' and props['ExecMainCode'] == '1' and
            props['ExecMainStatus'] == '0' and props['ExecMainExitTimestamp'], 'Predecessor service failed/timeout/unproven')
    return not rows, dict(properties=props, residual=rows, historical_service_exit_verified=True)


def regression_command():
    return ['/usr/bin/python3', '-B', str(HELPER), 'run', '--image', str(IMAGE),
            '--out', str(REG), '--plan-sha256', REG_SHA, '--authorize-run']


def terminal_header(data, plan, digest, expected_status):
    require(data['status'] == expected_status and data['aborted'] is False and
            data['pins_unchanged'] is True and data['plan_sha256'] == digest and
            data['image_sha256'] == IMAGE_SHA, 'False/aborted/foreign terminal PASS')
    results = data['results']
    require(len(results) == len(plan['cases']) and
            {r['name'] for r in results} == {c['id'] for c in plan['cases']}, 'Partial/duplicate terminal membership')
    for case in plan['cases']:
        result = next(r for r in results if r['name'] == case['id'])
        require(result['status'] == 'PASS' and result['returncode'] == 0 and
                0 <= result['elapsed_s'] <= case['timeout_s'], 'Case exit/timeout/not PASS')
    require(data['evidence_pins'], 'Missing terminal evidence')


def expected_evidence(plan, root, predecessor):
    evidence = set()
    for stage in plan['stages']:
        cases = [c for c in plan['cases'] if c['id'] in stage['cases']] if predecessor else [
            c for c in plan['cases'] if c['stage'] == stage['name']]
        for case in cases:
            work = root / stage['name'] / 'tests' / case['id']
            names = ['input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log',
                     'commit_trace.csv', 'trace_summary.json']
            if predecessor:
                names += ['indexed_analysis.json']
                if stage['name'] == 'pilot': names += ['work/indexed_first_round.fsdb']
            elif case['id'] in {c['id'] for c in plan['controls']}:
                names += ['performance.json', 'cycle_differences.csv']
            evidence.update(str(work / name) for name in names)
        evidence.update(str(root / stage['name'] / name) for name in ('run.json', 'summary.json'))
    return evidence


def accept_terminal(root, plan, digest, worker, ledger, predecessor):
    terminal_path = root / 'complete.json'
    terminal_sha = sha(terminal_path)
    data = read(terminal_path)
    terminal_header(data, plan, digest, 'PASS_3_REFERENCE03_FULL50_M6' if predecessor else 'PASS_48_ARCHITECTURAL')
    require(0 <= data['elapsed_s'] < 8800, 'Predecessor shared timeout') if predecessor else None
    require(set(data['evidence_pins']) == expected_evidence(plan, root, predecessor), 'Evidence membership differs')
    verify(data['evidence_pins'])
    require(not list(root.rglob('firstfailure.json')), 'First failure evidence exists')
    for stage in plan['stages']:
        summary = read(root / stage['name'] / 'summary.json')
        names = stage['cases'] if predecessor else [c['id'] for c in plan['cases'] if c['stage'] == stage['name']]
        records = [r for r in data['results'] if r['name'] in names]
        require(summary == records, 'Summary differs from terminal')
        worker.common.check_stage([SimpleNamespace(**r) for r in records],
                                  read(root / stage['name'] / 'run.json'),
                                  [c for c in plan['cases'] if c['id'] in names], threading.Event())
        for case in (c for c in plan['cases'] if c['id'] in names):
            work = root / stage['name'] / 'tests' / case['id']
            result = next(r for r in records if r['name'] == case['id'])
            require(result['artifact_dir'] == str(work), 'Foreign artifact directory')
            if not predecessor:
                worker.common.check_artifacts(SimpleNamespace(**dict(result, artifact_dir=work)), case, ledger)
                continue
            worker.console(case, (work / 'console.log').read_text())
            worker.console(case, (work / 'work/run.vcs.log').read_text())
            require(sha(work / 'input.elf') == case['sha256'], 'Private ELF drift')
            require(read(work / 'inputs.json') == dict(
                binary=dict(source=case['elf'], path=str(work / 'input.elf'), sha256=case['sha256']),
                simv=dict(path=ledger['simv'], image_sha256=ledger['files'])), 'Input/image provenance mismatch')
            command = [ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
                       '+PRELOAD=' + str(work / 'input.elf'), '+TESTCASE=' + case['original_name'],
                       '+NO_FSDB', '+COMMIT_TRACE=' + str(work / 'commit_trace.csv'), worker.DEBUG]
            if stage['name'] == 'pilot': command += ['-ucli', '-do', plan['pilot_capture']]
            require(read(work / 'command.json') == dict(command=command, cwd=str(work / 'work')), 'Actual command mismatch')
            require(read(work / 'trace_summary.json')['status'] == 'VALID', 'Invalid RVFI summary')
            analysis = read(work / 'indexed_analysis.json')
            count, faults = (50, 1600) if case['fault'] else (51, 0)
            require(analysis['status'] == 'CSV_FULL_ORACLE_PASS' and analysis['rounds'] == 50 and
                    analysis['checks'] == case['checks'] and len(analysis['points']) == count and
                    [p['round'] for p in analysis['points']] == list(range(count)) and
                    analysis['reloads'] == analysis['successful_target_retires'] == count and
                    analysis['accepted_targets'] == count + faults and
                    analysis['fault_responses'] == analysis['repairs'] == analysis['retries'] == faults and
                    len(analysis['traps']) == faults and analysis['backing_words_read'] == 32768 and
                    analysis['pte_words_read'] == 1536, 'Incomplete recorded full oracle')
    if not predecessor:
        require(set(data['performance']) == {c['id'] for c in plan['controls']} and
                all(p['noncycle_equal'] is True and p['rows'] > 0 for p in data['performance'].values()),
                'Missing/nonmatching performance controls')
        for control in plan['controls']:
            case = next(c for c in plan['cases'] if c['id'] == control['id'])
            require(data['performance'][case['id']] == read(root / case['stage'] / 'tests' /
                    case['id'] / 'performance.json'), 'Performance ledger mismatch')
    require(sha(terminal_path) == terminal_sha, 'Terminal changed during acceptance')
    return dict(terminal_sha256=terminal_sha, evidence_count=len(data['evidence_pins']),
                evidence_pins=data['evidence_pins'], results=len(data['results']))


def prepare(out):
    require(not out.exists() and out.parent == HERE, 'Fresh direct owned output required')
    host = read(HERE / 'host_successor_final.json')
    require(host['status'] == 'HOST_PASS_NOT_DUT', 'Host negatives not accepted')
    verify(host['pins'])
    pre, reg, worker = load_inputs()
    shared_validation(pre, reg, worker)
    require(not (REG / 'launch.json').exists() and not (REG / 'complete.json').exists(), 'Regression already used')
    previous_path = HERE / 'prepared01/plan.json'
    require(sha(previous_path) == '4765cdfc0805b304b593b4fed7be2542a66907b4890ae777f0707bbe0c6ae007',
            'Previous plan drift')
    previous = read(previous_path)
    require(len(previous['pins']) == 885, 'Previous exact885 scope drift')
    verify(previous['pins'])
    pins = dict(previous['pins'])
    pins.update(pre['pins']); pins.update(reg['pins']); pins.update(host['pins'])
    require(all(pins[p] == h for p, h in previous['pins'].items()), 'Lost previous pin')
    pins[str(previous_path)] = sha(previous_path)
    for path in (PRE / 'plan.json', REG / 'plan.json', HERE / 'host_successor_final.json'):
        pins[str(path)] = sha(path)
    plan = dict(status='PREPARED_NOT_RUN', pins=pins, predecessor=str(PRE), predecessor_sha256=PRE_SHA,
                regression=str(REG), regression_sha256=REG_SHA, image=str(IMAGE), image_sha256=IMAGE_SHA,
                wait_seconds=WAIT_SECONDS, sleep_seconds=SLEEP_SECONDS, regression_seconds=REG_SECONDS,
                service_seconds=SERVICE_SECONDS, unit=UNIT, retries=0, no_build=True,
                unknown_predecessor_exit='HOLD_NO_AUTOMATIC_FALLBACK', previous_pin_count=885,
                command=regression_command())
    out.mkdir(); save(out / 'plan.json', plan)
    command = ['systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec',
               '--property=RuntimeMaxSec=' + str(SERVICE_SECONDS), '--property=TimeoutStopSec=60',
               '--property=KillMode=control-group', '--property=Restart=no',
               '--property=StandardOutput=append:' + str(out / 'service.log'),
               '--property=StandardError=append:' + str(out / 'service.log'),
               '/usr/bin/python3', '-B', str(HERE / 'coordinator_successor.py'), 'run', '--out', str(out),
               '--plan-sha256', sha(out / 'plan.json'), '--authorize-run']
    save(out / 'service_command.NOT_EXECUTED.json', command)
    print(json.dumps(dict(status='PREPARED_NOT_RUN', plan=str(out / 'plan.json'), sha256=sha(out / 'plan.json'))))


def run(out, digest, authorized):
    require(authorized and sha(out / 'plan.json') == digest, 'Explicit run authorization/pinned plan required')
    plan = read(out / 'plan.json'); verify(plan['pins'])
    require(plan['unit'] == UNIT and plan['wait_seconds'] == WAIT_SECONDS and
            plan['sleep_seconds'] == SLEEP_SECONDS and plan['regression_seconds'] == REG_SECONDS and
            plan['service_seconds'] == SERVICE_SECONDS and plan['retries'] == 0 and plan['no_build'] is True,
            'Execution budget/contract drift')
    require(plan['command'] == regression_command() and
            plan['unknown_predecessor_exit'] == 'HOLD_NO_AUTOMATIC_FALLBACK' and
            plan['previous_pin_count'] == 885, 'Sealed command/strict exit policy drift')
    pre, reg, worker = load_inputs()
    owner = service_owner(worker)
    save(out / 'launch.json', dict(pid=os.getpid(), service=owner, started=time.time(), plan_sha256=digest))
    started = time.monotonic(); abort = threading.Event(); child = None
    terminal = dict(status='BLOCKED_PREDECESSOR', phase='predecessor', plan_sha256=digest, image_sha256=IMAGE_SHA)
    with worker.common.abort_signals(abort):
        try:
            while True:
                require(not abort.is_set() and time.monotonic() - started < WAIT_SECONDS,
                        'Predecessor wait cancelled/expired; never accepted missing terminal')
                if (PRE / 'complete.json').exists():
                    terminal_header(read(PRE / 'complete.json'), pre, PRE_SHA, 'PASS_3_REFERENCE03_FULL50_M6')
                    quiet, proof = predecessor_state(worker)
                    if quiet: break
                abort.wait(min(SLEEP_SECONDS, max(0, WAIT_SECONDS - (time.monotonic() - started))))
            # No repeated full hashing while waiting. Validators run once at admission.
            verify(plan['pins'])
            ledger = shared_validation(pre, reg, worker)
            accepted = accept_terminal(PRE, pre, PRE_SHA, worker, ledger, True)
            quiet, proof = predecessor_state(worker)
            require(quiet, 'Predecessor still owns processes')
            require(not (REG / 'launch.json').exists() and not (REG / 'complete.json').exists(), 'No regression retry')
            require(not [r for r in owned_rows(processes(), REG, UNIT) if r['pid'] != os.getpid()],
                    'Regression output/service already owned')
            resource = worker.common.resources(REG, 4, reg['reserved_slots'])
            require(not abort.is_set() and time.monotonic() - started < WAIT_SECONDS,
                    'Predecessor acceptance exceeded wait budget')
            save(out / 'admission.json', dict(predecessor=accepted, predecessor_service=proof,
                                             resources=resource, owner=owner))
            terminal.update(status='REGRESSION_NOT_ACCEPTED', phase='regression')
            run_started = time.monotonic()
            with (out / 'regression.log').open('x') as log:
                child = subprocess.Popen(plan['command'], cwd=REG.parent, stdout=log, stderr=subprocess.STDOUT,
                                         env=worker.common.base.shared.environment())
                child_group = next(x.split(':', 2)[2] for x in (Path('/proc') / str(child.pid) / 'cgroup').read_text().splitlines()
                                   if x.startswith('0::'))
                require(child_group == owner['ControlGroup'], 'Child escaped owned service cgroup')
                save(out / 'child.json', dict(pid=child.pid, command=plan['command'], parent=os.getpid(),
                                               cgroup=owner['ControlGroup'], new_service=False))
                while child.poll() is None:
                    require(not abort.is_set() and time.monotonic() - run_started < REG_SECONDS,
                            'Regression cancelled/deadline expired')
                    try: child.wait(timeout=max(0, min(SLEEP_SECONDS, REG_SECONDS - (time.monotonic() - run_started))))
                    except subprocess.TimeoutExpired: pass
                require(child.returncode == 0 and not abort.is_set(), 'Regression nonzero/cancelled')
            verify(plan['pins'])
            result = accept_terminal(REG, reg, REG_SHA, worker, ledger, False)
            require(time.monotonic() - run_started < REG_SECONDS and not abort.is_set(), 'Late regression acceptance')
            require(not [r for r in owned_rows(processes(), REG, UNIT) if r['pid'] not in (os.getpid(),)],
                    'Residual regression/service processes')
            terminal.update(status='REGRESSION48_PASS', predecessor=accepted, regression=result)
        except BaseException as error:
            terminal['error'] = f'{type(error).__name__}: {error}'
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try: child.wait(timeout=30)
                except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=30)
            terminal.update(aborted=abort.is_set(), elapsed_s=time.monotonic() - started, finished=time.time())
            if terminal['status'] == 'REGRESSION48_PASS' and time.monotonic() - run_started >= REG_SECONDS:
                terminal.update(status='REGRESSION_NOT_ACCEPTED', error='Deadline before terminal publication')
            worker.common.publish(out, terminal, abort)
    return int(terminal['status'] != 'REGRESSION48_PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args(); out = args.out.resolve()
    require(out.parent == HERE, 'Only new owned direct outputs')
    if args.mode == 'prepare': prepare(out); return 0
    return run(out, args.plan_sha256, args.authorize_run)


if __name__ == '__main__':
    raise SystemExit(main())
