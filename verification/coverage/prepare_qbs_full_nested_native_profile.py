"""Full1344-group/two-bank discovery profile; no application or automatic launch."""
import argparse
import json
from pathlib import Path
import re
import tkinter

import prepare_qbs_nested224_tree_profile as two

f = two.f
HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TEST = HERE/'test_qbs_full_nested_native_profile.py'
BODY = HERE/'qbs_full_nested_native_body.tcl'
TCL = HERE/'qbs_full_nested_native_session.tcl'
CAPTURE = f.proof.OUT/'qbs-nested224-tree-profile-parent-20261006-01'
CAPTURE_SEAL = 'ba5d7c05673dd581b0e1d027b72e7e2dd65823fa47018237fe909203679e0d0e'
BASE_WRITE = f.write


def reviewed_capture():
    path = CAPTURE/'discovery-plan.json'
    f.require(f.sha(path) == CAPTURE_SEAL, 'Parent two-tree capture seal differs')
    plan = json.loads(path.read_bytes())
    status = json.loads((CAPTURE/'capture-status.json').read_bytes())
    f.check_pins(plan['pins']); f.check_pins(status['artifacts'])
    actual = two.inspect_rows((CAPTURE/'native-rows.tcllist').read_bytes(), {})
    f.require(status['status'] == actual['status'] and status['returncode'] == 0 and
              status['observations'] == actual['observations'] and
              all(o['relation'] == 'Historical path/meta shape observed' for o in actual['observations']),
              'Actual parent tree relation differs')
    f.require(json.loads((CAPTURE/'actual-executable.json').read_bytes())['executable_verified'], 'Actual DVE identity missing')
    pins = dict(plan['pins']); pins.update(status['artifacts'])
    pins[str(CAPTURE/'capture-status.json')] = f.sha(CAPTURE/'capture-status.json')
    return dict(status='INDEPENDENT_READ_ONLY_TWO_PARENT_ARTIFACTS_VERIFIED', pins=pins,
        provenance='PARENT_AGENT_INDEPENDENT_EXECUTION', capture_seal=CAPTURE_SEAL,
        observations=actual['observations'], not_full1792_qualification=True)


def groups(artifact):
    result = []
    for g in artifact['native_groups']:
        parent = ''
        if g['expression'].startswith(('(weight_valid_i[0]', '(activation_valid_i[0]')):
            matches = [p for p in artifact['native_groups'] if p['scope'] == g['scope'] and
                p['generate_info'] == g['generate_info'] and p['expression'].endswith(' || '+g['expression']+')')]
            f.require(len(matches) == 1, 'Unique expected parent missing')
            parent = matches[0]['expression']
        result.append(dict(scope=g['scope'], expression=g['expression'], parent=parent,
                           names=g['names'], targets=g['targets'], retained=g['retained']))
    f.require(len(result) == len({(g['scope'], g['expression']) for g in result}) == 1344 and
        sum(bool(g['parent']) for g in result) == 448 and sum(len(g['targets']) for g in result) == 1792 and
        sum(len(g['retained']) for g in result) == 1792, 'Full exact group/protection population differs')
    return result


def selection(artifact, database, test):
    two.serializer.OLD_SELECTION(artifact, database, test)
    rows = groups(artifact); word = f.tcl_word
    lines = ['set qsd_design '+word(f.proof.DESIGN), 'set qsd_testdir '+word(database),
             'set qsd_test '+word(test), 'set qbf_scopes {}']
    for scope in sorted(artifact['scope_protection']):
        lines.append('set qbf_groups {}')
        bank = [g for g in rows if g['scope'] == scope]
        f.require(len(bank) == 672 and sum(bool(g['parent']) for g in bank) == 224, 'Per-bank population differs')
        for g in bank:
            lines.append('lappend qbf_groups [list '+word(g['expression'])+' '+word(g['parent'])+
                         ' [list '+' '.join(map(word, g['names']))+']]')
        lines.append('lappend qbf_scopes [list '+word(scope)+' $qbf_groups]')
    text = '\n'.join(lines)+'\n'
    t = tkinter.Tcl(); t.tk.wantobjects(False); t.eval(text)
    actual = []
    for bank in t.splitlist(t.getvar('qbf_scopes')):
        scope, raw = t.splitlist(bank)
        for row in t.splitlist(raw):
            expression, parent, names = t.splitlist(row)
            actual.append((scope, expression, parent, list(t.splitlist(names))))
    f.require(actual == [(g['scope'], g['expression'], g['parent'], g['names']) for g in rows],
              'Host full selection execution differs')
    return text


def safe_tcl(text):
    joined = text+'\n'+BODY.read_text()
    code = '\n'.join(l for l in joined.splitlines() if not l.lstrip().startswith('#'))
    expected = {'gui_list_get', 'gui_list_get_selected', 'gui_list_select', 'gui_cov_show_cond_ids',
                'gui_list_action', 'gui_covdetail_query', 'gui_list_expand', 'gui_open_cov', 'gui_exit'}
    f.require(set(re.findall(r'\bgui_\w+', code)) == expected and not re.search(
        r'\b(exec|eval|uplevel|after|lassign|dict|lmap|try|apply)\b|\-columns|\-text|\.el\b|\{\*\}', code),
        'Unsafe/nonlegacy full discovery API')
    f.require(text.count('source ') == 2 and 'source {'+str(BODY)+'}' in text and
        'source $env(QBS_SIDE1792_SELECTION)' in text and '-select [list $meta]' in code,
        'Pinned body/input and observed meta only')


def write(path, value):
    if path.name == 'discovery-plan.json':
        verified = reviewed_capture()
        value['pins'].update(verified['pins'])
        for p in (SCRIPT, TEST, BODY, two.SCRIPT, two.TEST, two.TCL, two.PROBE):
            value['pins'][str(p)] = f.sha(p)
        value['schema'] = 'QBS_FULL_NESTED_NATIVE_PROFILE_V1'
        value['reviewed_two_parent_capture'] = verified
        value['full_group_profile'] = dict(banks=2, groups=1344, nested_per_bank=224,
            root_bound=8192, subtree_bound=128, max_depth=8, source_qualification_baseline=732,
            no_separate_two_parent_repeat=True, old_handles_not_reused_in_new_session=True,
            prior_two_groups_need_current_session_vectors_and_display=True,
            actual_bank1_nested_shape_not_yet_verified=True)
        value['identity_policy'] = 'Observe actual handle/path/meta, select captured meta only, verify complete actual vectors; capture per-selected-object ID-display raw bytes without interpreting IDs/order. Numeric signatures/protection remain HOLD.'
        value['protections'] = 'No columns/exclusion/reset/import/saveEL. Exact2 banks/1344 groups; all1792 candidates,1792 neighbors and41214 complement pinned. Read-only discovery cannot authorize exclusions.'
    BASE_WRITE(path, value)


def inspect_rows(raw, artifact):
    f.require(0 < len(raw) <= 32*1024*1024 and raw.endswith(b'\n') and b'\x00' not in raw, 'Incomplete/bounded full capture')
    text = raw.decode('ascii')
    t = tkinter.Tcl(); t.tk.wantobjects(False)
    t.eval('set qbf_test_only 1'); t.eval(BODY.read_text())
    expected = {(g['scope'], g['expression']): g for g in groups(artifact)}
    scopes = set(artifact['scope_protection'])
    inventories, objects, observed, completed, handles = set(), {}, set(), set(), set()
    terminal = False; pending = None
    for line in text.splitlines():
        f.require(not terminal, 'Data after full terminal')
        row = t.splitlist(line); f.require(row, 'Empty full native record')
        if row[0] == 'inventory':
            f.require(len(row) == 4 and row[1] in scopes and row[1] not in inventories and
                      0 < int(row[2]) <= 8192 and pending is None, 'Invalid native inventory')
            names = [t.call('qbf_name', x) for x in t.splitlist(row[3])]
            f.require(0 < len(names) <= 21503 and len(names) == len(set(names)), 'Actual inventory ambiguity/bound')
            inventories.add(row[1])
        elif row[0] == 'object':
            f.require(len(row) == 7 and pending is None, 'Object shape/order differs')
            key = row[1], row[2]
            f.require(key in expected and key not in objects and row[1] in inventories and
                      row[3] == expected[key]['parent'] and row[4] not in ('', '0') and
                      (row[1], row[4]) not in handles, 'Foreign/duplicate actual object')
            if row[3]:
                f.require(row[5] == row[3]+'.'+row[2] and row[6] == row[3]+'  .'+row[2], 'Actual child relation differs')
            else:
                f.require(row[5] == row[6] == row[2], 'Actual root relation differs')
            objects[key] = row; handles.add((row[1], row[4])); pending = key
        elif row[0] == 'group':
            f.require(len(row) == 11 and (row[1], row[2]) == pending, 'Group/order differs')
            key = pending; obj = objects[key]
            f.require(row[:7] == ('group',)+obj[1:] and t.call('qbf_name', row[7]) == obj[6], 'Selected actual object drift')
            names = [t.call('qbf_name', x) for x in t.splitlist(row[8])]
            f.require(sorted(names) == sorted(expected[key]['names']), 'Actual truth table drift')
            f.require(row[9] != '' and row[10] != '', 'Missing actual IDs-display data')
            observed.add(key); pending = None
        elif row[0] == 'scope_complete':
            f.require(row[1] in scopes and row[1] not in completed and pending is None and
                      row == ('scope_complete', row[1], '672', '224') and
                      sum(k[0] == row[1] for k in observed) == 672, 'Scope incomplete')
            completed.add(row[1])
        else:
            f.require(row == ('complete', '1344', '448', 'FULL1792_NATIVE_HOLD'), 'Unexpected/qualified full terminal')
            terminal = True
    f.require(terminal and pending is None and set(objects) == observed == set(expected) and completed == inventories == scopes,
              'Incomplete full native mapping')
    return dict(status='FULL1344_TREE_VECTORS_DISPLAY_CAPTURED_SIGNATURE_PROTECTION_HOLD',
        groups=1344, nested_groups=448, actual_vectors=3584, target_count=1792, protected_condition_count=41214,
        native_qualified=False, numeric_signature_bound=False, full_protection_qualified=False)


def configure():
    f.TCL = TCL; f.selection = selection; f.safe_tcl = safe_tcl
    f.write = write; f.inspect_rows = inspect_rows


def verify(output, seal):
    plan = f.verify(output, seal)
    f.require(plan['schema'] == 'QBS_FULL_NESTED_NATIVE_PROFILE_V1' and
        plan['reviewed_two_parent_capture'] == reviewed_capture() and
        plan['pins'].get(str(SCRIPT)) == f.sha(SCRIPT) and plan['pins'].get(str(TEST)) == f.sha(TEST),
        'Full profile/capture binding differs')
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify', 'capture-readonly'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--authorization', type=Path)
    args = parser.parse_args(); configure(); safe_tcl(TCL.read_text()); output = args.output.absolute()
    if args.command == 'prepare':
        f.prepare(output)
    elif args.command == 'verify':
        verify(output, args.seal)
    else:
        f.require(args.authorization is not None, 'Parent receipt required')
        verify(output, args.seal); f.capture(output, args.seal, args.authorization.absolute())


if __name__ == '__main__':
    main()
