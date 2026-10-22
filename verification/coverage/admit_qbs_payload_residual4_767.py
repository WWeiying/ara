"""Exact766 prefix plus one native-qualified matrix4; offline admission only."""
import argparse
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import coverage_bitmap_delta as bitmap
import qualify_qbs_payload_residual4_766 as q
import admit_qbs_payload_phase764 as prior
from admit_gap113_cached742 import toggle_shape

life,require=q.life,q.require
BASE,BASE_SHA=q.ranking.BASE,q.ranking.BASE_SHA
QUAL=life.OUT/'qbs-payload-residual4-qualified766-agent-20261007-01'
QUAL_SHA='b9f739e6bc557736c3bf2fc4996acd58cf49c522fdc85ec47685079113d92cad'
RUN=q.runner.RUN
OUT=life.OUT/'qbs-payload-residual4-offline-admitted-767-agent-20261007-01'
SCHEMA='QBS_RESIDUAL4_HISTORICAL767_NATIVE_ADMISSION_V1'


def contract(qual,audit):
    q.runner.reused.exact(qual,dict(status='RESIDUAL4_FULL_NATIVE_QUALIFIED_NOT_ADMITTED',baseline=766,
        native_destination_bytes=1024,full_vrf_bytes=16384,initial_vrf_bytes=16384,
        csr_values=48,source_readback_bytes=18176,commands=4,software_checks=24,
        full_scalar_isa_verified=False,custom_spike_pass=False,coverage_admitted=False,
        total_new_raw_directions=504,measured_predicted_directions=500),'Matrix qualification')
    require(len(audit['bindings'])==4 and [b['phase'] for b in audit['bindings']]==list(range(4)), 'Four phase bindings')
    q.runner.reused.exact(audit['contract'],dict(requests=92,responses=92,exceptions=0,
        protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0),'Native contract')
    require(all(b['backend_vl']==256 and b['software_vl']==8 and b['native_active_write_bytes']==256 and
        b['preserved_vrf_bytes']==3840 and sum(b['readback_bytes'].values())==9072 for b in audit['bindings']),
        'Full VRF/CSR/guards/source native scope')
    require(audit['source_observer_contract']==q.frozen.source_observer_contract(), 'Exact frozen load result observer')


def merge(before,single):
    require(len(before['tests'])==len(set(before['tests']))==766 and single['tests']==[str(RUN/'code.vdb')] and
        single['tests'][0] not in before['tests'], 'Unique full766 prefix')
    after=bitmap.combine(before,single);count=0
    require(after['tests']==before['tests']+single['tests'] and len(set(after['tests']))==767,'Exact767 append')
    for metric,rows in before['metrics'].items():
        for scope,row in rows.items():
            add=single['metrics'][metric][scope];new=after['metrics'][metric][scope]
            require(type(row['width']) is int and row['width']>=0 and
                (row['width'],row['checksum'])==(add['width'],add['checksum'])==(new['width'],new['checksum']) and
                max(int(row['bits'],16).bit_length(),int(add['bits'],16).bit_length())<=row['width'] and
                int(new['bits'],16)==int(row['bits'],16)|int(add['bits'],16),'Independent every-instance OR')
            count+=1
    require(count==6162 and set(before['metrics'])==set(bitmap.METRICS),'Exact6162 four-metric shape')
    return after,bitmap.delta(before,after)


def evaluate():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    qual=life.read_bound(QUAL/'qualification.json',QUAL_SHA)
    pins=life.merge_pins(life.merge_pins(base['input_pins'],base['output_pins']),
                         life.merge_pins(qual['input_pins'],qual['output_pins']))
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):QUAL_SHA})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_qbs_payload_residual4_767.py'),
                 Path(bitmap.__file__).resolve(),Path(prior.__file__).resolve()):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    def read(p):return life.read_bound(p,pins[str(p)])
    status=read(BASE/'status.json')
    require(status['aggregate_passed']==766 and status['coverage_admitted'] is True and
        status['status']=='PASS_RAW_UNION_HISTORICAL_ONLY','Formal766 not admitted')
    before=read(BASE/'combined-bits.json')
    require((BASE/'combined-inputs.txt').read_text().splitlines()==[str(life.IMAGE)+'.vdb',*before['tests']], 'Exact ordered766 ledger')
    audit=read(QUAL/'runtime-audit.json');contract(qual,audit)
    life.check(pins)
    require(q.runtime(RUN)==audit,'Independent full native/readback/lifecycle replay differs')
    inputs=str(life.IMAGE)+'.vdb\n'+str(RUN/'code.vdb')+'\n'
    with tempfile.TemporaryDirectory(prefix='qbs-residual4-raw-') as temporary:
        path=Path(temporary)/'inputs.txt';path.write_text(inputs)
        single=bitmap.collect(path)
    require(all(pins.get(p)==sha for p,sha in single['input_hashes'].items()), 'Singleton raw input not qualified')
    design=Path(str(life.IMAGE)+'.vdb')/'snps/coverage/db'
    require(single['design']==before['design'] and
        all(pins.get(str(design/p))==sha for p,sha in single['design'].items()), 'Frozen compiled design pin')
    after,delta=merge(before,single)
    gain_record=read(QUAL/'toggle-gain.json');scopes=sorted(gain_record['scopes'])
    suffix_files=list((Path(before['tests'][-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    new_files=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(suffix_files)==len(new_files)==1,'Unique native Toggle data')
    require(toggle_shape(suffix_files[0])==toggle_shape(new_files[0]), 'Full native binary/interval shape mismatch')
    old=read(BASE/'scoped-toggle-gain.json')['combined_rows']
    require(gain_record['baseline']==766 and gain_record['baseline_seal']==BASE_SHA,'Exact formal766 Toggle provenance')
    sample,sha=q.frozen.toggle.rows(new_files[0],scopes);require(sha==pins[str(new_files[0])],'Actual sample Toggle SHA')
    newer=q.frozen.toggle.union(old,sample);gains=q.frozen.toggle.gains(old,newer)
    require(old==gain_record['before_rows'] and sample==gain_record['single_rows'] and newer==gain_record['combined_rows'] and
        gains==gain_record['scopes'] and sum(map(len,gains.values()))==504,'Exact measured766 Toggle gain')
    shape=design/'shape/tgl.verilog.shape.xml'
    checks,defs=q.frozen.toggle.definitions(q.frozen.toggle.xml(design/'design/verilog.design.xml'),
        q.frozen.toggle.xml(shape.with_name('tgl.verilog.info.xml')),q.frozen.toggle.xml(shape),scopes)
    fields={s:prior.field_map(ET.fromstring(defs[s]['shape']),sample[s]['width'],gains[s]) for s in scopes}
    require(all(checks[s]==sample[s]['checksum']=='3657545390' for s in scopes),'Exact payload compiled binding')
    prior.positive(delta,504)
    scoped=dict(baseline=766,population=767,scopes=gains,field_map=fields,
        new_raw_directions_by_scope={s:len(gains[s]) for s in scopes},total_new_raw_directions=504,
        predicted_directions=504,measured_predicted_directions=500,
        baseline_rows=old,single_rows=sample,combined_rows=newer,official_percentage=False,
        official_denominator_verified=False,semantics='Exact binary instance_data positions, serialized pair-slot identity retained; not all-chip Toggle percentage or packed-array gain')
    facts=dict(commands=4,requests=92,responses=92,uop_allocations=36,uop_completions=36,
        custom_destination_bytes=1024,full_vrf_bytes=16384,initial_vrf_bytes=16384,
        csr_values=48,source_readback_bytes=18176,software_checks=24,host_checks=28,host_negative_tests=24,
        exceptions=0,full_scalar_ISA_verified=False,custom_spike_ISA_PASS=False,
        source_readback_semantics=audit['source_observer_contract']['semantics'])
    values={'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,
        'raw-new-coordinates.json':prior.coordinates(before,after),'scoped-toggle-gain.json':scoped,
        'native-gold-facts.json':facts,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
        aggregate_passed=767,baseline=766,new_passed=1,exact766_prefix=True,full_OR_instances=6162,
        coverage_admitted=True,raw_delta=delta['metrics'],scoped_payload_toggle_new_raw_directions=504,
        historical_fixed_image_only=True,new_RTL_signoff=False,rtl_changed=False,simulation_rerun=False,
        DVE_launched=False,full_scalar_ISA_verified=False,official_percentage_claimed=False)}
    life.check(pins)
    return pins,values


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-authorized',action='store_true')
    p.add_argument('--verify-seal');a=p.parse_args()
    require(bool(a.parent_authorized)!=bool(a.verify_seal),'One explicit mode')
    if a.parent_authorized:require(not OUT.exists(),'Preserve all prior outputs')
    pins,values=evaluate();ledger='\n'.join([str(life.IMAGE)+'.vdb',*values['combined-bits.json']['tests']])+'\n'
    if a.verify_seal:
        manifest=life.read_bound(OUT/'admission-manifest.json',a.verify_seal)
        require(manifest['schema']==SCHEMA and manifest['baseline_seal']==BASE_SHA and manifest['qualification_seal']==QUAL_SHA and
            manifest['input_pins']==pins and manifest['output']==str(OUT) and
            manifest['authorization_source']=='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL' and
            set(manifest['output_pins'])=={str(OUT/n) for n in (*values,'combined-inputs.txt')},'Terminal manifest binding')
        life.check(manifest['output_pins'])
        require(all(read_value(OUT/n,manifest['output_pins'][str(OUT/n)])==v for n,v in values.items()),'Terminal independent replay')
        require((OUT/'combined-inputs.txt').read_text()==ledger,'Exact767 ledger')
        print('FORMAL767_REVERIFIED '+a.verify_seal,flush=True);return
    OUT.mkdir()
    for name,value in values.items():life.save(OUT/name,value)
    with (OUT/'combined-inputs.txt').open('x') as f:f.write(ledger)
    life.save(OUT/'admission-manifest.json',dict(schema=SCHEMA,baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(QUAL/'qualification.json'),qualification_seal=QUAL_SHA,output=str(OUT),input_pins=pins,
        output_pins={str(p):life.digest(p) for p in OUT.iterdir() if p.is_file()},coverage_admitted=True,
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    print(json.dumps(dict(status='FORMAL767_ADMITTED',manifest=str(OUT/'admission-manifest.json'),
        seal=life.digest(OUT/'admission-manifest.json'),raw_delta=values['status.json']['raw_delta'],
        scoped_payload_toggle_new_raw_directions=504)),flush=True)


def read_value(path,sha):return life.read_bound(path,sha)


if __name__=='__main__':main()
