#!/usr/bin/env python3
"""Six exact branch policies on an explicitly sealed historical706/707 base."""
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
import apply_branch_combo_701 as four
import apply_branch_combo_five_701 as five
import capture_fp16_pack_native208_v2 as pack
import apply_branch_combo_701_v2 as roots_api
from report_scope_ancestors import report_ancestors

HERE, OUT = four.HERE, four.OUT
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = SCRIPT.with_name('test_apply_branch_combo_six_latest.py')
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
    require(len(bitmap['tests']) == len(set(bitmap['tests'])) == population and population in (706, 707), 'Not explicit706/707 bitmap population')
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
    with tempfile.TemporaryDirectory(prefix='six-policy-bind-') as name:
        directory = Path(name)
        write(directory / 'config.json', config)
        (directory / 'native.el').write_bytes(raw)
        command = [sys.executable, '-B', str(SCRIPT), 'worker', '--group', group,
                   '--group-config', str(directory / 'config.json'), '--native', str(directory / 'native.el')]
        if states is not None:
            command += ['--states', str(states)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=240, check=True)
        return json.loads(result.stdout)


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
    base, raw_report = Path(base).absolute(), Path(raw_report).absolute()
    require(base.parent == OUT and raw_report.parent == OUT and
            base.resolve() == base and raw_report.resolve() == raw_report, 'Unsafe explicit baseline')
    verified = load_sealed(pin(pins, raw_report / 'population-verification.json', raw_seal), raw_seal)
    require(verified['status'] == 'VERIFIED_HISTORICAL_RAW_REPORT' and
            verified['admitted_tests'] in (706, 707) and verified['current_RTL_signoff'] is False,
            'Not reviewed explicit706/707 raw population')
    for path, expected in verified['pins'].items():
        pin(pins, path, expected)
    bitmap_path, state_path, inputs_path = [base / n for n in
                                         ('combined-bits.json', 'status.json', 'combined-inputs.txt')]
    require(all(str(p) in verified['pins'] for p in (bitmap_path, state_path, inputs_path)),
            'Raw verification does not bind explicit admitted base')
    bits = json.loads(bitmap_path.read_bytes())
    state = json.loads(state_path.read_bytes())
    count = verified['admitted_tests']
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            state['aggregate_passed'] == len(bits['tests']) == len(set(bits['tests'])) == count,
            'Admitted population differs')
    inputs = inputs_path.read_text().splitlines()
    require(inputs == [str(OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb'), *bits['tests']],
            'Explicit base input membership/order differs')
    evidence = json.loads(pin(pins, base / 'evidence-pins.json', evidence_seal).read_bytes())
    for path, expected in evidence.items():
        pin(pins, path, expected)
    for path, expected in bits['input_hashes'].items():
        pin(pins, path, expected)
    for relative, expected in bits['design'].items():
        pin(pins, Path(inputs[0]) / 'snps/coverage/db' / relative, expected)
    tests = (raw_report / 'selected_tests.txt').read_text().splitlines()
    derived = []
    for root in inputs[1:]:
        root = Path(root)
        require(root.resolve() == root and not root.is_symlink(), 'Aliased VDB root')
        dirs = list((root / 'snps/coverage/db/testdata').iterdir())
        require(len(dirs) == 1 and dirs[0].is_dir(), 'Not singleton admitted VDB')
        derived.append(str(root.with_suffix('') / dirs[0].name))
    require(len(tests) == len(set(tests)) == count and set(tests) == set(derived),
            'Native selected-test identities differ from explicit VDBs')
    require((raw_report / 'inputs.txt').read_text().splitlines() == inputs,
            'Raw report input paths differ')
    return bits, inputs, tests, count


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
    original, result, pc, saved = checked_qualifications()
    pins = dict(original['pins'])
    for inventory_pins in (pc['pins'], result['files'], saved['files']):
        for path, expected in inventory_pins.items():
            pin(pins, path, expected)
    for path, expected in ((BASE / 'config.json', BASE_SEAL), (BASE / 'capture-result.json', BASE_RESULT),
                           (PACK / 'config.json', PACK_SEAL), (PACK / 'capture-result.json', PACK_RESULT)):
        pin(pins, path, expected)
    bitmap, inputs, tests, count = baseline_inputs(base_path, raw_report, raw_seal, evidence_seal, pins)
    require(bitmap['tests'][:701] == original['inputs'][1:], 'Historical701 membership not retained')
    groups = copy.deepcopy(original['groups'])
    groups['pack'] = copy.deepcopy(pc)
    require(all(g['plan']['design_vdb'] == inputs[0] for g in groups.values()), 'Mixed compiled designs')
    require(all(g['plan']['tool_identity'] == pc['plan']['tool_identity'] for g in groups.values()),
            'Mixed actual tool identities')
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
    joined = (BASE / 'combined.el').read_bytes() + b'\n' + (PACK / 'first.el').read_bytes()
    parts = partition(joined, owners)
    bindings_prepared = {g: invoke(g, groups[g], parts[g]) for g in GROUPS}
    require(sum(r['records'] for r in bindings_prepared.values()) == TOTAL, 'Not exact5808 native records')
    for result_binding in bindings_prepared.values():
        for path, expected in result_binding['dependencies'].items():
            pin(pins, path, expected)
    for path in (SCRIPT, TCL, TEST, HERE / 'report_scope_ancestors.py'):
        pin(pins, path)
    for path, expected in pins.items():
        require(sha(path) == expected, 'Source/input drift before prepare')
    config = dict(schema='six-policy-explicit-historical-base-v1', output=str(output), mode='report',
                  groups=groups, scope_owners=owners, inputs=inputs, selected_tests=tests,
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
    require(config['schema'] == 'six-policy-explicit-historical-base-v1' and config['output'] == str(output)
            and config['mode'] == 'report' and config['aggregate_admission'] is False
            and config['application_approval'] is False and config['new_RTL_signoff'] is False
            and config['official_denominator_verified'] is False and config['FSM_included'] is False,
            'Wrong exact six-policy report contract')
    require((config['source_five_config_sha256'], config['source_five_result_sha256'],
             config['pack_config_sha256'], config['pack_result_sha256']) ==
            (BASE_SEAL, BASE_RESULT, PACK_SEAL, PACK_RESULT), 'Qualification source seals differ')
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
    q.product_match(raw, reference)
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
    rooted = roots_api.rooted_rows(output / 'rooted-metrics.csv', config['root_refresh_scopes'], config['root_display_names'], reference)
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
    return dict(status='EXPLICIT_HISTORICAL_BASE_EXACT5808_PRODUCT_BRANCH_REPORT_NOT_AGGREGATE_SIGNOFF', tests=config['population'],
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
        require(args.base is not None and args.raw_report is not None, 'Explicit base/raw report required')
        prepare(output, args.base, args.raw_report, args.raw_seal, args.evidence_seal)
    elif args.command == 'verify':
        print(json.dumps(verify_artifacts(output, read_config(output, args.seal)), indent=2))
    else:
        run(output, args.seal)


if __name__ == '__main__':
    main()
