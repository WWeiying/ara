"""Formal794 plus qualified61 exact EL; prepare only until parent reviews."""
import argparse
from pathlib import Path
from types import FunctionType

import report_population793_qbs3232 as prior
import soc_constants61_native_v3 as native

engine, stable, life, need = prior.engine, prior.stable, prior.life, prior.need
HERE = Path(__file__).resolve().parent
BASE = life.OUT/'itlb-ppn-aba-offline-admitted794-parent-20261008-01/admission-manifest.json'
BASE_SHA = '02ee7424a6b21d8073097d8a6389be4393d76fc7a3ab31ce410f1c24f70de8cf'
REPORT = life.OUT/'current-population793-qbs3232-parent-20261008-01'
REPORT_CONFIG_SHA = 'b38418835ab071fdd5918f51bc4b7e85e22e4851b4e6478c2c4a75b11d934549'
REPORT_QUAL_SHA = '290d18b35691338479d73b13ce1c2220b6a88830a10bd60b8038cf5cb7607a9b'
LOCAL = life.OUT/'soc-constants61-native-parent-20261008-03'
LOCAL_SHA = '58d4d73db333c8e517122948b95b394a126ebe5020c2aff753483efd48f43902'
LOCAL_QUAL_SHA = '40bd30fd8fafcdb2fb32751d742e01e7f7bc236fa8a8a11634a53a3ffbdee8a3'
FORMAL793_SHA = '757513188f805841491c898584b22722df80facd8f8c9fb424564a82502f17c3'
SCHEMA = 'FORMAL794_QUALIFIED793_COMPLETE_EL_PLUS_SOC61_V1'
physical = prior.physical


def suffix_chain(chain):
    rows = [r for r in chain if r['population'] > 783]
    need([r['population'] for r in rows] == list(range(784,795)), 'Exact784..794 genealogy')
    prior.suffix_chain(rows[:-1])
    need(rows[-2]['seal'] == FORMAL793_SHA and rows[-1]['manifest'] == str(BASE) and
         rows[-1]['seal'] == BASE_SHA, 'Published793/794 authority endpoints')
    return rows


def union_gate(base, addition, config):
    need(len(native.el_gate(addition,config)) == 61, 'Exact61 native typed membership')
    old, extra = stable.semantic(base), stable.semantic(addition)
    occupied, targets = physical(old), physical(extra)
    need(not extra[0] and sum(bin(v).count('1') for v in targets.values()) == 7686, 'Toggle-only7686 addition')
    # A same-scope FSM/Branch waiver does not own its Toggle bits. Whole
    # observers and opaque Toggle declarations do; retain all other metrics.
    opaque = [r for r in old[0] if r[3] == 'WHOLE_SCOPE' or r[3].startswith('Toggle ')]
    for key, mask in targets.items():
        scope, checks, name, prefix, direction = key
        need(not any(scope == r[0] or scope.startswith(r[0]+'.') for r in opaque), 'Opaque scope ownership overlap')
        for previous, value in occupied.items():
            if previous[0] != scope: continue
            need(previous[1] == checks, 'Physical checksum conflict')
            if previous[2:] == (name,prefix,direction): need(not value & mask, 'Already-owned physical directions')
            need(not(name.startswith(previous[2]+'.') or previous[2].startswith(name+'.')), 'Packed ownership overlap')
    text = base.rstrip('\n')+'\n'+addition.rstrip('\n')+'\n'
    combined = stable.semantic(text); expected = dict(occupied)
    for key, mask in targets.items(): expected[key] = expected.get(key,0) | mask
    need(combined[0] == old[0] and physical(combined) == expected, 'Inherited full policy preserved')
    return text


def local_authority(reader):
    c = reader.read(LOCAL/'config.json',LOCAL_SHA,True)
    q = reader.read(LOCAL/'capture-result.json',LOCAL_QUAL_SHA,True)
    need(q['status'] == 'SOC_CONSTANTS61_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED' and
         q['config_seal'] == LOCAL_SHA and (q['fields'],q['directions'],q['protected_objects']) == (61,7686,8951) and
         type(q['terminal_returncode']) is int and q['terminal_returncode'] == 0 and
         q['stages'] == list(native.old.STAGES) and q['population_application'] is False and
         q['initial_X_or_delta_instrumentation_qualified'] is False, 'Actual61 five-stage authority, not X waiver')
    need(native.context()['verify'](LOCAL,LOCAL_SHA) == q, 'Full unchanged61 native verifier')
    pins = stable.merge(c['pins'],q['pins'],{str(LOCAL/'config.json'):LOCAL_SHA,
                                         str(LOCAL/'capture-result.json'):LOCAL_QUAL_SHA})
    blobs = [reader.read(LOCAL/n,pins[str(LOCAL/n)]).decode('ascii') for n in ('first.el','second.el')]
    need(native.el_gate(blobs[0],c) == native.el_gate(blobs[1],c), 'Typed61 semantic reload')
    return c,pins,blobs[1]


def constant_rows(rows, definitions, proof):
    """Use the original typed serializer, never infer bit direction labels."""
    scopes = {r['scope'] for r in proof['candidates']}
    need(set(rows) == scopes, 'Exact61 raw scope membership')
    for scope in scopes:
        row = rows[scope]
        nodes, _ = native.old.source.typed.typed_nodes(definitions[scope]['shape'],row)
        names = {n['name']:n for n in nodes}
        need(len(names) == len(nodes), 'Unique raw typed names')
        for target in [r for r in proof['candidates'] if r['scope'] == scope]:
            expected = target['compiled_attributes']; actual = names.get(target['name'])
            need(row['checksum'] == target['toggle_checksum'] and actual is not None and
                 all(actual.get(k) == v for k,v in expected.items()
                     if k not in ('missing_coordinates','missing_slots')), 'Exact61 source/compiled serialized binding')
            coordinates = list(range(expected['serialized_offset'],expected['serialized_offset']+2*target['width']))
            need(expected['missing_coordinates'] == coordinates and actual['missing_coordinates'] == coordinates,
                 'HOLD61 source constant counterexample')


def historical792(reader,config,proof,source,pins):
    # Native qualification used one representative test, not all792 tests.
    # The independent source review binds the complete published792 OR.
    need(native.old.source.evidence() == proof, 'Full792 source/compiled/OR review replay')
    manifest_path = native.old.source.BASE/'admission-manifest.json'
    manifest = reader.read(manifest_path,native.old.source.BASE_SHA,True)
    need(manifest['coverage_admitted'] is True, 'Published792 historical zero authority')
    authority = stable.merge(manifest['input_pins'],manifest['output_pins'])
    path = native.old.source.BASE/'combined-inputs.txt'
    ledger = reader.read(path,authority[str(path)]).decode('ascii').splitlines()
    need(len(ledger) == len(set(ledger)) == 793 and source['input_ledger'][:793] == ledger and
         config['source_population'] == 792 and config['design'] == ledger[0] and config['vdb'] in ledger[1:],
         'Exact792 full prefix and native sample membership')
    testdata = Path(config['vdb'])/'snps/coverage/db/testdata'/Path(config['test']).name/'tgl.verilog.data.xml'
    need(str(testdata) in config['pins'] and str(testdata) in authority and
         config['pins'][str(testdata)] == authority[str(testdata)], 'Native exact test belongs to admitted792')
    reader.read(testdata,authority[str(testdata)])
    path = native.old.source.BASE/'combined-toggle-bits.json'
    union = reader.read(path,authority[str(path)],True)
    db = Path(ledger[0])/'snps/coverage/db'
    trees = []
    for name in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        path = db/name; reader.read(path,authority[str(path)]); trees.append(prior.suffix.native.xml(path))
    scopes = {r['scope'] for r in proof['candidates']}
    _, definitions = prior.suffix.native.definitions(*trees,scopes)
    constant_rows({s:union[s] for s in scopes},definitions,proof)
    pins.update(stable.merge(proof['input_pins'],reader.pins))
    return dict(population=792,complete_OR_zero=True,directions=7686,
                source_review_sha256=native.old.SOURCE_SHA,native_sample_in_full_ledger=True,
                native_sample_not_claimed_as_full_population=True)


def suffix_zero(reader,pins,chain,config,source):
    rr = reader.read(prior.inherited.prior.LOCAL/'config.json',prior.inherited.prior.LOCAL_SHA,True)
    historical = FunctionType(prior.inherited.prior.suffix_zero.__code__,
        dict(prior.inherited.prior.suffix_zero.__globals__,suffix_chain=suffix_chain))(reader,pins,chain,rr)
    proof = reader.read(native.old.SOURCE,native.old.SOURCE_SHA,True)
    need(config['instances'] == native.old.instances(proof), 'Exact61 complete compiled inventory')
    history = historical792(reader,config,proof,source,pins)
    qbs_c = reader.read(prior.suffix.LOCAL/'config.json',prior.suffix.CONFIG_SHA,True)
    qbs_proof_path = life.OUT/'qbs-bank1-group-hit789-all-cycle-source-review-agent-20261008-01.json'
    qbs_proof = reader.read(qbs_proof_path,qbs_c['plan']['source_review_sha256'],True)
    targets = {r['name']:r for r in qbs_proof['source_targets']}
    need(len(targets) == 72 and sum(len(t['source_zero_bit_indices']) for t in targets.values()) == 1616,
         'Exact QBS partial source targets')
    db = Path(source['input_ledger'][0])/'snps/coverage/db'
    trees = []
    for name in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        path = db/name; reader.read(path,pins[str(path)]); trees.append(prior.suffix.native.xml(path))
    scopes = {r['scope'] for r in proof['candidates']}
    _, definitions = prior.suffix.native.definitions(*trees,scopes | {prior.suffix.SCOPE})
    import xml.etree.ElementTree as ET
    qbs_nodes = list(ET.fromstring(definitions[prior.suffix.SCOPE]['shape']).find('tglshape'))
    parent = next(i for i in qbs_c['instances'] if i['scope'] == prior.suffix.SCOPE)
    need({n.get('name'):dict(n.attrib) for n in qbs_nodes} ==
         {b['attributes']['name']:b['attributes'] for b in parent['bindings']}, 'Full qualified QBS typed inventory')
    audits = []
    for record in suffix_chain(chain)[-2:]:
        paths = list((Path(record['new_vdb'])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(paths) == 1, 'One complete admitted suffix test')
        path = paths[0]; reader.read(path,pins[str(path)])
        rows, sha = prior.suffix.native.rows(path,scopes | {prior.suffix.SCOPE})
        need(sha == pins[str(path)] and set(rows) == scopes | {prior.suffix.SCOPE}, 'Pinned full raw scope set')
        constant_rows({s:rows[s] for s in scopes},definitions,proof)
        qbs_fields = prior.suffix.fields(qbs_nodes,rows[prior.suffix.SCOPE],targets)
        need(not any(f['candidate_raw_hit_coordinates'] for f in qbs_fields), 'HOLD QBS suffix counterexample')
        audits.append(dict(population=record['population'],path=str(path),sha256=sha,
                           SOC61_directions=7686,SOC61_hits=[],QBS3232_hits=[],full_QBS_fields=len(qbs_fields)))
    return dict(SOC61_complete_population792_zero=history,historical_constant_families=historical,new_suffixes=audits)


def approved(reader,manifest,seal):
    need(Path(manifest) == BASE and seal == BASE_SHA, 'Only published exact794')
    source,pins,_,bits,chain,activity = engine.approved(reader,manifest,seal)
    c = reader.read(REPORT/'config.json',REPORT_CONFIG_SHA,True)
    q = reader.read(REPORT/'qualification.json',REPORT_QUAL_SHA,True)
    need(q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         q['config_seal'] == REPORT_CONFIG_SHA and q['population'] == q['actual_selected_tests'] == 793 and
         q['source_design_native_pins'] == c['pins'] and q['new_exclusions_added'] is True and
         q['EL_additions'] == c['EL_additions'] and c['EL_additions']['new_direction_count'] == 3232,
         'Qualified793 complete policy authority')
    for flag in ('complete_approved_EL_bitmask_union','all_other_bits_protected','raw_reset_final_equal',
                 'applied_reloaded_equal','raw_hierarchy_vs_rooted_six_metrics_equal','supported_roots_all_six_metrics_present'):
        need(q[flag] is True, 'Inherited native gate '+flag)
    need(len(source['input_ledger']) == len(set(source['input_ledger'])) == 795 and
         source['input_ledger'][:794] == c['input_ledger'] and bits['tests'] == source['input_ledger'][1:] and
         len(bits['tests']) == 794 and source['hierarchy_roots'] == c['hierarchy_roots'] and
         len(source['hierarchy_roots']) == 72 and source['tool_identity'] == c['tool_identity'], '794 exact prefix/roots/tools/membership')
    suffix_chain(chain)
    pins = stable.merge(pins,c['pins'],q['output_pins'],{str(REPORT/'config.json'):REPORT_CONFIG_SHA,
                                                    str(REPORT/'qualification.json'):REPORT_QUAL_SHA})
    for path,sha in q['output_pins'].items(): reader.read(Path(path),sha)
    base = reader.read(REPORT/'combined.el',pins[str(REPORT/'combined.el')]).decode('ascii')
    need(stable.semantic_seal(stable.semantic(base)) == c['expected_EL_semantic_sha256'], 'Complete793 EL seal')
    for name in ('applied.el','reloaded.el'):
        need(stable.semantic(reader.read(REPORT/name,pins[str(REPORT/name)]).decode('ascii')) == stable.semantic(base), 'Inherited actual reload')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        need(reader.read(REPORT/name,pins[str(REPORT/name)]) == b'', 'Inherited empty state')
    local_c,more,extra = local_authority(reader)
    need(local_c['design'] == source['input_ledger'][0], 'Same frozen image')
    pins = stable.merge(pins,more,reader.pins)
    audit = suffix_zero(reader,pins,chain,local_c,source)
    metadata = dict(new_exclusions_added=True,family='SOC_SOURCE_CONSTANTS61',new_direction_count=7686,
        candidate_objects=61,inherited_complete_EL_sha256=pins[str(REPORT/'combined.el')],
        inherited_report_qualification_sha256=REPORT_QUAL_SHA,native_qualification_sha256=LOCAL_QUAL_SHA,
        exact_physical_disjoint_union=True,inherited_QBS3232_retained_not_readded=True,
        protected_local_objects=8951,initial_X_or_delta_instrumentation_qualified=False)
    activity = dict(activity,EL_additions=metadata,source_constant_suffix_audit=audit,
                    policy='Qualified793 complete EL plus exact61; full794 measured report only')
    return source,stable.merge(pins,reader.pins),union_gate(base,extra,local_c),bits,chain,activity


def dependencies():
    return stable.merge(prior.dependencies(),{str(p):life.digest(p) for p in
        (Path(__file__).resolve(),HERE/'test_report_population794_soc61.py',Path(native.__file__).resolve(),
         Path(native.previous.__file__).resolve(),Path(native.old.__file__).resolve())})


def context():
    prepared,checked,verified,_ = prior.context()
    namespace = dict(prepared.__globals__,__file__=__file__,SCHEMA=SCHEMA,approved=approved,dependencies=dependencies)
    functions = [FunctionType(f.__code__,namespace,f.__name__,f.__defaults__) for f in (prepared,checked,verified)]
    namespace.update(zip(('prepare','check','verify'),functions))
    run = FunctionType(engine.run.__code__,namespace)
    return (*functions,run)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','verify','run-reviewed'))
    p.add_argument('--output',type=Path,required=True); p.add_argument('--seal',required=True)
    p.add_argument('--service-unit'); p.add_argument('--parent-reviewed-seal')
    a = p.parse_args(); functions = context(); out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.service_unit,'Explicit parent owning service required')
        functions[0](out,BASE,a.seal,a.service_unit)
    else:
        need(a.service_unit is None,'Runtime identity from sealed config only')
        if a.mode == 'check': functions[1](out,a.seal); print('FORMAL794_SOC61_CHECK_PASS_NO_EDA')
        elif a.mode == 'verify': functions[2](out,a.seal)
        else: functions[3](out,a.seal,a.parent_reviewed_seal)
