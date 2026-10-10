"""Prepare local partial-bit roundtrip; native EL, not aggregate flags, owns bits."""
import argparse
import csv
import json
from pathlib import Path
import re
import sys
from types import FunctionType, SimpleNamespace
import fpnew_tied90_local as old
import prove_fpnew_class_padding783 as proof

life, need = old.life, old.need
HERE = Path(__file__).resolve().parent
HOOK = HERE/'fpnew_class_padding_local.tcl'
SOURCE = life.OUT/'fpnew-class-padding783-static-agent-20261008-01.json'
SOURCE_SHA = 'ee6f03ff7f941dca1e5c78c581561ac659c12dd6431e9a866238cbaadd42c793'
TEMPLATE = life.OUT/'fpnew-tied90-local-prepared781-parent-20261008-02'
TEMPLATE_SHA = 'dc049f1066dc8c6451b981ed9323edc3e3a6e422ad69d055a805733cad9cc71d'
NOTE = 'Source-proven classification padding only; all dynamic slots and typed complements protected'
STAGES = old.STAGES
FILES = dict(before='initial-empty.el', applied='first.el', reset='reset-empty.el',
             reloaded='second.el', final='final-empty.el')


def wanted(c):
    return {(i['scope'],n['name'],b,d) for i in c['instances'] for n in i['signals']
            for b in n['bits'] for d in ('0to1','1to0')}


def candidate(c):
    lines = []
    for i in c['instances']:
        lines += ['CHECKSUM: "%s %s"'%(i['design_module_checksum'],i['toggle_checksum']),
                  'INSTANCE: '+i['scope'], 'ANNOTATION: "'+NOTE+'"']
        for n in i['signals']:
            for b in n['bits']:
                for d in ('0to1','1to0'):
                    lines.append('Toggle %s %s [%d] "logic %s[%d:%d]"'%(d,n['name'],b,n['name'],n['left'],n['right']))
    return '\n'.join(lines)+'\n'


def records(text,c):
    expected = {i['scope']:i for i in c['instances']}
    found, annotated, headers = set(), set(), set()
    scope, checksum = None, None
    for line in text.splitlines():
        if line == '': continue
        match = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
        if match:
            checksum=match.groups(); scope=None; continue
        match=re.fullmatch(r'INSTANCE: (\S+)',line)
        if match:
            scope=match[1]
            need(scope in expected and checksum == (expected[scope]['design_module_checksum'],
                 expected[scope]['toggle_checksum']), 'Exact native scope/checksum')
            headers.add(scope);continue
        if line.startswith('ANNOTATION:'):
            need(scope is not None and line=='ANNOTATION: "'+NOTE+'"','Exact annotation')
            annotated.add(scope);continue
        match=re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) \[(\d+)(?::(\d+))?\] "logic (\S+)\[(\d+):(\d+)\]"',line)
        need(scope is not None and match is not None,'Only explicit partial-bit native grammar')
        direction,name,hi,lo,signature,left,right=match.groups()
        signals={n['name']:n for n in expected[scope]['signals']}
        need(name in signals and signature==name and (int(left),int(right))==
             (signals[name]['left'],signals[name]['right']), 'Foreign field/signature/bounds')
        hi,lo=int(hi),int(lo if lo is not None else hi)
        need(hi>=lo and set(range(lo,hi+1)) <= set(signals[name]['bits']), 'Dynamic/complement bit excluded')
        for b in range(lo,hi+1):
            for d in (direction,) if direction else ('0to1','1to0'):
                key=(scope,name,b,d);need(key not in found,'Duplicate direction/overlapping range');found.add(key)
    need(headers==annotated==set(expected) and found==wanted(c),'Missing/extra exact partial membership')
    return found


def contract(c):
    need(c['schema']=='FPNEW_CLASS_PADDING783_LOCAL_PREPARED' and c['source_sha']==SOURCE_SHA and
         c['population_application'] is False and c['raw_serialized_mapping_calibrated'] is False,
         'Exact local source/authority contract')
    need(len(c['instances'])==31 and sum(len(i['signals']) for i in c['instances'])==62 and
         len(wanted(c))==5316,'Exact31 scopes/62 objects/5316 directions')
    for i in c['instances']:
        for n in i['signals']:
            need(n['name'] in proof.FIELDS and set(n['bits']) == proof.zero_bits(i['parameters'],n['name'])
                 and set(n['bits']).isdisjoint(n['protected_bits']) and
                 set(n['bits'])|set(n['protected_bits'])==set(range(n['left']+1)),
                 'Exact source-derived mask and complementary slots')


def check(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins'])
    need(c['output']==str(out),'Output identity')
    old.primitive.old.frozen.tools.revalidate(c['identity'])
    records((out/'candidate.el').read_text(),c)
    return c


def stage(out,c,s):
    need(s in STAGES,'Unknown stage')
    text=(out/FILES[s]).read_text()
    if s in ('before','reset','final'): need(text=='','Global empty native reset')
    else: records(text,c)
    bound=[]
    for index,i in enumerate(c['instances']):
        rows=old.bind(i,(out/('native_%s_%d.tsv'%(s,index))).read_text());bound.append(rows)
        before=old.bind(i,(out/('native_before_%d.tsv'%index)).read_text())
        targets=set(old.labels(i))
        need(set(rows)==set(before),'Exact full native complement')
        for label,row in rows.items():
            keys=set(row)-{'handle'}
            if s in ('applied','reloaded') and label in targets: keys-={'coverage','display'}
            need(all(row[k]==before[label][k] for k in keys),'Protected/reset native attribute differs')
        with (out/('excluded_%s_%d.tsv'%(s,index))).open() as stream:
            flags=list(csv.DictReader(stream,delimiter='\t'))
        need(len(flags)==len(rows) and {r['label'] for r in flags}==set(rows),'Full native flags bijection')
        for r in flags:
            need(set(r)=={'label','excluded'} and r['excluded'] in ('0','1'),'Exact aggregate flag encoding')
            if s in ('before','reset','final') or r['label'] not in targets:
                need(r['excluded']=='0','Protected object/array/port excluded')
    return bound


def verify(out,seal):
    c=check(out,seal)
    t=json.loads((out/'terminal.json').read_bytes());live=json.loads((out/'live-identity.json').read_bytes())
    need(type(t['returncode']) is int,'Terminal returncode type')
    old.primitive.terminal_gate(t,c,live)
    log=(out/'DVEfiles/dve_gui.log').read_text().splitlines()
    need(log.count('FPNEW_CLASS_PADDING_NATIVE_DONE')==1 and not (out/'error.txt').exists() and
         not any(re.match(r'^(?:FPNEW_CLASS_PADDING_FAILED|Error(?:[:\[]|-)|ERROR\b)',line) for line in log),
         'Actual complete native pipeline')
    execution=json.loads((out/'execution.json').read_bytes())
    need(execution['config_seal']==seal and execution['cwd']==str(out) and execution['command'][-2:]==
         ['-script',str(out/'native-bind.tcl')], 'Exact execution script/config')
    for s in STAGES: stage(out,c,s)
    need(records((out/'first.el').read_text(),c)==records((out/'second.el').read_text(),c),'Exact semantic reload')
    need((out/'cleanup-empty.el').read_bytes()==b'','Independent cleanup reset')
    outputs={str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='capture-result.json'}
    result=dict(status='CLASS_PADDING5316_LOCAL_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED',config_seal=seal,
        objects=62,bits=2658,directions=5316,full_native_typed_complements=True,
        per_bit_GUI_flags_claimed=False,raw_serialized_mapping_calibrated=False,
        authority='Exact native EL partial membership in both directions; aggregate flags only for non-target protection',
        population_application=False,official_percentage=None,pins=life.merge_pins(c['pins'],outputs))
    life.check(result['pins']);p=out/'capture-result.json'
    if p.exists(): need(json.loads(p.read_bytes())==result,'Existing sealed result differs')
    else:life.save(p,result)
    return result


def prepare(out):
    need(out.parent==life.OUT and not out.exists(),'Fresh own output')
    q=life.read_bound(SOURCE,SOURCE_SHA);life.check(q['pins'])
    need(q['candidate_objects']==62 and q['candidate_bits']==2658 and q['candidate_directions']==5316 and
         not q['hold'] and q['EDA_started'] is False,'Exact reviewed static candidates')
    template=old.check(TEMPLATE,TEMPLATE_SHA)
    instances={}
    for r in q['candidates']:
        i=instances.setdefault(r['scope'],dict(scope=r['scope'],parameters=r['parameters'],
            design_module_checksum=r['module_checksum'],toggle_checksum=r['toggle_checksum'],signals=[],
            typed_objects=[dict(kind=n['kind'],**n['attributes']) for n in r['full_typed_inventory']]))
        a=r['attributes'];i['signals'].append(dict(name=r['field'],left=int(a['left']),right=int(a['right']),
            bits=r['logical_bits'],protected_bits=r['protected_bits']))
    pins=life.merge_pins(life.merge_pins(q['pins'],template['pins']),
                         {str(SOURCE):SOURCE_SHA,str(TEMPLATE/'config.json'):TEMPLATE_SHA})
    for module in (sys.modules[__name__], old, proof):
        p=Path(module.__file__).resolve();pins[str(p)]=life.digest(p)
    pins.update(old.tcl_pins(HOOK))
    p=HERE/'test_fpnew_class_padding_local.py';pins[str(p)]=life.digest(p)
    c=dict(schema='FPNEW_CLASS_PADDING783_LOCAL_PREPARED',output=str(out),source_sha=SOURCE_SHA,
        instances=list(instances.values()),pins=pins,population_application=False,
        raw_serialized_mapping_calibrated=False,timeout_seconds=5400,
        **{k:template[k] for k in ('design','vdb','test','identity')})
    contract(c);text=candidate(c);records(text,c)
    selection=''.join('set ::mq_%s {%s}\n'%(k,c[k]) for k in ('design','vdb','test'))
    selection+='set ::mq_instances [list '+' '.join('[list {%s} [list %s]]'%(i['scope'],
        ' '.join('{%s}'%label for label in old.labels(i))) for i in c['instances'])+']\n'
    selection+='set ::cp_python {%s}\nset ::cp_helper {%s}\nset ::cp_seal $::env(CLASS_PADDING_SEAL)\n'%(sys.executable,Path(__file__).resolve())
    life.check(pins);out.mkdir()
    for name,blob in [('candidate.el',text),('selection.tcl',selection),('native-bind.tcl',HOOK.read_text())]:
        with (out/name).open('x') as stream:stream.write(blob)
        pins[str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),state='PREPARED_NO_EDA')))


def run(out,seal,reviewed):
    env=dict(old.primitive.old.frozen.os.environ);env['CLASS_PADDING_SEAL']=seal
    need(env.get('PYTHONPATH') and all(Path(p).is_absolute() for p in env['PYTHONPATH'].split(':')),
         'Explicit absolute Python dependency paths required')
    namespace=dict(vars(old.primitive.old.frozen),check=check,verify=verify)
    namespace['os']=SimpleNamespace(**{**vars(namespace['os']),'environ':env})
    return FunctionType(old.primitive.old.frozen.run.__code__,namespace)(out,seal,reviewed)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','check','stage','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--stage',choices=STAGES)
    p.add_argument('--parent-reviewed-seal');a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    elif a.mode=='check':check(out,a.seal);print('CHECK_PASS_NO_EDA')
    elif a.mode=='stage':stage(out,check(out,a.seal),a.stage);print('STAGE_PASS '+a.stage)
    elif a.mode=='verify':verify(out,a.seal);print('VERIFY_PASS')
    else:run(out,a.seal,a.parent_reviewed_seal)
