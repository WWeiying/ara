"""Exact14 native singleton successor; preparation and offline gates, no EDA launch."""
import argparse
import json
import re
import sys
from pathlib import Path
from types import FunctionType

sys.dont_write_bytecode = True
import prove_alub_lane0_reduction_zero_731 as static

native = static.native
capture = native.capture
require, sha = static.require, native.sha
HERE, OUT = native.HERE, native.OUT
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = HERE / 'test_prepare_alub_lane0_native14_731.py'
ADAPTER = HERE / 'alub_lane0_native14_731.selection.tcl'
ARTIFACT = OUT / 'alub-lane0-static14-731-parent-20261006-01/candidate.json'
ARTIFACT_SEAL = '81eb26c1cb540374af0324377f5a1bc36e298a6f265f4db4078198c2c051c71c'
NATIVE_FIXTURE = OUT / 'branch-combo-six-policy-population-729-agent-20261006-01/combined.el'
NATIVE_FIXTURE_SHA = '3e2345b2bc906413c1baf65dd912a15faa70d55276e7c0cd772585a591bbca7f'
HELP = OUT / 'dcache-read-port2-native-inventory-714-20261006-03/DVEfiles/dve_gui.log'
HELP_SHA = '0684e69dc06cdcd940c6820a1b9d31aa4e6c6eb3fa2d06e8c30194987385692e'
ANNOTATION = 'ALUB lane0 static14 native singleton qualification only; not application approval'
SCHEMA = 'ALUB_LANE0_NATIVE14_731_V1'


def private(function, **bindings):
    namespace = dict(function.__globals__, **bindings)
    return FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)


def signatures(raw):
    """Extract observed native text, never synthesize it from compiled bit vectors."""
    rows = {}
    for line in raw.decode('ascii').splitlines():
        match = re.fullmatch(r'Branch 5 "718333796" "cmd.conv" \((2[4-8])\) "(.*)"', line)
        if match:
            key, text = match.groups()
            require(text.startswith('cmd.conv OpQueueReductionZExt '), 'Wrong observed branch semantics')
            require(key not in rows or rows[key] == text, 'Conflicting historical native signature')
            rows[key] = text
    require(set(rows) == {'24', '25', '26', '27', '28'}, 'Missing observed signatures')
    return rows


def population(plan):
    counts = {m: sum(r['target'] for metrics in plan['scopes'].values() for r in metrics[m])
              for m in ('line', 'branch')}
    require(len(plan['scopes']) == 8 and counts == {'line': 9, 'branch': 5}, 'Not exact14 population')
    for scope, metrics in plan['scopes'].items():
        require(set(metrics) == {'line', 'branch'}, 'Unsupported metric')
        require(re.fullmatch(r'ara_tb\.dut\.i_ara_soc\.i_system\.i_ara\.gen_lanes\[[0-3]\]'
                            r'\.i_lane\.i_operand_queues\.i_operand_queue_alu_[ab]', scope), 'Wrong protected scope')
        for metric, rows in metrics.items():
            require(len(rows) == (177 if metric == 'line' else 101), 'Compiled object inventory differs')
            require(len({r['coordinate'] for r in rows}) == len(rows), 'Duplicate coordinate')
            for row in rows:
                point = row['point']
                require(row['coordinate'] == native.coordinate(point, metric), 'Coordinate differs')
                wanted = scope.endswith('gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_alu_b') and (
                    point['raw_index'] in (static.LINE_TARGETS if metric == 'line' else static.BRANCH_TARGETS))
                require(row['target'] is wanted, 'Target/protection differs')
    return counts


def bind_native(raw, config):
    entries = private(native.bind_native, ANNOTATION=ANNOTATION)(raw, config)
    expected = {(s, 'Block ' + r['point']['native_id'] if m == 'line' else
                 'Branch %s (%s)' % (r['point']['native_id'], r['point']['vector'])): (m, r['point'])
                for s, metrics in config['plan']['scopes'].items() for m, rows in metrics.items()
                for r in rows if r['target']}
    for entry in entries:
        metric, point = expected[entry['scope'], entry['point']]
        if metric == 'line':
            match = re.fullmatch(r'Block [0-9]+ "([0-9]+)" ".*"', entry['native_directive'])
            require(match[1] == point['attributes']['chksum'], 'Native Block point checksum differs')
        else:
            require(entry['native_signature'] == config['observed_branch_signatures'][point['vector']],
                    'Native branch full signature differs')
    return entries


def audit_states(path, config, stage, previous=None):
    got = native.audit_states(path, config, stage, previous)
    for (_, metric, key), (meta, path_value) in got.items():
        if metric == 'line':
            require(meta == 'Block' + key and re.fullmatch(r'(?:.*\.)?' + re.escape(meta), path_value),
                    'Not an actual Block leaf identity')
        else:
            sid, vid = key.split(',')
            require(meta in ('Branch' + sid + '.' + vid, 'MISSING_ELSE' + sid + '.' + vid),
                    'Not an actual branch leaf identity')
            require(path_value == 'Item' + sid + '.' + meta, 'Actual branch path differs')
    return got


def verify_artifacts(output, config):
    result = private(native.verify_artifacts, bind_native=bind_native, audit_states=audit_states,
                     SAMPLE=Path(config['plan']['selected_test_vdb']))(output, config)
    require(result['records'] == 14 and result['protected'] == {'line': 1407, 'branch': 803},
            'Unexpected qualification population')
    result.update(status='ALUB_LANE0_NATIVE14_ROUNDTRIP_QUALIFIED_NOT_APPLIED',
                  static_artifact_sha256=ARTIFACT_SEAL, protected_points=2210,
                  historical_signature_fixture_is_current_scope_evidence=False,
                  aggregate_application=False, waiver_approval=False)
    return result


def config_read(output, seal):
    require(re.fullmatch(r'[a-f0-9]{64}', seal or '') and sha(output / 'config.json') == seal, 'External seal differs')
    config = json.loads((output / 'config.json').read_bytes())
    require(config['schema'] == SCHEMA and config['output'] == str(output), 'Wrong config')
    require(config['static_artifact_sha256'] == ARTIFACT_SEAL and config['launch_supported'] is False and
            config['application_approval'] is False, 'Wrong preparation authority')
    capture.check_inputs(config)
    population(config['plan'])
    require(config['observed_branch_signatures'] == signatures(NATIVE_FIXTURE.read_bytes()), 'Fixture differs')
    return config


def prepare(output):
    require(output.parent.resolve() == OUT.resolve() and not output.exists(), 'Fresh direct out required')
    require(sha(ARTIFACT) == ARTIFACT_SEAL, 'Static artifact differs')
    artifact = json.loads(ARTIFACT.read_bytes())
    require(artifact['status'] == static.STATUS and artifact['candidate_count'] == 14 and
            artifact['protected_count'] == 2210 and artifact['baseline_seal'] == static.BASE_SEAL and
            artifact['native_qualified'] is False and artifact['exclusions_applied'] is False,
            'Static authority differs')
    pins = dict(artifact['pins'])
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), 'Missing/aliased input')
        digest = sha(path)
        require(expected is None or digest == expected, 'Pin differs: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == digest, 'Pin collision')
        pins[str(path)] = digest
    for path, expected in list(pins.items()):
        pin(path, expected)
    pin(ARTIFACT, ARTIFACT_SEAL)
    pin(NATIVE_FIXTURE, NATIVE_FIXTURE_SHA)
    pin(HELP, HELP_SHA)
    plan = dict(artifact['plan'])
    targets = population(plan)
    members = (Path(artifact['baseline']) / 'combined-inputs.txt').read_text().splitlines()
    require(len(members) == len(set(members)) == 732, 'Not exact731 membership')
    sample = Path(members[1])
    require(sample.is_dir() and not sample.is_symlink(), 'Missing historical sample')
    plan.update(design_vdb=members[0], selected_test_vdb=str(sample),
                input_membership={str(sample): capture.proof.tree_members(sample)},
                tool_identity=native.tool.prepare('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve',
                                                  '/usr/bin/xvfb-run'))
    for path in sample.rglob('*'):
        if path.is_file():
            pin(path)
    for path in (SCRIPT, TEST, TCL, ADAPTER, native.TCL, Path(capture.__file__),
                 Path(capture.proof.__file__), Path(native.tool.__file__)):
        pin(path)
    text = native.selection(plan)
    text = text.replace(capture.literal(str(Path(native.__file__).resolve())), capture.literal(str(SCRIPT)))
    text += ('set dbg_library_only 1\nsource ' + capture.literal(str(native.TCL)) +
             '\nsource ' + capture.literal(str(ADAPTER)) + '\n')
    output.mkdir()
    (output / 'selection.tcl').write_text(text)
    pin(output / 'selection.tcl')
    config = dict(schema=SCHEMA, output=str(output), pins=pins, plan=plan, targets=targets,
                  protected={'line': 1407, 'branch': 803}, static_artifact_sha256=ARTIFACT_SEAL,
                  observed_branch_signatures=signatures(NATIVE_FIXTURE.read_bytes()),
                  historical_signature_fixture_is_current_scope_evidence=False,
                  launch_supported=False, capture_only=True, application_approval=False,
                  native_status='HOLD_NOT_CAPTURED',
                  line_leaf_probe='Category Block readonly action is a candidate; no actual API-value proof yet; HOLD unless 177 exact Block leaves per scope',
                  stages=list(native.STAGES), other_metrics='Condition/FSM/Toggle untouched; exact EL rejects all extra records',
                  command=native.tool.launch_command(plan['tool_identity'], TCL))
    capture.check_inputs(config)
    native.write(output / 'config.json', config)
    seal = sha(output / 'config.json')
    native.write(output / 'status.json', dict(status='PREPARED_NO_DVE_NATIVE_HOLD', config_sha256=seal,
                  targets=targets, protected_points=2210, application_approval=False))
    print('PREPARED_NO_DVE config_sha256=' + seal)
    return seal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'check', 'first', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent.resolve() == OUT.resolve() and not output.is_symlink(), 'Unsafe output')
    if args.command == 'prepare':
        prepare(output)
        return
    config = config_read(output, args.seal)
    if args.command == 'check':
        print('CHECK_PASS_NO_DVE_NATIVE_HOLD')
    elif args.command == 'first':
        before = audit_states(output / 'states_before.tsv', config, 'before')
        audit_states(output / 'states_selected.tsv', config, 'selected', before)
        require((output / 'initial-empty.el').read_bytes() == b'', 'Initial reset differs')
        print('DBG_FIRST_EXACT ' + str(len(bind_native((output / 'first.el').read_bytes(), config))))
    else:
        print(json.dumps(verify_artifacts(output, config), indent=2))


if __name__ == '__main__':
    main()
