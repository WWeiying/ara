"""Exact763 prefix plus one native-qualified QBS case; no simulation/DVE."""
import argparse
from collections import Counter
import json
from pathlib import Path
from types import FunctionType

import coverage_bitmap_delta as bitmap
import qualify_qbs_payload_phase763 as q

life,require,toggle=q.life,q.require,q.toggle
BASE=q.recipe.BASE
BASE_SHA=q.recipe.BASE_SHA
QUAL=life.OUT/'qbs-payload-phase-qualified763-agent-20261007-01'
QUAL_SHA='7929b72d7ecb452d89cf59591acf5434db1945541a81e85f2ef0eff9619463b7'
RUN=life.OUT/'qbs-payload-phase-old-image763-agent-20261007-01'
OUT=life.OUT/'qbs-payload-phase-offline-admitted-764-agent-20261007-01'
CACHE=life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_BASE=life.OUT/'targeted-toggle-offline-admitted-741-parent-20261007-01/combined-bits.json'
SCHEMA='QBS_PHASE_HISTORICAL764_NATIVE_ADMISSION_V1'


def contract(qual,audit):
    expected=dict(status='QBS_PHASE763_FULL_NATIVE_QUALIFIED_NOT_ADMITTED',native_destination_bytes=512,
        full_vrf_bytes=8192,source_guard_bytes=7328,csr_words=24,measured_predicted_new_raw_directions=288,
        coverage_admitted=False,full_scalar_isa_verified=False,custom_spike_pass=False,simulation_rerun=False)
    q.runner.reused.exact(qual,expected,'Native qualification')
    q.runner.reused.exact(audit,dict(status='FULL8_COMPLETE_NATIVE_VRF_CSR_LIFECYCLE_PASS_NOT_FULL_SCALAR_ISA',
        custom_write_bytes=512,full_vrf_bytes=8192,initial_vrf_bytes=8192,csr_values=24,
        source_guard_bytes=7328,checks=41,full_scalar_isa_verified=False,spike_custom_isa_pass=False,
        coverage_admitted=False),'Native audit')
    q.runner.reused.exact(audit['contract'],dict(requests=51,responses=51,exceptions=0,
        protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0),'Native transaction contract')
    require(len(audit['bindings'])==2 and [b['phase'] for b in audit['bindings']]==[0,1] and
        all(b['backend_vl']==256 and b['software_vl']==8 and b['native_active_write_bytes']==256 and
            b['preserved_vrf_bytes']==3840 for b in audit['bindings']),'Actual two full8 bindings')


def merge(before,single):
    require(len(before['tests'])==len(set(before['tests']))==763 and
        str(RUN/'code.vdb') not in before['tests'] and single['tests']==[str(RUN/'code.vdb')],
        'Unique exact763 prefix and sole candidate')
    combined=bitmap.combine(before,single)
    require(combined['tests']==before['tests']+[str(RUN/'code.vdb')] and
        len(set(combined['tests']))==764,'Exact764 append')
    count=0
    for metric,rows in before['metrics'].items():
        for scope,row in rows.items():
            add=single['metrics'][metric][scope];new=combined['metrics'][metric][scope]
            require(type(row['width']) is int and row['width']>=0 and
                (row['width'],row['checksum'])==(add['width'],add['checksum'])==(new['width'],new['checksum']) and
                max(int(row['bits'],16).bit_length(),int(add['bits'],16).bit_length())<=row['width'] and
                int(new['bits'],16)==int(row['bits'],16)|int(add['bits'],16),'Independent every-instance OR')
            count+=1
    require(count==6162 and set(before['metrics'])==set(bitmap.METRICS),'Frozen6162 four-metric shape')
    return combined,bitmap.delta(before,combined)


def coordinates(before,after):
    records=[]
    for metric,rows in before['metrics'].items():
        for scope,row in rows.items():
            added=int(after['metrics'][metric][scope]['bits'],16)&~int(row['bits'],16)
            if added:
                records.append(dict(metric=metric,scope=scope,checksum=row['checksum'],width=row['width'],
                    positions=[i for i in range(row['width']) if added>>(row['width']-1-i)&1]))
    return records


def field_map(definition,width,gains):
    offset=0;output=[];seen=set()
    for node in definition.find('tglshape'):
        require(node.tag in ('node','vectornode'),'Unknown compiled Toggle node')
        name=node.get('name');require(name not in seen,'Duplicate compiled signal');seen.add(name)
        left=int(node.get('left',0));right=int(node.get('right',0))
        size=abs(left-right)+1 if node.tag=='vectornode' else 1
        selected=[c for c in gains if offset<=c<offset+2*size]
        if selected:
            output.append(dict(signal=name,declaration_line=node.get('line_num'),left=left,right=right,
                raw_offset=offset,raw_coordinates=selected,
                bit_pair_slots=[dict(bit=right+(c-offset)//2*(1 if left>=right else -1),
                    serialized_pair_slot=(c-offset)%2,coordinate=c) for c in selected]))
        offset+=2*size
    require(offset==width and sum(len(r['raw_coordinates']) for r in output)==len(gains),
        'Every new Toggle coordinate mapped exactly once')
    return output


def positive(delta,toggle_count):
    require(type(toggle_count) is int and toggle_count>=0 and
        all(type(v) is int and v>=0 for v in delta['metrics'].values()) and
        sum(delta['metrics'].values())+toggle_count>0,'Zero gain cannot become a formal case')


def check(single_inputs):
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    q.runner.reused.exact(base,dict(status='INDEPENDENT763_ADMITTED_DEFINED_ARCHITECTURE_PASS',population=763,
        baseline=762,coverage_admitted=True),'Formal763')
    qual=life.read_bound(QUAL/'qualification.json',QUAL_SHA)
    pins=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(pins,life.merge_pins(qual['input_pins'],qual['output_pins']))
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):QUAL_SHA})
    static=life.read_bound(q.recipe.STATIC,q.recipe.STATIC_SHA)
    pins=life.merge_pins(pins,static['pins'])
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_qbs_payload_phase764.py'),
              Path(bitmap.__file__).resolve(),Path(toggle.__file__).resolve(),Path(toggle.base.__file__).resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    # The cache and its exact741 prefix are sealed by the scoped source certificate.
    require(str(CACHE) in pins and str(CACHE_BASE) in pins,'Unbound prior Toggle OR cache/prefix')
    life.check(pins)
    def read(p):return life.read_bound(p,pins[str(p)])
    before=read(BASE/'combined-bits.json')
    ledger=[str(life.IMAGE)+'.vdb',*before['tests']]
    require(read(CACHE_BASE)['tests']==before['tests'][:741] and
        (BASE/'combined-inputs.txt').read_text().splitlines()==ledger,'Exact historical prefix/ledger')
    audit=read(QUAL/'runtime-audit.json');contract(qual,audit)
    # Recompute the complete native reference from sealed source bytes, not DUT-filled expected values.
    inputs=q.independent_native();view=q.view();symbols,data,sites=view.elf_view()
    replay=FunctionType(q.full8.runtime.__code__,dict(vars(q.full8),RUN=RUN))(view,symbols,data,sites,inputs)
    require(replay==audit,'Complete native gold/lifecycle replay differs')
    full_inputs=[str(life.IMAGE)+'.vdb',str(RUN/'code.vdb')]
    require(single_inputs.read_text().splitlines()==full_inputs,'Sole exact design/candidate input')
    single=bitmap.collect(single_inputs)
    require(all(pins.get(p)==h for p,h in single['input_hashes'].items()),'Unpinned candidate raw metric')
    design_db=Path(full_inputs[0])/'snps/coverage/db'
    for relative,sha in single['design'].items():
        path=design_db/relative
        require(pins.get(str(path))==sha,'Design/shape differs from frozen qualification')
    combined,delta=merge(before,single)
    cache=read(CACHE)
    require(cache['tests']==741 and cache['schema']=='RAW741_TOGGLE_SERIALIZED_CAPACITY_V1',
        'Wrong prior cache semantics')
    scopes=sorted(q.full8.SCOPES[:2])
    older={s:{k:cache['instances'][s][k] for k in ('width','checksum','bits')} for s in scopes}
    for name in before['tests'][741:]:
        files=list((Path(name)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Ambiguous763 suffix native Toggle')
        p=files[0];require(str(p) in pins,'Unpinned suffix native Toggle')
        rows,sha=toggle.rows(p,scopes);require(sha==pins[str(p)],'Suffix bytes drift')
        older=toggle.union(older,rows)
    files=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1 and files[0].parent.name==q.runner.NAME,'Exact candidate native Toggle')
    sample,sha=toggle.rows(files[0],scopes);require(sha==pins[str(files[0])],'Actual Toggle differs')
    newer=toggle.union(older,sample);gains=toggle.gains(older,newer)
    prediction=read(q.runner.PRE/'target-prediction.json')
    measured=q.measured_targets(prediction,sample)
    require(read(QUAL/'target-hit-audit.json')['targets']==measured and
        sum(len(t['measured_new_coordinates']) for t in measured)==288 and
        all(set(t['measured_new_coordinates'])<=set(gains[t['scope']]) for t in measured),
        'All predicted288 coordinates must be genuinely new vs763')
    shape=design_db/'shape/tgl.verilog.shape.xml'
    require(str(shape) in pins and life.digest(shape)==pins[str(shape)],'Unpinned Toggle declaration shape')
    checks,defs=toggle.definitions(toggle.xml(design_db/'design/verilog.design.xml'),
        toggle.xml(shape.with_name('tgl.verilog.info.xml')),toggle.xml(shape),scopes)
    fields={}
    for scope in scopes:
        require(checks[scope]==sample[scope]['checksum']=='3657545390','Compiled instance checksum')
        definition=q.recipe.mapping.mapping.ET.fromstring(defs[scope]['shape'])
        fields[scope]=field_map(definition,sample[scope]['width'],gains[scope])
    gain=sum(map(len,gains.values()));positive(delta,gain)
    toggle_record=dict(baseline=763,population=764,cache_population=741,exact_suffix_members=22,
        cache_historical_inputs_freshly_rehashed=False,scopes=gains,field_map=fields,
        new_raw_directions_by_scope={s:len(gains[s]) for s in scopes},total_new_raw_directions=gain,
        predicted_new_raw_directions=288,baseline_rows=older,single_rows=sample,combined_rows=newer,
        official_percentage=False,official_denominator_verified=False,
        semantics='Binary instance_data positions; serialized pair slots not relabeled as native0to1/1to0. Packed interval data is preserved as VDB evidence but not decoded.')
    facts=dict(native_destination_bytes=512,complete_vrf_bytes=8192,initial_vrf_bytes=8192,
        preserved_destination_register_bytes=7680,source_guard_bytes=7328,csr_values=24,
        software_checks=41,host_checks=44,host_negative_tests=42,requests=51,responses=51,
        uop_allocations=18,uop_completions=18,exceptions=0,full_scalar_ISA_verified=False,
        spike_custom_ISA_PASS=False,scope=qual['qualification_scope'])
    status=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=764,baseline=763,new_passed=1,
        exact763_prefix=True,full_OR_instances=6162,coverage_admitted=True,raw_delta=delta['metrics'],
        scoped_payload_toggle_new_raw_directions=gain,scoped_predicted_toggle_new_raw_directions=288,
        native_gold_facts=facts,historical_fixed_image_only=True,new_RTL_signoff=False,
        rtl_changed=False,simulation_rerun=False,DVE_launched=False,official_denominator_verified=False)
    life.check(pins)
    return pins,{'single-bits.json':single,'combined-bits.json':combined,'raw-delta.json':delta,
        'raw-new-coordinates.json':coordinates(before,combined),'scoped-toggle-gain.json':toggle_record,
        'native-gold-facts.json':facts,'status.json':status}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent-authorized',action='store_true');p.add_argument('--verify-seal');a=p.parse_args()
    require(bool(a.parent_authorized)!=bool(a.verify_seal),'One explicit mode')
    if not a.verify_seal:
        require(not OUT.exists(),'Preserve any previous evidence')
        OUT.mkdir()
        with (OUT/'single-inputs.txt').open('x') as stream:
            stream.write(str(life.IMAGE)+'.vdb\n'+str(RUN/'code.vdb')+'\n')
    pins,values=check(OUT/'single-inputs.txt')
    ledger='\n'.join([str(life.IMAGE)+'.vdb',*values['combined-bits.json']['tests']])+'\n'
    if a.verify_seal:
        manifest=life.read_bound(OUT/'admission-manifest.json',a.verify_seal)
        require(manifest['schema']==SCHEMA and manifest['baseline_seal']==BASE_SHA and
            manifest['qualification_seal']==QUAL_SHA and manifest['input_pins']==pins and
            manifest['output']==str(OUT) and manifest['explicit_parent_authorized'] is True and
            set(manifest['output_pins'])=={str(OUT/n) for n in (*values,'single-inputs.txt','combined-inputs.txt')},
            'Terminal sealed manifest binding')
        life.check(manifest['output_pins'])
        for name,value in values.items():
            require(life.read_bound(OUT/name,manifest['output_pins'][str(OUT/name)])==value,'Terminal replay differs')
        require((OUT/'combined-inputs.txt').read_text()==ledger,'Terminal exact763 ledger differs')
        print('QBS_PHASE764_REVERIFIED',a.verify_seal,flush=True);return
    for name,value in values.items():life.save(OUT/name,value)
    with (OUT/'combined-inputs.txt').open('x') as stream:stream.write(ledger)
    life.save(OUT/'admission-manifest.json',dict(schema=SCHEMA,output=str(OUT),baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(QUAL/'qualification.json'),qualification_seal=QUAL_SHA,input_pins=pins,
        output_pins={str(path):life.digest(path) for path in OUT.iterdir() if path.is_file()},
        explicit_parent_authorized=True))
    print('QBS_PHASE764_ADMITTED',life.digest(OUT/'admission-manifest.json'),
        values['status.json']['raw_delta'],values['status.json']['scoped_payload_toggle_new_raw_directions'],flush=True)


if __name__=='__main__':main()
