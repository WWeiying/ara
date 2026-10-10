"""Exact737 + reviewed clip17 terminal proof: raw candidate and separate admission. No EDA."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex

import coverage_bitmap_delta as bitmap
import qualify_narrow_clip_reject_terminal as q
from closure_point_inventory import read_xml

life, require = q.life, q.require
OUT = life.OUT
BASE = OUT / 'narrow-source-group-offline-admitted-737-parent-20261006-01'
BASE_SEAL = 'bd0ee8b3f52627578b120eb97109d7efc40a6e44466867f3d816ca2ec35a12ad'
RUN = OUT / 'narrow-clip-reject-450-old-image-parent-20261006-01'
RUN_SEAL = '2e7cac11b8c42b8cf1c514f8cb41fd695753927ec154e11c61cfa82d03ffeafe'
QUAL_PLAN = OUT / 'narrow-clip-reject-450-qualification-plan-parent-20261006-02/plan.json'
QUAL_PLAN_SEAL = 'c4e45acf7793251ea058481ec94aba322e56747ec0db379ecdf98bfe3c0ce906'
QUAL = OUT / 'narrow-clip-reject-450-qualified-parent-20261006-01/qualification-seal.json'
QUAL_SEAL = '990f68434c1a2caa0c9d4902ad5bc972abb072c843226187662d033f295f1007'
QUALIFIER_SHA = '327c27954429d5b5d3a60d93c5d802a1b22ac36d8236bdbc1ce17e52571a2f59'
BITMAP_SHA = 'e251f049f619ca86e4a9578a468ddca8619ac532ead0ed0c5661a7ee3756e0e3'
DESIGN = Path(str(life.IMAGE) + '.vdb')
POSITIVE = 'CLIP17_POSITIVE_PRIMARY_RAW_GAIN_NOT_ADMITTED'
HOLD = 'CLIP17_ZERO_OR_NO_PRIMARY_GAIN_HOLD_NOT_ADMITTED'
PROOFS = ('scalar-comparison.json', 'vector-comparison.json', 'observed-signatures.json',
          'lifecycle.json', 'trap-proof.json', 'contract-summary.json', 'status.json')


def canonical(path, fresh=False):
    require(path.resolve() == path and path.parent == OUT and (not fresh or not path.exists()),
            'Canonical direct output required; no overwrite')


def qualification_gate(result):
    fixed = dict(status='CLIP17_FULL_SCALAR_MEMORY_VECTOR_CSR_TRAP_QUALIFIED_NOT_ADMITTED',
                 run=str(RUN), baseline=737, preflight_seal=q.PRE_SEAL, checks=2094, expected_traps=17,
                 normal_vector_writers=33, timeout_s=450, native_known_write_bytes=4100,
                 runner_sha256=q.RUNNER_SHA, runner_test_sha256=q.RUNNER_TEST_SHA,
                 full_scalar_differential_qualified=True, all_scalar_memory_differential_qualified=True,
                 software_noC=True, compressed_retirements=0, skipped_scalar_memory=0, full_VRF_snapshots=3,
                 per_cell_rejected_backend_uops=0, per_cell_rejected_native_events=0, OS_returncode=0,
                 terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT')
    for key, value in fixed.items():
        require(type(result.get(key)) is type(value) and result[key] == value, 'Qualification mismatch: ' + key)
    for key in ('coverage_admitted', 'raw_bitmap_collected', 'rtl_changed', 'simulations_started',
                'new_RTL_signoff', 'native_cycle_qualified', 'whole_ISA_qualified',
                'official_denominator_verified', 'application_approval'):
        require(result.get(key) is False, 'Qualification promoted: ' + key)


def union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 737 and
            single['tests'] == [str(RUN / 'code.vdb')] and single['tests'][0] not in before['tests'],
            'Exact737 prefix and unique clip singleton required')
    for sample in (before, single):
        require(set(sample['metrics']) == set(bitmap.METRICS) and
                sum(len(rows) for rows in sample['metrics'].values()) == 6162, 'Full6162 universe required')
        for rows in sample['metrics'].values():
            for row in rows.values():
                require(type(row['width']) is int and row['width'] >= 0 and
                        0 <= int(row['bits'], 16) < 1 << row['width'], 'Malformed bitmap')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    combined = bitmap.combine(before, single)
    require(combined['tests'] == before['tests'] + single['tests'] and len(set(combined['tests'])) == 738,
            'Exact737 prefix lost')
    for metric, rows in before['metrics'].items():
        for scope, row in rows.items():
            require(int(combined['metrics'][metric][scope]['bits'], 16) ==
                    int(row['bits'], 16) | int(single['metrics'][metric][scope]['bits'], 16), 'Full OR differs')
    return combined, bitmap.delta(before, combined)


def target_hits(before, single, targets):
    require(len(targets) == 42 and len({(t['metric'], t['scope'], t['point']['raw_index']) for t in targets}) == 42,
            'Exact42 compiled targets required')
    hits = []
    for t in targets:
        old, new = (sample['metrics'][t['metric']][t['scope']] for sample in (before, single))
        require((old['width'], old['checksum']) == (new['width'], new['checksum']) == (t['width'], t['checksum']) and
                t['hit_before'] is False, 'Target shape/baseline differs')
        index = t['point']['raw_index']
        require(type(index) is int and 0 <= index < t['width'], 'Invalid target index')
        mask = 1 << (t['width'] - 1 - index)
        require(not int(old['bits'], 16) & mask, 'Target already hit737')
        hit = bool(int(new['bits'], 16) & mask)
        hits.append(dict(t, single_hit=hit, fresh_target_gain=hit, native_ID_claimed=False))
    return hits


def gain_status(delta, hits):
    require(set(delta['metrics']) == set(bitmap.METRICS) and
            all(type(v) is int and v >= 0 for v in delta['metrics'].values()), 'Invalid actual delta')
    return POSITIVE if sum(delta['metrics'].values()) > 0 and any(h['fresh_target_gain'] for h in hits) else HOLD


def inputs(qualification, seal):
    require(qualification == QUAL and seal == QUAL_SEAL, 'Exact parent clip17 qualification/seal required')
    require(qualification.name == 'qualification-seal.json' and qualification.parent.parent == OUT and
            qualification.resolve() == qualification, 'Direct sealed qualification required')
    require(life.digest(Path(q.__file__)) == QUALIFIER_SHA and life.digest(Path(bitmap.__file__)) == BITMAP_SHA,
            'Frozen qualifier/bitmap drift')
    proof = life.read_bound(qualification, seal); qualification_gate(proof['result'])
    require(set(proof['output_pins']) == {str(qualification.parent / n) for n in PROOFS}, 'Full owned proof outputs required')
    pins = life.merge_pins(proof['input_pins'], proof['output_pins'])
    pins = life.merge_pins(pins, {str(qualification): seal})
    require(pins.get(str(QUAL_PLAN)) == QUAL_PLAN_SEAL and pins.get(str(Path(q.__file__).resolve())) == QUALIFIER_SHA,
            'Reviewed qualification plan/source pin missing')
    plan, prepared, pre = q.verify_plan(QUAL_PLAN, QUAL_PLAN_SEAL)
    require(plan['run'] == str(RUN) and plan['prepared_seal'] == RUN_SEAL and
            all(pins.get(p) == h for p, h in prepared['pins'].items()), 'Exact450 prepared lineage required')
    require(pins.get(str(RUN.with_name(RUN.name + '.prepared.json'))) == RUN_SEAL, 'Prepared seal pin missing')
    def artifact(name):
        path = qualification.parent / name
        return life.read_bound(path, proof['output_pins'][str(path)])
    require(artifact('status.json') == proof['result'], 'Qualification status differs')
    control = artifact('lifecycle.json')
    require(control['exceptions'] == 17 and control['rejected_backend_uops'] == control['rejected_vrf_activities'] == 0 and
            len(control['per_cell']) == len(control['rejected_arch_seqs']) == 17 and
            [c['cell'] for c in control['per_cell']] == list(range(17)) and
            [c['arch_seq'] for c in control['per_cell']] == control['rejected_arch_seqs'] and
            all(c['rejected_backend_uops'] == c['rejected_native_events'] == 0 for c in control['per_cell']),
            'Full17 zero-backend/native proof required')
    q.common.scalar_exact(artifact('scalar-comparison.json'), pre['reference_counts'])
    q.vector_gate(artifact('vector-comparison.json'), control['rejected_arch_seqs'],
                  q.p.frozen.shared.parse_spike_commits(q.PRE / 'spike.trace'))
    for name in ('simulation-status.json', 'manifest.json', 'started.json', 'commit_trace.csv', 'vector_trace.csv',
                 'console.log', 'run.vcs.log', 'trace_hart_0.log', 'trace_hart_0_commit.log'):
        require(str(RUN / name) in pins, 'Dropped terminal evidence: ' + name)
    q.terminal(life.read_bound(RUN/'simulation-status.json', pins[str(RUN/'simulation-status.json')]),
               life.read_bound(RUN/'manifest.json', pins[str(RUN/'manifest.json')]),
               life.read_bound(RUN/'started.json', pins[str(RUN/'started.json')]), prepared)
    baseline = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    require(baseline['output'] == str(BASE), 'Formal737 ownership differs')
    pins = life.merge_pins(pins, baseline['output_pins'])
    pins = life.merge_pins(pins, {str(BASE / 'admission-manifest.json'): BASE_SEAL})
    before = life.read_bound(BASE / 'combined-bits.json', pins[str(BASE / 'combined-bits.json')])
    state = life.read_bound(BASE / 'status.json', pins[str(BASE / 'status.json')])
    require(state['aggregate_passed'] == 737 and state['coverage_admitted'] is True and
            state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            (BASE / 'combined-inputs.txt').read_text().splitlines() == [str(DESIGN), *before['tests']], 'Exact formal737 required')
    pins = life.merge_pins(pins, before['input_hashes'])
    targets, sourcepins = q.p.targets()
    require(targets == pre['targets'] == plan['targets'], 'Exact frozen source/compiled targets differ')
    pins = life.merge_pins(pins, sourcepins)
    directory = RUN / 'code.vdb/snps/coverage/db/testdata' / q.p.APP.stem
    require(directory.resolve() == directory and list(directory.parent.iterdir()) == [directory], 'Wrong singleton directory')
    names = {'vcmArguments.xml', 'siminfo.xml', *{m + '.verilog.data.xml' for m in (*bitmap.METRICS, 'tgl')}}
    require({x.name for x in directory.iterdir()} == names, 'Wrong singleton membership')
    args, info = read_xml(directory / 'vcmArguments.xml'), read_xml(directory / 'siminfo.xml')
    tests = list(info.iter('srctest'))
    options = [x.get('vcm_opt') for x in args.iter('vcm_arg_data') if x.get('vcm_opt') is not None]
    require(args.get('compvdbpath') == str(DESIGN) and len(options) == 5 and
            set(options) == {'-cm ' + m for m in ('line', 'cond', 'branch', 'fsm', 'tgl')} and len(tests) == 1 and
            shlex.split(tests[0].get('cmdline', '')) == prepared['command'] and tests[0].get('workdir') == str(RUN) and
            tests[0].get('seed') == '1' and tests[0].get('teststatus') == 'unknown', 'Singleton command/design identity differs')
    for x in directory.iterdir():
        require(x.is_file() and not x.is_symlink() and pins.get(str(x)) == life.digest(x), 'Unqualified raw evidence')
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_clip17_raw_admission.py')):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    return before, targets, pins


def evaluate(plan):
    require(plan['status'] == 'CLIP17_GAIN_PLAN_NOT_COLLECTED' and plan['baseline_seal'] == BASE_SEAL and
            plan['baseline'] == str(BASE) and plan['coverage_admitted'] is False, 'Exact gain plan required')
    before, targets, pins = inputs(Path(plan['qualification']), plan['qualification_seal'])
    require(pins == plan['pins'] and targets == plan['targets'], 'Plan pins/targets drift')
    return before, targets, pins


def raw_products(plan, inputfile, context=None):
    before, targets, pins = evaluate(plan) if context is None else context
    require(inputfile.read_text().splitlines() == [str(DESIGN), str(RUN / 'code.vdb')], 'Exact singleton input ordering')
    single = bitmap.collect(inputfile)
    expected = {str(RUN / 'code.vdb/snps/coverage/db/testdata' / q.p.APP.stem / (m + '.verilog.data.xml')):
                pins[str(RUN / 'code.vdb/snps/coverage/db/testdata' / q.p.APP.stem / (m + '.verilog.data.xml'))] for m in bitmap.METRICS}
    require(single['input_hashes'] == expected, 'Four actual singleton data hashes differ')
    combined, delta = union(before, single)
    hits = target_hits(before, single, targets)
    return {'single-bits.json': single, 'combined-bits.json': combined, 'raw-delta.json': delta,
            'target-hits.json': hits}, pins


def candidate(directory, seal):
    canonical(directory)
    record = life.read_bound(directory / 'candidate.json', seal)
    require(record['output'] == str(directory) and record['coverage_admitted'] is False and
            record['baseline_seal'] == BASE_SEAL and record['exact737_prefix'] is True and
            record['full_OR_instances'] == 6162, 'Exact candidate scope required')
    for key in ('application_approval', 'native_cycle_qualified', 'DVE_native_exclusion_qualified'):
        require(record.get(key) is False, 'Candidate promoted: ' + key)
    names = ('single-inputs.txt', 'single-bits.json', 'combined-bits.json', 'raw-delta.json', 'target-hits.json',
             'combined-inputs.txt', 'evidence-pins.json')
    require(set(record['output_pins']) == {str(directory / n) for n in names}, 'Owned candidate outputs required')
    life.check(record['output_pins'])
    planpath = Path(record['plan']); plan = life.read_bound(planpath, record['plan_seal'])
    products, pins = raw_products(plan, directory / 'single-inputs.txt')
    pins = life.merge_pins(pins, {str(planpath): record['plan_seal']})
    for name, obj in products.items():
        require(life.read_bound(directory / name, record['output_pins'][str(directory/name)]) == obj, 'Candidate replay differs: ' + name)
    require(life.read_bound(directory/'evidence-pins.json', record['output_pins'][str(directory/'evidence-pins.json')]) == pins,
            'Dropped evidence pins')
    text = '\n'.join([str(DESIGN), *products['combined-bits.json']['tests']]) + '\n'
    require((directory/'combined-inputs.txt').read_text() == text and record['status'] ==
            gain_status(products['raw-delta.json'], products['target-hits.json']) and
            record['raw_delta'] == products['raw-delta.json']['metrics'] and
            record['qualification'] == plan['qualification'] and record['qualification_seal'] == plan['qualification_seal'],
            'Candidate status/lineage differs')
    life.check(pins)
    return record, products, pins, text


def admission_products(directory, seal):
    record, products, pins, text = candidate(directory, seal)
    require(record['status'] == POSITIVE, 'Zero/no primary gain HOLD; admission forbidden')
    pins = life.merge_pins(pins, record['output_pins'])
    pins = life.merge_pins(pins, {str(directory/'candidate.json'): seal})
    products['evidence-pins.json'] = pins
    products['status.json'] = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', baseline=737, aggregate_passed=738,
        new_passed=1, case=q.p.APP.stem, coverage_admitted=True, exact737_prefix=True, full_OR_instances=6162,
        raw_delta=record['raw_delta'], checks=2094, expected_traps=17, native_known_write_bytes=4100,
        rejected_backend_uops=0, rejected_VRF_activities=0, UVM_errors=0, UVM_override_applied=False,
        qualification=record['qualification'], qualification_seal=record['qualification_seal'], candidate_seal=seal,
        historical_fixed_image_only=True, new_RTL_signoff=False, official_denominator_verified=False,
        application_approval=False, native_cycle_qualified=False, whole_ISA_qualified=False,
        rtl_changed=False, simulations_started=False)
    return record, products, text


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare-gain', 'collect-gain', 'verify-candidate', 'prepare-admission', 'admit'))
    for key in ('qualification', 'plan', 'candidate', 'output'): p.add_argument('--' + key, type=Path)
    p.add_argument('--seal'); p.add_argument('--prepared-seal'); p.add_argument('--parent-authorized', action='store_true')
    a = p.parse_args(argv)
    require(a.seal and ((a.mode == 'admit') == a.parent_authorized), 'Seal and separate admission authorization required')
    if a.mode == 'prepare-gain':
        require(a.qualification and a.output, 'Qualification/output required'); out = a.output.absolute(); canonical(out, True)
        before, targets, pins = inputs(a.qualification.absolute(), a.seal)
        require(len(before['tests']) == len(set(before['tests'])) == 737, 'Exact737 required')
        out.mkdir(); life.save(out/'plan.json', dict(status='CLIP17_GAIN_PLAN_NOT_COLLECTED',
            qualification=str(a.qualification.absolute()), qualification_seal=a.seal, baseline=str(BASE), baseline_seal=BASE_SEAL,
            targets=targets, pins=pins, coverage_admitted=False))
        print(json.dumps(dict(plan=str(out/'plan.json'), seal=life.digest(out/'plan.json')))); return
    if a.mode == 'collect-gain':
        require(a.plan and a.output, 'Plan/output required'); out = a.output.absolute(); canonical(out, True)
        plan = life.read_bound(a.plan.absolute(), a.seal); context = evaluate(plan)
        out.mkdir(); (out/'single-inputs.txt').write_text(str(DESIGN)+'\n'+str(RUN/'code.vdb')+'\n')
        products, pins = raw_products(plan, out/'single-inputs.txt', context)
        pins = life.merge_pins(pins, {str(a.plan.absolute()): a.seal})
        for name, obj in dict(products, **{'evidence-pins.json': pins}).items(): life.save(out/name, obj)
        (out/'combined-inputs.txt').write_text('\n'.join([str(DESIGN), *products['combined-bits.json']['tests']])+'\n')
        life.check(pins)
        life.save(out/'candidate.json', dict(status=gain_status(products['raw-delta.json'], products['target-hits.json']),
            output=str(out), plan=str(a.plan.absolute()), plan_seal=a.seal, qualification=plan['qualification'],
            qualification_seal=plan['qualification_seal'], baseline_seal=BASE_SEAL, exact737_prefix=True,
            full_OR_instances=6162, raw_delta=products['raw-delta.json']['metrics'], coverage_admitted=False,
            application_approval=False, native_cycle_qualified=False, DVE_native_exclusion_qualified=False,
            output_pins={str(x):life.digest(x) for x in out.iterdir() if x.is_file()}))
        print(json.dumps(dict(candidate=str(out/'candidate.json'), seal=life.digest(out/'candidate.json')))); return
    require(a.candidate, 'Candidate required')
    if a.mode == 'verify-candidate':
        candidate(a.candidate.absolute(), a.seal); print('VERIFY_PASS NOT_ADMITTED'); return
    require(a.output, 'Formal output required'); out = a.output.absolute(); canonical(out, True)
    record, products, text = admission_products(a.candidate.absolute(), a.seal)
    hashes = {str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in products.items()}
    hashes[str(out/'combined-inputs.txt')] = hashlib.sha256(text.encode()).hexdigest()
    prepared = dict(schema='CLIP17_RAW_ADMISSION_PREPARED_V1', output=str(out), candidate=str(a.candidate.absolute()),
                    candidate_seal=a.seal, baseline=str(BASE), baseline_seal=BASE_SEAL,
                    qualification=record['qualification'], qualification_seal=record['qualification_seal'],
                    input_pins=products['evidence-pins.json'], output_pins=hashes)
    sidecar = out.with_name(out.name+'.prepared.json')
    if a.mode == 'prepare-admission':
        require(not sidecar.exists() and not a.prepared_seal, 'Fresh admission review required')
        life.save(sidecar, prepared); print(json.dumps(dict(prepared=str(sidecar), seal=life.digest(sidecar)))); return
    require(a.prepared_seal and life.read_bound(sidecar,a.prepared_seal) == prepared, 'Reviewed admission drift')
    life.check(prepared['input_pins']); out.mkdir()
    for name,obj in products.items(): life.save(out/name,obj)
    (out/'combined-inputs.txt').write_text(text); life.check(hashes)
    life.save(out/'admission-manifest.json',dict(prepared, schema='CLIP17_RAW_HISTORICAL_ADMISSION_V1',
              prepared=str(sidecar), prepared_seal=a.prepared_seal))
    print(json.dumps(dict(output=str(out), admission_seal=life.digest(out/'admission-manifest.json'))))


if __name__ == '__main__': main()
