"""One formal742 report using qualified exact native scope unions, not new stimuli."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

import chain_fsm_fma742 as chain
import c910_srt_datapath_native_v4 as c910

base, life, require = chain.base, chain.life, chain.require
HERE = Path(__file__).resolve().parent
TCL = HERE / 'report_c910_combo742.tcl'
PRIOR = life.OUT / 'fsm124-fma108-observers-full742-20261007-02'
PRIOR_SEAL = '9320e443a56f61f4dd2fba0f75aa9cca6b43ad7f8304e7a3129ccebbec148850'
C910 = life.OUT / 'c910-srt-native1264-recovery-agent-20261007-01'
C910_SEAL = '5fa9180cf70f658fbf355e7510a8d9c99af0240f6be22084139791f47fddbf38'


def dwc_parser(config):
    p = Path(config['dwc_parser']['path'])
    life.check({str(p): config['dwc_parser']['sha256']})
    require(p == HERE / 'qualify_dwc_points742_v2.py', 'Unreviewed DWC parser family')
    spec = importlib.util.spec_from_file_location('combo_private_dwc', p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def records(text, config):
    groups = dict(prior=[], c910=[], dwc=[])
    cscopes = {i['scope'] for i in config['c910_config']['instances']}
    dscopes = {r[0] for r in config.get('dwc_config', {}).get('fsm_records', [])}
    dscopes |= {t['scope'] for t in config.get('dwc_config', {}).get('toggles', [])}
    require(not cscopes & dscopes, 'Overlapping typed scopes')
    for block in re.split(r'(?m)(?=^CHECKSUM:)', text):
        if not block:
            continue
        scopes = re.findall(r'(?m)^INSTANCE: *(\S+)$', block)
        require(len(scopes) == 1, 'Unbound or mixed native block')
        scope = scopes[0]
        family = 'c910' if scope in cscopes else 'dwc' if scope in dscopes else 'prior'
        groups[family].append(block)
    prior = chain.records(''.join(groups['prior']), config['fma_config'])
    arithmetic = c910.parse_el(''.join(groups['c910']), config['c910_config'])
    dwc = dwc_parser(config).parse_el(''.join(groups['dwc']), config['dwc_config']) if dscopes else []
    return json.loads(json.dumps(dict(prior=prior, c910=arithmetic, dwc=dwc)))


def native_tree(path):
    with path.open() as stream:
        rows = list(csv.reader(stream, delimiter='\t'))
    require(rows and rows[0] == ['handle', 'path', 'meta', 'name'] and
            all(len(r) == 4 and all(r) for r in rows[1:]), 'Malformed native inventory')
    identities = sorted(tuple(r[1:]) for r in rows[1:])
    require(identities and len(identities) == len(set(identities)), 'Duplicate native tree')
    return identities


def prepare(out, dwc_out=None):
    require(out.parent == life.OUT and not out.exists(), 'Fresh output required')
    c = life.read_bound(PRIOR / 'config.json', PRIOR_SEAL)
    q = json.loads((PRIOR / 'qualification.json').read_bytes())
    require(q['status'] == 'FULL742_EXACT124_FSM_FOUR_OBSERVER_FMA108_REPORT_VERIFIED' and
            q['config_seal'] == PRIOR_SEAL and q['population'] == 742, 'Prior report not qualified')
    cq = life.read_bound(C910 / 'capture-result.json', C910_SEAL)
    require(cq['status'] == 'EXACT_C910_1264_NATIVE_ROUNDTRIP_NOT_POPULATION_APPLICATION' and
            cq['objects'] == 1264 and cq['protected_local_objects'] == 416 and
            cq['semantic_reload'] and cq['finalreset'] and cq['non_target_exclusions'] == 0,
            'C910 not qualified')
    cc = life.read_bound(C910 / 'config.json', cq['config_seal'])
    require(c910.parse_el((C910 / 'first.el').read_text(), cc) ==
            c910.parse_el((C910 / 'second.el').read_text(), cc), 'C910 native reload differs')
    pins = chain.merge_inventories(c['pins'], q['output_pins'], cq['pins'],
            {str(PRIOR / 'config.json'): PRIOR_SEAL,
             str(PRIOR / 'qualification.json'): life.digest(PRIOR / 'qualification.json'),
             str(C910 / 'capture-result.json'): C910_SEAL})
    config = dict(c, output=str(out), c910_config=cc, dwc_included=dwc_out is not None)
    combined = (PRIOR / 'applied.el').read_text() + (C910 / 'first.el').read_text()
    dwc_selection = ''
    if dwc_out is not None:
        dq = json.loads((dwc_out / 'capture-result.json').read_bytes())
        require(dq['status'] == 'EXACT_DWC31_FSM_168_INTERNAL_TOGGLE_NATIVE_QUALIFIED_NOT_APPLIED' and
                dq['global_empty'] and dq['five_stages'] and dq['interfaces_retained'] and
                dq['toggle_directions'] == 168 and dq['protected_toggle_positions'] == 4188,
                'DWC not qualified')
        dc = life.read_bound(dwc_out / 'config.json', dq['config_seal'])
        prior_targets = {(g['scope'], g['machine']['name'], g['mode'], r['name'])
                         for g in c['plan']['groups'] for r in g['rows'] if r['target']}
        prior_protected = {(g['scope'], g['machine']['name'], g['mode'], r['name'])
                           for g in c['plan']['groups'] for r in g['rows'] if not r['target']}
        dwc_targets = {(r[0], r[3], r[5], r[6]) for r in dc['fsm_records']}
        require(not dwc_targets & (prior_targets | prior_protected),
                'DWC duplicates target or contradicts prior protection')
        parser_path = HERE / 'qualify_dwc_points742_v2.py'
        require(str(parser_path) in dq['pins'], 'Qualified DWC parser not pinned')
        config.update(dwc_config=dc, dwc_parser=dict(path=str(parser_path), sha256=dq['pins'][str(parser_path)]),
                      dwc_qualification_seal=life.digest(dwc_out / 'capture-result.json'))
        parsed = dwc_parser(config)
        require(parsed.parse_el((dwc_out / 'first.el').read_text(), dc) ==
                parsed.parse_el((dwc_out / 'second.el').read_text(), dc), 'DWC reload differs')
        pins = chain.merge_inventories(pins, dq['pins'],
                    {str(dwc_out / 'capture-result.json'): config['dwc_qualification_seal']})
        combined += (dwc_out / 'first.el').read_text()
        dwc_selection = (dwc_out / 'selection.tcl').read_text()
    expected = records(combined, config)
    require(len(expected['prior'][0]) == 124 and len(expected['prior'][1]) == 4 and
            len(expected['prior'][2]) == 108 and len(expected['c910']) == 1264,
            'Native union counts differ')
    tgl_groups = []
    for policy, capture, configured in [('fma', chain.FMA, c['fma_config']), ('c910', C910, cc)]:
        for index, instance in enumerate(configured['instances']):
            reference = native_tree(capture / ('native_before_%d.tsv' % index))
            targets = [s['name'] + '[%d:%d]' % (s['left'], s['right']) for s in instance['signals']]
            names = [r[2] for r in reference]
            require(all(names.count(t) == 1 for t in targets), 'Target native identity missing')
            tgl_groups.append(dict(policy=policy, index=index, scope=instance['scope'],
                                   targets=targets, reference=[list(r) for r in reference],
                                   protected=[n for n in names if n not in targets]))
    scopes = {g['scope'] for g in tgl_groups}
    require(len(scopes) == 20, 'Overlapping arithmetic scopes')
    for observer in c['observers']:
        arithmetic_scopes = scopes | {t['scope'] for t in config.get('dwc_config', {}).get('toggles', [])}
        require(not any(s == observer or s.startswith(observer + '.') for s in arithmetic_scopes),
                'Observer would blanket arithmetic scope')
    deps = [Path(__file__).resolve(), TCL, HERE / 'test_report_c910_combo742.py',
            Path(chain.__file__).resolve(), Path(c910.__file__).resolve()]
    pins = chain.merge_inventories(pins, {str(p): life.digest(p) for p in deps})
    life.check(pins)
    require(len(c['expected_selected']) == len(set(c['expected_selected'])) == 742 and
            len(c['input_ledger']) == len(set(c['input_ledger'])) == 743,
            'Not exact742 native population')
    out.mkdir()
    (out / 'inputs.txt').write_text((PRIOR / 'inputs.txt').read_text())
    (out / 'combined.el').write_text(combined)
    atom = base.capture.tcl_atom
    selection = (PRIOR / 'selection.tcl').read_text() + dwc_selection + '\nset combo_groups {}\n'
    for number, g in enumerate(tgl_groups):
        labels = ' '.join(atom(t) for t in [*g['targets'], *g['protected']])
        selection += 'lappend combo_groups [list %s %d [list %s]]\n' % (atom(g['scope']), number, labels)
    selection += 'set combo_has_dwc %d\n' % bool(dwc_out)
    (out / 'selection.tcl').write_text(selection)
    pins = chain.merge_inventories(pins, {str(out / n): life.digest(out / n)
                                         for n in ('inputs.txt', 'combined.el', 'selection.tcl')})
    config.update(schema='FULL742_QUALIFIED_NATIVE_UNION_C910_V1', pins=pins, expected_union=expected,
                  toggle_groups=tgl_groups, c910_qualification_seal=C910_SEAL,
                  integration_scope_not_unreachable=True, official_denominator_verified=False)
    life.save(out / 'config.json', config)
    seal = life.digest(out / 'config.json')
    print(json.dumps(dict(status='PREPARED_NO_DVE', seal=seal, dwc_included=bool(dwc_out),
                          c910_objects=1264, tests=742)), flush=True)
    return seal


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    require(not (out / 'error.txt').exists(), 'Native error artifact')
    require((out / 'inputs.txt').read_text().splitlines() == c['input_ledger'] and
            (out / 'selected_tests.txt').read_text().splitlines() == c['expected_selected'],
            '742 exact membership differs')
    for name in ('applied.el', 'reloaded.el'):
        require(records((out / name).read_text(), c) == c['expected_union'], 'Native union differs')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
        require((out / name).read_bytes() == b'', 'Nonempty reset')
    base.native.audit_points(list(csv.reader((out / 'exact-audit.tsv').open(), delimiter='\t')), c['plan'])
    for index, group in enumerate(c['toggle_groups']):
        for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
            require(native_tree(out / ('combo_%s_%d.tsv' % (stage, index))) ==
                    [tuple(r) for r in group['reference']], 'Target/protected native tree differs')
    if c['dwc_included']:
        d = c['dwc_config']
        rows = list(csv.reader((out / 'dwc-audit.tsv').open(), delimiter='\t'))
        wanted = {(stage, 'FSM', g['machine'], g['mode'], r['name'])
                  for stage in ('before', 'selected', 'reset', 'reloaded', 'final')
                  for g in d['groups'] for r in g['rows']}
        wanted |= {(stage, 'Toggle', t['scope'], '', t['label'])
                   for stage in ('before', 'selected', 'reset', 'reloaded', 'final') for t in d['toggles']}
        require(len(rows) == len(wanted) and {tuple(r[:5]) for r in rows} == wanted, 'DWC audit incomplete')
        for r in rows:
            require(r[5] in ('0', '1') and (r[6] == 'EL_AUTHORITY' or r[5] == r[6]), 'DWC membership differs')
        for index in range(3):
            def identities(stage):
                return sorted(tuple(r[1:]) for r in csv.reader(
                    (out / ('toggle-%s-%d.tsv' % (stage, index))).open(), delimiter='\t'))
            before = identities('before')
            require(before and len(before) == len(set(before)), 'Ambiguous DWC tree')
            require(all(identities(s) == before for s in ('selected', 'reset', 'reloaded', 'final')),
                    'DWC native complement differs')
    reports = {}
    for stage in ('raw', 'applied', 'reset', 'reloaded', 'final'):
        rows = list(csv.DictReader((out / ('rooted_' + stage + '.csv')).open()))
        require(len(rows) == 1 and rows[0]['Scope'] == rows[0]['Token'] == base.observer.SYSTEM and
                rows[0]['Name'] == rows[0]['GUIPath'] == 'i_system' and rows[0]['Stage'] == stage,
                'Rooted scope differs')
        reports[stage] = {m: rows[0][m] for m in base.native.METRICS}
    require(reports['raw'] == reports['reset'] == reports['final'] and
            reports['applied'] == reports['reloaded'], 'Raw/reset/reload metrics differ')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('COMBO742_NATIVE_DONE') == 1 and
            gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE') == 1 and
            gui.splitlines().count('DVE_SELECTED_TESTS: ' + ' '.join(c['expected_selected'])) == 1 and
            not re.search(r'EXPORT_FAILED|COMBO742_FAILED|Error:|Fatal:|EK-CMD-|DVTC[0-9]+|UCAPI-DLMA|DVCDT136', gui),
            'Native report failed')
    life.check(c['pins'])
    result = dict(status='FULL742_QUALIFIED_NATIVE_UNION_REPORT_VERIFIED', config_seal=seal,
                  population=742, system=reports, c910_objects=1264, fma_objects=108,
                  fsm_prior=124, observers=4, dwc_included=c['dwc_included'],
                  official_denominator_verified=False, input_pins=c['pins'],
                  output_pins={str(p): life.digest(p) for p in out.rglob('*') if p.is_file() and
                               p.name != 'qualification.json'})
    life.save(out / 'qualification.json', result)
    print(json.dumps(dict(status=result['status'], seal=life.digest(out / 'qualification.json'), system=reports)), flush=True)


def run(out, seal):
    # Use the mature launch/identity/lifecycle, replacing only its private hook.
    def popen(*args, **kwargs):
        env = dict(kwargs['env'])
        env['DVE_REVIEWED_WAIVERS'] = str(TCL)
        kwargs['env'] = env
        return base.subprocess.Popen(*args, **kwargs)
    namespace = dict(base.run.__globals__, verify=verify,
                     subprocess=SimpleNamespace(Popen=popen, TimeoutExpired=base.subprocess.TimeoutExpired))
    FunctionType(base.run.__code__, namespace)(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--dwc-output', type=Path)
    a = p.parse_args()
    if a.mode == 'prepare':
        prepare(a.output.absolute(), a.dwc_output.absolute() if a.dwc_output else None)
    else:
        require(a.seal, 'Exact seal required')
        (run if a.mode == 'run' else verify)(a.output.absolute(), a.seal)
