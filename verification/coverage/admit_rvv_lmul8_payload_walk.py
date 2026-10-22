"""Direct744 admission: reviewed strict proof plus two measured743-fresh Toggle positions."""
import argparse
import json
from pathlib import Path

import coverage_bitmap_delta as bitmap
import collect_rvv_lmul8_payload_walk as collector
import rvv_lmul8_payload_walk as r

life,require=r.life,r.require
BASE=life.OUT/'gap114-offline-admitted-743-agent-20261007-01'
BASE_SHA='385fdd6de589640f540d1d7679fa1004f285f8d377e5653df83b8feb28167848'
QUAL=life.OUT/'rvv-lmul8-payload-walk-qualified-742-agent-20261007-01/qualification.json'
QUAL_SHA='e5694aef6b990e7c941aae894ff2c14136835ea3d885317d425f864930ad1285'
TOGGLE=life.OUT/'rvv-lmul8-payload-walk-toggle742-fullserialized-delta-agent-20261007-01.json'
TOGGLE_SHA='9dc675fae05b044dcb7ecfcbc666ac349115c3e5c6d96f55636e899d264e5f01'
SCOPE='ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_scoreboard'
RUN=life.OUT/'rvv-lmul8-payload-walk-old-image-742-agent-20261007-01'
POSITIONS=[27864,27865]

def union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==743 and single['tests']==[str(RUN/'code.vdb')]
            and single['tests'][0] not in before['tests'],'Exact743 prefix and unique singleton required')
    for sample in (before,single):
        require(set(sample['metrics'])==set(bitmap.METRICS) and
                sum(len(rows) for rows in sample['metrics'].values())==6162,'Full6162 universe required')
        for rows in sample['metrics'].values():
            for value in rows.values():
                require(type(value['width']) is int and value['width']>=0 and
                    0<=int(value['bits'],16)<1<<value['width'],'Invalid raw vector')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    after=bitmap.combine(before,single)
    require(after['tests']==before['tests']+single['tests'],'Prefix lost')
    for metric,rows in before['metrics'].items():
        for scope,v in rows.items():
            require(int(after['metrics'][metric][scope]['bits'],16)==
                    int(v['bits'],16)|int(single['metrics'][metric][scope]['bits'],16),'Exact OR failure')
    return after

def evidence():
    q=life.read_bound(QUAL,QUAL_SHA);life.check(q['pins']);life.check(q['outputs'])
    require(q['status']=='STRICT_FUNCTIONAL_PASS_RAW_DIAGNOSTIC_NOT_ADMITTED' and q['baseline']==742
            and q['coverage_admitted'] is False,'Wrong terminal qualification')
    require(q['pins'][str(Path(collector.__file__).resolve())]==life.digest(Path(collector.__file__)),
            'Sealed collector source drift')
    def proof(name):return life.read_bound(QUAL.parent/(name+'.json'),q['outputs'][str(QUAL.parent/(name+'.json'))])
    scalar,vector,memory=proof('scalar'),proof('vector'),proof('footprint')
    require(scalar['status']=='TERMINAL_TOHOST_MATCH' and scalar['matched_instructions']==125541 and
        scalar['matched_scalar_writes']==75490 and scalar['matched_scalar_memory_accesses']==21354 and
        scalar['skipped_unobservable_register_values']==scalar['ara_trap_events']==0 and scalar['mismatch'] is None,
        'Full scalar proof mismatch')
    require(vector['status']=='PASS' and vector['compared_instructions']==24 and vector['compared_bytes']==15505 and
        vector['skipped_unknown_bytes']==vector['unobservable_instructions']==vector['non_bit_exact_instructions']==0 and
        not vector['incomplete_requests'] and not vector['unretired_requests'] and not vector['trapped_requests'] and
        vector['first_mismatch'] is None,'Full native vector proof mismatch')
    require(memory==dict(strict_snapshot_bytes=12800,csr_values=27,checks=7803,failed=0),'Footprint mismatch')
    require(proof('lifecycle')==dict(requests=71,responses=71,exceptions=0,backend=33),'Protocol mismatch')
    td=life.read_bound(TOGGLE,TOGGLE_SHA);life.check(td['pins'])
    require(td['baseline']==742 and td['fresh_serialized_directions']==2 and td['changed_scopes']==1 and
        td['changes']==[dict(scope=SCOPE,width=28718,checksum='264082867',fresh_positions=POSITIONS)],
        'Exact two measured Toggle positions required')
    a=life.read_bound(BASE/'admission-manifest.json',BASE_SHA);life.check(a['output_pins'])
    before=life.read_bound(BASE/'combined-bits.json',a['output_pins'][str(BASE/'combined-bits.json')])
    old=life.read_bound(r.BASE/'combined-bits.json',q['pins'][str(r.BASE/'combined-bits.json')])
    require(before['tests'][:742]==old['tests'] and len(before['tests'])==743,'Exact742/743 prefix mismatch')
    single=proof('singleton');after=union(before,single)
    f=list((Path(before['tests'][-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(f)==1,'Exact GAP114 Toggle test required')
    rows,sha=r.toggle.rows(f[0],[SCOPE]);v=rows[SCOPE]
    require((v['width'],v['checksum'])==(28718,'264082867'),'743 scoreboard shape drift')
    bits=bin(int(v['bits'],16))[2:].zfill(v['width'])
    require(all(bits[i]=='0' for i in POSITIONS),'Two positions not fresh against743')
    book=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    sources=json.loads(book.read_bytes());source=life.ROOT/'hardware/deps/cva6/core/scoreboard.sv'
    pins=life.merge_pins(q['pins'],q['outputs']);pins=life.merge_pins(pins,td['pins'])
    pins=life.merge_pins(pins,a['output_pins']);pins=life.merge_pins(pins,before['input_hashes'])
    pins=life.merge_pins(pins,{str(QUAL):QUAL_SHA,str(TOGGLE):TOGGLE_SHA,
        str(BASE/'admission-manifest.json'):BASE_SHA,str(f[0]):sha,str(book):life.digest(book),
        str(source):sources[str(source)]})
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_rvv_lmul8_payload_walk.py'),
              Path(bitmap.__file__),Path(collector.__file__),Path(collector.common.__file__)):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    return before,single,after,pins

def admit(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh744 output required; no overwrite')
    before,single,after,pins=evidence();delta=bitmap.delta(before,after)
    out.mkdir()
    for name,data in (('single-bits',single),('combined-bits',after),('raw-delta',delta)):
        life.save(out/(name+'.json'),data)
    design=str(life.IMAGE)+'.vdb'
    (out/'combined-inputs.txt').write_text('\n'.join([design]+after['tests'])+'\n')
    (out/'single-inputs.txt').write_text(design+'\n'+str(RUN/'code.vdb')+'\n')
    life.save(out/'status.json',dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=744,baseline=743,
        new_passed=1,exact743_prefix=True,exact742_prefix=True,unique_new_vdb=True,full_OR_instances=6162,
        raw_delta=delta['metrics'],measured_binary_toggle_new_positions=2,
        measured_toggle_scope=SCOPE,measured_toggle_positions=POSITIONS,operand_primary_gain=0,
        native_metrics_complete=['line','cond','branch','fsm','tgl'],coverage_admitted=True,
        historical_fixed_image_only=True,new_RTL_signoff=False,whole_ISA_qualified=False,
        official_denominator_verified=False,official_Toggle_percentage_claimed=False,
        array_intervaldata_not_decoded=True,simulations_started=False,rtl_changed=False))
    life.check(pins)
    manifest=dict(schema='RVV_LMUL8_WALK744_ADMISSION_V1',output=str(out),baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(QUAL),qualification_seal=QUAL_SHA,input_pins=pins,
        output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()},
        authorization_source='EXPLICIT_USER_PASS_PLUS_POSITIVE_GAIN_ADMISSION_AFTER_GAP114743',
        explicit_parent_authorized=True)
    life.save(out/'admission-manifest.json',manifest)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'admission-manifest.json'),population=744)))

def verify(out,seal):
    m=life.read_bound(out/'admission-manifest.json',seal);life.check(m['input_pins']);life.check(m['output_pins'])
    before,single,after,pins=evidence()
    require(m['input_pins']==pins and m['output']==str(out) and m['baseline_seal']==BASE_SHA,'Admission lineage mismatch')
    require(life.read_bound(out/'combined-bits.json',m['output_pins'][str(out/'combined-bits.json')])==after,
            'All6162 OR verification failure')
    require((out/'combined-inputs.txt').read_text().splitlines()==[str(life.IMAGE)+'.vdb']+after['tests'],
            'Exact744 ledger mismatch')
    print('VERIFY_PASS_EXACT744_743PREFIX_742PREFIX_6162OR_TWO_FRESH_TOGGLE_POSITIONS')

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=('admit','verify'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--manifest-seal')
    a=ap.parse_args();out=a.output.resolve()
    if a.mode=='admit':admit(out)
    else:verify(out,a.manifest_seal)
