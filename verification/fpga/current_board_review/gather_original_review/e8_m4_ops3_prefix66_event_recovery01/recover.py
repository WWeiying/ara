"""One offline recovery of the completed DUT data, preserving the worker ERROR."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'e8_m4_ops3_prefix66_vcs_m6_plan01'
P = OLD / 'prepared01'
ROOT = P / 'replay/tests/gather_prefix_e8_m4_ops3'
NAME = 'gather_prefix_e8_m4_ops3'
PLAN_SHA = '5de3a259e330825548009fbe17a4f80da34c3a6b816b495a695564621ea4ddbb'
OLD_CHECKER_SHA = '959689ad2d2a26d1a879b5c0f9fe7d1b1b8f7f03071a8101a5058fa5a5841b59'
G = HERE.parents[1]
TRANSPORT = G / 'ordered_reduction/original_remaining9_terminal_audit01/observer.py'
TRACE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/verification/ara_verify/trace.py')
sys.path.insert(0, str(OLD))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fixed = load(HERE / 'checker.py', 'gather_terminal_event_corrected_checker')
require, read, sha = fixed.require, fixed.read, fixed.sha


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def identity(path):
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def admission():
    require(sha(P / 'plan.json') == PLAN_SHA and sha(OLD / 'checker.py') == OLD_CHECKER_SHA,
            'Sealed plan/checker changed')
    plan = read(P / 'plan.json')
    fixed.common.base.verify_pins(plan['pins'])
    done = read(P / 'complete.json')
    cause = read(P / 'first_cause.json')
    require(done['status'] == 'NOT_PASS' and done['aborted'] is True and done['retries'] == 0
            and done['plan_sha256'] == PLAN_SHA, 'Original metadata ERROR must remain')
    require(cause['kind'] == 'POSTCHECK_EXCEPTION'
            and cause['error'] == 'ValueError: Cycle reversal/unknown event/exception'
            and type(cause['returncode']) is int and cause['returncode'] == 0
            and type(cause['runner_returncode']) is int and cause['runner_returncode'] == 0,
            'Not the proven event-whitelist postcheck failure')
    require(len(done['results']) == 1 and done['results'][0]['name'] == NAME
            and done['results'][0]['status'] == 'ERROR'
            and done['results'][0]['reason'] == cause['error'], 'Unexpected original result')
    monitor = read(ROOT / 'child_outcome.unvalidated.json')
    require(type(monitor['returncode']) is int and monitor['returncode'] == 0
            and monitor['timed_out'] is False and monitor['failure_seen'] is False
            and monitor['name'] == NAME and 0 < monitor['elapsed_s'] <= 5400,
            'No actual successful simulator outcome')
    command = read(ROOT / 'command.json')
    require(command['command'] == monitor['command'] and command['cwd'] == monitor['cwd']
            and monitor['cwd'] == str(ROOT / 'work'), 'Actual monitor command differs')
    expected = [plan['image'] + '/_build/vcs/simv', '-l', 'run.vcs.log', '+ntb_random_seed=1',
                '+PRELOAD=' + str(ROOT / 'input.elf'), '+TESTCASE=' + NAME, '+NO_FSDB',
                '+COMMIT_TRACE=' + str(ROOT / 'commit_trace.csv')]
    require(command['command'] == expected, 'Private DUT command differs')
    inputs = read(ROOT / 'inputs.json')
    require(inputs['binary'] == dict(source=plan['case']['elf'], path=str(ROOT / 'input.elf'),
                                    sha256=plan['case']['sha256'])
            and sha(ROOT / 'input.elf') == plan['case']['sha256'], 'Actual private ELF differs')
    require(inputs['simv']['path'] == expected[0], 'Actual simulator differs')
    fixed.common.base.verify_pins(inputs['simv']['image_sha256'])
    metadata = read(P / 'replay/run.json')
    require(metadata['status'] == 'COMPLETE' and metadata['tests'] == [NAME]
            and metadata['jobs'] == 1 and metadata['timeout_s'] == 5400
            and metadata['seed'] == 1 and metadata['commit_trace'] is True,
            'Original execution scope changed')
    for name in ('console.log', 'work/run.vcs.log'):
        fixed.console_gate((ROOT / name).read_text())
    generic = read(ROOT / 'trace_summary.json')
    require(generic['status'] == 'VALID' and generic['cvx_exception_count'] == 0,
            'Frozen generic validation did not pass')
    return plan, done, monitor, generic


def main(checker_sha, host_sha):
    require(__debug__ and sha(HERE / 'checker.py') == checker_sha
            and sha(HERE / 'host.json') == host_sha, 'Reviewed recovery inputs required')
    host = read(HERE / 'host.json')
    require(host['status'] == 'PASS_HOST_ONLY_NOT_DUT' and host['failures'] == host['errors'] == 0,
            'Recovery Host checks failed')
    fixed.common.base.verify_pins(host['pins'])
    plan, done, monitor, stored_generic = admission()
    out = HERE / 'offline01'
    require(not out.exists(), 'No retry or overwrite')
    pins = dict(plan['pins'])
    paths = [HERE / n for n in ('checker.py', 'test_recovery.py', 'host.json', 'recover.py')]
    paths += [P / n for n in ('plan.json', 'complete.json', 'first_cause.json')]
    paths += [ROOT / n for n in ('input.elf', 'inputs.json', 'command.json', 'console.log',
                                'work/run.vcs.log', 'trace_summary.json', 'child_outcome.unvalidated.json')]
    paths += [P / 'replay/run.json', TRANSPORT, TRACE]
    pins.update({str(p): sha(p) for p in paths})
    out.mkdir()
    save(out / 'input_pins.json', pins)
    save(out / 'invocation.json', dict(pid=os.getpid(), argv=sys.argv, started=time.time(),
                                     no_DUT=True, original_worker_ERROR_preserved=True))
    mature = load(TRANSPORT, 'gather_recovery_lossless_transport')
    trace = load(TRACE, 'gather_recovery_frozen_trace')

    class Observer(mature.Observer):
        def __init__(self):
            self.count, self.pcs = Counter(), Counter()
            self.pending, self.uops = {}, {}
            self.requests, self.arch, self.retvec = [], [], []
            self.first = self.last = -1
            self.maxcvx = self.maxuop = 0
            self.before, self.after = hashlib.sha256(), hashlib.sha256()

        def retirement(self, row, cycle, insn, order):
            pass

        def finish(self):
            require(not self.pending and not self.uops, 'Uncompleted interface transactions')
            require(self.count['rows'] == self.count['unmodified_delivered_rows']
                    and self.before.digest() == self.after.digest(), 'Rows changed or lost')
            return dict(rows=self.count['rows'], first_cycle=self.first, last_cycle=self.last,
                        retire_count=self.count['retire'], vector_retire_count=len(self.retvec),
                        cvx_request_count=self.count['cvx_req'], cvx_response_count=self.count['cvx_resp'],
                        cvx_max_inflight=self.maxcvx,
                        cvx_replay_count=trace._validate_retired_request_sequence(self.retvec, self.requests),
                        arch_request_replay_count=trace._validate_retired_request_sequence(self.arch, self.requests),
                        cvx_exception_count=0, architecture_request_count=len(self.arch),
                        backend_uop_alloc_count=self.count['uop_alloc'],
                        backend_uop_done_count=self.count['uop_done'], backend_uop_max_inflight=self.maxuop)

    path = ROOT / 'commit_trace.csv'
    before = identity(path)
    digest, observer = hashlib.sha256(), Observer()
    start = time.monotonic()
    try:
        with path.open('rb') as stream:
            def lines():
                for line in stream:
                    digest.update(line)
                    yield line.decode('utf-8')
            strict = fixed.retirement(observer.rows(csv.DictReader(lines())), plan['spec'], fixed.model())
        generic = observer.finish()
        require(identity(path) == before and dict(generic, status='VALID') == stored_generic,
                'CSV changed or frozen generic result differs')
        require((strict['csv_rows'], strict['csv_last_cycle'], strict['retired_rows'])
                == (generic['rows'], generic['last_cycle'], generic['retire_count']), 'Counts differ')
        require((strict['fullcap_checks'], strict['guards'], strict['returned_vstart_zero'],
                 strict['helper_instruction_retirements']) == (33792, 132, 66, 858), 'Incomplete numeric scope')
        fixed.common.base.verify_pins(pins)
        require(identity(path) == before, 'CSV changed after traversal')
        report = dict(status='ARCHITECTURAL_PREFIX66_ACCEPTED_OLD_WORKER_ERROR_PRESERVED',
                      plan_sha256=PLAN_SHA, generic=generic, strict=strict,
                      actual_monitor=monitor, csv_sha256=digest.hexdigest(), csv_identity=before,
                      csv_parses=1, seconds=time.monotonic()-start, pins_pre_post_unchanged=True,
                      original_worker_status=done['status'], original_worker_aborted=done['aborted'],
                      original_worker_relabelled=False, new_DUT_runs=0, RTL_changes=0,
                      unknown_stall_closed=False, full2688_accepted=False, Linux_execution=False)
        save(out / 'result.json', report)
        print(report['status'], generic['rows'], flush=True)
    except BaseException as error:
        save(out / 'NOT_ACCEPTED.json', dict(status='NOT_ACCEPTED_NO_RETRY', error=repr(error),
                                           original_worker_ERROR_preserved=True))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-recovery', action='store_true')
    parser.add_argument('--checker-sha256', required=True)
    parser.add_argument('--host-sha256', required=True)
    args = parser.parse_args()
    require(args.authorize_recovery, 'Recovery must be explicitly authorized after review')
    main(args.checker_sha256, args.host_sha256)
