"""Only new even-start proved partial hit bits, exact native roundtrip, not apply."""
import argparse
import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

import qbs_scale_hit_native762_v2 as predecessor

old = predecessor.old
primitive, life, tools, require = old.primitive, old.life, old.tools, old.require
HERE = Path(__file__).resolve().parent
PROOF = life.OUT/'qbs-even-start-hit-static762-agent-20261007-02.json'
PROOF_SHA = 'e00a593df5e8fc302484209d22965d9cfc9a133a472966beb2a63a481120164d'
TEMPLATE = life.OUT/'qbs-bank0-scale-hit120-native762-agent-20261007-02'
TEMPLATE_SHA = 'ec5c04c3c372ee34da28964c696d4184e142c6c9cb7b50587146b0b7a43b657a'
NEW = 'NEW_EVEN_START_MAPPING_ZERO_NATIVE_REQUIRED'


def targets(proof):
    selected = {}
    for scope,data in proof['scopes'].items():
        signals = {}
        for item in data['records']:
            if item['classification'] != NEW: continue
            require(len(item['missing_serialized_coordinates']) == 2 and item['mapping_witness'] is None,
                    'Target not zero in both directions')
            name,bit = item['signal'],item['bit']
            require(name.endswith('.hit') and item['right'] == 0 and item['left'] in (15,31) and
                    item['declaration_line'] in ('269','355','381'), 'Non-hit/unknown compiled type')
            record = signals.setdefault(name,dict(name=name,bits=[],scalar=False,left=item['left'],right=0,
                native_label=name+'['+str(item['left'])+':0]'))
            require(bit not in record['bits'] and 0 <= bit <= item['left'], 'Duplicate/out of bounds')
            record['bits'].append(bit)
        for record in signals.values():
            record['bits'].sort()
            require(len(record['bits']) < record['left']+1, 'Whole hit vector forbidden')
        selected[scope] = [signals[name] for name in sorted(signals)]
    counts = sorted(sum(len(s['bits'])*2 for s in signals) for signals in selected.values())
    require(len(selected) == 2 and counts == [9600,9728], 'Exact new19328 target population')
    return selected


def parse_el(text,c):
    instances = {i['scope']:i for i in c['instances']}
    by_name = {scope:{s['name']:s for s in i['signals']} for scope,i in instances.items()}
    found,scope,checksum = set(),None,None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'): continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\n]*"',line),'Annotation grammar')
            continue
        if line.startswith('CHECKSUM:'):
            m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
            require(m is not None,'Target scopes require both checksums')
            checksum,scope = list(m.groups()),None
            continue
        if line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip()
            require(scope in instances and checksum == [instances[scope]['design_module_checksum'],
                                                       instances[scope]['toggle_checksum']], 'Unknown scope/checksum')
            continue
        m=re.fullmatch(r'Toggle(?:\s+(0to1|1to0))?\s+([\w.\[\]]+)\s*(?:\[([0-9]+)(?::([0-9]+))?\])?(?:\s+"([^"\n]+)")?',line)
        require(scope is not None and m is not None,'Unknown native metric/directive')
        direction,name,left,right,signature=m.groups()
        signal=by_name[scope].get(name)
        require(signal is not None,'Protected signal or old qualified object')
        require(left is not None,'Whole hit vector forbidden')
        lo,hi=sorted((int(left),int(right or left)))
        bits=list(range(lo,hi+1))
        require(set(bits)<=set(signal['bits']),'Protected bit')
        if signature:
            declaration=name+'['+str(signal['left'])+':0]'
            require(signature in ('net '+declaration,'wire '+declaration),'Wrong native declaration type/bounds')
        for bit in bits:
            for d in (direction,) if direction else ('0to1','1to0'):
                key=(scope,name,bit,d)
                require(key not in found,'Duplicate native direction')
                found.add(key)
    require(found==primitive.bitset(c),'Missing/extra native set')
    return sorted(found)


def checked_config(out,seal):
    c=life.read_bound(out/'config.json',seal)
    require(c['output']==str(out) and c['baseline']==762 and not c['population_application'] and
            c['source_proof_sha256']==PROOF_SHA,'Bound output/proof identity')
    life.check(c['pins'])
    require(len(c['instances'])==2 and len(primitive.bitset(c))==19328,'Exact new9664 bits')
    require(all(not s['scalar'] and len(s['bits'])<s['left']+1 for i in c['instances'] for s in i['signals']),
            'Whole signal exclusion forbidden')
    parse_el((out/'candidate.el').read_text(),c)
    return c


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh output only')
    p=life.read_bound(PROOF,PROOF_SHA)
    life.check(p['pins'])
    require(p['baseline']==762 and p['all_compiled_hit_bits_checked_for_observed_counterexamples'] and
            not p['excluded_initial_X'] and not p['native_qualification'],'Complete static proof required')
    template=predecessor.backend()['checked_config'](TEMPLATE,TEMPLATE_SHA)
    selected=targets(p)
    shape_path=next(Path(k) for k in p['pins'] if k.endswith('/shape/tgl.verilog.shape.xml'))
    shape=primitive.toggle.xml(shape_path)
    definitions=[d for d in shape.iter('tgldef') if d.get('name')=='qbs_payload_buffer']
    require(len(definitions)==1 and definitions[0].get('chksum')=='3657545390','Compiled payload definition')
    nodes={n.get('name'):n for n in definitions[0].find('tglshape')}
    require(len(nodes)==3193,'Complete complement shape')
    instances=[]
    for prior in template['instances']:
        scope=prior['scope'];signals=selected[scope]
        for s in signals:
            n=nodes[s['name']]
            require(n.tag=='vectornode' and int(n.get('left'))==s['left'] and n.get('right')=='0' and
                    n.get('line_num') in ('269','355','381'),'Exact native compiled declaration')
            s['shape']=dict(n.attrib)
        names={s['name'] for s in signals}
        instances.append(dict(scope=scope,design_module_checksum=prior['design_module_checksum'],
            toggle_checksum=prior['toggle_checksum'],signals=signals,
            protected=[dict(n.attrib) for name,n in nodes.items() if name not in names],
            retained_target_signal_bits={s['name']:sorted(set(range(s['left']+1))-set(s['bits'])) for s in signals}))
    c=dict(template,output=str(out),instances=instances,pins=life.merge_pins(template['pins'],p['pins']),
        source_proof_sha256=PROOF_SHA,physical_bits=9664,bit_directions=19328,
        protected_direction_count=113352,native_binding_required=True,automatic_retry=False)
    for obsolete in ('source_certificate_sha256','protected_target_vector_bits','failed01_first_is_format_evidence_not_roundtrip_receipt'):
        c.pop(obsolete,None)
    c['protected_target_vector_bits']=sum(s['left']+1-len(s['bits']) for i in instances for s in i['signals'])
    c['non_target_compiled_signal_count']=sum(len(i['protected']) for i in instances)
    for path in (PROOF,Path(__file__).resolve(),HERE/'test_qbs_even_hit_native762.py',
                 HERE/'queue_constant_native.tcl',TEMPLATE/'config.json'):
        c['pins'][str(path)]=life.digest(path)
    tools.revalidate(c['identity'])
    text=primitive.candidate(c)
    parse_el(text,c)
    life.check(c['pins'])
    out.mkdir()
    for name,contents in (('candidate.el',text),('queue_constant_native.tcl',(HERE/'queue_constant_native.tcl').read_text())):
        primitive.common.common.save(out/name,contents)
    selection=(TEMPLATE/'selection.tcl').read_text()
    require(selection.count('set qc_helper {')==1 and selection.count('set qc_instances {}')==1,'Frozen Tcl binding anchors')
    selection=selection.split('set qc_instances {}')[0]
    selection=re.sub(r'set qc_helper \{[^\n]+\}', 'set qc_helper {'+str(Path(__file__).resolve())+'}',selection)
    selection+='set qc_instances {}\n'
    for i in instances:
        labels=' '.join('{'+s['native_label']+'}' for s in i['signals'])
        selection+='lappend qc_instances [list {'+i['scope']+'} [list '+labels+']]\n'
    primitive.common.common.save(out/'selection.tcl',selection)
    for name in ('candidate.el','queue_constant_native.tcl','selection.tcl'):c['pins'][str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',c)
    checked_config(out,life.digest(out/'config.json'))
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),bits=9664,directions=19328)))


def verify(out,seal):
    c=checked_config(out,seal)
    tools.revalidate(c['identity'])
    for name in ('launcher.log','DVEfiles/dve_gui.log'):
        require(re.search(r'(?:Error-|Fatal-|Warning-|\b(?:Error|Fatal):)',(out/name).read_text()) is None,
                'Native diagnostic: '+name)
    def save(path,value):
        if path.name=='capture-result.json':
            value.update(status='QBS_EVEN_START9664_BITS19328_NATIVE_ROUNDTRIP_NOT_APPLICATION',baseline=762,
                physical_bits=9664,bit_directions=19328,source_proof_sha256=PROOF_SHA,
                partial_bits_only=True,old1792_and_scale120_not_added=True,initial_X_excluded=False,
                protected_target_vector_bits=c['protected_target_vector_bits'])
            if path.exists():
                require(json.loads(path.read_bytes())==value,'Existing receipt differs');return
        life.save(path,value)
    ns=dict(vars(primitive),parse_el=parse_el,life=SimpleNamespace(**dict(vars(life),save=save)))
    FunctionType(primitive.verify.__code__,ns)(out,seal)


def run(out,seal):
    checked_config(out,seal)
    FunctionType(primitive.run.__code__,dict(vars(primitive),HERE=out,verify=verify))(out,seal)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('prepare','check','run','verify','el'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal');parser.add_argument('--file')
    args=parser.parse_args();out=args.output.resolve()
    if args.mode=='prepare':prepare(out)
    elif args.mode=='check':checked_config(out,args.seal);print('QBS_EVEN_HIT19328_PREPARED_CHECK_PASS_NO_EDA')
    elif args.mode=='el':print(json.dumps(dict(bit_directions=len(parse_el((out/args.file).read_text(),json.loads((out/'config.json').read_bytes()))))))
    else:(run if args.mode=='run' else verify)(out,args.seal)


if __name__=='__main__':main()
