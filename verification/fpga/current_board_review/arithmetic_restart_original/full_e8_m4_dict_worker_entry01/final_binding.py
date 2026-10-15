"""Bind the completed narrow static review; never starts worker or tests."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORK = HERE.parent / 'full_e8_m4_dict_vcs_m9_plan01'
OUT = WORK / 'prepared01'
DIGEST = '4df0c5b631b8645fb51a4ca52ca1bb916dec03ad455e88c0a380a5b023f2c2db'
sys.path.insert(0, str(WORK))
import replay as worker


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    start = time.time()
    assert sha(OUT / 'plan.json') == DIGEST
    plan = read(OUT / 'plan.json')
    worker.validate(plan, worker.IMAGE)
    host = read(WORK / 'host03.json')
    host_exit = read(WORK / 'host03_process_exit.json')
    assert host['status'] == 'PASS_HOST_ONLY' and host['tests'] == 20 and host['failures'] == 0
    assert type(host_exit['returncode']) is int and host_exit['returncode'] == 0
    assert host_exit['timed_out'] is False and host_exit['elapsed_s'] < 300
    for name, digest in host['pins'].items():
        path = Path(name)
        if path.name == 'replay.py':
            path = WORK / 'host03_code/replay.py'
        assert sha(path) == digest, str(path)
    clone = read(WORK / 'host_clone_result.json')
    clone_exit = read(WORK / 'host_clone_execution.json')
    assert clone['status'] == 'PASS_COMPLETE_MUTABLE_CLONE'
    assert type(clone_exit['actual_wait_returncode']) is int and clone_exit['actual_wait_returncode'] == 0
    assert clone_exit['elapsed_s'] < 30
    for name, digest in clone['pins'].items():
        assert sha(Path(name)) == digest, name
    ready = read(OUT / 'ready.json')
    dryrun = read(OUT / 'dryrun.json')
    assert ready['plan_sha256'] == dryrun['plan_sha256'] == DIGEST
    assert ready['DUT_started'] is False and dryrun['status'] == 'DRYRUN_ONLY_NO_PROCESS'
    assert len(dryrun['commands']) == 1
    case, = plan['cases']
    root = OUT / 'replay/tests' / case['id']
    image = read(worker.IMAGE / 'image.json')
    assert dryrun['commands'] == [dict(cwd=str(root / 'work'), command=[
        image['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
        '+PRELOAD=' + str(root / 'input.elf'), '+TESTCASE=' + case['id'],
        '+NO_FSDB', '+COMMIT_TRACE=' + str(root / 'commit_trace.csv')])]
    service = shlex.split(ready['service_command'])
    for arg in ('--property=RuntimeMaxSec=13200', '--property=TimeoutStopSec=360',
                '--property=KillMode=control-group', '--property=Restart=no'):
        assert arg in service
    assert any(arg.startswith('--property=ExecStopPost=') and str(WORK / 'exit_hook.py') in arg for arg in service)
    assert service[-len(ready['command']):] == ready['command']
    assert sha(OUT / 'plan.json') == DIGEST
    for name, digest in plan['pins'].items():
        assert sha(Path(name)) == digest, name
    evidence = [OUT / 'plan.json', OUT / 'ready.json', OUT / 'dryrun.json',
                WORK / 'host03.json', WORK / 'host03_process_exit.json',
                WORK / 'host_clone_result.json', WORK / 'host_clone_execution.json',
                WORK / 'HOST_HISTORY.md', Path(__file__).resolve(),
                HERE / 'DRAFT01.md', HERE / 'CLONE_REVIEW01.md']
    result = dict(status='NO_BLOCKER_ENTRY_REVIEW', plan_sha256=DIGEST,
                  image_sha256=plan['image_sha256'], reference_ready_sha256=plan['reference_ready_sha256'],
                  scope=[case['id']], pins=plan['pins'], reviewer='Tesla',
                  evidence_pins={str(p): sha(p) for p in evidence},
                  host=dict(tests=20, actual_exit=host_exit, clone_actual_exit=clone_exit),
                  review_scope='Exact entry only; full4095 continuous source port, not Linux stall closure',
                  qualified_owners=dict(payload=20475, nonempty_targets=2610, op24=117),
                  preserved_history='Host01 interface failure and Host02 timeout remain; Host03 and local clone successor are distinct evidence',
                  preparation_delta='Only bind actual Host03 archived worker and complete-clone evidence; no runtime oracle relaxation',
                  constraints=dict(jobs=1, case_seconds=10800, worker_seconds=12000, service_seconds=13200,
                                   stop_seconds=360, collector_seconds=300, retry=False, fsdb=False, build=False),
                  no_new_Host_reference_CSV_or_DUT_execution=True,
                  authorized_launcher='Zeno only, existing conditional user authorization',
                  started=start, finished=time.time())
    path = HERE / 'ENTRY02.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    digest = sha(path)
    worker.reviews(plan, DIGEST, path, digest, None, None)
    print(json.dumps(dict(status=result['status'], review=str(path), sha256=digest,
                          pins=len(plan['pins']), plan_sha256=DIGEST)))


if __name__ == '__main__':
    main()
