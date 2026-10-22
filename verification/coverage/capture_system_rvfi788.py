"""Exact parent RVFI observation-only native qualification; no population application."""
import argparse
import csv
import json
from pathlib import Path
import re
import shutil
import sys
import types

import review_system_rvfi_toggle762 as review
import capture_scalar_radix158 as scalar

life, require, tools = scalar.life, scalar.require, scalar.tools
HERE=Path(__file__).resolve().parent
REVIEW=life.OUT/'system-rvfi-toggle-source-review762-agent-20261007-01.json'
REVIEW_SHA='ad3c6b81cead4ae594f270f4bbf5b459e312770cd8d7aaa853e21f0dae3581b3'
BASE=life.OUT/'operand-mask-data-defined-policy-admitted763-agent-20261007-01'
HOOK=HERE/'capture_system_rvfi788.tcl'
ANNOTATION='Observation-only parent RVFI net; full typed complements retained'


def records(text,c):
    wanted={p['signal']:p for p in c['targets']};found={};scope=None;checksum=None;block=0;annotation=None
    for line in text.splitlines():
        require(line!='','Empty native directive')
        m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
        if m:
            require(checksum is None,'Duplicate native checksum');checksum=m.groups();continue
        m=re.fullmatch(r'INSTANCE:\s*(\S+)',line)
        if m:
            block+=1;scope=m[1]
            require(block==1 and scope==review.SCOPE and checksum==(c['module_checksum'],'3385959260'),
                'Foreign instance/checksum/scope exclusion');continue
        m=re.fullmatch(r'ANNOTATION: "([^"\r\n]*)"',line)
        if m:
            require(m[1]==ANNOTATION,'Annotation differs');annotation=m[1];continue
        m=re.fullmatch(r'Toggle (\S+) "(wire|net|logic|reg) (\S+)"',line)
        require(m is not None and scope is not None and annotation==ANNOTATION,'Unknown/incomplete native directive')
        name,kind,decl=m.groups();p=wanted.get(name)
        require(p is not None and decl==p['native_name'] and kind in ('wire','net','logic'),
            'Protected field, partial bounds, direction or non-net type excluded')
        require(name not in found,'Duplicate native object');found[name]=(scope,*checksum,kind,decl,annotation)
    require(block==1 and len(found)==len(wanted)==788 and set(found)==set(wanted),'Not exact788 native objects')
    return sorted((name,*value) for name,value in found.items())


def matches(meta,name,p):
    # Exact scalar/vector names. Arrays remain whole protected containers, never targets.
    if p['kind']!='arrays':return p['label'] in (meta,name)
    base=p['attributes']['name']
    return any(v==base or (v.startswith(base+'[') and re.fullmatch(r'(?:\[[0-9]+(?::[0-9]+)?\])+',v[len(base):])) for v in (meta,name))


def inventory(out,c,stage):
    require(stage in ('before','selected','reset','reloaded','final'),'Unknown inventory stage')
    with (out/('native_'+stage+'.tsv')).open() as f:
        reader=csv.DictReader(f,delimiter='\t');require(reader.fieldnames==['handle','path','meta','name','excluded'],'Wrong native inventory header')
        rows=list(reader)
    require(rows and all(set(p)==set(reader.fieldnames) and p['handle'] and p['path'] and p['name'] and
        p['excluded'] in ('0','1') for p in rows),'Malformed native rows')
    require(len({p['path'] for p in rows})==len(rows),'Duplicate native path')
    targets={p['native_name']:p for p in c['targets']};seen={};active=stage in ('selected','reloaded')
    for row in rows:
        names=[label for label in targets if label in (row['meta'],row['name'])]
        require(len(names)<=1,'Ambiguous target metadata')
        if names:
            label=names[0];require(label not in seen,'Duplicate native target');seen[label]=row
            require(row['excluded']==str(int(active)),'Target exclusion state differs')
    require(set(seen)==set(targets),'Missing native targets')
    for p in c['protected']:
        hits=[row for row in rows if matches(row['meta'],row['name'],p)]
        require(hits,'Missing full typed protection: '+p['attributes']['name'])
        require(p['kind']=='arrays' or len(hits)==1,'Duplicate typed protected object')
        require(all(row['excluded']=='0' for row in hits),'Protected object excluded: '+p['attributes']['name'])
    return [(p['path'],p['meta'],p['name']) for p in rows]


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh output required')
    r=life.read_bound(REVIEW,REVIEW_SHA);life.check(r['pins'])
    require(r['candidate_objects']==788 and r['candidate_bits']==22126 and r['protected_objects']==418 and
        r['all_arrays_protected'] and not r['source_contract']['hardware_feedback'],'Wrong reviewed observer partition')
    basepath=BASE/'admission-manifest.json';base_sha=life.digest(basepath);base=life.read_bound(basepath,base_sha)
    bpath=BASE/'combined-bits.json';bsha=base['output_pins'][str(bpath)];b=life.read_bound(bpath,bsha)
    require(len(b['tests'])==len(set(b['tests']))==763,'Not explicit formal763 context')
    old_bitmap=review.frozen.BASE/'combined-bits.json'
    old=life.read_bound(old_bitmap,r['pins'][str(old_bitmap)])
    require(b['tests'][:762]==old['tests'],'Formal763 prefix differs from reviewed762')
    compiled_pins={}
    for relative,sha in b['design'].items():
        p=scalar.fixture.old.BUILD/'sim/simv.vdb/snps/coverage/db'/relative
        require(life.digest(p)==sha and (str(p) not in r['pins'] or r['pins'][str(p)]==sha),
            'Formal763 compiled shape differs')
        compiled_pins[str(p)]=sha
    qpath=scalar.fixture.QUAL/'qualification.json';q=life.read_bound(qpath,scalar.QUAL_SHA)
    pins=life.merge_pins(r['pins'],life.merge_pins(q['input_pins'],q['output_pins']))
    pins=life.merge_pins(pins,compiled_pins)
    pins=life.merge_pins(pins,{str(REVIEW):REVIEW_SHA,str(qpath):scalar.QUAL_SHA,str(basepath):base_sha,str(bpath):bsha})
    protected=[]
    for p in r['protected']:
        a=p['attributes'];label=a['name']
        if p['kind']=='vectornode':label+='[%s:%s]'%(a['left'],a['right'])
        protected.append(dict(p,label=label))
    targets=r['targets'];require(len({p['native_name'] for p in targets})==788,'Ambiguous labels')
    identity=tools.prepare(shutil.which('dve'),'/usr/bin/xvfb-run')
    deps=[Path(__file__).resolve(),HOOK,HERE/'test_capture_system_rvfi788.py',Path(scalar.__file__).resolve(),
        Path(scalar.launch.__file__).resolve(),Path(tools.__file__).resolve(),
        HERE/'qualify_dwc_points742.tcl',HERE/'fsm741_transition_batch.tcl',HERE/'fsm741_native_singleton.tcl',
        HERE/'fsm741_native_probe.tcl',HERE/'discover_ptw_pmp0_fsm_v2.tcl',HERE/'apply_points740_v4.tcl']
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in deps})
    pins=life.merge_pins(pins,{f['path']:f['sha256'] for f in identity['files']});life.check(pins)
    design=scalar.fixture.old.BUILD/'sim/simv.vdb';vdb=scalar.fixture.RUN/'code.vdb'
    tests=list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(tests)==1 and tests[0].name=='scalar_divsqrt_finite','Historical PASS sample differs')
    values=dict(rvfi_design=str(design),rvfi_sample=str(vdb),rvfi_test=str(vdb.with_suffix('')/tests[0].name),
        rvfi_python=sys.executable,rvfi_helper=str(Path(__file__).resolve()),rvfi_scope=review.SCOPE)
    atom=lambda s:'{'+s+'}'
    require(all(not any(ch in value for ch in '{}\\\n\r') for value in values.values()),'Unsafe Tcl atom')
    selection=''.join('set '+key+' '+atom(value)+'\n' for key,value in values.items())
    selection+='set rvfi_targets [list '+' '.join(atom(p['native_name']) for p in targets)+']\n'
    c=dict(identity=identity,pins=pins,targets=targets,protected=protected,
        module_checksum=r['compiled_module']['chksum'],selected=values['rvfi_test'],context_population=763,
        source_review_sha256=REVIEW_SHA,population_application=False,automatic_retry=False,timeout_seconds=600)
    out.mkdir()
    for name,text in (('selection.tcl',selection),('capture.tcl',HOOK.read_text())):
        scalar.launch.primitive.one.common.save(out/name,text);pins[str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins),objects=788,protected=418)),flush=True)


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins']);tools.revalidate(c['identity'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Native terminal failed')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('SYSTEM_RVFI788_NATIVE_DONE')==1 and
        gui.splitlines().count('SYSTEM_RVFI788_SELECTED '+c['selected'])==1 and
        not re.search(r'Error:|Fatal:|EK-CMD-|DVTC[0-9]+|UCAPI-DLMA|DVCDT136|SYSTEM_RVFI788_FAILED',gui),'Native GUI/load failure')
    require(records((out/'first.el').read_text(),c)==records((out/'second.el').read_text(),c),'Native identity/type/attribute roundtrip differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        require((out/name).read_bytes()==b'','Global exclusions not empty')
    before=inventory(out,c,'before')
    for stage in ('selected','reset','reloaded','final'):
        require(inventory(out,c,stage)==before,'Native full target/complement metadata drift')
    result=dict(status='SYSTEM_RVFI788_NATIVE_ROUNDTRIP_QUALIFIED_NOT_POPULATION_APPLICATION',config_seal=seal,
        source_review_sha256=REVIEW_SHA,objects=788,bits=22126,protected_objects=418,all_arrays_ports_control_protected=True,
        semantic_reload=True,finalreset=True,non_target_exclusions=0,population_application=False,official_denominator=False,
        pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in out.rglob('*') if p.is_file()}))
    life.check(result['pins']);life.save(out/'capture-result.json',result)
    print('QUALIFIED '+life.digest(out/'capture-result.json'),flush=True)


def run(out,seal):
    worker=types.FunctionType(scalar.launch.run.__code__,dict(scalar.launch.run.__globals__,verify=verify))
    worker(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','verify','el','inventory'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--file',choices=('first.el','second.el'))
    p.add_argument('--stage');a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('el','inventory'):
        c=json.loads((out/'config.json').read_bytes());life.check(c['pins'])
        if a.mode=='el':require(a.file,'EL required');print('EXACT788 '+str(len(records((out/a.file).read_text(),c))))
        else:print('FULL_NATIVE_INVENTORY '+str(len(inventory(out,c,a.stage))))
    else:
        require(a.seal,'Config seal required');(run if a.mode=='run' else verify)(out,a.seal)
