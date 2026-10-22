"""Prepare/check a single 180s cause-storage run; parent authorization required."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import build_csr_cause_wlrl788 as oracle
import run_csr_satp_sepc786 as prior

life, require, template, converter = prior.life, prior.require, prior.template, prior.converter
BASE, BASE_SHA = oracle.BASE, oracle.BASE_SHA
PRE = life.OUT / 'csr-cause-wlrl788-preflight-agent-20261008-02'
PRE_SEAL = '953943c09cbd5ff93fad321edc715c957b08b837de7e472deae12da9eed5d2cb'
ELF, ELF_SHA = PRE / 'input.elf', '381df713076070b35094afaa29eedfdfb0ffd1d94f3284931b06d8e8b5a7dca2'
NAME, BUDGET = 'csr_cause_wlrl788', 180
SERVICE = 'ara-csr-cause-wlrl788-parent-20261008-01.service'
PROBE, IMAGE_SHA, exact_fields = prior.PROBE, prior.IMAGE_SHA, prior.exact_fields
source_contract = prior.source_contract

def reference(pre):
    cs = list(oracle.shared.parse_spike_commits(PRE / 'spike.trace'))
    start = next(i for i,c in enumerate(cs) if c.pc == 0x80000000)
    end = next(i for i,c in enumerate(cs) if (pre['symbols']['tohost'],1) in c.memory_accesses)
    return cs[start:end+1]

def command(out):
    return FunctionType(prior.command.__code__, dict(prior.command.__globals__, ELF=ELF, NAME=NAME, PROBE=PROBE))(out)

def manifest(out, service=SERVICE):
    out = Path(out).absolute()
    require(out.parent == life.OUT and out.resolve() == out, 'Canonical direct run')
    import re
    require(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service', service) is not None, 'Exact service')
    pre = life.read_bound(PRE/'preflight-manifest.json', PRE_SEAL)
    exact_fields(pre, dict(status='CAUSE_WLRL788_PREFLIGHT_PASS_NOT_DUT', baseline=788,
                          baseline_seal=BASE_SHA, VCS_authorized=False, coverage_admitted=False, RTL_changed=False), 'Frozen cause preflight')
    require(pre['output_pins'][str(ELF)] == ELF_SHA, 'Exact ELF')
    ref = reference(pre); require(oracle.validate(ref, pre['symbols']) == pre['validation'], 'Full independent Spike replay')
    counts = template.reference_counts(ref,0x80000000,pre['symbols']['tohost'])
    exact_fields(counts,dict(matched_instructions=664,matched_scalar_writes=380,matched_scalar_memory_accesses=168), 'Exact terminal prefix')
    base = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    st = life.read_bound(BASE/'status.json',base['output_pins'][str(BASE/'status.json')])
    require(type(st['aggregate_passed']) is int and st['aggregate_passed'] == 788 and st['coverage_admitted'] is True, 'Formal788')
    ledger = BASE/'combined-inputs.txt'; require(life.digest(ledger)==base['output_pins'][str(ledger)],'Ledger SHA')
    members = ledger.read_text().splitlines(); require(len(members)==len(set(members))==789,'Exact788 membership')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['image'][str(life.IMAGE)]==IMAGE_SHA,'Fixed image66')
    proof, src = source_contract(); implpins={}; impl=oracle.source_contract(implpins)
    pins=life.merge_pins(pre['pins'],pre['output_pins'])
    for extra in (src,implpins,image['image'],image['design_files'],{str(PRE/'preflight-manifest.json'):PRE_SEAL,str(BASE/'admission-manifest.json'):BASE_SHA,str(life.PLAN):life.PLAN_SEAL}): pins=life.merge_pins(pins,extra)
    for n in ('status.json','combined-inputs.txt','combined-bits.json'): pins=life.merge_pins(pins,{str(BASE/n):base['output_pins'][str(BASE/n)]})
    import csr_satp_sepc_cycle_adapter as cycle
    pins=life.merge_pins(pins,cycle.source_contract()['pins'])
    files=[Path(__file__).resolve(),Path(__file__).with_name('test_run_csr_cause_wlrl788.py'),Path(__file__).with_name('collect_csr_cause_wlrl788.py'),Path(__file__).with_name('test_collect_csr_cause_wlrl788.py'),Path(prior.__file__),PROBE,Path(cycle.__file__),Path(cycle.packed.__file__),Path(cycle.original.__file__),Path(template.__file__),Path(template.frozen.__file__),Path(life.__file__),converter.CONVERTER]
    files+=list((life.ROOT/'verification/ara_verify').rglob('*.py'))
    require(life.digest(converter.CONVERTER)==converter.CONVERTER_SHA,'Converter SHA')
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    return dict(case=NAME,output=str(out),pins=pins,command=command(out),timeout_s=BUDGET,input_elf=str(ELF),input_spike_trace=str(PRE/'spike.trace'),elf_sha256=ELF_SHA,image_sha256=IMAGE_SHA,preflight_seal=PRE_SEAL,raw_baseline=str(BASE),raw_baseline_seal=BASE_SHA,raw_baseline_population=788,source_contract=proof,implementation_contract=impl,scalar_reference_counts=counts,expected_checks=44,expected_observed_bytes=336,old_image_files_checked=66,automatic_retry=False,no_FSDB=True,focused_readonly_VPD=True,systemd_policy=dict(RuntimeMaxSec=240,TimeoutStopSec=10,KillMode='control-group'),coverage_admitted=False,RTL_changed=False,terminal_oracle_verified=False,service=service,authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED_BEFORE_RUN')

def verify_prepared(out, record, terminal=False):
    require(terminal or not Path(out).exists(),'Fresh run output')
    require(record==manifest(out,record['service']),'Full prepared identity/source/command drift');return record

def lifecycle_namespace(out,record):
    return FunctionType(prior.lifecycle_namespace.__code__,dict(prior.lifecycle_namespace.__globals__,PRE=PRE,ELF_SHA=ELF_SHA,IMAGE_SHA=IMAGE_SHA,BUDGET=BUDGET,NAME=NAME,command=command))(out,record)

def run(out,record): lifecycle_namespace(out,record)['run'](out,record)

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','run'));p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal');p.add_argument('--service',default=SERVICE);p.add_argument('--parent-authorized',action='store_true');a=p.parse_args()
    require((a.mode!='prepare')==bool(a.prepared_seal),'Prepared seal required');require((a.mode=='run')==a.parent_authorized,'Explicit parent run approval')
    out=a.output.absolute();path=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not out.exists() and not path.exists(),'Fresh output/sidecar');life.save(path,manifest(out,a.service));print(json.dumps(dict(prepared=str(path),seal=life.digest(path),VCS_started=False)))
    else:
        record=life.read_bound(path,a.prepared_seal);verify_prepared(out,record)
        if a.mode=='run':run(out,record)
        else:print('CAUSE_WLRL788_PREPARED_VERIFY_PASS_NO_VCS')
if __name__=='__main__':main()
