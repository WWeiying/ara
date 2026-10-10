"""One offline qualification and exact746-prefix merge for the completed matrix."""
import argparse
import json
import re
from pathlib import Path
from types import FunctionType, SimpleNamespace
import run_fpu_external_reset_matrix as matrix
import prepare_fpu_reset_matrix as oracle
import qualify_external_reset_fixture as shared

life, require = matrix.life, matrix.require
SEAL = '9e0c4ba9545639916c33b79ccf2a0990e85d496fc76866abba96f7f1d5d7b5dd'
OUT = life.OUT / 'fpu-reset-matrix-qualified-746-agent-20261007-01'
ADMIT = life.OUT / 'fpu-reset-matrix-offline-admitted-746plus-agent-20261007-01'
events = shared.events


def expected_word(sew, index):
    require(sew in oracle.GOLD and 0 <= index < 512, 'Invalid canonical VRF word')
    return 0x123456789abcdef0 if index < 128 else oracle.GOLD[sew][index // 128 - 1]


def epoch0_bytes(rows, sew, stage):
    owners = {}; count = 0
    for row in rows:
        if row['event'] == 'alloc':
            owners[int(row['arch_seq'])] = row
        if row['event'] != 'write':
            continue
        owner = owners[int(row['arch_seq'])]
        insn, vd, eew = int(owner['insn'], 16), int(owner['vd']), int(owner['eew'])
        if eew == 3 and int(owner['vl']) == 16 and insn & 0xfc00707f == 0x5c004057:
            word = 0x0101010101010101 * (0x40 + vd)
        elif eew == {16: 1, 32: 2, 64: 3}[sew] and insn in (0x5e02c057, 0x5e02c857, 0x92001457):
            word = oracle.GOLD[sew][1 if insn == 0x5e02c857 else 0]
        elif insn == 0x82881c57 and stage == 'WB_REQ' and eew == {16: 1, 32: 2, 64: 3}[sew]:
            word = oracle.GOLD[sew][2]
        else:
            raise ValueError('Unproven epoch0 writer/precision/stage')
        be, data = int(row['be'], 16), int(row['wdata'], 16)
        require(0 < be <= 255, 'Invalid epoch0 byte enable')
        for index in range(8):
            if be >> index & 1:
                require((data >> (8 * index)) & 255 == (word >> (8 * index)) & 255,
                        'Epoch0 canonical written byte differs')
                count += 1
    return count


def cancelled_owners(commits, vectors, case):
    pending = {}
    for row in vectors:
        if row['event'] == 'alloc':
            vid = int(row['vid']); require(vid not in pending, 'Duplicate live VID')
            pending[vid] = row
        elif row['event'] == 'done':
            require(int(row['vid']) in pending, 'Orphan completion')
            pending.pop(int(row['vid']))
    words = {int(row['insn'], 16) for row in pending.values()}
    require(0x82881c57 in words and words <= {0x82881c57, 0x5e02c857}, 'Unexpected cancelled operation')
    seqs = []
    for row in pending.values():
        seq, insn = int(row['arch_seq']), int(row['insn'], 16)
        require(int(row['eew']) == {16: 1, 32: 2, 64: 3}[case['sew']] and
                int(row['vl']) == 8192 // case['sew'] and int(row['vd']) == (24 if insn == 0x82881c57 else 16),
                'Cancelled operand/precision differs')
        starts = [r for r in commits if r['event'] == 'arch_start' and int(r['order']) == seq]
        symbol = case['preflight_case']['symbols']['fpar_div'] if insn == 0x82881c57 else None
        require(len(starts) == 1 and int(starts[0]['insn'], 16) == insn, 'Cancelled owner unbound')
        if symbol is not None:
            retire = [r for r in commits if r['event'] == 'retire' and int(r['pc'], 16) == symbol]
            require(len(retire) == 1 and int(retire[0]['insn'], 16) == insn and int(retire[0]['trap']) == 0,
                    'Cancelled DIV exact site/accepted retirement differs')
        seqs.append(seq)
    return seqs


def all_controller_states(path, record):
    names = [t['state_signal'] for t in record['targets']] + ['ara_tb.rst_n']
    namespace = dict(shared.parser.vcd.__globals__, ROOT='ara_tb',
                     WIDTHS={p[7:]: 1 if p == 'ara_tb.rst_n' else 4 for p in names})
    iterator = iter(FunctionType(shared.parser.vcd.__code__, namespace)(path))
    _, declarations = next(iterator)
    codes = {p: declarations[p]['code'] for p in names}
    samples = []
    for time, before, after in iterator:
        reset = codes['ara_tb.rst_n']
        if before.get(reset) == '1' and after.get(reset) == '0':
            sample = {}
            for p in names[:-1]:
                bits = before.get(codes[p], 'x')
                require(set(bits) <= {'0', '1'}, 'Unknown active controller at reset')
                sample[p] = int(bits, 2)
            samples.append(dict(time_100fs=time, states=sample))
    require(len(samples) == 1 and samples[0]['states'][record['selection']['ext_target']] ==
            matrix.STAGES[record['stage']][0], 'Actual stage/precision controller window differs')
    return samples[0]


def runtime(record, destination):
    root = Path(record['output']); pre = record['preflight_case']
    require(json.loads((root / 'simulation-status.json').read_bytes())['returncode'] == 0, 'Not successful terminal')
    require(json.loads((root / 'manifest.json').read_bytes()) == dict(record, pins=life.merge_pins(
        record['pins'], {str(matrix.PLAN): SEAL})), 'Executed matrix identity differs')
    require(life.digest(root / 'external-reset-selection.tcl') == record['selection_sha256'], 'Executed selection differs')
    console = (root / 'console.log').read_text(); log = (root / 'run.vcs.log').read_text()
    target, stage = record['selection']['ext_target'], record['selection']['ext_value']
    markers = ['EXT_RESET_READY %s %d' % (target, stage), 'EXT_RESET_TARGET %s %d' % (target, stage),
               'EXT_RESET_ASSERT', *['EXT_RESET_LOW_EDGE %d' % n for n in range(1, 5)],
               'EXT_RESET_RELEASE', 'EXT_RESET_DONE']
    require([s for s in console.splitlines() if s.startswith('EXT_RESET_')] == markers and
            console.count('Core Test *** SUCCESS ***') == 1 and not re.search(
                r'(?m)^UVM_(ERROR|FATAL)\b|\[ARA_CONTRACT_ERROR\]|trace.*truncat', log), 'Terminal/reset/error markers differ')
    cf, cr = events.run.reset.read_csv(root / 'commit_trace.csv')
    vf, vr = events.run.reset.read_csv(root / 'vector_trace.csv')
    epochs, cut = events.run.reset.split_epochs(cr, vr)
    for index, (commits, vectors) in enumerate(epochs):
        ep = destination / ('epoch%d' % index); ep.mkdir()
        events.run.reset.write_csv(ep / 'commit_trace.csv', cf, commits)
        events.run.reset.write_csv(ep / 'vector_trace.csv', vf, vectors)
    cancelled = cancelled_owners(*epochs[0], record)
    backend = [events.backend(*epochs[0], cancelled), events.backend(*epochs[1], set())]
    spike = Path(pre['spike_trace'])
    prefix = events.run.shared.shared.spike_trace.compare_commit_prefix(spike, destination / 'epoch0/commit_trace.csv',
        0x80000000, rvfi_store_data_layout='unshifted')
    require(prefix['status'] == 'PREFIX' and prefix['mismatch'] is None and
            prefix['skipped_unobservable_register_values'] == 0 and prefix['ara_trap_events'] == 0 and
            prefix['ara_retired_instructions'] == prefix['matched_instructions'], 'Scalar cancelled prefix differs')
    known_bytes = epoch0_bytes(epochs[0][1], record['sew'], record['stage'])
    original = events.run.reset.check_real_uvm_log(root / 'run.vcs.log', require_events=True, require_backend=True,
        require_axi=True, vector_trace=root / 'vector_trace.csv', reset_kind='state')
    life.save(destination / 'original-uvm-audit.json', original)
    require(original['uvm_backend_event_sha256'] == original['vector_backend_event_sha256'] and
            original['uvm_backend_event_count'] == original['vector_backend_event_count'] < 100000,
            'UVM/vector full backend sequence differs')
    observed = list(events.uvm._RESET_OBSERVED.finditer(log))
    require([int(m['epoch']) for m in observed] == [1, 2], 'Exact reset epochs differ')
    boundary = int(observed[1]['cycle'])
    ue, ui = events.uvm._events(log, '[CVXIF/EVENT]', events.uvm._UVM_EVENT, 10)
    ce, ci = events.uvm._events(log, '[ARA_CONTRACT_TRACE]', events.uvm._CONTRACT_EVENT, 16)
    require(not ui and not ci and 0 < len(ue) == len(ce) < 100000 and
            events.uvm._event_digest(ue) == events.uvm._event_digest(ce) and not any(e[0] == boundary for e in ce),
            'CVXIF/contract full event sequence differs')
    cvx = []
    for index, (rows, _) in enumerate(epochs):
        selected = [e for e in ce if (e[0] < boundary if index == 0 else e[0] > boundary)]
        counts = events.traffic(selected)
        require(counts['aborted'] == 0, 'Unexpected front-end cancellation')
        commits = [(int(r['cycle']), r['event'], int(r['trans_id']),
                    int(r['insn'], 16) if r['event'] == 'cvx_req' else 0, int(r['trap']))
                   for r in rows if r['event'] in ('cvx_req', 'cvx_resp')]
        flattened = [(e[0], name, key, insn, exc) for e in selected for name, key, insn, exc in
                     ([('cvx_req', e[2], e[3], 0)] if e[1] else []) +
                     ([('cvx_resp', e[5], 0, e[6])] if e[4] else [])]
        require(events.relative_events(commits) == events.relative_events(flattened), 'Commit/CVX identity differs')
        cvx.append(counts)
    require(original['contract_counts']['requests'] == cvx[1]['requests'] == original['contract_counts']['responses']
            and cvx[1]['responses'] == cvx[1]['requests'] and all(original['contract_counts'][k] == 0
                for k in ('exceptions', 'protocol_errors', 'outstanding')), 'Final contract conservation differs')
    memory = {}
    for row in epochs[1][0]:
        if row['event'] == 'retire':
            store = events.run.shared.shared.scalar_store(row)
            if store:
                memory.update({store[0] + n: b for n, b in enumerate(store[1])})
    def value(name, offset=0, size=8):
        address = pre['symbols'][name] + offset
        require(all(address + n in memory for n in range(size)), 'Missing recovery oracle byte')
        return int.from_bytes(bytes(memory[address + n] for n in range(size)), 'little')
    oracle.oracle(value, record['sew'])
    scalar = events.run.shared.shared.spike_trace.compare_commit_prefix(spike, destination / 'epoch1/commit_trace.csv',
        0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
    events.run.shared.shared.scalar_exact(scalar, pre['counts'])
    vector = events.run.shared.shared.compare_vector_commits(spike, destination / 'epoch1/commit_trace.csv',
        destination / 'epoch1/vector_trace.csv', 0x80000000)
    require(vector['status'] == 'PASS' and all(vector[k] == 0 for k in (
        'skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions')) and
        not vector['incomplete_requests'] and not vector['unretired_requests'] and all(
            r['unknown_write_bytes'] == r['skipped_unknown_bytes'] == r['mismatch_count'] == 0 for r in vector['instructions']),
        'Recovery full vector byte comparison differs')
    reader = events.run.shared.template.s.LLVM / 'llvm-readelf'
    snapshot = events.run.shared.template.s._elf_symbol(Path(pre['ELF']), reader, 'snapshot')
    namespace = dict(shared.wave.__globals__, gold=SimpleNamespace(
        expected_word=lambda i: expected_word(record['sew'], i)))
    axi = FunctionType(shared.wave.__code__, namespace)(root / 'external-reset.vcd', record['selection'],
                                                       pre['symbols']['source'] + 128, snapshot)
    axi['status'] = 'EXACT_SEW_STAGE_FOUR_CLOCK_ALL_AXI_CHANNELS_PASS'
    timestamps = re.findall(r'@ (\d+):[^\n]*\[CVXIF/RESET\][^\n]*epoch=2', log)
    require(len(timestamps) == 1 and axi['resets_100fs'][0] < int(timestamps[0]) <= axi['resets_100fs'][1],
            'Wave/reset trace epoch boundary differs')
    controllers = all_controller_states(root / 'external-reset.vcd', record)
    require(controllers['time_100fs'] == axi['resets_100fs'][0], 'Controller/AXI reset boundary differs')
    values = {'prefix-scalar.json': prefix, 'recovery-scalar.json': scalar, 'recovery-vector.json': vector,
              'axi-audit.json': axi, 'controller-window.json': controllers,
              'event-audit.json': dict(cvx_epochs=cvx, backend_epochs=backend, epoch0_known_write_bytes=known_bytes)}
    for name, obj in values.items():
        life.save(destination / name, obj)
    return dict(software_checks=679, full_vrf_bytes=4096, csr_words=5, source_guards_checked=True,
                epoch_count=2, scalar_counts=pre['counts'], vector_instructions=vector['compared_instructions'],
                vector_bytes=vector['compared_bytes'], axi_all_channels_verified=True,
                uvm_check_report_pass=False, missing_uvm_summary_preserved=True)


def merge(before, singles):
    require(len(before['tests']) == len(set(before['tests'])) == 746, 'Exact formal746 required')
    result = before
    for single in singles:
        require(len(single['tests']) == 1 and single['tests'][0] not in result['tests'], 'Duplicate/new VDB differs')
        require(set(single['metrics']) == set(before['metrics']) and all(
            set(single['metrics'][metric]) == set(scopes) for metric, scopes in before['metrics'].items()),
            'Singleton metric/scope inventory differs')
        result = shared.coverage.bitmap.combine(result, single)
    count = 0
    for metric, scopes in before['metrics'].items():
        for scope, row in scopes.items():
            bits = int(row['bits'], 16)
            for single in singles:
                added = single['metrics'][metric][scope]
                require((row['width'], row['checksum']) == (added['width'], added['checksum']), 'Compiled identity differs')
                bits |= int(added['bits'], 16)
            require(int(result['metrics'][metric][scope]['bits'], 16) == bits, 'Independent complete OR differs')
            count += 1
    require(count == 6162 and result['tests'] == before['tests'] + [s['tests'][0] for s in singles],
            'Full6162 OR/exact746 prefix differs')
    return result


def context():
    plan = life.read_bound(matrix.PLAN, SEAL)
    require([(r['sew'], r['stage']) for r in plan['cases']] == matrix.CASES, 'Exact remaining11 required')
    pre = life.read_bound(matrix.PRE / 'preflight.json', matrix.PRE_SHA)
    for record in plan['cases']:
        selection, row, active = matrix.select(pre, record['sew'], record['stage'])
        require(record['selection'] == selection and record['preflight_case'] == row and
                [t['scope'] for t in record['targets']] == [t['scope'] for t in active], 'Stage/SEW/preflight binding differs')
    terminal_path = matrix.PLAN.with_name(matrix.PLAN.name + '.terminal.json')
    terminal = json.loads(terminal_path.read_bytes())
    require(terminal['plan_seal'] == SEAL and len(terminal['cases']) == 11 and
            {r['case'] for r in terminal['cases']} == {r['case'] for r in plan['cases']} and
            all(r['status'] == 'TERMINAL_CAPTURE_PENDING_ARCHITECTURE_QUALIFICATION' for r in terminal['cases']),
            'Exact completed matrix required')
    base = life.read_bound(matrix.BASE / 'admission-manifest.json', matrix.BASE_SHA)
    pins = life.merge_pins(plan['pins'], base['input_pins'])
    pins = life.merge_pins(pins, base['output_pins'])
    pins = life.merge_pins(pins, {str(matrix.PLAN): SEAL, str(matrix.BASE / 'admission-manifest.json'): matrix.BASE_SHA,
                                  str(terminal_path): life.digest(terminal_path)})
    for record in plan['cases']:
        pins = life.merge_pins(pins, record['pins'])
    for module in (matrix, oracle, shared, events, shared.parser, shared.coverage):
        p = Path(module.__file__).resolve(); pins = life.merge_pins(pins, {str(p): life.digest(p)})
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_qualify_fpu_reset_matrix.py')):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins)
    before = life.read_bound(matrix.BASE / 'combined-bits.json', pins[str(matrix.BASE / 'combined-bits.json')])
    require((matrix.BASE / 'combined-inputs.txt').read_text().splitlines() == [str(shared.coverage.DESIGN)] + before['tests'],
            'Exact baseline input ledger differs')
    return plan, pins, before


def qualify():
    require(not OUT.exists(), 'Fresh qualification only')
    plan, common, before = context(); OUT.mkdir(); results = []
    for record in plan['cases']:
        destination = OUT / record['case']; destination.mkdir()
        root = Path(record['output'])
        try:
            require((root / 'external-reset.vcd').is_file(), 'Parent converted waveform not ready')
            pins = dict(common)
            for p in root.rglob('*'):
                if p.is_file():
                    pins = life.merge_pins(pins, {str(p): life.digest(p)})
            life.check(pins)
            result = runtime(record, destination)
            inputs = destination / 'single-inputs.txt'
            with inputs.open('x') as stream:
                stream.write(str(shared.coverage.DESIGN) + '\n' + str(root / 'code.vdb') + '\n')
            single = shared.coverage.bitmap.collect(inputs)
            require(single['tests'] == [str(root / 'code.vdb')] and
                    all(pins.get(p) == sha for p, sha in single['input_hashes'].items()), 'Unbound singleton input')
            after = merge(before, [single]); delta = shared.coverage.all_delta(before, after)
            raw = matrix.STAGES[record['stage']][1]; hits = []
            for target in record['targets']:
                old = before['metrics']['fsm'][target['scope']]; new = single['metrics']['fsm'][target['scope']]
                require(old['width'] == new['width'] == 17 and old['checksum'] == new['checksum'], 'Controller native identity differs')
                hits.append(dict(scope=target['scope'], raw_index=raw, serialized_bit=16-raw,
                    before=bool(int(old['bits'], 16) & (1 << (16-raw))),
                    single=bool(int(new['bits'], 16) & (1 << (16-raw)))))
            life.check(pins)
            for name, value in [('single-bits.json', single), ('raw-delta.json', delta), ('fsm-targets.json', hits), ('evidence-pins.json', pins)]:
                life.save(destination / name, value)
            result.update(status='MATRIX_CASE_WAVE_ARCHITECTURE_PASS_NOT_ADMITTED', case=record['case'], sew=record['sew'],
                stage=record['stage'], baseline=746, coverage_admitted=False, raw_delta=delta['metrics'],
                actual_target_hits=sum(h['single'] and not h['before'] for h in hits),
                output_pins={str(p): life.digest(p) for p in destination.rglob('*') if p.is_file()})
            life.save(destination / 'qualification.json', result)
            results.append(dict(case=record['case'], status='PASS', qualification=str(destination / 'qualification.json'),
                                seal=life.digest(destination / 'qualification.json'), raw_delta=delta['metrics']))
            print('QUALIFIED ' + record['case'] + ' ' + json.dumps(delta['metrics']), flush=True)
        except Exception as exc:
            failure = dict(case=record['case'], status='FAILED_NOT_ADMITTED', reason=str(exc), coverage_admitted=False)
            life.save(destination / 'failure.json', failure); results.append(failure)
            print('REJECTED ' + record['case'] + ': ' + str(exc), flush=True)
    life.check(common)
    life.save(OUT / 'result.json', dict(schema='FPU_EXTERNAL_RESET_MATRIX_QUALIFICATION_V1', baseline=746,
        baseline_seal=matrix.BASE_SHA, plan_seal=SEAL, cases=results, coverage_admitted=False,
        simulator_rerun=False, input_pins=common))
    print('MATRIX_QUALIFICATION ' + life.digest(OUT / 'result.json'), flush=True)


def admit(result_seal):
    require(not ADMIT.exists(), 'Fresh admission only')
    plan, pins, before = context()
    result = life.read_bound(OUT / 'result.json', result_seal)
    require(result['plan_seal'] == SEAL and result['baseline_seal'] == matrix.BASE_SHA and
            [r['case'] for r in result['cases']] == [r['case'] for r in plan['cases']], 'Qualification matrix identity differs')
    pins = life.merge_pins(pins, {str(OUT / 'result.json'): result_seal})
    singles = []; accepted = []; excluded = []
    for row, record in zip(result['cases'], plan['cases']):
        if row['status'] != 'PASS':
            require(row['status'] == 'FAILED_NOT_ADMITTED', 'Unknown matrix outcome')
            excluded.append(row); continue
        path = Path(row['qualification']); q = life.read_bound(path, row['seal'])
        require(q['status'] == 'MATRIX_CASE_WAVE_ARCHITECTURE_PASS_NOT_ADMITTED' and q['case'] == record['case'] and
                q['sew'] == record['sew'] and q['stage'] == record['stage'] and q['baseline'] == 746 and
                q['software_checks'] == 679 and q['full_vrf_bytes'] == 4096 and q['csr_words'] == 5 and
                q['source_guards_checked'] is True and q['axi_all_channels_verified'] is True and
                q['epoch_count'] == 2 and q['coverage_admitted'] is False and q['uvm_check_report_pass'] is False,
                'Incomplete or mismatched case qualification')
        pins = life.merge_pins(pins, q['output_pins'])
        evidence = path.parent / 'evidence-pins.json'
        pins = life.merge_pins(pins, life.read_bound(evidence, q['output_pins'][str(evidence)]))
        pins = life.merge_pins(pins, {str(path): row['seal']})
        single_path = path.parent / 'single-bits.json'
        single = life.read_bound(single_path, q['output_pins'][str(single_path)])
        require(single['tests'] == [str(Path(record['output']) / 'code.vdb')] and
                all(pins.get(p) == sha for p, sha in single['input_hashes'].items()), 'Wrong/unbound qualified singleton')
        singles.append(single); accepted.append(row)
    require(bool(singles), 'No independently qualified cases')
    combined = merge(before, singles); delta = shared.coverage.all_delta(before, combined)
    require(sum(delta['metrics'].values()) > 0, 'No new raw product coverage')
    life.check(pins); ADMIT.mkdir()
    final = 746 + len(singles)
    status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', baseline=746, aggregate_passed=final, new_passed=len(singles),
        exact746_prefix=True, full_OR_instances=6162, raw_delta=delta['metrics'], coverage_admitted=True,
        accepted=accepted, excluded=excluded, independent_external_reset_wave_and_architecture_pass=True,
        uvm_check_report_pass=False, missing_uvm_summary_preserved=True, official_denominator_verified=False,
        rtl_changed=False, simulation_rerun=False)
    for name, obj in [('combined-bits.json', combined), ('raw-delta.json', delta), ('status.json', status)]:
        life.save(ADMIT / name, obj)
    with (ADMIT / 'combined-inputs.txt').open('x') as stream:
        stream.write('\n'.join([str(shared.coverage.DESIGN)] + combined['tests']) + '\n')
    life.check(pins)
    life.save(ADMIT / 'admission-manifest.json', dict(schema='FPU_RESET_MATRIX_FORMAL_ADMISSION_V1', output=str(ADMIT),
        baseline=str(matrix.BASE), baseline_seal=matrix.BASE_SHA, qualification_seal=result_seal,
        explicit_parent_authorized=True, input_pins=pins,
        output_pins={str(p): life.digest(p) for p in ADMIT.iterdir()}))
    print('MATRIX_ADMITTED %d %s %s' % (final, life.digest(ADMIT / 'admission-manifest.json'), json.dumps(delta['metrics'])), flush=True)


def verify(seal):
    manifest = life.read_bound(ADMIT / 'admission-manifest.json', seal)
    require(manifest['schema'] == 'FPU_RESET_MATRIX_FORMAL_ADMISSION_V1' and
            manifest['baseline'] == str(matrix.BASE) and manifest['baseline_seal'] == matrix.BASE_SHA and
            manifest['output'] == str(ADMIT) and manifest['explicit_parent_authorized'] is True,
            'Admission source/schema differs')
    life.check(manifest['input_pins']); life.check(manifest['output_pins'])
    def read(path):
        pins = life.merge_pins(manifest['input_pins'], manifest['output_pins'])
        return life.read_bound(path, pins[str(path)])
    result = life.read_bound(OUT / 'result.json', manifest['qualification_seal'])
    status = read(ADMIT / 'status.json')
    accepted = [r for r in result['cases'] if r['status'] == 'PASS']
    require(status['accepted'] == accepted and status['excluded'] == [r for r in result['cases'] if r['status'] != 'PASS']
            and status['baseline'] == 746 and status['aggregate_passed'] == 746 + len(accepted) and
            status['coverage_admitted'] is True and status['uvm_check_report_pass'] is False,
            'Admission outcome differs')
    singles = []
    for row in accepted:
        path = Path(row['qualification']); qualification = life.read_bound(path, row['seal'])
        require(qualification['status'] == 'MATRIX_CASE_WAVE_ARCHITECTURE_PASS_NOT_ADMITTED', 'Unqualified case')
        singles.append(read(path.parent / 'single-bits.json'))
    before = read(matrix.BASE / 'combined-bits.json'); combined = merge(before, singles)
    delta = shared.coverage.all_delta(before, combined)
    require(read(ADMIT / 'combined-bits.json') == combined and read(ADMIT / 'raw-delta.json') == delta and
            status['raw_delta'] == delta['metrics'] and
            (ADMIT / 'combined-inputs.txt').read_text().splitlines() == [str(shared.coverage.DESIGN)] + combined['tests'],
            'Exact full OR/ledger/delta replay differs')
    print('MATRIX_OFFLINE_REVERIFIED ' + seal, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qualify', action='store_true'); p.add_argument('--admit-qualified-seal'); p.add_argument('--verify-seal')
    a = p.parse_args(); require(sum(bool(v) for v in (a.qualify, a.admit_qualified_seal, a.verify_seal)) == 1,
                              'One exact offline mode required')
    if a.qualify:
        qualify()
    elif a.admit_qualified_seal:
        admit(a.admit_qualified_seal)
    else:
        verify(a.verify_seal)
