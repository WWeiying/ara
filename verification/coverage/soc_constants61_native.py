"""Prepare-only until parent review: exact61 binary vectors, full native complement."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import FunctionType
import xml.etree.ElementTree as ET

import fpnew_tied90_local as frozen
import rr_disabled190_local as lifecycle
import audit_soc_constants792_static as source

life, need, primitive=frozen.life,frozen.need,frozen.primitive
HERE=Path(__file__).resolve().parent
TCL=HERE/'soc_constants61_native.tcl'
SOURCE=life.OUT/'soc-source-constants792-static-agent-20261008-01.json'
SOURCE_SHA='a42f4eb04f41d892eb4cf092426d5f26387189a8e59b668cef8c250c0dfa91b2'
SCHEMA='SOC_CONSTANTS61_LOCAL_NATIVE_PREPARED_V1'
ANNOTATION='Frozen SoC direct constants and explicitly disabled outputs only; all other objects and unknown states retained'
STAGES=frozen.STAGES
labels,bind=frozen.labels,frozen.bind


def inherited(name,**changes):
    fn=getattr(frozen,name)
    return FunctionType(fn.__code__,dict(vars(frozen),**changes),name,fn.__defaults__)


candidate=inherited('candidate',ANNOTATION=ANNOTATION)
before_gate=inherited('before_gate',bind=bind)


def el_gate(text,c):
    allowed={(i['design_module_checksum'],i['toggle_checksum']) for i in c['instances']}
    for line in text.splitlines():
        if line.strip().startswith('CHECKSUM:'):
            match=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line.strip())
            need(match is not None and match.groups() in allowed,'No foreign empty checksum block')
    return inherited('el_gate',ANNOTATION=ANNOTATION)(text,c)


def instances(q):
    need(q['status']=='SOURCE_BOUND_STATIC_CONSTANT_CANDIDATES792_NOT_NATIVE_APPROVED' and q['population']==792
         and q['manifest_seal']==source.BASE_SHA and q['native_report_seal']==source.QUAL_SHA
         and q['EDA_started'] is False and q['waivers_applied'] is False and not q['shape_or_MDA_HOLD'], 'Closed static proof')
    wanted={(r['scope'],r['name']):r for r in source.targets()}
    need(len(q['candidates'])==61 and len(wanted)==61 and not q['existing_EL_removed_or_held'], 'Exact61 unowned source fields')
    db=Path(str(life.IMAGE)+'.vdb')/'snps/coverage/db'
    tree=[source.t.xml(db/r) for r in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')]
    grouped={};seen=set()
    for r in q['candidates']:
        key=(r['scope'],r['name']);need(key in wanted and key not in seen,'No duplicate/foreign source target');seen.add(key)
        need(all(r[k]==wanted[key][k] for k in ('family','scope','name','value','width')) and
             r['constant_after_combinational_settling'] is True and r['initial_X_or_delta_instrumentation_qualified'] is False
             and r['native_binding_qualified'] is False and r['excluded'] is False,'Narrow constant contract, not X waiver')
        scope=r['scope']
        if scope not in grouped:
            checks,defs=source.t.definitions(*tree,[scope]);d=ET.fromstring(defs[scope]['shape'])
            need(checks[scope]==r['toggle_checksum'] and defs[scope]['module']==r['module'],'Exact compiled module/checksum')
            grouped[scope]=dict(scope=scope,design_module_checksum=r['module']['chksum'],toggle_checksum=checks[scope],
                signals=[],typed_objects=[dict(kind=n.tag,**n.attrib) for n in d.find('tglshape')])
        i=grouped[scope];matches=[n for n in i['typed_objects'] if n['name']==r['name']]
        need(len(matches)==1,'Unique complete compiled target')
        n=matches[0]
        need(n['kind']=='vectornode' and n.get('type') in ('1','3') and n.get('portnode') in ('0','2','3')
             and int(n['left'])==r['width']-1 and int(n['right'])==0
             and all(r['compiled_attributes'].get(k)==v for k,v in n.items() if k!='kind'), 'Binary complete vector only; no MDA/partial')
        need(r['raw_missing']==2*r['width'],'792 raw constant directions not active')
        i['signals'].append(dict(name=r['name'],left=int(n['left']),right=0))
    need(seen==set(wanted) and len(grouped)==18,'Exact source scope registry')
    return list(grouped.values())


def stage_gate(instance,before,actual,stage):
    need(stage in STAGES and set(actual)==set(before),'Exact stage/full native row universe')
    targets=set(labels(instance))
    for label,row in actual.items():
        need(set(row)==set(before[label]),'Native row schema')
        keys=set(row)-{'handle'}
        if stage in ('applied','reloaded') and label in targets:keys-={'coverage','display'}
        need(all(row[k]==before[label][k] for k in keys),'Protected/reset/identity row differs: '+label)


def selection(c):
    text=''.join('set mq_%s {%s}\n'%(k,c[k]) for k in ('design','vdb','test'))
    text+='set mq_instances [list '+' '.join('[list {%s} [list %s]]'%(i['scope'],' '.join('{%s}'%l for l in labels(i))) for i in c['instances'])+']\n'
    return text+'set tied_python {%s}\nset tied_helper {%s}\nset tied_seal $env(TIED90_CONFIG_SEAL)\n'%(sys.executable,Path(__file__).resolve())


def host_hook(c,text,el):
    with tempfile.TemporaryDirectory(prefix='soc61-host-') as tmp:
        root=Path(tmp);(root/'selection.tcl').write_text(text);(root/'candidate.el').write_text(el)
        mappings=[]
        for index,i in enumerate(c['instances']):
            rows=['handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay']
            for j,n in enumerate(i['typed_objects']):
                dims=primitive.indexed.previous.frozen.dimensions(n)
                label=n['name']+''.join('[%d:%d]'%d for d in dims)
                role='MDA' if n['kind']=='arrays' else 'port' if n['portnode'] in ('2','3') else 'signal'
                rows.append('\t'.join([str(j),'Item%d'%j,'Item%d'%j,label,role,'0.00%','0.00%']))
            data='\n'.join(rows)+'\n';bind(i,data);(root/('model_%d.tsv'%index)).write_text(data)
            mappings.append('set model_scope {%s}\nset model_index($model_scope) %d'%(i['scope'],index))
        script='''
set soc_test_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set env(TIED90_CONFIG_SEAL) host
%s
set active 0
proc p740_root {} {}
proc p740_select {scope} {return $scope}
proc gui_open_cov {args} {}
proc gui_list_action {args} {set ::scope [lindex $args end]}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_get_property {args} {set n [lindex $args end];if {$n>=4} {error end};return [lindex {Variable Type Coverage Display} $n]}
proc gui_list_get {args} {return first}
proc gui_list_select {args} {error "Per-object selection forbidden"}
proc gui_exclusion {args} {if {[lsearch -exact $args -reset]>=0} {set ::active 0;return}}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lsearch -exact $args -load]>=0} {set ::active 1;return}
    if {$::active} {file copy -force [file join $::env(DVE_COVERAGE_OUTPUT) candidate.el] $path} else {close [open $path w]}
}
proc qc_walk {item stream columns} {
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) model_$::model_index($::scope).tsv] r]
    set data [read $f];close $f;set ::qc_seen {}
    foreach line [lrange [split [string trimright $data "\\n"] "\\n"] 1 end] {
        puts $stream $line;lappend ::qc_seen [lindex [split $line "\\t"] 3]
    }
}
set gates {}
proc soc_gate {mode} {lappend ::gates $mode}
soc_session
if {$active!=0 || $gates ne {before first second}} {error "Gate/reset order"}
puts SOC61_HOST_PASS
'''%(TCL,root,'\n'.join(mappings))
        result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=120)
        need(result.returncode==0 and result.stderr=='' and 'SOC61_HOST_PASS' in result.stdout,'Actual source/eval five-stage hook: '+result.stderr)
        reference=before_gate(root,c)
        for stage in STAGES:
            for index,i in enumerate(c['instances']):stage_gate(i,reference[index],bind(i,(root/('native_%s_%d.tsv'%(stage,index))).read_text()),stage)
        need(el_gate((root/'first.el').read_text(),c)==el_gate((root/'second.el').read_text(),c),'Host full EL roundtrip')
        for name in ('initial-empty.el','reset-empty.el','final-empty.el'):need((root/name).read_bytes()==b'','Host global reset')
    return dict(status='ACTUAL_SOURCED_GUI_STUB_FIVE_STAGE_PASS_NOT_NATIVE',scope_inventories=5*len(c['instances']),
        per_object_GUI_select_calls=0,protection='Full typed inventories plus exact global whole-field both-direction EL',EDA_started=False)


def check(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins'])
    need(c['schema']==SCHEMA and c['output']==str(out) and c['source_sha']==SOURCE_SHA and c['population_application'] is False
         and c['automatic_retry'] is False and c['timeout_seconds']==5400,'Closed local config')
    primitive.old.frozen.tools.revalidate(c['identity'])
    q=life.read_bound(SOURCE,SOURCE_SHA);need(c['instances']==instances(q),'Exact target/full typed protection')
    for path,sha in frozen.tcl_pins(TCL).items():need(c['pins'].get(path)==sha,'Transitive sourced Tcl pin')
    el_gate((out/'candidate.el').read_text(),c)
    return c


def prepare(out):
    need(out.parent==life.OUT and not out.exists(),'Fresh independent output')
    q=life.read_bound(SOURCE,SOURCE_SHA);life.check(q['input_pins']);ii=instances(q)
    template=life.read_bound(primitive.old.RUN/'config.json',primitive.old.SEAL)
    pins=life.merge_pins(q['input_pins'],template['pins']);pins[str(SOURCE)]=SOURCE_SHA
    pins[str(primitive.old.RUN/'config.json')]=primitive.old.SEAL
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).resolve().parent==HERE:pins[str(Path(path).resolve())]=life.digest(path)
    pins.update(frozen.tcl_pins(TCL));test=HERE/'test_soc_constants61_native.py';pins[str(test)]=life.digest(test)
    protected=sum(len(i['typed_objects'])-len(i['signals']) for i in ii)
    c=dict(schema=SCHEMA,output=str(out),source_sha=SOURCE_SHA,source_population=792,timeout_seconds=5400,
        population_application=False,automatic_retry=False,instances=ii,pins=pins,target_vectors=61,target_scalars=0,
        target_MDA=0,target_bits=3843,target_directions=7686,protected_objects=protected,
        **{k:template[k] for k in ('design','vdb','test','identity')})
    el=candidate(ii);el_gate(el,c);text=selection(c);host=host_hook(c,text,el);life.check(pins)
    out.mkdir()
    for name,data in (('candidate.el',el),('selection.tcl',text),('native-bind.tcl',TCL.read_text())):
        (out/name).write_text(data);c['pins'][str(out/name)]=life.digest(out/name)
        if name.endswith('.tcl'):primitive.check_generated_tcl.check(out/name)
    life.save(out/'host-evidence.json',host);c['pins'][str(out/'host-evidence.json')]=life.digest(out/'host-evidence.json')
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),scopes=len(ii),vectors=61,
        directions=7686,protected_objects=protected,EDA_started=False)),flush=True)


def verify(out,seal):
    c=check(out,seal);need(not (out/'error.txt').exists(),'No recorded GUI failure')
    terminal=json.loads((out/'terminal.json').read_text());live=json.loads((out/'live-identity.json').read_text())
    primitive.terminal_gate(terminal,c,live)
    log=(out/'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('SOC_CONSTANTS61_FIVE_PHASE_DONE')==1 and 'SOC_CONSTANTS61_FAILED' not in log,'Actual full completion')
    execution=json.loads((out/'execution.json').read_text())
    need(execution['config_seal']==seal and execution['cwd']==str(out) and execution['command'][-2:]==['-script',str(out/'native-bind.tcl')],'Exact native execution')
    ref=before_gate(out,c)
    for stage in STAGES:
        for index,i in enumerate(c['instances']):stage_gate(i,ref[index],bind(i,(out/('native_%s_%d.tsv'%(stage,index))).read_text()),stage)
    need(el_gate((out/'first.el').read_text(),c)==el_gate((out/'second.el').read_text(),c),'Exact global semantic reload')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):need((out/name).read_bytes()==b'','Full global empty reset')
    files=[out/('native_%s_%d.tsv'%(s,i)) for s in STAGES for i in range(len(c['instances']))]
    files+=[out/n for n in ('config.json','terminal.json','execution.json','live-identity.json','first.el','second.el',
        'initial-empty.el','reset-empty.el','final-empty.el','DVEfiles/dve_gui.log','launcher.log')]
    result=dict(status='SOC_CONSTANTS61_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=seal,fields=61,directions=7686,
        target_MDA=0,protected_objects=c['protected_objects'],terminal_returncode=0,stages=list(STAGES),population_application=False,
        initial_X_or_delta_instrumentation_qualified=False,pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in files}))
    life.check(result['pins']);path=out/'capture-result.json'
    if path.exists():need(json.loads(path.read_text())==result,'Sealed result differs')
    else:life.save(path,result)
    return result


def run(out,seal,reviewed):
    return FunctionType(lifecycle.run.__code__,dict(vars(lifecycle),check=check,verify=verify))(out,seal,reviewed)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','before','first','second','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-reviewed-seal')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    else:
        c=check(out,a.seal)
        if a.mode=='before':before_gate(out,c)
        elif a.mode in ('first','second'):el_gate((out/(a.mode+'.el')).read_text(),c)
        elif a.mode=='verify':verify(out,a.seal)
        elif a.mode=='run':run(out,a.seal,a.parent_reviewed_seal)
        print(a.mode+'_PASS')
