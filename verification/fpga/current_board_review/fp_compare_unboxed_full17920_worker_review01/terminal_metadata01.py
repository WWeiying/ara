"""Independent closed metadata review; never open CSV or reference raw logs."""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
G = HERE.parent
P = G / 'fp_compare_unboxed_full17920_vcs_m9_plan01/prepared02'
T = P / 'replay/tests/fp_compare_unboxed_e16_mf4_full17920'
O = P / 'terminal_observer01'

def read(p):
    return json.loads(p.read_text())

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def zero(x):
    assert type(x) is int and x == 0

plan = read(P / 'plan.json')
complete = read(P / 'complete.json')
col = read(P / 'collector_result.json')
obs = read(O / 'result.json')
notice = read(O / 'notification.json')
report = read(T / 'strict_original.json')
strict, generic, owners = (report[x] for x in ('strict', 'generic', 'owners'))
child = read(T / 'child_outcome.unvalidated.json')
launch = read(P / 'launch.json')
plan_sha = sha(P / 'plan.json')
assert plan_sha == 'b6d0677124a045a35294a1c0be4a7b0f6a004f52e9f570e6e5b9478c4296bdbd'
for d in (complete, col, obs, launch):
    assert d['plan_sha256'] == plan_sha
assert complete['status'] == 'PASS_M9_FULL17920_UNBOXED_SOURCE_PORT_NOT_LINUX'
assert col['status'] == 'PASS_FULL17920_M9_METADATA_COLLECTED_NOT_LINUX'
assert obs['status'] == notice['status'] == 'ACCEPTED_FULL17920_M9_METADATA_REVIEW_NOT_LINUX'
assert complete['aborted'] is False and complete['retries'] == 0
assert complete['pins_unchanged'] is col['pins_unchanged'] is obs['producer_pins_unchanged'] is True
assert len(complete['results']) == 1
case = complete['results'][0]
zero(case['returncode']); zero(child['returncode'])
assert case['status'] == 'PASS' and child['kind'] == 'ACTUAL_MONITOR_WAIT'
assert child['timed_out'] is child['failure_seen'] is False
assert child == col['actual_simulator_wait']
assert case['elapsed_s'] == child['elapsed_s'] == obs['actual_simulator_elapsed_s'] < 10800
cmd = read(T / 'command.json')
assert child['command'] == cmd['command'] and child['cwd'] == cmd['cwd']
assert child['command'] == [plan['image']+'/_build/vcs/simv', '-l', 'run.vcs.log',
    '+ntb_random_seed=1', '+PRELOAD='+str(T/'input.elf'),
    '+TESTCASE='+case['name'], '+NO_FSDB', '+COMMIT_TRACE='+str(T/'commit_trace.csv')]
assert sha(T / 'input.elf') == plan['cases'][0]['sha256'] == plan['spec']['elf_sha256']
service = read(P / 'service_exit.json')
assert service == col['service_exit'] == obs['service_exit']
assert service['kind'] == 'ACTUAL_SYSTEMD_EXEC_STOP_POST'
assert (service['SERVICE_RESULT'],service['EXIT_CODE'],service['EXIT_STATUS']) == ('success','exited','0')
assert plan['service_terminal_contract']['RemainAfterExit'] is False
cw = read(P / 'collector.wait.json'); ow = read(O / 'observer.wait.json')
for w in (cw, ow):
    zero(w['actual_wait_exit']); assert w['timed_out'] is False
zero(read(O / 'notification_wait.receipt.json')['actual_wait_exit'])
assert cw == obs['collector_wait'] and ow == notice['actual_observer_wait']
assert sha(P/'collector.log') == cw['log_sha256']
assert sha(O/'observer.log') == ow['log_sha256']
assert notice['result'] == str(O/'result.json') and notice['result_sha256'] == sha(O/'result.json')
scope = dict(calls=17920,result_bits=286720,guards=35840,flags=17920,vstarts=17920,
    helper_instructions=326144,capacity_instructions=3,fresh_stores=734720,
    input_LD=143360,output_LWU=17920,record_LD=2240,FPR_committed_writebacks=10752)
for k,v in scope.items():
    assert strict[k] == obs['scope'][k] == v, k
assert strict['raw_scalar_seed_counts'] == {str(s):336 for s in range(32)}
assert strict['status'] == 'FULL17920_RVFI_SOURCE_PARENT_ACCEPTED_NOT_LINUX'
assert strict['full_parent'] is True and strict['linux'] is False
assert report['closed_semantic_passes'] == 1
assert strict['rows'] == generic['rows'] == obs['rows'] == 3413323
assert strict['retired'] == generic['retire_count'] == 2665794
assert strict['last_cycle'] == generic['last_cycle'] == 6152665
assert generic['cvx_exception_count'] == generic['cvx_replay_count'] == generic['arch_request_replay_count'] == 0
assert generic['architecture_request_count'] == generic['cvx_request_count'] == generic['cvx_response_count'] == 179203
console = (T/'console.log').read_text()
assert console.count(strict['console']) == 1
assert 'Core Test *** SUCCESS ***' in console
for marker in plan['cases'][0]['pass_markers']:
    assert marker in strict['console']
assert not any(x in console for x in ('FAIL', 'ERROR', 'TIMEOUT'))

# Cross-check every metadata owner against bound call geometry and actual helper code.
model = read(G/'fp_compare_unboxed_full17920_prepare01/source_model02/model.json')['rows']
assert len(model) == 17920
ledger = owners['owner_ledger']; by_call = collections.defaultdict(list)
assert len(ledger) == generic['architecture_request_count']
for order, e in enumerate(ledger):
    assert e['arch_order'] == order and e['alloc'] == e['done']
    assert type(e['alloc']) is int and e['alloc'] in (0,1)
    if e['call'] is None:
        assert e['kind'] == 'configuration' and not e['required'] and e['alloc'] == 0
    else:
        assert 0 <= e['call'] < len(model)
        by_call[e['call']].append(e)
counts = collections.Counter()
for n,g in enumerate(model):
    assert g['ordinal'] == n+1
    expected = []
    for i,h in enumerate(plan['spec']['helpers'][g['op']]):
        c = int(h['insn'],16); opcode = c & 127; f3 = (c >> 12) & 7
        vector = opcode == 0x57 or opcode in (7,39) and f3 in (0,5,6,7)
        csr = opcode == 0x73 and f3 != 0 and c >> 20 in (8,9,10,15,0xc20,0xc21,0xc22)
        if not (vector or csr):
            continue
        kind = 'memory' if opcode in (7,39) else 'target' if opcode == 0x57 and f3 != 7 else 'configuration'
        required = kind == 'memory' or kind == 'target' and g['vl'] > 0
        expected.append((i,h['pc'],c,kind,required))
    actual = by_call[n]
    assert [(e['helper_index'],e['pc'],e['insn'],e['kind'],e['required']) for e in actual] == expected
    for e in actual:
        assert e['alloc'] == int(e['required'])
        if e['kind'] == 'memory': counts['memory'] += 1
        if e['kind'] == 'target': counts['target_required' if e['required'] else 'target_elidable'] += 1
contract = dict(memory=89600,target_required=15360,target_elidable=2560)
assert dict(counts) == contract == plan['owner_contract'] == owners['contract'] == col['owner_contract'] == obs['owner_contract']
assert sum(e['alloc'] for e in ledger) == owners['total_actual_alloc'] == owners['total_actual_done'] == generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] == 104960

pins = {}
for d in (plan['pins'],complete['evidence_pins'],col['evidence_pins'],obs['evidence_pins'],launch['approval_pins']):
    for path,digest in d.items():
        assert path not in pins or pins[path] == digest
        pins[path] = digest
for path in (P/'collector.wait.json',O/'result.json',O/'notification.json',O/'observer.wait.json',O/'notification_wait.receipt.json',HERE/'ENTRY_REVIEW02.json'):
    pins[str(path)] = sha(path)
skip = {plan['reference_raw_identity']['path'],str(T/'commit_trace.csv')}
assert plan['pins'][plan['reference_raw_identity']['path']] == plan['reference_raw_identity']['sha256']
assert pins[str(T/'commit_trace.csv')] == report['csv_sha256'] == col['csv_identity_inherited_from_complete'] == obs['CSV_identity_inherited']
for path,digest in pins.items():
    if path not in skip:
        assert sha(Path(path)) == digest, path
assert len(plan['pins']) == obs['input_pin_count'] == 750
assert not (P/'firstfailure.json').exists()
result = dict(status='ACCEPTED_FULL17920_M9_INDEPENDENT_TERMINAL_METADATA_NOT_LINUX',
    plan_sha256=plan_sha,scope=scope,owner_contract=contract,owner_ledger_entries=len(ledger),
    alloc_done=104960,rows=strict['rows'],retired=strict['retired'],last_cycle=strict['last_cycle'],
    child=child,service_exit=service,collector_wait=cw,observer_wait=ow,
    input_pins=750,unique_pins=len(pins),rehashed_nonraw=len(pins)-len(skip),
    inherited_raw={p:pins[p] for p in sorted(skip)},evidence_pins=pins,
    semantic_CSV_reads=0,raw_reference_reads=0,rerun=False,
    FPR_scope='10752 committed writeback payloads, not physical FPR readback or accelerator operand snapshot',
    limitation='Metadata acceptance of the sealed single semantic pass; not an independent numerical reparse or Linux incident closure.')
with (HERE/'TERMINAL_REVIEW01.json').open('x') as f:
    json.dump(result,f,indent=2); f.write('\n')
print(json.dumps({k:result[k] for k in ('status','scope','unique_pins','rehashed_nonraw','alloc_done')}))
