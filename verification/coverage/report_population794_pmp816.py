"""Independent full794 five-stage report: complete qualified policy plus PMP816."""
import argparse
from pathlib import Path
from types import FunctionType

import prepare_pmp816_global_union as handoff

prior = handoff.global794
engine, stable, life, need = prior.engine, prior.stable, prior.life, prior.need
HERE = Path(__file__).resolve().parent
SCHEMA = 'FORMAL794_COMPLETE_QUALIFIED_POLICY_PLUS_PMP816_V1'


def handoff_gate(q):
    need(q['status'] == 'PMP816_EXACT794_UNION_HANDOFF_PREPARED_NOT_POPULATION_APPLIED' and
         q['population'] == 794 and q['global_qualification_sha256'] == handoff.GLOBAL_SHA and
         q['local_qualification_sha256'] == handoff.LOCAL_SHA and
         (q['fields'], q['directions'], q['source_MDA_HOLD']) == (816, 2176, 13),
         'Exact sealed794/PMP816 handoff authority')
    for flag in ('exact_physical_disjoint', 'inherited_EL_bytes_preserved'):
        need(q[flag] is True, 'Handoff gate ' + flag)
    for flag in ('EDA_started', 'population_application', 'initial_X_qualified'):
        need(q[flag] is False, 'No premature population/X qualification')


def approved_for(path, seal):
    def approved(reader, manifest, admission_seal):
        need(Path(manifest) == prior.BASE and admission_seal == prior.BASE_SHA,
             'Only published formal794; no relabelled population')
        source, pins, _, bits, chain, activity = engine.approved(reader, manifest, admission_seal)
        q = reader.read(path, seal, True)
        handoff_gate(q)
        c = reader.read(handoff.GLOBAL/'config.json', handoff.GLOBAL_CONFIG_SHA, True)
        g = reader.read(handoff.GLOBAL/'qualification.json', handoff.GLOBAL_SHA, True)
        handoff.global_gate(g, c)
        need(source['input_ledger'] == c['input_ledger'] and len(bits['tests']) == 794 and
             bits['tests'] == source['input_ledger'][1:] and
             source['hierarchy_roots'] == c['hierarchy_roots'] and len(c['hierarchy_roots']) == 72 and
             source['tool_identity'] == c['tool_identity'], 'Exact full794 ledger/root/tool contract')
        pins = stable.merge(pins, q['input_pins'], q['output_pins'], reader.pins)
        base_path = handoff.GLOBAL/'combined.el'
        authority = stable.merge(c['pins'], g['output_pins'])
        need(q['global_combined_EL_sha256'] == authority[str(base_path)], 'Inherited full EL authority')
        base = reader.read(base_path, q['global_combined_EL_sha256']).decode('ascii')
        local_q = reader.read(handoff.LOCAL/'capture-result.json', handoff.LOCAL_SHA, True)
        local_c = reader.read(handoff.LOCAL/'config.json', local_q['config_seal'], True)
        obligations = stable.merge(c['pins'], g['output_pins'], local_c['pins'], local_q['pins'],
            {str(handoff.GLOBAL/'config.json'): handoff.GLOBAL_CONFIG_SHA,
             str(handoff.GLOBAL/'qualification.json'): handoff.GLOBAL_SHA,
             str(handoff.LOCAL/'config.json'): local_q['config_seal'],
             str(handoff.LOCAL/'capture-result.json'): handoff.LOCAL_SHA})
        need(all(q['input_pins'].get(p) == h for p, h in obligations.items()),
             'Handoff retains every inherited/source/native protection pin')
        extra_path = handoff.LOCAL/'second.el'
        extra = reader.read(extra_path, q['input_pins'][str(extra_path)]).decode('ascii')
        union_path = path.parent/'candidate-union.el'
        need(set(q['output_pins']) == {str(union_path)}, 'Only exact handoff EL output')
        text = reader.read(union_path, q['output_pins'][str(union_path)]).decode('ascii')
        need(text == handoff.union_gate(base, extra, local_c) and
             stable.semantic_seal(stable.semantic(text)) == q['union_semantic_sha256'],
             'Exact inherited EL plus disjoint typed PMP union')
        metadata = dict(family='PMP_SOURCE_CONSTANTS816', new_direction_count=2176,
            candidate_objects=816, protected_local_objects=4509, source_MDA_HOLD=13,
            handoff_path=str(path), handoff_seal=seal,
            inherited_report_qualification_sha256=handoff.GLOBAL_SHA,
            inherited_complete_EL_sha256=q['global_combined_EL_sha256'],
            native_qualification_sha256=handoff.LOCAL_SHA, exact_physical_disjoint_union=True,
            inherited_all_families_retained_not_readded=True,
            initial_X_or_delta_instrumentation_qualified=False)
        activity = dict(activity, EL_additions=metadata,
            policy='Full794 actual five-stage report; complete inherited policy plus exact PMP816')
        return source, stable.merge(pins, reader.pins), text, bits, chain, activity
    return approved


def dependencies():
    return stable.merge(prior.dependencies(), {str(p): life.digest(p) for p in
        (Path(__file__).resolve(), HERE/'test_report_population794_pmp816.py',
         Path(handoff.__file__).resolve(), HERE/'test_prepare_pmp816_global_union.py',
         Path(handoff.local.__file__).resolve(), Path(handoff.local.proof.__file__).resolve())})


def context(path, seal):
    path = Path(path).resolve()
    need(path.name == 'handoff.json' and path.parent.parent == life.OUT and
         len(seal) == 64 and all(x in '0123456789abcdef' for x in seal), 'Explicit sealed handoff path/SHA')
    prepared, checked, verified, _ = prior.context()
    namespace = dict(prepared.__globals__, __file__=__file__, SCHEMA=SCHEMA,
                     approved=approved_for(path, seal), dependencies=dependencies)
    functions = [FunctionType(f.__code__, namespace, f.__name__, f.__defaults__)
                 for f in (prepared, checked, verified)]
    namespace.update(zip(('prepare', 'check', 'verify'), functions))
    return (*functions, FunctionType(engine.run.__code__, namespace))


def runtime_context(out, seal):
    c = life.read_bound(out/'config.json', seal)
    need(c['schema'] == SCHEMA and c['successor_entry'] == str(Path(__file__).resolve()) and
         c['output'] == str(out), 'Exact sealed report runtime identity')
    m = c['EL_additions']
    entry = str(Path(__file__).resolve())
    need(c['pins'].get(entry) == life.digest(entry) and
         c['pins'].get(m['handoff_path']) == m['handoff_seal'],
         'Sealed runtime entry and handoff dependency binding')
    return context(m['handoff_path'], m['handoff_seal'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'verify', 'run-reviewed'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal', required=True)
    p.add_argument('--handoff', type=Path); p.add_argument('--handoff-seal')
    p.add_argument('--service-unit'); p.add_argument('--parent-reviewed-seal')
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.handoff is not None and a.handoff_seal is not None and a.service_unit is not None,
             'Explicit handoff and owning service required')
        context(a.handoff, a.handoff_seal)[0](out, prior.BASE, a.seal, a.service_unit)
    else:
        need(a.handoff is None and a.handoff_seal is None and a.service_unit is None,
             'Runtime uses sealed identity only')
        f = runtime_context(out, a.seal)
        if a.mode == 'check': f[1](out, a.seal); print('FULL794_PMP816_CHECK_PASS_NO_EDA')
        elif a.mode == 'verify': f[2](out, a.seal)
        else: f[3](out, a.seal, a.parent_reviewed_seal)
