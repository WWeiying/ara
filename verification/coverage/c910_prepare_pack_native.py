"""Exact240 arithmetic native roundtrip with full local/scalar/child guards."""
import argparse
from collections import defaultdict
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

import c910_srt_datapath_native as old
import review_c910_prepare_pack_boundaries as boundary

life,tools,need=old.life,old.tools,old.require
HERE=Path(__file__).resolve().parent
ENTRY=HERE/'c910_prepare_pack_native.tcl'
REVIEW=life.OUT/'c910-prepare-pack-boundary-review762-agent-20261007-01.json'
REVIEW_SHA='96af8d1f80f17d581f74f8dbccc78646f49d742725ca78c431e9e81234a6a486'
STAGES=('initial','apply','reset','reload','final')
ELS=dict(initial='initial-empty.el',apply='first.el',reset='reset-empty.el',
         reload='second.el',final='final-empty.el')


def instances(review):
    need(review['status']=='EXACT_SOURCE_BOUND_240_TARGETS_COMPLEMENT_PREPARED_NATIVE_PENDING' and
         not review['native_qualified'] and not review['whole_module_waiver'], 'Wrong source review')
    grouped={}
    for collection,target in ((review['targets'],True),(review['protected_local_complement'],False),
                               (review['protected_scalar_objects'],False)):
        for row in collection:
            s=row['scope'];n=row['native_shape'];m=row['module']
            i=grouped.setdefault(s,dict(scope=s,module=m,targets=[],objects=[],
                design_checksum=boundary.first.IDENTITY[m][1],
                toggle_checksum=boundary.first.IDENTITY[m][2]))
            i['objects'].append(n)
            if target:i['targets'].append(n)
    for child in review['protected_children']:
        need(child['scope'] not in grouped,'Overlapping child/parent guard')
        grouped[child['scope']]=dict(scope=child['scope'],module=child['module'],targets=[],
            objects=[x['native_shape'] for x in child['objects']],
            design_checksum=child['design_checksum'],toggle_checksum=child['toggle_checksum'])
    result=sorted(grouped.values(),key=lambda i:(not bool(i['targets']),i['module'],i['scope']))
    need(len(result)==82 and sum(len(i['targets']) for i in result)==240 and
         sum(len(i['objects'])-len(i['targets']) for i in result)==3740,
         'Exact82 scopes/240 targets/3740 guards differs')
    for index,i in enumerate(result):
        i['index']=index
        names=[boundary.r.native_name(n) for n in i['objects']]
        need(len(names)==len(set(names)),'Duplicate whole native name')
        i['native_names']=names
    return result


def source_bindings(c):
    review=life.read_bound(REVIEW,REVIEW_SHA)
    need(c['instances']==instances(review),'Config/source shape identity differs')
    ledger=json.loads((life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
    original=life.read_bound(boundary.REVIEW,boundary.SEAL)
    modules={m['module']:m for m in original['modules']}
    bindings={}
    for i in c['instances']:
        for n in i['targets']:
            m=modules[i['module']];path=Path(m['source'])
            need(life.digest(path)==ledger[str(path)]==m['source_sha256'],'Frozen source drift')
            line=path.read_text().splitlines()[int(n['line_num'])-1]
            match=re.fullmatch(r'\s*(wire|reg)\s+\[(\d+):(\d+)\]\s+'+re.escape(n['name'])+r'\s*;\s*',line)
            need(match and match.groups()[1:]==(n['left'],n['right']) and n['portnode']=='0',
                 'Source complete type/bounds differs')
            typ,left,right=match.groups()
            bindings[i['scope'],n['name']]=dict(source=str(path),source_sha256=m['source_sha256'],
                declaration_line=int(n['line_num']),declaration=line,source_type=typ,
                native_type='net' if typ=='wire' else 'reg',left=int(left),right=int(right),
                design_checksum=i['design_checksum'],toggle_checksum=i['toggle_checksum'])
    need(len(bindings)==240,'Source binding exact union differs')
    return bindings


def parse_el(text,c,subset=None):
    bindings=source_bindings(c)
    wanted=set(bindings) if subset is None else set(subset)
    need(wanted<=set(bindings) and wanted,'Unapproved empty/extra subset')
    scope=None;checksum=None;blocks=set();found=defaultdict(list)
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('ANNOTATION:'):
            need(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"',line),'Invalid annotation');continue
        if line.startswith('CHECKSUM:'):
            need(scope is not None or checksum is None,'Consecutive checksum')
            match=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
            need(match,'Bad checksum');checksum=match.groups();scope=None;continue
        if line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip()
            need(scope not in blocks and any(s==scope for s,n in wanted),'Unapproved/duplicate scope')
            b=next(b for (s,n),b in bindings.items() if s==scope)
            need(checksum==(b['design_checksum'],b['toggle_checksum']),'Scope checksum differs')
            blocks.add(scope);continue
        match=re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\w+) "(net|reg) (\w+)\[(\d+):(\d+)\]"',line)
        need(match and scope,'Invalid metric/type/qualifier')
        direction,name,typ,decl,left,right=match.groups();key=scope,name
        need(key in wanted and name==decl,'Protected/unknown/renamed field')
        b=bindings[key]
        need((typ,int(left),int(right))==(b['native_type'],b['left'],b['right']),
             'Native source type/full bounds differs')
        found[key].append(direction)
    need(set(found)==wanted and blocks=={s for s,n in wanted} and scope is not None,
         'Not exact requested whole-object union')
    for key,directions in found.items():
        need(directions==[None] or len(directions)==2 and set(directions)=={'0to1','1to0'},
             'Missing/duplicate/mixed whole and directional pair')
    return sorted((s,n,json.dumps(bindings[s,n],sort_keys=True)) for s,n in found)


def el_text(c):
    b=source_bindings(c);lines=[]
    for i in c['instances']:
        if not i['targets']:continue
        lines+=['CHECKSUM: "%s %s"'%(i['design_checksum'],i['toggle_checksum']),
                'INSTANCE: '+i['scope']]
        for n in i['targets']:
            x=b[i['scope'],n['name']]
            lines.append('Toggle %s "%s %s[%d:%d]"'%(n['name'],x['native_type'],n['name'],x['left'],x['right']))
    return '\n'.join(lines)+'\n'


def inventory(path,i):
    with path.open(newline='') as stream:
        reader=csv.DictReader(stream,delimiter='\t')
        need(reader.fieldnames==['handle','path','meta','name'],'Native TSV schema differs')
        rows=list(reader)
    need(rows and all(set(n)=={'handle','path','meta','name'} and all(n.values()) for n in rows),
         'Incomplete native inventory')
    names=[n['name'] for n in rows]
    need(len(names)==len(set(names))==len(i['objects']) and set(names)==set(i['native_names']),
         'Native exact full object inventory differs: '+i['scope'])
    return sorted((n['path'],n['meta'],n['name']) for n in rows)


def check_stage(out,c,stage):
    need(stage in STAGES,'Unknown stage')
    text=(out/ELS[stage]).read_text()
    if stage in ('apply','reload'):parse_el(text,c)
    else:need(text=='','Global reset/initial EL not empty')
    count=0
    for i in c['instances']:
        rows=inventory(out/('native_%s_%d.tsv'%(stage,i['index'])),i)
        if stage!='initial':
            need(rows==inventory(out/('native_initial_%d.tsv'%i['index']),i),'Native full guard identity changed')
        count+=len(rows)-len(i['targets'])
    need(count==3740,'Exact global checked complement differs')
    return dict(stage=stage,target_objects=240,local_guards=3280,scalar_guards=220,
                child_scopes=48,child_guard_objects=240,all_checked_non_targets=count,global_EL_exact=True)


def selection(c):
    values=dict(pp_design=c['design'],pp_vdb=c['vdb'],pp_test=c['native_test'],
                pp_python=sys.executable,pp_helper=str(Path(__file__).resolve()),
                c910_fma_tcl=str(HERE/'fma_datapath_native.tcl'))
    need(all(v and not any(x in v for x in '{}\\\r\n') for v in values.values()),'Unsafe Tcl path')
    lines=['set ::%s {%s}\n'%x for x in values.items()]+['set ::pp_instances {}\n']
    for i in c['instances']:
        names=' '.join(boundary.r.native_name(n) for n in i['targets'])
        lines.append('lappend ::pp_instances [list {%s} {%s} {%s} %d]\n'%(
            i['scope'],names,' '.join(i['native_names']),i['index']))
    return ''.join(lines)


def configuration():
    review=life.read_bound(REVIEW,REVIEW_SHA);life.check(review['pins'])
    original=life.read_bound(boundary.REVIEW,boundary.SEAL)
    # One representative compatible admitted VDB, not a full-population rerun.
    vdb=life.OUT/'gap84-div32-old-image-20261006-01/code.vdb'
    ledger=(boundary.r.BASE/'combined-inputs.txt').read_text().splitlines()
    need(str(vdb) in ledger,'Capture VDB not admitted762')
    tests=list((vdb/'snps/coverage/db/testdata').iterdir())
    need(len(tests)==1 and tests[0].is_dir(),'Ambiguous representative native test')
    reference=life.read_bound(old.fma.PRODUCT/'config.json',life.digest(old.fma.PRODUCT/'config.json'))
    tools.revalidate(reference['identity'])
    c=dict(schema='C910_PREPARE_PACK_240_NATIVE_V1',instances=instances(review),
        design=str(life.IMAGE)+'.vdb',vdb=str(vdb),native_test=str(vdb.with_suffix('')/tests[0].name),
        identity=reference['identity'],timeout_seconds=1800,objects=240,logical_bits=10896,
        source_review_sha256=REVIEW_SHA,population_application=False,automatic_retry=False)
    source_bindings(c)
    return c,review,original


def prepare(out):
    need(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh independent output required')
    c,review,original=configuration()
    need(life.digest(life.IMAGE)=='2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3','Image drift')
    pins=dict(review['pins']);pins[str(REVIEW)]=REVIEW_SHA
    for path in Path(c['vdb']).rglob('*'):
        if path.is_file():
            need(not path.is_symlink() and path.resolve()==path,'Aliased VDB')
            pins[str(path)]=life.digest(path)
    for path in (Path(__file__).resolve(),ENTRY,HERE/'test_c910_prepare_pack_native.py',
        HERE/'c910_prepare_pack_native_mock.py',HERE/'fma_datapath_native.tcl',
        HERE/'c910_srt_datapath_native_v3.tcl',Path(old.__file__),Path(old.fma.__file__),
        Path(old.one.__file__),Path(old.one.common.__file__),Path(life.__file__),Path(tools.__file__),
        Path(boundary.__file__),Path(boundary.first.__file__),Path(boundary.r.__file__)):
        pins[str(path)]=life.digest(path)
    # Bind actual previous measured wire->net / reg->reg format, read-only.
    prior=life.OUT/'c910-fp16-additional8-native742-agent-20261007-01'
    result=json.loads((prior/'capture-result.json').read_bytes())
    need(result['both_directions'] and result['semantic_reload'] and result['finalreset'],'Prior format not qualified')
    for name in ('capture-result.json','first.el'):
        path=prior/name;pins[str(path)]=life.digest(path)
        if name=='first.el':need(pins[str(path)]==result['pins'][str(path)],'Measured prior EL pin drift')
    actual=(prior/'first.el').read_text()
    need('Toggle cur_rem "reg cur_rem[60:0]"' in actual and
         'Toggle srt_remainder_nxt "net srt_remainder_nxt[60:0]"' in actual,'Prior measured source types differ')
    life.check(pins)
    out.mkdir();c.update(output=str(out),pins=pins)
    (out/'selection.tcl').write_text(selection(c),encoding='ascii')
    (out/'candidate.el').write_text(el_text(c),encoding='ascii')
    parse_el((out/'candidate.el').read_text(),c)
    from c910_prepare_pack_native_mock import qualify
    life.save(out/'plain-tcl-entry-regression.json',qualify(out,c))
    regression=subprocess.run([sys.executable,'-B','-m','unittest','test_c910_prepare_pack_native',
        'test_review_c910_prepare_pack_numeric','test_review_c910_prepare_pack_boundaries','-v'],
        cwd=HERE,text=True,capture_output=True)
    need(regression.returncode==0 and regression.stderr.rstrip().endswith('OK'),
         'Full regressions failed: '+regression.stderr)
    life.save(out/'test-regression.json',dict(returncode=regression.returncode,stdout=regression.stdout,stderr=regression.stderr))
    for name in ('selection.tcl','candidate.el','plain-tcl-entry-regression.json','test-regression.json'):
        pins[str(out/name)]=life.digest(out/name)
    life.check(pins);life.save(out/'config.json',c)
    print(json.dumps(dict(seal=life.digest(out/'config.json'),objects=240,guards=3740)),flush=True)


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    need(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,
         'Actual DVE/terminal failed')
    log=(out/'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('C910_PREPARE_PACK_NATIVE_DONE')==1 and 'C910_PREPARE_PACK_NATIVE_FAILED' not in log,
         'Native session failed; preserve captures')
    stages=[check_stage(out,c,s) for s in STAGES]
    need(parse_el((out/'first.el').read_text(),c)==parse_el((out/'second.el').read_text(),c),
         'Typed EL semantic reload differs')
    need((out/'calibration-reset-empty.el').read_bytes()==b'','Calibration reset not empty')
    calibration=json.loads((out/'calibration-proof.json').read_bytes())
    need(calibration['status']=='ACTUAL_NATIVE_NET_REG_SOURCE_BOUND_CALIBRATION_PASS','Calibration absent')
    if (out/'service.log').exists():shutil.copyfile(out/'service.log',out/'service-output-before-seal.log')
    result=dict(status='EXACT_C910_PREPARE192_PACK48_NATIVE_ROUNDTRIP_PASS',config_seal=seal,
        source_review_sha256=REVIEW_SHA,objects=240,logical_bits=10896,stages=stages,
        both_directions=True,non_target_exclusions=0,semantic_reload=True,reset_global_empty=True,
        all16_vector_cores_source_and_architecture_bound=True,scalar_and_children_retained=True,
        population_application=False,exhaustive_IEEE_validation=False,
        pins={**c['pins'],**{str(p):life.digest(p) for p in out.rglob('*') if p.is_file()
            and p.name!='capture-result.json' and p!=out/'service.log'}})
    life.save(out/'capture-result.json',result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(out/'capture-result.json'))),flush=True)


def run(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins']);tools.revalidate(c['identity'])
    need(c['output']==str(out) and c['objects']==240 and not (out/'execution.json').exists(),'One-shot execution claim differs')
    need(os.environ.get('INVOCATION_ID'),'Independent directly owning systemd service required')
    env=tools.controlled_environment(c['identity'],os.environ);env.pop('DVE',None)
    env.update(DVE_COVERAGE_OUTPUT=str(out),C910_PREPARE_PACK_SEAL=seal)
    command=[c['identity']['roles']['xvfb_run'],'-a','-e',str(out/'xvfb.log'),'-s',
        '-screen 0 1280x1024x24',c['identity']['roles']['launcher'],'-full64','-cov','-script',str(ENTRY)]
    life.save(out/'execution.json',dict(command=command,cwd=str(out),timeout_seconds=c['timeout_seconds'],
        systemd_invocation=os.environ['INVOCATION_ID'],automatic_retry=False))
    with (out/'launcher.log').open('x') as log:
        process=subprocess.Popen(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        time.sleep(10);actual=[]
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():continue
            try:
                if (path/'exe').resolve()==Path(c['identity']['executable']) and (path/'cwd').resolve()==out:
                    actual.append(dict(pid=int(path.name),exe=str((path/'exe').resolve()),cwd=str(out),
                        cgroup=(path/'cgroup').read_text(),command=(path/'cmdline').read_bytes().decode().replace('\0',' ')))
            except OSError:continue
        life.save(out/'live-identity.json',actual);print(json.dumps(dict(actual_dve=actual)),flush=True)
        timeout=False
        try:process.wait(timeout=c['timeout_seconds'])
        except subprocess.TimeoutExpired:
            timeout=True;os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    life.save(out/'terminal.json',dict(returncode=process.returncode,timeout=timeout,actual_dve=actual))
    try:verify(out,seal)
    except Exception as error:
        life.save(out/'qualification-reject.json',dict(status='REJECTED_NOT_QUALIFIED',reason=str(error),
            config_seal=seal,captures_preserved=True,automatic_retry=False));raise


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=('prepare','run','verify','stage','el','calibration'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seal')
    ap.add_argument('--stage',choices=STAGES);ap.add_argument('--file')
    args=ap.parse_args();out=args.output.absolute()
    if args.mode=='prepare':prepare(out)
    else:
        seal=args.seal or os.environ.get('C910_PREPARE_PACK_SEAL')
        need(seal,'Sealed config required');c=life.read_bound(out/'config.json',seal);life.check(c['pins'])
        if args.mode=='stage':print(json.dumps(check_stage(out,c,args.stage)))
        elif args.mode=='el':print(json.dumps(dict(objects=len(parse_el((out/args.file).read_text(),c)))))
        elif args.mode=='calibration':
            chosen=[(i['scope'],n['name']) for i in c['instances'] for n in i['targets']
                if (i['index']==0 and n['name'] in ('ex4_frac','ex4_frac_52')) or
                   (i['index']==16 and n['name']=='ex1_oper0_frac')]
            need(len(chosen)==3,'Exact calibration identities differ')
            parse_el((out/'calibration.el').read_text(),c,chosen)
            need((out/'calibration-reset-empty.el').read_bytes()==b'','Calibration reset absent')
            life.save(out/'calibration-proof.json',dict(status='ACTUAL_NATIVE_NET_REG_SOURCE_BOUND_CALIBRATION_PASS',
                fields=chosen,pins={str(out/'calibration.el'):life.digest(out/'calibration.el')}))
        else:(run if args.mode=='run' else verify)(out,seal)
