"""Prepare exact pack literal bits using frozen five-stage native primitive; no launch by prepare."""
import argparse
import copy
import json
from pathlib import Path
import re
import shutil
from types import FunctionType, SimpleNamespace
import cva6_fixed_fields_native768 as native
import vlsu_address_padding_native770 as labels
import prove_c910_pack_literals770 as proof
import inventory_operand_debug

life,require,tools=native.life,native.require,native.tools
HERE=Path(__file__).resolve().parent
TEMPLATE=life.OUT/'cva6-fixed120-native768-agent-20261007-01/config.json'
TEMPLATE_SHA='1a34f949b9d89a1a7403c067a1d3c56228df3d72d9d4527b36d6c33c2604858c'


def parse_el(text,c):
    instances={i['scope']:i for i in c['instances']};found=set();scope=None;checks=None
    for line in map(str.strip,text.splitlines()):
        if not line or line.startswith('//'):continue
        if re.fullmatch(r'ANNOTATION: "[^"\n]*"',line):continue
        m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
        if m:checks=list(m.groups());scope=None;continue
        if line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip()
            require(scope in instances and checks==[instances[scope]['design_module_checksum'],instances[scope]['toggle_checksum']],'Unknown scope/checksum');continue
        m=re.fullmatch(r'Toggle(?: (0to1|1to0))? (\w+)\s*(?:\[(\d+)(?::(\d+))?\])?(?: "([^"\n]+)")?',line)
        require(scope is not None and m is not None,'Unknown metric/native directive')
        direction,name,left,right,sig=m.groups();s=next((s for s in instances[scope]['signals'] if s['name']==name),None)
        require(s is not None and left is not None,'Protected field or whole-object request')
        hi,lo=int(left),int(right or left);require(63>=hi>=lo>=0 and set(range(lo,hi+1))<=set(s['bits']),'Dynamic sign/payload/normal bit excluded')
        if sig is not None:require(sig in ('wire '+s['native_label'],'net '+s['native_label']),'Source wire/native net signature/bounds')
        for bit in range(lo,hi+1):
            for d in (direction,) if direction else ('0to1','1to0'):
                key=(scope,name,bit,d);require(key not in found,'Duplicate direction');found.add(key)
    require(found==native.primitive.bitset(c),'Not exact323/35632 literal direction set')
    return sorted(found)


def audit(i,stages):
    before=native.native_rows(stages['before']);modified=copy.deepcopy(i);replacements={}
    # Only true compiled vector[0:0] *ports*, if native actually emits a scalar.
    # Never strip array/element indices; identity and every full row stay protected.
    for node in i['protected_shape']:
        if node['tag']!='vectornode' or node.get('left')!='0' or node.get('right')!='0' or node['portnode'] not in ('2','3'):continue
        name=node['name'];old=name+'[0:0]'
        if name not in before:continue
        require(old not in before and name+'[0]' not in before and before[name]['path']==before[name]['meta']==name and before[name]['type']=='port','Not bijective width1 port alias')
        for stage in ('selected','reset','reloaded','final'):require(native.native_rows(stages[stage]).get(name)==before[name],'Alias full row changed')
        replacements[old]=name
    modified['all_typed_labels']=[replacements.get(n,n) for n in i['all_typed_labels']]
    norm=native.normalized_label;expected=[norm(x) for x in modified['all_typed_labels']];observed=[norm(x) for x in before]
    require(len(expected)==len(set(expected)) and len(observed)==len(set(observed)) and set(expected)==set(observed),'Complete fresh-before inventory not bijective')
    return native.audit_native(modified,stages)


def prepare(out,path,seal):
    require(out.parent==life.OUT and not out.exists(),'Fresh config output only')
    p=life.read_bound(path,seal);life.check(p['pins'])
    require(p['schema']=='C910_PACK_LITERAL770_SOURCE_PROOF_V1' and p['baseline']==770 and p['objects']==323 and p['directions']==35632,'Exact proof boundary')
    reference=life.read_bound(proof.STATIC,proof.STATIC_SHA)
    require(proof.semantics(proof.SOURCE.read_text(),reference)==p['semantic_literal_proof'],'Independent semantic replay')
    # Recheck only the closed proof inventory, not our generated self candidate.
    for row in p['historical_EL_inventory']:
        require(life.digest(row['path'])==row['sha256'],'Historical EL drift')
        proof.old_overlap(Path(row['path']).read_text(),set(reference['scopes']),{s['name'] for s in reference['signals']})
    template=life.read_bound(TEMPLATE,TEMPLATE_SHA);tools.revalidate(template['identity'])
    base=life.read_bound(proof.shared.BASE/'admission-manifest.json',proof.shared.BASE_SHA)
    ledger=proof.shared.BASE/'combined-inputs.txt';require(life.digest(ledger)==base['output_pins'][str(ledger)],'770 exact input ledger')
    paths=ledger.read_text().splitlines();require(len(paths)==len(set(paths))==771,'Exact770 membership')
    pins=dict(p['pins']);pins[str(path)]=seal;pins[str(TEMPLATE)]=TEMPLATE_SHA
    instances=[]
    for item in p['instances']:
        targets={s['name'] for s in item['signals']};signals=[]
        for s in item['signals']:
            require(s['shape']['type']=='3' and s['shape']['portnode']=='0','Source wire internal only')
            signals.append(dict(name=s['name'],scalar=False,left=63,right=0,bits=s['bits'],native_label=s['name']+'[63:0]',shape=s['shape']))
        nodes=item['full_shape'];alllabels=[]
        for node in nodes:
            if node['tag']=='node':label=node['name']
            elif node['tag']=='vectornode':label=node['name']+'['+node['left']+':'+node['right']+']'
            else:require(False,'Unexpected array in pack scope')
            alllabels.append(label)
        instances.append(dict(scope=item['scope'],design_module_checksum=item['design_module_checksum'],toggle_checksum=item['toggle_checksum'],
                              signals=signals,all_typed_labels=alllabels,protected_shape=[n for n in nodes if n['name'] not in targets],
                              retained_target_bits={s['name']:sorted(set(range(64))-set(s['bits'])) for s in signals}))
    require(len(instances)==17 and sum(len(i['signals']) for i in instances)==323,'17/323 boundary')
    vdb=Path(paths[-1]);samples=list((vdb/'snps/coverage/db/testdata').iterdir());require(len(samples)==1,'Single admitted sample')
    for f in samples[0].iterdir():
        if not f.is_file():continue
        sha=life.digest(f)
        if str(f) in base['input_pins']:require(sha==base['input_pins'][str(f)],'Admitted coverage drift')
        else:require(f.name in ('siminfo.xml','vcmArguments.xml'),'Unpinned sample artifact')
        pins[str(f)]=sha
    for module in (native,native.primitive,native.primitive.common,native.primitive.common.common,native.primitive.toggle,life,tools,proof,proof.shared,inventory_operand_debug):
        file=Path(module.__file__).resolve();pins[str(file)]=life.digest(file)
    for name in ('c910_pack_literal_native770.py','test_c910_pack_literal_native770.py','cva6_fixed_fields_native768.tcl'):
        file=HERE/name;pins[str(file)]=life.digest(file)
    c=dict(schema='C910_PACK_LITERAL323_NATIVE770_PREPARED_V1',baseline=770,output=str(out),instances=instances,pins=pins,identity=template['identity'],
           design=paths[0],vdb=str(vdb),test=str(vdb.with_suffix('')/samples[0].name),timeout_seconds=900,launch_authorized=False,
           source_proof_seal=seal,historical_EL_inventory=p['historical_EL_inventory'],population_application=False,official_denominator_verified=False,
           protection_method='Exact global both-direction literal bit EL; full protected rows and all target nonliteral bits retained')
    text=native.primitive.candidate(c);parse_el(text,c);life.check(pins)
    out.mkdir();native.primitive.common.common.save(out/'candidate.el',text)
    native.primitive.common.common.save(out/'queue_constant_native.tcl',(HERE/'cva6_fixed_fields_native768.tcl').read_text())
    selection=''.join('set qc_'+k+' {'+c[k]+'}\n' for k in ('design','vdb','test'))
    selection+='set qc_python {'+shutil.which('python3')+'}\nset qc_helper {'+str(Path(__file__).resolve())+'}\nset qc_instances {}\n'
    for i in instances:selection+='lappend qc_instances [list {'+i['scope']+'} [list '+' '.join('{'+s['native_label']+'}' for s in i['signals'])+']]\n'
    native.primitive.common.common.save(out/'selection.tcl',selection)
    for name in ('candidate.el','queue_constant_native.tcl','selection.tcl'):pins[str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),objects=323,directions=35632,launch_authorized=False)))


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins']);tools.revalidate(c['identity'])
    terminal=json.loads((out/'terminal.json').read_bytes());require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Actual terminal identity')
    for name in ('launcher.log','DVEfiles/dve_gui.log'):require(not re.search(r'(?:Warning-|Error-|Fatal-|\b(?:Error|Fatal):|QUEUE_CONSTANT_NATIVE_FAILED)',(out/name).read_text()),'Native diagnostic')
    require((out/'DVEfiles/dve_gui.log').read_text().splitlines().count('QUEUE_CONSTANT_NATIVE_DONE')==1,'Incomplete five stages')
    require(parse_el((out/'first.el').read_text(),c)==parse_el((out/'second.el').read_text(),c),'Exact global semantic reload')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):require((out/name).read_bytes()==b'','Global exclusions not empty')
    counts=[audit(i,{s:(out/f'native_{s}_{k}.tsv').read_text() for s in ('before','selected','reset','reloaded','final')}) for k,i in enumerate(c['instances'])]
    result=dict(status='C910_PACK_LITERAL323_35632_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=seal,native_inventory_counts=counts,
                exact_global_EL=True,semantic_reload=True,finalreset=True,all_nonliteral_bits_retained=True,protected_full_rows_unchanged=True,
                population_application=False,official_denominator_verified=False,
                pins={**c['pins'],**{str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='capture-result.json'}})
    life.save(out/'capture-result.json',result)


def run(out,seal,authorization):
    require(seal is not None and authorization==seal,'Explicit parent-reviewed config seal required')
    c=life.read_bound(out/'config.json',seal);require(c['schema']=='C910_PACK_LITERAL323_NATIVE770_PREPARED_V1' and c['launch_authorized'] is False,'Wrong config')
    def bound(path,sha):
        value=life.read_bound(path,sha)
        return dict(value,launch_authorized=True) if Path(path)==out/'config.json' else value
    private=SimpleNamespace(**{**vars(life),'read_bound':bound})
    FunctionType(native.run.__code__,{**vars(native),'life':private,'verify':verify})(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','el','verify','run'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--proof',type=Path);p.add_argument('--proof-seal');p.add_argument('--seal');p.add_argument('--file');p.add_argument('--parent-reviewed-seal')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out,a.proof.resolve(),a.proof_seal)
    elif a.mode=='el':print(len(parse_el((out/a.file).read_text(),json.loads((out/'config.json').read_bytes()))))
    elif a.mode=='verify':verify(out,a.seal)
    else:run(out,a.seal,a.parent_reviewed_seal)
