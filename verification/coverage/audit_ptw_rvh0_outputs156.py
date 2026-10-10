"""Separate typed EL qualification from native flag observability; never infer flags from Display."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import ptw_rvh0_outputs156_local as original
import ptw_rvh0_outputs156_local_v2 as successor

life, need = original.life, original.need


def affirmative(instance, rows):
    expected = [dict(stage=s, scope=instance['scope'], label=label,
                     excluded='1' if s in ('applied','reloaded') else '0')
                for s in original.STAGES for label in original.labels(instance)]
    need(rows == expected, 'Exact observed native excluded flags required; no no-op/duplicate/foreign rows')


def stages_gate(instance, stages):
    need(set(stages) == set(original.STAGES), 'All five actual inventories required')
    before = stages['before']
    for label in original.labels(instance):
        need(before[label]['coverage'] == '0.00%', 'Measured source-constant before coverage')
    for stage in original.STAGES:
        fn = original.soc.stage_gate
        FunctionType(fn.__code__, dict(fn.__globals__, labels=original.labels))(instance, before, stages[stage], stage)
    return dict(native_flag_observation='UNOBSERVED', display_is_flag=False,
                reason='SOC capture has no flags.tsv; empty Display and 0.00% cannot distinguish exclusion from no-op')


def original_readonly_verify(out, seal):
    captured = []
    def save(path, value):
        need(path == out/'capture-result.json' and not captured,
             'No foreign write in read-only predecessor verification')
        captured.append(value)
    proxy = SimpleNamespace(**dict(vars(life), save=save))
    cpath=out/'config.json'
    if cpath.exists() and json.loads(cpath.read_bytes()).get('schema') == successor.SCHEMA:
        env=successor.context();env['check']=successor.check
        fn=env['verify']
    else:
        fn=original.verify
    result = FunctionType(fn.__code__, dict(fn.__globals__, life=proxy))(out, seal)
    need(not captured or captured == [result], 'Exact intercepted original result')
    return result


def suffix_zero(population, seal, proof):
    m = life.read_bound(population/'admission-manifest.json', seal)
    need(m['coverage_admitted'] is True, 'Only formally admitted suffix population')
    authority = life.merge_pins(m['input_pins'], m['output_pins'])
    files = ['combined-inputs.txt', 'combined-toggle-bits.json']
    pins = {str(population/'admission-manifest.json'): seal}
    for name in files:
        p = population/name
        need(str(p) in authority and life.digest(p) == authority[str(p)], 'Bound actual suffix input')
        pins[str(p)] = authority[str(p)]
    baseline = life.read_bound(original.BASE/'admission-manifest.json', original.BASE_SHA)
    p = original.BASE/'combined-inputs.txt'
    need(life.digest(p) == baseline['output_pins'][str(p)], 'Frozen794 prefix')
    pins[str(p)] = baseline['output_pins'][str(p)]
    old = p.read_text().splitlines()
    ledger = (population/'combined-inputs.txt').read_text().splitlines()
    need(len(old) == 795 and len(ledger) == len(set(ledger)) and ledger[:len(old)] == old,
         'Exact794 prefix; unique latest membership')
    row = json.loads((population/'combined-toggle-bits.json').read_bytes())[original.SCOPE]
    need((row['checksum'], row['width']) == ('313685876', 3274), 'Same compiled PTW image')
    db = Path(str(life.IMAGE)+'.vdb')/'snps/coverage/db'
    p = db/'shape/tgl.verilog.shape.xml'
    need(life.digest(p) == proof['pins'][str(p)], 'Exact frozen compiled shape')
    pins[str(p)] = proof['pins'][str(p)]
    defs = [d for d in original.soc.source.t.xml(p).findall('tgldef')
            if d.get('chksum') == '313685876' and d.get('name').split(' (')[0] == 'cva6_ptw']
    need(len(defs) == 1, 'Unique PTW definition')
    nodes = original.soc.source.typed.typed_nodes(original.ET.tostring(defs[0], encoding='unicode'), row)[0]
    by = {n['name']: n for n in nodes}
    for s in proof['instance']['signals']:
        n = by[s['name']]
        need(n['missing_coordinates'] == s['missing_coordinates']
             and n['missing_slots'] == 2*original.WIDTHS[s['name']], 'Suffix remains source constant zero')
    life.check(pins)
    return dict(tests=len(ledger)-1, prefix794_exact=True, missing_serialized_positions=156, pins=pins)


def audit(out, seal, population, population_seal, destination):
    need(destination.parent == life.OUT and not destination.exists(), 'Fresh independent audit directory')
    result = original_readonly_verify(out, seal)
    c = life.read_bound(out/'config.json', seal)
    stages = {s: original.bind(c['instances'][0], (out/('native_%s_0.tsv'%s)).read_text())
              for s in original.STAGES}
    proof = json.loads((out/'source-proof.json').read_bytes())
    suffix = suffix_zero(population, population_seal, proof)
    pins = life.merge_pins(result['pins'], suffix['pins'])
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_audit_ptw_rvh0_outputs156.py')):
        pins[str(p)] = life.digest(p)
    observation = stages_gate(c['instances'][0], stages)
    status = 'PTW156_TYPED_LOCAL_ROUNDTRIP_VERIFIED_FLAGS_UNOBSERVED_GLOBAL_NATIVE_AUDIT_REQUIRED'
    issue = None
    receipt = dict(status=status, issue=issue, original_run=str(out), original_config_seal=seal,
                   fields=12, directions=156, protected_objects=137, suffix_audit=suffix,
                   native_flag_observation=observation,
                   blank_native_display_is_excluded=False, synthetic_test_is_native_calibration=False,
                   global_application=False, EDA_started=False, pins=pins)
    life.check(pins)
    destination.mkdir()
    life.save(destination/'audit.json', receipt)
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True); p.add_argument('--seal', required=True)
    p.add_argument('--population', type=Path, required=True); p.add_argument('--population-seal', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    q = audit(a.run.resolve(), a.seal, a.population.resolve(), a.population_seal, a.output.resolve())
    print(json.dumps(dict(status=q['status'], issue=q['issue'], output=str(a.output))))
    if q['issue'] is not None: raise SystemExit(1)
