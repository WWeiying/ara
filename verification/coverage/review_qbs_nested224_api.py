"""Read-only actual inventory/legacy tree API review; no EDA entry."""
import argparse
import csv
import json
from pathlib import Path
import tkinter

import prepare_qbs_side1792_native_discovery_v3 as v3

f = v3.frozen
HERE = Path(__file__).resolve().parent
TCL = HERE/'qbs_nested224_tree_probe.tcl'
TEST = HERE/'test_review_qbs_nested224_api.py'
TREE = f.proof.OUT/'lzc-native-discovery-20261006-01/native-condition-tree.csv'
TREE_LOG = TREE.parent/'DVEfiles/dve_gui.log'
HELP = f.proof.OUT/'lzc-native-api-20261006-02/DVEfiles/dve_gui.log'
SUCCESS_SCRIPT = HERE/'discover_lzc_condition.tcl'


def pairs(artifact, scope, actual_names):
    groups = [g for g in artifact['native_groups'] if g['scope'] == scope]
    missing = [g for g in groups if g['expression'] not in actual_names]
    result = []
    for child in missing:
        parent = [g for g in groups if g['expression'] in actual_names and
                  g['generate_info'] == child['generate_info'] and
                  g['expression'].endswith(' || '+child['expression']+')')]
        f.require(len(parent) == 1, 'Missing child has no unique actual parent')
        result.append(dict(scope=scope, child_expression=child['expression'],
            parent_expression=parent[0]['expression'], child_targets=child['targets'],
            retained=child['retained'], generate_info=child['generate_info'],
            actual_child_meta='HOLD_NOT_CAPTURED_NO_SYNTHESIZED_SELECTOR'))
    f.require(len(result) == 224, 'Exact missing224 required')
    return result


def evidence():
    compatibility = v3.compatibility_evidence()
    artifact = json.loads((f.PARENT/'proof-native-plan.json').read_bytes())
    t = tkinter.Tcl(); t.tk.wantobjects(False)
    t.eval('set qsd_test_only 1'); t.eval(v3.TCL.read_text())
    rawrows = [t.splitlist(l) for l in (v3.FAILED/'native-rows.tcllist').read_text().splitlines()]
    row = next(r for r in rawrows if r[0] == 'inventory')
    names = {t.call('qsd_name', x) for x in t.splitlist(row[2])}
    mappings = pairs(artifact, row[1], names)
    with TREE.open() as stream:
        rows = list(csv.DictReader(stream))
    parents, nested = {}, []
    for r in rows:
        if r['Depth'] == '0':
            parents[r['Path']] = r
        elif r['Depth'] == '1':
            matches = [p for p in parents if r['Path'] == p+'.'+r['Column0']]
            f.require(len(matches) == 1 and r['Meta'] == matches[0]+'  .'+r['Column0'],
                      'Historical child path/meta relation differs')
            nested.append(dict(path=r['Path'], meta=r['Meta'], expression=r['Column0']))
        else:
            raise ValueError('Unexpected historical tree depth')
    f.require(nested and 'LZC_READ_ONLY_DISCOVERY_DONE 36' in TREE_LOG.read_text(), 'Successful native tree evidence absent')
    helptext = HELP.read_text()
    f.require(all(option in helptext for option in ('-firstChild', '-nextSibling', '-path', '-meta', '-childCount')),
              'Actual tree API help absent')
    pins = dict(compatibility['pins'])
    for path in (Path(__file__).resolve(), TEST, TCL, TREE, TREE_LOG, HELP, SUCCESS_SCRIPT,
                 v3.SCRIPT, v3.TEST, v3.TCL, f.PARENT/'proof-native-plan.json'):
        pins[str(path)] = f.sha(path)
    examples = [next(p for p in mappings if p['child_expression'].startswith('('+kind+'_valid_i'))
                for kind in ('weight', 'activation')]
    return dict(status='NESTED224_API_STUDY_NO_LAUNCH_NATIVE_HOLD', pins=pins,
        baseline='exact732 sourceproof; not733 coverage qualification',
        known_legal_API='gui_list_expand CovDetail.1 root; gui_list_get actual handle firstChild/nextSibling/path/meta/childCount',
        historical_nested_examples=nested[:2], historical_tree_rows=len(rows),
        help_not_equivalent_to_QBS_child_capture=True, actual_parent_mappings=mappings,
        actual_bank0_missing_groups=224, actual_bank1_inventory='NOT_CAPTURED',
        parent_child_relation='Missing inner conjunction is structurally inside a unique actually observed outer OR; not a bracket-only normalization of the top-level selector.',
        proposed_probe=dict(scope=row[1], examples=examples, parent_count=2, root_bound=8192,
            subtree_bound=128, max_depth=8, selects=False, columns=False,
            numeric_identity_binding=False, all1792_candidates_retained=True),
        target_count=1792, protected_condition_count=41214, source_scope=f.SCOPE_BOUNDARY,
        exclusions=False, EDA_started=False, native_qualified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    f.require(output.parent == f.proof.OUT and output.resolve() == output and not output.exists(), 'Fresh study required')
    record = evidence()
    output.mkdir()
    probe = record['proposed_probe']
    # One complete command per line; example child text is audit data, never a selector.
    selection = 'set qnt_scope '+f.tcl_word(probe['scope'])+'\nset qnt_parents [list '+ ' '.join(
        f.tcl_word(x['parent_expression']) for x in probe['examples'])+']\n'
    f.write(output/'probe-selection.tcl', selection)
    t = tkinter.Tcl(); t.tk.wantobjects(False); t.eval(selection)
    f.require(t.getvar('qnt_scope') == probe['scope'] and
              list(t.splitlist(t.getvar('qnt_parents'))) == [x['parent_expression'] for x in probe['examples']],
              'Diagnostic generated selection differs')
    record['pins'][str(output/'probe-selection.tcl')] = f.sha(output/'probe-selection.tcl')
    f.write(output/'review.json', record)
    print(json.dumps(dict(output=str(output), review_seal=f.sha(output/'review.json'), native_qualified=False)))


if __name__ == '__main__':
    main()
