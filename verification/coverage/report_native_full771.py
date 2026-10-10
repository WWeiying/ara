"""Fresh formal771 report: qualified padding51/pack323; no speculative native owners."""
import argparse
import copy
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import verify_full770_queue_owner_offline as predecessor
import verify_vlsu_padding51_native770_offline as padding
import c910_pack_literal_native770 as pack
import mfpu_constants272_sourcefirst770 as mfpu

life,require=predecessor.life,predecessor.require
old=predecessor.frozen
base=old.frozen.frozen.base
HERE=Path(__file__).resolve().parent
TCL=Path(__file__).with_suffix('.tcl')
SCHEMA='FORMAL771_QUALIFIED770_PADDING51_PACK323_V1'
BASE=predecessor.OUT
Q=life.OUT/'native-increment770-offline-closure-agent-20261007-01/qualification.json'
Q_SHA='762f949e8bbb8cb55de20970c1f771b399cb4a6c6f0d09ab478da7d102f1259b'
CLOSURE=Q.parent/'closure.json'
CLOSURE_SHA='c91da347cbe4c3cc9b96d4aabf8923d8cae2cfe1a6481025d39b27f293e18fa0'
MANIFEST=life.OUT/'sv39-alias-offline-admitted-771-agent-20261007-01/admission-manifest.json'
MANIFEST_SHA='ad9e01dcd0ea3ef442d7f28934bf1695dca61c7b6d1c7580bd2a49f0c2569860'
PADDING=life.OUT/'vlsu-padding51-native770-offline-qualified-parent-20261007-01/qualification.json'
PADDING_SHA='f46d8d1d5405f72673bb11f70b226122e57a2e892fd0e6d9fe49d85386d4500d'
PACK=life.OUT/'c910-pack-literal323-native770-agent-20261007-01/capture-result.json'
PACK_SHA='7b0ea4d1136d5611f0ff3a66928c9b6028d7d949d0e232250688810db59f7a94'
MFPU_SHA='c952ffb9e09569c219b0a0cc878478a5941c603f02a92eb9b55662d098cc3215'
ADDED={'padding51':(PADDING,PADDING_SHA,padding.frozen,padding.audit,6528),
       'pack323':(PACK,PACK_SHA,pack,pack.audit,35632)}


def predecessor_gate():
    q=life.read_bound(Q,Q_SHA);b=life.read_bound(CLOSURE,CLOSURE_SHA)
    require(q['population']==770 and q['config_seal']==predecessor.SEAL and
            b['status']=='FULL770_RETAINED_QUEUE_OWNER_OFFLINE_CLOSURE_PASS' and
            b['qualification_sha256']==Q_SHA and b['source']==str(BASE) and
            b['source_directory_unchanged'] and b['original_failure_preserved'] and b['EDA_launched'] is False,
            'Exact offline-qualified770 predecessor required')
    require(q['observer_owner_reconciliation']['unique_retained_scalars']==40 and
            q['observer_owner_reconciliation']['changed_EL_coordinates']==0 and
            q['terminal_evidence']['wrapper_OS_exit_status']==1 and
            q['terminal_evidence']['launch_process_returncode']==0,'Preserve actual offline failure/closure distinction')
    for pins in (q['input_pins'],q['output_pins'],q['offline_adapter_pins'],b['external_pins']):life.check(pins)
    return q


def population(original):
    b=life.read_bound(MANIFEST,MANIFEST_SHA)
    require(b['coverage_admitted'] is True and b['baseline']==str(old.MANIFEST.parent) and
            b['baseline_seal']==old.MANIFEST_SHA,'Exact admitted770->771 prefix')
    pins=base.merge(b['input_pins'],b['output_pins'],{str(MANIFEST):MANIFEST_SHA})
    def bound(p):return life.read_bound(p,pins[str(p)])
    status=bound(MANIFEST.parent/'status.json')
    require(status['coverage_admitted'] is True and status['aggregate_passed']==771,'Formal771 status')
    bits=bound(MANIFEST.parent/'combined-bits.json')
    base.full_or(bound(old.MANIFEST.parent/'combined-bits.json'),bits,bound(MANIFEST.parent/'single-bits.json'),771)
    path=MANIFEST.parent/'combined-inputs.txt';require(life.digest(path)==pins[str(path)],'771 ledger pin')
    ledger=path.read_text().splitlines()
    require(ledger[:-1]==original['input_ledger'] and ledger==[ledger[0],*bits['tests']],'Exact770 prefix/unique771')
    selected=[str(Path(db).with_suffix('')/p.name) for db in ledger for p in
              sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if p.is_dir()]
    require(len(selected)==len(set(selected))==771,'Exact771 native selection')
    life.check(pins);return ledger,selected,pins


def qualified_family(key):
    require(key in ADDED,'Closed qualified registry')
    path,seal,module,audit,count=ADDED[key];q=life.read_bound(path,seal);life.check(q['pins'])
    if key=='padding51':
        require(q['status']=='VLSU_PADDING51_6528_NATIVE_OFFLINE_REVERIFIED_NOT_APPLIED' and
                q['original_DVE_returncode']==0 and q['arrays_flattened'] is False,'Exact padding offline qualification')
        out=Path(q['original_run']);cfgseal=padding.SEAL
    else:
        require(q['status']=='C910_PACK_LITERAL323_35632_NATIVE_QUALIFIED_NOT_APPLIED' and
                q['exact_global_EL'] and q['semantic_reload'] and q['finalreset'],'Exact pack native qualification')
        out=path.parent;cfgseal=q['config_seal']
    require(q['population_application'] is False,'Local qualification, not population report')
    c=life.read_bound(out/'config.json',cfgseal);life.check(c['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and terminal['timeout'] is False and len(terminal['actual_dve'])==1,'Actual native terminal0')
    refs={};signals={};labels={};whole={}
    for index,i in enumerate(c['instances']):
        stages={s:(out/('native_%s_%d.tsv'%(s,index))).read_text() for s in predecessor.STAGES}
        audit(i,stages)
        rows=pack.native.native_rows(stages['before']);scope=i['scope']
        refs[scope]=sorted([v['path'],v['meta'],name] for name,v in rows.items())
        signals[scope]=sorted(s['name'] for s in i['signals'])
        labels[scope]=sorted(s['native_label'] for s in i['signals'])
        whole[scope]=sorted(s['native_label'] for s in i['signals'] if set(s['bits'])==set(range(s['right'],s['left']+1)))
    text=(out/'first.el').read_text();canonical=module.parse_el(text,c)
    require(len(canonical)==count and canonical==module.parse_el((out/'second.el').read_text(),c),'Exact paired semantic reload')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):require((out/name).read_bytes()==b'','Native final/reset empty')
    return dict(config=c,output=str(out),reference=refs,signals=signals,native_targets=labels,targets=whole,
                canonical=base.prior.old.normalized(canonical),el=text,local_qualified=True,qualification_seal=seal,
                qualification_origin='SEALED_NATIVE_OR_STRICT_OFFLINE_REVERIFIED',
                source_pins=base.merge(c['pins'],q['pins'],{str(path):seal,str(out/'config.json'):cfgseal}))


def held_candidates():
    c=life.read_bound(mfpu.CONFIG,MFPU_SHA);mfpu.check_pins(c['pins']);mfpu.contract(c)
    return dict(mfpu_constants272=dict(status='HOLD_FRESH_BEFORE_BINDER_NOT_IMPLEMENTED_IN_THIS_REUSED_REPORT',
        source_contract_passed=True,source_config=str(mfpu.CONFIG),source_seal=MFPU_SHA,scopes=44,targets=272,
        required='Fresh complete typed inventory and every protected child; exact native target labels before apply',
        local_qualified=False,included=False),monitor02=dict(status='FAILED_BEFORE_IDENTITY_API_UNRESOLVED',included=False))


def model():
    ns=old.context()['private_namespace']()
    modules=dict(ns['MODULES'],**{k:SimpleNamespace(records=m.parse_el) for k,(_,_,m,_,_) in ADDED.items()})
    ns['MODULES']=modules
    def partition(text,c):
        template=Path(c['output'])/'combined.el'
        if not template.exists() or text==template.read_text():return base.partition(text,c)
        proxy=SimpleNamespace(private_namespace=lambda:dict(ns,partition=base.partition),base=old.closure.report.base)
        return FunctionType(old.closure.export_partition.__code__,
            dict(old.closure.export_partition.__globals__,report=proxy,OUT=template.parent))(text,c)
    records=FunctionType(base.records.__code__,dict(ns,partition=partition))
    def groups(c):
        proxy=SimpleNamespace(private_namespace=lambda:dict(ns,merged_observers=base.merged_observers),base=old.closure.report.base)
        legacy,_=FunctionType(old.closure.corrected_groups.__code__,dict(old.closure.corrected_groups.__globals__,report=proxy))(c)
        return predecessor.corrected_groups(c,legacy)[0]
    ns.update(records=records,merged_observers=groups)
    return ns


def canonical_gate(c,text):
    actual=model()['records'](text,c)
    require(actual==c['expected_union'],'Exact canonical global union differs')
    return actual


def host_hook(selection,c):
    import report_native_batch768_v3 as hostmodule
    host=FunctionType(hostmodule.host_hook.__code__,dict(vars(hostmodule),
        TCL=TCL,private_namespace=model))
    return host(selection,c)


def dependency_pins():
    files=[Path(__file__).resolve(),TCL,HERE/'test_report_native_full771.py',Path(predecessor.__file__),
           HERE/'test_verify_full770_queue_owner_offline.py',Path(padding.__file__),Path(pack.__file__),
           Path(mfpu.__file__),HERE/'report_native_batch768_v3.py']
    require([line for line in TCL.read_text().splitlines() if line and not line.startswith('#')]
            ==['source {'+str(old.frozen.TCL)+'}'],
            'Exact sourced Tcl predecessor')
    held=life.read_bound(mfpu.CONFIG,MFPU_SHA)
    return base.merge(old.dependency_pins(),held['pins'],
        {str(p):life.digest(p) for p in files},{str(mfpu.CONFIG):MFPU_SHA})


def retained_gate(c,original):
    changed={'schema','output','population','successor_entry','input_ledger','expected_selected',
             'new_families','added_qualified_families','held_candidates','admission',
             'predecessor_full_qualification','parent_launch_approval_required','expected_union','pins'}
    require(all(c.get(k)==v for k,v in original.items() if k not in changed),
            'Retained scope/shape/runtime contract differs')


def audit_observers(out,c):
    for name in ('applied.el','reloaded.el'):canonical_gate(c,(out/name).read_text())
    base.prior.audit_observers(out,dict(c,observer_captures=model()['merged_observers'](c)))


def check(out,seal):
    c=life.read_bound(out/'config.json',seal)
    require(c['schema']==SCHEMA and c['output']==str(out) and c['population']==771 and
            c['successor_entry']==str(Path(__file__).resolve()) and c['runtime_timeout_seconds']==5400,
            'Exact fresh771 report identity/budget')
    require(c['added_qualified_families']==sorted(ADDED) and c['parent_launch_approval_required'] is True,
            'No unknown additions')
    original=life.read_bound(BASE/'config.json',predecessor.SEAL)
    retained_gate(c,original)
    for p,sha in dependency_pins().items():require(c['pins'].get(p)==sha,'Dependency differs: '+p)
    require(set(c['new_families'])==set(original['new_families'])|set(ADDED),'Closed family registry')
    require(all(c['new_families'][k]==v for k,v in original['new_families'].items()),'Retained family drift')
    for key in ADDED:require(c['new_families'][key]==qualified_family(key),'Exact qualified family differs')
    predecessor_gate();life.check(c['pins'])
    ledger,selected,_=population(original)
    require(c['input_ledger']==ledger and c['expected_selected']==selected and
            (out/'inputs.txt').read_text().splitlines()==ledger,'Native population mismatch')
    actual=canonical_gate(c,(out/'combined.el').read_text())
    for key in ADDED:require(actual.pop(key)==c['new_families'][key]['canonical'],'Addition canonical mismatch')
    require(actual==original['expected_union'],'Retained complete770 canonical union differs')
    require(c['held_candidates']==held_candidates(),'HOLD origin/inclusion drift')
    return c


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh independent output')
    q=predecessor_gate();original=life.read_bound(BASE/'config.json',predecessor.SEAL)
    ledger,selected,ppins=population(original);extra={k:qualified_family(k) for k in ADDED}
    c=copy.deepcopy(original)
    c.update(schema=SCHEMA,output=str(out),population=771,successor_entry=str(Path(__file__).resolve()),
             input_ledger=ledger,expected_selected=selected,new_families=dict(original['new_families'],**extra),
             added_qualified_families=sorted(ADDED),held_candidates=held_candidates(),
             admission=dict(manifest=str(MANIFEST),seal=MANIFEST_SHA,population=771,exact770prefix=True,full6162_OR=True),
             predecessor_full_qualification=dict(path=str(Q),seal=Q_SHA),parent_launch_approval_required=True)
    combined=(BASE/'combined.el').read_text()+''.join(i['el'] for i in extra.values())
    c['expected_union']=model()['records'](combined,c)
    retained=copy.deepcopy(c['expected_union'])
    for key,item in extra.items():require(retained.pop(key)==item['canonical'],'Added canonical mismatch')
    require(retained==original['expected_union'],'Retained full770 union differs')
    selection=(BASE/'selection.tcl').read_text()+base.prior.selection_tail(dict(c,observer_captures=model()['merged_observers'](c)))
    deps=dependency_pins()
    pins=base.merge(original['pins'],q['output_pins'],q['offline_adapter_pins'],ppins,deps,
          {str(Q):Q_SHA,str(CLOSURE):CLOSURE_SHA},
          *(i['source_pins'] for i in extra.values()))
    life.check(pins);out.mkdir()
    for name,text in [('selection.tcl',selection),('combined.el',combined),('inputs.txt','\n'.join(ledger)+'\n')]:
        with (out/name).open('x') as f:f.write(text)
        require((out/name).read_bytes()==text.encode('ascii'),'No JSON-serialized Tcl')
        pins[str(out/name)]=life.digest(out/name)
    syntax=base.prior.old.parser(HERE/'check_generated_tcl.py')
    evidence=dict(syntax=[syntax.check(out/'selection.tcl'),syntax.check(TCL)],
        hook=host_hook(out/'selection.tcl',c),
        retained770_exact=True,extra_directions=42160,no_EDA=True)
    life.save(out/'host-generated-tcl-evidence.json',evidence);pins[str(out/'host-generated-tcl-evidence.json')]=life.digest(out/'host-generated-tcl-evidence.json')
    c['pins']=pins;life.check(pins);life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins),
                         included=sorted(ADDED),held=c['held_candidates'],host=evidence['hook'],EDA_launched=False)),flush=True)


def namespace():
    ns=old.context()['namespace']()
    def snapshot(data,out):
        c=life.read_bound(out/'config.json',data['config_seal'])
        require(c['output']==str(out) and c['schema']==SCHEMA and c['population']==771,
                'Snapshot output/config/schema identity differs')
        # Retain the actual directory-owned stdout contract; no external log substitution.
        ns_old=old.context()['namespace']()['snapshot_stdout']
        ns_old(data,out)
        data.update(population=771,formal771_manifest_seal=MANIFEST_SHA,added_qualified_families=sorted(ADDED),
                    excluded_MFPU272=False,monitor_included=False,source_first_full_session_qualified=sorted(set(old.frozen.frozen.inherited.FIRST)|{'queue312'}))
    ns.update(check=check,records=model()['records'],audit_observers=audit_observers,snapshot_stdout=snapshot,
              __file__=__file__,TCL=TCL)
    for name in ('verify','run'):ns[name]=FunctionType(ns[name].__code__,ns)
    return ns


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal')
    p.add_argument('--authorize-reviewed-run',action='store_true');p.add_argument('--authorize-source-first-full-session',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    else:
        require(a.seal,'Exact sealed config required')
        if a.mode=='run':require(a.authorize_reviewed_run and a.authorize_source_first_full_session,'Parent review required')
        namespace()[a.mode](out,a.seal)
