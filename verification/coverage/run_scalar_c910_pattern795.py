"""One600s frozen-image run, prepared only until explicit parent authorization."""
import argparse
import json
from pathlib import Path
from types import FunctionType, ModuleType
import run_scalar_div_subnormal794 as old
import build_scalar_c910_pattern795 as oracle

life,require=old.life,old.require
exact_fields=old.exact_fields
PRE=life.OUT/'scalar-c910-pattern795-preflight-agent-20261008-02'
PRE_SHA='4594beb4e13a04c4a401bf2538c8fc7820069b209d47e7631aace5c13b804263'
ELF=PRE/'input.elf';IMAGE_SHA=old.IMAGE_SHA
NAME='scalar_c910_pattern795';BUDGET=600
SERVICE='ara-scalar-c910-pattern795-parent-20261008-01.service'
PROBE=Path(__file__).with_name('scalar_c910_pattern795_probe.tcl').resolve()


def source_contract():
    p=old.source_contract();names=old.reused.packed.unique(r'typedef\s+enum\s+logic\s*\[7:0\]\s*\{([^{}]*)\}\s*fu_op',
        old.reused.packed.clean((life.ROOT/'hardware/deps/cva6/core/include/ariane_pkg.sv').read_text()))
    p['ariane_ops']['FSQRT']=[n.strip() for n in names.split(',') if n.strip()].index('FSQRT')
    names=old.reused.packed.unique(r'typedef\s+enum\s+logic\s*\[OP_BITS-1:0\]\s*\{([^{}]*)\}\s*operation_e',
        old.reused.packed.clean((life.ROOT/'hardware/deps/fpnew/src/fpnew_pkg.sv').read_text()))
    p['fpnew_ops']['SQRT']=[n.strip() for n in names.split(',') if n.strip()].index('SQRT')
    wrap=old.reused.packed.clean((life.ROOT/'hardware/deps/cva6/core/fpu_wrap.sv').read_text())
    require('FSQRT:   fpu_op_d = fpnew_pkg::SQRT;' in wrap,'Frozen SQRT request mapping')
    p['request_counts']=dict(DIV=160,SQRT=64,FMV_X2F=448,FMV_F2X=224,total=896)
    return p


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+str(ELF),
        '+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(out/'commit_trace.csv'),
        '+VECTOR_TRACE='+str(out/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),
        '-cm_name',NAME,'+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000','-ucli','-do',str(PROBE)]


def manifest(out,service=SERVICE):
    out=Path(out).absolute();require(out.parent==life.OUT and out.resolve()==out,'Canonical output')
    require(old.reused.re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service',service) is not None,'Owning service')
    pre=life.read_bound(PRE/'preflight.json',PRE_SHA)
    old.exact_fields(pre,dict(status='SPIKE_SCALAR_C910_NORMAL224_INTEGER_GOLD_PASS_NOT_NATIVE',baseline=795,
        baseline_seal=oracle.BASE_SHA,cells=224,checks=675,DIV_cells=160,SQRT_cells=64,RTL_changed=False,EDA_started=False),'Frozen preflight')
    require(oracle.validate(oracle.build.parse_spike_commits(PRE/'spike.trace'),pre['symbols'])==pre['counts'],'Full reference replay')
    require(oracle.header()==(PRE/'pattern-gold.h').read_text() and oracle.cells()==json.loads((PRE/'gold.json').read_text()),'Exact integer gold header')
    evidence=oracle.source_evidence()
    require(evidence==life.read_bound(PRE/'source-targets.json',pre['pins'][str(PRE/'source-targets.json')]),'Exact source/target replay')
    proof=source_contract();plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(plan['image'])==66 and plan['image'][str(life.IMAGE)]==IMAGE_SHA,'Frozen66 image')
    pins=life.merge_pins(pre['pins'],proof['pins'])
    for more in (plan['image'],plan['design_files'],{str(life.PLAN):life.PLAN_SEAL,str(PRE/'preflight.json'):PRE_SHA}):pins=life.merge_pins(pins,more)
    import collect_scalar_c910_pattern795 as collector
    pending=[old,oracle,collector];seen=set();files=[PROBE,Path(__file__).resolve(),Path(__file__).with_name('test_run_collect_scalar_c910_pattern795.py'),old.reused.lifecycle.converter.CONVERTER]
    while pending:
        m=pending.pop();f=getattr(m,'__file__',None)
        if m in seen or not f or not str(f).startswith(str(life.ROOT/'verification')):continue
        seen.add(m);files.append(Path(f).resolve());pending.extend(v for v in vars(m).values() if isinstance(v,ModuleType))
    files+=list((life.ROOT/'verification/ara_verify').rglob('*.py'))
    base=life.read_bound(oracle.BASE/'admission-manifest.json',oracle.BASE_SHA)
    for name in ('combined-inputs.txt','combined-bits.json','combined-toggle-bits.json','status.json'):
        p=oracle.BASE/name;pins=life.merge_pins(pins,{str(p):base['output_pins'][str(p)]})
    require(life.digest(old.reused.lifecycle.converter.CONVERTER)==old.reused.lifecycle.converter.CONVERTER_SHA,'Frozen VPD converter')
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    return dict(case=NAME,output=str(out),command=command(out),pins=pins,timeout_s=BUDGET,input_elf=str(ELF),
        elf_sha256=pre['pins'][str(ELF)],image_sha256=IMAGE_SHA,preflight_seal=PRE_SHA,source_contract=proof,
        scalar_reference_counts=pre['counts'],expected_checks=675,raw_baseline_population=795,
        raw_baseline_seal=oracle.BASE_SHA,service=service,systemd_policy=dict(RuntimeMaxSec=660,TimeoutStopSec=10,KillMode='control-group'),
        automatic_retry=False,no_FSDB=True,focused_readonly_VPD=True,RTL_changed=False,coverage_admitted=False,
        terminal_oracle_verified=False,authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED_BEFORE_RUN')


def verify(out,record,terminal=False):
    require(terminal or not out.exists(),'Fresh output');require(record==manifest(out,record['service']),'Prepared exact pins/command')


def run(out,record):
    FunctionType(old.reused.run.__code__,dict(old.reused.run.__globals__,PRE=PRE,ELF=ELF,NAME=NAME,BUDGET=BUDGET,command=command))(out,record)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal');p.add_argument('--service',default=SERVICE)
    p.add_argument('--parent-authorized',action='store_true');a=p.parse_args();out=a.output.resolve();side=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':require(not out.exists() and not side.exists() and not a.parent_authorized,'Fresh preparation');life.save(side,manifest(out,a.service));print('PREPARED_NOT_RUN',life.digest(side))
    else:
        require(a.prepared_seal is not None,'Sealed preparation');record=life.read_bound(side,a.prepared_seal);verify(out,record)
        if a.mode=='verify':require(not a.parent_authorized,'No launch');print('PREPARED_VERIFY_PASS_NO_RUN')
        else:require(a.parent_authorized,'Explicit parent authorization');run(out,record)
