"""One explicit783 successor: qualified existing EL plus5316 local directions."""
import argparse
from pathlib import Path
from types import FunctionType
import report_population783_fpnew90 as previous
import fpnew_class_padding_local as native

stable, life, need = previous.stable, previous.life, previous.need
HERE = Path(__file__).resolve().parent
BASE, BASE_SHA = previous.BASE, previous.BASE_SHA
REPORT = life.OUT/'current-population783-fpnew90-prepared-agent-20261008-02'
REPORT_CONFIG_SHA = 'cd90ea43f021b88ae42eab1ab60c8112c7e92bc1201b5a11f1a8bd3d1cf9edae'
REPORT_QUAL_SHA = '9608d8a9cd8bc4a19601853bcf5e956b5681106c0aea07ab9668a25732bc04a9'
LOCAL = life.OUT/'fpnew-class-padding5316-local-prepared783-agent-20261008-01'
LOCAL_CONFIG_SHA = '0f5f5d968572f5402ffe8baa653d7bee54bf60df252cb6b335fd8575ea91cc3b'
LOCAL_QUAL_SHA = '8bf9630e48af1b05f62c528c43f0756d8c9fffaf06dd62c2764717b01eea1e63'
SCHEMA = 'EXACT_FORMAL783_EXISTING18220_PLUS_CLASS_PADDING5316_V1'
engine = previous.prior.frozen


def report_gate(q,c):
    need(q['status']=='CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         q['population']==q['actual_selected_tests']==c['population']==783 and
         q['config_seal']==REPORT_CONFIG_SHA and q['admission_seal']==BASE_SHA and
         c['schema']==previous.SCHEMA and c['admission']==dict(path=str(BASE),sha256=BASE_SHA),
         'Exact completed783 report authority')
    need(all(q[k] is True for k in ('complete_approved_EL_bitmask_union','all_other_bits_protected',
         'raw_reset_final_equal','applied_reloaded_equal','raw_hierarchy_vs_rooted_six_metrics_equal',
         'supported_roots_all_six_metrics_present','historical_PASS_only_no_new_RTL_signoff')),
         'Full preceding native five-stage qualification')
    need(q['source_design_native_pins']==c['pins'] and c['additional_direction_count']==18220 and
         len(c['input_ledger'])==len(set(c['input_ledger']))==784 and len(c['expected_selected'])==783 and
         c['full_OR_metric_instances']==6162 and c['official_denominator_verified'] is False,
         'Preserved exact783 source/policy boundary')


def local_gate(q,c):
    native.contract(c)
    need(q['status']=='CLASS_PADDING5316_LOCAL_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED' and
         q['config_seal']==LOCAL_CONFIG_SHA and (q['objects'],q['bits'],q['directions'])==(62,2658,5316) and
         q['full_native_typed_complements'] is True and q['per_bit_GUI_flags_claimed'] is False and
         q['raw_serialized_mapping_calibrated'] is False and q['population_application'] is False and
         q['official_percentage'] is None,'Exact completed partial-bit local qualification')


def union_gate(base,addition,c):
    native.records(addition,c)  # Reject duplicate directions/ranges before semantic set normalization.
    old, extra = stable.semantic(base), stable.semantic(addition)
    occupied, targets = engine.physical(old), engine.physical(extra)
    need(not extra[0] and sum(bin(v).count('1') for v in targets.values())==5316,'Exact5316 Toggle-only addition')
    headers={r for r in old[0] if previous.exact_fsm_header(r)}
    opaque=[r for r in old[0] if not previous.exact_fsm_record(r,headers)]
    for key,mask in targets.items():
        scope,checks,name,prefix,direction=key
        need(not any(scope==r[0] or scope.startswith(r[0]+'.') for r in opaque),'Opaque/whole ancestor collision')
        for prior,value in occupied.items():
            if prior[0]!=scope:continue
            need(prior[1]==checks,'Same-scope checksum collision')
            if name==prior[2] and prefix==prior[3] and direction==prior[4]:
                need(not value&mask,'Already-owned physical direction')
            need(not (name.startswith(prior[2]+'.') or prior[2].startswith(name+'.')),
                 'Packed parent/child ownership collision')
    combined=base.rstrip('\n')+'\n'+addition.rstrip('\n')+'\n'
    actual=stable.semantic(combined);expected=dict(occupied)
    for key,mask in targets.items():expected[key]=expected.get(key,0)|mask
    need(actual[0]==old[0] and engine.physical(actual)==expected,
         'Exact complete old non-Toggle and Toggle union preservation')
    return combined


def inherited(reader):
    q=reader.read(REPORT/'qualification.json',REPORT_QUAL_SHA,True)
    c=reader.read(REPORT/'config.json',REPORT_CONFIG_SHA,True);report_gate(q,c)
    pins=stable.merge(c['pins'],q['output_pins'],{str(REPORT/'qualification.json'):REPORT_QUAL_SHA,
        str(REPORT/'config.json'):REPORT_CONFIG_SHA})
    texts=[reader.read(REPORT/name,pins[str(REPORT/name)]).decode('ascii')
           for name in ('combined.el','applied.el','reloaded.el')]
    need(all(stable.semantic_seal(stable.semantic(t))==c['expected_EL_semantic_sha256'] for t in texts),
         'Existing qualified global EL exact semantic identity')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        need(reader.read(REPORT/name,pins[str(REPORT/name)])==b'','Predecessor actual empty states')
    return c,pins,texts[0]


def local(reader):
    q=reader.read(LOCAL/'capture-result.json',LOCAL_QUAL_SHA,True)
    c=reader.read(LOCAL/'config.json',LOCAL_CONFIG_SHA,True);local_gate(q,c)
    need(native.verify(LOCAL,LOCAL_CONFIG_SHA)==q,'Full unchanged local verifier replay differs')
    pins=stable.merge(c['pins'],q['pins'],{str(LOCAL/'capture-result.json'):LOCAL_QUAL_SHA,
                                         str(LOCAL/'config.json'):LOCAL_CONFIG_SHA})
    blobs=[reader.read(LOCAL/name,pins[str(LOCAL/name)]).decode('ascii') for name in ('first.el','second.el')]
    need(native.records(blobs[0],c)==native.records(blobs[1],c),'Exact partial native reload')
    return c,pins,blobs[1]


def approved(reader,manifest,seal):
    need(manifest==BASE and seal==BASE_SHA,'Fixed formal783, no successor population relabel')
    source,pins,text=inherited(reader)
    config,more,extra=local(reader)
    need(config['design']==source['input_ledger'][0],'Same frozen compiled image')
    pins=stable.merge(pins,more)
    a=reader.read(BASE,BASE_SHA,True)
    need(a['coverage_admitted'] is True,'Formal783 admission')
    p=BASE.parent/'combined-bits.json';bits=reader.read(p,a['output_pins'][str(p)],True)
    need(len(bits['tests'])==len(set(bits['tests']))==783 and
         sum(map(len,bits['metrics'].values()))==6162,'Preserved actual783 four-metric corpus')
    p=BASE.parent/'combined-inputs.txt'
    need(reader.read(p,a['output_pins'][str(p)]).decode().splitlines()==source['input_ledger'], 'Exact783 ledger')
    pins=stable.merge(pins,{str(BASE):BASE_SHA,str(BASE.parent/'combined-bits.json'):a['output_pins'][str(BASE.parent/'combined-bits.json')],
                          str(p):a['output_pins'][str(p)]})
    return source,pins,union_gate(text,extra,config),bits,source['genealogy'],source['suffix_activity']


def dependencies():
    return stable.merge(engine.dependencies(),{str(p):life.digest(p) for p in
        (Path(__file__).resolve(),HERE/'test_report_population783_classpadding.py',
         Path(previous.__file__).resolve(),Path(native.__file__).resolve())})


def metadata():
    c=life.read_bound(REPORT/'config.json',REPORT_CONFIG_SHA)
    return dict(additional_direction_count=23536,local_qualifications=[*c['local_qualifications'],
        dict(family='CLASS_PADDING5316',path=str(LOCAL/'capture-result.json'),sha256=LOCAL_QUAL_SHA,
             config_seal=LOCAL_CONFIG_SHA,directions=5316)],
        protection_basis=c['protection_basis']+'; exact classification padding partial bits; low class/slot bits and full typed complements retained')


namespace=dict(engine.prepare.__globals__,__file__=__file__,BASE=BASE,BASE_SHA=BASE_SHA,
               SCHEMA=SCHEMA,approved=approved,dependencies=dependencies,metadata=metadata)
prepare=FunctionType(engine.prepare.__code__,namespace)
check=FunctionType(engine.check.__code__,namespace)
verify=FunctionType(engine.verify.__code__,dict(namespace,check=check))
run=FunctionType(engine.run.__code__,dict(namespace,check=check,verify=verify))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','check','verify','run-reviewed'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--service-unit')
    p.add_argument('--parent-reviewed-seal');a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':
        need(a.service_unit and not a.seal and not a.parent_reviewed_seal,'Host-only prepare')
        prepare(out,a.service_unit)
    else:
        need(a.seal and not a.service_unit,'Sealed runtime only')
        if a.mode=='check':check(out,a.seal);print('CHECK_PASS_NO_EDA')
        elif a.mode=='verify':verify(out,a.seal)
        else:run(out,a.seal,a.parent_reviewed_seal)
