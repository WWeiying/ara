"""Read-only frozen entry metadata/pin audit, not a Host or trace test."""
import hashlib
import json
from pathlib import Path
import shlex

HERE = Path(__file__).resolve().parent
WORK = HERE.parent / 'full_e8_m1_packed_vcs_m9_plan01'
OUT = WORK / 'prepared01'
EXPECTED = '150703ba0c1dc2baf5fd6c68d21fa465fd8302056071405fee8ada05c8b4aa04'

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
ref = HERE.parent / 'full_e8_m1_packed_prepare01'
raw = ref / 'reference01/commits.log'
assert sha(ref / 'reference01/result.json') == '6e46a6e2f37ce61fc0579af4c1d8712c9d0ebec535c31bb4eaa629d811abb8ba'
for path, digest in plan['pins'].items():
    if Path(path) == raw:
        assert digest == '80e1f0d351e0ddabc40bbf4aceae8e5585b09d215c2170d5f650bb521b8ebed9'
        assert raw.stat().st_size == 108320800
    else:
        assert sha(path) == digest, path
assert str(raw) in plan['pins']
host = read(WORK / 'host01.json')
receipt = read(WORK / 'host01_process_exit.json')
assert host['status'] == 'PASS_HOST_ONLY' and host['tests'] == 28 and host['failures'] == 0
assert host['full4095_streams'] == 1 and host['actual_abi_entry_checked'] is True
assert host['CSV_reads'] == host['DUT_reference_build_runs'] == 0
assert type(receipt['returncode']) is int and receipt['returncode'] == 0
assert receipt['timed_out'] is False and receipt['pins_unchanged'] is True and receipt['retries'] == 0
assert 0 < receipt['elapsed_s'] <= 600
assert all(plan['pins'][path] == digest for path, digest in host['pins'].items())
assert [plan[k] for k in ('jobs', 'case_timeout_s', 'worker_timeout_s', 'service_timeout_s', 'reserved_slots')] == [1, 10800, 12000, 13200, 0]
assert all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb', 'stop_first_fail'))
assert plan['owner_counts'] == dict(compulsory_memory_owners=20475, required_target_owners=2592,
    required_op24_memory_targets=117, minimum_required_owners=23067)
rows = read(ref / 'sequence.json')
helpers = read(ref / 'proof.json')['backends']['soc']['helpers']
assert len(rows) == 4095
required = []
noops = []
for row in rows:
    insn = helpers[f'op_{row["op"]}'][8]['insn']
    original_window = row['start'] < row['vl']
    is_slide = (insn & 127) == 0x57 and ((insn >> 12) & 7) == 3 and (insn >> 26) == 14
    if is_slide:
        assert row['op'] == 19 and insn == 0x38813c57
        offset = (insn >> 15) & 31
        assert offset == 2
    null_slide = is_slide and ((insn >> 15) & 31) >= row['vl']
    required.append(original_window and not null_slide)
    if original_window and null_slide:
        noops.append(row['ordinal'])
assert len(noops) == 18 and sum(required) == 2592
derived = dict(compulsory_memory_owners=5*len(rows), required_target_owners=sum(required),
    required_op24_memory_targets=sum(need and row['op']==24 for row,need in zip(rows,required)),
    minimum_required_owners=5*len(rows)+sum(required))
assert plan['owner_counts'] == derived
profile = read(WORK / 'reset_profile.json')
assert profile['allowed_shape'] == 'rvv_matrix_e8_m1'
assert profile['initial_gpr_values'] == [0]*32 and profile['FpgaEn'] == 0
assert profile['image_sha256'] == plan['image_sha256']
assert profile['original_soc_elf_sha256'] == '60ce49d374a4b8491d503f3159d3d13c32489e30141b3a52192ea8f47eb01621'
case, = plan['cases']
assert case['id'] == 'arithmetic_original_e8_m1_full4095_packed'
assert case['sha256'] == '60ce49d374a4b8491d503f3159d3d13c32489e30141b3a52192ea8f47eb01621'
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
    full_pin_count=796, fresh_file_hash_checks=795,
    reference_raw_pin='Previously accepted exact digest and current size; no raw reread by reviewer; worker rehashes at admission',
    independent_derived_owner_counts=derived, exact_noop_one_based_ordinals=noops,
    host_actual_wait=receipt, raw_semantic_reparses=0,
    reviewer_DUT_Host_reference_build_runs=0, source_port_only=True, original_Linux_closed=False,
    execution_owner='Aquinas; single conditional launch; reviewer does not launch')
with (HERE / 'result.json').open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(status=result['status'], pins=796, result_sha256=sha(HERE / 'result.json'),
    host_actual_elapsed_s=receipt['elapsed_s'], plan_sha256=EXPECTED)))
