"""Order-only successor; exact records/annotations and all five stages remain required."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tkinter

import prepare_qbs_full1792_qualification as old

f = old.f
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_qbs_full1792_multiset_v2.py')
TCL = SCRIPT.with_name('qbs_full1792_qualification_multiset_v2.tcl')
FAILED = f.proof.OUT/'qbs-full1792-native-qualification-agent-20261006-01'
OLD_PLAN_SHA = '224eb4be2d8202858cc2ed89b0f3246a83f688c162284d6b12e7e6233f043f01'
FIRST_SHA = 'a01ec0bf13bdd1c14083af8257a0e39e038f608ec16fbdf2c33ce2876fd72121'
SECOND_SHA = '27357bc6c2e1f67ce39e033c3d01cf5d89a4aa7e5ff598e0804467510f259401'
OLD_TCL = old.TCL
OLD_SCRIPT = old.SCRIPT
OLD_TEST = old.TEST
OLD_SAFE = old.safe
BASE_WRITE = f.write
MULTISET = SCRIPT.with_name('native_exclusion_multiset_v2.tcl')


def canonical(raw, artifact):
    f.proof.bind_native(raw, artifact['candidates'])
    # splitlist only: captured native text is an argument, never evaluated Tcl.
    t = tkinter.Tcl(); t.tk.wantobjects(False); t.eval(MULTISET.read_text())
    try: records = [t.splitlist(r) for r in t.splitlist(t.call('nem_records',raw.decode('ascii')))]
    except tkinter.TclError as exc: raise ValueError('Strict annotated native multiset invalid: '+str(exc)) from exc
    f.require(len(records) == 1792 and all(len(r)==10 for r in records), 'Exact annotated native records required')
    return Counter(records)


def equivalent(first, second, artifact):
    f.require(canonical(first,artifact) == canonical(second,artifact), 'Reload native identity/attribute multiset drift')


def failure_evidence(artifact):
    path = FAILED/'qualification-plan.json'
    f.require(f.sha(path) == OLD_PLAN_SHA, 'Frozen failed plan seal differs')
    plan = json.loads(path.read_bytes()); f.check_pins(plan['pins'])
    first = (FAILED/'first.el').read_bytes(); second = (FAILED/'second.el').read_bytes()
    f.require(f.sha(FAILED/'first.el') == FIRST_SHA and f.sha(FAILED/'second.el') == SECOND_SHA, 'Actual failed EL drift')
    equivalent(first,second,artifact)
    raw = (FAILED/'native-qualification.tcllist').read_bytes()
    t = tkinter.Tcl(); t.tk.wantobjects(False)
    rows = [t.splitlist(line) for line in raw.decode('ascii').splitlines()]
    f.require(rows[-1] == ('terminal','1','Reload native signature drift','0','') and
        not any(r[0]=='complete' or (r[0]=='stage' and r[1]=='final') for r in rows), 'Original failure must remain incomplete HOLD')
    return dict(original_terminal='HOLD_RELOAD_BYTE_ORDER_DRIFT_FINAL_STAGE_MISSING',
        actual_records_per_EL=1792, exact_identity_attribute_annotation_multiset_equal=True,
        raw_line_multiset_equal=Counter(first.splitlines()) == Counter(second.splitlines()),
        raw_bytes_equal=first == second, qualification_salvaged=False, original_outputs_unchanged=True)


def safe():
    text = TCL.read_text()
    f.require(not re.search(r'\b(lassign|dict|lmap|exec|eval|uplevel|after|apply)\b|\{\*\}|-columns|-unique',text), 'Nonlegacy/unknown successor API')
    f.require(set(re.findall(r'\bgui_\w+',text)) == {'gui_open_cov','gui_list_expand','gui_exclusion','gui_exit'}, 'Unexpected successor GUI API')
    f.require('nem_require_equal' in text and 'nem_install' not in text and '$count == 1792' in text, 'Exact1792 primitive only')
    saved = old.TCL
    try: old.TCL = OLD_TCL; OLD_SAFE()
    finally: old.TCL = saved


def write(path, value):
    if path.name == 'qualification-plan.json':
        artifact = json.loads((f.PARENT/'proof-native-plan.json').read_bytes())
        value['schema'] = 'QBS_FULL1792_NATIVE_MULTISET_V2'
        value['order_only_failure_diagnosis'] = failure_evidence(artifact)
        value['reload_equivalence'] = 'Exact multiset of observed scope,module/metric/point checksums,native Condition ID,expression,width,bit,native vector ID,truth vector AND attached annotation. No byte-order requirement; multiplicity/aliases/extra/missing remain rejected.'
        for p in (OLD_SCRIPT,OLD_TEST,OLD_TCL,MULTISET,FAILED/'qualification-plan.json',FAILED/'first.el',
                  FAILED/'second.el',FAILED/'native-qualification.tcllist'):
            value['pins'][str(p)] = f.sha(p)
    BASE_WRITE(path,value)


def configure():
    old.SCRIPT=SCRIPT; old.TEST=TEST; old.TCL=TCL; old.safe=safe; f.write=write


def inspect(output,artifact):
    first=(output/'first.el').read_bytes(); second=(output/'second.el').read_bytes()
    equivalent(first,second,artifact)
    records=f.proof.bind_native(first,artifact['candidates'])
    for name in ('initial-empty.el','before-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        f.require((output/name).read_bytes()==b'', 'Global population not empty')
    raw=(output/'native-qualification.tcllist').read_bytes()
    f.require(0 < len(raw) < 32*1024*1024 and raw.endswith(b'\n') and b'\x00' not in raw,'Invalid native evidence')
    t=tkinter.Tcl(); t.tk.wantobjects(False)
    lines=raw.decode('ascii').splitlines(); rows=[t.splitlist(line) for line in lines]
    f.require(rows[0]==('saved','initial-empty.el'),'Initial guard absent')
    discovery=[]; i=1
    while i<len(rows) and rows[i][0] in ('inventory','object','group','scope_complete'):
        discovery.append(lines[i]); i+=1
    old.full.inspect_rows(('\n'.join(discovery)+'\ncomplete 1344 448 FULL1792_NATIVE_HOLD\n').encode('ascii'),artifact)
    metas={(r[1],r[2]):r[6] for r in rows[1:i] if r[0]=='object'}
    for stage,active,name in (('before',False,'before-empty.el'),('selected',True,'first.el'),
                            ('reset',False,'reset-empty.el'),('reloaded',True,'second.el'),('final',False,'final-empty.el')):
        expected=[]
        for g in old.full.groups(artifact):
            for vector in g['names']:
                expected.append(('audit',stage,g['scope'],g['expression'],metas[(g['scope'],g['expression'])],vector,
                                 str(int(active and vector in g['targets']))))
        f.require(rows[i:i+3584]==expected,'Exact target/neighbor stage differs: '+stage); i+=3584
        f.require(rows[i:i+2]==[('stage',stage,'3584',str(1792*int(active))),('saved',name)],'Stage order/population differs'); i+=2
    f.require(rows[i:]==[('complete','FULL1792_SIGNATURE_PROTECTION_ONLY_NOT_APPLICATION'),
        ('saved','cleanup-empty.el'),('terminal','0','','0','')],'Full terminal/cleanup absent')
    old.single.audit.protection(artifact)
    return dict(status='FULL1792_NATIVE_MULTISET_SIGNATURE_PROTECTION_PASS_NOT_APPLICATION',target_count=1792,
        protected_count=41214,actual_native_records=records,five_stages_pass=True,application=False,
        source_control_boundary=f.SCOPE_BOUNDARY,not_arbitrary_X_or_delta_proof=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','verify','inspect')); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal'); args=parser.parse_args(); configure()
    output=args.output.absolute()
    if args.command=='prepare':
        # Use the reviewed v1 prepare exactly, with new profile paths and evidence hook.
        old.main()
    else:
        artifact=old.verify(output,args.seal)
        plan=json.loads((output/'qualification-plan.json').read_bytes())
        f.require(plan['schema']=='QBS_FULL1792_NATIVE_MULTISET_V2' and
            plan['order_only_failure_diagnosis']==failure_evidence(artifact),'Successor diagnosis drift')
        if args.command=='inspect': print(json.dumps(inspect(output,artifact)))


if __name__=='__main__': main()
