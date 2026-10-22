"""Fresh successor builder; all three added families require explicit qualified seals."""
import argparse
import copy
import inspect
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import report_native_batch768 as frozen
import capture_tlb_rvh0_726 as tlb
import launch_tlb_rvh0_726 as tlb_launch
import qbs_accum66_native as accum
import cva6_fixed_fields_native768 as fixed

life,require,merge=frozen.life,frozen.require,frozen.merge
HERE=Path(__file__).resolve().parent
TCL=Path(__file__).with_suffix('.tcl')
SCHEMA='FORMAL768_RETAINED766_SIX_FAMILIES_OPTIONAL_FIRST_CSR_V2'
FIXED_ANNOTATION='Frozen post-reset source invariant; no X, pressure, or module waiver'
REGISTRY={
    'tlb726':dict(module=tlb,status='TLB_RVH0_EXACT726_LOCAL_NATIVE_QUALIFIED',directions=8448,objects=726,
                  result='qualification.json',marker='TLB726_NATIVE_DONE'),
    'accum66':dict(module=accum,status='QBS_ACCUM66_CONFIG2112_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED',
                  directions=4224,objects=66,result='capture-result.json',marker='QBS_ACCUM66_NATIVE_DONE'),
    'fixed120':dict(module=fixed,status='CVA6_FIXED120_4396_NATIVE_QUALIFIED_NOT_APPLIED',directions=4396,
                   objects=120,result='capture-result.json',marker='QUEUE_CONSTANT_NATIVE_DONE')}


def fixed_contract(c):
    proof=life.read_bound(fixed.PROOF,fixed.PROOF_SHA);life.check(proof['pins'])
    require(c['source_proof_sha256']==fixed.PROOF_SHA and c['baseline']==768 and
            c['population_application'] is False,'Exact fixed-fields source proof')
    expected={(s['scope'],s['name']):s for s in proof['candidates']}
    observed={(i['scope'],s['name']):(i,s) for i in c['instances'] for s in i['signals']}
    require(set(expected)==set(observed) and len(observed)==120,'Only exact proof-owned120 objects')
    for key,p in expected.items():
        i,s=observed[key]
        require(s['bits']==list(range(p['selected_right'],p['selected_left']+1)) and
                i['toggle_checksum']==p['checksum'],'Fixed partial bits/checksum differ')
    require(len(fixed.primitive.bitset(c))==4396,'Exact fixed paired directions')


def fixed_records(text,c):
    annotations=[line.strip() for line in text.splitlines() if line.strip().startswith('ANNOTATION:')]
    require(annotations and all(line=='ANNOTATION: "'+FIXED_ANNOTATION+'"' for line in annotations),
            'Exact intended fixed-field annotation')
    # Original parser retains typed declaration, source partial bits and paired uniqueness.
    return fixed.parse_el(text,c)


MODULES=dict(frozen.MODULES,tlb726=SimpleNamespace(contract=tlb_launch.contract,records=tlb.records,__file__=tlb_launch.__file__),accum66=accum,
             fixed120=SimpleNamespace(contract=fixed_contract,records=fixed_records,__file__=fixed.__file__))


def parse(key,text,c):
    require(key in REGISTRY,'No arbitrary module registry')
    module=MODULES[key];module.contract(c)
    value=module.records(text,c)
    require(len(value)==REGISTRY[key]['directions'],'Exact direction capacity, not inferred gain')
    return frozen.prior.old.normalized(value)


def replay_qualified(key,path,seal):
    """Run the original full verifier without writes; no volatile-pin bypass."""
    require(key in REGISTRY,'Unreviewed family')
    d=REGISTRY[key];module=d['module'];q=life.read_bound(path,seal)
    require(path.name==d['result'] and q['status']==d['status'] and q['population_application'] is False,
            'Native family not qualified')
    out=path.parent;cfg_path=out/'config.json'
    cfg_seal=q.get('config_seal') or q['pins'].get(str(cfg_path))
    require(cfg_seal,'Explicit sealed native config required')
    c=life.read_bound(cfg_path,cfg_seal);life.check(c['pins']);life.check(q['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and terminal['timeout'] is False and len(terminal['actual_dve'])==1,
            'Actual terminal0 and launch-bound executable')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count(d['marker'])==1 and not (out/'error.txt').exists(),'Single complete native capture')
    writes=[]
    def save(destination,value):
        require(destination==path and not writes and value==q,'Substantive native replay differs')
        writes.append(True)
    proxy=SimpleNamespace(**dict(vars(module.life),save=save))
    # TLB has an equality-only existing-result path, so it need not invoke save.
    verifier=tlb_launch.verify if key=='tlb726' else module.verify
    FunctionType(verifier.__code__,dict(verifier.__globals__,life=proxy,print=lambda *a,**k:None))(out,cfg_seal)
    require(life.digest(path)==seal,'Qualification changed during readonly replay')
    return out,c,q,cfg_seal


def qualified_family(key,path,seal):
    out,c,q,cfg_seal=replay_qualified(key,path,seal)
    canonical=parse(key,(out/'first.el').read_text(),c)
    require(canonical==parse(key,(out/'second.el').read_text(),c),'Exact semantic saved reload')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes()==b'','Native global reset/final empty')
    refs={};signals={};native_targets={};whole={}
    for index,i in enumerate(c['instances']):
        scope=i['scope']
        if key=='fixed120':
            stages={s:(out/('native_%s_%d.tsv'%(s,index))).read_text() for s in frozen.prior.STAGES}
            fixed.audit_native(i,stages)
            rows=fixed.native_rows(stages['before'])
            refs[scope]=sorted([v['path'],v['meta'],name] for name,v in rows.items())
            signals[scope]=sorted(s['name'] for s in i['signals'])
            native_targets[scope]=sorted(s['native_label'] for s in i['signals'])
            whole[scope]=sorted(s['native_label'] for s in i['signals']
                                if set(s['bits'])==set(range(s['right'],s['left']+1)))
        else:
            module=REGISTRY[key]['module'];before=module.inventory(out,c,'before',index)
            require(all(module.inventory(out,c,s,index)==before for s in frozen.prior.STAGES),'Five-stage complement identity')
            mapping=before if key=='tlb726' else dict(before)
            refs[scope]=sorted(list(row) for row in mapping.values())
            names=sorted(t.get('signal',t.get('name')) for t in i['targets'])
            signals[scope]=names;native_targets[scope]=sorted(mapping[n][2] for n in names)
            whole[scope]=sorted(mapping[t.get('signal',t.get('name'))][2] for t in i['targets']
                                if not t.get('retained_source_bits'))
        require(len(signals[scope])==len(set(native_targets[scope])),'Unique exact actual target labels')
    require(sum(map(len,signals.values()))==REGISTRY[key]['objects'],'Exact full field set')
    pins=merge(c['pins'],q['pins'],{str(path):seal,str(out/'config.json'):cfg_seal,
        str(Path(REGISTRY[key]['module'].__file__).resolve()):life.digest(REGISTRY[key]['module'].__file__)})
    return dict(config=c,output=str(out),canonical=canonical,reference=refs,signals=signals,
        native_targets=native_targets,targets=whole,local_qualified=True,qualification_seal=seal,
        membership_authority='Exact source-bound paired typed EL; complete same-session aggregate flag complement',
        source_pins=pins,el=(out/'first.el').read_text())


def receipt_gate(receipts):
    require(set(receipts)==set(REGISTRY),'All three explicit qualified receipts required; no partial final batch')
    for key,(path,seal) in receipts.items():
        require(path.is_file() and len(seal)==64 and all(ch in '0123456789abcdef' for ch in seal),
                'Qualification absent or malformed: '+key)


def private_namespace():
    ns=dict(vars(frozen),__file__=__file__,TCL=TCL,SCHEMA=SCHEMA,MODULES=MODULES)
    for name in ('partition','records','merged_observers','audit_observers','host_hook','check','snapshot_stdout'):
        ns[name]=FunctionType(getattr(frozen,name).__code__,ns)
    return ns


def prepare(out,receipts,include_csr=True):
    receipt_gate(receipts)  # Runs before heavy pins and before output creation.
    extra={key:qualified_family(key,*receipt) for key,receipt in receipts.items()}
    read_path=life.OUT/'requester-read108-native767-agent-20261007-01/capture-result.json'
    read_seal='a31abca542924c82f51f53e4e2c5ed17b22c3476eae035ecdccd5f355dbe749b'
    ns=private_namespace()
    def additions(csr=False,*args):return dict(frozen.additions(csr,read_path,read_seal),**extra)
    ns['additions']=additions
    body=inspect.getsource(frozen.prepare)
    anchor="    deps=[Path(__file__).resolve(),TCL,HERE/'test_report_native_batch768.py',Path(prefix.__file__),"
    require(body.count(anchor)==1,'Frozen dependency adapter anchor differs')
    body=body.replace("HERE/'test_report_native_batch768.py'","HERE/'test_report_native_batch768_v2.py'")
    anchor="    c['expected_union']=records(combined,c)"
    require(body.count(anchor)==1,'Canonical construction anchor differs')
    body=body.replace(anchor,"    c['pending_next_family']=None\n    c['required_qualified_registry']=sorted(REGISTRY)\n"+anchor)
    ns['REGISTRY']=REGISTRY
    exec(compile(body,__file__,'exec'),ns)
    ns['prepare'](out,include_csr,read_path,read_seal)


def namespace():
    ns=frozen.namespace();private=private_namespace()
    ns.update({k:private[k] for k in ('__file__','TCL','SCHEMA','MODULES','check','records','audit_observers','snapshot_stdout')})
    original_check=ns['check']
    def check(out,seal):
        c=original_check(out,seal)
        require(set(REGISTRY)<=set(c['new_families']) and c['required_qualified_registry']==sorted(REGISTRY)
                and c['pending_next_family'] is None,'Pending/partial families cannot run')
        for key in REGISTRY:
            item=c['new_families'][key];require(item['local_qualified'] and item['qualification_seal'],
                                            'No source-only promotion')
        return c
    ns['check']=check
    for name in ('verify','run'):ns[name]=FunctionType(ns[name].__code__,ns)
    return ns


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal')
    p.add_argument('--receipt',nargs=3,action='append',metavar=('KEY','QUALIFICATION','SHA'))
    p.add_argument('--without-csr',action='store_true');p.add_argument('--authorize-reviewed-run',action='store_true')
    p.add_argument('--authorize-csr-first-qualification',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':
        entries=a.receipt or [];receipts={key:(Path(path).resolve(),sha) for key,path,sha in entries}
        require(len(entries)==len(receipts),'Duplicate family receipts')
        prepare(out,receipts,not a.without_csr)
    else:
        require(a.seal,'Exact sealed config')
        if a.mode=='run':
            c=namespace()['check'](out,a.seal)
            require(a.authorize_reviewed_run and (not c['csr_first_population_qualification'] or
                    a.authorize_csr_first_qualification),'Explicit parent authorization required')
        namespace()[a.mode](out,a.seal)
