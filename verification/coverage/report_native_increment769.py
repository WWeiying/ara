"""One incremental entry, gated by qualified full768; no local native reruns."""
import argparse
import copy
import inspect
import json
import subprocess
from pathlib import Path
from types import FunctionType, SimpleNamespace

import report_native_batch768_v3 as inherited
import fma_lzc_assigned_native as lzc
import qualify_queue_fp312_native as queue
import audit_lzc_assigned_union_overlap as overlap

base,life,require=inherited.base,inherited.life,inherited.require
HERE=Path(__file__).resolve().parent
TCL=Path(__file__).with_suffix('.tcl')
SCHEMA='FORMAL769_INCREMENT_QUALIFIED768_LZC_QUEUE312_V1'
PREDECESSOR=overlap.BASE
PREDECESSOR_SHA=overlap.BASE_SHA
FORMAL=life.OUT/'tlb-asid-vpn-rsw-offline-admitted-769-agent-20261007-01'
MANIFEST=FORMAL/'admission-manifest.json'
MANIFEST_SHA='b6bd6cca9a31b67b38ae834bfb5736ed04c31f14302efeac2440657147317ecf'
QUEUE=life.OUT/'queue-fp312-native768-prepare-agent-20261007-01'
QUEUE_SHA='2695e8b64ff86f16bfe3c21d697825430a531e066250ebc19a2610cb6b443a18'
LZC_SHA='650c8ae7b592720ef66b1fe13252193a789bbdfcc9ce0c6d47267cd739b5ec2f'
UNIT_RECEIPT=life.OUT/'native-batch-full768-v3-unit-receipt-agent-20261007-02.json'
UNIT_RECEIPT_SHA='fe1082239eb69a5ffadb2ed4d983081f4b421ba7117d66526b1e5fbcadaed6b9'


def check_real_terminal(fields,receipt):
    require(fields.get('Id')==receipt['unit'] and fields.get('LoadState')=='loaded'
            and fields.get('ActiveState')=='inactive' and fields.get('SubState')=='dead'
            and fields.get('ExecMainCode')=='1' and fields.get('ExecMainStatus')=='0'
            and fields.get('ExecMainPID')==str(receipt['runner_pid']),
            'Actual original systemd foreground terminal0 required; active/GC/unknown stays HOLD')
    command=fields.get('ExecStart','')
    require(str(inherited.HERE/'report_native_batch768_v3.py') in command
            and str(PREDECESSOR) in command and PREDECESSOR_SHA in command,
            'Real terminal unit command/config differs')
    return dict(source='ACTUAL_SYSTEMD_FOREGROUND_EXECMAINSTATUS_ZERO_PLUS_PINNED_LIFECYCLE_GUARD',
                unit=receipt['unit'],observed_properties=fields,
                observed_foreground_returncode=0,standalone_DVE_OS_receipt_available=False,
                launch_bound_DVE_pid=receipt['actual_dve_pid'],unit_receipt_sha256=UNIT_RECEIPT_SHA)


def real_terminal():
    receipt=life.read_bound(UNIT_RECEIPT,UNIT_RECEIPT_SHA)
    require(receipt['config_sha256']==PREDECESSOR_SHA and receipt['actual_dve_cwd']==str(PREDECESSOR),
            'Original observed launch/config binding')
    names='Id,LoadState,ActiveState,SubState,ExecMainPID,ExecMainCode,ExecMainStatus,ExecStart'
    text=subprocess.check_output(['systemctl','--user','show',receipt['unit'],'--property='+names],text=True)
    return check_real_terminal(dict(row.split('=',1) for row in text.splitlines()),receipt)


def lzc_contract(c):
    q=life.read_bound(overlap.NEW/'capture-result.json',LZC_SHA)
    require(c==life.read_bound(overlap.NEW/'config.json',q['config_seal']), 'Exact qualified LZC config')


def queue_contract(c):
    queue.contract(c)
    require(c==life.read_bound(QUEUE/'config.json',QUEUE_SHA),'Exact source-bound queue312 config')


MODULES=dict(inherited.MODULES,
    lzc23132=SimpleNamespace(contract=lzc_contract,records=lzc.parse_el,__file__=lzc.__file__),
    queue312=SimpleNamespace(contract=queue_contract,records=queue.parse_el,__file__=queue.__file__))


def new_families():
    overlap.audit()
    q=life.read_bound(overlap.NEW/'capture-result.json',LZC_SHA);life.check(q['pins'])
    c=life.read_bound(overlap.NEW/'config.json',q['config_seal'])
    refs={};signals={};labels={};whole={}
    for k,i in enumerate(c['instances']):
        rows=lzc.native.native_rows((overlap.NEW/('native_before_%d.tsv'%k)).read_text())
        scope=i['scope'];refs[scope]=sorted([v['path'],v['meta'],n] for n,v in rows.items())
        signals[scope]=sorted(s['name'] for s in i['signals'])
        labels[scope]=sorted(s['native_label'] for s in i['signals'])
        whole[scope]=sorted(s['native_label'] for s in i['signals'] if s['dimensions']==s['selected_dimensions'])
    text=(overlap.NEW/'first.el').read_text()
    result=dict(lzc23132=dict(config=c,output=str(overlap.NEW),reference=refs,signals=signals,
        native_targets=labels,targets=whole,canonical=base.prior.old.normalized(lzc.parse_el(text,c)),el=text,
        local_qualified=True,qualification_seal=LZC_SHA,qualification_origin='QUALIFIED_ASSIGNED_LIBRARY_SCOPE',
        source_pins=base.merge(c['pins'],q['pins'],{str(overlap.NEW/'capture-result.json'):LZC_SHA,
            str(overlap.NEW/'config.json'):q['config_seal']})))
    c=life.read_bound(QUEUE/'config.json',QUEUE_SHA);life.check(c['pins']);queue_contract(c)
    bindings,hpins=queue.historical_binding()
    require(json.loads(json.dumps(bindings))==c['historical_bindings'],'Exact historical full68 reference')
    refs={};signals={};labels={};lines=[]
    for i,b in zip(c['instances'],bindings):
        scope=i['scope'];refs[scope]=sorted(list(row[1:]) for row in b['exact_full68_identity'])
        signals[scope]=sorted(n['name'] for n in i['targets'])
        names={r[0]:r[3] for r in b['exact_full68_identity']};labels[scope]=sorted(names[n] for n in signals[scope])
        lines+=['CHECKSUM: "'+i['design_module_checksum']+' '+i['toggle_checksum']+'"',
                'INSTANCE: '+scope,'ANNOTATION: "'+queue.ANNOTATION+'"']
        lines+=['Toggle '+n['name']+' "logic '+n['name']+queue.bounds(n)+'"' for n in i['targets']]
    text='\n'.join(lines)+'\n';canonical=queue.parse_el(text,c)
    _,old_fields=overlap.ownership((PREDECESSOR/'combined.el').read_text())
    fields={(s,n) for s,ns in signals.items() for n in ns}
    require(not old_fields&fields,'Queue field ownership overlaps retained EL; explicit review required')
    result['queue312']=dict(config=c,output=str(QUEUE),reference=refs,signals=signals,native_targets=labels,
        targets=labels,el=text,canonical=base.prior.old.normalized(canonical),local_qualified=False,
        qualification_seal=None,qualification_origin=inherited.ROLE,population_application=False,
        reference_pins=hpins,source_pins=base.merge(c['pins'],hpins,{str(QUEUE/'config.json'):QUEUE_SHA}),
        first_full_session_before_required=True)
    return result


def predecessor_gate(path,seal):
    require(path==PREDECESSOR/'qualification.json','Only current full768 predecessor')
    q=life.read_bound(path,seal)
    require(q['status']=='SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED' and q['population']==768,
            'Full768 not qualified; no pending-result promotion')
    life.check(q['output_pins'])
    require(q['source_first_full_session_qualified']==sorted(inherited.FIRST), 'Missing source-first full validation')
    # Full-population reports use the pinned foreground lifecycle zero-return
    # guard, not the local-native terminal.json receipt format.
    lifecycle=inspect.getsource(base.prior.old.base.run)
    require("require(code == 0, 'DVE nonzero exit')" in lifecycle and
            lifecycle.index("require(code == 0, 'DVE nonzero exit')") < lifecycle.index('verify(out, seal)'),
            'Frozen foreground zero-return-before-verify guard differs')
    require(q['config_seal']==PREDECESSOR_SHA and q['lifecycle_stdout']['immutable_prefix_sha256']==
            q['output_pins'][q['lifecycle_stdout']['immutable_snapshot']],
            'Actual successful lifecycle snapshot and predecessor config binding')
    reports=q['module_reports'];main='ara_tb.dut.i_ara_soc.i_system'
    require(all(main in reports[s] for s in ('raw','applied','reset','reloaded','final')),
            'Exact main-root five metrics required')
    require(reports['raw']==reports['reset']==reports['final'] and reports['applied']==reports['reloaded'],
            'Full768 five-stage metric parity')
    q=dict(q,observed_terminal_evidence=real_terminal())
    return q


def population(original):
    book=life.read_bound(MANIFEST,MANIFEST_SHA)
    require(book['coverage_admitted'] is True and book['baseline']==str(base.FORMAL)
            and book['baseline_seal']==base.MANIFEST_SHA,'Exact admitted769 prefix')
    pins=base.merge(book['input_pins'],book['output_pins'],{str(MANIFEST):MANIFEST_SHA})
    def bound(p):return life.read_bound(p,pins[str(p)])
    bits=bound(FORMAL/'combined-bits.json')
    base.full_or(bound(base.FORMAL/'combined-bits.json'),bits,bound(FORMAL/'single-bits.json'),769)
    ledger=bound(FORMAL/'status.json')
    require(ledger['coverage_admitted'] is True and ledger['aggregate_passed']==769,'Formal769 status')
    path=FORMAL/'combined-inputs.txt';require(life.digest(path)==pins[str(path)],'Actual ledger pin')
    ledger=path.read_text().splitlines()
    require(ledger[:-1]==original['input_ledger'] and ledger==[ledger[0],*bits['tests']], 'Exact768 prefix to769')
    selected=[str(Path(db).with_suffix('')/p.name) for db in ledger for p in
              sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if p.is_dir()]
    require(len(selected)==len(set(selected))==769,'Actual769 selection')
    return ledger,selected,pins


def private_namespace():
    ns=inherited.private_namespace()
    ns.update(__file__=__file__,TCL=TCL,SCHEMA=SCHEMA,MODULES=MODULES,BASE=PREDECESSOR,
              BASE_SHA=PREDECESSOR_SHA,FORMAL=FORMAL,MANIFEST=MANIFEST,MANIFEST_SHA=MANIFEST_SHA)
    def origin(key,item):
        if key=='queue312':inherited.origin_gate('csr1193',item)
        else:inherited.origin_gate(key,item)
    ns['origin_gate']=origin
    for name in ('partition','records','merged_observers','audit_observers'):
        ns[name]=FunctionType(getattr(base,name).__code__,ns)
    body=inspect.getsource(base.check).replace("require(item['local_qualified'] == (key != 'csr1193'), 'Separate qualification origins')",'origin_gate(key,item)')
    body=body.replace("c['population'] == 768","c['population'] == 769").replace('== 768\n','== 769\n')
    exec(compile(body,__file__,'exec'),ns)
    def host(selection,c):
        # The inherited fixed host adapter uses its own merged groups: pass all families,
        # and private-load the exact same source with this entry's Tcl path only.
        body=inspect.getsource(inherited.host_hook).replace('TCL=TCL','TCL=next_tcl')
        scope=dict(vars(inherited),next_tcl=TCL)
        exec(compile(body,__file__,'exec'),scope)
        return scope['host_hook'](selection,c)
    ns['host_hook']=host
    return ns


def prepare(out,qualification,seal):
    q=predecessor_gate(qualification,seal)  # Reject pending before creating output.
    original=life.read_bound(PREDECESSOR/'config.json',PREDECESSOR_SHA)
    extra=new_families();ns=private_namespace()
    ns['additions']=lambda *args:dict(copy.deepcopy(original['new_families']),**extra)
    def pop(c):
        ledger,selected,pins=population(c)
        return ledger,selected,base.merge(pins,q['output_pins'],{str(qualification):seal,str(UNIT_RECEIPT):UNIT_RECEIPT_SHA})
    ns['population']=pop
    body=inspect.getsource(base.prepare)
    body=body.replace('population=768','population=769').replace('population=768,exact766prefix=True','population=769,exact766prefix=True')
    body=body.replace("HERE/'test_report_native_batch768.py'","HERE/'test_report_native_increment769.py', Path(inherited.__file__), inherited.TCL, Path(lzc.__file__), Path(queue.__file__), Path(overlap.__file__)")
    anchor="    c['expected_union']=records(combined,c)"
    require(body.count(anchor)==1,'Increment construction anchor')
    body=body.replace(anchor,"    c['pending_next_family']=None\n    c['predecessor_full_qualification']={'path':str(qualification),'seal':seal}\n    c['predecessor_terminal_evidence']=predecessor_terminal_evidence\n"+anchor)
    anchor="    for key,item in extra.items():require(retained.pop(key) == item['canonical'],'New canonical membership differs')"
    require(body.count(anchor)==1,'Increment retained-union anchor')
    body=body.replace(anchor,anchor.replace('extra.items()','added.items()'))
    ns.update(inherited=inherited,lzc=lzc,queue=queue,overlap=overlap,qualification=qualification,seal=seal,added=extra,
              predecessor_terminal_evidence=q['observed_terminal_evidence'])
    exec(compile(body,__file__,'exec'),ns);ns['prepare'](out,True,Path('unused'), 'inherited')


def namespace():
    ns=inherited.namespace();private=private_namespace()
    ns.update({k:private[k] for k in ('__file__','TCL','SCHEMA','MODULES','check','records','audit_observers')})
    def snapshot(data,out):
        base.prior.snapshot_stdout(data,out)
        data.update(population=769,formal769_manifest_seal=MANIFEST_SHA,
                    queue312_first_full_session_qualified=True,lzc_assigned_bits=23132,
                    LZC_initial_X_excluded=False,LZC_spare_bits_retained=212)
    ns['snapshot_stdout']=snapshot
    for name in ('verify','run'):ns[name]=FunctionType(ns[name].__code__,ns)
    return ns


def rehearsal(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh host-only evidence directory')
    c=life.read_bound(PREDECESSOR/'config.json',PREDECESSOR_SHA)
    ledger,selected,ppins=population(c)
    added=new_families();c=copy.deepcopy(c);c['new_families'].update(added)
    ns=private_namespace();text=(PREDECESSOR/'combined.el').read_text()+''.join(i['el'] for i in added.values())
    canonical=ns['records'](text,c);retained=copy.deepcopy(canonical)
    for key,item in added.items():require(retained.pop(key)==item['canonical'],'Added canonical differs')
    require(retained==life.read_bound(PREDECESSOR/'config.json',PREDECESSOR_SHA)['expected_union'],
            'Retained768 changed')
    selection=(PREDECESSOR/'selection.tcl').read_text()+base.prior.selection_tail(
        dict(c,observer_captures=ns['merged_observers'](c)))
    out.mkdir()
    with (out/'selection.tcl').open('x') as stream:stream.write(selection)
    evidence=ns['host_hook'](out/'selection.tcl',c)
    syntax=base.prior.old.parser(HERE/'check_generated_tcl.py')
    evidence['syntax']=[syntax.check(out/'selection.tcl'),syntax.check(TCL)]
    life.save(out/'host-evidence.json',evidence)
    deps=[Path(__file__).resolve(),TCL,HERE/'test_report_native_increment769.py',
          Path(inherited.__file__),inherited.TCL,Path(lzc.__file__),Path(queue.__file__),Path(overlap.__file__)]
    pins=base.merge(ppins,*(i['source_pins'] for i in added.values()),
        {str(p):life.digest(p) for p in deps},
        {str(PREDECESSOR/'config.json'):PREDECESSOR_SHA,
         str(out/'selection.tcl'):life.digest(out/'selection.tcl'),
         str(out/'host-evidence.json'):life.digest(out/'host-evidence.json')})
    life.check(pins)
    plan=dict(status='HOST_REHEARSAL_PASS_NOT_RUNTIME_PREPARED',population=769,
        manifest_seal=MANIFEST_SHA,exact768prefix=True,full6162_OR=True,selected_tests=len(selected),
        new_families={k:dict(local_qualified=i['local_qualified'],qualification_origin=i['qualification_origin'],
            scopes=len(i['reference']),fields=sum(map(len,i['signals'].values()))) for k,i in added.items()},
        retained768_canonical_exact=True,parent_launch_required=True,
        predecessor_full768_qualification_and_real_terminal_required=True,EDA_launched=False,pins=pins)
    life.save(out/'plan.json',plan)
    print(json.dumps(dict(status=plan['status'],output=str(out),seal=life.digest(out/'plan.json'))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('rehearsal','prepare','check','verify','run'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seal');p.add_argument('--predecessor-seal');p.add_argument('--authorize-reviewed-run',action='store_true')
    p.add_argument('--authorize-source-first-full-session',action='store_true');a=p.parse_args()
    if a.mode=='rehearsal':rehearsal(a.output.resolve())
    elif a.mode=='prepare':prepare(a.output.resolve(),PREDECESSOR/'qualification.json',a.predecessor_seal)
    else:
        require(a.seal,'Exact config seal')
        if a.mode=='run':inherited.authorize(a.authorize_reviewed_run,a.authorize_source_first_full_session)
        namespace()[a.mode](a.output.resolve(),a.seal)
