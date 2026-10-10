"""Two-parent read-only profile of the sealed capture platform; parent launch only."""
import argparse
import json
from pathlib import Path
import re
import tkinter

import prepare_qbs_side1792_native_discovery_v2 as serializer
import review_qbs_nested224_api as study

f = serializer.frozen
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_qbs_nested224_tree_profile.py')
TCL = SCRIPT.with_name('qbs_nested224_tree_session.tcl')
PROBE = study.TCL
STUDY = f.proof.OUT/'qbs-nested224-api-study-agent-20261006-01/review.json'
STUDY_SEAL = 'b8debf69472e81cde14b876e6d2d118342e625ebcbd9af675d21678422cc6f2c'
BASE_WRITE = f.write


def profile():
    f.require(f.sha(STUDY) == STUDY_SEAL, 'Reviewed identity study seal differs')
    record = json.loads(STUDY.read_bytes())
    f.check_pins(record['pins'])
    result = record['proposed_probe']
    f.require(result['parent_count'] == 2 and not record['native_qualified'] and
              record['target_count'] == 1792 and record['protected_condition_count'] == 41214,
              'Exact limited study required')
    return result


def selection(artifact, database, test):
    serializer.OLD_SELECTION(artifact, database, test)  # Preserve full proof population gates.
    p = profile(); word = f.tcl_word
    text = '\n'.join(('set qsd_design '+word(f.proof.DESIGN), 'set qsd_testdir '+word(database),
        'set qsd_test '+word(test), 'set qnt_scope '+word(p['scope']),
        'set qnt_parents [list '+' '.join(word(x['parent_expression']) for x in p['examples'])+']'))+'\n'
    interp = tkinter.Tcl(); interp.tk.wantobjects(False); interp.eval(text)
    f.require(interp.getvar('qnt_scope') == p['scope'] and
        list(interp.splitlist(interp.getvar('qnt_parents'))) == [x['parent_expression'] for x in p['examples']],
        'Actual evaluated two-parent input differs')
    return text


def safe_tcl(text):
    body = PROBE.read_text()
    joined = text+'\n'+body
    expected_GUI = {'gui_list_get', 'gui_list_action', 'gui_covdetail_query', 'gui_list_expand',
                    'gui_cov_show_cond_ids', 'gui_open_cov', 'gui_exit'}
    f.require(set(re.findall(r'\bgui_\w+', joined)) == expected_GUI, 'Profile GUI API drift')
    code = '\n'.join(line for line in joined.splitlines() if not line.lstrip().startswith('#'))
    f.require(not re.search(r'\b(exec|eval|uplevel|after|lassign|dict)\b|\-columns|\-text|\.el\b|\{\*\}', code),
              'Nonlegacy/unsafe profile query')
    f.require(text.count('source ') == 2 and 'source {'+str(PROBE)+'}' in text and
              'source $env(QBS_SIDE1792_SELECTION)' in text, 'Only pinned body and generated selection allowed')
    f.require(body.count('gui_list_action ') == 1 and 'Exact observed bank0 scope required' in body,
              'Exact scope/view protection differs')


def write(path, value):
    if path.name == 'discovery-plan.json':
        record = json.loads(STUDY.read_bytes())
        value['pins'].update(record['pins'])
        for p in (STUDY, PROBE, SCRIPT, TEST, serializer.SCRIPT, serializer.TEST):
            value['pins'][str(p)] = f.sha(p)
        value['schema'] = 'QBS_NESTED224_TWO_PARENT_PROFILE_V1'
        value['profile'] = profile()
        value['identity_policy'] = 'Only actual returned GUI tree handles/path/meta; no XML ID mapping or constructed child selector. Two-parent observation is not full1792 qualification.'
        value['protections'] = 'Bank0 Condition tree view only; no item selection, columns, exclusion/reset/import/saveEL. Full1792/41214 protection remains HOLD.'
        value['hypothesis'] = 'Nested conjunction is a child coverage object under actually enumerated OR parent, not a bare top-level condition name. Missing/ambiguous child remains HOLD, never substitute parent.'
        value['actual_API_success_evidence'] = dict(tree=str(study.TREE), log=str(study.TREE_LOG),
            help=str(study.HELP), successful_script=str(study.SUCCESS_SCRIPT),
            prior_native_tree_rows=36, applies_directly_to_QBS_children=False)
    BASE_WRITE(path, value)


def inspect_rows(raw, artifact):
    f.require(0 < len(raw) <= 1024*1024 and raw.endswith(b'\n') and b'\x00' not in raw, 'Incomplete/bounded tree capture')
    text = raw.decode('ascii')
    interp = tkinter.Tcl(); interp.tk.wantobjects(False)
    p = profile(); expected = p['examples']
    parents, nodes, seen = [], [], set()
    complete = False
    for line in text.splitlines():
        f.require(not complete, 'Records after terminal')
        row = interp.splitlist(line)
        f.require(row, 'Empty tree row')
        if row[0] == 'parent':
            f.require(len(row) == 4 and row[2] not in ('', '0') and len(parents) < 2 and
                      row[1] == expected[len(parents)]['parent_expression'], 'Wrong/extra actual parent')
            parents.append(row); nodes.append([])
        elif row[0] == 'child':
            f.require(len(row) == 6 and parents and row[2] not in ('', '0') and row[2] not in seen, 'Invalid/duplicate child handle')
            depth, count = int(row[1]), int(row[5])
            f.require(0 <= depth <= 8 and 0 <= count <= 128 and len(nodes[-1]) < 128, 'Tree bound differs')
            if not nodes[-1]:
                f.require(depth == 0 and row[2] == parents[-1][2] and row[3] == parents[-1][3] and row[4] == parents[-1][1],
                          'Actual root path/meta differs')
            else:
                f.require(0 < depth <= int(nodes[-1][-1][1])+1, 'Invalid child depth sequence')
            seen.add(row[2]); nodes[-1].append(row)
        else:
            f.require(row == ('diagnostic_complete', 'NATIVE_IDENTITY_HOLD'), 'Unexpected/qualified tree terminal')
            complete = True
    f.require(complete and len(parents) == 2 and all(len(n) > 1 for n in nodes), 'Incomplete two-parent tree')
    observations = []
    for example, root, rows in zip(expected, parents, nodes):
        for i, row in enumerate(rows):
            depth = int(row[1]); direct = 0
            for other in rows[i+1:]:
                if int(other[1]) <= depth:
                    break
                direct += int(int(other[1]) == depth+1)
            f.require(direct == int(row[5]), 'Actual childCount/traversal differs')
        child = example['child_expression']
        matches = [r for r in rows[1:] if r[3] == root[3]+'.'+child and r[4] == root[1]+'  .'+child]
        observations.append(dict(parent=root[1], actual_parent_handle=root[2],
            expected_child=child, matching_observed_handles=[r[2] for r in matches],
            relation='Historical path/meta shape observed' if len(matches) == 1 else 'HOLD_OTHER_OR_AMBIGUOUS_SHAPE'))
    return dict(status='TWO_PARENT_TREE_CAPTURED_FULL1792_NATIVE_HOLD', native_qualified=False,
                observations=observations, captured_nodes=len(seen), target_count=1792,
                protected_condition_count=41214)


def configure():
    f.TCL = TCL
    f.selection = selection
    f.safe_tcl = safe_tcl
    f.write = write
    f.inspect_rows = inspect_rows


def verify(output, seal):
    plan = f.verify(output, seal)
    f.require(plan['schema'] == 'QBS_NESTED224_TWO_PARENT_PROFILE_V1' and plan['profile'] == profile() and
              plan['pins'].get(str(SCRIPT)) == f.sha(SCRIPT) and plan['pins'].get(str(TEST)) == f.sha(TEST),
              'Profile binding differs')
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify', 'capture-readonly'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--authorization', type=Path)
    args = parser.parse_args(); configure(); safe_tcl(TCL.read_text())
    output = args.output.absolute()
    if args.command == 'prepare':
        f.prepare(output)
    elif args.command == 'verify':
        verify(output, args.seal)
    else:
        f.require(args.authorization is not None, 'Parent receipt required')
        verify(output, args.seal)
        f.capture(output, args.seal, args.authorization.absolute())


if __name__ == '__main__':
    main()
