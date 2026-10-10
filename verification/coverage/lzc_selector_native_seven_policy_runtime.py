"""Independent seven-policy runtime preparation/verification; never starts EDA."""
import argparse
import ast
import copy
import csv
import inspect
import json
from pathlib import Path
import re

import prepare_six_policy_population_v2 as six
import lzc_selector_native_seven_policy_plan as seven
import capture_operand_1144 as lifecycle

frozen, require = six.frozen, six.require
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = SCRIPT.with_name('test_lzc_selector_native_seven_policy_runtime.py')
STAGES = ('before', 'selected', 'reset', 'reloaded', 'after-root', 'final')
BINDINGS = frozen.OUT / 'lzc_selector_native_product_batch-707-20261006-05/native-bindings.tcl'
HELPERS = ('root-helpers.tcl', 'capture-helpers.tcl', 'combo-library.tcl',
           'operand-selection.tcl', 'debug-selection.tcl', 'ff1-selection.tcl',
           'exponent-selection.tcl', 'root-row-helpers.tcl', 'qbs-selection.tcl',
           'selection.tcl', 'pack-selection.tcl', 'root-selection.tcl', 'population-selection.tcl')


def six_library():
    text = six.prior.TCL.read_text()
    boundary = 'set failed [catch {six_initialize; qbsapp_session} message]\n'
    require(text.count(boundary) == 1, 'Frozen six entry library boundary differs')
    library = text.split(boundary)[0]
    require(library.startswith('# Tcl 8.4.') and 'proc six_initialize {}' in library
            and 'gui_exit' not in library, 'Not a library-only six prefix')
    return library


def row_key(row):
    return tuple(row.get(k) for k in ('scope', 'metric', 'native_id', 'expression', 'vector'))


def target_positions(plan):
    rows = plan['exact_lzc_protection_rows']
    keys = [row_key(r) for r in rows]
    require(len(keys) == len(set(keys)) == 4200, 'Not exact unique4200')
    targets = {(r['scope'], 'cond', None, r['expression'], '1') for r in plan['condition_native_records']}
    require(len(targets) == 60 and targets <= set(keys)
            and all(r['vector'] == '1' and r['module_checksum'] == '3250293308'
                    for r in plan['condition_native_records']), 'Not exact60 known-true child vectors')
    return [i for i, key in enumerate(keys) if key in targets]


def selection_text(plan):
    literal = lifecycle.literal
    rows = []
    for i, row in enumerate(plan['exact_lzc_protection_rows']):
        values = [row['scope'], row['metric'], row['native_id'] or '',
                  row['expression'] or '', row['vector'], str(i)]
        rows.append('{' + ' '.join(literal(v) for v in values) + '}')
    return ('source ' + literal(str(BINDINGS)) + '\nset seven_rows {' + ' '.join(rows) +
            '}\nset seven_target_positions {' + ' '.join(map(str, target_positions(plan))) + '}\n')


def contract(plan, config):
    require(plan['population'] == config['population'] >= 724
            and plan['admission'] == config['admitted_base']
            and plan['admission_sha256'] == config['admission_manifest_sha256'], 'Fresh724-or-later population binding required')
    require((plan['original_six_targets'], plan['original_six_protected'], plan['extra_cond_targets'],
             plan['total_targets'], plan['total_protected'], plan['total_audited_positions']) ==
            (5808, 13562, 60, 5868, 17702, 23570), 'Seven counts differ')
    require(plan['branch_hold'] == 60 and plan['op16'] == 'HOLD'
            and plan['source_four_state_closure_proved']
            and not plan['frozen_four_state_initialization_qualified']
            and not plan['native_X_semantics_measured'] and not plan['application_approval'], 'Source-only narrow contract differs')
    target_positions(plan)


def prepare(output, six_output, six_seal, plan_output, plan_seal, accept_contract=False):
    require(accept_contract, 'Explicit parent acceptance of padding X/0 limits required')
    require(output.parent == frozen.OUT and output.resolve() == output and not output.exists(), 'Fresh independent runtime output required')
    _, config = six.read_config(six_output, six_seal)
    plan = frozen.load_sealed(plan_output / 'application-plan.json', plan_seal)
    contract(plan, config)
    require(plan['six_config'] == str(six_output / 'config.json')
            and plan['six_config_sha256'] == six_seal, 'Six/plan exact identity differs')
    pins = dict(config['pins'])
    for path, expected in plan['pins'].items():
        require(path not in pins or pins[path] == expected, 'Input pin conflict')
        pins[path] = expected
    require(pins.get(str(BINDINGS)) == '097fdb5473177274c02e895c9f5ee44c8e34c5133621ef1d40b279b5201ff613',
            'Observed native binding dependency missing')
    for path in (SCRIPT, TCL, TEST, SCRIPT.with_name('run_lzc_selector_native_seven_policy.py'),
                 SCRIPT.with_name('test_run_lzc_selector_native_seven_policy.py'),
                 SCRIPT.with_name('run_six_policy_population.py'),
                 plan_output / 'application-plan.json', six_output / 'config.json', six.prior.TCL):
        actual = frozen.sha(path)
        require(str(path) not in pins or pins[str(path)] == actual, 'Runtime dependency drift')
        pins[str(path)] = actual
    for path, expected in pins.items():
        require(frozen.sha(path) == expected, 'Input drift: ' + path)
    combined = (plan_output / 'combined-seven-proposal.el').read_bytes()
    original, _ = seven.split_seven(combined, config, plan['condition_native_records'])
    require(original == (six_output / 'combined.el').read_bytes(), 'Original six EL changed')
    output.mkdir()
    for group in (*frozen.GROUPS, 'lzc'):
        (output / group).mkdir()
    for name in HELPERS:
        source = six_output / name
        require(config['pins'].get(str(source)) == frozen.sha(source), 'Generated six helper not pinned: ' + name)
        (output / name).write_bytes(source.read_bytes())
    (output / 'six-library.tcl').write_text(six_library())
    (output / 'seven-selection.tcl').write_text(selection_text(plan))
    (output / 'combined-seven.el').write_bytes(combined)
    for path in output.iterdir():
        if path.is_file():
            pins[str(path)] = frozen.sha(path)
    # Retain a sealed six-view facade for the frozen lifecycle result's config pin.
    # The separately sealed runtime-plan is authoritative for seventh-policy counts.
    (output / 'config.json').write_bytes((six_output / 'config.json').read_bytes())
    pins[str(output / 'config.json')] = frozen.sha(output / 'config.json')
    runtime = dict(schema='lzc-seven-policy-runtime-v1', output=str(output),
                   six_output=str(six_output), six_config_sha256=six_seal,
                   seven_output=str(plan_output), seven_plan_sha256=plan_seal,
                   population=config['population'], admission_sha256=config['admission_manifest_sha256'],
                   targets=5868, protected=17702, audited=23570, stages=list(STAGES),
                   command=lifecycle.tool.launch_command(config['plan']['tool_identity'], TCL),
                   timeout_seconds=frozen.TIMEOUT, padding_x0_contract_accepted=True,
                   native_X_semantics_measured=False, four_state_initialization_qualified=False,
                   branch_hold=60, op16='HOLD', launch_approved=False, application_approval=False,
                   official_denominator_verified=False, automatic_retry=False, pins=pins)
    frozen.write(output / 'runtime-plan.json', runtime)
    frozen.write(output / 'runtime-plan.sha256.json', {str(output / 'runtime-plan.json'): frozen.sha(output / 'runtime-plan.json')})
    frozen.write(output / 'status.json', dict(status='PREPARED_NO_DVE', application_approval=False))
    return runtime


def read_config(output, seal):
    runtime = frozen.load_sealed(output / 'runtime-plan.json', seal)
    require(runtime['schema'] == 'lzc-seven-policy-runtime-v1' and runtime['output'] == str(output)
            and (runtime['targets'], runtime['protected'], runtime['audited']) == (5868, 17702, 23570)
            and runtime['stages'] == list(STAGES) and runtime['timeout_seconds'] == frozen.TIMEOUT
            and runtime['padding_x0_contract_accepted'] and not runtime['native_X_semantics_measured']
            and not runtime['four_state_initialization_qualified'] and runtime['branch_hold'] == 60
            and runtime['op16'] == 'HOLD' and not runtime['launch_approved']
            and not runtime['application_approval'] and not runtime['official_denominator_verified']
            and not runtime['automatic_retry'], 'Runtime contract differs')
    for path, expected in runtime['pins'].items():
        require(frozen.sha(path) == expected, 'Runtime pin drift: ' + path)
    context, config = six.read_config(Path(runtime['six_output']), runtime['six_config_sha256'])
    plan = frozen.load_sealed(Path(runtime['seven_output']) / 'application-plan.json', runtime['seven_plan_sha256'])
    contract(plan, config)
    expected_pins = dict(config['pins'], **plan['pins'])
    require(all(runtime['pins'].get(p) == h for p, h in expected_pins.items()), 'Mandatory input pins omitted')
    mandatory = (SCRIPT, TCL, TEST, SCRIPT.with_name('run_lzc_selector_native_seven_policy.py'),
                 SCRIPT.with_name('test_run_lzc_selector_native_seven_policy.py'),
                 SCRIPT.with_name('run_six_policy_population.py'), six.prior.TCL,
                 Path(runtime['seven_output']) / 'application-plan.json',
                 Path(runtime['six_output']) / 'config.json', output / 'config.json',
                 output / 'six-library.tcl', output / 'seven-selection.tcl', output / 'combined-seven.el',
                 *(output / name for name in HELPERS))
    require(all(runtime['pins'].get(str(p)) == frozen.sha(p) for p in mandatory), 'Mandatory runtime dependency omitted')
    require(runtime['population'] == config['population']
            and runtime['admission_sha256'] == config['admission_manifest_sha256']
            and plan['six_config'] == str(Path(runtime['six_output']) / 'config.json')
            and plan['six_config_sha256'] == runtime['six_config_sha256'], 'Population/plan identity differs')
    require((output / 'six-library.tcl').read_text() == six_library()
            and (output / 'seven-selection.tcl').read_text() == selection_text(plan), 'Generated runtime library/coordinates differ')
    for name in HELPERS:
        require((output / name).read_bytes() == (Path(runtime['six_output']) / name).read_bytes(), 'Six helper bytes differ')
    require((output / 'combined-seven.el').read_bytes() ==
            (Path(runtime['seven_output']) / 'combined-seven-proposal.el').read_bytes(), 'Combined proposal changed')
    require((output / 'config.json').read_bytes() ==
            (Path(runtime['six_output']) / 'config.json').read_bytes(), 'Frozen six-view facade differs')
    require(runtime['command'] == lifecycle.tool.launch_command(config['plan']['tool_identity'], TCL), 'Actual Tcl command differs')
    derived = copy.deepcopy(config)
    derived.update(output=str(output), command=runtime['command'], pins=runtime['pins'])
    return context, derived


def read_lzc_states(path, plan, active):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(reader.fieldnames == ['position', 'scope', 'metric', 'native_id', 'expression', 'vector', 'excluded'], 'LZC audit schema differs')
        actual = list(reader)
    wanted = []
    targets = set(target_positions(plan))
    for i, row in enumerate(plan['exact_lzc_protection_rows']):
        wanted.append(dict(position=str(i), scope=row['scope'], metric=row['metric'],
                           native_id=row['native_id'] or '', expression=row['expression'] or '',
                           vector=row['vector'], excluded=str(int(active and i in targets))))
    require(actual == wanted, 'Full4200 LZC identity/protected state differs: ' + str(path))
    return len(actual)


def change_allowed(scope, metric, six_active, lzc_active):
    ancestor = lambda scopes: any(s == scope or s.startswith(scope + '.') for s in scopes)
    return ((metric in ('Branch', 'Score') and ancestor(six_active)) or
            (metric in ('Condition', 'Score') and ancestor(lzc_active)))


def seven_verifier(namespace, allow):
    # One exact AST replacement; all other frozen verifier checks remain intact.
    tree = ast.parse(inspect.getsource(frozen.verify_artifacts))
    needle = ast.parse("metric in ('Branch', 'Score') and any(s == scope or s.startswith(scope + '.') for s in active)", mode='eval').body
    class Adapter(ast.NodeTransformer):
        replacements = 0

        def visit_BoolOp(self, node):
            if ast.dump(node) == ast.dump(needle):
                self.replacements += 1
                return ast.copy_location(ast.parse('seven_change_allowed(scope, metric, active)', mode='eval').body, node)
            return self.generic_visit(node)
    adapter = Adapter()
    tree = adapter.visit(tree)
    require(adapter.replacements == 1, 'Frozen report metric allowance boundary differs')
    bindings = dict(frozen.__dict__, **namespace, seven_change_allowed=allow)
    exec(compile(ast.fix_missing_locations(tree), str(SCRIPT), 'exec'), bindings)
    return bindings['verify_artifacts']


def verify(output, seal):
    context, config = read_config(output, seal)
    runtime = frozen.load_sealed(output / 'runtime-plan.json', seal)
    plan = frozen.load_sealed(Path(runtime['seven_output']) / 'application-plan.json', runtime['seven_plan_sha256'])
    native = plan['condition_native_records']
    def bind(raw, cfg, states=None):
        original, _ = seven.split_seven(raw, cfg, native)
        return frozen.bindings(original, cfg, states)
    lzc_active = {r['scope'] for r in native}
    namespace = dict(context.namespace(), bindings=bind,
                     log_adapter=lambda p: (p / 'DVEfiles/dve_gui.log').read_text().splitlines().count('SIX_POPULATION_SELECTION_ADAPTER_INSTALLED') == 1)
    result = seven_verifier(namespace, lambda scope, metric, active: change_allowed(scope, metric, active, lzc_active))(output, config)
    paths = []
    log = (output / 'DVEfiles/dve_gui.log').read_text()
    require(not re.search(r'SEVEN_(?:ERROR|FAILED)', log), 'Seven Tcl failure')
    for stage in STAGES:
        path = output / 'lzc' / ('states_' + stage + '.tsv')
        require(path.is_file() and not path.is_symlink(), 'Missing/aliased LZC audit')
        read_lzc_states(path, plan, stage in ('selected', 'reloaded', 'after-root'))
        paths.append(path)
        for marker in ('SEVEN_LZC_AUDIT %s 4200' % stage, 'SEVEN_FULL_AUDIT %s 23570' % stage):
            require(log.splitlines().count(marker) == 1, 'Missing complete audit: ' + marker)
    for group in frozen.GROUPS:
        path = output / group / 'states_after-root.tsv'
        require(path.is_file() and not path.is_symlink() and path.read_bytes() ==
                (output / group / 'states_selected.tsv').read_bytes(), 'Six after-root state differs')
        paths.append(path)
    applied = (output / 'applied.el').read_bytes()
    for name in ('reloaded.el', 'after-root.el'):
        path = output / name
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == applied, 'Combined roundtrip bytes differ')
        bind(path.read_bytes(), config)
        paths.append(path)
    path = output / 'session-final-empty.el'
    require(path.is_file() and not path.is_symlink() and path.read_bytes() == b'', 'Session final reset not empty')
    paths.append(path)
    for marker in ('SEVEN_RUNTIME_INSTALLED', 'SEVEN_ACTUAL_RELOAD_EXACT5868', 'SEVEN_DONE_EXACT5868'):
        require(log.splitlines().count(marker) == 1, 'Missing exact seven completion')
    result.update(status='HISTORICAL_POPULATION_SEVEN_POLICY_REPORT_NOT_FINAL_APPROVAL',
                  records=5868, protected=17702, audited=23570, state_checks=23570 * len(STAGES),
                  tests=config['population'], application_approval=False, official_denominator_verified=False,
                  admission_manifest_sha256=runtime['admission_sha256'], actual_combined_reload_verified=True,
                  source_padding_x0_contract_accepted=True, native_X_semantics_measured=False,
                  four_state_initialization_qualified=False, branch_hold=60, op16='HOLD',
                  historical_percentages_inherited=False)
    result['files'].update({str(p): frozen.sha(p) for p in paths})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--six-output', type=Path)
    parser.add_argument('--six-seal')
    parser.add_argument('--seven-output', type=Path)
    parser.add_argument('--seven-seal')
    parser.add_argument('--seal')
    parser.add_argument('--accept-padding-x0-contract', action='store_true')
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == frozen.OUT and output.resolve() == output, 'Direct output required')
    if args.mode == 'prepare':
        require(args.six_output and args.six_seal and args.seven_output and args.seven_seal and not args.seal, 'Sealed preparation inputs required')
        prepare(output, args.six_output.absolute(), args.six_seal, args.seven_output.absolute(), args.seven_seal,
                args.accept_padding_x0_contract)
        print(json.dumps(dict(status='PREPARED_NO_DVE', seal=frozen.sha(output / 'runtime-plan.json'))))
    else:
        require(args.seal and not any((args.six_output, args.six_seal, args.seven_output, args.seven_seal,
                                      args.accept_padding_x0_contract)), 'Only sealed output accepted')
        result = verify(output, args.seal) if args.mode == 'verify' else dict(status='CHECKED_NO_DVE', population=read_config(output, args.seal)[1]['population'])
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
