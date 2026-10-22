"""Thin positive runner: frozen image66, reviewed fixture, focused VPD, one600s run."""
import argparse
import json
from pathlib import Path
import sys
from types import FunctionType

import run_gap110_simulation as old

life=old.life
PRE=life.OUT/'qbs-k2-row-pending-preflight781-agent-20261008-01'
SEAL='58f652b1600bb7e6bb72819aba94d9d5a12b2b072fc8d453f742bb995b3594a1'
NAME='qbs_k2_row_pending781'
ELF=PRE/(NAME+'.elf')
ELF_SHA='318c69139db124d61a168ec2bf666c11dff295c0853a09ec9cc0819938c80789'
BASE=life.OUT/'dtlb-permissions-offline-admitted782-agent-20261008-01'
BASE_SHA='a52004d8882b5101d823d6dd647b7fb20c7c25a544abc96d15cb6f85d36d50b8'
PROBE=Path(__file__).with_name('qbs_k2_row_pending781_probe.tcl').resolve()
OLD_SHA='4c49a8ce42e66864b3c31ea7c9ff417fb269969396502145f621b47653549ef3'
CONVERTER=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')


def validate(pre):
    old.exact(pre,dict(status='HOST_NATIVE_QBS_GOLD_ELF_READY_NOT_DUT_PASS',binary=str(ELF),
        binary_sha256=ELF_SHA,m=4,n=8,k_blocks=2,weight_profile=7,activation_profile=1,
        weight_layout=1,activation_layout=1,wp=10,ap=0,commands=1,host_checks=7,dut_checks=6,
        host_negative_tests=9,full_vrf_bytes=4096,csr_values=12,source_readback_bytes=4032,
        active_outputs=32,legacy_m4_zero_tail_bytes=384,budget_s=600,custom_spike_pass=False,
        full_scalar_ISA_verified=False,vcs_launched=False,coverage_admitted=False,rtl_changed=False),'Fixture')
    if len(pre['sites'])!=1 or pre['sites'][0]['word']!=0x06b5045b:
        raise ValueError('Exact one M4 site')


def command(output):
    ns=dict(vars(old),NAME=NAME,ELF=ELF)
    return FunctionType(old.command.__code__,ns)(output)+['-ucli','-do',str(PROBE)]


def prepare(output):
    output=Path(output).absolute()
    if output.parent!=life.OUT or output.resolve()!=output or output.exists():raise ValueError('Fresh output')
    if life.digest(Path(old.__file__))!=OLD_SHA or life.digest(Path(life.__file__))!=old.LIFE_SEAL:
        raise ValueError('Frozen lifecycle changed')
    pre=life.read_bound(PRE/'preflight-manifest.json',SEAL);validate(pre)
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    if base['coverage_admitted'] is not True:raise ValueError('Unadmitted782')
    bits_path=BASE/'combined-bits.json'
    bits=life.read_bound(bits_path,base['output_pins'][str(bits_path)])
    if len(bits['tests'])!=782 or len(set(bits['tests']))!=782:raise ValueError('Exact782 membership')
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    if len(plan['image'])!=66 or plan['simv']!=str(life.IMAGE) or plan['image'].get(str(life.IMAGE))!=old.IMAGE_SEAL:
        raise ValueError('Frozen image66')
    import collect_qbs_k2_row_pending782
    pins=life.merge_pins(pre['input_pins'],pre['output_pins'])
    pins=life.merge_pins(pins,plan['image'])
    pins=life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):SEAL,str(BASE/'admission-manifest.json'):BASE_SHA,
        str(bits_path):base['output_pins'][str(bits_path)],str(life.PLAN):life.PLAN_SEAL,
        str(PROBE):life.digest(PROBE),str(CONVERTER):life.digest(CONVERTER),str(Path(sys.executable).resolve()):life.digest(Path(sys.executable).resolve())})
    for module in list(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name:
            path=Path(name).resolve()
            if path.suffix=='.py' and str(path).startswith(str(life.ROOT/'verification')+'/'):
                pins=life.merge_pins(pins,{str(path):life.digest(path)})
    test=Path(__file__).with_name('test_qbs_k2_row_pending782_runtime.py').resolve()
    pins=life.merge_pins(pins,{str(test):life.digest(test)})
    pins=life.merge_pins(pins,collect_qbs_k2_row_pending782.observer_pins())
    life.check(pins)
    return output,dict(case=NAME,command=command(output),timeout_s=600,preflight=pre,pins=pins,
        baseline=str(BASE),baseline_seal=BASE_SHA,old_image_files_checked=66,
        wave_byte_limit=64*1024*1024,automatic_retry=False,coverage_admitted=False,
        qualification_required='Native integer Q2 gold/full VRF/CSR/source guards/lifecycle and focused pending witness; no custom Spike/full scalar ISA')


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal');a=p.parse_args()
    if (a.mode!='prepare')!=bool(a.prepared_seal):p.error('Verify/run requires prepared seal')
    output,record=prepare(a.output);path=output.with_name(output.name+'.prepared.json')
    if a.mode=='prepare':
        if path.exists():raise ValueError('Preserve preparation')
        life.save(path,record);print(json.dumps(dict(prepared=str(path),seal=life.digest(path),pins=len(record['pins']))),flush=True)
    else:
        if life.read_bound(path,a.prepared_seal)!=record:raise ValueError('Prepared drift')
        if a.mode=='verify':print('VERIFY_PASS');return
        ns=dict(vars(old),NAME=NAME,ELF=ELF,ELF_SEAL=ELF_SHA,command=command)
        FunctionType(old.run.__code__,ns)(output,record)


if __name__=='__main__':main()
