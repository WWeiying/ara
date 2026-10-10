"""Exact816 PMP binary fields only; full typed complement, no MDA exclusion."""
import argparse
import json
from pathlib import Path
import re
import sys
from types import FunctionType, SimpleNamespace
import xml.etree.ElementTree as ET

import soc_constants61_native as old
import soc_constants61_native_v2 as aliases
import audit_pmp_constants794_static_v2 as proof

life,need=old.life,old.need
HERE=Path(__file__).resolve().parent
TCL=HERE/'pmp_constants816_native.tcl'
SOURCE=life.OUT/'pmp-unused-entries794-static-agent-20261008-02.json'
SOURCE_SHA='88d09c5fd376db8a3c8426fe320245b1e3f9dd17ebde3ff1c4e8ba89f59862b4'
SCHEMA='PMP_CONSTANTS816_LOCAL_NATIVE_PREPARED_V1'
ANNOTATION='Frozen NrPMPEntries0 reset-settled binary constant aliases only; MDA, dynamic d, initial unknowns and all other objects retained'
STAGES=old.STAGES


def labels(i):
    return [s['name'] if s['kind']=='node' else s['name']+'[%d:%d]'%(s['left'],s['right']) for s in i['signals']]


def bind(i,text):
    indexed=SimpleNamespace(**dict(vars(old.primitive.indexed),Resolver=aliases.Resolver))
    primitive=SimpleNamespace(**dict(vars(old.primitive),indexed=indexed))
    fn=old.frozen.bind
    return FunctionType(fn.__code__,dict(fn.__globals__,primitive=primitive,labels=labels))(i,text)


def instances(q):
    need(q['status']=='PMP0_DIRECT_CONSTANT_ALIASES794_STATIC_NOT_NATIVE_APPROVED' and
         q['population']==794 and q['admission_seal']==proof.old.SEAL and q['existing_EL_population']==791 and
         q['EDA_started'] is False and q['EL_generated'] is False and q['target_MDA']==0 and
         q['proof']['actual_NrPMPEntries']==0 and len(q['fresh_candidates'])==816 and len(q['HOLD'])==13,
         'Closed source proof, not a native qualification')
    texts={}
    for rel in proof.old.FILES:
        p=proof.old.ROOT/rel;need(life.digest(p)==q['input_pins'][str(p)],'Frozen PMP source')
        texts[p.name]=p.read_text()
    need(q['complete_reflection_writer_closure']==json.loads(json.dumps(proof.writer_guard(texts))),
         'Complete source writer closure, canonical sealed JSON')
    db=Path(str(life.IMAGE)+'.vdb')/'snps/coverage/db'
    trees=[proof.old.base.t.xml(db/r) for r in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')]
    result={};seen=set()
    owned={(r['scope'],r['compiled']['name']) for r in q['already_owned']}
    for r in q['fresh_candidates']:
        scope,name=r['scope'],r['compiled']['name'];key=(scope,name)
        need(key not in seen and key not in owned and r['constant']=='0' and
             r['initial_X_qualified'] is False and r['native_qualified'] is False,'No duplicate/old owner/X claim')
        seen.add(key)
        if scope not in result:
            checks,defs=proof.old.base.t.definitions(*trees,[scope]);d=defs[scope]
            need(d['module']==r['module'] and checks[scope]==r['checksum'],'Exact source scope/module/checksum')
            result[scope]=dict(scope=scope,design_module_checksum=d['module']['chksum'],toggle_checksum=checks[scope],
                              typed_objects=[dict(kind=n.tag,**n.attrib) for n in ET.fromstring(d['shape']).find('tglshape')],signals=[])
        i=result[scope];nodes=[n for n in i['typed_objects'] if n['name']==name]
        need(len(nodes)==1,'Unique compiled field');n=nodes[0]
        need(n['kind'] in ('node','vectornode') and n['type']=='1' and n['portnode'] in ('0','2','3') and
             all(r['compiled'].get(k)==v for k,v in n.items() if k!='kind') and
             set(r['compiled'])==(set(n)-{'kind'})|{'serialized_offset','logical_width','missing_coordinates','missing_slots'}
             and r['module']['chksum']==i['design_module_checksum'] and r['checksum']==i['toggle_checksum'],
             'Exact binary kind/type/port/source; MDA excluded')
        s=dict(name=name,kind=n['kind'])
        if n['kind']=='vectornode':s.update(left=int(n['left']),right=int(n['right']))
        width=1 if n['kind']=='node' else abs(s['left']-s['right'])+1
        need(r['compiled']['logical_width']==width and r['compiled']['missing_slots']==2*width,'Complete missing binary directions')
        i['signals'].append(s)
    kinds=[s['kind'] for i in result.values() for s in i['signals']]
    need(len(result)==8 and kinds.count('node')==544 and kinds.count('vectornode')==272,'Exact816 binary registry')
    return list(result.values())


def candidate(ii):
    lines=[]
    for i in ii:
        lines+=['CHECKSUM: "%s %s"'%(i['design_module_checksum'],i['toggle_checksum']),
                'INSTANCE: '+i['scope'],'ANNOTATION: "'+ANNOTATION+'"']
        for s,label in zip(i['signals'],labels(i)):lines.append('Toggle '+s['name']+' "logic '+label+'"')
    return '\n'.join(lines)+'\n'


def el_gate(text,c):
    ii={i['scope']:i for i in c['instances']};scope=None;checksum=None;headers=set();annotations=set();actual={}
    allowed={(i['design_module_checksum'],i['toggle_checksum']) for i in ii.values()}
    for line in map(str.strip,text.splitlines()):
        if not line or line.startswith('//'):continue
        m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
        if m:
            checksum=m.groups();need(checksum in allowed,'Unknown checksum including empty block');scope=None;continue
        m=re.fullmatch(r'INSTANCE: (\S+)',line)
        if m:
            scope=m.group(1)
            need(scope in ii and checksum==(ii[scope]['design_module_checksum'],ii[scope]['toggle_checksum']),'Exact scope/checksum tuple')
            headers.add(scope);continue
        if line.startswith('ANNOTATION:'):
            need(scope in ii and line=='ANNOTATION: "'+ANNOTATION+'"','Exact scope annotation');annotations.add(scope);continue
        m=re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) "logic (\S+)"',line)
        need(m is not None and scope in ii,'Only exact whole binary Toggle declaration')
        direction,name,signature=m.groups()
        targets=dict(zip([s['name'] for s in ii[scope]['signals']],labels(ii[scope])))
        need(name in targets and signature==targets[name],'Exact scalar/vector full range; no MDA/alias/partial')
        n=next(n for n in ii[scope]['typed_objects'] if n['name']==name)
        need(n['kind'] in ('node','vectornode') and n['type']=='1' and n['portnode'] in ('0','2','3'),'Compiled binary type/role')
        key=(scope,checksum,name,signature);dirs={direction} if direction else {'0to1','1to0'}
        need(not actual.get(key,set())&dirs,'Duplicate direction');actual.setdefault(key,set()).update(dirs)
    wanted={(i['scope'],(i['design_module_checksum'],i['toggle_checksum']),s['name'],label)
            for i in ii.values() for s,label in zip(i['signals'],labels(i))}
    need(headers==annotations==set(ii) and set(actual)==wanted and all(d=={'0to1','1to0'} for d in actual.values()),
         'Complete exact816 whole both-direction members')
    return sorted(wanted)


def stage_gate(i,before,actual,stage):
    return FunctionType(old.stage_gate.__code__,dict(vars(old),labels=labels))(i,before,actual,stage)


def inherited(name):
    return FunctionType(getattr(old,name).__code__,dict(vars(old),__file__=__file__,TCL=TCL,
        bind=bind,labels=labels,stage_gate=stage_gate,before_gate=before_gate,el_gate=el_gate))


def before_gate(out,c):return [bind(i,(out/('native_before_%d.tsv'%index)).read_text()) for index,i in enumerate(c['instances'])]
def selection(c):return inherited('selection')(c)
def host_hook(c,text,el):return inherited('host_hook')(c,text,el)


def check(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins'])
    need(c['schema']==SCHEMA and c['output']==str(out) and c['source_sha']==SOURCE_SHA and c['timeout_seconds']==5400 and
         c['population_application'] is False and c['automatic_retry'] is False,'Closed local context')
    need(c['instances']==instances(life.read_bound(SOURCE,SOURCE_SHA)),'Exact source/compiled complete inventory')
    old.primitive.old.frozen.tools.revalidate(c['identity'])
    for p,h in old.frozen.tcl_pins(TCL).items():need(c['pins'].get(p)==h,'Transitive sourced Tcl pinned')
    el_gate((out/'candidate.el').read_text(),c)
    return c


def prepare(out):
    need(out.parent==life.OUT and not out.exists(),'Fresh local output only')
    q=life.read_bound(SOURCE,SOURCE_SHA);life.check(q['input_pins']);ii=instances(q)
    template=life.read_bound(old.primitive.old.RUN/'config.json',old.primitive.old.SEAL)
    pins=life.merge_pins(q['input_pins'],template['pins']);pins[str(SOURCE)]=SOURCE_SHA
    pins[str(old.primitive.old.RUN/'config.json')]=old.primitive.old.SEAL
    for module in list(sys.modules.values()):
        p=getattr(module,'__file__',None)
        if p and Path(p).resolve().parent==HERE:pins[str(Path(p).resolve())]=life.digest(p)
    pins.update(old.frozen.tcl_pins(TCL));pins[str(HERE/'test_pmp_constants816_native.py')]=life.digest(HERE/'test_pmp_constants816_native.py')
    c=dict(schema=SCHEMA,output=str(out),source_sha=SOURCE_SHA,timeout_seconds=5400,source_population=794,
           population_application=False,automatic_retry=False,instances=ii,pins=pins,
           target_scalars=544,target_vectors=272,target_MDA=0,source_MDA_HOLD=13,target_bits=1088,target_directions=2176,
           protected_objects=sum(len(i['typed_objects'])-len(i['signals']) for i in ii),
           **{k:template[k] for k in ('design','vdb','test','identity')})
    el=candidate(ii);el_gate(el,c);text=selection(c);host=host_hook(c,text,el);life.check(pins)
    out.mkdir()
    for name,data in (('candidate.el',el),('selection.tcl',text),('native-bind.tcl',TCL.read_text())):
        (out/name).write_text(data);c['pins'][str(out/name)]=life.digest(out/name)
        if name.endswith('.tcl'):old.primitive.check_generated_tcl.check(out/name)
    life.save(out/'host-evidence.json',host);c['pins'][str(out/'host-evidence.json')]=life.digest(out/'host-evidence.json')
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),fields=816,
                         protected_objects=c['protected_objects'],EDA_started=False)),flush=True)


def verify(out,seal):
    c=check(out,seal);need(not (out/'error.txt').exists(),'No GUI error')
    terminal=json.loads((out/'terminal.json').read_text());live=json.loads((out/'live-identity.json').read_text())
    old.primitive.terminal_gate(terminal,c,live)
    log=(out/'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('PMP_CONSTANTS816_FIVE_PHASE_DONE')==1 and 'PMP_CONSTANTS816_FAILED' not in log,'Actual complete five stages')
    execution=json.loads((out/'execution.json').read_text())
    need(execution['config_seal']==seal and execution['cwd']==str(out) and
         execution['command'][-2:]==['-script',str(out/'native-bind.tcl')],'Exact native invocation')
    refs=before_gate(out,c)
    for stage in STAGES:
        for index,i in enumerate(c['instances']):stage_gate(i,refs[index],bind(i,(out/('native_%s_%d.tsv'%(stage,index))).read_text()),stage)
    need(el_gate((out/'first.el').read_text(),c)==el_gate((out/'second.el').read_text(),c),'Exact global direction-semantic roundtrip')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):need((out/name).read_bytes()==b'','Global empty reset')
    files=[out/('native_%s_%d.tsv'%(s,index)) for s in STAGES for index in range(len(c['instances']))]
    files += [out/n for n in ('config.json','terminal.json','execution.json','live-identity.json','first.el','second.el',
                             'initial-empty.el','reset-empty.el','final-empty.el','DVEfiles/dve_gui.log','launcher.log')]
    result=dict(status='PMP_CONSTANTS816_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=seal,fields=816,bits=1088,directions=2176,
                target_MDA=0,source_MDA_HOLD=13,protected_objects=c['protected_objects'],terminal_returncode=0,
                stages=list(STAGES),population_application=False,initial_X_or_delta_instrumentation_qualified=False,
                pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in files}))
    life.check(result['pins']);p=out/'capture-result.json'
    if p.exists():need(json.loads(p.read_text())==result,'Sealed result differs')
    else:life.save(p,result)
    return result


def run(out,seal,reviewed):
    return FunctionType(old.lifecycle.run.__code__,dict(vars(old.lifecycle),check=check,verify=verify))(out,seal,reviewed)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','before','first','second','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-reviewed-seal');a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    elif a.mode=='run':run(out,a.seal,a.parent_reviewed_seal)
    else:
        c=check(out,a.seal)
        if a.mode=='before':before_gate(out,c)
        elif a.mode in ('first','second'):el_gate((out/(a.mode+'.el')).read_text(),c)
        elif a.mode=='verify':verify(out,a.seal)
        print(a.mode+'_PASS')
