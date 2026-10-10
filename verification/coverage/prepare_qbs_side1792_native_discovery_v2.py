"""Selection serializer successor: execute all generated Tcl on host before EDA."""
import argparse
import json
from pathlib import Path
import tkinter

import prepare_qbs_side1792_native_discovery as frozen

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_qbs_side1792_native_discovery_v2.py')
OLD_SELECTION = frozen.selection
OLD_WRITE = frozen.write
FAILED = frozen.proof.OUT / 'qbs-side1792-native-discovery-parent-20261006-01'


def failure_evidence():
    plan_path = FAILED/'discovery-plan.json'
    frozen.require(frozen.sha(plan_path) == 'f84487e23126c677e1d40d986ea1f2a8e0ce4c8a739d8b47163bfd8519c8ad86',
                   'Original parent plan seal differs')
    status = json.loads((FAILED/'capture-status.json').read_bytes())
    log = (FAILED/'DVEfiles/dve_gui.log').read_text()
    frozen.require('invalid command name "{(activation_valid_i[0]' in log and
                   'qsd_scopes": no such variable' in log and
                   (FAILED/'native-rows.tcllist').read_bytes() == b'' and
                   status['status'] == 'HOLD' and status['returncode'] == 0,
                   'Observed original failure differs')
    pins = {str(FAILED/'capture-status.json'): frozen.sha(FAILED/'capture-status.json')}
    for rel in ('discovery-plan.json', 'selection.tcl', 'DVEfiles/dve_gui.log',
                'native-rows.tcllist', 'actual-executable.json'):
        path = FAILED/rel
        frozen.require(status['artifacts'][str(path)] == frozen.sha(path), 'Original failure artifact drift')
        pins[str(path)] = frozen.sha(path)
    return dict(status='READ_ONLY_GENERATED_SELECTION_SYNTAX_ROOT_CONFIRMED', pins=pins,
        original_directory=str(FAILED), terminal='HOLD', returncode=0,
        cause='Nested multiline list command substitutions lack Tcl continuation: group list becomes a command; source abort leaves qsd_scopes unset.',
        stage='Before gui_open_cov and before any native Condition query',
        DVE_API_or_license_failure=False, native_evidence_rows=0, native_qualified=False)


def validate_generated(text, artifact, database, test):
    interp = tkinter.Tcl()
    interp.tk.wantobjects(False)
    # Execute our generated input only, never captured DVE output.
    interp.eval(text)
    require = frozen.require
    require(interp.getvar('qsd_design') == str(frozen.proof.DESIGN) and
            interp.getvar('qsd_testdir') == str(database) and interp.getvar('qsd_test') == test,
            'Evaluated selection input differs')
    scopes = interp.splitlist(interp.getvar('qsd_scopes'))
    expected_scopes = sorted(artifact['scope_protection'])
    require(len(scopes) == len(expected_scopes) == 2, 'Evaluated scope population differs')
    count = 0
    for raw, scope in zip(scopes, expected_scopes):
        pair = interp.splitlist(raw)
        require(len(pair) == 2 and pair[0] == scope, 'Evaluated scope identity differs')
        groups = interp.splitlist(pair[1])
        expected = [g for g in artifact['native_groups'] if g['scope'] == scope]
        require(len(groups) == len(expected) == 672, 'Evaluated group population differs')
        for group, reference in zip(groups, expected):
            fields = interp.splitlist(group)
            require(len(fields) == 2 and fields[0] == reference['expression'] and
                    list(interp.splitlist(fields[1])) == reference['names'],
                    'Evaluated expression/vector names differ')
            count += 1
    require(count == 1344, 'Incomplete evaluated group population')
    return dict(status='HOST_GENERATED_SELECTION_EXECUTION_PASS_NOT_NATIVE_EVIDENCE',
                scopes=2, groups=count, vectors=3584, native_qualified=False)


def selection(artifact, database, test):
    OLD_SELECTION(artifact, database, test)  # Retain every frozen population/word gate.
    word = frozen.tcl_word
    lines = ['set qsd_design '+word(frozen.proof.DESIGN),
             'set qsd_testdir '+word(database), 'set qsd_test '+word(test), 'set qsd_scopes {}']
    for scope in sorted(artifact['scope_protection']):
        lines.append('set qsd_groups {}')
        for g in artifact['native_groups']:
            if g['scope'] == scope:
                lines.append('lappend qsd_groups [list '+word(g['expression'])+
                             ' [list '+' '.join(map(word, g['names']))+']]')
        lines.append('lappend qsd_scopes [list '+word(scope)+' $qsd_groups]')
    text = '\n'.join(lines)+'\n'
    validate_generated(text, artifact, database, test)
    return text


def write(path, value):
    if path.name == 'discovery-plan.json':
        value['pins'][str(SCRIPT)] = frozen.sha(SCRIPT)
        value['pins'][str(TEST)] = frozen.sha(TEST)
        diagnostic = failure_evidence()
        value['pins'].update(diagnostic['pins'])
        value['original_failure_diagnosis'] = diagnostic
        artifact = json.loads(Path(value['proof']).read_bytes())
        value['selection_host_execution'] = validate_generated(
            (path.parent/'selection.tcl').read_text(), artifact,
            Path(value['sample_database']), value['sample_test'])
        value['successor_reason'] = 'Observed Tcl newline command boundary in original selection; no DVE API/license failure. Frozen GUI capture body unchanged.'
        value['schema'] = 'QBS_SIDE1792_NATIVE_DISCOVERY_V2'
    OLD_WRITE(path, value)


def configure():
    frozen.selection = selection
    frozen.write = write


def verify(output, seal):
    plan = frozen.verify(output, seal)
    frozen.require(plan['schema'] == 'QBS_SIDE1792_NATIVE_DISCOVERY_V2' and
                   plan['pins'].get(str(SCRIPT)) == frozen.sha(SCRIPT) and
                   plan['pins'].get(str(TEST)) == frozen.sha(TEST), 'Successor binding differs')
    artifact = json.loads(Path(plan['proof']).read_bytes())
    actual = validate_generated((output/'selection.tcl').read_text(), artifact,
                               Path(plan['sample_database']), plan['sample_test'])
    frozen.require(plan['selection_host_execution'] == actual, 'Host execution evidence differs')
    frozen.require(plan['original_failure_diagnosis'] == failure_evidence(), 'Original failure diagnosis drift')
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify', 'capture-readonly'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--authorization', type=Path)
    args = parser.parse_args()
    configure()
    output = args.output.absolute()
    if args.command == 'prepare':
        frozen.prepare(output)
    elif args.command == 'verify':
        verify(output, args.seal)
    else:
        frozen.require(args.authorization is not None, 'Parent authorization required before launch')
        verify(output, args.seal)
        frozen.capture(output, args.seal, args.authorization.absolute())


if __name__ == '__main__':
    main()
