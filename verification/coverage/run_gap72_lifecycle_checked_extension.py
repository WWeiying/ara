#!/usr/bin/env python3
"""Gap72 multi-case sealed admission; parent owns runner/launch orchestration."""
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import coverage_evidence as evidence
import run_checked_extension as checked
import audit_gap72_lifecycle as audit

ROOT, SCHEMA = audit.ROOT, audit.SCHEMA
_RAW_CASE_NAMES = audit.CASE_NAMES
CASE_NAMES = ['app:' + name for name in _RAW_CASE_NAMES]
SCRIPT = Path(__file__).resolve()
require = audit.require
MANIFESTS = ('tool_hashes.json', 'link-inputs.json', 'protected-inputs.json', 'artifact_hashes.json')
_HOOKS = None
_NATIVE_PRECHECK = evidence.precheck


class RuntimeFiles:
    """Collect only checked case-local bytes, separately from static proof pins."""
    def __init__(self, target, row, proof):
        self.target, self.row, self.proof = Path(target).resolve(strict=True), row, proof
        self.files = {}

    def pin(self, path, database=False):
        path = Path(path)
        hashes = self.row['vdb_files' if database else 'files']
        root = Path(self.row['vdb']).resolve(strict=True) if database else self.target
        require(str(path) in hashes and path.resolve(strict=True).is_relative_to(root),
                'unbound/out-of-scope runtime artifact: ' + str(path))
        checked_path = self.proof.pin(path, hashes[str(path)])
        require(self.proof.files[str(path)] == hashes[str(path)], 'runtime bytes were not checked')
        self.files[str(path)] = hashes[str(path)]
        return checked_path


def precheck(item, proof, delegate):
    require(item.get('name') in CASE_NAMES and
            type(item.get('timeout_s')) is int and item['timeout_s'] in (300,1800) and
            item['runtime_contract'] == SCHEMA, 'gap72 identity/budget/runtime schema differs')
    path = evidence.full.absolute(item['precheck']['record']).resolve(strict=True)
    directory = path.parent
    require(directory.parent == ROOT / 'verification/out' and directory.name.startswith('gap72-'),
            'foreign gap72 preflight directory')
    draft, saved_path, artifacts = [directory / n for n in
        ('selection.checked-draft.json', 'checked-precheck.json', 'artifact_hashes.json')]
    seals = proof.read(directory / 'draft.sha256.json')
    require(set(seals) == set(map(str, (draft, saved_path, artifacts))), 'wrong gap72 seal set')
    proof.hashes(seals)
    selection = proof.read(draft)
    names = [i['name'] for i in selection['cases']]
    require(len(set(names)) == len(names) and set(names) <= set(CASE_NAMES) and
            [i for i in selection['cases'] if i['name'] == item['name']] == [item] and
            selection['baseline'] == str(audit.BASE) and selection['measured_gain'] is None,
            'case differs from sealed latest654 draft')
    saved = proof.read(saved_path)
    require(saved['status'] == 'PASS' and saved['read_only_validation'] is True and
            saved['vcs_launched'] is False and saved['scope'] == 'host-reference-only',
            'gap72 saved precheck scope differs')
    replay = evidence.Evidence(); replay.pin(draft)
    for name in MANIFESTS:
        replay.hashes(replay.read(directory / name))
    result = delegate(item, replay)
    require(saved['cases'][item['name']] == dict(result=result, checked_files=replay.files),
            'gap72 exact native replay differs')
    proof.hashes(replay.files)
    record = proof.read(path)
    name, label = record['name'], record['label']
    require(record['schema'] == SCHEMA and record['custom_instruction_execution_prechecked'] is False,
            'software reference became custom ISA evidence')
    audit.validate_log(proof.pin(record['host_log']).read_text(), name, host=True)
    negative = proof.pin(directory / (label + '-negative.log')).read_text()
    audit.validate_log(negative, name, host=True, negative=True)
    require(f"G72_NEGATIVE bytes={record['negative_byte_mutations']} errors=0" in negative,
            'negative byte coverage differs')
    meta = json.loads(proof.pin(record['metadata']).read_text())[0]
    require(audit.elf_audit(meta, proof.pin(item['binary'], record['binary_sha256']).read_bytes(), name) ==
            record['elf_audit'], 'linked raw opcode/layout/CSR audit differs')
    require(audit.native_targets(proof) == proof.read(directory / 'native-targets.json'),
            'latest654 native shape/source target replay differs')
    software = proof.read(record['software_spike'])
    command = software['command']
    require(command == [command[0], '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu',
            '--pmpregions=0', '-l', '--log-commits', software['elf']], 'software Spike command differs')
    proof.pin(command[0], software['spike_sha256'])
    proof.pin(software['elf'], software['elf_sha256'])
    require(proof.pin(software['stdout']).read_text().splitlines() ==
            [f'PASSED: {name} SOFTWARE_REFERENCE_ONLY'], 'software Spike not PASS')
    actual = audit.software_trace(proof.pin(software['trace']).read_text(), name)
    require(all(software.get(k) == v for k, v in actual.items()), 'software Spike trace replay differs')
    commands = proof.read(directory / 'commands.json')
    require(commands and all(c['status'] == 'PASS' and c['returncode'] == 0 and
            0 < c['timeout_s'] <= 120 for c in commands), 'failed/unbounded preflight command')
    require(len([c for c in commands if c['command'] == command and c['timeout_s'] == 30]) == 1,
            'software Spike run not bound to command log')
    for path in (SCRIPT, Path(audit.__file__), Path(checked.__file__), Path(evidence.__file__)):
        proof.pin(path)
    return dict(result, runtime_contract=SCHEMA, software_spike_scope='SOFTWARE_REFERENCE_ONLY',
                custom_instruction_execution_prechecked=False, target_hits_measured=False)


def install_hooks():
    """Only evidence hooks; do not replace checked.SCRIPT or any runner entrypoint."""
    global _HOOKS
    if _HOOKS is not None:
        return _HOOKS
    prior = evidence.precheck
    def wrapped(item, proof):
        return precheck(item, proof, prior) if item.get('name') in CASE_NAMES else prior(item, proof)
    wrapped.delegate = prior
    evidence.precheck = wrapped
    _HOOKS = dict(case_names=CASE_NAMES, precheck=wrapped, runtime_proof=runtime_proof,
                  perf_command=perf_command)
    return _HOOKS


def perf_command(command):
    """Case-local flags for the parent's compatible multi-case loader."""
    command = list(map(str, command))
    tests = [x.removeprefix('+TESTCASE=') for x in command if x.startswith('+TESTCASE=')]
    require(len(tests) == 1 and tests[0] in _RAW_CASE_NAMES and command.count('+NO_FSDB') == 1,
            'gap72 requires exact case and no-FSDB profile')
    flag = '+QBS_PERF' if tests[0] == _RAW_CASE_NAMES[0] else '+AKV_PERF'
    require(not any(s.startswith(('+QBS_PERF', '+AKV_PERF', '+VECTOR_TRACE=')) for s in command),
            'unexpected existing PERF/vector trace flag')
    traces = [Path(x.removeprefix('+COMMIT_TRACE=')) for x in command if x.startswith('+COMMIT_TRACE=')]
    require(len(traces) == 1 and traces[0].name == 'commit_trace.csv', 'commit trace required')
    return command + [flag, '+VECTOR_TRACE=' + str(traces[0].parent / 'work/vector_trace.csv')]


def runtime_proof(output, plan, row, proof):
    """Read-only independent oracle; never launches tools or executes references."""
    name = row.get('name', '').removeprefix('app:')
    require(name in _RAW_CASE_NAMES and row.get('status') == 'PASS' and row.get('returncode') == 0 and
            row.get('passed_only') is True and row.get('vdb_valid') is True and row.get('reused') is False,
            'fresh independent generic PASS required')
    cases = [c for c in plan['cases'] if c['name'] == name and c['source_name'] == 'app:' + name]
    require(len(cases) == 1 and type(cases[0]['timeout_s']) is int and
            cases[0]['timeout_s'] in (300,1800), 'runtime case/budget differs')
    case = cases[0]
    def frozen(path):
        require(str(path) in plan['files'], 'unbound frozen input: ' + str(path))
        return proof.pin(path, plan['files'][str(path)])
    selection = proof.read(frozen(Path(plan['source_selection']['selection'])))
    items = [i for i in selection['cases'] if i['name'] == 'app:' + name]
    require(len(items) == 1, 'runtime selection ambiguity')
    item = items[0]
    require(item['timeout_s'] == case['timeout_s'], 'runtime sealed budget differs')
    # Parent may have combined this exact item with other extensions.
    admitted = precheck(item, proof, _NATIVE_PRECHECK)
    require(case['elf_sha256'] == row['elf_sha256'] == admitted['elf_sha256'], 'runtime ELF identity differs')
    record = proof.read(frozen(Path(item['precheck']['record'])))
    elf = proof.pin(case['frozen_elf'], record['binary_sha256'])
    meta = json.loads(proof.pin(record['metadata']).read_text())[0]
    linked = audit.elf_audit(meta, elf.read_bytes(), name)
    target = Path(output).resolve(strict=True) / 'results' / name
    runtime = RuntimeFiles(target, row, proof)
    def bound(path):
        return runtime.pin(path)
    summaries = proof.read(bound(target / 'summary.json'))
    require(len(summaries) == 1 and summaries[0]['status'] == 'PASS' and
            summaries[0]['name'] == 'app:' + name, 'functional summary differs')
    artifact = Path(summaries[0]['artifact_dir']).resolve(strict=True)
    require(artifact == target / 'tests' / ('app_' + name), 'foreign runtime artifact')
    require(Path(row['vdb']).resolve(strict=True) == artifact / 'work/code.vdb', 'foreign coverage VDB')
    executed_elf = proof.pin(bound(artifact / 'input.elf'), record['binary_sha256'])
    inputs = proof.read(bound(artifact / 'inputs.json'))
    require(inputs['binary']['sha256'] == record['binary_sha256'] and
            inputs['simv']['image_sha256'] == plan['wrapper_image'], 'executed ELF/image differs')
    original = proof.read(bound(artifact / 'command.json'))
    actual = proof.read(bound(artifact / 'work/coverage.command.json'))
    command = actual['command']
    require(command[0] == plan['simv'] and actual['cwd'] == str(artifact / 'work') and
            command.count('+TESTCASE=' + name) == 1 and command.count('+NO_FSDB') == 1 and
            command.count('+QBS_PERF' if name == _RAW_CASE_NAMES[0] else '+AKV_PERF') == 1 and
            command.count('+COMMIT_TRACE=' + str(artifact / 'commit_trace.csv')) == 1 and
            command.count('+VECTOR_TRACE=' + str(artifact / 'work/vector_trace.csv')) == 1,
            'actual custom command/trace/PERF identity differs')
    require(original['cwd'] == str(artifact / 'work'), 'original command directory differs')
    stdout = bound(artifact / 'work/run.vcs.log')
    console = bound(artifact / 'console.log')
    uart = audit.validate_log(stdout.read_text(), name)
    perf = audit.perf_records(stdout.read_text(), name)
    commit = bound(artifact / 'commit_trace.csv')
    vector = bound(artifact / 'work/vector_trace.csv')
    trace = audit.trace_oracle(commit, vector, linked, name)
    require(sum(p['busy_cycles'] for p in perf) <= trace['last_cycle'], 'command cycles exceed run')
    contract = re.findall(r'^\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+) '
        r'mmu_request_cycles=(\d+) protocol_errors=(\d+) outstanding=(\d+) req_stalled=([01]) resp_stalled=([01])$',
        stdout.read_text(), re.M)
    require(len(contract) == 1 and list(map(int, contract[0]))[:3] ==
            [trace['requests'], trace['responses'], 2] and list(map(int, contract[0]))[4:] == [0, 0, 0, 0],
            'protocol log differs from trace')
    targets = proof.read(frozen(Path(item['precheck']['record']).parent / 'native-targets.json'))
    require(plan['design_vdb'] == targets['design_vdb'], 'compiled coverage shape differs')
    from closure_point_inventory import read_xml
    raw_paths = [Path(p) for p in row['vdb_files'] if p.endswith('/cond.verilog.data.xml')]
    require(len(raw_paths) == 1 and raw_paths[0].is_relative_to(Path(row['vdb'])), 'foreign raw condition data')
    raw = runtime.pin(raw_paths[0], database=True)
    nodes = list(read_xml(raw).iter('instance_data'))
    by_scope = {n.get('name'): n for n in nodes}
    require(len(by_scope) == len(nodes), 'duplicate raw condition scope')
    gains = []
    for point in targets['targets']:
        if point['module'] != ('qbs_engine' if name == _RAW_CASE_NAMES[0] else 'akv_engine'):
            continue
        node = by_scope[point['scope']]
        bits = node.get('value')
        require(node.get('chksum') == point['checksum'] and len(bits) == point['width'] and set(bits) <= {'0', '1'},
                'raw condition shape differs')
        require(bits[point['raw_index']] == '1', 'intended lifecycle raw vector not measured')
        gains.append(dict(scope=point['scope'], native_id=point['native_id'], vector=point['vector'],
                          raw_index=point['raw_index'], observed=1, native_dve_qualified=False))
    # Static/history pins remain in proof; the batch admits only local runtime files.
    proof.hashes(dict(proof.files))
    return dict(status='PASS', schema=SCHEMA, name='app:' + name, uart=uart, perf=perf, trace=trace,
                raw_targets=gains, elf_sha256=record['binary_sha256'], files=dict(runtime.files),
                runtime_artifacts=dict(stdout=str(stdout), console=str(console), commit=str(commit),
                                       vector=str(vector), elf=str(executed_elf)),
                scope='Independent custom protocol/PC/CSR/numerical VRF replay; raw gains not native DVE qualification')


if __name__ == '__main__':
    raise SystemExit('Import install_hooks() into the parent multi-case adapter; no standalone launch.')
