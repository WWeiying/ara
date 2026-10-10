"""One separately authorized300s frozen-image run; no EDA during prepare/verify."""
import argparse
import json
from pathlib import Path
from types import FunctionType, ModuleType, SimpleNamespace

import preflight_vsmul_saturation796 as p
import run_pure_war_simulation as worker
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence_v2 as toggle

life, require = p.life, p.require
NAME = 'vsmul_saturation796'
PRE = p.DEFAULT_OUT/'preflight.json'
PRE_SHA = 'f8661178864094e49c6d5d83a45f11e1361fb524d0ec01d7ef628cdff115b3da'
ELF = PRE.parent/'input.elf'
ELF_SHA = 'b55eb5bc77e56804072081b710991e9ef9134d17134c38b9555c4d43bfe98ee6'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
COMPILE = life.OUT/'repaired-aligned-build-20260930-01/compile.command.json'
COMPILE_SHA = '30cdd93809c183f5004767d6190ca33d1d78aed68e73dcf42d6fef793269cbb1'
BASE, BASE_SHA = p.BASE, p.BASE_SHA
BUDGET = 300


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]


def preflight():
    pre=life.read_bound(PRE,PRE_SHA);life.check(pre['input_pins'])
    require(pre['status']=='VSMUL_SATURATION796_HOST_SPIKE_PASS_NOT_DUT' and
        pre['ELF']==str(ELF) and life.digest(ELF)==ELF_SHA and pre['baseline']==796 and
        pre['target_raw_zero_slots']==114 and pre['coverage_admitted'] is False and pre['VCS_started'] is False,
        'Exact frozen software preflight')
    counts=pre['counts']
    require({k:counts[k] for k in ('checks','target_operations','vector_writers','full_defined_snapshot_bytes','source_guard_bytes','exact_CSRs')}
        ==dict(checks=1272,target_operations=12,vector_writers=48,full_defined_snapshot_bytes=4608,source_guard_bytes=3840,exact_CSRs=72)
        and counts['runtime']['entry_to_tohost_instructions']==18927 and counts['runtime']['stack_top']==0x80040000
        and counts['runtime']['all_runtime_memory_widths_decoded'] is True,'Complete software oracle/reference')
    require('sim_l2_mb=2' in life.read_bound(COMPILE,COMPILE_SHA)['command'],'Exact2MiB image compile')
    return pre


def baseline():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True,'Formal796 admitted authority')
    path=BASE/'combined-inputs.txt';require(life.digest(path)==base['output_pins'][str(path)],'Exact796 ledger SHA')
    ledger=path.read_text().splitlines()
    before=life.read_bound(BASE/'combined-bits.json',base['output_pins'][str(BASE/'combined-bits.json')])
    tgl=life.read_bound(BASE/'combined-toggle-bits.json',base['output_pins'][str(BASE/'combined-toggle-bits.json')])
    require(len(ledger)==len(set(ledger))==797 and before['tests']==ledger[1:] and len(tgl)==2989,'Exact796 prefix/Toggle universe')
    require({m:len(rows) for m,rows in before['metrics'].items()}==dict(line=1892,cond=2023,branch=2155,fsm=92),'Full6162 instance universe')
    return base,before,tgl,ledger


def direct_source_pins():
    bookpath=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book=life.read_bound(bookpath,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    pins={str(life.ROOT/rel):book[str(life.ROOT/rel)] for rel in
          ('hardware/src/lane/simd_mul.sv','hardware/include/ara_pkg.sv','hardware/src/ara_sequencer.sv')}
    snapshot=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pins[str(snapshot)]=book[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]
    life.check(pins)
    require('ara_req.vtype.vsew = EW8;' in snapshot.read_text() and
            'ara_req.vl = VLENB << 0;' in snapshot.read_text(),'Whole-store byte-stream source contract')
    return pins


def prepare(out,existing=False):
    import collect_vsmul_saturation796 as collector
    require(out.parent==life.OUT and out.resolve()==out and (out.is_dir() if existing else not out.exists()),'Fresh run or explicit terminal existing directory')
    pre=preflight();base,before,tgl,ledger=baseline()
    static=life.read_bound(PRE.parent/'source-targets.json',pre['input_pins'][str(PRE.parent/'source-targets.json')])
    require(p.source_evidence()==static,'Fresh796 source/typed zero/EL ownership replay')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['image'][str(life.IMAGE)]==IMAGE_SHA,'Frozen runtime66')
    pins=life.merge_pins(life.merge_pins(pre['input_pins'],image['image']),direct_source_pins())
    fixed={str(PRE):PRE_SHA,str(COMPILE):COMPILE_SHA,str(life.PLAN):life.PLAN_SEAL,str(BASE/'admission-manifest.json'):BASE_SHA}
    for name in ('combined-inputs.txt','combined-bits.json','combined-toggle-bits.json'):
        path=BASE/name;fixed[str(path)]=base['output_pins'][str(path)]
    for name,h in before['design'].items():
        path=Path(ledger[0])/'snps/coverage/db'/name
        require(base['input_pins'][str(path)]==h,'Bound compiled design membership');fixed[str(path)]=h
    modules,seen=[p,worker,bitmap,toggle,collector],set()
    while modules:
        module=modules.pop()
        if id(module) in seen:continue
        seen.add(id(module));file=getattr(module,'__file__',None)
        if file:
            path=Path(file).resolve()
            if path.suffix=='.py' and life.ROOT/'verification' in path.parents:
                fixed[str(path)]=life.digest(path)
                modules.extend(v for v in vars(module).values() if isinstance(v,ModuleType))
    for name in ('run_vsmul_saturation796.py','collect_vsmul_saturation796.py','test_vsmul_saturation796_run_collect.py'):
        path=Path(__file__).with_name(name).resolve();fixed[str(path)]=life.digest(path)
    pins=life.merge_pins(pins,fixed);life.check(pins)
    return dict(schema='VSMUL_SATURATION796_RUN_V1',case=NAME,output=str(out),command=command(out),pins=pins,
        preflight=str(PRE),preflight_seal=PRE_SHA,image_sha256=IMAGE_SHA,elf_sha256=ELF_SHA,
        baseline=796,baseline_seal=BASE_SHA,targets=static['targets'],timeout_s=BUDGET,
        scalar_reference_instructions=18927,expected_missing_coordinates=114,old_image_files_checked=66,
        foreground_lifetime=True,authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        systemd_policy=dict(RuntimeMaxSec=360,TimeoutStopSec=10,KillMode='control-group'),
        budget_basis='18927 terminal-prefix instructions; ~95s at measuredVALU200inst/s; initial300s including startup/reshuffles, no retry',
        automatic_retry=False,no_FSDB=True,raw_commit=True,raw_vector=True,coverage_admitted=False,
        admission_performed=False,RTL_modified=False,qualification_required='Full scalar/memory/CSR,48 architectural writers+all identity transport,36 snapshots,2989Toggle/6162metric OR')


def invoke_run(out,manifest):
    ns=dict(worker.run.__globals__,BUDGET=BUDGET,PRE=ELF.parent,ELF_SEAL=ELF_SHA,
        IMAGE_SEAL=IMAGE_SHA,preflight=SimpleNamespace(NAME=NAME),command=command)
    FunctionType(worker.run.__code__,ns,argdefs=worker.run.__defaults__)(out,
        dict(manifest,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','verify','run'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal');parser.add_argument('--parent-authorized',action='store_true')
    args=parser.parse_args();require((args.mode!='prepare')==bool(args.seal),'Verify/run need prepared SHA')
    require((args.mode=='run')==args.parent_authorized,'Explicit parent authorization only')
    out=args.output.resolve();record=out.with_name(out.name+'.prepared.json');manifest=prepare(out)
    if args.mode=='prepare':
        life.save(record,manifest);print('PREPARED_NO_VCS',life.digest(record),len(manifest['pins']),flush=True)
    else:
        require(life.read_bound(record,args.seal)==manifest,'Prepared contract/pins drift')
        if args.mode=='verify':print('VERIFY_PASS_NO_VCS',flush=True)
        else:invoke_run(out,manifest)
