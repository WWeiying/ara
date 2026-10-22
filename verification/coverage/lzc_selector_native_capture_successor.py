#!/usr/bin/env python3
"""Prepare a fresh standalone capture using strict DVE selection normalization."""
import argparse
import copy
import json
from pathlib import Path

import lzc_selector_native_prepare as native
import lzc_selector_native_run as runner


def prepare(prepared, suffix, script):
    native.require(prepared.parent == native.OUT and script.parent == native.HERE
                   and script.name.startswith('lzc_selector_native_capture_'), 'Standalone successor only')
    experiments = json.loads((prepared / 'experiments.json').read_bytes())['experiments']
    for experiment in experiments:
        case = prepared / experiment['top']
        old = case / 'lzc_selector_native_capture-01'
        new = case / suffix
        native.require(new.parent == case and new.name.startswith('lzc_selector_native_capture-')
                       and not new.exists(), 'Fresh standalone capture required')
        plan = json.loads((old / 'capture-plan.json').read_bytes())
        runner.check_pins(plan['pins'])
        updated = copy.deepcopy(plan)
        new.mkdir()
        selection = (old / 'selection.tcl').read_text()
        native.require(selection.count(str(old)) == 1, 'Unexpected selection output binding')
        if script.name == 'lzc_selector_native_capture_v3.tcl':
            design = native.Design(case / 'simv.vdb')
            _, population = native.compiled_points(design, experiment['top'] + '.dut', 'cond')
            hidden = {p['native_id'] for p in population if p['attributes'].get('optype') == '16'}
            updated['xml_only_rows'] = [r for r in plan['rows'] if r[0] == 'cond' and r[1] in hidden]
            updated['rows'] = [r for r in plan['rows'] if r not in updated['xml_only_rows']]
            original_targets = [plan['rows'][i] for i in plan['targets']]
            updated['targets'] = [i for i, r in enumerate(updated['rows']) if r in original_targets]
            updated['limitation'] = 'op16 XML monitored rows are not independently exposed by native DVE; they remain unqualified and are not claimed as individually audited.'
            words = ['set lsn_scope ' + native.tcl_word(experiment['top'] + '.dut'),
                     'set lsn_vdb ' + native.tcl_word(case / 'simv.vdb'),
                     'set lsn_test ' + native.tcl_word(str(case / 'simv') + '/' + experiment['top']),
                     'set lsn_output ' + native.tcl_word(new), 'set lsn_rows {']
            words += ['  {' + ' '.join(native.tcl_word(v) for v in r) + '}' for r in updated['rows']]
            words += ['}', 'set lsn_targets {' + ' '.join(map(str, updated['targets'])) + '}']
            selection = '\n'.join(words) + '\n'
            updated['pins'][str(native.HERE / 'lzc_selector_native_capture_v2.tcl')] = native.sha(
                native.HERE / 'lzc_selector_native_capture_v2.tcl')
        else:
            selection = selection.replace(str(old), str(new))
        native.write(new / 'selection.tcl', selection)
        updated['command'][-1] = str(script)
        updated['environment']['LZC_SELECTOR_NATIVE_SELECTION'] = str(new / 'selection.tcl')
        for path in (old / 'capture-plan.json', new / 'selection.tcl', script,
                     Path(__file__).resolve()):
            updated['pins'][str(path)] = native.sha(path)
        updated['capture_successor'] = dict(parent=str(old), output=str(new), script=str(script),
                                           simulation_changed=False,
                                           rows_changed=script.name == 'lzc_selector_native_capture_v3.tcl')
        native.write(new / 'capture-plan.json', updated)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--suffix', required=True)
    parser.add_argument('--script', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.prepared.absolute(), args.suffix, args.script.absolute())
