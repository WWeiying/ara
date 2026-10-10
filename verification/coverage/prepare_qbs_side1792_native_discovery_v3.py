"""Legacy Tcl syntax successor; actual nested-condition identity remains HOLD."""
import argparse
import json
from pathlib import Path
import re
import tkinter

import prepare_qbs_side1792_native_discovery_v2 as v2

frozen = v2.frozen
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_qbs_side1792_native_discovery_v3.py')
TCL = SCRIPT.with_name('qbs_side1792_native_discovery_v3.tcl')
OLD_TCL = frozen.TCL
FAILED = frozen.proof.OUT/'qbs-side1792-native-discovery-v2-parent-20261006-01'


def compatibility_evidence():
    status = json.loads((FAILED/'capture-status.json').read_bytes())
    log = (FAILED/'DVEfiles/dve_gui.log').read_text()
    frozen.require('was loaded successfully' in log and 'invalid command name "lassign"' in log and
                   status['status'] == 'HOLD', 'Actual v2 failure differs')
    pins = {str(FAILED/'capture-status.json'): frozen.sha(FAILED/'capture-status.json')}
    for rel in ('discovery-plan.json', 'selection.tcl', 'DVEfiles/dve_gui.log',
                'native-rows.tcllist', 'actual-executable.json'):
        p = FAILED/rel
        frozen.require(status['artifacts'][str(p)] == frozen.sha(p), 'Actual v2 pin drift')
        pins[str(p)] = frozen.sha(p)
    interp = tkinter.Tcl(); interp.tk.wantobjects(False)
    interp.eval('set qsd_test_only 1'); interp.eval(TCL.read_text())
    rows = [interp.splitlist(line) for line in (FAILED/'native-rows.tcllist').read_bytes().decode('ascii').splitlines()]
    inventory = [row for row in rows if row[0] == 'inventory']
    frozen.require(len(inventory) == 1, 'Unexpected actual inventory population')
    _, scope, raw = inventory[0]
    names = [interp.call('qsd_name', token) for token in interp.splitlist(raw)]
    artifact = json.loads((frozen.PARENT/'proof-native-plan.json').read_bytes())
    expected = [g['expression'] for g in artifact['native_groups'] if g['scope'] == scope]
    missing = sorted(set(expected)-set(names))
    frozen.require(len(names) == len(set(names)) == 6840 and len(expected) == 672 and len(missing) == 224,
                   'Actual expression availability differs')
    return dict(status='ACTUAL_LASSIGN_UNAVAILABLE_NESTED_IDENTITY_HOLD', pins=pins,
        actual_Tcl_version='NOT_CAPTURED_DO_NOT_INFER_EXACT_VERSION',
        lassign='Actual invalid-command failure',
        lsort_unique='Actual duplicate check completed before reaching lassign; also used in prior successful RVH scripts',
        core_profile='8.4-era command subset modeled on host; not an actual old-interpreter execution',
        actual_inventory=dict(scope=scope, unique_expressions=6840, expected_groups=672,
            present_groups=448, missing_groups=224, missing_expressions=missing),
        next_identity_action='Read-only investigate nested Condition child/subexpression API from existing help; no raw/XML ID inference, no dropping224 groups, no blind v3 launch',
        native_qualified=False)


def audit_tcl():
    text = TCL.read_text()
    frozen.safe_tcl(text)
    frozen.require(not re.search(r'\b(lassign|dict|lmap|try|coroutine|tailcall|apply)\s|\{\*\}',
                    '\n'.join(l for l in text.splitlines() if 'info commands' not in l)),
                   'Modern core command syntax')
    frozen.require('set expression [lindex $group 0]' in text and 'set expected [lindex $group 1]' in text,
                   'Exact legacy pair extraction required')
    return dict(commands=['proc', 'if', 'error', 'for', 'set', 'llength', 'lindex', 'incr', 'break',
        'global', 'puts', 'flush', 'foreach', 'lappend', 'expr', 'list', 'lsort -unique',
        'lsearch -exact', 'source', 'open', 'file join', 'close', 'catch', 'info exists/commands/patchlevel/tclversion'],
        GUI_APIs=sorted(frozen.ALLOWED), unsupported_lassign_replaced=True, hidden_columns=False,
        command_expansion=False, expression_operators='eq/ne and Boolean/comparison only; no in/ni')


def write(path, value):
    if path.name == 'discovery-plan.json':
        # Keep all prior proof, population, serializer and original-failure gates.
        value['pins'].update({str(p): frozen.sha(p) for p in (SCRIPT, TEST, v2.SCRIPT, v2.TEST, OLD_TCL)})
        original = v2.failure_evidence(); current = compatibility_evidence()
        value['pins'].update(original['pins']); value['pins'].update(current['pins'])
        value['original_failure_diagnosis'] = original
        value['v2_compatibility_and_identity_diagnosis'] = current
        value['Tcl_command_audit'] = audit_tcl()
        artifact = json.loads(Path(value['proof']).read_bytes())
        value['selection_host_execution'] = v2.validate_generated((path.parent/'selection.tcl').read_text(),
            artifact, Path(value['sample_database']), value['sample_test'])
        value['schema'] = 'QBS_SIDE1792_NATIVE_DISCOVERY_V3'
        value['readiness'] = 'HOST_SYNTAX_READY_ACTUAL_NESTED224_BINDING_HOLD_NO_LAUNCH'
    v2.OLD_WRITE(path, value)


def configure():
    v2.configure()
    frozen.TCL = TCL
    frozen.write = write


def verify(output, seal):
    plan = frozen.verify(output, seal)
    frozen.require(plan['schema'] == 'QBS_SIDE1792_NATIVE_DISCOVERY_V3' and
        plan['pins'].get(str(SCRIPT)) == frozen.sha(SCRIPT) and plan['pins'].get(str(TEST)) == frozen.sha(TEST),
        'v3 source binding differs')
    frozen.require(plan['v2_compatibility_and_identity_diagnosis'] == compatibility_evidence() and
                   plan['Tcl_command_audit'] == audit_tcl(), 'Compatibility/identity audit differs')
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args(); configure(); audit_tcl()
    if args.command == 'prepare':
        frozen.prepare(args.output.absolute())
    else:
        verify(args.output.absolute(), args.seal)


if __name__ == '__main__':
    main()
