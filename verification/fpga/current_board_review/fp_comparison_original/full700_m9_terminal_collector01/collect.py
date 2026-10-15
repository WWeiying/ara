"""One pidfd attachment; one closed CSV audit; no DUT/reference dispatch."""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORK = HERE.parent / 'full700_vcs_m9_plan01'
RUN = WORK / 'prepared03'
OUT = HERE / 'run01'
PLAN = 'f1472802594a02022bf42b4652977db2c2d30e3cf8d622c014529f7200107290'
ENTRY = '12f51b0facdc454d6d6722a06ecb1d2e6be728746a5ac4fa85c70c09f46f8408'
GENERIC = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/verification/ara_verify/trace.py')
TEMPLATE = HERE.parent / 'fp_alias50_terminal_eventcheck01'
WAIT, AUDIT = 9000, 1500
UNIT = 'ara-fp-alias-original700-m9-terminal01.service'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


base = load('immutable_terminal700_utilities', TEMPLATE / 'audit.py')
base.OUT = OUT
read, sha, save, require, verify = base.read, base.sha, base.save, base.require, base.verify


def modules():
    sys.path.insert(0, str(WORK))
    import replay
    return replay, load('terminal700_frozen_protocol', GENERIC), load(
        'terminal700_lossless', TEMPLATE / 'observer.py').Observer


def bus():
    env = dict(os.environ)
    env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
               DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    return env


def systemd(unit):
    keys = 'Id,LoadState,ActiveState,SubState,MainPID,Result,ExecMainCode,ExecMainStatus,ControlGroup'
    p = subprocess.run(['systemctl', '--user', 'show', unit, '--property=' + keys],
                       env=bus(), capture_output=True, text=True, timeout=10)
    require(p.returncode == 0 and not p.stderr.strip(), 'Real user-manager query failed')
    data = dict(line.split('=', 1) for line in p.stdout.splitlines())
    require(set(data) == set(keys.split(',')), 'Incomplete service properties')
    require(data['Id'] == unit and data['LoadState'] == 'loaded', 'No GC/default service evidence')
    return data


def exited(p):
    return (p['MainPID'] == '0' and p['SubState'] in ('exited', 'dead', 'failed')
            and p['ExecMainCode'] in ('1', 'exited', 'CLD_EXITED', '2', '3', 'killed', 'dumped'))


def successful_exit(p):
    return (exited(p) and p['Result'] == 'success' and p['ExecMainStatus'] == '0'
            and p['ExecMainCode'] in ('1', 'exited', 'CLD_EXITED'))


def ready_gate(digest):
    require(not sys.flags.optimize and sha(HERE / 'READY.json') == digest, 'Collector READY/assertions')
    ready = read(HERE / 'READY.json')
    verify(ready['pins'])
    require(sha(RUN / 'plan.json') == PLAN and sha(WORK / 'ENTRY.json') == ENTRY, 'Producer identity drift')
    return ready


def success_gate(w, terminal, root, ledger, service):
    require(successful_exit(service), 'Actual producer service exit0 required')
    require(terminal['status'] == w.PASS and terminal['plan_sha256'] == PLAN
            and terminal['aborted'] is False and terminal['pins_unchanged'] is True
            and terminal['retries'] == 0 and not terminal.get('error'), 'Whole producer acceptance')
    require(not (RUN / 'first_cause.json').exists() and not (root / 'first_cause.json').exists(), 'Sticky failure')
    require(terminal['results'] == read(RUN / 'replay/summary.json') and len(terminal['results']) == 1,
            'Exact original700 result membership')
    results = [SimpleNamespace(**dict(r, artifact_dir=Path(r['artifact_dir']))) for r in terminal['results']]
    w.worker.terminal_gate(results, read(RUN / 'replay/run.json'), threading.Event(), ledger)
    r = results[0]
    require(r.name == w.NAME and r.artifact_dir == root and r.status == 'PASS'
            and type(r.returncode) is int and r.returncode == 0 and not r.reason
            and 0 <= r.elapsed_s <= 7200, 'Exact numeric result')
    child = read(root / 'child_outcome.unvalidated.json')
    require(child['name'] == w.NAME and child['source_label'] == w.HISTORICAL
            and type(child['returncode']) is int and child['returncode'] == 0
            and child['timed_out'] is False and child['failure_seen'] is False
            and child['architectural_acceptance'] is False and child['timeout_s'] == 7200
            and 0 <= child['elapsed_s'] <= 7200, 'Durable actual numeric monitor0')
    command = read(root / 'command.json')
    expected = dict(command=w.worker.monitor_command(root, ledger['simv'], w.NAME), cwd=str(root / 'work'))
    require(command == expected and child['command'] == expected['command']
            and child['cwd'] == expected['cwd'], 'Private exact command')
    provenance = read(root / 'child_command.provenance.json')
    require(provenance['command'] == command and provenance['command_sha256'] == sha(root / 'command.json')
            and provenance['actual_monitor_command'] == expected['command'], 'Durable command provenance')
    return r


def audit(digest):
    ready_gate(digest)
    w, protocol, Observer = modules()
    plan = read(RUN / 'plan.json')
    w.terminal_plan_gate(RUN, PLAN, w.IMAGE)
    w.authorization_gate(PLAN, WORK / 'ENTRY.json', ENTRY)
    terminal = read(RUN / 'complete.json')
    closure = read(OUT / 'closed.json')
    require(sha(RUN / 'complete.json') == closure['complete_sha256'], 'Closed complete identity')
    root = RUN / 'replay/tests' / w.NAME
    ledger = read(w.IMAGE / 'image.json')
    eligibility_error = None
    try:
        result = success_gate(w, terminal, root, ledger, closure['producer_service'])
    except Exception as error:
        eligibility_error = repr(error)
    eligible = eligibility_error is None
    raw = root / 'commit_trace.csv'
    evidence = dict(terminal.get('evidence_pins', {}))
    for path in (RUN / 'complete.json', root / 'child_outcome.unvalidated.json',
                 root / 'command.json', root / 'console.log', root / 'checker_firstfailure.json'):
        if path.exists():
            evidence.setdefault(str(path), sha(path))
    verify(evidence, [raw])
    save(OUT / 'evidence_pre.json', evidence)
    spec = plan['specs'][w.NAME]
    require(spec == w.checker.specification(Path(plan['cases'][0]['elf'])), 'Actual SoC spec')
    if eligible:
        w.common.check_artifacts(result, plan['cases'][0], ledger)
        for p in (root / 'console.log', root / 'work/run.vcs.log'):
            w.checker.console_gate(p.read_text())
    before = base.raw_identity(raw)
    stream = base.HashLines(raw)
    observer, events = Observer(protocol), []
    semantic, generic, binding, diagnostic = None, None, None, None
    try:
        semantic = w.checker.source.audit(w.checker.convert(observer.rows(csv.DictReader(stream)), events), spec)
        generic = observer.finish()
        binding = w.checker.protocol_gate(events, semantic, generic)
    except Exception as error:
        diagnostic = getattr(error, 'diagnostic', {'original_firstcause': repr(error)})
    finally:
        # After the first semantic rejection only hash the unread bytes, never reparse.
        for block in iter(lambda: stream.stream.read(1048576), b''):
            stream.hash.update(block)
            stream.bytes += len(block)
        stream.stream.close()
    require(base.raw_identity(raw) == before and stream.bytes == before[2], 'Closed CSV changed or missing EOF')
    raw_sha = stream.hash.hexdigest()
    if str(raw) in evidence:
        require(evidence[str(raw)] == raw_sha, 'Producer full CSV hash mismatch')
    evidence[str(raw)] = raw_sha
    verify(evidence, [raw])
    ready_gate(digest)
    require(sha(RUN / 'complete.json') == closure['complete_sha256'], 'Late complete drift')
    save(OUT / 'evidence_post.json', evidence)
    if eligible and diagnostic is None:
        require(semantic['retired'] == generic['retire_count'], 'Retire count agreement')
        require([semantic[k] for k in ('target_calls', 'full_result_bit_checks', 'guard_checks',
                'returned_vstart_zero', 'returned_flags_checked', 'helper_instructions')]
                == [700, 358400, 1400, 700, 700, 12880], 'Full700 exact oracle')
        require(sum(r['backend_required'] for r in semantic['retired_offloads']) == 3396,
                '2800 memory plus596 nonempty target owners')
        previous = read(root / 'strict_original.json')
        require(json.loads(json.dumps(semantic)) == previous['strict'] and generic == previous['generic']
                and binding == previous['protocol'] and raw_sha == previous['csv_sha256'], 'Independent result agreement')
        require(dict(generic, status='VALID') == read(root / 'trace_summary.json'), 'Six-event generic agreement')
        save(OUT / 'full_strict.json', semantic)
        status = 'PASS_INDEPENDENT_ORIGINAL700_NOT_FULL17920_OR_LINUX'
    else:
        status = 'NOT_ACCEPTED_CLOSED_PREFIX_DIAGNOSTIC'
    save(OUT / 'result.json', dict(status=status, producer_status=terminal.get('status'),
         eligibility_error=eligibility_error, first_error=diagnostic, generic=generic, protocol=binding,
         csv_sha256=raw_sha, csv_bytes=stream.bytes, csv_parses=1, complete_sha256=closure['complete_sha256'],
         scope='700 contiguous original calls/699 predecessors,358400bits,1400guards,700flags/vstart',
         required_owners=3396, raw_identity=before, producer_service=closure['producer_service'],
         no_DUT_REF_build=True, no_retry=True, pins_unchanged=True,
         full_parent_accepted=False, direct_vector_payload_claimed=False))
    return 0 if status.startswith('PASS_') else 1


def prepare():
    require(not (HERE / 'READY.json').exists(), 'Fresh collector seal')
    w, _, _ = modules()
    require(sha(RUN / 'plan.json') == PLAN and sha(WORK / 'ENTRY.json') == ENTRY, 'Admitted exact plan')
    launch = read(RUN / 'launch.json')
    pid = launch['owner']['pid']
    proc = Path('/proc') / str(pid)
    argv = (proc / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
    require('--parent-review-sha256' in argv and argv[argv.index('--parent-review-sha256') + 1] == ENTRY,
            'Actual ENTRY invocation')
    cgroup = launch['owner']['properties']['ControlGroup']
    require((proc / 'cgroup').read_text().strip() == '0::' + cgroup, 'Actual producer cgroup')
    pins = dict(read(RUN / 'plan.json')['pins'])
    paths = [HERE / 'collect.py', HERE / 'test_collect.py', HERE / 'host01.json', GENERIC,
             TEMPLATE / 'audit.py', TEMPLATE / 'observer.py', WORK / 'ENTRY.json', RUN / 'plan.json',
             RUN / 'launch.json', RUN / 'launch_invocation.json', RUN / 'launch_process_exit.json',
             RUN / 'launch_receipt.json', RUN / 'startup_observation.json']
    for mod in list(sys.modules.values()):
        p = getattr(mod, '__file__', None)
        if p and Path(p).is_file() and Path(p).resolve().is_relative_to(HERE.parents[4]):
            paths.append(Path(p).resolve())
    for path in paths:
        pins[str(path)] = sha(path)
    save(HERE / 'READY.json', dict(status='SEALED_CONDITIONAL_COLLECTOR_NOT_ACCEPTANCE', pins=pins,
         worker_pid=pid, worker_command=argv, worker_cgroup=cgroup,
         worker_start_ticks=int((proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]),
         worker_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
         wait_seconds=WAIT, audit_seconds=AUDIT, outer_seconds=10800,
         authority='Main authorized one independent conditional terminal collector; Zeno sole DUT launcher',
         service=UNIT, plan_sha256=PLAN, entry_sha256=ENTRY))
    print(sha(HERE / 'READY.json'))


def attach(digest):
    ready = ready_gate(digest)
    require(not OUT.exists(), 'One fresh attachment only')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == ready['worker_boot_id'], 'Boot identity')
    OUT.mkdir()
    try:
        fd = os.pidfd_open(ready['worker_pid'])
        try:
            proc = Path('/proc') / str(ready['worker_pid'])
            base.identity((proc / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0'),
                          (proc / 'cgroup').read_text(),
                          int((proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]), ready)
            own = systemd(UNIT)
            require(own['MainPID'] == str(os.getpid()) and own['SubState'] == 'running', 'Direct collector service')
            save(OUT / 'attached.json', dict(status='PIDFD_ATTACHED_NO_ACTIVE_CSV_READ',
                 worker_pid=ready['worker_pid'], observer_pid=os.getpid(), collector_service=own,
                 ready_sha256=digest, plan_sha256=PLAN, entry_sha256=ENTRY, time=time.time()))
            poller = select.poll()
            poller.register(fd, select.POLLIN)
            events = poller.poll(WAIT * 1000)
            require(events and any(f & select.POLLIN for _, f in events)
                    and all(not f & select.POLLNVAL for _, f in events), 'Bounded pidfd wait failed')
        finally:
            os.close(fd)
        group = base.empty_cgroup(ready['worker_cgroup'])
        # A short bounded settle handles the manager processing the same exit event.
        for _ in range(10):
            props = systemd('ara-fp-alias-original700-m9-01.service')
            if exited(props):
                break
            time.sleep(0.2)
        require(exited(props), 'No actual terminal service evidence')
        save(OUT / 'closed.json', dict(producer_service=props, cgroup=group,
             complete_sha256=sha(RUN / 'complete.json'), pidfd_exit=True, CSV_content_reads=0))
        command = [sys.executable, '-B', str(HERE / 'collect.py'), 'audit', '--ready-sha256', digest]
        save(OUT / 'attempt.json', dict(command=command, timeout_s=AUDIT, retries=0))
        with (OUT / 'audit.log').open('x') as log:
            start = time.monotonic()
            p = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            code, timeout = base.wait_child(p, start, AUDIT)
        result_path = OUT / 'result.json'
        accepted = code == 0 and not timeout and result_path.exists() and read(result_path)['status'].startswith('PASS_')
        save(OUT / 'TERMINAL.json', dict(status='PASS_INDEPENDENT_ORIGINAL700' if accepted else 'NOT_ACCEPTED',
             actual_audit_returncode=code, timed_out=timeout,
             result_sha256=sha(result_path) if result_path.exists() else None,
             actual_exit_sha256=sha(OUT / 'actual_exit_unvalidated.json'), plan_sha256=PLAN,
             ready_sha256=digest, producer_service=props, no_retry=True))
        return 0 if accepted else 1
    except BaseException as error:
        save(OUT / 'STOPPED.json', dict(status='NOT_ACCEPTED_FIRST_ERROR_NO_RETRY', error=repr(error),
             producer_not_stopped=True, no_DUT_REF_build=True))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'attach', 'audit'])
    parser.add_argument('--ready-sha256')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare()
    else:
        require(args.ready_sha256, 'Sealed digest required')
        raise SystemExit(attach(args.ready_sha256) if args.mode == 'attach' else audit(args.ready_sha256))
