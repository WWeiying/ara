"""Explicit formal729-or-successor raw diagnostic plan; no EDA or admission."""
import argparse
import json
from pathlib import Path

import coverage_bitmap_delta as bitmap
import inventory_operand_debug as compiled
from closure_point_inventory import definition, read_xml
import qualify_pure_war_budget900_terminal as q

life, require = q.life, q.require
DESIGN = life.OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb'
BASE729 = life.OUT / 'gap107-offline-admitted-729-parent-20261006-01'
BASE729_SEAL = 'e5bd9eeb19acc452d25db12f342c3c12532614a0c773c43355a33e34d8dd1912'
QUAL = life.OUT / 'pure-war-budget900-qualified-agent-20261006-01/qualification.json'
QUAL_SEAL = 'b6859948cfaf0949f5bd8ebc476fba46840ae67515b56876cd3cc17ce450d161'
PLAN_STATUS = 'PURE_WAR_RAW_DIAGNOSTIC_PREPARED_NOT_COLLECTED'


def baseline_contract(manifest, status, before, original, base):
    require(manifest['output'] == str(base) and manifest['output_pins'] and
            all(Path(p).parent == base for p in manifest['output_pins']), 'Baseline output alias')
    count = status['aggregate_passed']
    require(type(count) is int and count >= 729 and status['coverage_admitted'] is True and
            status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY', 'Not formal729 or successor')
    require(len(before['tests']) == len(set(before['tests'])) == count and
            len(original['tests']) == len(set(original['tests'])) == 729 and
            before['tests'][:729] == original['tests'], 'Exact729 prefix differs')
    require(before['design'] == original['design'], 'Historical design differs')
    life.merge_pins(before['input_hashes'], original['input_hashes'])
    return count


def qualification_contract(record):
    require(record['status'] == 'PURE_WAR_FULL_DUT_QUALIFIED_NOT_ADMITTED' and
            record['run'] == str(life.OUT / 'pure-war-budget900-parent-20261006-01') and
            record['coverage_admitted'] is False and record['rtl_changed'] is False and
            record['simulations_started'] is False and
            record['raw_coverage_increment_not_collected'] is True, 'Not exact full900 qualification')


def target_contract(targets, before):
    require(len(targets) == 4, 'Exactly four targets required')
    d = compiled.Design(DESIGN)
    shape = read_xml(d.db / 'shape/cond.verilog.shape.xml')
    for lane, target in enumerate(targets):
        scope = f'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[{lane}].i_lane.i_operand_requester'
        require(target['scope'] == scope and target['metric'] == 'cond' and
                target['raw_index'] == 1059 and target['width'] == 1256 and
                target['checksum'] == '1592560956', 'Target scope/shape differs')
        row = before['metrics']['cond'][scope]
        require((row['width'], row['checksum']) == (1256, '1592560956'), 'Baseline target shape differs')
        node = definition(shape, d.hierarchy[scope], row['checksum'])
        point = next(p for p in compiled.points('cond', node, row['width']) if p['raw_index'] == 1059)
        require(point == target['point'] and d.source(scope) == target['source'] and
                point['native_id'] == '402' and point['file_id'] == '552' and
                point['line'] == '496' and point['vector'] == '010' and
                point['spec']['generate_info'] == 'requester_index=8', 'Compiled target/source differs')


def combine(before, single, run):
    require(single['tests'] == [str(run / 'code.vdb')] and
            single['tests'][0] not in before['tests'], 'Duplicate/wrong candidate VDB')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    after = bitmap.combine(before, single)
    require(after['tests'] == before['tests'] + single['tests'] and
            len(set(after['tests'])) == len(after['tests']), 'Baseline prefix/unique singleton differs')
    return after, bitmap.delta(before, after)


def prepare(out, base, seal):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh plan directory required')
    require(base.parent == life.OUT and base.resolve() == base, 'Exact baseline directory required')
    record = life.read_bound(QUAL, QUAL_SEAL); qualification_contract(record)
    pins = life.merge_pins(record['pins'], {str(QUAL): QUAL_SEAL})
    def baseline(path, expected):
        nonlocal pins
        manifest = life.read_bound(path / 'admission-manifest.json', expected)
        pins = life.merge_pins(life.merge_pins(pins, {str(path / 'admission-manifest.json'): expected}), manifest['output_pins'])
        life.check(manifest['output_pins'])
        return manifest, json.loads((path / 'status.json').read_bytes()), json.loads((path / 'combined-bits.json').read_bytes())
    _, _, original = baseline(BASE729, BASE729_SEAL)
    manifest, status, before = baseline(base, seal)
    count = baseline_contract(manifest, status, before, original, base)
    require((base / 'combined-inputs.txt').read_text().splitlines() == [str(DESIGN), *before['tests']], 'Formal input order differs')
    pins = life.merge_pins(life.merge_pins(pins, before['input_hashes']),
        {str(DESIGN / 'snps/coverage/db' / p): h for p, h in before['design'].items()})
    pre = life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.runner.PRE_SEAL)
    targets = pre['targets']; target_contract(targets, before)
    run = Path(record['run'])
    require(str(run / 'code.vdb') not in before['tests'], 'Candidate already in formal baseline')
    # The terminal VDB is pinned now, but is parsed only by explicit collect.
    for metric in bitmap.METRICS:
        files = list((run / 'code.vdb/snps/coverage/db/testdata').glob(f'*/{metric}.verilog.data.xml'))
        require(len(files) == 1, 'Missing/ambiguous terminal coverage metric')
        pins = life.merge_pins(pins, {str(files[0]): life.digest(files[0])})
    for mod in (bitmap, compiled, q, q.frozen):
        path = Path(mod.__file__).resolve(); pins = life.merge_pins(pins, {str(path): life.digest(path)})
    for name in ('prepare_pure_war_raw_gain.py', 'test_prepare_pure_war_raw_gain.py'):
        path = Path(__file__).with_name(name); pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    out.mkdir()
    life.save(out / 'plan.json', dict(status=PLAN_STATUS, baseline=str(base), baseline_seal=seal,
        baseline_count=count, qualification=str(QUAL), qualification_seal=QUAL_SEAL,
        run=str(run), targets=targets, pins=pins, coverage_admitted=False, simulations_started=False,
        rtl_changed=False, native_DVE_selector_binding=False, positive_gain_required_for_future_admission=True,
        zero_gain_or_unhit_targets_preserved=True, source_lifetime_stall_not_directly_observed=True))
    print(json.dumps(dict(plan=str(out / 'plan.json'), seal=life.digest(out / 'plan.json'), pins=len(pins))))


def verify(path, seal):
    plan = life.read_bound(path, seal)
    require(plan['status'] == PLAN_STATUS and plan['coverage_admitted'] is False and
            plan['qualification'] == str(QUAL) and plan['qualification_seal'] == QUAL_SEAL, 'Plan contract differs')
    life.check(plan['pins'])
    manifest = life.read_bound(Path(plan['baseline']) / 'admission-manifest.json', plan['baseline_seal'])
    original_manifest = life.read_bound(BASE729 / 'admission-manifest.json', BASE729_SEAL)
    life.check(manifest['output_pins']); life.check(original_manifest['output_pins'])
    base = Path(plan['baseline']); before = json.loads((base / 'combined-bits.json').read_bytes())
    original = json.loads((BASE729 / 'combined-bits.json').read_bytes())
    require(baseline_contract(manifest, json.loads((base / 'status.json').read_bytes()), before, original, base)
            == plan['baseline_count'], 'Plan population drift')
    qualification_contract(life.read_bound(QUAL, QUAL_SEAL)); target_contract(plan['targets'], before)
    return plan, before


def collect(path, seal, out):
    plan, before = verify(path, seal)
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh diagnostic output required')
    out.mkdir()
    try:
        inputs = out / 'single-inputs.txt'
        with inputs.open('x') as stream:
            stream.write(str(DESIGN) + '\n' + str(Path(plan['run']) / 'code.vdb') + '\n')
        single = bitmap.collect(inputs)
        require(all(plan['pins'].get(p) == h for p, h in single['input_hashes'].items()), 'Collected VDB pin drift')
        after, change = combine(before, single, Path(plan['run']))
        def hit(row, raw):
            return bool(int(row['bits'], 16) & (1 << (row['width'] - 1 - raw)))
        hits = [dict(**t, before_hit=hit(before['metrics']['cond'][t['scope']], t['raw_index']),
                     single_hit=hit(single['metrics']['cond'][t['scope']], t['raw_index']),
                     after_hit=hit(after['metrics']['cond'][t['scope']], t['raw_index'])) for t in plan['targets']]
        life.check(plan['pins'])
        for name, value in [('single-bits.json', single), ('combined-bits.proposed.json', after),
                            ('raw-delta.json', change), ('target-hits.json', hits)]:
            life.save(out / name, value)
        pins = life.merge_pins(life.merge_pins(plan['pins'], {str(path): seal}),
                              {str(p): life.digest(p) for p in out.iterdir() if p.is_file()})
        life.save(out / 'diagnostic.json', dict(status='PURE_WAR_QUALIFIED_RAW_DIAGNOSTIC_NOT_ADMITTED',
            baseline=plan['baseline'], baseline_seal=plan['baseline_seal'], baseline_count=plan['baseline_count'],
            exact_baseline_prefix=True, unique_new_vdb=True, qualification_seal=QUAL_SEAL,
            raw_delta=change['metrics'], targets_hit_single=sum(h['single_hit'] for h in hits),
            new_targets=sum(h['single_hit'] and not h['before_hit'] for h in hits), pins=pins,
            positive_raw_gain=sum(change['metrics'].values()) > 0, coverage_admitted=False,
            source_lifetime_stall_proven=False, native_DVE_selector_binding=False,
            rtl_changed=False, simulations_started=False, baseline_VDBs_recollected=False))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'diagnostic.json'), delta=change['metrics'], admitted=0)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='RAW_DIAGNOSTIC_FAIL_NOT_ADMITTED', reason=str(error), coverage_admitted=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'collect'))
    for name in ('output', 'baseline', 'plan'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--baseline-seal'); parser.add_argument('--seal')
    a = parser.parse_args()
    if a.mode == 'prepare':
        require(a.output and a.baseline and a.baseline_seal and not a.plan and not a.seal, 'Explicit fresh plan/base/seal required')
        prepare(a.output.absolute(), a.baseline.absolute(), a.baseline_seal)
    elif a.mode == 'verify':
        require(a.plan and a.seal and not a.output and not a.baseline, 'Plan/seal only')
        verify(a.plan.absolute(), a.seal); print('VERIFY_PASS PURE_WAR_RAW_PLAN NO_ADMISSION')
    else:
        require(a.plan and a.seal and a.output and not a.baseline, 'Plan/seal/fresh output required')
        collect(a.plan.absolute(), a.seal, a.output.absolute())


if __name__ == '__main__':
    main()
