"""Prepare one local-session nested vector measurement; never launch or apply."""
import argparse
import json
from pathlib import Path
import re
import tkinter

import bind_qbs_full_native_signatures_offline as audit

f = audit.f
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_qbs_nested_singleton11.py')
TCL = SCRIPT.with_name('qbs_nested_singleton11.tcl')
REVIEW = f.proof.OUT/'qbs-full-native-signature-protection-offline-agent-20261006-01/review-plan.json'
SEAL = 'ad9200bf6979c1b1cf00b9be6a9ce6d79868f52887f90332246ee04721a62525'


def inputs():
    f.require(f.sha(REVIEW) == SEAL, 'Independent interface study seal drift')
    record = json.loads(REVIEW.read_bytes()); f.check_pins(record['pins'])
    f.require(record == audit.evidence(), 'Actual capture/interface evidence differs')
    plan = json.loads((audit.CAPTURE/'discovery-plan.json').read_bytes())
    return record, plan


def selection(record, plan, output):
    candidate = record['bounded_singleton_interface_study']['QBS_probe_candidate']
    p = candidate['point']; expression = p['expression']
    parent = '(gen_side_row[0].gen_activation_byte[0].use_newer || '+expression+')'
    values = dict(qs_scope=candidate['scope'], qs_expression=expression, qs_parent=parent,
        qs_module=candidate['module_checksum'], qs_metric=candidate['checksum'],
        qs_point=p['attributes']['chksum'], qs_width=p['attributes']['width'],
        qs_annotation=f.proof.ANNOTATION, qs_design=str(f.proof.DESIGN),
        qs_testdir=plan['sample_database'], qs_test=plan['sample_test'], qs_output=str(output))
    text = '\n'.join('set '+k+' '+f.tcl_word(v) for k, v in values.items())+'\n'
    t = tkinter.Tcl(); t.tk.wantobjects(False); t.eval(text)
    f.require(all(t.getvar(k) == v for k, v in values.items()), 'Actual host selection serialization differs')
    return text


def safe():
    text = TCL.read_text()
    apis = set(re.findall(r'\bgui_\w+', text))
    f.require(apis == {'gui_list_get', 'gui_list_get_selected', 'gui_list_select', 'gui_list_action',
        'gui_covdetail_query', 'gui_list_expand', 'gui_cov_show_cond_ids', 'gui_exclusion_file',
        'gui_exclude_items', 'gui_exclusion', 'gui_open_cov', 'gui_exit'}, 'Unexpected singleton API')
    f.require(not re.search(r'\b(lassign|dict|lmap|exec|eval|uplevel|after|apply)\b|\{\*\}|-columns', text), 'Nonlegacy/unknown API')
    f.require('-list vector -selected -annotation' in text and '-list cond -selected -annotation' not in text,
              'Whole condition mutation forbidden')


def inspect(output, candidate):
    records = []
    for name in ('first.el', 'second.el'):
        records.append(f.proof.bind_native((output/name).read_bytes(), [candidate]))
    f.require(records[0] == records[1] and (output/'first.el').read_bytes() == (output/'second.el').read_bytes(), 'Native singleton reload drift')
    for name in ('initial-empty.el', 'before-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
        f.require((output/name).read_bytes() == b'', 'Global empty EL differs')
    t = tkinter.Tcl(); t.tk.wantobjects(False)
    raw = (output/'native-singleton.tcllist').read_bytes()
    f.require(raw.endswith(b'\n') and b'\x00' not in raw, 'Incomplete raw singleton')
    rows = [t.splitlist(line) for line in raw.decode('ascii').splitlines()]
    expression = candidate['point']['expression']; parent = '(gen_side_row[0].gen_activation_byte[0].use_newer || '+expression+')'
    meta = parent+'  .'+expression
    obj = rows[0]; f.require(len(obj) == 5 and obj[:4] == ('object', candidate['scope'], expression, parent), 'Actual object scope/expression differs')
    handle, path, observed = t.splitlist(obj[4])
    f.require(handle not in ('', '0') and path == parent+'.'+expression and observed == meta, 'Actual native child relation differs')
    expected_audits = [(stage, m, v, str(int(active and m == meta and v == '11')))
        for stage, active in (('before', False), ('selected', True), ('reset', False), ('reloaded', True), ('final', False))
        for m, vs in ((meta, ('01', '10', '11')), (parent, ('00', '01', '10'))) for v in vs]
    f.require([r[1:] for r in rows if r[0] == 'audit'] == expected_audits, 'Exact lifecycle/neighbor protection differs')
    saved = [r for r in rows if r[0] == 'saved']
    expected_names = ['initial-empty.el', 'before-empty.el', 'first.el', 'reset-empty.el', 'second.el', 'final-empty.el', 'cleanup-empty.el']
    f.require([r[1] for r in saved] == expected_names and all(len(r) == 3 for r in saved), 'Saved lifecycle differs')
    for r in saved:
        expected = (str(records[0][0]['native_id']), str(records[0][0]['vector_id'])) if r[1] in ('first.el', 'second.el') else ()
        f.require(t.splitlist(r[2]) == expected, 'Saved numeric signature differs')
    timeline = [('object',), ('saved', 'initial-empty.el')]
    for stage, name in (('before', 'before-empty.el'), ('selected', 'first.el'), ('reset', 'reset-empty.el'),
                        ('reloaded', 'second.el'), ('final', 'final-empty.el')):
        timeline.extend([('audit', stage)]*6)
        timeline.append(('saved', name))
    timeline.extend([('complete',), ('saved', 'cleanup-empty.el'), ('terminal',)])
    f.require([r[:2] if r[0] in ('audit', 'saved') else r[:1] for r in rows] == timeline,
              'Interleaved lifecycle order differs')
    f.require(rows[-2] == ('saved', 'cleanup-empty.el', '') and rows[-1] == ('terminal', '0', '', '0', '') and
        [r for r in rows if r[0] == 'complete'] == [('complete', 'SINGLETON11_SIGNATURE_PROTECTION_ONLY_FULL1792_HOLD')] and
        len(rows) == 40 and all(r[0] in ('object', 'audit', 'saved', 'complete', 'terminal') for r in rows), 'Incomplete/extra terminal evidence')
    return dict(status='SINGLETON11_NATIVE_SIGNATURE_PROTECTION_PASS_FULL1792_HOLD', records=records[0], protected_points=43005,
        application=False, full1792_qualified=False)


def verify(output, seal):
    f.require(f.sha(output/'singleton-plan.json') == seal, 'External plan seal drift')
    plan = json.loads((output/'singleton-plan.json').read_bytes()); f.check_pins(plan['pins'])
    record, original = inputs(); safe(); f.tool.revalidate(plan['tool_identity'])
    f.require((output/'selection.tcl').read_text() == selection(record, original, output), 'Generated selection drift')
    f.require(plan['command'] == ['/usr/bin/timeout', '--kill-after=10s', '300s'] + f.tool.launch_command(plan['tool_identity'], TCL) and
        plan['environment'] == dict(QBS_SINGLETON_SELECTION=str(output/'selection.tcl')) and
        plan['candidate'] == record['bounded_singleton_interface_study']['QBS_probe_candidate'] and
        plan['protected_points'] == 43005 and not plan['launched'] and not plan['application'], 'Plan scope/launch drift')
    print('VERIFY_PASS_SINGLETON_PREPARED_NOT_LAUNCHED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify', 'inspect'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    args = parser.parse_args(); output = args.output.absolute()
    f.require(output.parent == f.proof.OUT and output.resolve() == output, 'Direct output required')
    if args.command == 'prepare':
        f.require(not output.exists(), 'Existing evidence protected')
        record, original = inputs(); safe()
        text = selection(record, original, output); output.mkdir(); f.write(output/'selection.tcl', text)
        pins = dict(record['pins'])
        for p in (REVIEW, SCRIPT, TEST, TCL, output/'selection.tcl', audit.full.BODY): pins[str(p)] = f.sha(p)
        identity = original['tool_identity']; f.tool.revalidate(identity)
        plan = dict(schema='QBS_NESTED_SINGLETON11_V1', status='PREPARED_NOT_LAUNCHED', pins=pins,
            candidate=record['bounded_singleton_interface_study']['QBS_probe_candidate'], tool_identity=identity,
            command=['/usr/bin/timeout', '--kill-after=10s', '300s']+f.tool.launch_command(identity, TCL),
            environment=dict(QBS_SINGLETON_SELECTION=str(output/'selection.tcl')), budget_seconds=300,
            protected_points=43005, source_scope_boundary=f.SCOPE_BOUNDARY,
            authorization_required='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL: ONE_LOCAL_SESSION_SINGLETON11_TEMPORARY_EXCLUSION_SAVE_RESET_RELOAD; exact plan seal; no final application',
            protection='Global empty->exact singleton EL->reset empty->reload identical singleton->final/cleanup empty; nested01/10 and parent00/01/10 unchanged. Exact global one-record EL protects all other scopes/metrics and43005 raw conditions.',
            launched=False, application=False, full1792_qualified=False)
        f.write(output/'singleton-plan.json', plan)
        print(json.dumps(dict(output=str(output), seal=f.sha(output/'singleton-plan.json'), pins=len(pins))))
    else:
        verify(output, args.seal)
        if args.command == 'inspect':
            print(json.dumps(inspect(output, json.loads((output/'singleton-plan.json').read_bytes())['candidate'])))


if __name__ == '__main__': main()
