"""Full797 five-stage report with exactly qualified796 EL; no new waivers."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace
import xml.etree.ElementTree as ET

import report_population796_alua_ptw as inherited
import admit_vsmul_saturation797 as admission

engine, stable, life, need = inherited.engine, inherited.stable, inherited.life, inherited.need
HERE = Path(__file__).resolve().parent
BASE = life.OUT / 'vsmul-saturation-offline-admitted797-parent-20261008-01/admission-manifest.json'
BASE_SHA = '775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4'
REPORT = life.OUT / 'current-population796-alua137-ptw156-agent-20261008-01'
CONFIG_SHA = '062daf585d00ef170942b36f5a631dee7f4676af32fcbb4e5d8af86a8159badf'
QUAL_SHA = 'f439bae9092c0a787ee8fb8177ee33277e6ec25f61ef0c198f5a8dce50807270'
SCHEMA = 'FORMAL797_EXACT_QUALIFIED796_EL_FULL_SUFFIX_ZERO_V1'


def report_gate(config, q):
    need(config['schema'] == inherited.SCHEMA and config['admission'] ==
         dict(path=str(inherited.BASE), sha256=inherited.BASE_SHA)
         and config['population'] == 796 and q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED'
         and q['config_seal'] == CONFIG_SHA and q['admission_seal'] == inherited.BASE_SHA
         and q['population'] == q['actual_selected_tests'] == 796
         and q['source_design_native_pins'] == config['pins']
         and q['EL_additions'] == config['EL_additions']
         and q['new_exclusions_added'] is True, 'Exact qualified796 complete authority')
    for key in ('complete_approved_EL_bitmask_union', 'all_other_bits_protected', 'raw_reset_final_equal',
                'applied_reloaded_equal', 'raw_hierarchy_vs_rooted_six_metrics_equal',
                'supported_roots_all_six_metrics_present', 'historical_PASS_only_no_new_RTL_signoff'):
        need(q[key] is True, 'Inherited796 global gate: ' + key)
    need(len(config['hierarchy_roots']) == 72 and config['full_OR_metric_instances'] == 6162
         and config['raw_hierarchy_rows'] == 2989, 'Unchanged full-scope contract')


def corpus_gate(source, bits, chain, previous):
    ledger = source['input_ledger']
    need(len(ledger) == len(set(ledger)) == 798 and ledger[:-1] == previous['input_ledger']
         and len(previous['input_ledger']) == 797 and bits['tests'] == ledger[1:]
         and ledger[-1] == str(admission.RUN / 'code.vdb'), 'Exact796 prefix/unique797 native suffix')
    need(chain[:-1] == previous['genealogy'] and chain[-1] ==
         dict(population=797, manifest=str(BASE), seal=BASE_SHA, new_vdb=ledger[-1]), 'Exact797 genealogy')
    need({k:len(v) for k,v in bits['metrics'].items()} == engine.METRIC_COUNTS,
         'Complete6162 metric families')
    need(source['hierarchy_roots'] == previous['hierarchy_roots'] and len(source['hierarchy_roots']) == 72
         and source['tool_identity'] == previous['tool_identity'], 'Unchanged roots/tools')


def inherited_el(reader, config, q, pins):
    blobs = [reader.read(REPORT / name, pins[str(REPORT / name)]).decode('ascii')
             for name in ('combined.el', 'applied.el', 'reloaded.el')]
    for text in blobs:
        need(stable.semantic_seal(stable.semantic(text)) == config['expected_EL_semantic_sha256'],
             'Exact complete inherited796 EL; no new waiver')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
        need(reader.read(REPORT / name, pins[str(REPORT / name)]) == b'', 'Inherited796 empty phase')
    reports = {}
    for stage in stable.STAGES:
        ep = REPORT / stable.EL_FILES[stage]
        stable.el_gate(reader.read(ep, pins[str(ep)]), stage, config['expected_EL_semantic_sha256'])
        path = REPORT / ('modules_' + stage + '.csv')
        reports[stage] = stable.summary(reader.read(path, pins[str(path)]), stage, config['hierarchy_roots'])
    admission.exact(reports, q['module_reports'], 'All796 five-stage module reports')
    stable.summaries_gate(reports)
    stable.raw_summary_gate(reader.read(REPORT / 'raw.csv', pins[str(REPORT / 'raw.csv')]),
                            config['hierarchy_roots'], reports['raw'])
    selected = reader.read(REPORT / 'selected_tests.txt', pins[str(REPORT / 'selected_tests.txt')]).decode().splitlines()
    stable.membership(config['input_ledger'], selected, 796)
    need(selected == config['expected_selected'], 'Actual796 selected test order')
    return blobs[0]


def full_source_zero(reader, source, pins, bits, toggle):
    native = engine.stable.cvx.base.proof.typed
    db = Path(source['input_ledger'][0]) / 'snps/coverage/db'
    trees = []
    for name in ('design/verilog.design.xml', 'shape/tgl.verilog.info.xml', 'shape/tgl.verilog.shape.xml'):
        path = db / name
        reader.read(path, pins[str(path)])
        trees.append(native.xml(path))
    cvx = engine.stable.cvx.base.proof
    proof = reader.read(engine.stable.PROOF, engine.stable.PROOF_SHA, True)
    checks, definitions = native.definitions(*trees, cvx.SCOPES)
    for target in proof['targets']:
        scope = target['scope']
        _, _, width = cvx.bind_scope(scope, ET.fromstring(definitions[scope]['shape']),
                                    checks[scope], definitions[scope]['module']['chksum'])
        engine.zero_row(toggle[scope], width, checks[scope], target['raw_positions'])
    ms = engine.stable.inherited.predecessor.strict.qualification.source.SCOPE
    mask = source['masku_raw776']
    engine.zero_row(toggle[ms], mask['union']['width'], mask['union']['checksum'], mask['positions'])
    branches = [r for r in source['branch720']['branch_inventory'] if r['target']]
    need(len(branches) == 720 and len(mask['positions']) == 512, 'Complete original source-zero families')
    for target in branches:
        row = bits['metrics']['branch'][target['scope']]
        engine.zero_row(row, row['width'], row['checksum'], [target['raw_index']])
    older = inherited.old.older
    rr_config = reader.read(older.LOCAL / 'config.json', older.LOCAL_SHA, True)
    rr = reader.read(older.native.SOURCE, older.native.SOURCE_SHA, True)
    older.native.source_gate(rr)
    cls = older.previous
    class_config = reader.read(cls.LOCAL / 'config.json', cls.LOCAL_CONFIG_SHA, True)
    class_proof = reader.read(cls.native.SOURCE, cls.native.SOURCE_SHA, True)
    fp_config = reader.read(cls.previous.LOCAL / 'config.json', cls.previous.LOCAL_CONFIG_SHA, True)
    fp = cls.previous.native
    fp_proof = reader.read(fp.SOURCE, fp.SOURCE_SHA, True)
    families = [('RR190', older.target_groups(rr, rr_config, 'missing_coordinates')),
                ('CLASS_PADDING', older.target_groups(class_proof, class_config, 'raw_coordinates')),
                ('FPNEW90', older.target_groups(fp_proof, fp_config, 'coordinates'))]
    scopes = {scope for _, groups in families for scope in groups}
    older.suffix_rows({s:toggle[s] for s in scopes}, families)
    return dict(population=797, CVXIF_zero_directions=18516, MASKU_zero_directions=512,
                parameter_false_branches=720, RR190_zero=True, class_padding_zero=True, FPNEW90_zero=True)


def approved(reader, manifest, seal):
    need(Path(manifest) == BASE and seal == BASE_SHA, 'Only actual admitted797')
    previous = reader.read(REPORT / 'config.json', CONFIG_SHA, True)
    q = reader.read(REPORT / 'qualification.json', QUAL_SHA, True)
    report_gate(previous, q)
    base = reader.read(BASE, BASE_SHA, True)
    need(base['coverage_admitted'] is True and base['output'] == str(BASE.parent)
         and base['baseline'] == str(inherited.BASE.parent) and base['baseline_seal'] == inherited.BASE_SHA,
         'Exact admitted796->797 authority')
    pins = stable.merge(previous['pins'], q['output_pins'], base['input_pins'], base['output_pins'],
        {str(BASE):BASE_SHA, str(REPORT / 'config.json'):CONFIG_SHA, str(REPORT / 'qualification.json'):QUAL_SHA})
    def doc(directory, name):
        path = directory / name
        return reader.read(path, pins[str(path)], True)
    oldbase = reader.read(inherited.BASE, inherited.BASE_SHA, True)
    need(oldbase['coverage_admitted'] is True, 'Formal796 prefix authority')
    pins = stable.merge(pins, oldbase['input_pins'], oldbase['output_pins'], {str(inherited.BASE):inherited.BASE_SHA})
    before = doc(inherited.BASE.parent, 'combined-bits.json')
    bits = doc(BASE.parent, 'combined-bits.json')
    single = doc(BASE.parent, 'single-bits.json')
    ledger = reader.read(BASE.parent / 'combined-inputs.txt', pins[str(BASE.parent / 'combined-inputs.txt')]).decode().splitlines()
    oldledger = reader.read(inherited.BASE.parent / 'combined-inputs.txt', pins[str(inherited.BASE.parent / 'combined-inputs.txt')]).decode().splitlines()
    need(oldledger == previous['input_ledger'] and before['tests'] == oldledger[1:], 'Qualified796 exact admitted ledger')
    engine.population_gate(before, bits, single, oldledger, ledger)
    admission.c.exact_raw_union(before, single, bits, population=796)
    admission.exact(single, admission.r.bitmap.collect(admission.QUAL / 'single-inputs.txt'), 'Actual797 native6162 singleton')
    status = doc(BASE.parent, 'status.json')
    need(status['coverage_admitted'] is True and type(status['aggregate_passed']) is int
         and status['aggregate_passed'] == 797 and status['full_OR_metric_instances'] == 6162
         and status['full_OR_Toggle_instances'] == 2989, 'Formal797 full status')
    bt = doc(inherited.BASE.parent, 'combined-toggle-bits.json')
    toggle = doc(BASE.parent, 'combined-toggle-bits.json')
    path = admission.RUN / 'code.vdb/snps/coverage/db/testdata' / admission.r.NAME / 'tgl.verilog.data.xml'
    reader.read(path, pins[str(path)])
    sample, sha = admission.r.toggle.rows(path, list(bt))
    need(sha == pins[str(path)], 'Actual797 native2989 Toggle SHA')
    admission.toggle_or(bt, sample, toggle)
    identity = admission.c.coverage_identity(path.parent, admission.RUN,
        reader.read(admission.RUN / 'manifest.json', pins[str(admission.RUN / 'manifest.json')], True), Path(ledger[0]))
    need(all(pins.get(p) == h for p,h in identity.items()), 'Native797 compile/command/cwd/five metrics')
    text = inherited_el(reader, previous, q, pins)
    # Reuse the closed source books once; the qualified796 pins already retain
    # historical genealogy and policy proofs, so only the new suffix is replayed.
    source, more, _, _ = engine.stable.approved(reader)
    pins = stable.merge(pins, more, reader.pins)
    source = dict(source, input_ledger=ledger, expected_selected=engine.selected_tests(ledger))
    chain = previous['genealogy'] + [dict(population=797, manifest=str(BASE), seal=BASE_SHA, new_vdb=ledger[-1])]
    corpus_gate(source, bits, chain, previous)
    activity = engine.suffix_activity(reader, source, pins, [chain[-1]], before)
    prior = SimpleNamespace(**dict(vars(inherited.old.prior), BASE=inherited.BASE, BASE_SHA=inherited.BASE_SHA))
    zero = FunctionType(inherited.old.suffix_zero.__code__, dict(inherited.old.suffix_zero.__globals__,
        BASE=BASE, BASE_SHA=BASE_SHA, prior=prior))
    constant_audit = dict(zero(reader, pins, chain[-1], source), population=797)
    full = full_source_zero(reader, source, pins, bits, toggle)
    ac, pc, packet, blobs, localpins = inherited.qualification(reader)
    pins = stable.merge(pins, localpins)
    inherited795 = reader.read(inherited.REPORT / 'combined.el', pins[str(inherited.REPORT / 'combined.el')]).decode('ascii')
    need(stable.semantic(inherited.union_gate(inherited795, *blobs)) == stable.semantic(text),
         'Complete796 inherited EL family closure; no new exclusion')
    design = inherited.alua.source.Design(Path(ledger[0]))
    alua_ptw = [inherited.added_zero(b, t, ac, pc, packet, design) for b,t in ((single, sample), (bits, toggle))]
    activity = dict(activity, VSMUL797_constant_suffix_and_full_audit=constant_audit,
        full797_original_source_zero=full, ALUA_PTW_suffix_and_full797_zero=alua_ptw,
        inherited796_qualification=QUAL_SHA, inherited796_EL_sha256=pins[str(REPORT / 'combined.el')],
        inherited796_EL_additions=previous['EL_additions'], inherited796_suffix_activity=previous['suffix_activity'],
        new_exclusions_added=False, all_history_pins_retained=True, complete_Toggle_OR_instances=2989,
        policy='Exact qualified796 EL; full797 five stages required; trusted active IP not reclassified unreachable')
    return source, stable.merge(pins, reader.pins), text, bits, chain, activity


def dependencies():
    return stable.merge(inherited.dependencies(), {str(p):life.digest(p) for p in
        (Path(__file__).resolve(), HERE / 'test_report_population797_inherited796.py',
         Path(admission.__file__).resolve(), HERE / 'test_admit_vsmul_saturation797.py')})


def context():
    namespace = dict(engine.prepare.__globals__, __file__=__file__, SCHEMA=SCHEMA,
                     approved=approved, dependencies=dependencies)
    functions = [FunctionType(f.__code__, namespace, f.__name__, f.__defaults__)
                 for f in (engine.prepare, engine.check, engine.verify)]
    namespace.update(zip(('prepare', 'check', 'verify'), functions))
    return (*functions, FunctionType(engine.run.__code__, namespace))


def runtime_context(out, seal):
    config = life.read_bound(out / 'config.json', seal)
    need(config['schema'] == SCHEMA and config['successor_entry'] == str(Path(__file__).resolve())
         and config['output'] == str(out) and config['admission'] == dict(path=str(BASE), sha256=BASE_SHA),
         'Exact797 report runtime')
    need(config['pins'].get(str(Path(__file__).resolve())) == life.digest(__file__), 'Frozen797 entry')
    return context()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify', 'run-reviewed'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    parser.add_argument('--service-unit')
    parser.add_argument('--parent-reviewed-seal')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.mode == 'prepare':
        need(args.service_unit is not None, 'Explicit future service only; no launch')
        context()[0](out, BASE, args.seal, args.service_unit)
    else:
        need(args.service_unit is None, 'Service identity from frozen config')
        functions = runtime_context(out, args.seal)
        if args.mode == 'check':
            functions[1](out, args.seal)
            print('FULL797_INHERITED796_CHECK_PASS_NO_EDA')
        elif args.mode == 'verify':
            functions[2](out, args.seal)
        else:
            functions[3](out, args.seal, args.parent_reviewed_seal)
