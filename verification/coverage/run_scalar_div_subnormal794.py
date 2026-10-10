"""Frozen software reference, one600s run only after separate parent authorization."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import run_scalar_fpu_fma_arbiter792 as reused
import build_scalar_div_subnormal794 as oracle

life,require=reused.life,reused.require
IMAGE_SHA=reused.IMAGE_SHA
PRE=life.OUT/'scalar-div-subnormal794-preflight-agent-20261008-02'
PRE_SHA='82d307a6feac27599e395d5e304097a78be2e1aaa26194595824a38854f3f4c5'
ELF=PRE/'input.elf'
NAME='scalar_div_subnormal794'
BUDGET=600
SERVICE='ara-scalar-div-subnormal794-parent-20261008-01.service'
PROBE=Path(__file__).with_name('scalar_div_subnormal794_probe.tcl').resolve()
exact_fields=reused.exact_fields


def source_contract():
    proof=reused.source_contract();packed=reused.packed
    layouts=packed.source_proof()['layouts']
    proof['issue_layout']=layouts['scoreboard_entry_t']
    require(proof['issue_layout']['width']==438 and proof['issue_layout']['fields']['pc']==[437,374] and
        proof['issue_layout']['fields']['trans_id']==[373,371],'Complete source-derived issue PC/TID layout')
    book=life.read_bound(oracle.old.BUILD/'build-source-pins.json',oracle.old.SOURCE_SHA)
    for rel in ('hardware/deps/cva6/core/issue_read_operands.sv',
        'hardware/deps/cva6/core/include/build_config_pkg.sv',
        'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv'):
        p=life.ROOT/rel;require(life.digest(p)==book[str(p)],'Frozen registered issue producer')
        proof['pins'][str(p)]=book[str(p)]
    issue=(life.ROOT/'hardware/deps/cva6/core/issue_read_operands.sv').read_text()
    require('assign fu_data_o = fu_data_q;' in issue and 'assign fpu_valid_o = fpu_valid_q;' in issue and
        'fpu_valid_q    <= fpu_valid_n;' in issue and 'fu_data_q <= fu_data_n;' in issue and
        'if (!issue_instr_i[i].ex.valid && issue_instr_valid_i[i] && issue_ack_o[i])' in issue,
        'Accepted issue PC/TID maps to next-edge registered FPU request')
    cfg=(life.ROOT/'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv').read_text()
    require("SuperscalarEn: bit'(0)" in cfg,'One issue port actual config')
    ariane=packed.clean((life.ROOT/'hardware/deps/cva6/core/include/ariane_pkg.sv').read_text())
    body=packed.unique(r'typedef\s+enum\s+logic\s*\[7:0\]\s*\{([^{}]*)\}\s*fu_op',ariane)
    names=[s.strip() for s in body.split(',') if s.strip()]
    for name in ('FMV_F2X','FMV_X2F'):proof['ariane_ops'][name]=names.index(name)
    pkg=packed.clean((life.ROOT/'hardware/deps/fpnew/src/fpnew_pkg.sv').read_text())
    body=packed.unique(r'typedef\s+enum\s+logic\s*\[OP_BITS-1:0\]\s*\{([^{}]*)\}\s*operation_e',pkg)
    proof['fpnew_ops']['SGNJ']=[s.strip() for s in body.split(',') if s.strip()].index('SGNJ')
    wrap=packed.clean((life.ROOT/'hardware/deps/cva6/core/fpu_wrap.sv').read_text())
    for op in ('FMV_F2X','FMV_X2F'):
        body=packed.unique(op+r':\s*begin(.*?)end',wrap)
        require('fpu_op_d        = fpnew_pkg::SGNJ;' in body and "fpu_rm_d        = 3'b011;" in body,
            'Both transfers are actual SGNJ passthrough FPU requests')
    proof['request_counts']=dict(DIV=144,FMV_X2F=288,FMV_F2X=144,total=576)
    return proof


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',NAME,
        '+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000','-ucli','-do',str(PROBE)]


def manifest(out,service=SERVICE):
    out=Path(out).absolute();require(out.parent==life.OUT and out.resolve()==out,'Canonical fresh run path')
    require(reused.re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service',service) is not None,'Actual owning service')
    pre=life.read_bound(PRE/'preflight.json',PRE_SHA)
    exact_fields(pre,dict(status='SPIKE_SCALAR_DIV_SUBNORMAL144_PASS_NOT_NATIVE',baseline=794,
        baseline_seal=oracle.BASE_SHA,cells=144,checks=436,RTL_changed=False,EDA_started=False),'Fixed preflight')
    require(oracle.validate(oracle.build.parse_spike_commits(PRE/'spike.trace'),pre['symbols'])==pre['counts'],
        'Full software/independent gold replay')
    require(json.loads(json.dumps(oracle.source_evidence()))==life.read_bound(PRE/'source-targets.json',pre['pins'][str(PRE/'source-targets.json')]),
        'Full source predicate/compiled794 replay')
    proof=source_contract();plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(plan['image'])==66 and plan['image'][str(life.IMAGE)]==reused.IMAGE_SHA,'Frozen image66')
    pins=life.merge_pins(pre['pins'],proof['pins'])
    for extra in (plan['image'],plan['design_files'],{str(life.PLAN):life.PLAN_SEAL,str(PRE/'preflight.json'):PRE_SHA}):
        pins=life.merge_pins(pins,extra)
    files=[Path(__file__).resolve(),PROBE,Path(__file__).with_name('collect_scalar_div_subnormal794.py'),
        Path(__file__).with_name('test_scalar_div_subnormal794.py'),Path(reused.__file__).resolve(),
        Path(reused.lifecycle.__file__).resolve(),Path(oracle.__file__).resolve(),
        reused.lifecycle.converter.CONVERTER]
    # The inherited lifecycle uses only these frozen module families; no public mutations.
    pending=[oracle,reused];seen=set()
    while pending:
        module=pending.pop();f=getattr(module,'__file__',None)
        if module in seen or not f or not str(f).startswith(str(life.ROOT/'verification')):continue
        seen.add(module);files.append(Path(f).resolve())
        pending.extend(v for v in vars(module).values() if isinstance(v,reused.ModuleType))
    files+=list((life.ROOT/'verification/ara_verify').rglob('*.py'))
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    return dict(case=NAME,output=str(out),command=command(out),pins=pins,timeout_s=BUDGET,
        input_elf=str(ELF),elf_sha256=pre['pins'][str(ELF)],image_sha256=reused.IMAGE_SHA,
        preflight_seal=PRE_SHA,raw_baseline_population=794,raw_baseline_seal=oracle.BASE_SHA,
        source_contract=proof,scalar_reference_counts=pre['counts'],expected_checks=436,service=service,
        systemd_policy=dict(RuntimeMaxSec=660,TimeoutStopSec=10,KillMode='control-group'),
        automatic_retry=False,no_FSDB=True,focused_readonly_VPD=True,RTL_changed=False,
        coverage_admitted=False,terminal_oracle_verified=False,
        authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED_BEFORE_RUN')


def verify(out,record,terminal=False):
    require(terminal or not out.exists(),'Fresh run output')
    require(record==manifest(out,record['service']),'Exact prepared command/source/dependencies')


def run(out,record):
    ns=dict(reused.run.__globals__,PRE=PRE,ELF=ELF,NAME=NAME,BUDGET=BUDGET,command=command)
    FunctionType(reused.run.__code__,ns)(out,record)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal')
    p.add_argument('--service',default=SERVICE);p.add_argument('--parent-authorized',action='store_true');a=p.parse_args()
    require(bool(a.prepared_seal)==(a.mode!='prepare') and a.parent_authorized==(a.mode=='run'),
        'Parent authorization only for run; seal for verify/run')
    out=a.output.resolve();sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not out.exists() and not sidecar.exists(),'Unique output/sidecar')
        life.save(sidecar,manifest(out,a.service));print('PREPARED_NO_VCS',life.digest(sidecar))
    else:
        record=life.read_bound(sidecar,a.prepared_seal);verify(out,record)
        if a.mode=='run':run(out,record)
        else:print('PREPARED_VERIFY_PASS_NO_VCS')
