#!/usr/bin/env python3
"""Fresh historical717 raw/applied/reset; exact qualified707 native policies only."""
import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
import apply_branch_combo_six_latest as sealed_core
import apply_branch_combo_701 as four
import apply_branch_combo_five_701 as five
import capture_fp16_pack_native208_v2 as pack
import apply_branch_combo_701_v2 as roots_api
from report_scope_ancestors import report_ancestors

HERE, OUT = four.HERE, four.OUT
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = SCRIPT.with_name('test_apply_branch_combo_six_717.py')
BASE = OUT / 'branch-combo-five-policy-701-20261006-01'
BASE_SEAL = '9ee807bbb65c0f2404dac7970507a2903820ff44943b5169660295848fffaba8'
BASE_RESULT = '3d7ab8fe82c7ff2962d8f67a0ea45bef2880ac4426c20a044270894f991ccd26'
PACK = OUT / 'fp16-pack-native208-capture-prepare-20261006-02'
PACK_SEAL = '99c9c638f5fbfb3df697b039d51ae28367a8c76efc7fb1711d6f54cc49b2685e'
PACK_RESULT = 'd54c32975e8d5b4c24df12ec0afd0c059a6c94bd38507cef1771d9fdec042c0b'
GROUPS = five.GROUPS + ('pack',)
COUNTS = dict(five.COUNTS, pack=(208, 936))
STAGES = five.STAGES
TOTAL, PROTECTED = 5808, 13562
TIMEOUT = 10800
CLASSIFICATIONS = dict(five.CLASSIFICATIONS, pack='structural_FP16_pack_lower_bound')
require, sha, write, pin = four.require, four.sha, four.write, four.pin
INHERITED_TOOL_LINKS = {
    '/home/wangwy/openproject/ara/install/riscv-llvm/bin/clang': 'clang-22',
    '/home/wangwy/openproject/ara/install/riscv-llvm/bin/llvm-readelf': 'llvm-readobj',
    '/home/wangwy/openproject/ara/install/riscv-llvm/bin/ld.lld': 'lld',
    '/lib64/libgcc_s.so.1': 'libgcc_s-11-20240719.so.1',
    '/usr/bin/python3': 'python3.9',
}


def tool_link_identity(path):
    path = Path(path).absolute()
    require(str(path) in INHERITED_TOOL_LINKS and path.is_symlink() and
            str(path.readlink()) == INHERITED_TOOL_LINKS[str(path)], 'Inherited tool link identity differs')
    resolved = path.resolve(strict=True)
    require(resolved.is_file() and not resolved.is_symlink(), 'Unproven inherited resolved tool')
    return dict(link_target=str(path.readlink()), resolved=str(resolved), sha256=sha(resolved))


def pin(pins, path, expected=None):
    path = Path(path).absolute()
    if path.is_symlink():
        identity = tool_link_identity(path)
        require(expected is not None and identity['sha256'] == expected,
                'Inherited tool link lacks sealed byte identity')
        require(str(path) not in pins or pins[str(path)] == expected, 'Inherited tool pin conflict')
        pins[str(path)] = expected
        four.pin(pins, identity['resolved'], expected)
        return path
    return four.pin(pins, path, expected)


QUALIFIED707 = OUT / 'branch-combo-six-policy-707-20261006-02'
QUALIFIED_CONFIG = '9412f766aa75e7099fb3c0b354db655b78b1b6bee3abf39032b81d651128acaa'
QUALIFIED_RESULT = '076db58229664a213a389601ce8ac61a4b8805449489f7e0b6764c4e2217f3ea'
LATEST = OUT / 'cache-port1-offline-admitted-717-20261006-01'
LATEST_SEAL = '82cd5f277d934c7b2435bfff3e2af1d4dd64cdea6435baba67b72749be183b62'
RAW_GEOMETRY = OUT / 'raw715-dve-20261006-01'
RAW_GEOMETRY_SEAL = 'c6723a317c3e1a1701c0966a6a9466c322204198e9910734e2bf133aa17d6380'
EVIDENCE_SEAL = 'f676292e4aedbc89c2b6681ec350f0ef1fd1bb3033a3169a5172ed965808d42d'
SELECTION_HELPER = HERE / 'six_policy_singleton_selection_v2.tcl'
SELECTION_TEST = HERE / 'test_six_policy_singleton_selection_v2.py'

def qualification707(pins=None):
    config = load_sealed(QUALIFIED707 / 'config.json', QUALIFIED_CONFIG)
    result = load_sealed(QUALIFIED707 / 'capture-result.json', QUALIFIED_RESULT)
    require(result['config_sha256'] == QUALIFIED_CONFIG and result['tests'] == 707 and
            result['records'] == TOTAL and result['protected'] == PROTECTED and
            result['audited'] == TOTAL + PROTECTED and result['after_root_audit'] is True and
            result['after_root_native_export'] is True and result['final_reset'] is True,
            'Qualified707 exact native report differs')
    require(result['coordinate_review'] == config['coordinate_review'], '707 review differs')
    for p, expected in result['files'].items():
        require(sha(p) == expected, 'Qualified707 evidence drift: ' + p)
    require(all((QUALIFIED707 / n).read_bytes() == b'' for n in
                ('initial-empty.el', 'reset-empty.el', 'final-empty.el')), 'Qualified707 reset not empty')
    bound = sealed_core.bindings((QUALIFIED707 / 'combined.el').read_bytes(), config)
    require(all(bound[g]['binding_sha256'] == result['group_results'][g]['binding_sha256']
                for g in GROUPS), 'Independent707 native binding differs')
    if pins is not None:
        for p, expected in config['pins'].items():
            pin(pins, p, expected)
        for p, expected in result['files'].items():
            pin(pins, p, expected)
        pin(pins, QUALIFIED707 / 'config.json', QUALIFIED_CONFIG)
        pin(pins, QUALIFIED707 / 'capture-result.json', QUALIFIED_RESULT)
        pin(pins, QUALIFIED707 / 'combined.el')
    return config

def product_geometry_match(raw, reference, allowed):
    extra = set(raw) - set(reference)
    missing = set(reference) - set(raw)
    require(not extra and missing <= {allowed['scope']}, 'Product/external report hierarchy differs')
    require(allowed['scope'] == 'uvm_custom_install_verdi_recording' and allowed['descendants'] == [] and
            allowed['definition']['chksum'] == '2787408814' and
            allowed['native_exclusion_authorized'] is False, 'External root exception differs')
    for scope, row in raw.items():
        require(set(row) - {'GUIPath', 'Scope'} == set(reference[scope]) and
                row['Name'] == reference[scope]['Name'] and row['Depth'] == reference[scope]['Depth'],
                'Raw717 Name/Depth/column identity differs')
        # Metrics are actual717 exports, never inherited715 percentages.
        for k, value in row.items():
            if k in ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch'):
                require(value == 'NA' or re.fullmatch(r'(?:100|[0-9]{1,2})(?:\.[0-9]+)?%', value),
                        'Invalid official metric value')


def load_sealed(path, seal):
    require(re.fullmatch(r'[0-9a-f]{64}', seal or '') and sha(path) == seal,
            'External source seal differs: ' + str(path))
    return json.loads(Path(path).read_bytes())


def inventory(groups):
    require(set(groups) == set(GROUPS), 'Not exact six groups')
    owners, target_sets, protected_sets = {}, {}, {}
    for group in GROUPS:
        target, protected = set(), set()
        for scope, metrics in groups[group]['plan']['scopes'].items():
            require(scope not in owners, 'Overlapping native scope inventories')
            owners[scope] = group
            if group == 'operand':
                entries = [(r, True) for r in metrics['targets']] + [(r, False) for r in metrics['protected']]
            else:
                require(set(metrics) == {'branch'}, 'Foreign metric in group inventory')
                entries = [(r, r['target']) for r in metrics['branch']]
            for row, wanted in entries:
                index = row['raw_index'] if group == 'operand' else row['point']['raw_index']
                require(type(index) is int and index >= 0 and type(wanted) is bool, 'Invalid raw coordinate/decision')
                key = scope, index
                require(key not in target and key not in protected, 'Duplicate compiled coordinate')
                (target if wanted else protected).add(key)
        require((len(target), len(protected)) == COUNTS[group], 'Group target/protected count differs: ' + group)
        target_sets[group], protected_sets[group] = target, protected
    for a in GROUPS:
        for b in GROUPS:
            if a != b:
                require(not target_sets[a] & target_sets[b], 'Cross-group target overlap')
                require(not target_sets[a] & protected_sets[b], 'Target conflicts with cross-group protection')
                require(not protected_sets[a] & protected_sets[b], 'Cross-group protected overlap')
    require(len(owners) == 114, 'Not exact114 native scopes')
    return owners, target_sets, protected_sets


def latest_review(groups, bitmap, design, population):
    owners, targets, protected = inventory(groups)
    require(len(bitmap['tests']) == len(set(bitmap['tests'])) == population and type(population) is int and population == 717, 'Not exact717 bitmap population')
    hit_counts = dict.fromkeys(GROUPS, 0)
    build_pins = json.loads((OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
    for scope, group in owners.items():
        metrics = groups[group]['plan']['scopes'][scope]
        record = bitmap['metrics']['branch'][scope]
        require(type(record['width']) is int and record['width'] > 0, 'Invalid bitmap width')
        bits = int(record['bits'], 16)
        require(0 <= bits < 1 << record['width'], 'Bitmap out of range')
        definition = design.definition(scope, 'branch')
        require(record['checksum'] == definition.get('chksum') or
                (group == 'operand' and record['checksum'] is None), 'Compiled metric checksum differs')
        source = design.source(scope)
        require(sha(source['resolved_path']) == build_pins.get(source['resolved_path']), 'Compiled source bytes differ')
        from closure_point_inventory import points
        compiled = points('branch', definition, record['width'])
        by_index = {p['raw_index']: p for p in compiled}
        if group != 'operand':
            rows = metrics['branch']
            require(compiled == [r['point'] for r in rows], 'Complete compiled branch inventory differs')
            for row in rows:
                require(row['module_checksum'] == design.hierarchy[scope].get('chksum') and
                        row['metric_checksum'] == definition.get('chksum'), 'Compiled module ownership differs')
        else:
            for row in metrics['targets'] + metrics['protected']:
                p = by_index[row['raw_index']]
                require(row['selector'] == p['native_id'] + ',' + p['vector'] and
                        row['spec_checksum'] == p['attributes']['chksum'], 'Operand compiled coordinate differs')
            for row in metrics['targets']:
                require(row['module_checksum'] == design.hierarchy[scope].get('chksum') and
                        row['metric_checksum'] == definition.get('chksum'), 'Operand compiled ownership differs')
            require(set(by_index) == {r['raw_index'] for r in metrics['targets'] + metrics['protected']},
                    'Incomplete operand compiled inventory')
        for _, index in targets[group] | protected[group]:
            if _ == scope:
                require(index in by_index, 'Coordinate absent from compiled definition')
        for _, index in targets[group]:
            if _ == scope:
                hit = bool(bits & (1 << (record['width'] - index - 1)))
                require(group == 'debug' or not hit, 'Hit contradicts structural target proof')
                hit_counts[group] += int(hit)
        if group == 'exponent':
            import prepare_narrow_exponent_native1272 as proof
            # Classification is derived again from each actual compiled case spec.
            specs = {n.get('id'): n for n in definition.iter('branch_spec')}
            original = groups[group]['source_scopes'][scope]
            require(source == original['source'], 'Exponent compiled source owner differs')
            for row in metrics['branch']:
                p = row['point']
                hit = bool(bits & (1 << (record['width'] - 1 - p['raw_index'])))
                wanted, item = proof.classify(p, specs[p['native_id']], original['physical_position'][1],
                                             hit, proof.OWNERS[scope.rsplit('.', 1)[1]])
                require((wanted, item) == (row['target'], row['case_item']),
                        'Exponent source-derived default/WIDTH64 eligibility differs')
    require(all(hit_counts[g] == 0 for g in GROUPS if g != 'debug'), 'Structural target hit population differs')
    return dict(target_counts={g: len(targets[g]) for g in GROUPS},
                protected_counts={g: len(protected[g]) for g in GROUPS}, target_hits=hit_counts,
                unique_targets=sum(map(len, targets.values())), unique_protected=sum(map(len, protected.values())),
                cross_target_protection_conflicts=0, native_scopes=len(owners), tests=population)


def actual_roots(groups, reference):
    owners, targets, _ = inventory(groups)
    active = {scope for group in targets.values() for scope, index in group}
    roots = report_ancestors(list(reference.values()), active)
    require(all(r in reference and (r == 'ara_tb' or r.startswith('ara_tb.')) for r in roots),
            'Absent or external report root')
    return roots, {r: reference[r]['Name'] for r in roots}


def partition(raw, owners):
    require(raw.endswith(b'\n') and not re.search(rb'[^\x0a\x20-\x7e]', raw), 'Invalid aggregate EL bytes')
    result = {g: [] for g in GROUPS}
    for chunk in re.split(r'(?m)(?=^CHECKSUM:)', raw.decode('ascii')):
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        require(len(lines) >= 4 and re.fullmatch(r'CHECKSUM: "[0-9]+ [0-9]+"', lines[0]), 'Unknown EL header')
        match = re.fullmatch(r'INSTANCE: ?([A-Za-z_][A-Za-z0-9_.\[\]]*)', lines[1])
        require(match is not None and match[1] in owners, 'Extra native scope')
        result[owners[match[1]]].append(chunk)
    require(all(result.values()), 'Missing native group')
    return {g: ''.join(parts).encode('ascii') for g, parts in result.items()}


def worker(group, config_path, native_path, states=None):
    config = json.loads(Path(config_path).read_bytes())
    if group == 'pack':
        pack.validate_plan(config['plan'])
        rows = pack.bind_native(Path(native_path).read_bytes(), config)
        previous = None
        if states is not None:
            for stage in STAGES:
                previous = pack.audit_states(Path(states) / ('states_' + stage + '.tsv'), config, stage, previous)
        dependencies = {str(Path(m.__file__).resolve()): sha(m.__file__) for m in tuple(sys.modules.values())
                        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == HERE
                        and Path(m.__file__).suffix == '.py'}
        return dict(records=len(rows), binding_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                    audited=len(previous) if previous is not None else 0,
                    after_root_audited=len(previous) if previous is not None else 0, dependencies=dependencies)
    if group != 'exponent':
        result = five.worker(group, config_path, native_path, states)
        if states is not None:
            # Existing workers audit four stages; explicitly bind the new active
            # after-root observation to the same native identities as selected.
            if group == 'operand':
                import capture_operand_1144 as m
                audit = lambda path, stage, prior: m.states(path, config['plan'], stage, prior)
            elif group == 'ff1':
                import capture_ff1_native904 as m
                audit = lambda path, stage, prior: m.audit_states(path, config, stage, prior)
            elif group == 'qbs':
                import apply_qbs_rooted_701 as m
                audit = lambda path, stage, prior: m.base.q.audit_states(path, config, stage, prior)
            else:
                import apply_operand_debug_1832 as m
                audit = lambda path, stage, prior: m.base.audit_states(path, config, stage, prior)
            selected = audit(Path(states) / 'states_selected.tsv', 'selected', None)
            refreshed = audit(Path(states) / 'states_reloaded.tsv', 'reloaded', selected)
            require(refreshed == selected and len(refreshed) == sum(COUNTS[group]), 'After-root protection/identity differs')
        result['after_root_audited'] = sum(COUNTS[group]) if states is not None else 0
        return result
    import capture_narrow_exponent_native1272 as exp
    rows = exp.bind_native(Path(native_path).read_bytes(), config)
    previous = None
    if states is not None:
        for stage in STAGES:
            previous = exp.audit_states(Path(states) / ('states_' + stage + '.tsv'), config, stage, previous)
    dependencies = {str(Path(m.__file__).resolve()): sha(m.__file__) for m in tuple(sys.modules.values())
                    if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == HERE
                    and Path(m.__file__).suffix == '.py'}
    return dict(records=len(rows), binding_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                audited=len(previous) if previous is not None else 0,
                after_root_audited=len(previous) if previous is not None else 0, dependencies=dependencies)


def invoke(group, config, raw, states=None):
    # Use the frozen worker so its native parsing and dependency identity stay exact.
    return sealed_core.invoke(group, config, raw, states)


def bindings(raw, config, output=None):
    parts = partition(raw, config['scope_owners'])
    results = {g: invoke(g, config['groups'][g], parts[g], output / g if output else None) for g in GROUPS}
    for group, result in results.items():
        expected = config['bindings'][group]
        require(result['records'] == COUNTS[group][0] and
                result['binding_sha256'] == expected['binding_sha256'] and
                result['dependencies'] == expected['dependencies'], 'Native binding/source pin changed: ' + group)
    require(sum(r['records'] for r in results.values()) == TOTAL, 'Not exact5808 native records')
    return results



def baseline_inputs(base, raw_report, raw_seal, evidence_seal, pins):
    import capture_operand_1144 as lifecycle
    require(Path(base).absolute() == LATEST and Path(raw_report).absolute() == RAW_GEOMETRY and
            raw_seal == RAW_GEOMETRY_SEAL and evidence_seal == EVIDENCE_SEAL,
            'Only exact formal717 and source-reviewed715 geometry allowed')
    admitted = load_sealed(pin(pins, LATEST / 'admission-manifest.json', LATEST_SEAL), LATEST_SEAL)
    for path, expected in admitted['output_pins'].items():
        pin(pins, path, expected)
    evidence = json.loads(pin(pins, LATEST / 'evidence-pins.json', EVIDENCE_SEAL).read_bytes())
    for path, expected in evidence.items():
        pin(pins, path, expected)
    bits = json.loads((LATEST / 'combined-bits.json').read_bytes())
    state = json.loads((LATEST / 'status.json').read_bytes())
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            state['aggregate_passed'] == len(bits['tests']) == len(set(bits['tests'])) == 717,
            'Formal717 PASS population differs')
    inputs = (LATEST / 'combined-inputs.txt').read_text().splitlines()
    require(inputs == [str(OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb'), *bits['tests']],
            'Formal717 ordered membership differs')
    for path, expected in bits['input_hashes'].items():
        require(evidence.get(path) == expected, 'Raw member not bound to admission ledger')
        pin(pins, path, expected)
    for relative, expected in bits['design'].items():
        pin(pins, Path(inputs[0]) / 'snps/coverage/db' / relative, expected)
    geom = load_sealed(pin(pins, RAW_GEOMETRY / 'population-verification.json', raw_seal), raw_seal)
    require(geom['status'] == 'VERIFIED_HISTORICAL_RAW_REPORT' and geom['admitted_tests'] == 715 and
            geom['current_RTL_signoff'] is False, 'Geometry reference not verified historical715')
    for name in ('summary.csv', 'inputs.txt', 'selected_tests.txt'):
        path = RAW_GEOMETRY / name
        require(str(path) in geom['pins'], 'Unpinned geometry reference')
        pin(pins, path, geom['pins'][str(path)])
    require((RAW_GEOMETRY / 'inputs.txt').read_text().splitlines() == inputs[:716],
            'Raw715 geometry not same ordered design/prefix')
    tests = []
    for root in inputs[1:]:
        root = Path(root)
        require(root.resolve() == root and not root.is_symlink(), 'Aliased VDB root')
        dirs = list((root / 'snps/coverage/db/testdata').iterdir())
        require(len(dirs) == 1 and dirs[0].is_dir(), 'Not singleton admitted VDB')
        tests.append(str(root.with_suffix('') / dirs[0].name))
    require(len(tests) == len(set(tests)) == 717, 'Duplicate native selected-test identity')
    return bits, inputs, tests, 717


def checked_qualifications():
    base = five.read_config(BASE, BASE_SEAL)
    result = load_sealed(BASE / 'capture-result.json', BASE_RESULT)
    require(result['config_sha256'] == BASE_SEAL and result['records'] == 5600 and
            result['protected'] == 12626 and result['audited'] == 18226 and result['tests'] == 701 and
            result['after_root_audit'] is True and result['after_root_native_export'] is True and
            result['final_reset'] is True, 'Five-group parent qualification differs')
    for path, expected in result['files'].items():
        require(sha(path) == expected, 'Five-group artifact drift')
    pc = pack.read_config(PACK, PACK_SEAL)
    saved = load_sealed(PACK / 'capture-result.json', PACK_RESULT)
    verified = pack.verify(PACK, pc)
    require(saved['config_sha256'] == PACK_SEAL and
            all(saved.get(k) == v for k, v in verified.items() if k != 'files') and
            set(saved['files']) == set(verified['files']) | {str(PACK / 'config.json'), str(PACK / 'selection.tcl')} and
            all(saved['files'].get(k) == v for k, v in verified['files'].items()) and
            saved['files'][str(PACK / 'config.json')] == PACK_SEAL and
            saved['files'][str(PACK / 'selection.tcl')] == sha(PACK / 'selection.tcl'),
            'Pack exact independently regenerated qualification differs')
    return base, result, pc, saved


def prepare(output, base_path, raw_report, raw_seal, evidence_seal):
    import capture_operand_1144 as lifecycle
    import apply_qbs_rooted_701 as q
    from inventory_operand_debug import Design
    require(output.parent == OUT and not output.exists() and output.resolve() == output,
            'Fresh direct output required')
    qualified = qualification707()
    original = load_sealed(BASE / 'config.json', BASE_SEAL)
    pc = load_sealed(PACK / 'config.json', PACK_SEAL)
    pins = dict(qualified['pins'])
    for path, expected in ((BASE / 'config.json', BASE_SEAL), (BASE / 'capture-result.json', BASE_RESULT),
                           (PACK / 'config.json', PACK_SEAL), (PACK / 'capture-result.json', PACK_RESULT)):
        pin(pins, path, expected)
    for path, expected in load_sealed(QUALIFIED707 / 'capture-result.json', QUALIFIED_RESULT)['files'].items():
        pin(pins, path, expected)
    pin(pins, QUALIFIED707 / 'config.json', QUALIFIED_CONFIG)
    pin(pins, QUALIFIED707 / 'capture-result.json', QUALIFIED_RESULT)
    pin(pins, QUALIFIED707 / 'combined.el')
    bitmap, inputs, tests, count = baseline_inputs(base_path, raw_report, raw_seal, evidence_seal, pins)
    require(bitmap['tests'][:701] == original['inputs'][1:], 'Historical701 membership not retained')
    groups = copy.deepcopy(original['groups'])
    groups['pack'] = copy.deepcopy(pc)
    require(all(g['plan']['design_vdb'] == inputs[0] for g in groups.values()), 'Mixed compiled designs')
    require(all(g['plan']['tool_identity'] == pc['plan']['tool_identity'] for g in groups.values()),
            'Mixed actual tool identities')
    require(groups == qualified['groups'], 'Frozen707 group plans/nativeIDs changed')
    owners, _, _ = inventory(groups)
    design = Design(Path(inputs[0]))
    review = latest_review(groups, bitmap, design, count)
    # Independently classify pack cases against the source-bound old shape, now
    # using every current raw bit; diagnostic/native expressions remain separate.
    for scope, metrics in groups['pack']['plan']['scopes'].items():
        definition = design.definition(scope, 'branch')
        table = pack.inventory.case_table(definition)
        record = bitmap['metrics']['branch'][scope]
        for row in metrics['branch']:
            p = row['point']
            hit = bool(int(record['bits'], 16) & (1 << (record['width'] - 1 - p['raw_index'])))
            decision, item = pack.inventory.classify(p, table, hit)
            require(row['target'] == decision.startswith('SOURCE_PROOF') and
                    row['case_item'] == (item['item'] if item else None),
                    'Current source-derived pack/default/boundary identity differs')
    reference = q.reference_rows(Path(raw_report) / 'summary.csv')
    roots, names = actual_roots(groups, reference)
    membership = {root: lifecycle.proof.tree_members(root) for root in inputs}
    for root, members in membership.items():
        for name in members:
            pin(pins, Path(root) / name)
    joined = (QUALIFIED707 / 'combined.el').read_bytes()
    parts = partition(joined, owners)
    bindings_prepared = {g: invoke(g, groups[g], parts[g]) for g in GROUPS}
    require(bindings_prepared == qualified['bindings'], 'Frozen707 binding signatures/dependencies changed')
    require(sum(r['records'] for r in bindings_prepared.values()) == TOTAL, 'Not exact5808 native records')
    for result_binding in bindings_prepared.values():
        for path, expected in result_binding['dependencies'].items():
            pin(pins, path, expected)
    for path in (SCRIPT, TCL, TEST, SELECTION_HELPER, SELECTION_TEST, HERE / 'report_scope_ancestors.py',
                 HERE / 'test_report_scope_ancestors.py'):
        pin(pins, path)
    for path, expected in pins.items():
        require(sha(path) == expected, 'Source/input drift before prepare')
    config = dict(schema='six-policy-historical717-qualified707-v1', output=str(output), mode='report',
                  groups=groups, scope_owners=owners, inputs=inputs, selected_tests=tests,
                  qualification707_config_sha256=QUALIFIED_CONFIG, qualification707_result_sha256=QUALIFIED_RESULT,
                  inherited_tool_links={p: tool_link_identity(p) for p in INHERITED_TOOL_LINKS},
                  hierarchy_reference_only=True, reference_population=715, reference_metric_comparison=False,
                  population=count, admitted_base=str(Path(base_path).absolute()),
                  raw_report=str(Path(raw_report).absolute()), raw_verification_sha256=raw_seal,
                  evidence_sha256=evidence_seal, source_five_config_sha256=BASE_SEAL,
                  source_five_result_sha256=BASE_RESULT, pack_config_sha256=PACK_SEAL,
                  pack_result_sha256=PACK_RESULT, coordinate_review=review,
                  plan=dict(design_vdb=inputs[0], tool_identity=pc['plan']['tool_identity'],
                            scopes={s: m for g in groups.values() for s, m in g['plan']['scopes'].items()},
                            input_membership=membership),
                  targets=TOTAL, protected=PROTECTED, audited=TOTAL + PROTECTED,
                  bindings=bindings_prepared, pins=pins, root_refresh_scopes=roots, root_display_names=names,
                  audit_stages=list(STAGES), after_root_stage='reloaded', run_timeout_seconds=TIMEOUT,
                  policy_classifications=CLASSIFICATIONS, reviewed_external_root=original['reviewed_external_root'],
                  command=q.base.tool.launch_command(pc['plan']['tool_identity'], TCL),
                  application_approval=False, aggregate_admission=False, new_RTL_signoff=False,
                  official_denominator_verified=False, FSM_included=False)
    output.mkdir()
    for group in GROUPS:
        (output / group).mkdir()
    for name in ('root-helpers.tcl', 'capture-helpers.tcl', 'combo-library.tcl',
                 'operand-selection.tcl', 'debug-selection.tcl', 'ff1-selection.tcl', 'exponent-selection.tcl',
                 'root-row-helpers.tcl'):
        (output / name).write_bytes((BASE / name).read_bytes())
    excluded_vars = {'qbsapp_databases', 'qbsapp_tests', 'qbsapp_count', 'qbsapp_native'}
    lines = []
    for line in (BASE / 'qbs-selection.tcl').read_text().splitlines():
        if line.startswith('set ') and line.split(' ', 2)[1] in excluded_vars:
            continue
        lines.append(line)
    literal = lifecycle.literal
    lines += ['set qbsapp_databases {' + ' '.join(literal(v) for v in inputs[1:]) + '}',
              'set qbsapp_tests {' + ' '.join(literal(v) for v in tests) + '}',
              'set qbsapp_count ' + str(count),
              'set qbsapp_native ' + literal(str(output / 'combined.el'))]
    selection = '\n'.join(lines) + '\n'
    for name in ('selection.tcl', 'qbs-selection.tcl'):
        (output / name).write_text(selection)
    (output / 'inputs.txt').write_text('\n'.join(inputs) + '\n')
    (output / 'population-selection.tcl').write_text('set six_expected_count ' + str(count) + '\n')
    (output / 'pack-selection.tcl').write_bytes((PACK / 'selection.tcl').read_bytes())
    root_selection = 'set qbsrefresh_scopes {' + ' '.join(literal(s) for s in roots) + '}\n'
    root_selection += 'global combo_root_names\narray unset combo_root_names\narray set combo_root_names {' + ' '.join(
        literal(s) + ' ' + literal(names[s]) for s in roots) + '}\n'
    (output / 'root-selection.tcl').write_text(root_selection)
    (output / 'combined.el').write_bytes(joined)
    write(output / 'coordinate-review.json', review)
    for path in output.iterdir():
        if path.is_file():
            pin(pins, path)
    check_config(config, output)
    write(output / 'config.json', config)
    write(output / 'status.json', dict(status='PREPARED_NO_DVE', config_sha256=sha(output / 'config.json'),
                                      tests=count, targets=TOTAL, protected=PROTECTED, aggregate_admission=False))
    print('SIX_POLICY_PREPARED ' + sha(output / 'config.json'), flush=True)


def check_config(config, output):
    import capture_operand_1144 as lifecycle
    import apply_qbs_rooted_701 as q
    require(config['schema'] == 'six-policy-historical717-qualified707-v1' and config['output'] == str(output)
            and config['mode'] == 'report' and config['aggregate_admission'] is False
            and config['application_approval'] is False and config['new_RTL_signoff'] is False
            and config['official_denominator_verified'] is False and config['FSM_included'] is False,
            'Wrong exact six-policy report contract')
    require(config['inherited_tool_links'] == {p: tool_link_identity(p) for p in INHERITED_TOOL_LINKS} and
            all(config['pins'].get(v['resolved']) == config['pins'].get(p) == v['sha256']
                for p, v in config['inherited_tool_links'].items()), 'Inherited link/resolved pins differ')
    require((config['source_five_config_sha256'], config['source_five_result_sha256'],
             config['pack_config_sha256'], config['pack_result_sha256']) ==
            (BASE_SEAL, BASE_RESULT, PACK_SEAL, PACK_RESULT), 'Qualification source seals differ')
    qualified = qualification707()
    require(config['groups'] == qualified['groups'] and config['bindings'] == qualified['bindings'] and
            config['qualification707_config_sha256'] == QUALIFIED_CONFIG and
            config['qualification707_result_sha256'] == QUALIFIED_RESULT and
            config['hierarchy_reference_only'] is True and config['reference_population'] == 715 and
            config['reference_metric_comparison'] is False, 'Qualification/reference contract differs')
    require((output / 'combined.el').read_bytes() == (QUALIFIED707 / 'combined.el').read_bytes(),
            'Aggregate native bytes differ from qualified707')
    original = load_sealed(BASE / 'config.json', BASE_SEAL)
    require({g: config['groups'][g] for g in five.GROUPS} == original['groups'],
            'Frozen six-policy qualifications changed')
    require(config['groups']['pack'] == load_sealed(PACK / 'config.json', PACK_SEAL),
            'Qualified pack inventory changed')
    pins = {}
    bitmap, inputs, tests, count = baseline_inputs(config['admitted_base'], config['raw_report'],
                    config['raw_verification_sha256'], config['evidence_sha256'], pins)
    require(config['inputs'] == inputs and config['selected_tests'] == tests and
            config['population'] == count and set(config['plan']['input_membership']) == set(inputs)
            and bitmap['tests'][:701] == original['inputs'][1:], 'Not exact explicitly bound population')
    require(all(config['pins'].get(p) == h for p, h in pins.items()), 'Baseline expected pins omitted')
    owners, _, _ = inventory(config['groups'])
    require(config['scope_owners'] == owners and config['audit_stages'] == list(STAGES) and
            config['after_root_stage'] == 'reloaded' and config['run_timeout_seconds'] == TIMEOUT and
            (config['targets'], config['protected'], config['audited']) == (TOTAL, PROTECTED, TOTAL + PROTECTED)
            and config['policy_classifications'] == CLASSIFICATIONS, 'Inventory/protection contract differs')
    reference = q.reference_rows(Path(config['raw_report']) / 'summary.csv')
    roots, names = actual_roots(config['groups'], reference)
    require((roots, names) == (config['root_refresh_scopes'], config['root_display_names']),
            'Collapsed Names/Depth actual ancestor contract differs')
    require(config['command'] == lifecycle.tool.launch_command(config['plan']['tool_identity'], TCL),
            'Launch command differs')
    from inventory_operand_debug import Design
    require(config['coordinate_review'] == latest_review(config['groups'], bitmap, Design(Path(inputs[0])), count),
            'Current raw coordinate/protected source review differs')
    lifecycle.check_inputs(config)


def read_config(output, seal):
    config = load_sealed(output / 'config.json', seal)
    check_config(config, output)
    return config


def log_adapter(output):
    return (output / 'DVEfiles/dve_gui.log').read_text().splitlines().count('SIX717_SELECTION_ADAPTER_INSTALLED') == 1


def verify_artifacts(output, config):
    import apply_qbs_rooted_701 as q
    names = ['applied.el', 'after-root.el', 'initial-empty.el', 'reset-empty.el', 'final-empty.el',
             'selected_tests.txt', 'summary_raw.csv', 'summary_applied.csv', 'summary_reset.csv',
             'rooted-metrics.csv', 'gui-contract.tsv', 'live-identity.json', 'execution.json',
             'integrity-before.json', 'integrity-after.json', 'DVEfiles/dve_gui.log', 'launcher.log']
    paths = [output / n for n in names] + [output / g / ('states_' + s + '.tsv') for g in GROUPS for s in STAGES]
    require(all(p.is_file() and not p.is_symlink() for p in paths), 'Missing/aliased six-policy evidence')
    results = bindings((output / 'applied.el').read_bytes(), config, output)
    after = bindings((output / 'after-root.el').read_bytes(), config)
    require(all(after[g]['binding_sha256'] == results[g]['binding_sha256'] for g in GROUPS), 'Root refresh changed exact exclusions')
    require(sum(r['after_root_audited'] for r in results.values()) == TOTAL + PROTECTED, 'Missing after-root all-point audit')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        require((output / name).read_bytes() == b'', 'Global reset not empty')
    require((output / 'selected_tests.txt').read_text().splitlines() == config['selected_tests'], 'Actual explicit selected population differs')
    raw, applied, reset = [q.previous.pilot.corrected.summary(output / ('summary_' + s + '.csv')) for s in ('raw', 'applied', 'reset')]
    require(raw == reset and set(raw) == set(applied), 'Hierarchy/reset differs')
    require((output / 'summary_raw.csv').read_bytes() == (output / 'summary_reset.csv').read_bytes(), 'Raw/reset report bytes differ')
    reference = q.reference_rows(Path(config['raw_report']) / 'summary.csv')
    from inventory_operand_debug import Design
    review = latest_review(config['groups'], json.loads((Path(config['admitted_base']) / 'combined-bits.json').read_bytes()),
                           Design(Path(config['inputs'][0])), config['population'])
    require(config['coordinate_review'] == review, 'Independent latest coordinate/protection review differs')
    product_geometry_match(raw, reference, config['reviewed_external_root'])
    require(log_adapter(output) is True, 'Strict singleton selection adapter not installed')
    changes = []
    owners, targets, _ = inventory(config['groups'])
    active = {s for coords in targets.values() for s, i in coords}
    for scope, row in raw.items():
        require(set(row) == set(applied[scope]), 'Report columns changed')
        for metric, value in row.items():
            other = applied[scope][metric]
            if value != other:
                require(metric in ('Branch', 'Score') and any(s == scope or s.startswith(scope + '.') for s in active),
                        'Functional/protected-only report metric changed')
                changes.append(dict(scope=scope, metric=metric, raw=value, applied=other))
    rooted = roots_api.rooted_rows(output / 'rooted-metrics.csv', config['root_refresh_scopes'], config['root_display_names'], raw)
    with (output / 'gui-contract.tsv').open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(reader.fieldnames == ['stage', 'root', 'rows'], 'GUI contract schema differs')
        require(list(reader) == [dict(stage=s, root='ara_tb', rows=str(len(raw))) for s in ('raw', 'applied', 'reset')],
                'GUI contract rows/root differs')
    log = (output / 'DVEfiles/dve_gui.log').read_text()
    for marker in ('QBSAPP_CANONICAL_INPUTS', 'QBSAPP_LOAD_GATE_PASSED', 'SIX_COMBO_AFTER_ROOT_VERIFIED', 'SIX_COMBO_DONE_EXACT5808'):
        require(log.splitlines().count(marker) == 1, 'Missing exact six-policy completion: ' + marker)
    for stage in STAGES:
        for group, prefix in dict(qbs='QBS_AUDIT', debug='OBD_AUDIT', operand='OP1144_AUDIT', ff1='FF1_AUDIT', exponent='EXP1272_AUDIT', pack='PACK208_AUDIT').items():
            require(log.splitlines().count('%s %s %s' % (prefix, stage, sum(COUNTS[group]))) == 1, 'Missing full protected audit marker')
    for name in ('launcher.log', 'DVEfiles/dve_gui.log'):
        require(not re.search(r'SIX_COMBO_FAILED|SIX_COMBO_ERROR|UCAPI-DLMA|DVCDT136|Load Failed|EK-CMD-|checksum.*mismatch|(?:^|\s)(Warning|Error|Fatal)(?:[\s:-]|$)',
                              (output / name).read_text(), re.I | re.M), 'DVE diagnostic')
    live, execution = [json.loads((output / n).read_bytes()) for n in ('live-identity.json', 'execution.json')]
    require(live['executable_verified'] is True and live['executable'] == config['plan']['tool_identity']['executable']
            and live['launch_pid'] == execution['launch_pid'] and live['launch_starttime'] == execution['launch_starttime']
            and execution['returncode'] == 0 and execution['launch_count'] == 1 and execution['timeout_seconds'] == TIMEOUT
            and execution['command'] == config['command'],
            'Unproven/bound-mismatched tool execution')
    for name, key in (('integrity-before.json', 'checked'), ('integrity-after.json', 'unchanged')):
        require(json.loads((output / name).read_bytes()) == {key: True, 'pins': config['pins'], 'membership': config['plan']['input_membership']},
                'Integrity/source membership differs')
    return dict(status='HISTORICAL717_EXACT5808_PRODUCT_BRANCH_REPORT_NOT_NEW_RTL_SIGNOFF', tests=config['population'],
                records=TOTAL, protected=PROTECTED, audited=TOTAL + PROTECTED, after_root_audit=True,
                after_root_native_export=True, final_reset=True, aggregate_admission=False,
                new_RTL_signoff=False, official_denominator_verified=False, group_results=results,
                policy_classifications=CLASSIFICATIONS,
                coordinate_review=config['coordinate_review'], summary_changes=changes, rooted_metrics=rooted,
                allowed_report_absence=config['reviewed_external_root'], files={str(p): sha(p) for p in paths})


def run(output, seal):
    import capture_operand_1144 as lifecycle
    config = read_config(output, seal)
    require(json.loads((output / 'status.json').read_bytes())['status'] == 'PREPARED_NO_DVE', 'No repeat launch')
    require(not any((output / n).exists() for n in ('live-ready', 'execution.json', 'DVEfiles')), 'Preexisting run artifacts')
    identity = config['plan']['tool_identity']
    status = dict(status='RUNNING', config_sha256=seal, aggregate_admission=False, application_approval=False)
    write(output / 'status.json', status)
    write(output / 'integrity-before.json', dict(checked=True, pins=config['pins'], membership=config['plan']['input_membership']))
    process = None
    try:
        env = lifecycle.environment(identity, output)
        for key in ('DVE_REVIEWED_WAIVERS', 'DEBUG_CAPTURE_SEAL', 'OP1144_BASE_HOOK', 'OBD_SELECTION', 'FF1_CAPTURE_SEAL', 'EXP1272_CAPTURE_SEAL'):
            env.pop(key, None)
        with (output / 'launcher.log').open('w') as stream:
            process = subprocess.Popen(config['command'], cwd=output, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            start = lifecycle.tool.process_info(process.pid)['starttime']
            execution = dict(launch_pid=process.pid, launch_starttime=start, launch_count=1,
                             timeout_seconds=TIMEOUT, command=config['command'])
            write(output / 'execution.json', execution)
            deadline, live = time.monotonic() + 60, None
            while process.poll() is None and time.monotonic() < deadline:
                live = lifecycle.find_live(process, identity, start)
                if live:
                    break
                time.sleep(0.2)
            require(live is not None, 'No launch-bound actual DVE executable')
            write(output / 'live-identity.json', live)
            lifecycle.check_inputs(config)
            (output / 'live-ready').write_text('LIVE_EXECUTABLE_VERIFIED\n')
            print('SIX_POLICY_DVE_STARTED pid=%s launch_pid=%s' % (live['pid'], process.pid), flush=True)
            execution['returncode'] = process.wait(timeout=TIMEOUT)
            write(output / 'execution.json', execution)
        require(execution['returncode'] == 0, 'DVE exited nonzero')
        lifecycle.check_inputs(config)
        write(output / 'integrity-after.json', dict(unchanged=True, pins=config['pins'], membership=config['plan']['input_membership']))
        status.update(verify_artifacts(output, config))
        status['files'][str(output / 'config.json')] = sha(output / 'config.json')
        write(output / 'capture-result.json', status)
        status['capture_result_sha256'] = sha(output / 'capture-result.json')
    except Exception as error:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        status.update(status='FAILED', reason='%s: %s' % (type(error).__name__, error))
        raise
    finally:
        write(output / 'status.json', status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify', 'run', 'worker'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seal')
    parser.add_argument('--group', choices=GROUPS)
    parser.add_argument('--group-config', type=Path)
    parser.add_argument('--native', type=Path)
    parser.add_argument('--states', type=Path)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--raw-report', type=Path)
    parser.add_argument('--raw-seal')
    parser.add_argument('--evidence-seal')
    args = parser.parse_args()
    if args.command == 'worker':
        print(json.dumps(worker(args.group, args.group_config, args.native, args.states)))
        return
    require(args.output is not None, 'Output required')
    output = args.output.absolute()
    require(output.parent.resolve() == OUT.resolve() and not output.is_symlink(), 'Unsafe output')
    if args.command == 'prepare':
        prepare(output, LATEST, RAW_GEOMETRY, RAW_GEOMETRY_SEAL, EVIDENCE_SEAL)
    elif args.command == 'verify':
        print(json.dumps(verify_artifacts(output, read_config(output, args.seal)), indent=2))
    else:
        run(output, args.seal)


if __name__ == '__main__':
    main()
