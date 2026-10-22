"""Single fresh735 combined native runtime: prepare/verify/inspect, never launch."""
import argparse
import copy
import csv
import json
from pathlib import Path
import re
import sys
import tkinter

import prepare_qbs_ninth735_qualification_plan as design
import lzc_snapshot_eight_policy_runtime as eight
import eight_policy_epoch_735_report_v5 as reader

f=design.f
merge=design.merge
SCRIPT=Path(__file__).resolve()
TCL=SCRIPT.with_suffix('.tcl')
TEST=SCRIPT.with_name('test_qbs_eight735_runtime.py')
NAME='combined-runtime.json'
BUDGET=14400
PROOF=f.proof.OUT/'qbs-payload-side1792-proof-native-plan-732-parent-20261006-01/proof-native-plan.json'


def dependencies():
    return (SCRIPT,TCL,TEST,reader.SCRIPT,reader.TEST,*reader.dependencies(),eight.SCRIPT,eight.TCL,
            design.SCRIPT,design.TEST,PROOF,Path('/usr/bin/timeout').resolve(),Path(sys.executable).resolve())


def replace_once(raw, old, new):
    f.require(raw.count(old)==1,'Frozen runtime install boundary differs')
    return raw.replace(old,new)


def payloads(output):
    source=json.loads(design.READER.read_bytes())
    names=(*eight.prior.HELPERS,'six-library.tcl','seven-selection.tcl','snapshot-selection.tcl',
           'csv-row-library.tcl')
    result={}
    for name in names:
        path=design.REPORT/name
        f.require(source['pins'].get(str(path))==f.sha(path),'Generated735 source helper drift: '+name)
        result[name]=path.read_bytes().replace(str(design.REPORT).encode(),str(output).encode())
    boundary=b'set failed [catch {eight_initialize; qbsapp_session} message]\n'
    raw=eight.TCL.read_bytes()
    f.require(raw.count(boundary)==1,'Frozen eight library boundary differs')
    result['eight-library.tcl']=raw.split(boundary)[0]
    # The prior real qualification selector is reused; native metas are rediscovered in this session.
    qpath=merge.qualified.RUN/'selection.tcl'
    qtext=qpath.read_text('ascii')
    t=tkinter.Tcl();t.tk.wantobjects(False);t.eval(qtext)
    old=t.getvar('qs_output')
    result['qbs-side-selection.tcl']=replace_once(qtext,
        'set qs_output '+f.tcl_word(old), 'set qs_output '+f.tcl_word(str(output))).encode('ascii')
    a=(merge.EIGHT/'applied.el').read_bytes()
    b=(merge.qualified.RUN/'first.el').read_bytes()
    merge.union_gate(a+b,merge.records(a),merge.records(b))
    result['combined-nine.el']=a+b
    return result


def reader_context(reader_plan, reader_seal, generated=None):
    """Use the independent repaired reader, not a replacement735 population implementation."""
    f.require(f.sha(reader_plan)==reader_seal,'Parent-selected735 reader seal drift')
    p=json.loads(reader_plan.read_bytes())
    f.require(reader_plan.name==reader.PLAN and Path(p['output'])==design.REPORT and p['population']==735 and
        p['admission_seal']=='4fb3c0219a791c9a669ad9403d97634042f57b423e0e94d7c65bdf57cfa59397',
        'Reviewed repaired735 v5 reader required; do not bypass reader fault')
    pins=dict(p['pins']);pins[str(reader_plan)]=reader_seal
    paths=list(p['byte_paths'])+[str(reader_plan)]
    jsons=list(p['json_paths'])+[str(reader_plan)]
    generated=generated or {}
    f.require(not set(generated)&set(pins),'Generated evidence cannot replace source authority')
    pins.update(generated);paths.extend(generated)
    jsons.extend(k for k in generated if k.endswith('.json'))
    owner=reader.Wiring(pins,paths,jsons)
    context,config=owner.fixed.read_config(owner.Path(design.REPORT),p['fixed_seal'])
    owner.check_inputs(config)
    return p,context,config


def prepare(output, reader_plan, reader_seal):
    f.require(output.parent==f.proof.OUT and output.resolve()==output and not output.exists(),'Fresh output only')
    baseline=design.evidence()
    source,_,config=reader_context(reader_plan,reader_seal)
    pins=dict(source['pins']);pins.update(baseline['pins']);pins[str(reader_plan)]=reader_seal
    for path in dependencies():
        pins[str(path)]=f.sha(path)
    f.check_pins(pins)
    identity=config['plan']['tool_identity'];f.tool.revalidate(identity)
    command=['/usr/bin/timeout','--kill-after=10s',str(BUDGET)+'s']+f.tool.launch_command(identity,TCL)
    data=payloads(output)
    output.mkdir()
    for group in (*eight.frozen.GROUPS,'lzc','snapshot'):(output/group).mkdir()
    for name,raw in data.items():
        with (output/name).open('xb') as stream:stream.write(raw)
        pins[str(output/name)]=f.sha(output/name)
    plan=dict(schema='QBS_EIGHT735_SINGLE_RUNTIME_V1',output=str(output),population=735,
        reader_plan=str(reader_plan),reader_seal=reader_seal,pins=pins,command=command,
        tool_identity=identity,budget_seconds=BUDGET,kill_after_seconds=10,stages=list(design.STAGES),
        targets=7684,protected_audited=19566,audited=27250,payload_condition_protected=41214,
        source_control_boundary=f.SCOPE_BOUNDARY,call_budget=baseline['call_budget'],
        application_approval=False,launch_approved=False,automatic_retry=False,
        parent_launch_metadata='Parent must preserve actual live-identity, execution, launcher, integrity-before/after using config below; exit0 is not qualification.')
    f.write(output/NAME,plan)
    f.write(output/'status.json',dict(status='PREPARED_NO_DVE',application_approval=False))
    return f.sha(output/NAME)


def verify(output, seal):
    f.require(output.parent==f.proof.OUT and output.resolve()==output,'Unsafe output')
    f.require(f.sha(output/NAME)==seal,'Runtime seal drift')
    p=json.loads((output/NAME).read_bytes());f.check_pins(p['pins'])
    f.require(p['schema']=='QBS_EIGHT735_SINGLE_RUNTIME_V1' and p['output']==str(output) and
        p['population']==735 and p['stages']==list(design.STAGES) and p['source_control_boundary']==f.SCOPE_BOUNDARY and
        (p['targets'],p['protected_audited'],p['audited'],p['payload_condition_protected'])==(7684,19566,27250,41214) and
        p['budget_seconds']==BUDGET and p['kill_after_seconds']==10 and
        not any(p[k] for k in ('application_approval','launch_approved','automatic_retry')),'Combined contract drift')
    source,context,config=reader_context(Path(p['reader_plan']),p['reader_seal'])
    for path in dependencies():f.require(p['pins'].get(str(path))==f.sha(path),'Mandatory runtime dependency omitted/drifted')
    for path,h in source['pins'].items():f.require(p['pins'].get(path)==h,'Inherited source ledger omitted')
    for name,raw in payloads(output).items():f.require((output/name).read_bytes()==raw,'Generated helper differs: '+name)
    expected=['/usr/bin/timeout','--kill-after=10s',str(BUDGET)+'s']+f.tool.launch_command(config['plan']['tool_identity'],TCL)
    f.require(p['command']==expected and p['tool_identity']==config['plan']['tool_identity'],'Tool binding differs')
    f.tool.revalidate(p['tool_identity'])
    derived=copy.deepcopy(config);derived.update(output=str(output),command=p['command'],pins=p['pins'])
    return p,context,derived


def check_union(raw):
    a=merge.records((merge.EIGHT/'applied.el').read_bytes())
    b=merge.records((merge.qualified.RUN/'first.el').read_bytes())
    return merge.union_gate(raw,a,b)


def qbs_rows(raw):
    t=tkinter.Tcl();t.tk.wantobjects(False)
    f.require(0<len(raw)<32*1024*1024 and raw.endswith(b'\n'),'Invalid QBS evidence size/termination')
    rows=[t.splitlist(line) for line in raw.decode('ascii').splitlines()]
    end=next((i for i,r in enumerate(rows) if r and r[0]=='audit'),None)
    f.require(end is not None,'Missing QBS stages')
    q=json.loads(design.QUALIFIED.read_bytes())
    artifact=json.loads(PROOF.read_bytes())
    # Fresh handle/path/meta discovery must pass the same full actual-object inspector.
    discovery=b'\n'.join(raw.splitlines()[:end])+b'\ncomplete 1344 448 FULL1792_NATIVE_HOLD\n'
    merge.qualified.native.old.full.inspect_rows(discovery,artifact)
    metas={(r[1],r[2]):r[6] for r in rows[:end] if r[0]=='object'}
    wanted=[]
    for stage in design.STAGES:
        active=stage in ('selected','reloaded','after-root')
        for g in merge.qualified.native.old.full.groups(artifact):
            for v in g['names']:
                wanted.append(('audit',stage,g['scope'],g['expression'],metas[g['scope'],g['expression']],v,
                               str(int(active and v in g['targets']))))
        wanted.append(('stage',stage,'3584',str(1792*int(active))))
    f.require(rows[end:]==wanted+[('terminal','0','','')],'Full six-stage QBS target/protection/terminal differs')
    f.require(q['qualification']['protected_count']==41214,'QBS complement differs')
    return 3584*6


def inspect(output,seal):
    p,context,config=verify(output,seal)
    produced={}
    for path in output.rglob('*'):
        if path.is_file() and str(path) not in p['pins']:
            f.require(not path.is_symlink() and path.resolve()==path,'Aliased generated evidence')
            produced[str(path)]=f.sha(path)
    _,context,_=reader_context(Path(p['reader_plan']),p['reader_seal'],produced)
    runtime=json.loads((design.REPORT/'runtime-plan.json').read_bytes())
    plan=json.loads((Path(runtime['seven_output'])/'application-plan.json').read_bytes())
    sources=dict(six=(Path(runtime['six_output'])/'combined.el').read_bytes(),
        lzc=(eight.SOURCE_PROOF/'candidate60.el').read_bytes(),snapshot=eight.MASK_EL.read_bytes())
    oldkeys={key for data in sources.values() for key,_ in eight.metric.blocks(data)}
    def old(raw):
        check_union(raw)
        return b''.join(chunk for key,chunk in eight.metric.blocks(raw) if key in oldkeys)
    def bind(raw,cfg,states=None):
        return eight.split_bind(old(raw),cfg,sources,runtime['snapshot_candidates'],states)
    condition_scopes={r['scope'] for r in plan['condition_native_records']}|{r['scope'] for r in runtime['snapshot_candidates']}
    qscopes=set(json.loads(design.QUALIFIED.read_bytes())['scope_protection']);condition_scopes|=qscopes
    namespace=dict(context.namespace(),bindings=bind,TIMEOUT=BUDGET,
        log_adapter=lambda path:(path/'DVEfiles/dve_gui.log').read_text().splitlines().count('SIX_POPULATION_SELECTION_ADAPTER_INSTALLED')==1)
    result=eight.prior.seven_verifier(namespace,
        lambda s,m,a:eight.prior.change_allowed(s,m,a,condition_scopes))(output,config)
    log=(output/'DVEfiles/dve_gui.log').read_text('utf-8')
    f.require(not re.search(r'(?:QBS_EIGHT|EIGHT|SEVEN)_(?:HOLD|FAILED|ERROR)',log),'Combined GUI failed')
    for marker in ('QBS_EIGHT_RUNTIME_INSTALLED','QBS_EIGHT_RELOAD_MULTISET_EXACT7684','QBS_EIGHT_COMPLETE7684_NOT_APPLICATION','EIGHT_CSV_WRITER_INSTALLED'):
        f.require(log.splitlines().count(marker)==1,'Missing exact completion: '+marker)
    files={}
    for stage in design.STAGES:
        active=stage in ('selected','reloaded','after-root')
        path=output/'lzc'/('states_'+stage+'.tsv');eight.prior.read_lzc_states(path,plan,active);files[str(path)]=f.sha(path)
        path=output/'snapshot'/('states_'+stage+'.csv')
        with path.open(newline='') as stream:
            r=csv.DictReader(stream);rows=list(r);f.require(r.fieldnames==eight.mask.native.AUDIT_COLUMNS,'Snapshot schema differs')
        wanted=[dict(zip(eight.mask.native.AUDIT_COLUMNS,[stage,g['scope'],g['expression'],' '.join(g['names']),
            ' '.join(g['targets']),' '.join(g['retained']),str(len(g['targets']) if active else 0),'0'])) for g in runtime['snapshot_groups']]
        f.require(rows==wanted,'Snapshot target/retained protection differs');files[str(path)]=f.sha(path)
        for marker in ('SEVEN_LZC_AUDIT %s 4200'%stage,'EIGHT_FULL_AUDIT %s 23666'%stage,'QBS_EIGHT_FULL_AUDIT %s 27250'%stage):
            f.require(log.splitlines().count(marker)==1,'Missing complete stage: '+marker)
    for name in ('applied.el','reloaded.el','after-root.el'):check_union((output/name).read_bytes());files[str(output/name)]=f.sha(output/name)
    for name in ('initial-empty.el','reset-empty.el','session-final-empty.el','final-empty.el','cleanup-empty.el'):
        f.require((output/name).read_bytes()==b'','Global empty/reset differs');files[str(output/name)]=f.sha(output/name)
    path=output/'native-qualification.tcllist';qbs_rows(path.read_bytes());files[str(path)]=f.sha(path)
    result.update(status='FRESH735_EIGHT_PLUS_QBS1792_QUALIFIED_NOT_APPLICATION',records=7684,
        audited=27250,state_checks=163500,payload_condition_protected=41214,application_approval=False,
        source_control_boundary=f.SCOPE_BOUNDARY,not_arbitrary_X_or_delta_proof=True)
    result['files'].update(files)
    f.require(all(f.sha(path)==h for path,h in produced.items()),'Generated evidence changed during verification')
    result['generated_evidence_pins']=produced
    return result


def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('mode',choices=('prepare','verify','inspect'))
    a.add_argument('--output',type=Path,required=True);a.add_argument('--seal')
    a.add_argument('--reader-plan',type=Path);a.add_argument('--reader-seal');args=a.parse_args();out=args.output.absolute()
    if args.mode=='prepare':
        f.require(args.reader_plan and args.reader_seal and not args.seal,'Exact repaired reader required')
        print(json.dumps(dict(seal=prepare(out,args.reader_plan.absolute(),args.reader_seal),output=str(out),DVE_started=False)))
    else:
        f.require(args.seal and not args.reader_plan and not args.reader_seal,'Sealed runtime only')
        if args.mode=='verify':
            p,_,_=verify(out,args.seal);print(json.dumps(dict(status='VERIFY_PASS_NOT_LAUNCHED',command=p['command'],budget_seconds=BUDGET)))
        else:print(json.dumps(inspect(out,args.seal)))


if __name__=='__main__':main()
