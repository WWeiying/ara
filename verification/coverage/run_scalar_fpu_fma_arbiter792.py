"""One frozen-ELF120s experiment. Prepare/check never execute VCS."""
import argparse
import json
from pathlib import Path
import re
from types import FunctionType, ModuleType

import build_scalar_fpu_fma_arbiter792 as oracle
import run_csr_satp_sepc786 as lifecycle
import csr_satp_sepc_packed_adapter as packed
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence_v2 as toggle
import diagnose_scalar_fpu_backpressure as diagnostic

life, require = lifecycle.life, lifecycle.require
PRE = life.OUT/'scalar-fpu-fma-arbiter792-preflight-agent-20261008-01'
PRE_SHA = 'a561c836e7f4114ae5311e706e4826e47986ac9f481cad7fb782c60ca0b4d3bb'
REVIEW = life.OUT/'scalar-fpu-fma-arbiter792-review-agent-20261008-01.json'
REVIEW_SHA = '5a2621c8a5dc5cb39ed02c9216a906249aa49bec22c6757100c90a59d49a7153'
ELF = PRE/'input.elf'
NAME, BUDGET = 'scalar_fpu_fma_arbiter792', 120
SERVICE = 'ara-scalar-fpu-fma-arbiter792-parent-20261008-01.service'
PROBE = Path(__file__).with_name('scalar_fpu_fma_arbiter792_probe.tcl').resolve()
IMAGE_SHA = lifecycle.IMAGE_SHA
exact_fields = lifecycle.exact_fields


def source_contract():
    proof = packed.source_proof()
    layout = proof['layouts']['fu_data_t']
    require(layout['width']==207 and layout['fields']['imm']==[66,3], 'Complete source-derived FU layout')
    bookpath = oracle.old.BUILD/'build-source-pins.json'
    book = life.read_bound(bookpath,oracle.old.SOURCE_SHA)
    pins = dict(proof['pins']); texts = {}
    for rel in ('hardware/deps/fpnew/src/fpnew_pkg.sv','hardware/deps/cva6/core/fpu_wrap.sv',
                'hardware/deps/cva6/core/scoreboard.sv','hardware/deps/cva6/core/cva6.sv',
                'hardware/deps/cva6/core/ex_stage.sv'):
        p=life.ROOT/rel; require(life.digest(p)==book[str(p)],'Frozen FMA mapping source')
        pins[str(p)]=book[str(p)];texts[rel]=packed.clean(p.read_text())
    pkg=texts['hardware/deps/fpnew/src/fpnew_pkg.sv']
    body=packed.unique(r'typedef\s+enum\s+logic\s*\[OP_BITS-1:0\]\s*\{([^{}]*)\}\s*operation_e',pkg)
    names=[s.strip() for s in body.split(',') if s.strip()]
    require(all(re.fullmatch(r'[A-Z][A-Z0-9_]*',s) for s in names),'Implicit FPNEW operation enum')
    ops={k:names.index(k) for k in ('FMADD','DIV','CLASSIFY')}
    require(ops==dict(FMADD=0,DIV=4,CLASSIFY=9),'Frozen operation identities')
    wrap=texts['hardware/deps/cva6/core/fpu_wrap.sv']
    writes=re.findall(r'assign\s+fpu_exception_o\.([a-z0-9_]+)\s*=\s*([^;]+);',wrap)
    require(dict(writes)==dict(cause="{59'h0, fpu_status}",valid="1'b0",tval="'0") and
            len(writes)==3 and len(re.findall(r'fpu_exception_o',wrap))==4,
            'Only cause/valid/tval driven; no whole-parent or extra writer')
    exception=proof['layouts']['exception_t']
    require(exception==dict(width=203,fields=dict(cause=[202,139],tval=[138,75],
            tval2=[74,34],tinst=[33,2],gva=[1,1],valid=[0,0])),
            'Complete source-derived exception packed layout')
    sb=texts['hardware/deps/cva6/core/scoreboard.sv']
    require('if (ex_i[i].valid) mem_n[trans_id_i[i]].sbe.ex = ex_i[i];' in sb and
            'mem_n[trans_id_i[i]].sbe.ex.cause = ex_i[i].cause;' in sb and
            'mem_q[trans_id_i[i]].sbe.fu == ariane_pkg::FPU' in sb and
            'assign ex_ex_ex_id[FPU_WB]    = fpu_exception_ex_id;' in texts['hardware/deps/cva6/core/cva6.sv'] and
            '.fpu_exception_o' in texts['hardware/deps/cva6/core/ex_stage.sv'],
            'FPU writeback consumer reads valid then cause; no unused-member interpretation')
    require('FMADD:   fpu_op_d = fpnew_pkg::FMADD;' in wrap and
            'operand_c_q  <= operand_c_d;' in wrap and 'fpu_tag_q    <= fpu_tag_d;' in wrap,
            'FMA and held operand/tag producer')
    pins[str(Path(packed.__file__).resolve())]=life.digest(Path(packed.__file__))
    op_width=int(packed.unique(r'localparam int unsigned OP_BITS\s*=\s*(\d+)\s*;',pkg))
    group_width=int(packed.unique(r'localparam int unsigned NUM_OPGROUPS\s*=\s*(\d+)\s*;',pkg))
    require(op_width==5 and group_width==5,'Actual FPNEW operation/group widths')
    ariane=packed.clean((life.ROOT/'hardware/deps/cva6/core/include/ariane_pkg.sv').read_text())
    body=packed.unique(r'typedef\s+enum\s+logic\s*\[7:0\]\s*\{([^{}]*)\}\s*fu_op',ariane)
    names=[s.strip() for s in body.split(',') if s.strip()]
    require(all(re.fullmatch(r'[A-Z][A-Z0-9_]*',s) for s in names),'Implicit CVA6 operation enum')
    return dict(fu_layout=layout,exception_layout=proof['layouts']['exception_t'],
                fpnew_ops=ops,ariane_ops={k:names.index(k) for k in ('FMADD','FDIV','FCLASS')},
                exception_observed=['cause','valid','tval'],
                exception_unobserved=['tval2','tinst','gva'],
                op_width=op_width,tag_width=3,group_width=group_width,format_width=6,pins=pins)


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',NAME,
        '+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000','-ucli','-do',str(PROBE)]


def manifest(out,service=SERVICE):
    out=Path(out).absolute()
    require(out.parent==life.OUT and out.resolve()==out,'Direct canonical output')
    require(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service',service) is not None,'Exact owning service')
    pre=life.read_bound(PRE/'preflight.json',PRE_SHA)
    exact_fields(pre,dict(status='SPIKE_FMA_DIV_CLASS_EXACT_PASS_ARBITRATION_UNPROVEN',
        baseline=792,baseline_seal=oracle.BASE_SHA,checks=56,FMA=40,DIV=2,FCLASS=8,
        flags=0,EDA_started=False,RTL_changed=False),'Frozen software contract')
    require(oracle.validate(oracle.build.parse_spike_commits(PRE/'spike.trace'),pre['symbols'])==pre['counts'],
            'Full frozen software reference replay')
    review=life.read_bound(REVIEW,REVIEW_SHA);life.check(review['input_pins'])
    base=life.read_bound(oracle.BASE/'admission-manifest.json',oracle.BASE_SHA)
    ledger=oracle.BASE/'combined-inputs.txt'
    require(life.digest(ledger)==base['output_pins'][str(ledger)] and
            len(ledger.read_text().splitlines())==len(set(ledger.read_text().splitlines()))==793,'Exact792 baseline')
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(plan['image'])==66 and plan['image'][str(life.IMAGE)]==IMAGE_SHA,'Frozen image66')
    proof=source_contract()
    pins=dict(pre['pins'])
    for extra in (review['input_pins'],plan['image'],plan['design_files'],proof['pins'],
        {str(REVIEW):REVIEW_SHA,str(PRE/'preflight.json'):PRE_SHA,str(life.PLAN):life.PLAN_SEAL}):
        pins=life.merge_pins(pins,extra)
    for name in ('combined-inputs.txt','combined-bits.json','combined-toggle-bits.json','status.json'):
        p=oracle.BASE/name;pins=life.merge_pins(pins,{str(p):base['output_pins'][str(p)]})
    files=[Path(__file__).resolve(),PROBE,Path(__file__).with_name('collect_scalar_fpu_fma_arbiter792.py'),
        Path(__file__).with_name('diagnose_scalar_fpu_backpressure.py'),
        Path(__file__).with_name('test_scalar_fpu_fma_arbiter792_runtime.py'),lifecycle.converter.CONVERTER]
    files+=list((life.ROOT/'verification/ara_verify').rglob('*.py'))
    # Follow only this consumer's imported modules, not the caller's sys.modules.
    pending=[oracle,lifecycle,packed,bitmap,toggle,diagnostic];seen=set()
    while pending:
        module=pending.pop();f=getattr(module,'__file__',None)
        if module in seen or not f or not str(f).startswith(str(life.ROOT/'verification')):continue
        seen.add(module);files.append(Path(f).resolve())
        pending.extend(v for v in vars(module).values() if isinstance(v,ModuleType))
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    require(life.digest(lifecycle.converter.CONVERTER)==lifecycle.converter.CONVERTER_SHA,'Frozen converter')
    return dict(case=NAME,output=str(out),command=command(out),pins=pins,timeout_s=BUDGET,
        input_elf=str(ELF),input_spike_trace=str(PRE/'spike.trace'),elf_sha256=pre['pins'][str(ELF)],
        image_sha256=IMAGE_SHA,preflight_seal=PRE_SHA,raw_baseline=str(oracle.BASE),
        raw_baseline_seal=oracle.BASE_SHA,raw_baseline_population=792,source_contract=proof,
        scalar_reference_counts=pre['counts'],expected_checks=56,service=service,
        systemd_policy=dict(RuntimeMaxSec=180,TimeoutStopSec=10,KillMode='control-group'),
        automatic_retry=False,no_FSDB=True,focused_readonly_VPD=True,RTL_changed=False,
        coverage_admitted=False,terminal_oracle_verified=False,
        authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED_BEFORE_RUN')


def verify(out,record,terminal=False):
    require(terminal or not out.exists(),'Fresh execution output')
    require(record==manifest(out,record['service']),'Exact prepared identity/source/command')


def run(out,record):
    ns=dict(lifecycle.lifecycle_namespace.__globals__,PRE=PRE,ELF_SHA=record['elf_sha256'],
            IMAGE_SHA=IMAGE_SHA,BUDGET=BUDGET,NAME=NAME,command=command)
    FunctionType(lifecycle.lifecycle_namespace.__code__,ns)(out,record)['run'](out,record)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','verify','run'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepared-seal');p.add_argument('--service',default=SERVICE)
    p.add_argument('--parent-authorized',action='store_true');a=p.parse_args()
    require(bool(a.prepared_seal)==(a.mode!='prepare'),'Prepared seal required')
    require(a.parent_authorized==(a.mode=='run'),'Separate parent approval required')
    out=a.output.resolve();sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not out.exists() and not sidecar.exists(),'Fresh output/sidecar')
        life.save(sidecar,manifest(out,a.service));print(sidecar,life.digest(sidecar))
    else:
        record=life.read_bound(sidecar,a.prepared_seal);verify(out,record)
        if a.mode=='run':run(out,record)
        else:print('FMA792_FIXED120_PREPARED_CHECK_PASS_NO_VCS')
