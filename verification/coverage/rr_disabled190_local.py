"""Data-driven disabled-format190 local native qualification; no population apply."""
import argparse
import csv
import json
import os
from pathlib import Path
import sys
from types import FunctionType, SimpleNamespace

import fpnew_tied90_local as frozen
import audit_rr_disabled_formats783 as source

life, need, primitive = frozen.life, frozen.need, frozen.primitive
HERE = Path(__file__).resolve().parent
TCL = HERE/'rr_disabled190_local.tcl'
SOURCE = life.OUT/'rr-disabled-formats783-residual-agent-20261008-01.json'
SOURCE_SHA = '72fa095bde6587789258359f12e8f7ddf921b7769e00734e6755918c5fe899e5'
ANNOTATION = 'Frozen compiled disabled-format direct input literals only; active formats and full complement retained'
STAGES = frozen.STAGES
SCHEMA = 'RR_DISABLED190_LOCAL_NATIVE_V1'


def inherited(name, **changes):
    fn = getattr(frozen, name)
    return FunctionType(fn.__code__, dict(vars(frozen), **changes), name, fn.__defaults__)


labels = frozen.labels
bind = frozen.bind
candidate = inherited('candidate', ANNOTATION=ANNOTATION)
el_gate = inherited('el_gate', ANNOTATION=ANNOTATION)
before_gate = inherited('before_gate', bind=bind)


def host_hook(c, selection, text):
    result = inherited('host_hook', TCL=TCL, el_gate=el_gate)(c, selection, text)
    result['target_flag_rows'] = 5*sum(len(i['signals']) for i in c['instances'])
    return result


def source_gate(q):
    need(q['schema']=='FORMAL783_RR_DISABLED_INPUT_PROOF_AND_RESIDUAL_CAPACITY_V1' and
         q['status']=='STATIC_SOURCE_PROVEN_NOT_NATIVE_QUALIFIED' and q['population']==783 and
         q['candidate_count']==190 and q['candidate_directions']==q['candidate_raw_missing']==22528 and
         q['EDA_started'] is False and q['waivers_applied'] is False, 'Exact static190 authority')
    callers = {i['scope']:i for i in q['callers']}
    need(len(callers)==len(q['callers'])==30, 'Exact30 caller identities')
    seen = set()
    for r in q['candidates']:
        key=(r['scope'],r['field']); need(key not in seen,'Duplicate source target'); seen.add(key)
        need(r['scope'] in callers and r['field'] in callers[r['scope']]['candidates'], 'Source caller ownership')
        p=callers[r['scope']]['parameters']; fmt=r['format_index']
        need(source.disabled(p['FpFmtMask'],p['FmtUnitTypes'],fmt), 'Active format forbidden')
        operand=r['field'].endswith('.tag.operand_a')
        name='data_i[%d].%s'%(fmt,'tag.operand_a' if operand else 'result')
        width=64 if operand else p['Width']; n=r['attributes']
        need(r['field']==name and n['name']==name and r['kind']=='vectornode' and
             n['portnode']=='2' and n['type']=='1' and n['left']==str(width-1) and n['right']=='0' and
             n['aux_file']=='210' and n['aux_line_num']=='103', 'Exact direct typed port')
        need(not operand or 'TagType=vfpu_tag_t' in callers[r['scope']]['definition'], 'Reviewed packed tag only')
        need(r['logical_bits']==list(range(width)) and r['constant_hex']==hex(0 if operand else (1<<width)-1)
             and r['raw_missing']==2*width and r['raw_range'][1]-r['raw_range'][0]==2*width and
             r['missing_coordinates']==list(range(*r['raw_range'])) and r['native_qualified'] is False,
             'All783 directions zero; no partial/direction inference')
    need(len(seen)==190 and sum(len(i['protected_objects']) for i in callers.values())==5160,
         'Complete source target/complement')


def collision_gate(q, text):
    entries, whole = source.rank.old.el_fields(text)
    for r in q['candidates']:
        scope, name = r['scope'], r['field']
        need(not any(scope==w or scope.startswith(w+'.') for w in whole), 'Whole scope already owned')
        need(not any(s==scope and (n==name or name.startswith(n+'.') or n.startswith(name+'.'))
                     for s,n in entries), 'Existing whole/partial/struct ownership collision')


def instances(q):
    source_gate(q)
    ep=source.POLICY/'combined.el'
    need(life.digest(ep)==q['policy_EL_sha'] and q['pins'].get(str(ep))==q['policy_EL_sha'],
         'Qualified783 EL identity')
    collision_gate(q,ep.read_text())
    db=life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    shape=source.m.xml(db/'shape/tgl.verilog.shape.xml')
    grouped={}
    for r in q['candidates']:
        scope=r['scope']
        if scope not in grouped:
            ds=[d for d in shape.findall('tgldef') if d.get('name').split(' (')[0]=='rr_arb_tree' and
                d.get('chksum')==r['checksum']]
            need(len(ds)==1,'Unique actual specialized rr definition')
            grouped[scope]=dict(scope=scope,design_module_checksum=r['module_checksum'],
                toggle_checksum=r['checksum'],signals=[],
                typed_objects=[dict(kind=n.tag,**n.attrib) for n in ds[0].find('tglshape')])
        i=grouped[scope]
        matches=[n for n in i['typed_objects'] if n['name']==r['field']]
        need(len(matches)==1 and {k:v for k,v in matches[0].items() if k!='kind'}==r['attributes'],
             'Target compiled/source attributes differ')
        i['signals'].append(dict(name=r['field'],left=int(r['attributes']['left']),right=0))
    for i in grouped.values():
        caller=next(c for c in q['callers'] if c['scope']==i['scope'])
        targets={s['name'] for s in i['signals']}
        protected=[n for n in i['typed_objects'] if n['name'] not in targets]
        need(protected==[dict(kind=n['kind'],**n['attributes']) for n in caller['protected_objects']],
             'All5160 protected typed objects unchanged')
    return list(grouped.values())


def check(out, seal):
    c=life.read_bound(out/'config.json',seal); life.check(c['pins'])
    need(c['schema']==SCHEMA and c['output']==str(out) and c['source_sha']==SOURCE_SHA and
         c['population_application'] is False and c['automatic_retry'] is False and
         c['timeout_seconds']==5400, 'Closed local config')
    primitive.old.frozen.tools.revalidate(c['identity'])
    q=life.read_bound(SOURCE,SOURCE_SHA)
    need(c['instances']==instances(q),'Complete source/compiled target/protection binding')
    for path,sha in frozen.tcl_pins(TCL).items(): need(c['pins'].get(path)==sha,'Transitive Tcl pin missing')
    el_gate((out/'candidate.el').read_text(),c)
    return c


def prepare(out):
    need(out.parent==life.OUT and not out.exists(),'Fresh independent output only')
    q=life.read_bound(SOURCE,SOURCE_SHA); life.check(q['pins'])
    ii=instances(q)
    template=life.read_bound(primitive.old.RUN/'config.json',primitive.old.SEAL)
    pins=life.merge_pins(q['pins'],template['pins'])
    pins[str(SOURCE)]=SOURCE_SHA; pins[str(primitive.old.RUN/'config.json')]=primitive.old.SEAL
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).resolve().parent==HERE: pins[str(Path(path).resolve())]=life.digest(path)
    pins.update(frozen.tcl_pins(TCL))
    test=HERE/'test_rr_disabled190_local.py'; pins[str(test)]=life.digest(test)
    c=dict(schema=SCHEMA,output=str(out),source_sha=SOURCE_SHA,timeout_seconds=5400,
        population_application=False,automatic_retry=False,source_population=783,instances=ii,pins=pins,
        **{k:template[k] for k in ('design','vdb','test','identity')})
    text=candidate(ii); el_gate(text,c)
    selection=''.join('set mq_%s {%s}\n'%(k,c[k]) for k in ('design','vdb','test'))
    selection+='set mq_instances [list '+ ' '.join('[list {%s} [list %s]]'%(i['scope'],
        ' '.join('{%s}'%l for l in labels(i))) for i in ii)+']\n'
    selection+='set tied_python {%s}\nset tied_helper {%s}\n'%(sys.executable,Path(__file__).resolve())
    selection+='set tied_seal $env(TIED90_CONFIG_SEAL)\n'
    host=host_hook(c,selection,text)
    life.check(pins); out.mkdir()
    for name,data in [('candidate.el',text),('selection.tcl',selection),('native-bind.tcl',TCL.read_text())]:
        (out/name).write_text(data); c['pins'][str(out/name)]=life.digest(out/name)
        if name.endswith('.tcl'): primitive.check_generated_tcl.check(out/name)
    life.save(out/'host-evidence.json',host); c['pins'][str(out/'host-evidence.json')]=life.digest(out/'host-evidence.json')
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),scopes=30,
                         fields=190,directions=22528,protected_objects=5160,EDA_started=False)))


def verify(out,seal):
    c=check(out,seal); need(not (out/'error.txt').exists(),'Recorded GUI failure')
    terminal=json.loads((out/'terminal.json').read_bytes()); live=json.loads((out/'live-identity.json').read_bytes())
    primitive.terminal_gate(terminal,c,live)
    log=(out/'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('RR_DISABLED190_FIVE_PHASE_DONE')==1 and
         'RR_DISABLED190_FAILED' not in log,'Actual complete session')
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
    with (out/'flags.tsv').open() as stream: flags=list(csv.DictReader(stream,delimiter='\t'))
    expected=[dict(stage=s,scope=i['scope'],label=l,excluded='1' if s in ('applied','reloaded') else '0')
              for s in STAGES for i in c['instances'] for l in labels(i)]
    need(flags==expected,'Exact five-stage flags')
    need(el_gate((out/'first.el').read_text(),c)==el_gate((out/'second.el').read_text(),c),'Semantic reload')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'): need((out/name).read_bytes()==b'','Global empty reset')
    files=[out/('native_%s_%d.tsv'%(s,i)) for s in STAGES for i in range(len(c['instances']))]
    files += [out/n for n in ('config.json','terminal.json','execution.json','live-identity.json','flags.tsv',
        'first.el','second.el','initial-empty.el','reset-empty.el','final-empty.el','DVEfiles/dve_gui.log','launcher.log')]
    result=dict(status='RR_DISABLED190_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=seal,fields=190,
        directions=22528,protected_objects=5160,terminal_returncode=0,stages=list(STAGES),
        population_application=False,pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in files}))
    life.check(result['pins']); path=out/'capture-result.json'
    if path.exists(): need(json.loads(path.read_bytes())==result,'Sealed result differs')
    else: life.save(path,result)
    return result


def run(out,seal,reviewed):
    paths=os.environ.get('PYTHONPATH','').split(os.pathsep)
    need(paths and all(p and Path(p).is_absolute() and Path(p).is_dir() for p in paths),
         'Explicit absolute child import paths required')
    namespace=dict(vars(primitive.old.frozen),check=check,verify=verify)
    environment=dict(os.environ,TIED90_CONFIG_SEAL=seal)
    namespace['os']=SimpleNamespace(**{**vars(os),'environ':environment})
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
