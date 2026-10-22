"""Two-scope ten partial ranges, local five-stage qualification; no auto launch."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys
import signal
from types import FunctionType, SimpleNamespace
import xml.etree.ElementTree as ET

import cva6_fixed_fields_native768 as native
import review_cvxif_padding776 as proof
import vlsu_address_padding_native770 as labels

life, require, tools = native.life, native.require, native.tools
HERE = Path(__file__).resolve().parent
PROOF = life.OUT / 'cvxif-padding776-static-prepared-agent-20261007-01.json'
PROOF_SHA = 'e37df8f2750fdc90be822307856aefbadfe92b394909e49651b211551ac7edb2'
TEMPLATE = life.OUT / 'cva6-fixed120-native768-agent-20261007-01/config.json'
TEMPLATE_SHA = '1a34f949b9d89a1a7403c067a1d3c56228df3d72d9d4527b36d6c33c2604858c'
SCHEMA = 'PASSIVE_CVXIF_PADDING10_NATIVE776_PREPARED_V1'
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')


def contract(c):
    require(c['schema'] == SCHEMA and c['baseline'] == 776 and c['timeout_seconds'] == 900 and
            c['launch_authorized'] is False and c['population_application'] is False and
         c['DUT_functional_gain'] is False, 'Prepared-only passive boundary')
    require(re.fullmatch(r'[A-Za-z0-9_-]+\.service',c['owning_service_unit']) and
            c['expected_cgroup']==service_cgroup(c['owning_service_unit'],c['owner_uid']), 'Exact owning user service')
    require([i['scope'] for i in c['instances']] == list(proof.SCOPES), 'Exact two scopes/order')
    total = 0
    for i in c['instances']:
        child = i['scope'] == proof.SCOPES[1]
        require(len(i['signals']) == 5 and len(i['protected_shape']) == (40 if child else 36),
                'Five targets + complete76 protected objects')
        require({s['name'] for s in i['signals']} ==
                {'axi_'+ch+'_payload'+('' if child else '_i') for ch in proof.CHANNELS}, 'Exact target fields')
        widths = dict(ar=98, aw=104, w=146, r=136, b=7)
        for s in i['signals']:
            ch = s['name'].split('_')[1]; low = widths[ch]
            require(s['scalar'] is False and s['left'] == 1023 and s['right'] == 0 and
                    s['bits'] == list(range(low,1024)) and s['native_label'] == s['name']+'[1023:0]' and
                    i['retained_target_bits'][s['name']] == list(range(low)), 'High padding only; low payload protected')
        total += len(i['all_typed_labels'])
    require(total == 86 and len(native.primitive.bitset(c)) == 18516, 'Exact10/76/18516 boundary')


def parse_el(text, c):
    """Require the exact physical bit/direction set, never a vector aggregate flag."""
    require(not text or text.endswith('\n'), 'Truncated native EL')
    require(all(ch in '\n\r\t' or 32 <= ord(ch) <= 126 for ch in text), 'Non-ASCII/control native EL')
    instances = {i['scope']: i for i in c['instances']}
    found, scope, checks = set(), None, None
    for line in map(str.strip,text.splitlines()):
        if not line or line.startswith('//'): continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\n]*"',line), 'Annotation grammar'); continue
        m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
        if m: checks=list(m.groups());scope=None;continue
        if line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip()
            require(scope in instances and checks == [instances[scope]['design_module_checksum'],
                    instances[scope]['toggle_checksum']], 'Unknown scope/checksum')
            continue
        m=re.fullmatch(r'Toggle(?: (0to1|1to0))? (\w+) \[(\d+)(?::(\d+))?\](?: "(logic|reg|wire|net) ([^"\n]+)")?',line)
        require(scope is not None and m is not None, 'Unknown metric/whole-vector/native directive')
        direction,name,hi,lo,kind,declaration=m.groups()
        s=next((s for s in instances[scope]['signals'] if s['name']==name),None)
        require(s is not None, 'Protected object excluded')
        hi,lo=int(hi),int(lo if lo is not None else hi)
        require(0 <= lo <= hi <= 1023 and set(range(lo,hi+1)) <= set(s['bits']), 'Low payload/out-of-bound bits excluded')
        # Shape type1 is logic/reg, not a source wire. Never accept net as an alias.
        if kind is not None:
            require(kind in ('logic','reg') and declaration == s['native_label'], 'Native type/declaration/bounds mismatch')
        for b in range(lo,hi+1):
            for d in (direction,) if direction else ('0to1','1to0'):
                key=(scope,name,b,d);require(key not in found,'Duplicate bit/direction');found.add(key)
    require(found == native.primitive.bitset(c), 'Missing/extra padding bit-direction set')
    return sorted(found)


def audit(instance, stages):
    require(set(stages) == set(STAGES), 'Complete five-stage inventory')
    before=native.native_rows(stages['before']); modified=copy.deepcopy(instance)
    aliases={}
    for node in instance['protected_shape']:
        if node['tag'] != 'vectornode' or node.get('left') != '0' or node.get('right') != '0' or node.get('portnode') not in ('2','3'):
            continue
        name=node['name']; old=name+'[0:0]'
        if name not in before: continue
        require(old not in before and name+'[0]' not in before and before[name]['path'] ==
                before[name]['meta'] == name and before[name]['type'] == 'port', 'Width1 port alias is not bijective')
        for stage in STAGES[1:]:
            require(native.native_rows(stages[stage]).get(name) == before[name], 'Single-bit port full row changed')
        aliases[old]=name
    modified['all_typed_labels']=[aliases.get(x,x) for x in instance['all_typed_labels']]
    for s in instance['signals']:
        require(s['native_label'] in before, 'Exact payload declaration missing')
    # All fresh-before native extras are also protected, not dropped as unmodeled rows.
    # Target percentages may change; first/second EL is the sole low-bit waiver guard.
    return native.audit_native(modified, stages)


def check(out, seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins']);tools.revalidate(c['identity'])
    parse_el((out/'candidate.el').read_text(),c)
    return c


def service_cgroup(unit, uid):
    require(type(uid) is int and uid >= 0 and re.fullmatch(r'[A-Za-z0-9_-]+\.service',unit), 'Service unit/UID identity')
    return '/user.slice/user-%d.slice/user@%d.service/app.slice/%s' % (uid,uid,unit)


def cgroup_path(text):
    rows=[line.split(':',2) for line in text.splitlines()]
    choices=[r[2] for r in rows if len(r)==3 and (r[:2]==['0',''] or 'name=systemd' in r[1].split(','))]
    require(len(set(choices))==1 and all(x.startswith('/') for x in choices), 'Missing/ambiguous systemd cgroup')
    return choices[0]


def terminal_gate(terminal,c,out):
    require(type(terminal.get('returncode')) is int and terminal['returncode']==0, 'Terminal must be integer0, never bool')
    require(type(terminal.get('timeout')) is bool and terminal['timeout'] is False, 'Timeout must be exact boolFalse')
    require(type(terminal.get('actual_dve')) is list and len(terminal['actual_dve'])==1, 'One actual DVE executable')
    actual=terminal['actual_dve'][0]
    require(actual.get('exe')==c['identity']['executable'] and actual.get('cwd')==str(out) and
            type(actual.get('pid')) is int and actual['pid']>0 and actual.get('cgroup')==c['expected_cgroup'] and
            actual.get('exe_sha256')==c['pins'][c['identity']['executable']], 'Exact actual executable/cwd/PID/service/hash')


def terminal_logs(out):
    """Seal terminal byte snapshots; later launcher tails are not receipt inputs."""
    result={};receipt=out/'capture-result.json'
    recorded=json.loads(receipt.read_bytes())['pins'] if receipt.exists() else None
    for name in ('launcher.log','DVEfiles/dve_gui.log'):
        snapshot=out/'terminal-evidence'/name
        if recorded is not None:
            require(str(snapshot) in recorded and life.digest(snapshot)==recorded[str(snapshot)], 'Frozen terminal log drift')
        else:
            source=out/name;data=source.read_bytes()
            require(source.read_bytes()==data, 'Log still appending while taking terminal snapshot')
            snapshot.parent.mkdir(parents=True,exist_ok=True)
            if snapshot.exists():require(snapshot.read_bytes()==data,'Existing unsealed terminal snapshot differs')
            else:
                with snapshot.open('xb') as stream:stream.write(data)
        result[name]=snapshot.read_text()
    return result


def prepare(out, service_unit=None):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent output only')
    p=life.read_bound(PROOF,PROOF_SHA);life.check(p['pins'])
    require(p['schema']=='PASSIVE_CVXIF_PADDING776_STATIC_PREPARATION_V1' and p['population']==776 and
            p['objects']==10 and p['old_overlap_directions']==0 and p['new_candidate_directions']==18516 and
            p['native_qualified'] is False and p['DUT_functional_gain'] is False, 'Reviewed sole proof boundary')
    require(proof.source_contract({f:(proof.ROOT/f).read_text() for f in proof.FILES},p['compiled_geometry']) ==
            p['source_proof'], 'Exact semantic source replay')
    oldtext=Path(p['old_EL_inventory']).read_text()
    require(not proof.existing_overlap(oldtext,p['targets']), 'Closed historical EL overlap')
    cbase=life.read_bound(proof.CONFIG,proof.CONFIG_SHA)
    manifest=life.read_bound(proof.BASE/'admission-manifest.json',proof.BASE_SHA)
    ledger=proof.BASE/'combined-inputs.txt'
    require(life.digest(ledger)==manifest['output_pins'][str(ledger)],'776 ledger pin')
    paths=ledger.read_text().splitlines()
    require(len(paths)==len(set(paths))==777 and paths[:776]==cbase['input_ledger'], 'Exact776 ledger/775 prefix')
    db=Path(paths[0])/'snps/coverage/db'
    checks,defs=proof.typed.definitions(*(proof.typed.xml(db/name) for name in
        ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')),proof.SCOPES)
    instances=[]
    for scope in proof.SCOPES:
        chosen,protected,_=proof.bind_scope(scope,ET.fromstring(defs[scope]['shape']),checks[scope],defs[scope]['module']['chksum'])
        prior=[s for s in p['targets'] if s['scope']==scope]
        require([s['name'] for s in chosen]==[s['name'] for s in prior], 'Compiled exact targets')
        require(protected==p['protected_by_scope'][scope], 'Compiled complete complement')
        signals=[]
        for node,old in zip(chosen,prior):
            require(all(old[k]==v for k,v in node.items()), 'Complete typed identity unchanged')
            signals.append(dict(name=node['name'],scalar=False,left=1023,right=0,bits=old['bits'],
                native_label=node['name']+'[1023:0]',shape={k:node[k] for k in
                ('name','file','line_num','type','portnode','excluded','left','right')}))
        nodes=list(ET.fromstring(defs[scope]['shape']).find('tglshape'))
        instances.append(dict(scope=scope,design_module_checksum=defs[scope]['module']['chksum'],
            toggle_checksum=checks[scope],signals=signals,all_typed_labels=[labels.label(n) for n in nodes],
            protected_shape=[dict(n.attrib,tag=n.tag) for n in nodes if n.get('name') not in {s['name'] for s in signals}],
            retained_target_bits={s['name']:list(range(min(s['bits']))) for s in signals}))
    template=life.read_bound(TEMPLATE,TEMPLATE_SHA);tools.revalidate(template['identity'])
    pins=dict(p['pins']);pins[str(PROOF)]=PROOF_SHA;pins[str(TEMPLATE)]=TEMPLATE_SHA
    for file in template['identity']['files']:pins[file['path']]=file['sha256']
    vdb=Path(paths[-1]);samples=list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(samples)==1 and samples[0].is_dir(), 'One admitted sample')
    for file in samples[0].iterdir():
        require(file.is_file(), 'Unexpected nested sample artifact')
        sha=life.digest(file)
        if str(file) in manifest['input_pins']:require(sha==manifest['input_pins'][str(file)],'Admitted sample drift')
        else:require(file.name in ('siminfo.xml','vcmArguments.xml'),'Unpinned sample artifact')
        pins[str(file)]=sha
    for module in (native,native.primitive,native.primitive.common,native.primitive.common.common,
                   native.primitive.toggle,life,tools,proof,labels):
        file=Path(module.__file__).resolve();pins[str(file)]=life.digest(file)
    for name in ('cvxif_padding_native776.py','test_cvxif_padding_native776.py','cva6_fixed_fields_native768.tcl'):
        file=HERE/name;pins[str(file)]=life.digest(file)
    interpreter=Path(sys.executable).resolve();pins[str(interpreter)]=life.digest(interpreter)
    c=dict(schema=SCHEMA,baseline=776,output=str(out),instances=instances,pins=pins,identity=template['identity'],
        design=paths[0],vdb=str(vdb),test=str(vdb.with_suffix('')/samples[0].name),timeout_seconds=900,
        launch_authorized=False,population_application=False,DUT_functional_gain=False,source_proof_seal=PROOF_SHA,
        old_EL_inventory=p['old_EL_inventory'],python_executable=str(interpreter),input_VDB_count=1,
        owning_service_unit=service_unit or 'ara-'+out.name+'.service',owner_uid=os.getuid(),
        expected_cgroup=service_cgroup(service_unit or 'ara-'+out.name+'.service',os.getuid()),
        official_denominator_verified=False,protection_method='Exact global EL physical both-direction set proves low payload untouched; all76 plus native extras full-row audit')
    contract(c);text=native.primitive.candidate(c);parse_el(text,c);life.check(pins)
    selection=''.join('set qc_'+k+' {'+c[k]+'}\n' for k in ('design','vdb','test'))
    selection+='set qc_python {'+str(interpreter)+'}\nset qc_helper {'+str(Path(__file__).resolve())+'}\nset qc_instances {}\n'
    for i in instances:
        selection+='lappend qc_instances [list {'+i['scope']+'} [list '+' '.join('{'+s['native_label']+'}' for s in i['signals'])+']]\n'
    out.mkdir()
    for name,data in (('candidate.el',text),('queue_constant_native.tcl',(HERE/'cva6_fixed_fields_native768.tcl').read_text()),('selection.tcl',selection)):
        native.primitive.common.common.save(out/name,data);pins[str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',c);seal=life.digest(out/'config.json');check(out,seal)
    print(json.dumps(dict(output=str(out),seal=seal,objects=10,directions=18516,protected=76,launch_authorized=False)))


def verify(out,seal):
    c=check(out,seal);terminal=json.loads((out/'terminal.json').read_bytes())
    terminal_gate(terminal,c,out)
    require(json.loads((out/'live-identity.json').read_bytes())==terminal['actual_dve'],'Live/terminal identity differs')
    owner=json.loads((out/'runtime-ownership.json').read_bytes())
    require(owner['config_seal']==seal and owner['unit']==c['owning_service_unit'] and
            owner['cgroup']==c['expected_cgroup'] and type(owner['pid']) is int and owner['pid']>0,
            'Owning-service launch context')
    logs=terminal_logs(out)
    for name in ('launcher.log','DVEfiles/dve_gui.log'):
        require(not re.search(r'(?:Warning-|Error-|Fatal-|\b(?:Error|Fatal):|QUEUE_CONSTANT_NATIVE_FAILED|QUEUE_CONSTANT_CLEANUP_FAILED)',
                              logs[name]),'Native diagnostic')
    require(logs['DVEfiles/dve_gui.log'].splitlines().count('QUEUE_CONSTANT_NATIVE_DONE')==1,'Five-stage completion')
    first=parse_el((out/'first.el').read_text(),c);second=parse_el((out/'second.el').read_text(),c)
    require(first==second,'Exact semantic reload')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):require((out/name).read_bytes()==b'','Global reset not empty')
    counts=[audit(i,{stage:(out/f'native_{stage}_{k}.tsv').read_text() for stage in STAGES}) for k,i in enumerate(c['instances'])]
    result=dict(status='PASSIVE_CVXIF_PADDING10_18516_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=seal,
        native_inventory_counts=counts,exact_global_EL=True,semantic_reload=True,final_reset=True,
        low_payload_bitmask_protected=True,all76_and_native_extras_protected=True,
        DUT_functional_gain=False,population_application=False,official_denominator_verified=False,
        pins={**c['pins'],**{str(out/name):life.digest(out/name) for name in
            ('config.json','terminal.json','live-identity.json','runtime-ownership.json','execution.json',
             'first.el','second.el','initial-empty.el','reset-empty.el','final-empty.el',
             'terminal-evidence/launcher.log','terminal-evidence/DVEfiles/dve_gui.log')},
            **{str(out/f'native_{stage}_{k}.tsv'):life.digest(out/f'native_{stage}_{k}.tsv')
               for k in range(2) for stage in STAGES}})
    receipt=out/'capture-result.json'
    if receipt.exists():require(json.loads(receipt.read_bytes())==result,'Existing qualification receipt differs')
    else:life.save(receipt,result)


def run(out,seal,authorization):
    require(seal is not None and authorization==seal,'Explicit parent-reviewed seal required; no implicit launch')
    c=check(out,seal)
    require(cgroup_path(Path('/proc/self/cgroup').read_text())==c['expected_cgroup'], 'Run only inside exact owning user service')
    require(not(out/'runtime-ownership.json').exists(),'Once-only owning-service execution')
    life.save(out/'runtime-ownership.json',dict(pid=os.getpid(),unit=c['owning_service_unit'],cgroup=c['expected_cgroup'],config_seal=seal))
    def read_bound(path,sha):
        value=life.read_bound(path,sha)
        return dict(value,launch_authorized=True) if Path(path)==out/'config.json' else value
    def save(path,value):
        if Path(path)==out/'live-identity.json':
            require(type(value) is list and len(value)==1,'Exactly one live executable')
            for actual in value:
                actual['cgroup']=cgroup_path((Path('/proc')/str(actual['pid'])/'cgroup').read_text())
                actual['exe_sha256']=life.digest(actual['exe'])
            terminal_gate(dict(returncode=0,timeout=False,actual_dve=value),c,out)
        return life.save(path,value)
    private=SimpleNamespace(**{**vars(life),'read_bound':read_bound,'save':save})
    launched=[]
    def popen(*args,**kwargs):
        process=native.subprocess.Popen(*args,**kwargs);launched.append(process);return process
    subprocess_private=SimpleNamespace(**{**vars(native.subprocess),'Popen':popen})
    try:
        FunctionType(native.run.__code__,{**vars(native),'life':private,'verify':verify,'subprocess':subprocess_private})(out,seal)
    finally:
        for process in launched:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except native.subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','el','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--file');p.add_argument('--parent-reviewed-seal');p.add_argument('--service-unit')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out,a.service_unit)
    elif a.mode=='check':check(out,a.seal);print('PREPARED_CHECK_PASS_NO_EDA')
    elif a.mode=='el':print(len(parse_el((out/a.file).read_text(),json.loads((out/'config.json').read_bytes()))))
    elif a.mode=='verify':verify(out,a.seal)
    else:run(out,a.seal,a.parent_reviewed_seal)
