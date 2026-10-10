"""Scoped qualified store singleton vs sealed formal729/730; no EDA/admission."""
import argparse
import json
from pathlib import Path
import shlex

import qualify_store_fifo_burst_terminal as q
import coverage_bitmap_delta as bitmap
from closure_point_inventory import read_xml

life, require = q.life, q.require
OUT, DESIGN = life.OUT, Path(str(life.IMAGE) + '.vdb')
QUAL = OUT / 'store-fifo-burst-qualification-729-agent-20261006-01/qualification.json'
QUAL_SEAL = 'a47662c6244db0f0d51b3f895ba694c190a5f58aca5e881c0afb5a963e84628a'
BITMAP_SEAL = 'e251f049f619ca86e4a9578a468ddca8619ac532ead0ed0c5661a7ee3756e0e3'
ROOT_SCOPE = 'ara_tb.dut.i_ara_soc.i_system'
PLAN_STATUS = 'STORE_FIFO_RAW_GAIN_PLAN_ONLY_NOT_COLLECTED_NOT_ADMITTED'


def qualification(record):
    require(record['status'] == 'STORE_FIFO_BURST_FULL_DUT_SCALAR_VECTOR_MEMORY_QUALIFIED_NOT_ADMITTED' and
            record['run'] == str(q.RUN) and record['baseline_tests'] == 729 and record['checks'] == 2360 and
            record['native_known_bytes'] == 128 and record['full_scalar_reference_instructions'] == 60995 and
            record['terminal_source'] == 'FOREGROUND_RUNNER_OS_RETURN_RECEIPT' and
            type(record['OS_returncode']) is int and record['OS_returncode'] == 0 and record['UVM_errors'] == 0,
            'Wrong actual full DUT qualification')
    for key in ('UVM_override_applied', 'full_ISA_signoff', 'coverage_admitted', 'simulations_started',
                'rtl_changed', 'target_hit_verified', 'directly_observed_per_owner_AXI', 'FIFO_push_pop_measured'):
        require(record[key] is False, 'Qualification boundary promoted: ' + key)
    require(record['raw_coverage_increment_not_collected'] is True, 'Wrong original qualification phase')


def sample_metadata(directory, prepared):
    args = read_xml(directory / 'vcmArguments.xml')
    require(args.tag == 'vcm_args' and args.get('compvdbpath') == str(DESIGN), 'Wrong compiled VDB path')
    options = [n.get('vcm_opt') for n in args.iter('vcm_arg_data') if n.get('vcm_opt') is not None]
    require(set(options) == {'-cm ' + m for m in ('line', 'cond', 'branch', 'fsm', 'tgl')} and len(options) == 5,
            'Incomplete/duplicate actual coverage options')
    info = read_xml(directory / 'siminfo.xml')
    records = list(info.iter('srctest'))
    require(len(records) == 1 and shlex.split(records[0].get('cmdline', '')) == prepared['command'] and
            records[0].get('workdir') == str(q.RUN) and records[0].get('seed') == '1',
            'Singleton command/ELF/cwd/seed mismatch')
    require(records[0].get('teststatus') == 'unknown', 'Unexpected raw simulator status encoding')
    return dict(command_exact=True, compiled_design_exact=True, raw_simulator_teststatus='unknown',
                functional_verdict_source=str(QUAL), raw_teststatus_not_used_as_PASS=True)


def validate_population(before, single, population):
    require(population in (729, 730) and len(before['tests']) == len(set(before['tests'])) == population,
            'Not exact formal729/730 unique population')
    require(single['tests'] == [str(q.RUN / 'code.vdb')] and single['tests'][0] not in before['tests'],
            'Duplicate/wrong singleton VDB')
    for sample in (before, single):
        require(set(sample['metrics']) == set(bitmap.METRICS) and
                sum(len(rows) for rows in sample['metrics'].values()) == 6162, 'Incomplete6162 OR universe')
        for rows in sample['metrics'].values():
            for row in rows.values():
                require(type(row['width']) is int and row['width'] >= 0 and
                        0 <= int(row['bits'], 16) < (1 << row['width']), 'Malformed/overflow bitmap')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    combined = bitmap.combine(before, single)
    require(combined['tests'] == before['tests'] + single['tests'] and
            len(set(combined['tests'])) == population + 1, 'Exact baseline prefix lost')
    for metric, rows in before['metrics'].items():
        for scope, row in rows.items():
            require(combined['metrics'][metric][scope]['bits'] ==
                    hex(int(row['bits'], 16) | int(single['metrics'][metric][scope]['bits'], 16)), 'Full OR differs')
    return combined, bitmap.delta(before, combined)


def target_hits(before, single, targets):
    require(len(targets) == 8 and len({(t['scope'], t['metric'], t['raw_index']) for t in targets}) == 8,
            'Not exact eight source-bound targets')
    results = []
    for t in targets:
        metric, scope, raw = t['metric'], t['scope'], t['raw_index']
        old, new = before['metrics'][metric][scope], single['metrics'][metric][scope]
        require((old['width'], old['checksum']) == (new['width'], new['checksum']) == (t['width'], t['checksum']),
                'FIFO target shape/checksum drift')
        mask = 1 << (t['width'] - 1 - raw)
        a, b = bool(int(old['bits'], 16) & mask), bool(int(new['bits'], 16) & mask)
        results.append(dict(t, before_hit=a, single_hit=b, after_hit=a or b, fresh_target_gain=b and not a,
                            role='ALREADY_HIT_WITNESS' if a else 'MISSING_TARGET',
                            DVE_native_exclusion_qualified=False))
    return results


def candidate_status(delta, hits):
    return ('STORE_FIFO_POSITIVE_TARGET_GAIN_CANDIDATE_NOT_ADMITTED' if
            sum(delta['metrics'].values()) > 0 and any(t['fresh_target_gain'] for t in hits) else
            'STORE_FIFO_NO_FRESH_TARGET_GAIN_HOLD_NOT_ADMITTED')


def inputs(baseline, baseline_seal):
    require(baseline.parent == OUT and baseline.resolve() == baseline, 'Direct sealed formal baseline required')
    pins = {str(QUAL): QUAL_SEAL}
    result = life.read_bound(QUAL, QUAL_SEAL); qualification(result)
    pins = life.merge_pins(pins, result['pins'])
    pre = life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.PRE_SEAL)
    prepared = life.read_bound(q.PREPARED, q.RUN_SEAL); q.binding(pre, prepared)
    pins = life.merge_pins(pins, {str(q.PREPARED): q.RUN_SEAL,
        str(q.runner.PRE / 'preflight-manifest.json'): q.PRE_SEAL})
    manifest = life.read_bound(baseline / 'admission-manifest.json', baseline_seal)
    require(manifest['output'] == str(baseline) and all(Path(path).parent == baseline for path in manifest['output_pins']),
            'Formal output ownership differs')
    pins = life.merge_pins(pins, {str(baseline / 'admission-manifest.json'): baseline_seal})
    pins = life.merge_pins(pins, manifest['output_pins'])
    before = life.read_bound(baseline / 'combined-bits.json', pins[str(baseline / 'combined-bits.json')])
    status = life.read_bound(baseline / 'status.json', pins[str(baseline / 'status.json')])
    population = len(before['tests'])
    require(population in (729, 730) and status['aggregate_passed'] == population and
            status['coverage_admitted'] is True and status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY',
            'Baseline is not formally admitted729/730')
    require((baseline / 'combined-inputs.txt').read_text().splitlines() == [str(DESIGN), *before['tests']],
            'Baseline VDB order differs')
    anchor_manifest = life.read_bound(q.p.BASE / 'admission-manifest.json', q.p.BASE_SEAL)
    anchor = life.read_bound(q.p.BASE / 'combined-bits.json',
                             anchor_manifest['output_pins'][str(q.p.BASE / 'combined-bits.json')])
    require(before['tests'][:729] == anchor['tests'] and before['design'] == anchor['design'], 'Not exact sealed729 prefix/design')
    require(all(before['input_hashes'].get(path) == digest for path, digest in anchor['input_hashes'].items()),
            'Inherited729 bitmap pins dropped/changed')
    bitmap.delta(anchor, before)
    pins = life.merge_pins(pins, {str(q.p.BASE / 'admission-manifest.json'): q.p.BASE_SEAL,
        str(q.p.BASE / 'combined-bits.json'): anchor_manifest['output_pins'][str(q.p.BASE / 'combined-bits.json')]})
    pins = life.merge_pins(pins, before['input_hashes'])
    bound_targets, compiled_pins = q.p.target_binding()
    require(bound_targets == pre['targets'], 'Eight compiled expression/source bindings differ')
    pins = life.merge_pins(pins, compiled_pins)
    directory = q.RUN / 'code.vdb/snps/coverage/db/testdata' / q.p.NAME
    require(directory.parent.resolve() == directory.parent and
            list(directory.parent.iterdir()) == [directory], 'Extra/aliased singleton testdata')
    metadata = sample_metadata(directory, prepared)
    names = {'vcmArguments.xml', 'siminfo.xml', *{m + '.verilog.data.xml' for m in (*bitmap.METRICS, 'tgl')}}
    require({path.name for path in directory.iterdir()} == names, 'Unexpected singleton metadata membership')
    vdb_pins = {}
    for path in directory.iterdir():
        require(path.is_file() and not path.is_symlink(), 'Aliased/nonfile raw VDB evidence')
        vdb_pins[str(path)] = life.digest(path)
    pins = life.merge_pins(pins, vdb_pins)
    require(life.digest(Path(bitmap.__file__)) == BITMAP_SEAL, 'Frozen bitmap parser changed')
    deps = [Path(__file__).resolve(), Path(__file__).with_name('test_prepare_store_fifo_burst_gain.py'),
            Path(q.__file__).resolve(), Path(bitmap.__file__).resolve()]
    pins = life.merge_pins(pins, {str(path): life.digest(path) for path in deps})
    return before, bound_targets, pins, vdb_pins, metadata, population


def prepare(out, baseline, baseline_seal):
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct plan output required')
    before, targets, pins, vdb_pins, metadata, population = inputs(baseline, baseline_seal)
    life.check(pins)
    out.mkdir()
    life.save(out / 'plan.json', dict(status=PLAN_STATUS, baseline=str(baseline), baseline_seal=baseline_seal,
        baseline_tests=population, exact729_prefix=True, qualification=str(QUAL), qualification_seal=QUAL_SEAL,
        singleton=str(q.RUN / 'code.vdb'), targets=targets, pins=pins, singleton_pins=vdb_pins,
        source_bound_compiled_targets=8, metadata=metadata, full_OR_instances=6162,
        coverage_admitted=False, application_approval=False, actual_raw_collected=False,
        no_target_gain_policy='HOLD even if incidental QBS/other gain is positive',
        simulations_started=False, rtl_changed=False))
    print(json.dumps(dict(plan=str(out / 'plan.json'), seal=life.digest(out / 'plan.json'),
                          pins=len(pins), baseline_tests=population, actual_raw_collected=False)))


def collect(plan_path, seal, out):
    plan = life.read_bound(plan_path, seal)
    require(plan['status'] == PLAN_STATUS and plan['qualification_seal'] == QUAL_SEAL and
            plan['singleton'] == str(q.RUN / 'code.vdb') and plan['coverage_admitted'] is False and
            plan['application_approval'] is False, 'Gain plan identity differs')
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct candidate output required')
    before, targets, pins, vdb_pins, metadata, population = inputs(Path(plan['baseline']), plan['baseline_seal'])
    require((targets, pins, vdb_pins, metadata, population) ==
            (plan['targets'], plan['pins'], plan['singleton_pins'], plan['metadata'], plan['baseline_tests']), 'Plan/source/raw input drift')
    pins = life.merge_pins(pins, {str(plan_path): seal}); life.check(pins)
    out.mkdir()
    try:
        (out / 'single-inputs.txt').write_text(str(DESIGN) + '\n' + str(q.RUN / 'code.vdb') + '\n')
        single = bitmap.collect(out / 'single-inputs.txt')
        require(all(vdb_pins.get(path) == digest for path, digest in single['input_hashes'].items()), 'Raw bytes not sealed in plan')
        combined, delta = validate_population(before, single, population)
        hits = target_hits(before, single, targets)
        for name, value in [('single-bits.json', single), ('combined-bits.json', combined),
                            ('raw-delta.json', delta), ('target-hits.json', hits), ('evidence-pins.json', pins)]:
            life.save(out / name, value)
        (out / 'combined-inputs.txt').write_text(str(DESIGN) + '\n' + '\n'.join(combined['tests']) + '\n')
        life.check(pins)
        outputs = {str(path): life.digest(path) for path in out.iterdir() if path.is_file()}
        life.save(out / 'candidate.json', dict(status=candidate_status(delta, hits), baseline=plan['baseline'],
            baseline_seal=plan['baseline_seal'], baseline_tests=population, exact_baseline_prefix=True,
            exact729_prefix=True, full_OR_instances=6162, proposed_population=population + 1,
            qualification=str(QUAL), qualification_seal=QUAL_SEAL, plan=str(plan_path), plan_seal=seal,
            raw_delta=delta['metrics'], gained_target_positions=sum(t['fresh_target_gain'] for t in hits),
            incidental_gain_not_queue_target_proof=True, coverage_admitted=False, application_approval=False,
            directly_observed_per_owner_AXI=False, DVE_native_exclusion_qualified=False,
            simulations_started=False, rtl_changed=False, output_pins=outputs))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'candidate.json'),
                              status=candidate_status(delta, hits), raw_delta=delta['metrics'],
                              gained_targets=sum(t['fresh_target_gain'] for t in hits))))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='STORE_GAIN_REJECTED_NOT_ADMITTED', reason=str(error), coverage_admitted=False))
        raise


def verify_candidate(out, seal):
    record = life.read_bound(out / 'candidate.json', seal)
    require(record['coverage_admitted'] is False and record['application_approval'] is False and
            record['qualification_seal'] == QUAL_SEAL and record['qualification'] == str(QUAL), 'Candidate scope/approval differs')
    require(set(record['output_pins']) == {str(out / name) for name in
            ('single-inputs.txt', 'single-bits.json', 'combined-bits.json', 'raw-delta.json',
             'target-hits.json', 'evidence-pins.json', 'combined-inputs.txt')}, 'Candidate output pins dropped/foreign')
    require(record['directly_observed_per_owner_AXI'] is False and record['DVE_native_exclusion_qualified'] is False and
            record['simulations_started'] is False and record['rtl_changed'] is False, 'Candidate proof scope promoted')
    life.check(record['output_pins'])
    pins = json.loads((out / 'evidence-pins.json').read_bytes()); life.check(pins)
    plan = life.read_bound(Path(record['plan']), record['plan_seal'])
    before, targets, expected_pins, _, _, population = inputs(Path(plan['baseline']), plan['baseline_seal'])
    require(pins == life.merge_pins(expected_pins, {record['plan']: record['plan_seal']}), 'Candidate dropped/changed evidence pins')
    require((out / 'single-inputs.txt').read_text().splitlines() == [str(DESIGN), str(q.RUN / 'code.vdb')], 'Wrong singleton input')
    single = bitmap.collect(out / 'single-inputs.txt')
    combined, delta = validate_population(before, single, population)
    hits = target_hits(before, single, targets)
    for name, value in [('single-bits.json', single), ('combined-bits.json', combined), ('raw-delta.json', delta), ('target-hits.json', hits)]:
        require(json.loads((out / name).read_bytes()) == value, 'Candidate replay differs: ' + name)
    require(record['status'] == candidate_status(delta, hits) and record['raw_delta'] == delta['metrics'] and
            record['gained_target_positions'] == sum(t['fresh_target_gain'] for t in hits) and
            record['baseline'] == plan['baseline'] and record['baseline_seal'] == plan['baseline_seal'] and
            record['baseline_tests'] == population and record['proposed_population'] == population + 1 and
            record['full_OR_instances'] == 6162 and record['exact_baseline_prefix'] is True and record['exact729_prefix'] is True,
            'Candidate classification/prefix differs')
    require((out / 'combined-inputs.txt').read_text().splitlines() == [str(DESIGN), *combined['tests']], 'Exact full prefix differs')
    life.check(pins); life.check(record['output_pins'])
    print('STORE_FIFO_CANDIDATE_REVERIFIED_NOT_ADMITTED ' + seal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify-plan', 'collect', 'verify-candidate'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--baseline-seal')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--seal')
    args = parser.parse_args()
    if args.mode == 'prepare':
        require(args.output is not None and args.plan is None and args.seal is None and
                args.baseline is not None and args.baseline_seal is not None, 'Fresh plan output and explicit formal baseline/seal required')
        prepare(args.output.absolute(), args.baseline.absolute(), args.baseline_seal)
    elif args.mode == 'verify-plan':
        require(args.plan is not None and args.seal is not None, 'Plan/seal required')
        plan = life.read_bound(args.plan, args.seal)
        require(plan['status'] == PLAN_STATUS and plan['coverage_admitted'] is False, 'Plan status differs')
        before, targets, pins, vdb_pins, metadata, population = inputs(Path(plan['baseline']), plan['baseline_seal'])
        require((targets, pins, vdb_pins, metadata, population) ==
                (plan['targets'], plan['pins'], plan['singleton_pins'], plan['metadata'], plan['baseline_tests']), 'Plan replay differs')
        life.check(pins); print('VERIFY_PLAN_PASS NO_COLLECTION NO_EDA')
    elif args.mode == 'collect':
        require(args.plan is not None and args.seal is not None and args.output is not None, 'Plan/seal/fresh output required')
        collect(args.plan.absolute(), args.seal, args.output.absolute())
    else:
        require(args.output is not None and args.seal is not None, 'Candidate output/seal required')
        verify_candidate(args.output.absolute(), args.seal)


if __name__ == '__main__':
    main()
