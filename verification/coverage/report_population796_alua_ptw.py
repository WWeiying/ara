"""Prepare one full796 five-stage report with exact ALUA137 and PTW156 additions."""
import argparse
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

import report_population795_pmp816 as old
import alua_group5_native137 as alua
import ptw_rvh0_outputs156_local_v2 as ptw

engine, stable, life, need = old.engine, old.stable, old.life, old.need
HERE = Path(__file__).resolve().parent
BASE = life.OUT/'akv-canonical-alias-offline-admitted796-parent-20261008-01/admission-manifest.json'
BASE_SHA = '1aa18b04d4b1f3a4a2d8182c0457e240f43e0538bbeabe1b0385724e5a56400d'
REPORT = life.OUT/'current-population795-pmp816-agent-20261008-01'
REPORT_SHA = '43b1c922c2561daa5d5e8cb51e30e471bb8d0eaa137d90ad10c63b55cf5257a5'
REPORT_CONFIG_SHA = 'e5914b638b926b7e983ab60187d94bfbc7623db88bbdca40d82faf0b340029c9'
ALUA = life.OUT/'alua-group5-native137-prepared795-agent-20261008-01'
ALUA_SHA = '25e2cb98bcf3ac6f31f85e508d1862e82a54dc19ecc61d9362ce675f0bd8966d'
PTW = life.OUT/'ptw-rvh0-outputs156-local-v2-prepared794-agent-20261008-01'
PTW_SHA = '903532ea922ee3dd427d289b8fda071a42b3939fa68f16a79aef8eab7f33ea4c'
SCHEMA = 'FORMAL796_EXACT795_POLICY_PLUS_ALUA137_PTW156_V1'
physical = old.prior.prior.physical


def corpus_gate(source,bits,chain,previous):
    ledger = source['input_ledger']
    need(len(ledger)==len(set(ledger))==797 and ledger[:-1]==previous['input_ledger'] and
         len(previous['input_ledger'])==796 and bits['tests']==ledger[1:], 'Exact795 prefix and unique796 endpoint')
    need(chain[:-1]==previous['genealogy'] and chain[-1]==dict(population=796,manifest=str(BASE),
         seal=BASE_SHA,new_vdb=ledger[-1]), 'Exact796 published genealogy')
    need({k:len(v) for k,v in bits['metrics'].items()}==engine.METRIC_COUNTS and
         sum(len(v) for v in bits['metrics'].values())==6162, 'Complete per-metric6162')
    need(source['hierarchy_roots']==previous['hierarchy_roots'] and len(source['hierarchy_roots'])==72 and
         source['tool_identity']==previous['tool_identity'], 'Unchanged roots and executable identity')


def union_gate(base,branch,toggle):
    before,b,t = map(stable.semantic,(base,branch,toggle))
    need(not b[1] and len(b[0])==137 and all(r[2]=='' and r[3].startswith('Branch 5 "718333796" "cmd.conv" (') for r in b[0]),
         'Only137 exact ALUA group5 Branch vectors')
    need(not t[0] and sum(bin(v).count('1') for v in physical(t).values())==156, 'Only156 exact PTW directions')
    need(not before[0]&b[0], 'Duplicate inherited Branch identity')
    for row in b[0]:
        scope,checks,metric,directive = row
        for previous in before[0]:
            if scope==previous[0]:
                need(checks==previous[1], 'Same scope checksum conflict')
                need(not(previous[3].startswith('Branch 5 ') and not re.search(r'\([0-9]+\)',previous[3])),
                     'Opaque whole Branch group overlap')
            need(not(previous[3]=='WHOLE_SCOPE' and (scope==previous[0] or scope.startswith(previous[0]+'.'))),
                 'Whole-scope ancestor overlaps ALUA')
    occupied,extra = physical(before),physical(t)
    for key,mask in extra.items():
        scope,checks,name,prefix,direction = key
        need(not any((scope==r[0] or scope.startswith(r[0]+'.')) and r[3]=='WHOLE_SCOPE' for r in before[0]),
             'Whole-scope ancestor overlaps PTW')
        for prior,value in occupied.items():
            if prior[0]!=scope:continue
            need(prior[1]==checks, 'Same PTW checksum conflict')
            need(not(prior==key and value&mask), 'Existing physical PTW direction overlap')
            need(not(name.startswith(prior[2]+'.') or prior[2].startswith(name+'.')),
                 'Packed parent/child overlap')
        need(not any(r[0]==scope and r[3].startswith('Toggle ') for r in before[0]),
             'Opaque same-scope Toggle ownership HOLD')
    text='\n'.join(s.rstrip('\n') for s in (base,branch,toggle))+'\n'
    after=stable.semantic(text);expected=dict(occupied)
    for key,mask in extra.items():expected[key]=expected.get(key,0)|mask
    need(after[0]==before[0]|b[0] and physical(after)==expected, 'Exact inherited plus137/156; no extra exclusion')
    return text


def qualification(reader):
    aq=reader.read(ALUA/'capture-result.json',ALUA_SHA,True)
    ac=reader.read(ALUA/'config.json',aq['config_sha256'],True)
    need(aq['status']=='ALUA_GROUP5_BRANCH137_NATIVE_QUALIFIED_NOT_APPLIED' and
         (aq['records'],aq['full_branch_inventory'],aq['protected_branch_positions'])==(137,404,267) and
         aq['terminal_returncode']==0 and aq['final_reset'] is True and aq['population_application'] is False and
         aq['initial_X_qualified'] is False and aq['condition_qualified'] is False, 'Full ALUA137 local qualification')
    alua.validate(ac)
    pq=reader.read(PTW/'capture-result.json',PTW_SHA,True)
    pc=reader.read(PTW/'config.json',pq['config_seal'],True)
    need(pq['status']=='PTW_RVH0_OUTPUTS156_LOCAL_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED' and
         (pq['fields'],pq['directions'],pq['protected_objects'])==(12,156,137) and
         pq['population_application'] is False and pq['X_MDA_internal_H_waived'] is False and
         pq['native_bit_direction_order_inferred'] is False and pc['schema']==ptw.SCHEMA,
         'PTW typed roundtrip only; no local excluded-flag or denominator claim')
    pins=stable.merge(ac['pins'],aq['files'],pc['pins'],pq['pins'],{
        str(ALUA/'capture-result.json'):ALUA_SHA,str(PTW/'capture-result.json'):PTW_SHA,
        str(ALUA/'config.json'):aq['config_sha256'],str(PTW/'config.json'):pq['config_seal']})
    blobs=[]
    for directory,config,gate in ((ALUA,ac,alua.bind_native),(PTW,pc,ptw.el_gate)):
        texts=[reader.read(directory/n,pins[str(directory/n)]).decode('ascii') for n in ('first.el','second.el')]
        values=[gate(s.encode('ascii') if directory==ALUA else s,config) for s in texts]
        need(values[0]==values[1], 'Full typed identity/annotation roundtrip')
        need(stable.semantic(texts[0])==stable.semantic(texts[1]), 'Full local EL semantic roundtrip')
        for n in ('initial-empty.el','reset-empty.el','final-empty.el'):
            need(reader.read(directory/n,pins[str(directory/n)])==b'', 'Local initial/reset/final empty')
        blobs.append(texts[1])
    packet=reader.read(alua.PACKET,alua.PACKET_SHA,True)
    # Source proofs are pinned independently of native capture success.
    source=reader.read(PTW/'source-proof.json',pins[str(PTW/'source-proof.json')],True)
    need(source['writer_proof'] and source['unknown_internal_H_state_protected'] is True and
         source['instance']==pc['instances'][0], 'Exact source-proven output instance only')
    return ac,pc,packet,blobs,stable.merge(pins,reader.pins)


def added_zero(bits,toggle,ac,pc,packet,design):
    alua.build_plan(packet,bits,design)
    count=0
    for scope,metrics in ac['plan']['scopes'].items():
        row=bits['metrics']['branch'][scope];definition=design.definition(scope,'branch')
        need(row['width']==101 and row['checksum'] in (None,'1417162425') and
             definition.get('chksum')=='1417162425', 'ALUA compiled checksum/shape')
        for entry in metrics['branch']:
            if entry['target']:
                index=entry['point']['raw_index']
                need(not(int(row['bits'],16)>>(row['width']-1-index)&1), 'ALUA source-zero counterexample HOLD')
                count+=1
    instance,=pc['instances'];row=toggle[instance['scope']]
    need(row['checksum']==instance['toggle_checksum'], 'PTW serialized checksum')
    coordinates=[i for s in instance['signals'] for i in s['missing_coordinates']]
    need(len(coordinates)==len(set(coordinates))==156 and row['width']>max(coordinates), 'Exact156 compiled coordinates')
    for index in coordinates:
        need(not(int(row['bits'],16)>>(row['width']-1-index)&1), 'PTW source-zero counterexample HOLD')
    need(count==137, 'Exact137 compiled targets')
    return dict(ALUA137_zero=True,PTW156_zero=True,PTW_local_excluded_flags_observed=False,
                local_official_denominator_proven=False,initial_X_or_delta_qualified=False)


def approved(reader,manifest,seal):
    need(Path(manifest)==BASE and seal==BASE_SHA, 'Only admitted formal796')
    source,pins,_,bits,chain,activity=engine.approved(reader,manifest,seal)
    previous=reader.read(REPORT/'config.json',REPORT_CONFIG_SHA,True)
    q=reader.read(REPORT/'qualification.json',REPORT_SHA,True)
    need(q['status']=='CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         q['config_seal']==REPORT_CONFIG_SHA and q['population']==q['actual_selected_tests']==795 and
         q['admission_seal']==old.BASE_SHA and q['source_design_native_pins']==previous['pins'], 'Complete795 report authority')
    for key in ('complete_approved_EL_bitmask_union','all_other_bits_protected','raw_reset_final_equal',
                'applied_reloaded_equal','raw_hierarchy_vs_rooted_six_metrics_equal','supported_roots_all_six_metrics_present'):
        need(q[key] is True, 'Inherited global gate '+key)
    corpus_gate(source,bits,chain,previous)
    pins=stable.merge(pins,previous['pins'],q['output_pins'],{
        str(REPORT/'config.json'):REPORT_CONFIG_SHA,str(REPORT/'qualification.json'):REPORT_SHA})
    base=reader.read(REPORT/'combined.el',pins[str(REPORT/'combined.el')]).decode('ascii')
    need(stable.semantic_seal(stable.semantic(base))==previous['expected_EL_semantic_sha256'], 'Sealed complete795 EL')
    for name in ('applied.el','reloaded.el'):
        need(stable.semantic(reader.read(REPORT/name,pins[str(REPORT/name)]).decode('ascii'))==stable.semantic(base),
             'Actual795 reload semantic union')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        need(reader.read(REPORT/name,pins[str(REPORT/name)])==b'', 'Actual795 empty reset/final')
    ac,pc,packet,blobs,extra=qualification(reader);pins=stable.merge(pins,extra)
    text=union_gate(base,*blobs)
    # Reuse the exact typed old constant-family serializers on the new sample
    # and complete796 OR; only the endpoint and its preceding manifest change.
    prior=SimpleNamespace(**dict(vars(old.prior),BASE=old.BASE,BASE_SHA=old.BASE_SHA))
    audit=FunctionType(old.suffix_zero.__code__,dict(old.suffix_zero.__globals__,
        BASE=BASE,BASE_SHA=BASE_SHA,prior=prior))(reader,pins,chain[-1],source)
    tpath=BASE.parent/'combined-toggle-bits.json'
    toggle=reader.read(tpath,pins[str(tpath)],True)
    design=alua.source.Design(Path(source['input_ledger'][0]))
    complete=added_zero(bits,toggle,ac,pc,packet,design)
    spath=BASE.parent/'single-bits.json'
    single=reader.read(spath,pins[str(spath)],True)
    paths=list((Path(chain[-1]['new_vdb'])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(paths)==1 and str(paths[0]) in pins, 'One admitted AKV796 Toggle sample')
    reader.read(paths[0],pins[str(paths[0])])
    rows,sha=old.prior.prior.suffix.native.rows(paths[0],{pc['instances'][0]['scope']})
    need(sha==pins[str(paths[0])], 'Actual796 native Toggle sample SHA')
    sample=added_zero(single,rows,ac,pc,packet,design)
    activity=dict(activity,AKV796_constant_suffix_audit=audit,ALUA_PTW_full796_zero=complete,
        ALUA_PTW_AKV796_single_zero=dict(sample, vdb=chain[-1]['new_vdb'],tgl_sha256=sha),
        EL_additions=dict(family='ALUA137_PTW156_ONLY',branch_vectors=137,toggle_directions=156,
            inherited_report_qualification_sha256=REPORT_SHA,inherited_complete_EL_sha256=pins[str(REPORT/'combined.el')],
            local_ALUA_qualification_sha256=ALUA_SHA,local_PTW_qualification_sha256=PTW_SHA,
            protected_ALUA_branch=267,protected_PTW_objects=137,exact_physical_disjoint_union=True,
            PTW_local_Excluded_readback_claimed=False,FP64_included=False),
        policy='Actual full796 five stages required; exact EL protects complement; no local denominator claim')
    return source,stable.merge(pins,reader.pins),text,bits,chain,activity


def dependencies():
    return stable.merge(old.dependencies(),{str(p):life.digest(p) for p in (
        Path(__file__).resolve(),HERE/'test_report_population796_alua_ptw.py',
        Path(alua.__file__).resolve(),Path(alua.source.__file__).resolve(),
        Path(ptw.__file__).resolve(),Path(ptw.old.__file__).resolve())})


def context():
    prepared,checked,verified,_=old.context()
    namespace=dict(prepared.__globals__,__file__=__file__,SCHEMA=SCHEMA,approved=approved,dependencies=dependencies)
    functions=[FunctionType(f.__code__,namespace,f.__name__,f.__defaults__) for f in (prepared,checked,verified)]
    namespace.update(zip(('prepare','check','verify'),functions))
    return (*functions,FunctionType(engine.run.__code__,namespace))


def runtime_context(out,seal):
    c=life.read_bound(out/'config.json',seal)
    need(c['schema']==SCHEMA and c['successor_entry']==str(Path(__file__).resolve()) and c['output']==str(out)
         and c['admission']==dict(path=str(BASE),sha256=BASE_SHA), 'Exact796 report runtime')
    need(c['pins'].get(str(Path(__file__).resolve()))==life.digest(__file__), 'Frozen consumer entry')
    return context()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','verify','run-reviewed'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal',required=True)
    p.add_argument('--service-unit');p.add_argument('--parent-reviewed-seal')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':
        need(a.service_unit is not None, 'Explicit future service only; no launch')
        context()[0](out,BASE,a.seal,a.service_unit)
    else:
        need(a.service_unit is None, 'Service identity from sealed config')
        f=runtime_context(out,a.seal)
        if a.mode=='check':f[1](out,a.seal);print('FULL796_ALUA_PTW_CHECK_PASS_NO_EDA')
        elif a.mode=='verify':f[2](out,a.seal)
        else:f[3](out,a.seal,a.parent_reviewed_seal)
