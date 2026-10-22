"""Thin GAP110 foreground lifecycle adapter. Prepare only until parent authorization."""
import argparse
import json
from pathlib import Path
import run_gap110_simulation as reused

life=reused.life
PRE=life.OUT/'gap113-payload-toggle-preflight-740-agent-20261007-01'
SEAL='a696ae21d758bdf55bd36a3c5a8cc1b5108235249668fe0ef18da9bc447a2790'
NAME='qbs_gap113_payload_toggle'
ELF_SHA='b83831455d658d62182bca6dd1dee02096313b8d1cdff45cb4ef30a5873e5bd1'


def validate(pre):
    reused.exact(pre,dict(status='GAP113_HOST_NATIVE_ELF_PREPARED_NOT_DUT_PASS',
        binary=str(PRE/(NAME+'.elf')),binary_sha256=ELF_SHA,host_checks=44,host_negative_tests=42,
        dut_checks=41,commands=2,budget_s=600,vrf_words=2048,source_bytes=7328,csr_words=24,
        spike='NOT_EXECUTED_CUSTOM_QBS_UNSUPPORTED',full_scalar_isa_verified=False,
        measured_gain=None,rtl_modified=False,vcs_launched=False,coverage_admitted=False),'GAP113 preflight')
    if len(pre['target']['serialized_zero_coordinates'])!=83:raise ValueError('Exact83 target coordinates')


def prepare(output):
    output=Path(output).absolute()
    if output.parent!=life.OUT or output.resolve()!=output or output.exists():raise ValueError('Fresh output required')
    pre=life.read_bound(PRE/'preflight-manifest.json',SEAL);validate(pre)
    pins=life.merge_pins(pre['input_pins'],pre['output_pins'])
    artifacts=life.read_bound(PRE/'artifact-hashes.json',pins[str(PRE/'artifact-hashes.json')])
    pins=life.merge_pins(pins,artifacts)
    if pins.get(pre['binary'])!=ELF_SHA:raise ValueError('Pinned ELF differs')
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    if plan['simv']!=str(life.IMAGE) or len(plan['image'])!=66 or plan['image'][str(life.IMAGE)]!=reused.IMAGE_SEAL:
        raise ValueError('Exact frozen simv66 required')
    pins=life.merge_pins(pins,plan['image'])
    pins=life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL,str(PRE/'preflight-manifest.json'):SEAL})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_run_gap113_payload_toggle.py'),
                 Path(reused.__file__).resolve(),Path(life.__file__).resolve()):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    if life.digest(Path(life.__file__))!=reused.LIFE_SEAL:raise ValueError('Frozen lifecycle drift')
    life.check(pins)
    reused.NAME=NAME;reused.ELF=Path(pre['binary']);reused.ELF_SEAL=ELF_SHA
    return output,dict(case=NAME,preflight=pre,pins=pins,command=reused.command(output),timeout_s=600,
        old_image_files_checked=66,coverage_admitted=False,automatic_retry=False,
        simulator_exit_is_not_functional_pass=True,qualification_required='Full native/scalar/vector/guards and exact raw Toggle gain')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal');a=p.parse_args()
    if (a.mode=='run')!=bool(a.prepared_seal):p.error('Only explicit run requires externally approved prepared seal')
    output,manifest=prepare(a.output);record=output.with_name(output.name+'.prepared.json')
    if a.mode=='prepare':
        if record.exists():raise ValueError('Preserve existing prepared record')
        life.save(record,manifest);print(json.dumps(dict(prepared=str(record),seal=life.digest(record),pins=len(manifest['pins']))))
    else:
        if life.read_bound(record,a.prepared_seal)!=manifest:raise ValueError('Prepared contract drift')
        reused.run(output,manifest)
