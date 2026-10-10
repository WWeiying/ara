"""Native03 uses only the complete sealed RVFI02 compiled/native bijection."""
import argparse
import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

import capture_system_rvfi788 as core
import system_rvfi_native_binding as mapping

life,require=core.life,core.require
HERE=Path(__file__).resolve().parent
HOOK=HERE/'capture_system_rvfi788_v3.tcl'
BINDING=life.OUT/'system-rvfi02-native-binding-agent-20261007-01.json'
BINDING_SHA='c43239e8e531a078b77cf781e38e6edcb0a8629d0243afd973b9900d24e4543e'


def contract(c):
    b=life.read_bound(BINDING,BINDING_SHA)
    require(c['binding_sha256']==BINDING_SHA and c['native_bindings']==b['bindings'] and
        c['origin_metadata']==b['native_identity_rows'] and c['module_checksum']==b['module_checksum'] and
        c['source_review_sha256']==b['source_review_sha256'],'Sealed full native binding differs')
    require({p['signal'] for p in c['targets']}=={p['compiled_name'] for p in b['bindings'] if p['role']=='target'} and
        len(c['targets'])==788 and len(c['protected'])==418,'Source target/complement differs')
    return b


def inventory(out,c,stage):
    contract(c)
    rows=mapping.parse(out/('native_'+stage+'.tsv'),c['native_bindings'],stage)
    require(rows==[tuple(p) for p in c['origin_metadata']], 'Fresh full path/meta/name differs from sealed02')
    return rows


def records(text,c):
    contract(c);wanted={p['signal']:p for p in c['targets']}
    aliases={p['compiled_name']:p for p in c['native_bindings'] if p['role']=='target'}
    checksum=None;scope=None;annotation=None;blocks=0;found={}
    for line in text.splitlines():
        require(line!='','Empty native directive')
        m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
        if m:
            require(checksum is None,'Duplicate checksum block');checksum=m.groups();continue
        m=re.fullmatch(r'INSTANCE:\s*(\S+)',line)
        if m:
            scope=m[1];blocks+=1
            require(blocks==1 and scope==core.review.SCOPE and checksum==(c['module_checksum'],'3385959260'),
                'Foreign scope/checksum/instance exclusion');continue
        m=re.fullmatch(r'ANNOTATION: "([^"\r\n]*)"',line)
        if m:
            require(m[1]==core.ANNOTATION,'Annotation differs');annotation=m[1];continue
        m=re.fullmatch(r'Toggle (\S+) "(net|wire|logic|reg) (\S+)"',line)
        require(m is not None and scope is not None and annotation==core.ANNOTATION,'Unknown/incomplete native directive')
        name,kind,decl=m.groups();p=wanted.get(name)
        require(p is not None and kind in ('net','wire','logic'),'Protected/foreign or non-net object')
        binding=aliases[name];allowed={binding['compiled_label']}
        if name in mapping.TARGET_SCALARS:
            require(binding['compiled_kind']=='vectornode' and
                binding['compiled_attributes']['left']==binding['compiled_attributes']['right']=='0',
                'Explicit scalar alias source bounds differ')
            allowed.add(binding['observed_label'])
        require(decl in allowed,'Wrong full bounds/direction or unreviewed scalar alias')
        require(name not in found,'Duplicate native object')
        # Both representations identify the same sole compiled bit, only for the 11 explicit aliases.
        found[name]=(scope,*checksum,kind,binding['compiled_label'],annotation)
    require(blocks==1 and len(found)==788 and set(found)==set(wanted),'Not exact788 native objects')
    return sorted((name,*value) for name,value in found.items())


def prepare(out):
    b=life.read_bound(BINDING,BINDING_SHA);life.check(b['pins'])
    require(b['status']=='RVFI02_FULL1206_OFFLINE_TYPED_NATIVE_BINDING_VERIFIED_NOT_EXCLUSION_QUALIFICATION' and
        b['targets']==788 and b['protected']==418 and b['target_scalar_aliases']==11 and b['protected_scalar_aliases']==30,
        'Wrong complete native binding')
    r=life.read_bound(core.REVIEW,core.REVIEW_SHA)
    require(mapping.bindings(r)==b['bindings'],'Compiled/source binding reconstruction differs')
    require(mapping.parse(mapping.ORIGIN/'native_before.tsv',b['bindings'])==[tuple(p) for p in b['native_identity_rows']],
        'Preserved native02 inventory differs')
    deps=(Path(__file__).resolve(),HERE/'test_capture_system_rvfi788_v3.py',Path(core.__file__).resolve(),core.HOOK,
        HERE/'capture_system_rvfi788_v2.py',HERE/'capture_system_rvfi788_v2.tcl',
        HERE/'test_capture_system_rvfi788_v2.py',HERE/'export_dve_coverage.tcl')
    pins=life.merge_pins(b['pins'],{str(BINDING):BINDING_SHA})
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in deps})
    def save(path,value):
        if path==out/'config.json':
            require(value['targets']==r['targets'],'Original source targets changed')
            value.update(binding_sha256=BINDING_SHA,native_bindings=b['bindings'],origin_metadata=b['native_identity_rows'],
                predecessor_failures_preserved=[str(life.OUT/'system-rvfi788-native-agent-20261007-01'),str(mapping.ORIGIN)])
            labels=[p['observed_label'] for p in b['bindings'] if p['role']=='target']
            require(len(labels)==len(set(labels))==788,'Ambiguous native capture labels')
            selection='set rvfi03_targets [list '+' '.join('{'+label+'}' for label in labels)+']\n'
            core.scalar.launch.primitive.one.common.save(out/'native-binding-selection.tcl',selection)
            merged=life.merge_pins(value['pins'],pins)
            merged=life.merge_pins(merged,{str(out/'native-binding-selection.tcl'):life.digest(out/'native-binding-selection.tcl')})
            value['pins'].update(merged);contract(value);life.check(value['pins'])
        life.save(path,value)
    private=SimpleNamespace(**dict(vars(life),save=save))
    worker=FunctionType(core.prepare.__code__,dict(core.prepare.__globals__,life=private,HOOK=HOOK,__file__=__file__))
    worker(out)


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c)
    def save(path,value):
        if path==out/'capture-result.json':
            value.update(binding_sha256=BINDING_SHA,complete1206_metadata_matches_sealed02=True,
                before_any_exclude_bijection_verified=True,explicit_target_aliases=11,explicit_protected_aliases=30)
        life.save(path,value)
    private=SimpleNamespace(**dict(vars(life),save=save))
    worker=FunctionType(core.verify.__code__,dict(core.verify.__globals__,life=private,records=records,inventory=inventory))
    worker(out,seal)


def run(out,seal):
    worker=FunctionType(core.scalar.launch.run.__code__,dict(core.scalar.launch.run.__globals__,verify=verify))
    worker(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','verify','el','inventory'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--file',choices=('first.el','second.el'))
    p.add_argument('--stage');a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('el','inventory'):
        c=json.loads((out/'config.json').read_bytes());life.check(c['pins'])
        if a.mode=='el':require(a.file,'EL required');print('EXACT788 '+str(len(records((out/a.file).read_text(),c))))
        else:print('SEALED_FULL1206 '+str(len(inventory(out,c,a.stage))))
    else:
        require(a.seal,'Config seal required');(run if a.mode=='run' else verify)(out,a.seal)
