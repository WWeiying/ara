"""Full native qualification preparation/inspection; no launch or final application."""
import argparse
import json
from pathlib import Path
import re
import tkinter

import prepare_qbs_nested_singleton11 as single

f = single.f
full = single.audit.full
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_qbs_full1792_qualification.py')
TCL = SCRIPT.with_name('qbs_full1792_qualification.tcl')
CAPTURE = f.proof.OUT/'qbs-nested-singleton11-parent-20261006-01'
CAPTURE_SHA = '7bbdd8227dae4eb6dcd8f9df547086eb775137819e688ee4ba5c1844b6f6f682'
BUDGET = 3600


def inputs():
    record, original = single.inputs()
    path = CAPTURE/'capture-status.json'
    f.require(f.sha(path) == CAPTURE_SHA, 'Actual parent singleton status seal drift')
    status = json.loads(path.read_bytes()); planpath = CAPTURE/'singleton-plan.json'
    single.verify(CAPTURE, status['plan_seal'])
    plan = json.loads(planpath.read_bytes()); observed = single.inspect(CAPTURE, plan['candidate'])
    f.require(all(status[k] == v for k, v in observed.items()) and
        status['provenance'] == 'PARENT_AGENT_INDEPENDENT_EXECUTION', 'Parent actual singleton reproduction differs')
    exe = json.loads((CAPTURE/'actual-executable.json').read_bytes())
    f.require(exe['executable_verified'], 'Actual DVE identity absent')
    pins = dict(record['pins']); pins.update(plan['pins'])
    for p in CAPTURE.iterdir():
        if p.is_file(): pins[str(p)] = f.sha(p)
    artifact = json.loads(Path(original['proof']).read_bytes())
    return artifact, original, pins, observed


def selection(artifact, original, output):
    text = full.selection(artifact, Path(original['sample_database']), original['sample_test'])
    text += '\n'.join('set '+k+' '+f.tcl_word(str(v)) for k, v in dict(
        qs_design=f.proof.DESIGN, qs_testdir=original['sample_database'], qs_test=original['sample_test'],
        qs_output=output, qs_annotation=f.proof.ANNOTATION).items())+'\n'
    text += 'set qn_scopes {}\nset qn_scope_names {}\narray set qn_expected {}\n'
    word = f.tcl_word
    for scope in sorted(artifact['scope_protection']):
        text += 'set qn_groups {}\nlappend qn_scope_names '+word(scope)+'\n'
        for g in full.groups(artifact):
            if g['scope'] == scope:
                text += 'lappend qn_groups [list '+word(g['expression'])+' '+word(g['parent'])+' [list '+' '.join(map(word,g['names']))+'] [list '+' '.join(map(word,g['targets']))+']]\n'
        text += 'lappend qn_scopes [list '+word(scope)+' $qn_groups]\n'
    for c in artifact['candidates']:
        point = c['point']; a = point['attributes']
        text += 'set qn_expected([list '+word(c['scope'])+' '+word(point['expression'])+' '+word(point['vector'])+']) [list '+word(a['chksum'])+' '+word(a['width'])+']\n'
    t = tkinter.Tcl(); t.tk.wantobjects(False); t.eval(text)
    f.require(int(t.eval('array size qn_expected')) == 1792 and len(t.splitlist(t.getvar('qn_scopes'))) == 2, 'Full actual Tcl serialization differs')
    return text


def safe():
    text = TCL.read_text()
    f.require(not re.search(r'\b(lassign|dict|lmap|exec|eval|uplevel|after|apply)\b|\{\*\}|-columns|-unique', text), 'Nonlegacy or unknown API')
    f.require(set(re.findall(r'\bgui_\w+', text)) == {'gui_list_action', 'gui_covdetail_query', 'gui_list_get_selected',
        'gui_exclusion_file', 'gui_exclude_items', 'gui_exclusion', 'gui_open_cov', 'gui_list_expand', 'gui_exit'}, 'Unexpected GUI API')
    f.require(text.count('gui_exclude_items ') == 1 and '-list vector -selected -annotation' in text,
        'Only per-vector local-session exclusions permitted')


def inspect(output, artifact):
    first = (output/'first.el').read_bytes(); second = (output/'second.el').read_bytes()
    records = f.proof.bind_native(first, artifact['candidates'])
    f.proof.bind_native(second, artifact['candidates'])
    f.require(first == second, 'Full native signature reload drift')
    for name in ('initial-empty.el','before-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        f.require((output/name).read_bytes() == b'', 'Global population not empty')
    raw = (output/'native-qualification.tcllist').read_bytes()
    f.require(0 < len(raw) < 32*1024*1024 and raw.endswith(b'\n') and b'\x00' not in raw, 'Invalid raw native evidence')
    t = tkinter.Tcl(); t.tk.wantobjects(False)
    lines = raw.decode('ascii').splitlines(); rows = [t.splitlist(line) for line in lines]
    f.require(rows[0] == ('saved','initial-empty.el'), 'Initial global guard absent')
    discovery = []; i = 1
    while i < len(rows) and rows[i][0] in ('inventory','object','group','scope_complete'):
        discovery.append(lines[i]); i += 1
    full.inspect_rows(('\n'.join(discovery)+'\ncomplete 1344 448 FULL1792_NATIVE_HOLD\n').encode('ascii'), artifact)
    metas = {(r[1],r[2]):r[6] for r in rows[1:i] if r[0] == 'object'}
    for stage, active, name in (('before',False,'before-empty.el'),('selected',True,'first.el'),
                              ('reset',False,'reset-empty.el'),('reloaded',True,'second.el'),('final',False,'final-empty.el')):
        expected = []
        for g in full.groups(artifact):
            for vector in g['names']:
                expected.append(('audit',stage,g['scope'],g['expression'],metas[(g['scope'],g['expression'])],vector,
                                 str(int(active and vector in g['targets']))))
        f.require(rows[i:i+3584] == expected, 'Exact3584 target/neighbor stage differs: '+stage)
        i += 3584
        f.require(rows[i:i+2] == [('stage',stage,'3584',str(1792*int(active))),('saved',name)], 'Stage population/order differs')
        i += 2
    f.require(rows[i:] == [('complete','FULL1792_SIGNATURE_PROTECTION_ONLY_NOT_APPLICATION'),
        ('saved','cleanup-empty.el'),('terminal','0','','0','')], 'Full native terminal/cleanup differs')
    single.audit.protection(artifact)
    return dict(status='FULL1792_NATIVE_SIGNATURE_PROTECTION_PASS_NOT_APPLICATION', target_count=1792,
        protected_count=41214, actual_native_records=records, five_stages_pass=True, application=False,
        source_control_boundary=f.SCOPE_BOUNDARY, not_arbitrary_X_or_delta_proof=True)


def verify(output, seal):
    f.require(f.sha(output/'qualification-plan.json') == seal, 'External plan seal drift')
    plan = json.loads((output/'qualification-plan.json').read_bytes()); f.check_pins(plan['pins'])
    artifact, original, _, actual = inputs(); safe(); f.tool.revalidate(plan['tool_identity'])
    f.require((output/'selection.tcl').read_text() == selection(artifact,original,output) and
        plan['actual_singleton'] == actual and plan['budget_seconds'] == BUDGET and
        plan['command'] == ['/usr/bin/timeout','--kill-after=10s',str(BUDGET)+'s']+f.tool.launch_command(plan['tool_identity'],TCL) and
        plan['environment'] == dict(QBS_FULL1792_SELECTION=str(output/'selection.tcl')) and
        plan['source_control_boundary'] == f.SCOPE_BOUNDARY and not plan['launched'] and not plan['application'], 'Full qualification binding drift')
    print('VERIFY_PASS_FULL1792_PREPARED_NO_LAUNCH')
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','verify','inspect'))
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--seal')
    args=parser.parse_args(); output=args.output.absolute()
    f.require(output.parent == f.proof.OUT and output.resolve() == output, 'Direct fresh output required')
    if args.command == 'prepare':
        f.require(not output.exists(), 'Historical evidence protected')
        artifact,original,pins,actual=inputs(); safe(); text=selection(artifact,original,output)
        output.mkdir(); f.write(output/'selection.tcl',text)
        for p in (SCRIPT,TEST,TCL,single.SCRIPT,single.TEST,single.TCL,full.SCRIPT,full.TEST,full.BODY,output/'selection.tcl'):
            pins[str(p)]=f.sha(p)
        identity=original['tool_identity']; f.tool.revalidate(identity)
        record=dict(schema='QBS_FULL1792_NATIVE_QUALIFICATION_V1',status='PREPARED_NATIVE_HOLD_NOT_LAUNCHED',
            pins=pins, actual_singleton=actual,tool_identity=identity,budget_seconds=BUDGET,
            command=['/usr/bin/timeout','--kill-after=10s',str(BUDGET)+'s']+f.tool.launch_command(identity,TCL),
            environment=dict(QBS_FULL1792_SELECTION=str(output/'selection.tcl')),
            scope_protection=single.audit.protection(artifact),source_control_boundary=f.SCOPE_BOUNDARY,
            numerical_IDS='Only actual EL numeric IDs; compiled point checksums/expression/width/bit/vector bind identity. No XML ID equality or guessed GUI handles.',
            budget_basis='Actual1344 discovery111.617s; full five stages require17920 vector exclusion observations plus selections and1792 local exclusions.3600s conservative single bounded run, not a measured guarantee; timeout preserves HOLD, no auto retry.',
            qualification_only=True, application=False,launched=False,native_qualified=False,
            authorization_required='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL exact seal; ONE_FULL1792_LOCAL_SESSION_QUALIFICATION;3600s; temporary exact vector exclusions/save/reset/reload; no final application')
        f.write(output/'qualification-plan.json',record)
        print(json.dumps(dict(output=str(output),seal=f.sha(output/'qualification-plan.json'),pins=len(pins))))
    else:
        artifact=verify(output,args.seal)
        if args.command == 'inspect': print(json.dumps(inspect(output,artifact)))


if __name__ == '__main__': main()
