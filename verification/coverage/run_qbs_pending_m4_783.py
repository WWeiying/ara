"""Two legal M4 ROW commands: full783 ELF dedup, frozen image66,600s, no automatic launch."""
import argparse
import inspect
import json
from pathlib import Path
import sys
from types import FunctionType

import run_qbs_k2_row_pending782 as old
import admit_qbs_k2_pending783 as admission

life=old.life
PRE=life.OUT/'qbs-pending-two-phase-m4-preflight783-agent-20261008-02'
SEAL='fec5c09a699bddfbea0a34341433e637f8d80904016cf1418330c2c43dc7fdba'
NAME='qbs_pending_two_phase_m4_783'
ELF=PRE/(NAME+'.elf')
ELF_SHA='a133fe7257b749f5ea34ff3154800cb45825fc5db11e0ea43a208c8326d7819b'
BASE=life.OUT/'qbs-k2-pending-offline-admitted783-agent-20261008-01'
BASE_SHA='8d0d58bf873e0b0f4c601d1e9fb88fca74babb572f822a0580967eef9e5d23f0'
PROBE=Path(__file__).with_name('qbs_pending_two_phase783_probe.tcl').resolve()
CORRECTION=life.OUT/'qbs-pending-two-phase-m4-static-correction783-agent-20261008-01.json'
CORRECTION_SHA='3001c1ee2c6a5e1dfbfe042a30a7b708d0ecefa6c888ffa641f5d8d58b00b4c0'
OLD_SHA='8556874f422accf02a3b67befb7b8f97824187cdd3db8f796917a7b965ca91f2'
CONVERTER=old.CONVERTER


def validate(pre):
    old.old.exact(pre,dict(status='LEGAL_TWO_PHASE_M4_HOST_INTEGER_GOLD_READY_NOT_DUT_PASS',
        binary=str(ELF),binary_sha256=ELF_SHA,commands=2,host_checks=14,dut_checks=12,
        host_negative_tests=19,n=8,k_blocks=2,weight_layout='ROW',activation_layout='ROW',
        activation_profile='Q8_K',full_vrf_checkpoint_bytes=[4096,4096],csr_values_per_checkpoint=12,
        all_source_container_bytes_per_checkpoint=12416,budget_s=600,custom_spike_pass=False,
        full_scalar_ISA_verified=False,vcs_launched=False,coverage_admitted=False,RTL_changed=False),'Legal M4 fixture')
    admission.require(pre['phases']==[
        dict(profile='Q2_K',m=4,wp=10,ap=0,weight_block_bytes=84,active_outputs=32),
        dict(profile='Q6_K',m=4,wp=10,ap=12,weight_block_bytes=210,active_outputs=32)] and
        len(pre['sites'])==2 and len({s['pc'] for s in pre['sites']})==2 and
        all(s['word']==0x06b5045b for s in pre['sites']),'Two exact legal sites')


def command(output):
    return FunctionType(old.command.__code__,dict(vars(old),NAME=NAME,ELF=ELF,PROBE=PROBE))(output)


def reject_duplicate(members,sha):
    admission.require(all(m['ELF_candidates'] and sha not in m['ELF_candidates'].values()
        for m in members),'Candidate ELF duplicates historical member')


def history():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    admission.require(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal783 authority')
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    ledger_path=BASE/'combined-inputs.txt'
    life.check({str(ledger_path):base['output_pins'][str(ledger_path)]})
    ledger=ledger_path.read_text().splitlines()
    admission.require(len(ledger)==len(set(ledger))==784 and ledger[0]==str(life.IMAGE)+'.vdb','Exact compile+783 ledger')
    audit_path=BASE/'elf-ledger-dedup.json'
    prior=life.read_bound(audit_path,base['output_pins'][str(audit_path)])
    admission.require(prior['ledger_members']==782 and len(prior['members'])==782 and
        [m['vdb'] for m in prior['members']]==ledger[1:783] and
        all(authority.get(p)==h for p,h in prior['pins'].items()),'Historical782 admitted pin ownership')
    reject_duplicate(prior['members'],ELF_SHA)
    namespace=admission.inherited(admission.DEDUP,admission.DEDUP_SHA,('elf_references','dedup'))
    suffix=namespace['dedup']([ledger[0],ledger[-1]],ELF_SHA,authority)
    admission.require(suffix['ledger_members']==1 and suffix['duplicate'] is False and
        [m['vdb'] for m in suffix['members']]==ledger[-1:] and
        all(authority.get(p)==h for p,h in suffix['pins'].items()),'783 suffix uses admitted authority only')
    members=prior['members']+suffix['members'];reject_duplicate(members,ELF_SHA)
    pins=life.merge_pins(prior['pins'],suffix['pins'])
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,
        str(ledger_path):base['output_pins'][str(ledger_path)],str(audit_path):base['output_pins'][str(audit_path)],
        str(admission.DEDUP.resolve()):admission.DEDUP_SHA})
    life.check(pins)
    return dict(status='ALL783_ADMITTED_ELF_MEMBERS_CHECKED_NO_DUPLICATE',members=members,
        candidate_ELF=str(ELF),candidate_sha256=ELF_SHA,ledger_members=783,
        exact783_prefix=True,duplicate=False,candidate_qualification_not_used_as_history=True,pins=pins)


def prepare(output):
    output=Path(output).absolute()
    admission.require(life.digest(Path(old.__file__))==OLD_SHA,'Frozen original runner')
    # Reuse the sealed runner's image66/source-observer/lifecycle pin checks.
    source=inspect.getsource(old.prepare)
    old_predicate="if len(bits['tests'])!=782 or len(set(bits['tests']))!=782:"
    admission.require(source.count(old_predicate)==1,'Exact population adaptation')
    source=source.replace(old_predicate,"if len(bits['tests'])!=783 or len(set(bits['tests']))!=783:")
    namespace=dict(vars(old),__file__=__file__,PRE=PRE,SEAL=SEAL,NAME=NAME,ELF=ELF,ELF_SHA=ELF_SHA,
        BASE=BASE,BASE_SHA=BASE_SHA,PROBE=PROBE,CONVERTER=CONVERTER,validate=validate,command=command)
    # Name only affects which new test is pinned; the inherited test remains pinned separately.
    admission.require(source.count('test_qbs_k2_row_pending782_runtime.py')==1,'Exact test dependency adaptation')
    source=source.replace('test_qbs_k2_row_pending782_runtime.py','test_run_qbs_pending_m4_783.py')
    exec(compile(source,'<sealed-runner-legal-M4-783-population>','exec'),namespace)
    output,record=namespace['prepare'](output)
    correction=life.read_bound(CORRECTION,CORRECTION_SHA)
    admission.require(correction['preflight_seal']==SEAL and correction['original4120_legal_bound_retracted'] is True,
        'Mandatory source witness correction')
    audit=history();record['historical_ELF_dedup']=audit
    fixed={str(Path(__file__).resolve()):life.digest(Path(__file__)),str(Path(old.__file__).resolve()):OLD_SHA,
        str(CORRECTION):CORRECTION_SHA,str(Path(admission.__file__).resolve()):life.digest(Path(admission.__file__))}
    record['pins']=life.merge_pins(record['pins'],life.merge_pins(audit['pins'],fixed))
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    record.update(image_source_proof=dict(image=str(life.IMAGE),sha256=old.old.IMAGE_SEAL,
        exact_image_files=66,build_source_book_sha256=admission.analysis.case.native.BUILD_SHA,
        QBS_source_hashes={p:h for p,h in record['pins'].items() if '/hardware/src/vlsu/qbs/' in p or p.endswith('/hardware/include/qbs_pkg.sv')},
        frozen_dispatcher_snapshot=str(life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'),
        live_modified_RTL_not_compiled=True),
        expected_commands=2,expected_backend_vl=[128,128],expected_software_vl=[8,8],
        expected_custom_bytes=[512,512],expected_active_bytes=[128,128],
        expected_full_VRF_bytes=[4096,4096],expected_CSR_count=[12,12],
        scalar_Spike_preflight_executed=False,custom_Spike_supported=False,full_scalar_ISA_verified=False,
        qualification_required='Two exact native command lifecycles, all18 vector activities, integer gold, both fullVRF/CSR/source checkpoints; independent fullVCD pending overwrite review and latest rawOR. Not exit0-only; not fullscalarISA.',
        collector_ready=False,EDA_launch_authorized=False)
    admission.require(plan['image'][str(life.IMAGE)]==record['image_source_proof']['sha256'],'Exact image identity')
    life.check(record['pins'])
    return output,record


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal');args=p.parse_args()
    admission.require((args.mode=='verify')==bool(args.prepared_seal),'Verify alone requires seal')
    out,record=prepare(args.output);path=out.with_name(out.name+'.prepared.json')
    if args.mode=='prepare':
        life.save(path,record);print(json.dumps(dict(prepared=str(path),seal=life.digest(path),members=783,pins=len(record['pins']))))
    else:
        admission.require(life.read_bound(path,args.prepared_seal)==record,'Prepared drift');print('VERIFY_PASS_NO_EDA')


if __name__=='__main__':main()
