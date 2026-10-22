"""Sealed full900 qualification + exact730 raw diagnostic; explicit offline731 only."""
import argparse
import json
from pathlib import Path

import prepare_pure_war_raw_gain as raw
import admit_gap107_offline as framework

life, require = raw.life, raw.require
BASE = life.OUT / 'gap108-offline-admitted-730-parent-20261006-01'
BASE_SEAL = '8da19c3fba8b438851231dfc79c8006caeea2364f578c29f9afa3c6fbf91d3f5'
CANDIDATE = life.OUT / 'pure-war-raw-diagnostic-730-parent-20261006-01'
CANDIDATE_SEAL = '5ed322cd80a3e5a134a4c3876a9e7cb51ff956481a4725cf48fa44394e165378'
QUAL_SEAL = raw.QUAL_SEAL
EXPECTED_DELTA = dict(line=0, cond=4, branch=0, fsm=0)
SCHEMA = 'PURE_WAR_HISTORICAL731_FULL_ARCHITECTURAL_ADMISSION_V1'


def candidate_contract(record):
    for key, value in dict(status='PURE_WAR_QUALIFIED_RAW_DIAGNOSTIC_NOT_ADMITTED',
        baseline=str(BASE), baseline_seal=BASE_SEAL, baseline_count=730,
        qualification_seal=QUAL_SEAL, exact_baseline_prefix=True, unique_new_vdb=True,
        raw_delta=EXPECTED_DELTA, targets_hit_single=4, new_targets=4,
        positive_raw_gain=True, coverage_admitted=False, rtl_changed=False,
        simulations_started=False, baseline_VDBs_recollected=False,
        native_DVE_selector_binding=False, source_lifetime_stall_proven=False).items():
        require(record.get(key) == value, 'Diagnostic contract differs: ' + key)


def exact_gain(before, after, targets):
    gained = set()
    for metric, rows in before['metrics'].items():
        for scope, row in rows.items():
            value = int(after['metrics'][metric][scope]['bits'], 16) & ~int(row['bits'], 16)
            for index in range(row['width']):
                if value & (1 << (row['width'] - 1 - index)):
                    gained.add((metric, scope, index))
    require(gained == {('cond', t['scope'], 1059) for t in targets} and len(gained) == 4,
            'Gain outside exact four compiled targets')


def evidence_elf_hashes(pins):
    """Check ELF/pin-ledger entries recursively; caller checks all other pins."""
    todo = [pins]; seen = set(); hashes = set()
    while todo:
        ledger = todo.pop()
        for path, seal in ledger.items():
            p = Path(path)
            if p.suffix.lower() == '.elf':
                life.check({path: seal}); hashes.add(seal)
            elif p.name.endswith('pins.json') and path not in seen:
                seen.add(path); life.check({path: seal})
                nested = json.loads(p.read_bytes())
                require(isinstance(nested, dict), 'Malformed inherited pin ledger')
                todo.append(nested)
    return hashes


def evaluate(base_seal, qualification_seal, candidate_seal):
    require((base_seal, qualification_seal, candidate_seal) == (BASE_SEAL, QUAL_SEAL, CANDIDATE_SEAL),
            'Only reviewed730/full900/diagnostic allowed')
    candidate = life.read_bound(CANDIDATE / 'diagnostic.json', candidate_seal); candidate_contract(candidate)
    pins = candidate['pins']; life.check(pins)
    qualification = life.read_bound(raw.QUAL, qualification_seal); raw.qualification_contract(qualification)
    require(life.merge_pins(pins, qualification['pins']) == pins, 'Lost complete qualification pins')
    manifest = life.read_bound(BASE / 'admission-manifest.json', base_seal)
    require(life.merge_pins(pins, manifest['output_pins']) == pins, 'Lost baseline output pins')
    life.check(manifest['output_pins'])
    def read(path):
        path = Path(path); require(str(path) in pins, 'Unpinned product: ' + str(path))
        return life.read_bound(path, pins[str(path)])
    before = read(BASE / 'combined-bits.json')
    original_manifest = life.read_bound(raw.BASE729 / 'admission-manifest.json', raw.BASE729_SEAL)
    original = life.read_bound(raw.BASE729 / 'combined-bits.json',
                              original_manifest['output_pins'][str(raw.BASE729 / 'combined-bits.json')])
    require(raw.baseline_contract(manifest, read(BASE / 'status.json'), before, original, BASE) == 730,
            'Not exact formal730')
    require((BASE / 'combined-inputs.txt').read_text().splitlines() == [str(raw.DESIGN), *before['tests']],
            'Baseline design/input order differs')
    run = Path(qualification['run']); single = read(CANDIDATE / 'single-bits.json')
    require((CANDIDATE / 'single-inputs.txt').read_text().splitlines() == [str(raw.DESIGN), str(run / 'code.vdb')],
            'Singleton input differs')
    require(life.merge_pins(pins, single['input_hashes']) == pins, 'Singleton raw pins missing')
    after, delta = raw.combine(before, single, run)
    require(after == read(CANDIDATE / 'combined-bits.proposed.json') and
            delta == read(CANDIDATE / 'raw-delta.json') and delta['metrics'] == EXPECTED_DELTA,
            'Exact730 union/delta differs')
    pre = life.read_bound(raw.q.runner.PRE / 'preflight-manifest.json', raw.q.runner.PRE_SEAL)
    raw.target_contract(pre['targets'], before); exact_gain(before, after, pre['targets'])
    hits = read(CANDIDATE / 'target-hits.json')
    require(len(hits) == 4, 'Target population differs')
    for target, hit in zip(pre['targets'], hits):
        require(hit == dict(**target, before_hit=False, single_hit=True, after_hit=True), 'Target evidence differs')
    baselinepins = read(BASE / 'evidence-pins.json')
    elf = Path(pre['input_elf']); elfseal = qualification['pins'][str(elf)]
    require(elfseal not in evidence_elf_hashes(baselinepins), 'Duplicate inherited ELF')
    pins = life.merge_pins(pins, {str(raw.QUAL): QUAL_SEAL,
        str(CANDIDATE / 'diagnostic.json'): CANDIDATE_SEAL, str(BASE / 'admission-manifest.json'): BASE_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_pure_war_offline731.py'),
                 Path(framework.__file__).resolve()):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    outputs = {'combined-bits.json': after, 'single-bits.json': single, 'raw-delta.json': delta,
        'target-hits.json': hits, 'evidence-pins.json': pins,
        'status.json': dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=731,
            baseline=730, new_passed=1, coverage_admitted=True, exact730_prefix=True,
            unique_new_vdb=True, duplicate_elf=False, qualification_seal=QUAL_SEAL,
            candidate_seal=CANDIDATE_SEAL, raw_delta=EXPECTED_DELTA, targets_hit=4,
            full_scalar_isa_verified=True, full_vector_exact_verified=True,
            architectural_qualification_reused=True, source_lifetime_stall_proven=False,
            native_DVE_selector_binding=False, historical_old_image_only=True,
            official_DVE_report=False, singleton_bitmap_recollected=False,
            inherited730_replayed=False, rtl_changed=False, simulations_started=False)}
    return outputs, '\n'.join([str(raw.DESIGN), *after['tests']]) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'admit'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal')
    a = p.parse_args(); out = a.output.absolute(); prepared = out.with_name(out.name + '.prepared.json')
    require(out.parent == life.OUT and out.resolve() == out, 'Independent exact output directory required')
    require((a.mode != 'prepare') == bool(a.seal), 'External prepared seal required')
    require(not out.exists(), 'Fresh formal output required')
    if a.mode == 'prepare': require(not prepared.exists(), 'Fresh prepared receipt required')
    outputs, text = evaluate(BASE_SEAL, QUAL_SEAL, CANDIDATE_SEAL)
    hashes = framework.fingerprints(out, outputs, text)
    proposal = dict(schema='PURE_WAR731_PREPARED_NOT_ADMITTED', output=str(out), baseline=str(BASE),
        baseline_seal=BASE_SEAL, qualification=str(raw.QUAL), qualification_seal=QUAL_SEAL,
        candidate=str(CANDIDATE), candidate_seal=CANDIDATE_SEAL, input_pins=outputs['evidence-pins.json'],
        output_pins=hashes, raw_delta=EXPECTED_DELTA, coverage_admitted=False)
    if a.mode == 'prepare':
        life.save(prepared, proposal); print(json.dumps(dict(prepared=str(prepared), seal=life.digest(prepared)))); return
    require(life.read_bound(prepared, a.seal) == proposal, 'Reviewed proposal differs')
    if a.mode == 'verify': print('VERIFY_PASS EXACT730_PLUS_ONE NO_ADMISSION'); return
    require(not out.exists(), 'Output appeared during verification'); out.mkdir()
    for name, value in outputs.items(): life.save(out / name, value)
    with (out / 'combined-inputs.txt').open('x') as stream: stream.write(text)
    life.check(outputs['evidence-pins.json']); life.check(hashes)
    life.save(out / 'admission-manifest.json', dict(schema=SCHEMA, output=str(out),
        baseline=str(BASE), baseline_seal=BASE_SEAL, qualification=str(raw.QUAL), qualification_seal=QUAL_SEAL,
        candidate=str(CANDIDATE), candidate_seal=CANDIDATE_SEAL, prepared=str(prepared), prepared_seal=a.seal,
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL', output_pins=hashes))
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'admission-manifest.json'))))


if __name__ == '__main__': main()
