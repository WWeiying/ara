"""Completed797 baseline plus exact MaskU zero3; new report requires parent review."""
import argparse
import csv
import inspect
import io
from pathlib import Path
from types import FunctionType

import prepare_masku_zero3_union797 as handoff
import report_population797_inherited796 as inherited

engine, stable, life, need = inherited.engine, inherited.stable, inherited.life, inherited.need
HERE = Path(__file__).resolve().parent
BASE, BASE_SHA = inherited.BASE, inherited.BASE_SHA
REPORT = handoff.REPORT797
CONFIG_SHA = handoff.CONFIG797_SHA
QUAL_SHA = '1ebc05103bc71ee6ec26d97e51ed4867fed3d35a21ee38490956c3ccadf2c5c6'
UNION = handoff.OUT / 'masku-zero3-union797-prepared-agent-20261008-01'
UNION_SHA = 'fb995f4d46fa436b89407fa80ef9447db371d82e07b8ceee2bdc0e952d73053e'
SCHEMA = 'FORMAL797_QUALIFIED_INHERITED_EL_PLUS_EXACT_MASKU_ZERO3_V1'


def baseline_gate(config, q):
    need(config['schema'] == inherited.SCHEMA and config['population'] == 797 and
         config['admission'] == dict(path=str(BASE), sha256=BASE_SHA) and
         q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         q['config_seal'] == CONFIG_SHA and q['admission_seal'] == BASE_SHA and
         type(q['population']) is int and q['population'] == q['actual_selected_tests'] == 797 and
         q['source_design_native_pins'] == config['pins'], 'Completed sealed report797 prerequisite')
    for key in ('complete_approved_EL_bitmask_union', 'all_other_bits_protected', 'raw_reset_final_equal',
                'applied_reloaded_equal', 'raw_hierarchy_vs_rooted_six_metrics_equal',
                'supported_roots_all_six_metrics_present', 'historical_PASS_only_no_new_RTL_signoff'):
        need(q[key] is True, 'Baseline797 acceptance gate: ' + key)
    stable.roots_gate(config['hierarchy_roots'])
    need(config['full_OR_metric_instances'] == 6162 and config['raw_hierarchy_rows'] == 2989 and
         len(q['module_reports']['raw']) == 73 and len(q['output_pins']) == 17,
         'Original five-phase73scope and17 output pins')
    stable.summaries_gate(q['module_reports'])


def baseline(reader):
    # Missing qualification or a wrong seal must fail before preparing outputs.
    qualification = reader.read(REPORT / 'qualification.json', QUAL_SHA, True)
    config = reader.read(REPORT / 'config.json', CONFIG_SHA, True)
    baseline_gate(config, qualification)
    pins = stable.merge(config['pins'], qualification['output_pins'],
                        {str(REPORT / 'qualification.json'): QUAL_SHA, str(REPORT / 'config.json'): CONFIG_SHA})
    base_el = reader.read(REPORT / 'combined.el', handoff.EL796_SHA).decode('ascii')
    need(stable.semantic_seal(stable.semantic(base_el)) == config['expected_EL_semantic_sha256'],
         'Exact complete inherited baseline EL')
    reports = {}
    for stage in stable.STAGES:
        ep = REPORT / stable.EL_FILES[stage]
        stable.el_gate(reader.read(ep, pins[str(ep)]), stage, config['expected_EL_semantic_sha256'])
        sp = REPORT / ('modules_' + stage + '.csv')
        reports[stage] = stable.summary(reader.read(sp, pins[str(sp)]), stage, config['hierarchy_roots'])
    need(reports == qualification['module_reports'], 'Exact baseline797 native five-stage metrics')
    stable.raw_summary_gate(reader.read(REPORT / 'raw.csv', pins[str(REPORT / 'raw.csv')]),
                            config['hierarchy_roots'], reports['raw'])
    selected = reader.read(REPORT / 'selected_tests.txt', pins[str(REPORT / 'selected_tests.txt')]).decode().splitlines()
    stable.membership(config['input_ledger'], selected, 797)
    need(selected == config['expected_selected'], 'Exact actual797 selected order')
    terminal = reader.read(REPORT / 'terminal.json', pins[str(REPORT / 'terminal.json')], True)
    stable.terminal_gate(terminal, config)
    need(terminal['config_seal'] == CONFIG_SHA, 'Executed baseline config seal')
    need(reader.read(REPORT / 'cleanup-empty.el', pins[str(REPORT / 'cleanup-empty.el')]) == b'', 'Baseline cleanup empty')
    for path in (REPORT / 'terminal-evidence/launcher.log', REPORT / 'terminal-evidence/dve_gui.log'):
        text = reader.read(path, pins[str(path)]).decode()
        stable.diagnostics(text)
    gui = reader.read(REPORT / 'terminal-evidence/dve_gui.log', pins[str(REPORT / 'terminal-evidence/dve_gui.log')]).decode()
    need(gui.splitlines().count('COMPACT777_FIVE_PHASE_DONE') == gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE') == 1,
         'Completed baseline native markers')
    return config, qualification, base_el, pins


def union_contract(config, baseline_config, pins, local, baseline_el, combined, delta):
    need(config['schema'] == handoff.SCHEMA and config['population'] == 797 and
         config['admission_manifest_sha256'] == BASE_SHA and config['input_ledger'] == baseline_config['input_ledger'] and
         config['inherited_EL_sha256'] == handoff.EL796_SHA and
         config['report797_config_sha256'] == CONFIG_SHA and config['strict_MASKU_receipt_sha256'] == handoff.STRICT_SHA and
         config['population_application'] is False and config['EDA_started'] is False and
         config['raw_zero']['suffix_raw_zero'] is config['raw_zero']['full797_zero'] is True and
         config['raw_zero']['raw796_zero'] is config['raw_zero']['exact_scope_OR'] is True and
         config['protected_complement']['retained_other_objects'] == 984, 'Exact independently qualified MaskU handoff')
    expected, added, stats = handoff.union_gate(baseline_el, local, pins)
    need(combined == expected and delta == added and config['union'] == stats and
         stats['added_objects'] == list(handoff.q.NAMES) and stats['already_inherited_objects'] == [] and
         stats['added_physical_bits'] == 768 and stats['added_toggle_direction_members'] == 1536,
         'Only exact three complete physical targets; every original rule retained')
    return stats


def approved(reader, manifest, seal):
    need(Path(manifest) == BASE and seal == BASE_SHA, 'Only same admitted797; not798 or an inferred suffix')
    previous, qualified, base_el, pins = baseline(reader)
    union = reader.read(UNION / 'config.json', UNION_SHA, True)
    pins = stable.merge(pins, union['pins'], {str(UNION / 'config.json'): UNION_SHA})
    local_config = reader.read(handoff.native.OUT / 'config.json', handoff.native.NATIVE_SHA, True)
    local = reader.read(handoff.native.OUT / 'first.el', pins[str(handoff.native.OUT / 'first.el')]).decode('ascii')
    combined = reader.read(UNION / 'combined.el', pins[str(UNION / 'combined.el')]).decode('ascii')
    delta = reader.read(UNION / 'masku-delta.el', pins[str(UNION / 'masku-delta.el')]).decode('ascii')
    stats = union_contract(union, previous, local_config, local, base_el, combined, delta)
    admission = reader.read(BASE, BASE_SHA, True)
    need(admission['coverage_admitted'] is True, 'Formal797 admission')
    bp = BASE.parent / 'combined-bits.json'
    bits = reader.read(bp, pins[str(bp)], True)
    need(bits['tests'] == previous['input_ledger'][1:] and
         {k:len(v) for k,v in bits['metrics'].items()} == engine.METRIC_COUNTS, 'Same complete797 corpus6162')
    ledger = reader.read(UNION / 'inputs.txt', pins[str(UNION / 'inputs.txt')]).decode().splitlines()
    need(ledger == previous['input_ledger'] and len(ledger) == len(set(ledger)) == 798, 'Exact797 members, not798 tests')
    statuspath = BASE.parent / 'status.json'
    status = reader.read(statuspath, pins[str(statuspath)], True)
    oldpath = handoff.OLD_BASE / 'combined-toggle-bits.json'
    fullpath = BASE.parent / 'combined-toggle-bits.json'
    old = reader.read(oldpath, pins[str(oldpath)], True)
    full = reader.read(fullpath, pins[str(fullpath)], True)
    suffix = Path(union['raw_zero']['suffix'])
    reader.read(suffix, pins[str(suffix)])
    sample, sha = handoff.raw.rows(suffix, [handoff.q.SCOPE])
    need(sha == pins[str(suffix)], 'Actual797 suffix native pin')
    handoff.population_gate(ledger[:-1], ledger, status, old[handoff.q.SCOPE], sample[handoff.q.SCOPE],
                            full[handoff.q.SCOPE], union['raw_zero']['positions'])
    activity = dict(previous['suffix_activity'],
                    baseline797_qualification_sha256=QUAL_SHA, baseline797_config_sha256=CONFIG_SHA,
                    MASKU_full797_suffix_zero=union['raw_zero'],
                    EL_additions=dict(family='MASKU_CHILD_ZERO3_ONLY', target_objects=3, physical_bits=768,
                                      toggle_direction_members=1536, protected_local_objects=984,
                                      strict_receipt_sha256=handoff.STRICT_SHA, exact_physical_dedup=True),
                    new_exclusions_added=True, all_original_pins_retained=True,
                    policy='Same797 population and original73scope six-metric protocol; exact inherited EL plus MaskU only')
    source = {k:previous[k] for k in ('input_ledger', 'expected_selected', 'hierarchy_roots', 'tool_identity')}
    return source, stable.merge(pins, reader.pins), combined, bits, previous['genealogy'], activity


def baseline_metrics_gate(reports, baseline_reports):
    stable.summaries_gate(reports)
    need(set(reports['raw']) == set(baseline_reports['raw']) and len(reports['raw']) == 73,
         'Original73scope exactly; no root expansion')
    for stage in ('raw', 'reset', 'final'):
        need(reports[stage] == baseline_reports[stage], 'Raw/reset/final all six metrics differ from same797 baseline')
    for stage in ('applied', 'reloaded'):
        for scope, metrics in baseline_reports[stage].items():
            affected = scope == handoff.q.SCOPE or handoff.q.SCOPE.startswith(scope + '.')
            fixed = ('Line', 'FSM', 'Condition', 'Branch') if affected else stable.METRICS
            need(all(reports[stage][scope][m] == metrics[m] for m in fixed),
                 'Non-target/other metric differs from same797 baseline: ' + scope)


def raw_metrics(blob):
    reader = csv.DictReader(io.StringIO(blob.decode('utf-8')))
    need(reader.fieldnames and {'Name', 'Depth', *stable.METRICS} <= set(reader.fieldnames), 'Raw six-metric schema')
    rows = list(reader)
    need(len(rows) == 2989, 'Full raw2989 hierarchy')
    return [tuple(r[k] for k in ('Name', 'Depth', *stable.METRICS)) for r in rows]


def compare_baseline_native(out, reports):
    reader = stable.Reader()
    q = reader.read(REPORT / 'qualification.json', QUAL_SHA, True)
    baseline_metrics_gate(reports, q['module_reports'])
    path = REPORT / 'raw.csv'
    need(raw_metrics((out / 'raw.csv').read_bytes()) == raw_metrics(reader.read(path, q['output_pins'][str(path)])),
         'Full raw hierarchy metrics differ from qualified same797 report')


def dependencies():
    return stable.merge(inherited.dependencies(), {str(p):life.digest(p) for p in
                        (Path(__file__).resolve(), HERE / 'test_report_population797_masku_zero3.py',
                         Path(handoff.__file__).resolve(), HERE / 'test_prepare_masku_zero3_union797.py')})


def context():
    namespace = dict(engine.prepare.__globals__, __file__=__file__, SCHEMA=SCHEMA, approved=approved,
                     dependencies=dependencies, QUAL_SHA=QUAL_SHA, compare_baseline_native=compare_baseline_native)
    anchors = {
        'prepare': {'new_exclusions_added=False': 'new_exclusions_added=True'},
        'check': {"config['new_exclusions_added'] is False": "config['new_exclusions_added'] is True"},
        'verify': {
            "gui=out/'DVEfiles/dve_gui.log'": "compare_baseline_native(out,reports)\n    gui=out/'DVEfiles/dve_gui.log'",
            "result=dict(status=": "result=dict(new_exclusions_added=True,EL_additions=config['suffix_activity']['EL_additions'],baseline797_qualification_sha256=QUAL_SHA,raw_metrics_equal_baseline797=True,status=",
        },
    }
    for name, replacements in anchors.items():
        source = inspect.getsource(getattr(engine, name))
        for before, after in replacements.items():
            need(source.count(before) == 1, 'Exact frozen engine anchor: ' + before)
            source = source.replace(before, after)
        exec(compile(source, __file__ + ':private-' + name, 'exec'), namespace)
    run = FunctionType(engine.run.__code__, namespace, 'run', engine.run.__defaults__)
    return namespace['prepare'], namespace['check'], namespace['verify'], run


def runtime(out, seal):
    config = life.read_bound(out / 'config.json', seal)
    need(config['schema'] == SCHEMA and config['output'] == str(out) and
         config['successor_entry'] == str(Path(__file__).resolve()) and config['population'] == 797 and
         config['suffix_activity']['baseline797_qualification_sha256'] == QUAL_SHA,
         'Exact frozen same797+MaskU runtime')
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
        need(args.service_unit is not None, 'Explicit future owning unit; preparation is not launch')
        context()[0](out, BASE, args.seal, args.service_unit)
    else:
        need(args.service_unit is None, 'Runtime unit from frozen config')
        functions = runtime(out, args.seal)
        if args.mode == 'check': functions[1](out, args.seal); print('FULL797_MASKU_ZERO3_CHECK_PASS_NO_EDA')
        elif args.mode == 'verify': functions[2](out, args.seal)
        else: functions[3](out, args.seal, args.parent_reviewed_seal)
