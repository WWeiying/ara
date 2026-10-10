"""Reuse sealed singleton: all-root four-metric OR and all-instance binary Toggle OR; no EDA."""
import argparse
import json
from pathlib import Path
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence_v2 as tgl
import admit_gap113_cached742 as native
import run_gap95_simulation as life

OUT=life.OUT
BASE=OUT/'gap113-full8-cached-offline-admitted-742-agent-20261007-01'
BASE_SHA='f07f7ccdcfc7257faad21aabdc45a48008658c70ee26abda275065f1e204a730'
QUAL=OUT/'gap113-cached-reset-qualified-742-agent-20261007-01'
QUAL_SHA='9302826b1f55ab3f55e63cc14b56eb694380817c121da37dc02582ce0c7d40ca'
RANK=OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
DESIGN=OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'


def all_delta(before,after):
    require=native.require;result={};instances=[]
    require(before['design']==after['design'],'Design drift')
    for metric,old in before['metrics'].items():
        new=after['metrics'][metric];require(set(old)==set(new),'Scope universe drift')
        total=0
        for scope,row in old.items():
            other=new[scope];require((row['width'],row['checksum'])==(other['width'],other['checksum']),'Shape drift')
            a,b=int(row['bits'],16),int(other['bits'],16)
            require(a&~b==0,'Hit lost');gain=b&~a
            if gain:
                positions=[i for i in range(row['width']) if gain>>(row['width']-1-i)&1]
                instances.append(dict(scope=scope,metric=metric,new_bits=len(positions),positions=positions,
                                      width=row['width'],checksum=row['checksum']))
                total+=len(positions)
        result[metric]=total
    return dict(scope='ALL_COMPILED_ROOTS_NO_PREFIX_FILTER',metrics=result,instances=instances,
                fsm_scopes_checked=len(before['metrics']['fsm']))


def collect(output):
    require=native.require;require(not output.exists(),'Fresh output required')
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    qual=life.read_bound(QUAL/'qualification.json',QUAL_SHA)
    require(qual['status']=='RESET_TWO_EPOCH_NATIVE_PASS_RAW742_DIAGNOSTIC_NOT_ADMITTED', 'Independent epoch qualification required')
    before=life.read_bound(BASE/'combined-bits.json',manifest['output_pins'][str(BASE/'combined-bits.json')])
    single=life.read_bound(QUAL/'single-bits.json',qual['output_pins'][str(QUAL/'single-bits.json')])
    require(len(before['tests'])==len(set(before['tests']))==742 and len(single['tests'])==1,'Exact742 + singleton required')
    inputs=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(inputs==[str(DESIGN)]+before['tests'] and single['tests'][0] not in before['tests'],'Prefix/unique candidate drift')
    pins=life.merge_pins(manifest['input_pins'],manifest['output_pins'])
    pins=life.merge_pins(pins,life.read_bound(QUAL/'evidence-pins.json',qual['output_pins'][str(QUAL/'evidence-pins.json')]))
    pins=life.merge_pins(pins,qual['output_pins'])
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):QUAL_SHA,
                             str(RANK):life.digest(RANK),str(Path(__file__).resolve()):life.digest(Path(__file__).resolve())})
    rank=json.loads(RANK.read_bytes());require(rank['tests']==741,'Not sealed741 Toggle union')
    pins=life.merge_pins(pins,rank['input_pins']);life.check(pins)
    merged=bitmap.combine(before,single);delta=all_delta(before,merged)
    # Reuse existing native shape validator, including every packed-array interval group.
    newdb=Path(single['tests'][0]);cached=Path(before['tests'][-1]);reference=Path(before['tests'][0])
    paths={}
    for metric in (*bitmap.METRICS,'tgl'):
        matches=list((newdb/'snps/coverage/db/testdata').glob('*/%s.verilog.data.xml'%metric))
        require(len(matches)==1 and pins.get(str(matches[0]))==life.digest(matches[0]),'Native input identity drift')
        paths[metric]=matches[0]
        if metric!='tgl':require(bitmap.read_metric(matches[0])==single['metrics'][metric],'Sealed/native singleton differs')
    ref=list((reference/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    cache=list((cached/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(ref)==len(cache)==1 and all(pins.get(str(p))==life.digest(p) for p in (ref[0],cache[0])), 'Baseline native pin drift')
    require(native.toggle_shape(paths['tgl'])==native.toggle_shape(ref[0])==native.toggle_shape(cache[0]),
            'Full native Toggle binary/array compatibility differs')
    scopes=list(rank['instances']);normal,_=tgl.rows(cache[0],scopes);sample,_=tgl.rows(paths['tgl'],scopes)
    raw741={s:{k:rank['instances'][s][k] for k in ('width','checksum','bits')} for s in scopes}
    toggle742=tgl.union(raw741,normal);toggle_candidate=tgl.union(toggle742,sample)
    gains=tgl.gains(toggle742,toggle_candidate)
    life.check(pins);output.mkdir()
    life.save(output/'combined-four-bits-diagnostic.json',merged)
    life.save(output/'combined-binary-toggle-diagnostic.json',dict(metrics=toggle_candidate,
        semantics='All instance_data direction positions only; interval arrays retained in native VDBs, not custom-decoded'))
    life.save(output/'all-root-raw-delta.json',delta)
    life.save(output/'all-instance-binary-toggle-gain.json',{s:p for s,p in gains.items() if p})
    (output/'five-metrics-native-inputs.txt').write_text('\n'.join(inputs+single['tests'])+'\n')
    life.save(output/'evidence-pins.json',pins)
    result=dict(status='FULL_DESIGN_FIVE_NATIVE_METRICS_COMPATIBLE_RAW742_DIAGNOSTIC_NOT_ADMITTED',
        baseline=742,diagnostic_candidate_population=743,exact742_prefix=True,unique_candidate=True,
        native_metrics=list((*bitmap.METRICS,'tgl')),raw_delta=delta['metrics'],
        all_fsm_scopes_checked=delta['fsm_scopes_checked'],
        fsm_gain_scopes=[i for i in delta['instances'] if i['metric']=='fsm'],
        binary_toggle_scopes_checked=len(gains),binary_toggle_new_positions=sum(map(len,gains.values())),
        interval_array_shape_compatible=True,interval_array_gain_custom_decoded=False,
        native_five_metric_input_union_available=True,official_toggle_percentage=None,
        previous_qualifier_delta_scope='ara_tb.dut.i_ara_soc.i_system (not global)',
        simulation_rerun=False,EDA_launched=False,coverage_admitted=False,
        output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()})
    life.save(output/'review.json',result)
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'review.json'),
                         raw=result['raw_delta'],binary_toggle=result['binary_toggle_new_positions'],
                         fsm_scopes=result['all_fsm_scopes_checked'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();collect(a.output.absolute())
