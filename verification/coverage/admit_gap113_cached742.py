"""Compact exact741 + one qualified full8 admission; five native metrics, no EDA."""
import argparse
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import coverage_bitmap_delta as bitmap
import run_gap95_simulation as life

OUT=life.OUT
BASE=OUT/'targeted-toggle-offline-admitted-741-parent-20261007-01'
BASE_SHA='ad53b488eb12de7c8fe1a470d72c5a36dbea5cb349383dcf9c3c8068cebfb0f1'
QUAL=OUT/'gap113-payload-full8-cached-qualified-agent-20261007-01'
QUAL_SHA='e55cd7a81b02211dc41d85eef3057c75e7c5b571ba10e548cb902520e7b43076'
VDB=OUT/'gap113-payload-full8-cached-old-image-741-agent-20261007-01/code.vdb'
NAME='qbs_gap113_payload_full8_cached'
ELF=OUT/'gap113-payload-full8-cached-preflight-741-agent-20261007-01'/ (NAME+'.elf')
ELF_SHA='ecf747a5c59d6c439819b2d7757a932684e52b16f183536660476d517b4165a5'
DESIGN=OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'


def require(ok,message):
    if not ok:raise ValueError(message)


def exact_prefix(before,inputs):
    require(len(before)==len(set(before))==741 and inputs==[str(DESIGN),*before],
            'Exact unique741 inputs required')
    require(str(VDB) not in before,'Duplicate candidate')


def oracle_contract(q,audit):
    require(q['status']=='FULL8_NATIVE_QUALIFIED_RAW741_DIAGNOSTIC_NOT_ADMITTED' and
            q['coverage_admitted'] is False and q['rtl_changed'] is False and
            q['simulation_rerun'] is False and q['full_scalar_isa_verified'] is False,'Exact full8 qualification')
    expected=dict(status='FULL8_COMPLETE_NATIVE_VRF_CSR_LIFECYCLE_PASS_NOT_FULL_SCALAR_ISA',
                  custom_write_bytes=512,custom_active_bytes=512,custom_preserved_vrf_bytes=7680,
                  full_vrf_bytes=8192,initial_vrf_bytes=8192,csr_values=24,source_guard_bytes=7328,
                  checks=41,full_scalar_isa_verified=False,spike_custom_isa_pass=False)
    require(all(audit.get(k)==v for k,v in expected.items()),'Incomplete native/VRF/source/CSR checks')
    c=audit['contract']
    require(c['requests']==c['responses']==51 and all(c[k]==0 for k in
            ('exceptions','protocol_errors','outstanding')),'Incomplete/error contract')
    require(len(audit['bindings'])==len(audit['numeric_oracles'])==2,'Exactly two native commands')
    for phase,(binding,oracle) in enumerate(zip(audit['bindings'],audit['numeric_oracles'])):
        require(binding['phase']==phase and binding['backend_vl']==256 and binding['software_vl']==8 and
                binding['native_total_write_bytes']==binding['native_active_write_bytes']==256 and
                binding['preserved_vrf_bytes']==3840 and oracle['n']==8 and oracle['fflags']==0 and
                len(oracle['result_bits'])==len(oracle['integer_dots'])==64 and
                binding['readback_bytes']==dict(initial=4224,actual=4224,weights=1024,activation=2496,
                                                descriptor_packet=144,csr_packet=160),
                'Incomplete per-command full native/readback/lifecycle evidence')


def toggle_shape(path):
    rows=bitmap.read_metric(path)
    with gzip.open(path,'rb') as stream:root=ET.parse(stream).getroot()
    intervals={}
    for node in root.iter('instance_intervaldata'):
        scope=node.get('name')
        require(scope in rows and scope not in intervals and node.get('chksum')==rows[scope]['checksum'] and
                node.get('value','').strip(),'Missing/duplicate/aliased array interval row')
        tokens=[int(x) for x in node.get('value').split()]
        require(tokens.count(-1)>0,'Incomplete native interval groups')
        intervals[scope]=(node.get('chksum'),tokens.count(-1))
    return {s:(r['width'],r['checksum']) for s,r in rows.items()},intervals


def native_five(single,pins,reference):
    paths=[]
    for metric in (*bitmap.METRICS,'tgl'):
        files=list((VDB/'snps/coverage/db/testdata').glob('*/%s.verilog.data.xml'%metric))
        require(len(files)==1 and files[0].parent.name==NAME,'Native five-metric test identity differs')
        p=files[0];require(pins.get(str(p))==life.digest(p),'Native metric pin drift');paths.append(p)
        if metric!='tgl':require(bitmap.read_metric(p)==single['metrics'][metric],'Qualified/native bitmap differs')
    old=list((Path(reference)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(old)==1 and pins.get(str(old[0]))==life.digest(old[0]),'Unpinned baseline Toggle shape')
    require(toggle_shape(paths[-1])==toggle_shape(old[0]),'Toggle binary/array checksum or group shape differs')
    return dict(metrics=list((*bitmap.METRICS,'tgl')),native_test=NAME,
                compatible=True,toggle_interval_scoring='Native DVE full742 report; no custom array decoder gate')


def check():
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    def baseline(name):return life.read_bound(BASE/name,manifest['output_pins'][str(BASE/name)])
    before=baseline('combined-bits.json');state=baseline('status.json')
    require(state['aggregate_passed']==741 and state['coverage_admitted'] is True and
            state['status']=='PASS_RAW_UNION_HISTORICAL_ONLY','Formal741 required')
    inputs=(BASE/'combined-inputs.txt').read_text().splitlines();exact_prefix(before['tests'],inputs)
    q=life.read_bound(QUAL/'qualification.json',QUAL_SHA)
    def qualified(name):return life.read_bound(QUAL/name,q['output_pins'][str(QUAL/name)])
    audit=qualified('runtime-audit.json');oracle_contract(q,audit)
    pins=life.merge_pins(manifest['input_pins'],manifest['output_pins'])
    pins=life.merge_pins(pins,qualified('evidence-pins.json'));pins=life.merge_pins(pins,q['output_pins'])
    require(pins.get(str(ELF))==ELF_SHA and ELF_SHA not in manifest['input_pins'].values(),
            'ELF unbound or already admitted')
    pins=life.merge_pins(pins,before['input_hashes'])
    for relative,sha in before['design'].items():
        pins=life.merge_pins(pins,{str(DESIGN/'snps/coverage/db'/relative):sha})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_gap113_cached742.py'),
                 Path(bitmap.__file__).resolve(),Path(life.__file__).resolve()):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):QUAL_SHA})
    life.check(pins)
    single=qualified('single-bits.json')
    require(single['tests']==[str(VDB)] and all(pins.get(p)==h for p,h in single['input_hashes'].items()),
            'Wrong/unpinned qualified singleton')
    native=native_five(single,pins,before['tests'][0])
    combined=bitmap.combine(before,single)
    require(combined['tests']==before['tests']+[str(VDB)] and len(set(combined['tests']))==742,'Exact741 prefix lost')
    for metric,rows in before['metrics'].items():
        for scope,row in rows.items():
            require(int(combined['metrics'][metric][scope]['bits'],16)==
                    int(row['bits'],16)|int(single['metrics'][metric][scope]['bits'],16),'Singleton OR differs')
    change=bitmap.delta(before,combined)
    require(change==qualified('raw-delta.json'),'Qualified raw gain differs')
    gain=qualified('toggle-gain.json')
    require(gain['baseline_population']==741 and gain['total_new_serialized_toggle_positions']==12 and
            sum(map(len,gain['scopes'].values()))==12,'Qualified binary Toggle gain differs')
    require(sum(change['metrics'].values())>0 or gain['total_new_serialized_toggle_positions']>0,'No measured gain')
    life.check(pins)
    return dict(before=before,single=single,combined=combined,delta=change,toggle_gain=gain,
                native=native,pins=pins,inputs=inputs+[str(VDB)])


def admit(out,record):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh formal output required')
    out.mkdir()
    try:
        for name,value in [('single-bits.json',record['single']),('combined-bits.json',record['combined']),
                           ('raw-delta.json',record['delta']),('scoped-toggle-gain.json',record['toggle_gain']),
                           ('native-five-metrics.json',record['native'])]:life.save(out/name,value)
        (out/'single-inputs.txt').write_text(str(DESIGN)+'\n'+str(VDB)+'\n')
        (out/'combined-inputs.txt').write_text('\n'.join(record['inputs'])+'\n')
        status=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=742,baseline=741,new_passed=1,
                    exact741_prefix=True,unique_new_vdb=True,raw_delta=record['delta']['metrics'],
                    scoped_toggle_new_positions=12,native_metrics_complete=['line','cond','branch','fsm','tgl'],
                    coverage_admitted=True,historical_fixed_image_only=True,new_RTL_signoff=False,
                    whole_ISA_qualified=False,spike_custom_isa_pass=False,official_denominator_verified=False,
                    array_toggle_scoring='Native DVE raw742 report',simulations_started=False,rtl_changed=False)
        life.save(out/'status.json',status);life.check(record['pins'])
        life.save(out/'admission-manifest.json',dict(schema='GAP113_CACHED742_ADMISSION_V1',output=str(out),
            baseline=str(BASE),baseline_seal=BASE_SHA,qualification=str(QUAL/'qualification.json'),
            qualification_seal=QUAL_SHA,input_pins=record['pins'],
            output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()},
            authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL',explicit_parent_authorized=True))
        print(json.dumps(dict(status=status,seal=life.digest(out/'admission-manifest.json'))))
    except Exception as error:
        life.save(out/'failure.json',dict(status='ADMISSION_FAILED_NOT_APPROVED',reason=str(error)));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true')
    p.add_argument('--output',type=Path);p.add_argument('--parent-authorized',action='store_true');a=p.parse_args()
    require((a.check and not a.output and not a.parent_authorized) or
            (not a.check and a.output and a.parent_authorized),'Check only, or authorized fresh admission')
    record=check()
    if a.check:print(json.dumps(dict(status='CHECK_PASS_READY742_NOT_ADMITTED',native=record['native'],delta=record['delta']['metrics'])))
    else:admit(a.output.absolute(),record)
