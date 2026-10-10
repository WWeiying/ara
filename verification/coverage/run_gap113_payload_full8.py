"""Single 600s full8 run using the reviewed GAP110 lifecycle; no automatic launch."""
import argparse
import json
from pathlib import Path
import run_gap110_simulation as reused

life=reused.life
PRE=life.OUT/'gap113-payload-full8-preflight-741-agent-20261007-02'
SEAL='63d1e264ab68bf0658088354a9a83f0b80f886ecdc528e1f8323e5aa6a80ca52'
NAME='qbs_gap113_payload_full8'
ELF_SHA='d4ffd96711e2cc84819a84860231de8440c78a9a06b9275c7bf6dec3f52bcda3'


def validate(pre):
    reused.exact(pre,dict(status='FULL8_HOST_NATIVE_ELF_PREFLIGHT_NOT_DUT_PASS',
        binary=str(PRE/(NAME+'.elf')),binary_sha256=ELF_SHA,m=8,n=8,k_blocks=1,
        host_checks=44,host_negative_tests=42,dut_checks=41,commands=2,budget_s=600,
        full_vrf_words=2048,initial_words=2048,source_guard_bytes=7328,csr_words=24,
        weight_scale_encodings=64,weight_quant_encodings=8,weight_high_mask_byte_encodings=256,
        activation_distinct_bytes_per_context=256,activation_groups_per_command=128,
        spike='NOT_EXECUTED_CUSTOM_QBS_UNSUPPORTED',full_scalar_isa_verified=False,
        rtl_modified=False,vcs_launched=False,coverage_admitted=False),'Full8 preflight')
    if len(pre['sites'])!=2 or any(s['word']!=0x0eb5045b for s in pre['sites']):
        raise ValueError('Exact two M8 sites required')


def prepare(output):
    output=Path(output).absolute()
    if output.parent!=life.OUT or output.resolve()!=output or output.exists():
        raise ValueError('Fresh independent output required')
    pre=life.read_bound(PRE/'preflight-manifest.json',SEAL);validate(pre)
    pins=life.merge_pins(pre['input_pins'],pre['output_pins'])
    if pins.get(pre['binary'])!=ELF_SHA:raise ValueError('Pinned ELF differs')
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    if plan['simv']!=str(life.IMAGE) or len(plan['image'])!=66 or plan['image'][str(life.IMAGE)]!=reused.IMAGE_SEAL:
        raise ValueError('Frozen simv66 differs')
    pins=life.merge_pins(pins,plan['image'])
    pins=life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL,str(PRE/'preflight-manifest.json'):SEAL})
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_run_gap113_payload_full8.py'),
              Path(reused.__file__).resolve(),Path(life.__file__).resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    if life.digest(Path(life.__file__))!=reused.LIFE_SEAL:raise ValueError('Lifecycle drift')
    life.check(pins)
    reused.NAME=NAME;reused.ELF=Path(pre['binary']);reused.ELF_SEAL=ELF_SHA
    return output,dict(case=NAME,preflight=pre,pins=pins,command=reused.command(output),timeout_s=600,
        old_image_files_checked=66,coverage_admitted=False,automatic_retry=False,
        simulator_exit_is_not_functional_pass=True,
        budget_basis='GAP113 two commands same 7328 guarded source bytes/full VRF snapshots: actual CPU374.65s; '
                    'same K1 and native allocations, M8/N8 adds active outputs but not scalar full-readback volume.',
        qualification_required='Independent integer native gold, full VRF/CSR/source guards/lifecycle; '
                               'measured same-design raw Toggle OR against exact741, including interval arrays')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal');a=p.parse_args()
    if (a.mode=='run')!=bool(a.prepared_seal):p.error('Run requires parent-approved prepared seal')
    output,manifest=prepare(a.output);record=output.with_name(output.name+'.prepared.json')
    if a.mode=='prepare':
        if record.exists():raise ValueError('Preserve prepared record')
        life.save(record,manifest);print(json.dumps(dict(prepared=str(record),seal=life.digest(record),pins=len(manifest['pins']))))
    else:
        if life.read_bound(record,a.prepared_seal)!=manifest:raise ValueError('Prepared contract drift')
        reused.run(output,manifest)
