"""One local native Toggle qualification of exact reviewed cast numeric objects."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import fma_datapath_native as inherited

life, require, tools = inherited.life, inherited.require, inherited.tools
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT/'fpnew-cast-fp-shared168-candidate745-agent-20261007-01.json'
REVIEW_SHA = '98e76dc52ff69028c6d2466924cb8339b72d8da892ec418d2d5b3a0468e6ca76'
STAGES = ('before','selected','reset','reloaded','final')


def contract(c):
    instances=c['instances']
    require(len(instances)==8 and len({i['scope']for i in instances})==8,'Exact eight scopes')
    require(sum(len(i['targets'])for i in instances)==168 and
            sum(t['logical_bits']for i in instances for t in i['targets'])==9576,'Exact168 numeric objects')
    require(all(i['toggle_checksum']=='400336858' and '.gen_operation_groups[3].'in i['scope']
                and '.gen_num_lanes[%d].'%slot in i['scope']
                for i in instances for slot in [0 if '.gen_num_lanes[0].'in i['scope'] else 1]),'Scope/config role')
    for i in instances:
        names=[t['native_name']for t in i['targets']]+i['protected']
        require(len(names)==len(set(names))==279 and len(i['protected'])==258,'Target/protected complement')


def inventory(out,c,stage,index):
    require(stage in STAGES and 0<=index<8,'Inventory selector')
    with (out/('native_%s_%d.tsv'%(stage,index))).open(newline='') as stream:
        table=list(csv.reader(stream,delimiter='\t'))
    require(table and table[0]==['handle','path','meta','name'] and
            all(len(r)==4 and all(r) for r in table[1:]),'Invalid native rows')
    rows=[tuple(r[1:])for r in table[1:]]
    require(len(rows)==len(set(rows)) and rows,'Duplicate/empty identities')
    names=[r[2]for r in rows]; i=c['instances'][index]
    required=[t['native_name']for t in i['targets']]+i['protected']
    require(all(names.count(n)==1 for n in required),'Missing/ambiguous target or protection')
    return sorted(rows)


def parse_el(text,c,native_meta=None):
    expected={i['scope']:i for i in c['instances']};scope=checksum=None;found={}
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"',line),'Invalid annotation')
        elif line.startswith('CHECKSUM:'):
            m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
            require(m is not None,'Checksum syntax');checksum=m.groups();scope=None
        elif line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip()
            require(scope in expected and checksum==('1144939760',expected[scope]['toggle_checksum']),
                    'Unapproved scope/checksum')
        else:
            m=re.fullmatch(r'Toggle (\w+) "((?:logic|reg|wire|net)(?: signed)? \w+(?:\[-?\d+:-?\d+\])+)"',line)
            require(scope is not None and m is not None,'Unexpected metric/direction/object syntax: '+line)
            name,meta=m.groups();target=next((t for t in expected[scope]['targets']if t['name']==name),None)
            require(target is not None,'Protected or extra object')
            suffix=meta.split(' ',2)[-1] if ' signed 'in meta else meta.split(' ',1)[1]
            require(suffix==target['native_name'],'Wrong full array/vector signature')
            key=(scope,name);require(key not in found,'Duplicate target')
            if native_meta is not None:require(native_meta[key]==meta,'Native metadata signature differs')
            found[key]=(checksum,meta)
    wanted={(i['scope'],t['name'])for i in c['instances']for t in i['targets']}
    require(set(found)==wanted and len(found)==168,'Incomplete/extra168')
    return sorted((scope,name,*value[0],value[1])for (scope,name),value in found.items())


def inspect(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,
            'Actual executable/terminal')
    gui=(out/'DVEfiles/dve_gui.log').read_text(errors='strict')
    require(gui.splitlines().count('CAST168_NATIVE_DONE')==1 and 'CAST168_NATIVE_FAILED'not in gui,
            'Five stages not complete')
    meta={}
    for index,i in enumerate(c['instances']):
        before=inventory(out,c,'before',index)
        for stage in STAGES[1:]:require(inventory(out,c,stage,index)==before,'Target/protection identity drift')
        byname={r[2]:r[1]for r in before}
        for t in i['targets']:meta[i['scope'],t['name']]=byname[t['native_name']]
    first=parse_el((out/'first.el').read_text(),c,meta)
    require(first==parse_el((out/'second.el').read_text(),c,meta),'Semantic reload differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes()==b'','Global reset EL not empty')
    pins=life.merge_pins(c['pins'],{str(p):life.digest(p)for p in out.rglob('*')if p.is_file()
                                   and p.name not in ('worker.log','capture-result.json')})
    result=dict(status='EXACT_CAST168_FIVE_STAGE_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=seal,
        objects=168,logical_bits=9576,protected_local_objects=2064,exact_EL_semantics=True,
        both_directions_whole_objects=True,semantic_reload=True,global_final_reset_empty=True,
        all_children_retained=True,baseline_evidence=745,official_percentage=None,
        exhaustive_IEEE=False,population_application=False,pins=pins)
    life.save(out/'capture-result.json',result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(out/'capture-result.json'))),flush=True)


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh independent output')
    review=life.read_bound(REVIEW,REVIEW_SHA);life.check(review['pins'])
    origin=Path(review['inventory400']);source=life.read_bound(origin,review['pins'][str(origin)])
    life.check(source['pins']);instances=[]
    for i in review['candidate_instances']:
        full=next(x for x in source['instances']if x['scope']==i['scope'])
        targets={t['name']for t in i['targets']}
        protected=[t['native_name']for t in full['targets']+full['protected']if t['name']not in targets]
        instances.append(dict(i,protected=protected))
    c=dict(instances=instances);contract(c)
    pins=life.merge_pins(review['pins'],source['pins'])
    pins=life.merge_pins(pins,{str(REVIEW):REVIEW_SHA})
    config=json.loads((inherited.PRODUCT/'config.json').read_bytes());identity=config['identity']
    tools.revalidate(identity)
    pins=life.merge_pins(pins,{str(inherited.PRODUCT/'config.json'):life.digest(inherited.PRODUCT/'config.json')})
    vdb=Path(source['evidence'][1]['vdb']);dirs=list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(dirs)==1 and dirs[0].is_dir(),'One admitted conversion VDB')
    for p in [*vdb.rglob('*'),Path(__file__).resolve(),HERE/'capture_cast168_native.tcl',
              HERE/'test_capture_cast168_native.py',HERE/'fma_datapath_native.tcl',
              Path(inherited.__file__).resolve(),Path(life.__file__).resolve(),Path(tools.__file__).resolve()]:
        if p.is_file():pins=life.merge_pins(pins,{str(p):life.digest(p)})
    out.mkdir()
    values=dict(fma_design=str(life.IMAGE)+'.vdb',fma_vdb=str(vdb),
        fma_test=str(vdb.with_suffix('')/dirs[0].name),fma_python=str(life.ROOT/'verification/tools/soc-venv/bin/python'),
        fma_helper=str(Path(__file__).resolve()),cast_primitives=str(HERE/'fma_datapath_native.tcl'))
    require(all(not any(ch in v for ch in '{}\\\r\n')for v in values.values()),'Unsafe Tcl value')
    lines=['set %s {%s}\n'%pair for pair in values.items()]+['set fma_instances {}\n']
    for idx,i in enumerate(instances):
        lines.append('lappend fma_instances [list {%s} {%s} {%s} %d]\n'%
                     (i['scope'],' '.join(t['native_name']for t in i['targets']),' '.join(i['protected']),idx))
    (out/'selection.tcl').write_text(''.join(lines))
    pins[str(out/'selection.tcl')]=life.digest(out/'selection.tcl');life.check(pins)
    c.update(output=str(out),pins=pins,identity=identity,timeout_seconds=900,automatic_retry=False,
             population_application=False,source_review_seal=REVIEW_SHA)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins))),flush=True)


def run(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins'])
    require(c['output']==str(out) and c['timeout_seconds']==900 and not (out/'execution.json').exists(),'One-shot identity/budget')
    tools.revalidate(c['identity']);env=tools.controlled_environment(c['identity'],os.environ)
    env.pop('DVE',None);env['DVE_COVERAGE_OUTPUT']=str(out)
    cmd=[shutil.which('xvfb-run'),'-a','-e',str(out/'xvfb.log'),'-s','-screen 0 1280x1024x24',
         c['identity']['roles']['launcher'],'-full64','-cov','-script',str(HERE/'capture_cast168_native.tcl')]
    life.save(out/'execution.json',dict(command=cmd,cwd=str(out),timeout_seconds=900,automatic_retry=False))
    try:
        with (out/'launcher.log').open('x') as log:
            process=subprocess.Popen(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            time.sleep(10);actual=[]
            for p in Path('/proc').iterdir():
                if not p.name.isdigit():continue
                try:
                    if (p/'exe').resolve()==Path(c['identity']['executable']) and (p/'cwd').resolve()==out:
                        actual.append(dict(pid=int(p.name),exe=str((p/'exe').resolve()),cwd=str(out)))
                except OSError:continue
            life.save(out/'live-identity.json',actual);print(json.dumps(dict(actual_dve=actual)),flush=True)
            timeout=False
            try:process.wait(timeout=900)
            except subprocess.TimeoutExpired:
                timeout=True;os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        life.save(out/'terminal.json',dict(returncode=process.returncode,timeout=timeout,actual_dve=actual))
        inspect(out,seal)
    except Exception as exc:
        life.save(out/'qualification-hold.json',dict(status='HOLD_NOT_APPLIED',reason=str(exc),population_application=False))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','inspect','el','inventory'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--file');p.add_argument('--stage');p.add_argument('--index',type=int)
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('el','inventory'):
        c=json.loads((out/'config.json').read_bytes())
        if a.mode=='el':
            require(a.file in ('first.el','second.el'),'EL filename');print(len(parse_el((out/a.file).read_text(),c)))
        else:print(len(inventory(out,c,a.stage,a.index)))
    else:
        require(a.seal,'Exact seal required');(run if a.mode=='run'else inspect)(out,a.seal)
