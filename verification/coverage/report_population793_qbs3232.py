"""Prepare/check formal793 plus exact qualified QBS3232; never auto-launch."""
import argparse
import inspect
from pathlib import Path
from types import FunctionType, SimpleNamespace

import audit_qbs_bank1_suffix793 as suffix
import qbs_bank1_group_hit_native791_v2 as local
import report_population791_inherited785 as inherited

engine, stable, life, need = inherited.prior.population, inherited.stable, inherited.life, inherited.need
HERE = Path(__file__).resolve().parent
REPORT = life.OUT/'current-population791-inherited785-parent-20261008-01'
REPORT_CONFIG_SHA = '480f8e9ef4f81caa6ab01c8cc04abb955ef46ad65c6ef3a150eac4a2e3d9b6f4'
REPORT_QUAL_SHA = 'ad675368b58524794a04cc7518374eaf025382e7687f57dd60f2bb9986cba1e3'
SCHEMA = 'FORMAL793_QUALIFIED791_EL_PLUS_EXACT_QBS3232_V1'
physical = inherited.prior.engine.physical


def union_gate(base, addition, config):
    need(len(local.records(addition, config)) == 3232, 'Exact native QBS partial directions')
    old, extra = stable.semantic(base), stable.semantic(addition)
    occupied, targets = physical(old), physical(extra)
    need(not extra[0] and sum(bin(mask).count('1') for mask in targets.values()) == 3232,
         'Toggle-only exact3232 addition')
    for key, mask in targets.items():
        scope, checks, name, prefix, direction = key
        need(not any(scope == row[0] or scope.startswith(row[0]+'.') for row in old[0]),
             'Opaque old ancestor/scope ownership overlap')
        for previous, value in occupied.items():
            if previous[0] != scope: continue
            need(previous[1] == checks, 'Same scope checksum conflict')
            if previous[2:] == (name,prefix,direction): need(not value & mask, 'Already owned physical directions')
            need(not(name.startswith(previous[2]+'.') or previous[2].startswith(name+'.')),
                 'Packed parent/child ownership conflict')
    text = base.rstrip('\n')+'\n'+addition.rstrip('\n')+'\n'
    combined = stable.semantic(text); expected = dict(occupied)
    for key, mask in targets.items(): expected[key] = expected.get(key,0) | mask
    need(combined[0] == old[0] and physical(combined) == expected,
         'All inherited metrics and physical masks preserved')
    return text


def suffix_chain(chain):
    rows = [row for row in chain if row['population'] > 783]
    need([row['population'] for row in rows] == list(range(784,794)), 'Exact784..793 suffix genealogy')
    need(rows[-3]['manifest'] == str(inherited.BASE) and rows[-3]['seal'] == inherited.BASE_SHA and
         rows[-2]['manifest'] == str(suffix.BASE/'admission-manifest.json') and rows[-2]['seal'] == suffix.BASE_SHA and
         rows[-1]['manifest'] == str(suffix.NEXT/'admission-manifest.json'), 'Exact791/792/793 ancestry')
    return rows


def approved(reader, manifest, seal):
    need(Path(manifest) == suffix.NEXT/'admission-manifest.json', 'Only explicit published formal793')
    source, pins, _, bits, chain, activity = engine.approved(reader, manifest, seal)
    old = reader.read(REPORT/'config.json', REPORT_CONFIG_SHA, True)
    q = reader.read(REPORT/'qualification.json', REPORT_QUAL_SHA, True)
    need(q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         q['config_seal'] == REPORT_CONFIG_SHA and q['population'] == q['actual_selected_tests'] == 791 and
         q['source_design_native_pins'] == old['pins'], 'Actual qualified791 authority')
    for flag in ('complete_approved_EL_bitmask_union','all_other_bits_protected','raw_reset_final_equal',
                 'applied_reloaded_equal','raw_hierarchy_vs_rooted_six_metrics_equal','supported_roots_all_six_metrics_present'):
        need(q[flag] is True, 'Inherited native gate: '+flag)
    need(len(source['input_ledger']) == len(set(source['input_ledger'])) == 794 and
         source['input_ledger'][:792] == old['input_ledger'] and bits['tests'] == source['input_ledger'][1:] and
         len(bits['tests']) == 793 and source['hierarchy_roots'] == old['hierarchy_roots'] and
         len(source['hierarchy_roots']) == 72 and source['tool_identity'] == old['tool_identity'],
         'Full793 exact791 prefix/test membership/root/tool identity')
    suffix_chain(chain)
    pins = stable.merge(pins, old['pins'], q['output_pins'],
        {str(REPORT/'config.json'):REPORT_CONFIG_SHA,str(REPORT/'qualification.json'):REPORT_QUAL_SHA})
    base = reader.read(REPORT/'combined.el', pins[str(REPORT/'combined.el')]).decode('ascii')
    need(stable.semantic_seal(stable.semantic(base)) == old['expected_EL_semantic_sha256'], 'Qualified791 complete EL')
    for name in ('applied.el','reloaded.el'):
        text = reader.read(REPORT/name, pins[str(REPORT/name)]).decode('ascii')
        need(stable.semantic(text) == stable.semantic(base), 'Inherited actual reload union')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        need(reader.read(REPORT/name,pins[str(REPORT/name)]) == b'', 'Inherited empty reset/final')
    # Recheck every added sample against the three post777 constant families,
    # rather than assuming the latest program cannot drive them.
    rr = reader.read(inherited.prior.LOCAL/'config.json', inherited.prior.LOCAL_SHA, True)
    audit_old = FunctionType(inherited.prior.suffix_zero.__code__,
        dict(inherited.prior.suffix_zero.__globals__, suffix_chain=suffix_chain))(reader,pins,chain,rr)
    local_q = reader.read(suffix.LOCAL/'qualification.json', suffix.LOCAL_SHA, True)
    local_c = reader.read(suffix.LOCAL/'config.json', suffix.CONFIG_SHA, True)
    need(local_q['status'] == 'QBS_BANK1_GROUP_HIT3232_V2_NATIVE_QUALIFIED_NOT_APPLIED' and
         local_q['config_sha256'] == suffix.CONFIG_SHA and local_q['target_directions'] == 3232 and
         local_q['complete_native_objects_per_stage'] == 6707 and local_q['complete_native_scopes_per_stage'] == 26 and
         local_q['mapping_permitted_missing704_protected'] is True and local_q['population_application'] is False,
         'Reviewed exact local QBS qualification')
    pins = stable.merge(pins,local_q['input_pins'],local_q['pins'],
        {str(suffix.LOCAL/'qualification.json'):suffix.LOCAL_SHA,str(suffix.LOCAL/'config.json'):suffix.CONFIG_SHA})
    addition = reader.read(suffix.LOCAL/'first.el', pins[str(suffix.LOCAL/'first.el')]).decode('ascii')
    reloaded = reader.read(suffix.LOCAL/'second.el', pins[str(suffix.LOCAL/'second.el')]).decode('ascii')
    need(local.records(addition,local_c) == local.records(reloaded,local_c), 'Local actual semantic reload')
    audit = suffix.collect(seal)
    need(audit['suffix_candidate_zero'] is True, '793 source-zero counterexample HOLD')
    # The separately completed792 audit is preserved, not overwritten.
    audit792_path = life.OUT/'qbs-bank1-group-hit792-suffix-static-agent-20261008-01.json'
    audit792 = reader.read(audit792_path,'99d1250705639195b855b44fe29f2310c3712a34e1eebb87c39d63082b113169',True)
    need(audit792['suffix792_candidate_hit_coordinates'] == [], '792 source-zero counterexample')
    pins = stable.merge(pins,audit['input_pins'],audit792['input_pins'],reader.pins)
    metadata = dict(new_exclusions_added=True, family='QBS_BANK1_GROUP_HIT_PARTIAL', new_direction_count=3232,
        inherited_complete_EL_sha256=pins[str(REPORT/'combined.el')], inherited_report_qualification_sha256=REPORT_QUAL_SHA,
        native_qualification_sha256=suffix.LOCAL_SHA, exact_physical_disjoint_union=True,
        candidate_objects=72, mapping_permitted_missing704_protected=True, HOOKE61_included=False)
    activity = dict(activity, inherited791_constants=audit_old, QBS793_source_zero=dict(
        sample=audit['sample'], input_pins=audit['input_pins'], candidate_directions=3232, hits=[]),
        EL_additions=metadata, policy='Qualified791 complete EL plus exact native QBS3232, full793 data; no percentage extrapolation')
    return source,pins,union_gate(base,addition,local_c),bits,chain,activity


def dependencies():
    return stable.merge(inherited.dependencies(),engine.dependencies(),{
        str(path):life.digest(path) for path in (Path(__file__).resolve(),HERE/'test_report_population793_qbs3232.py',
            Path(suffix.__file__).resolve(),HERE/'test_audit_qbs_bank1_suffix793.py',Path(local.__file__).resolve())})


def context():
    # A single private consumer of the unchanged global engine. Explicitly
    # correct its old no-new-EL metadata and keep its native report gates intact.
    namespace = dict(engine.prepare.__globals__, __file__=__file__, SCHEMA=SCHEMA,
        approved=approved, dependencies=dependencies,
        stable=SimpleNamespace(**dict(vars(stable), Reader=inherited.Reader)))
    replacements = {
        'prepare': [('new_exclusions_added=False,', "new_exclusions_added=True,EL_additions=activity['EL_additions'],")],
        'check': [("config['new_exclusions_added'] is False", "config['new_exclusions_added'] is True and config['EL_additions']==activity['EL_additions']")],
        'verify': [('historical_PASS_only_no_new_RTL_signoff=True)', "historical_PASS_only_no_new_RTL_signoff=True,new_exclusions_added=config['new_exclusions_added'],EL_additions=config['EL_additions'])")],
    }
    for name in ('prepare','check','verify'):
        text = inspect.getsource(getattr(engine,name))
        for anchor,replacement in replacements[name]:
            need(text.count(anchor) == 1, 'Exact unchanged engine metadata anchor '+name)
            text = text.replace(anchor,replacement)
        exec(compile(text,__file__+':private-'+name,'exec'),namespace)
    run = FunctionType(engine.run.__code__, dict(namespace,
        check=namespace['check'], verify=namespace['verify']))
    return namespace['prepare'],namespace['check'],namespace['verify'],run


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=('prepare','check','verify','run-reviewed'))
    cli.add_argument('--output', type=Path, required=True); cli.add_argument('--seal',required=True)
    cli.add_argument('--service-unit')
    cli.add_argument('--parent-reviewed-seal')
    a = cli.parse_args(); functions = context(); out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.service_unit, 'Explicit future owning service, no automatic launch')
        functions[0](out,suffix.NEXT/'admission-manifest.json',a.seal,a.service_unit)
    else:
        need(a.service_unit is None, 'Runtime service identity comes from sealed config')
        if a.mode == 'check': functions[1](out,a.seal); print('FORMAL793_QBS3232_CHECK_PASS_NO_EDA')
        elif a.mode == 'verify': functions[2](out,a.seal)
        else: functions[3](out,a.seal,a.parent_reviewed_seal)
