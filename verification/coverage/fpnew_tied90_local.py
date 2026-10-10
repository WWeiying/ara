"""Prepare one exact90-field native roundtrip; no population application."""
import argparse
from collections import Counter
import csv
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import FunctionType
import xml.etree.ElementTree as ET

import prove_fpnew_tied_fields781 as proof
import mfpu272_five_phase as primitive

life, need = primitive.life, primitive.require
HERE = Path(__file__).resolve().parent
TCL = HERE/'fpnew_tied90_local.tcl'
SOURCE = life.OUT/'fpnew-tied-fields781-static-candidates-agent-20261008-01.json'
SOURCE_SHA = '0bc436c274bd0a51ae9aca4ca4507b6dcf462c487bd152cb45aa19ea4b877469'
ANNOTATION = 'Frozen literal zero ID and disabled-format operand placeholders only; other fields protected'
STAGES = primitive.STAGES


def tcl_pins(path, seen=None):
    seen = {} if seen is None else seen
    path = path.resolve()
    if str(path) in seen: return seen
    seen[str(path)] = life.digest(path)
    for child in re.findall(r'^source\s+\{([^}]+)\}', path.read_text(), re.M):
        tcl_pins(Path(child), seen)
    return seen


def labels(instance):
    return [n['name']+'[%d:%d]' % (n['left'],n['right']) for n in instance['signals']]


def candidate(instances):
    lines = []
    for i in instances:
        lines += ['CHECKSUM: "%s %s"' % (i['design_module_checksum'],i['toggle_checksum']),
                  'INSTANCE: '+i['scope'], 'ANNOTATION: "'+ANNOTATION+'"']
        for n in i['signals']:
            lines.append('Toggle %s "logic %s[%d:%d]"' % (n['name'],n['name'],n['left'],n['right']))
    return '\n'.join(lines)+'\n'


def el_gate(text, c):
    expected = {i['scope']:i for i in c['instances']}
    actual = {}; headers = set(); annotations = []; scope = None; checksum = None
    for line in map(str.strip,text.splitlines()):
        if not line or line.startswith('//'): continue
        if line.startswith('CHECKSUM:'):
            match = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
            need(match is not None,'Checksum grammar'); checksum = match.groups(); scope = None
        elif line.startswith('INSTANCE:'):
            scope = line.split(':',1)[1].strip()
            need(scope in expected and checksum == (expected[scope]['design_module_checksum'],
                                                     expected[scope]['toggle_checksum']),'Exact scope/checksum')
            headers.add(scope)
        elif line.startswith('ANNOTATION:'):
            need(line == 'ANNOTATION: "'+ANNOTATION+'"','Foreign annotation'); annotations.append(scope)
        else:
            match = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) "logic (\S+)\[(\d+):(\d+)\]"',line)
            need(scope is not None and match is not None,'Only exact whole Toggle syntax')
            direction,name,signature,left,right = match.groups()
            targets = {n['name']:n for n in expected[scope]['signals']}
            need(name in targets and signature == name and (int(left),int(right)) ==
                 (targets[name]['left'],targets[name]['right']),'No foreign field or partial range')
            key = (scope,name); directions = {'0to1','1to0'} if direction is None else {direction}
            need(not (actual.get(key,set()) & directions),'Duplicate direction')
            actual.setdefault(key,set()).update(directions)
    wanted = {(i['scope'],n['name']) for i in c['instances'] for n in i['signals']}
    need(headers == set(expected) and set(annotations) == set(expected) and set(actual) == wanted and
         all(d == {'0to1','1to0'} for d in actual.values()),'Exact complete paired membership')
    return sorted(wanted)


def bind(instance,text):
    rows = primitive.old.frozen.pack.native.native_rows(text)
    resolver = primitive.indexed.Resolver(instance)
    owners = {n['name']:[] for n in instance['typed_objects']}
    for label,row in rows.items():
        matches = resolver.matches(label,row['type'])
        need(len(matches)==1,'Unknown/ambiguous typed native row: '+label)
        n,match = matches[0]
        need(primitive.indexed.previous.native_role(n,row),'Native role differs: '+label)
        owners[n['name']].append((label,match))
    for n in instance['typed_objects']:
        values = owners[n['name']]; need(values,'Missing compiled object')
        aggregates = [x for x,kind in values if kind[0]=='aggregate']
        need(len(aggregates)<=1,'Duplicate aggregate')
        if n['kind']!='arrays': need(len(values)==len(aggregates)==1,'Non-bijective field')
        elif not aggregates:
            dims = primitive.indexed.previous.frozen.dimensions(n)
            leaves = {index for _,(kind,index) in values if kind=='element' and len(index)==len(dims)-1}
            wanted = set(itertools.product(*(range(min(a,b),max(a,b)+1) for a,b in dims[:-1])))
            need(leaves==wanted,'Incomplete protected MDA')
    for signal,label in zip(instance['signals'],labels(instance)):
        need(owners[signal['name']]==[(label,('aggregate',None))], 'Exact target full-vector label required')
    return rows


def before_gate(out,c):
    return [bind(i,(out/('native_before_%d.tsv'%index)).read_text()) for index,i in enumerate(c['instances'])]


def host_hook(c,selection,text):
    """Actual sourced entry, modeled GUI only; not native measurement."""
    with tempfile.TemporaryDirectory(prefix='tied90-host-') as tmp:
        root=Path(tmp); (root/'selection.tcl').write_text(selection); (root/'candidate.el').write_text(text)
        lines=[]
        for index,i in enumerate(c['instances']):
            rows=['handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay']
            for j,n in enumerate(i['typed_objects']):
                dims=primitive.indexed.previous.frozen.dimensions(n)
                label=n['name']+''.join('[%d:%d]'%d for d in dims)
                role='MDA' if n['kind']=='arrays' else 'port' if n['portnode'] in ('2','3') else 'signal'
                rows.append('\t'.join([str(j),'Item%d'%j,'Item%d'%j,label,role,'0.00%','0.00%']))
            data='\n'.join(rows)+'\n'; bind(i,data)
            (root/('model_%d.tsv'%index)).write_text(data)
            lines.append('set k {%s}\nset model_index($k) %d'%(i['scope'],index))
        script='''
set tied_test_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set env(TIED90_CONFIG_SEAL) host
%s
set active 0
set selected {}
proc p740_root {} {}
proc p740_select {scope} {return $scope}
proc gui_open_cov {args} {}
proc gui_list_action {args} {set ::scope [lindex $args end]}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_get_property {args} {
    set c [lindex $args end]; if {$c>=4} {error end}
    return [lindex {Variable Type Coverage Display} $c]
}
proc gui_list_get {args} {return first}
proc gui_list_get_selected {args} {return $::selected}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect]>=0} {set ::selected {};return}
    set ::selected [lindex $args end]
}
proc gui_exclusion {args} {
    if {[lsearch -exact $args -reset]>=0} {set ::active 0;return}
    if {[lsearch -exact $args -excluded]>=0} {return $::active}
}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lsearch -exact $args -load]>=0} {set ::active 1;return}
    if {$::active} {file copy -force [file join $::env(DVE_COVERAGE_OUTPUT) candidate.el] $path
    } else {close [open $path w]}
}
proc qc_walk {item stream columns} {
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) model_$::model_index($::scope).tsv] r]
    set data [read $f];close $f;set ::qc_seen {}
    foreach line [lrange [split [string trimright $data "\\n"] "\\n"] 1 end] {
        puts $stream $line;lappend ::qc_seen [lindex [split $line "\\t"] 3]
    }
}
set gates {}
proc tied_gate {mode} {lappend ::gates $mode}
tied_session
if {$active!=0 || $gates ne {before first second}} {error "Gate/reset/order differs"}
puts TIED_HOST_PASS
'''%(TCL,root,'\n'.join(lines))
        r=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=120)
        need(r.returncode==0 and r.stderr=='' and 'TIED_HOST_PASS' in r.stdout,'Actual five-stage hook: '+r.stderr)
        before_gate(root,c)
        for s in STAGES:
            for index,i in enumerate(c['instances']):
                need(bind(i,(root/('native_%s_%d.tsv'%(s,index))).read_text())==
                     bind(i,(root/('model_%d.tsv'%index)).read_text()),'Host full complement')
        with (root/'flags.tsv').open() as f: flags=list(csv.DictReader(f,delimiter='\t'))
        expected=[dict(stage=s,scope=i['scope'],label=l,excluded='1' if s in ('applied','reloaded') else '0')
                  for s in STAGES for i in c['instances'] for l in labels(i)]
        need(flags==expected,'Host five-stage exact flags')
        for n in ('initial-empty.el','reset-empty.el','final-empty.el'): need((root/n).read_bytes()==b'','Host empty reset')
        need(el_gate((root/'first.el').read_text(),c)==el_gate((root/'second.el').read_text(),c),'Host semantic roundtrip')
    return dict(status='ACTUAL_SOURCED_TCL_GUI_STUB_FIVE_STAGE_PASS_NOT_NATIVE',scopes=len(c['instances']),
                inventories=5*len(c['instances']),target_flag_rows=450,EDA_started=False)


def check(out,seal):
    c = life.read_bound(out/'config.json',seal); life.check(c['pins'])
    need(c['schema']=='FPNEW_TIED90_LOCAL_NATIVE_V1' and c['output']==str(out) and
         c['source_sha']==SOURCE_SHA and c['population_application'] is False and
         c['timeout_seconds']==5400,'Closed config')
    primitive.old.frozen.tools.revalidate(c['identity'])
    need(len(c['instances'])==70 and sum(len(i['signals']) for i in c['instances'])==90 and
         sum(2*(s['left']-s['right']+1) for i in c['instances'] for s in i['signals'])==8520,
         'Exact70 scopes/90 fields/8520 directions')
    for path,sha in tcl_pins(TCL).items(): need(c['pins'].get(path)==sha,'Transitive Tcl pin missing')
    el_gate((out/'candidate.el').read_text(),c)
    return c


def prepare(out):
    need(out.parent==life.OUT and not out.exists(),'Fresh output only')
    q=life.read_bound(SOURCE,SOURCE_SHA); life.check(q['pins'])
    need(q['candidate_count']==90 and q['missing_directions']==8520 and not q['hold'],'Exact source candidates')
    db=life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    defs=proof.m.xml(db/'shape/tgl.verilog.shape.xml')
    instances={}; callers=Counter()
    for row in q['candidates']:
        scope=row['scope']; d=next(d for d in defs.findall('tgldef') if dict(d.attrib)==row['definition'])
        i=instances.setdefault(scope,dict(scope=scope,design_module_checksum=row['module_checksum'],
            toggle_checksum=row['checksum'],signals=[],typed_objects=[dict(kind=n.tag,**n.attrib) for n in d.find('tglshape')]))
        i['signals'].append(dict(name=row['field'],left=row['bounds'][0],right=row['bounds'][1]))
        if row['field']=='id_i': callers[row['proof']['caller']]+=1
    need(callers=={'fpnew_fma':32,'fpnew_cast_multi':18},'Exact32FMA/18Cast')
    for family in callers:
        source=(life.ROOT/('hardware/deps/fpnew/src/'+family+'.sv')).read_text()
        need(re.search(r'\.EnableRSR\s*\(\s*0\s*\)',source),'Frozen RSR disabled call parameter')
    # This established local sample is only an identity vehicle, not processor PASS proof.
    template=life.read_bound(primitive.old.RUN/'config.json',primitive.old.SEAL)
    pins=life.merge_pins(q['pins'],template['pins'])
    pins[str(SOURCE)]=SOURCE_SHA; pins[str(primitive.old.RUN/'config.json')]=primitive.old.SEAL
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and Path(file).resolve().parent==HERE: pins[str(Path(file).resolve())]=life.digest(file)
    pins.update(tcl_pins(TCL))
    test=HERE/'test_fpnew_tied90_local.py'; pins[str(test)]=life.digest(test)
    c=dict(schema='FPNEW_TIED90_LOCAL_NATIVE_V1',output=str(out),source_sha=SOURCE_SHA,
        timeout_seconds=5400,population_application=False,automatic_retry=False,instances=list(instances.values()),
        pins=pins,**{k:template[k] for k in ('design','vdb','test','identity')})
    text=candidate(c['instances']); el_gate(text,c)
    selection=''.join('set mq_%s {%s}\n'%(k,c[k]) for k in ('design','vdb','test'))
    selection+='set mq_instances [list '+ ' '.join('[list {%s} [list %s]]'%(i['scope'],
        ' '.join('{%s}'%label for label in labels(i))) for i in c['instances'])+']\n'
    selection+='set tied_python {%s}\nset tied_helper {%s}\n'%(sys.executable,Path(__file__).resolve())
    # The seal is supplied by the runtime environment, not embedded recursively in config.
    selection+='set tied_seal $env(TIED90_CONFIG_SEAL)\n'
    with tempfile.TemporaryDirectory() as tmp:
        f=Path(tmp)/'selection.tcl'; f.write_text(selection)
        result=subprocess.run(['tclsh'],input='set env(TIED90_CONFIG_SEAL) host\nsource {%s}\nputs [llength $mq_instances]\n'%f,
                              text=True,capture_output=True,timeout=10)
        need(result.returncode==0 and result.stderr=='' and result.stdout.strip()=='70','Actual bracketed selection source/eval')
    host=host_hook(c,selection,text)
    life.check(pins); out.mkdir()
    for name,text in [('candidate.el',text),('selection.tcl',selection),('native-bind.tcl',TCL.read_text())]:
        (out/name).write_text(text); c['pins'][str(out/name)]=life.digest(out/name)
        if name.endswith('.tcl'): primitive.check_generated_tcl.check(out/name)
    life.save(out/'host-evidence.json',host); c['pins'][str(out/'host-evidence.json')]=life.digest(out/'host-evidence.json')
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),scopes=70,fields=90,directions=8520,EDA_started=False)))


def verify(out,seal):
    c=check(out,seal); need(not (out/'error.txt').exists(),'Recorded GUI failure')
    terminal=json.loads((out/'terminal.json').read_bytes()); live=json.loads((out/'live-identity.json').read_bytes())
    primitive.terminal_gate(terminal,c,live)
    log=(out/'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('FPNEW_TIED90_FIVE_PHASE_DONE')==1 and 'FPNEW_TIED90_FAILED' not in log,'Actual full completion')
    execution=json.loads((out/'execution.json').read_bytes())
    need(execution['config_seal']==seal and execution['cwd']==str(out) and execution['command'][-2:]==
         ['-script',str(out/'native-bind.tcl')],'Exact execution/script')
    reference=before_gate(out,c)
    for stage in STAGES:
        for index,i in enumerate(c['instances']):
            rows=bind(i,(out/('native_%s_%d.tsv'%(stage,index))).read_text()); before=reference[index]
            need(set(rows)==set(before),'Full native membership')
            for label,row in rows.items():
                keys=set(row)-{'handle'}
                if stage in ('applied','reloaded') and label in labels(i): keys-={'coverage','display'}
                need(all(row[k]==before[label][k] for k in keys),'Protected/reset row differs: '+label)
    with (out/'flags.tsv').open() as f: flags=list(csv.DictReader(f,delimiter='\t'))
    wanted=[dict(stage=s,scope=i['scope'],label=l,excluded='1' if s in ('applied','reloaded') else '0')
            for s in STAGES for i in c['instances'] for l in labels(i)]
    need(flags==wanted,'Exact five-stage excluded flags')
    need(el_gate((out/'first.el').read_text(),c)==el_gate((out/'second.el').read_text(),c),'Semantic reload')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'): need((out/name).read_bytes()==b'','Global empty reset')
    files=[out/('native_%s_%d.tsv'%(s,i)) for s in STAGES for i in range(70)]
    files += [out/n for n in ('config.json','terminal.json','execution.json','live-identity.json','flags.tsv',
               'first.el','second.el','initial-empty.el','reset-empty.el','final-empty.el','DVEfiles/dve_gui.log','launcher.log')]
    result=dict(status='FPNEW_TIED90_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=seal,fields=90,directions=8520,
                terminal_returncode=0,stages=list(STAGES),population_application=False,
                pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in files}))
    life.check(result['pins']); path=out/'capture-result.json'
    if path.exists(): need(json.loads(path.read_bytes())==result,'Sealed result differs')
    else: life.save(path,result)
    return result


def run(out,seal,reviewed):
    namespace=dict(vars(primitive.old.frozen),check=check,verify=verify)
    environment=dict(namespace['os'].environ)
    environment['TIED90_CONFIG_SEAL']=seal
    # Private environment proxy; no mutation of a shared predecessor module.
    from types import SimpleNamespace
    namespace['os']=SimpleNamespace(**{**vars(namespace['os']),'environ':environment})
    return FunctionType(primitive.old.frozen.run.__code__,namespace)(out,seal,reviewed)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=('prepare','check','before','first','second','verify','run'))
    p.add_argument('--output',type=Path,required=True); p.add_argument('--seal'); p.add_argument('--parent-reviewed-seal')
    a=p.parse_args(); out=a.output.resolve()
    if a.mode=='prepare': prepare(out)
    else:
        c=check(out,a.seal)
        if a.mode=='before': before_gate(out,c)
        elif a.mode in ('first','second'): el_gate((out/(a.mode+'.el')).read_text(),c)
        elif a.mode=='verify': verify(out,a.seal)
        elif a.mode=='run': run(out,a.seal,a.parent_reviewed_seal)
        print(a.mode+'_PASS')
