"""One bounded phase12/0 experiment; frozen full8 lifecycle, no admission."""
import argparse
import json
from pathlib import Path
import sys
import run_gap113_payload_full8 as full8

reused, life = full8.reused, full8.life
PRE = life.OUT/'qbs-payload-phase-preflight763-agent-20261007-01'
SEAL = 'b0369662b82bc11a29f147416026112cd8718f232665fafb0a7dea2c206992c5'
NAME = 'qbs_payload_phase763'
ELF_SHA = '2644229f2706e98d9799a71c47f682c5989a4c43c176d8636b182eab64ab0c3e'


def validate(pre):
    reused.exact(pre, dict(status='FULL8_HOST_NATIVE_ELF_PREFLIGHT_NOT_DUT_PASS',
        case=NAME, binary=str(PRE/(NAME+'.elf')), binary_sha256=ELF_SHA,
        baseline=763, activation_skews=[12,0], m=8,n=8,k_blocks=1,
        host_checks=44,host_negative_tests=42,dut_checks=41,commands=2,budget_s=600,
        full_vrf_words=2048,initial_words=2048,source_guard_bytes=7328,csr_words=24,
        activation_distinct_bytes_per_context=2,activation_groups_per_command=128,
        spike='NOT_EXECUTED_CUSTOM_QBS_UNSUPPORTED',full_scalar_isa_verified=False,
        rtl_modified=False,vcs_launched=False,coverage_admitted=False), 'Phase preflight')
    if len(pre['sites'])!=2 or any(s['word']!=0x0eb5045b for s in pre['sites']):
        raise ValueError('Exact two M8 sites required')
    prediction=life.read_bound(PRE/'target-prediction.json',pre['prediction_sha256'])
    reused.exact(prediction,dict(baseline=763,physical_bits=144,raw_directions=288,
        official_percent_prediction=False,pending_hit_gain_claim=False),'Prediction')
    if len(prediction['targets'])!=144 or any(t['expected_hit_values']!=[0,1,0] for t in prediction['targets']):
        raise ValueError('Ordered exact prediction differs')


def prepare(output):
    output=Path(output).absolute()
    if output.parent!=life.OUT or output.resolve()!=output or output.exists():
        raise ValueError('Fresh independent output required')
    pre=life.read_bound(PRE/'preflight-manifest.json',SEAL);validate(pre)
    pins=life.merge_pins(pre['input_pins'],pre['output_pins'])
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    if plan['simv']!=str(life.IMAGE) or len(plan['image'])!=66 or plan['image'][str(life.IMAGE)]!=reused.IMAGE_SEAL:
        raise ValueError('Frozen simv66 differs')
    pins=life.merge_pins(pins,plan['image'])
    pins=life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL,str(PRE/'preflight-manifest.json'):SEAL})
    for name in ('run_qbs_payload_phase763.py','test_run_qbs_payload_phase763.py',
                 'qualify_qbs_payload_phase763.py','test_qualify_qbs_payload_phase763.py'):
        path=Path(__file__).with_name(name).resolve()
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    for path in (Path(full8.__file__),Path(reused.__file__),Path(life.__file__)):
        pins=life.merge_pins(pins,{str(path.resolve()):life.digest(path)})
    import qualify_qbs_payload_phase763 as qualifier
    if life.digest(Path(qualifier.full8.inherited.__file__))!='a721d950834d863b069c78ded382b3ae6e36a8e0841f201c850a6bd20699c691':
        raise ValueError('Frozen native checker drift')
    # Bind the actual imported comparison dependencies before simulation, not retrospectively.
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file:
            path=Path(file).resolve()
            if path.suffix=='.py' and str(path).startswith(str(life.ROOT/'verification')+'/'):
                pins=life.merge_pins(pins,{str(path):life.digest(path)})
    if life.digest(Path(life.__file__))!=reused.LIFE_SEAL:raise ValueError('Lifecycle drift')
    life.check(pins)
    reused.NAME=NAME;reused.ELF=PRE/(NAME+'.elf');reused.ELF_SEAL=ELF_SHA
    return output,dict(case=NAME,preflight=pre,pins=pins,command=reused.command(output),timeout_s=600,
        old_image_files_checked=66,coverage_admitted=False,automatic_retry=False,
        simulator_exit_is_not_functional_pass=True,
        qualification_required='Full native512 destination bytes/full8192 VRF snapshots/CSR/guards/lifecycle; no custom Spike full-state claim',
        budget_basis='Same two full8 K1 commands and complete snapshots as measured374.65s case; hard600s',
        predicted_new_physical_bits=144,predicted_new_raw_directions=288,
        warm_or_cold_cache_proven=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','run'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepared-seal');parser.add_argument('--qualification-output',type=Path);args=parser.parse_args()
    if (args.mode=='run')!=bool(args.prepared_seal):parser.error('Run needs prepared seal')
    if (args.mode=='run')!=bool(args.qualification_output):parser.error('Run needs independent qualification output')
    out,record=prepare(args.output);path=out.with_name(out.name+'.prepared.json')
    if args.mode=='prepare':
        if path.exists():raise ValueError('Preserve prepared record')
        life.save(path,record);print(json.dumps(dict(prepared=str(path),seal=life.digest(path),pins=len(record['pins']))))
    else:
        if life.read_bound(path,args.prepared_seal)!=record:raise ValueError('Prepared drift')
        reused.run(out,record)
        import qualify_qbs_payload_phase763 as qualifier
        print(json.dumps(qualifier.collect(out,args.prepared_seal,args.qualification_output)),flush=True)


if __name__=='__main__':main()
