"""One sealed reserved-NF case, frozen old image, explicit reviewed run only."""
import argparse
import json
from pathlib import Path

import build_gap104_preflight as proof
import run_gap95_simulation as life

PRE = life.OUT/'gap104-whole-nf-reserved-preflight-720-20261006-01'
PRE_SEAL = 'eb59bfec48f20d1a9176241277cc2f6b01b6e496fa479d7a73b3f0e8c3ff53ac'
ELF = PRE/'input.elf'
ELF_SEAL = 'dba8edfbde1aa504cee45134effe9d3b85888186cce243a59853d7d9a4ed3138'
LIFE_SEAL = '1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8'
IMAGE_SEAL = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
NAME = proof.NAME


def validate(pre):
    fixed = dict(status='GAP104_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS',case=NAME,baseline_tests=720,
        baseline_seal=proof.BASE_SEAL,checks=1309,opcodes=list(proof.WORDS),target_unhit_count=4,
        input_elf=str(ELF),input_spike_trace=str(PRE/'spike.trace'),coverage_admitted=False,
        rtl_changed=False,vcs_started=False,measured_raw_increment=None)
    if any(k not in pre or type(pre[k]) is not type(v) or pre[k]!=v for k,v in fixed.items()):
        raise ValueError('Exact GAP104 preflight differs')
    oracle = dict(status='GAP104_RESERVED_NF_SPIKE_PREFLIGHT_PASS_NOT_DUT',checks=1309,
        illegal_traps=2,phases=2,unchanged_vrf_bytes=8192,unchanged_target_guard_bytes=1024,
        recovery_guard_bytes=1024,coverage_admitted=False)
    if pre.get('validation')!=oracle or pre.get('pins',{}).get(str(ELF))!=ELF_SEAL:
        raise ValueError('Full oracle/ELF expected pin differs')
    if [pre['symbols'][key] for key in ('g104_bad_a','g104_bad_b','tohost')] != [2147492440,2147492460,0x80001000]:
        raise ValueError('Exact ELF trap/terminal PCs differ')
    for path in (PRE/'spike.trace',PRE/'compile-command.json',PRE/'spike-command.json',PRE/'host.log',
                 PRE/'host-reference',PRE/'target-before.json',PRE/'spike-validation.json',proof.APP,
                 Path(proof.__file__).resolve(),Path(proof.__file__).with_name('test_build_gap104_preflight.py'),
                 proof.ROOT/'verification/tests/gap104_reference.h',proof.ROOT/'verification/tests/gap104_host_reference.c'):
        if str(path) not in pre['pins']: raise ValueError('Unpinned preflight evidence: '+str(path))


def command(output):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'),'+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',NAME]


def prepare(output):
    output=Path(output).absolute()
    if output.parent!=life.OUT or output.resolve()!=output or output.exists():
        raise ValueError('Fresh independent runtime output required')
    helper=Path(life.__file__).resolve()
    if life.digest(helper)!=LIFE_SEAL: raise ValueError('Frozen lifecycle differs')
    pre=life.read_bound(PRE/'preflight-manifest.json',PRE_SEAL);validate(pre)
    evidence=life.read_bound(PRE/'target-before.json',pre['pins'][str(PRE/'target-before.json')])
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    if plan['simv']!=str(life.IMAGE) or len(plan['image'])!=66 or plan['image'].get(str(life.IMAGE))!=IMAGE_SEAL:
        raise ValueError('Exact frozen66-file image differs')
    pins=life.merge_pins(pre['pins'],plan['image'])
    pins=life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):PRE_SEAL,str(helper):LIFE_SEAL,
                             str(life.PLAN):life.PLAN_SEAL})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_run_gap104_simulation.py'),
                 Path(life.__file__).with_name('test_run_gap95_simulation.py')):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    if evidence!=proof.target_evidence(): raise ValueError('Fresh frozen720 source/shape targets differ')
    commits=proof.s.parse_spike_commits(PRE/'spike.trace')
    if proof.validate(commits,pre['symbols'],(PRE/'spike.trace').read_text())!=pre['validation']:
        raise ValueError('Independent raw Spike replay differs')
    if proof.elf_words(ELF,pre['symbols'])!=pre['opcodes']: raise ValueError('Actual ELF opcode differs')
    life.check(pins)
    return output,dict(case=NAME,preflight=pre,pins=pins,command=command(output),timeout_s=600,
        old_image_files_checked=66,baseline_tests=720,baseline_is_static_target_analysis_only=True,
        coverage_delta_requires_latest_formal_baseline=True,input_elf=str(ELF),
        input_spike_trace=str(PRE/'spike.trace'),expected_checks=1309,expected_illegal_traps=2,
        expected_bad_opcodes=list(proof.WORDS),expected_bad_pcs=[pre['symbols'][k] for k in ('g104_bad_a','g104_bad_b')],
        expected_full_vrf_snapshot_bytes=8192,expected_unchanged_target_guard_bytes=1024,
        expected_recovery_guard_bytes=1024,predicted_target_raw_branch=[390,336],
        predicted_target_raw_line=[1263,1346],target_hit_verified=False,dut_self_check_verified=False,
        coverage_admitted=False,admission_performed=False,rtl_changed=False,new_RTL_signoff=False,automatic_retry=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','run'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepared-seal');args=parser.parse_args(argv)
    if (args.mode=='run')!=bool(args.prepared_seal): parser.error('Explicit run alone requires external seal')
    output,manifest=prepare(args.output);record=output.with_name(output.name+'.prepared.json')
    if args.mode=='prepare':
        if record.exists(): raise ValueError('Fresh prepared record required')
        life.save(record,manifest)
        print(json.dumps(dict(status='GAP104_RUN_PREPARED_NO_VCS',prepared=str(record),
                              seal=life.digest(record),pins_checked=len(manifest['pins']))))
    else:
        if life.read_bound(record,args.prepared_seal)!=manifest: raise ValueError('Reviewed prepared contract differs')
        life.run(output,manifest)


if __name__=='__main__':main()
