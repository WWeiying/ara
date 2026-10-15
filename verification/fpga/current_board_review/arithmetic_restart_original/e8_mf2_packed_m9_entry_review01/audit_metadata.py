"""Read-only frozen entry metadata/pin audit, not a Host or trace test."""
import hashlib
import json
from pathlib import Path
import shlex

HERE = Path(__file__).resolve().parent
WORK = HERE.parent / 'full_e8_mf2_packed_vcs_m9_plan01'
OUT = WORK / 'prepared01'
EXPECTED = '6ed1c1ffafeddb136962cf49ab10e761441e9bf3d24be67a71770a2245a2ea3f'

def read(path):
    return json.loads(Path(path).read_text())

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

assert sha(OUT / 'plan.json') == EXPECTED
plan = read(OUT / 'plan.json')
assert plan['status'] == 'PREPARED_NOT_RUN'
assert len(plan['pins']) == 796
for path, digest in plan['pins'].items():
    assert sha(path) == digest, path
host = read(WORK / 'host01.json')
receipt = read(WORK / 'host01_process_exit.json')
assert host['status'] == 'PASS_HOST_ONLY' and host['tests'] == 25 and host['failures'] == 0
assert host['full4095_streams'] == 1 and host['actual_abi_entry_checked'] is True
assert host['CSV_reads'] == host['DUT_reference_build_runs'] == 0
assert type(receipt['returncode']) is int and receipt['returncode'] == 0
assert receipt['timed_out'] is False and receipt['pins_unchanged'] is True and receipt['retries'] == 0
assert 0 < receipt['elapsed_s'] <= 600
assert all(plan['pins'][path] == digest for path, digest in host['pins'].items())
assert [plan[k] for k in ('jobs', 'case_timeout_s', 'worker_timeout_s', 'service_timeout_s', 'reserved_slots')] == [1, 10800, 12000, 13200, 0]
assert all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb', 'stop_first_fail'))
assert plan['owner_counts'] == dict(compulsory_memory_owners=20475, required_target_owners=2610,
    required_op24_memory_targets=117, minimum_required_owners=23085)
case, = plan['cases']
assert case['id'] == 'arithmetic_original_e8_mf2_full4095_packed'
assert case['sha256'] == '5e901ae235792e40de311713125a7a37a480a3e266c3a7c8d8d4887bb8433839'
assert sha(case['elf']) == case['sha256'] and case['timeout_s'] == 10800
ready, dry = read(OUT / 'ready.json'), read(OUT / 'dryrun.json')
assert ready['plan_sha256'] == dry['plan_sha256'] == EXPECTED
assert ready['DUT_started'] is False and dry['status'] == 'DRYRUN_ONLY_NO_PROCESS'
image = Path(plan['image'])
assert image.parent.parent.name == 'current_board_memory_candidate09'
assert sha(image / 'image.json') == plan['image_sha256']
root = OUT / 'replay/tests' / case['id']
assert dry['commands'] == [dict(cwd=str(root / 'work'), command=[read(image / 'image.json')['simv'],
    '-l', 'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD=' + str(root / 'input.elf'),
    '+TESTCASE=' + case['id'], '+NO_FSDB', '+COMMIT_TRACE=' + str(root / 'commit_trace.csv')])]
assert ready['command'] == ['/usr/bin/python3', '-B', str(WORK / 'replay.py'), 'run', '--image',
    str(image), '--out', str(OUT), '--plan-sha256', EXPECTED, '--authorize-run']
service = shlex.split(ready['service_command'])
assert service[-len(ready['command']):] == ready['command']
for prop in ('RuntimeMaxSec=13200', 'TimeoutStopSec=360', 'KillMode=control-group', 'Restart=no',
    'ExecStopPost=/usr/bin/python3 -B ' + str(WORK / 'exit_hook.py') + ' --out ' + str(OUT)):
    assert '--property=' + prop in service
assert '--unit=' + plan['unit'] in service
assert not (OUT / 'launch_invocation.json').exists()
evidence = {str(path): sha(path) for path in (OUT / 'plan.json', OUT / 'ready.json', OUT / 'dryrun.json',
    WORK / 'host01.json', WORK / 'host01_process_exit.json', Path(__file__).resolve())}
result = dict(status='NO_BLOCKER_ENTRY_REVIEW', plan_sha256=EXPECTED,
    image_sha256=plan['image_sha256'], reference_ready_sha256=plan['reference_ready_sha256'],
    scope=[case['id']], pins=plan['pins'], independent_evidence_pins=evidence,
    full_pin_count=796, host_actual_wait=receipt, raw_semantic_reparses=0,
    reviewer_DUT_Host_reference_build_runs=0, source_port_only=True, original_Linux_closed=False,
    execution_owner='Aquinas; single conditional launch; reviewer does not launch')
with (HERE / 'result.json').open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(status=result['status'], pins=796, result_sha256=sha(HERE / 'result.json'),
    host_actual_elapsed_s=receipt['elapsed_s'], plan_sha256=EXPECTED)))
