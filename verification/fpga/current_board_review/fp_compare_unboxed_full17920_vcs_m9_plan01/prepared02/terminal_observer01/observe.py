"""One filesystem-event observation; no simulator queries or CSV reads."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = OUT.parent
NAME = 'fp_compare_unboxed_e16_mf4_full17920'
# Exact prepared02 identity, independent of any later on-disk metadata.
PLAN = 'b6d0677124a045a35294a1c0be4a7b0f6a004f52e9f570e6e5b9478c4296bdbd'
READY = '89c37924aefdcca6ada87dfb1430ce0bc8e6853c4827297eec10340b37e1339f'
START = 1792024000.28614
DEADLINE = START + 13200 + 300 + 60


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def save(name, value):
    path = HERE / name
    with path.with_suffix(path.suffix + '.tmp').open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    require(not path.exists(), 'Refuse overwrite ' + str(path))
    os.rename(path.with_suffix(path.suffix + '.tmp'), path)


def await_terminal():
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes = [ctypes.c_int]
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'inotify_init1')
    try:
        require(libc.inotify_add_watch(fd, os.fsencode(OUT), 0x08 | 0x80) >= 0, 'inotify watch failed')
        save('attached.json', dict(pid=os.getpid(), attached_at=time.time(), directory=str(OUT),
             required=['collector_result.json', 'collector.wait.json'], absolute_deadline=DEADLINE,
             mechanism='inotify IN_CLOSE_WRITE / IN_MOVED_TO; watch-before-existence',
             simulator_queries=0, CSV_reads=0, extends_DUT_budget=False))
        while not all((OUT / n).is_file() for n in ['collector_result.json', 'collector.wait.json']):
            remaining = DEADLINE - time.time()
            require(remaining > 0, 'Observation deadline: missing terminal receipts, NOT acceptance')
            require(select.select([fd], [], [], remaining)[0], 'Observation deadline: no terminal event')
            os.read(fd, 65536)
    finally:
        os.close(fd)


def audit():
    answer = dict(status='NOT_ACCEPTED', semantic_CSV_reads=0, DUT_rerun=False,
                  numerical_reaudit=False, linux_acceptance=False)
    try:
        await_terminal()
        require(sha(OUT/'plan.json') == PLAN and sha(OUT/'ready.json') == READY, 'Plan/ready identity')
        plan = read(OUT/'plan.json')
        require(len(plan['cases']) == 1 and plan['cases'][0]['id'] == NAME and
                plan['cases'][0]['historical_name'] == 'rvv_fp_compare_unboxed_unmasked_e16_mf4' and
                plan['cases'][0]['sha256'] == '19afd0c6fd9c0810efbfdd9a635d092672554e6a1f3d4a3a537af00c4de13e37',
                'Exact original source/runtime/ELF scope')
        require(sha(plan['cases'][0]['elf']) == plan['cases'][0]['sha256'], 'Small original ELF identity')
        require(plan['unit'] == 'ara-fp-unboxed-full17920-m9-01.service', 'Exact unit')
        require([plan[k] for k in ['jobs', 'case_timeout_s', 'worker_timeout_s', 'service_timeout_s']] ==
                [1, 10800, 12000, 13200], 'Original budgets')
        require(plan['service_terminal_contract']['RemainAfterExit'] is False, 'Automatic terminal hook')
        result = read(OUT/'collector_result.json')
        wait = read(OUT/'collector.wait.json')
        contract = plan['service_terminal_contract']
        for key in ['exit_hook', 'collector']:
            require(sha(contract[key]) == contract[key+'_sha256'], 'Terminal executable drift: '+key)
        command = read(OUT/'collector.command.json')
        require(command['command'][1:] == ['-B', contract['collector'], '--out', str(OUT)] and
                command['timeout_s'] == 180 and command['plan_sha256'] == PLAN, 'Actual collector command')
        require(type(wait['actual_wait_exit']) is int and wait['actual_wait_exit'] == 0 and
                wait['timed_out'] is False, 'Actual collector wait0 required: ' + repr(wait))
        require(sha(OUT/'collector.log') == wait['log_sha256'], 'Collector log receipt')
        require(result['status'] == 'PASS_FULL17920_M9_METADATA_COLLECTED_NOT_LINUX',
                'Collector not accepted: ' + repr(result.get('error', result['status'])))
        for p, h in result['evidence_pins'].items():
            require(Path(p).name != 'commit_trace.csv', 'Metadata-only evidence set')
            require(sha(p) == h, 'Collector evidence drift: ' + p)
        complete = read(OUT/'complete.json')
        hook = read(OUT/'service_exit.json')
        require(hook == result['service_exit'] and hook['kind'] == 'ACTUAL_SYSTEMD_EXEC_STOP_POST' and
                [hook[k] for k in ['SERVICE_RESULT', 'EXIT_CODE', 'EXIT_STATUS']] == ['success','exited','0'],
                'Actual service exit receipt; no GC inference')
        require(complete['plan_sha256'] == PLAN and result['plan_sha256'] == PLAN and
                complete['status'] == 'PASS_M9_FULL17920_UNBOXED_SOURCE_PORT_NOT_LINUX' and
                complete['pins_unchanged'] is True and complete['aborted'] is False and complete['retries'] == 0 and
                complete['full_parent'] is True and complete['linux'] is False,
                'Producer complete and no abort')
        rows = complete['results']
        require(len(rows) == 1 and rows[0]['name'] == NAME and rows[0]['status'] == 'PASS' and
                type(rows[0]['returncode']) is int and rows[0]['returncode'] == 0, 'Exact one outcome')
        case = OUT/'replay/tests'/NAME
        numeric = read(case/'child_outcome.unvalidated.json')
        require(numeric == result['actual_simulator_wait'] and type(numeric['returncode']) is int and
                numeric['returncode'] == 0 and numeric['timed_out'] is False and numeric['failure_seen'] is False and
                0 < numeric['elapsed_s'] <= 10800, 'Actual persisted simulator outcome')
        report = read(case/'strict_original.json')
        strict, generic, owners = report['strict'], report['generic'], report['owners']
        expected = dict(calls=17920, result_bits=286720, guards=35840, flags=17920, vstarts=17920,
                        helper_instructions=326144, capacity_instructions=3, fresh_stores=734720,
                        input_LD=143360, output_LWU=17920, record_LD=2240, FPR_committed_writebacks=10752)
        require(all(strict[k] == v for k,v in expected.items()), 'Complete source obligations')
        require(strict['status'] == 'FULL17920_RVFI_SOURCE_PARENT_ACCEPTED_NOT_LINUX', 'Strict accepted status')
        require(strict['raw_scalar_seed_counts'] == {str(i):336 for i in range(32)}, 'All32 FPR seed histories')
        require(owners['contract'] == plan['owner_contract'] == result['owner_contract'] ==
                dict(memory=89600, target_required=15360, target_elidable=2560) and
                owners['status'] == 'EVERY_NECESSARY_OWNER_COMPLETED', 'Source-derived owner contract')
        require(strict['rows'] == generic['rows'] and strict['retired'] == generic['retire_count'] and
                generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] > 0 and
                generic['cvx_exception_count'] == 0 and report['closed_semantic_passes'] == 1,
                'Existing full strict/protocol report')
        require(complete['evidence_pins'][str(case/'commit_trace.csv')] == report['csv_sha256'] ==
                result['csv_identity_inherited_from_complete'], 'Closed CSV digest linkage, not reread')
        run = read(OUT/'replay/run.json')
        require(run['status'] == 'COMPLETE' and run['tests'] == [NAME] and run['status_counts'] == {'PASS':1},
                'Exact runner membership')
        answer.update(status='ACCEPTED_FULL17920_M9_METADATA_REVIEW_NOT_LINUX', scope=expected,
                      actual_simulator_elapsed_s=numeric['elapsed_s'], collector_wait=wait, service_exit=hook,
                      owner_contract=owners['contract'], rows=strict['rows'], plan_sha256=PLAN,
                      CSV_identity_inherited=report['csv_sha256'], input_pin_count=len(plan['pins']),
                      producer_pins_unchanged=True, FPR_evidence='committed writeback, not physical FPR readback',
                      evidence_pins={str(p):sha(p) for p in [OUT/'collector_result.json', OUT/'collector.wait.json',
                          OUT/'complete.json', OUT/'service_exit.json', OUT/'plan.json', OUT/'ready.json',
                          case/'strict_original.json', case/'child_outcome.unvalidated.json']})
    except BaseException as e:
        answer['error'] = repr(e)
    answer['finished'] = time.time()
    save('result.json', answer)
    return int(answer['status'] != 'ACCEPTED_FULL17920_M9_METADATA_REVIEW_NOT_LINUX')


def supervise():
    start = time.time()
    with (HERE/'observer.log').open('x') as log:
        child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--audit'], stdout=log, stderr=log)
        timeout = max(1, DEADLINE - time.time() + 60)
        timed_out = False
        try:
            rc = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            rc = child.wait()
    receipt = dict(actual_wait_exit=rc, timed_out=timed_out, pid=child.pid,
                   elapsed_s=time.time()-start, log_sha256=sha(HERE/'observer.log'))
    save('observer.wait.json', receipt)
    status = read(HERE/'result.json')['status'] if (HERE/'result.json').exists() else 'MISSING_RESULT_NOT_ACCEPTED'
    save('notification.json', dict(status=status, actual_observer_wait=receipt,
         result=str(HERE/'result.json'), result_sha256=sha(HERE/'result.json') if (HERE/'result.json').exists() else None,
         finished=time.time()))
    return rc


if __name__ == '__main__':
    raise SystemExit(audit() if sys.argv[1:] == ['--audit'] else supervise())
