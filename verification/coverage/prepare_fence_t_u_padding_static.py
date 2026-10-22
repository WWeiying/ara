"""One source/compiled-target review record only; never build or launch tools."""
import hashlib
import json
from pathlib import Path
import sys

from inventory_operand_debug import Design, points
from closure_point_inventory import read_xml, definition

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'verification/out'
BUILD=OUT/'repaired-aligned-build-20260930-01'
BASE=OUT/'vnclipu-offline-admitted-726-parent-20261006-01'
BASE_SHA='3ce8d24ffa5bfee7f4b363878b348af4e4b4de67995bc71db7b2bb6931121517'
OLD=OUT/'gap41-fence-padding-analysis-20261004-01'
PREFIX='ara_tb.dut.i_ara_soc.i_system.i_ariane.'


def require(ok, message):
    if not ok:raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
    return h.hexdigest()


def prepare(output):
    require(output.parent==OUT and not output.exists() and output.resolve()==output,'Fresh owned output required')
    pins={}
    def pin(path, expected=None):
        path=Path(path).absolute();actual=sha(path)
        require(expected is None or actual==expected,'Pin differs: '+str(path))
        pins[str(path)]=actual;return path
    manifest=json.loads(pin(BASE/'admission-manifest.json',BASE_SHA).read_bytes())
    bits_path=BASE/'combined-bits.json'
    bits=json.loads(pin(bits_path,manifest['output_pins'][str(bits_path)]).read_bytes())
    require(len(bits['tests'])==len(set(bits['tests']))==726,'Wrong admitted sample population')
    sourcepins=json.loads(pin(BUILD/'build-source-pins.json',
        '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b').read_bytes())
    old=json.loads(pin(OLD/'source-evidence.json').read_bytes())
    for entry in old['compiled_sources_matched']:
        path=Path(entry['path']);require(sourcepins[str(path)]==entry['sha256'],'Old source binding differs')
        pin(path,entry['sha256'])
    for path,expected in old['frozen_image_hashes_verified'].items():pin(path,expected)
    pin(BUILD/'compile.command.json',old['input_sha256'][str(BUILD/'compile.command.json')])
    require('no_fsdb=1' in (BUILD/'compile.command.json').read_text(),'Observer compile assumption changed')
    for name in ('REPORT.txt','budget-boundaries.json','candidate-plan.json','evidence-contract.json'):
        pin(OLD/name)
    for relative in ('hardware/deps/cva6/core/include/riscv_pkg.sv','hardware/tb/ara_commit_monitor.sv'):
        pin(ROOT/relative,sourcepins[str(ROOT/relative)])
    for relative in ('apps/fence_t_gap36_smoke/main.c','apps/fence_t_gap36_smoke/probe.S',
        'apps/common/crt0.S','verification/coverage/fence_rvfi_audit.py'):
        pin(ROOT/relative,old['input_sha256'][str(ROOT/relative)])
    for relative in ('apps/fence_t_u_padding_successor/main.c','apps/fence_t_u_padding_successor/probe.S',
        'apps/fence_t_u_padding_successor/REVIEW.txt',
        'verification/coverage/fence_t_u_padding_oracle.py','verification/coverage/test_fence_t_u_padding_oracle.py',
        'verification/coverage/inventory_operand_debug.py','verification/coverage/closure_point_inventory.py',
        'verification/coverage/reviewed_20261004/audit_readonly.py','verification/coverage/closure_scorecard.py'):
        pin(ROOT/relative)
    pin(Path(__file__))
    design=Design(BUILD/'sim/simv.vdb')
    for relative,expected in bits['design'].items():pin(design.db/relative,expected)
    for relative in ('auxiliary/verilog.sourceinfo.xml','shape/branch.verilog.info.xml','shape/cond.verilog.info.xml'):
        pin(design.db/relative)
    conditions=read_xml(design.db/'shape/cond.verilog.shape.xml')
    selection={'controller_i':{'cond':{29,31,33,40,41,42,43,44,45,46,50},'branch':{1,33,36}},
               'csr_regfile_i':{'branch':{520},'line':{780}}}
    targets=[];extra=[]
    for instance,metrics in selection.items():
        scope=PREFIX+instance
        source=design.source(scope)
        require(source['resolved_path'] in pins,'Compiled source not pinned')
        for metric,indices in metrics.items():
            record=bits['metrics'][metric][scope]
            node=definition(conditions,design.hierarchy[scope],record['checksum']) if metric=='cond' else design.definition(scope,metric)
            mapped={p['raw_index']:p for p in points(metric,node,record['width'])}
            for index in sorted(indices):
                require(not int(record['bits'],16)&(1<<(record['width']-1-index)),'Target already hit; reassess')
                row=dict(scope=scope,metric=metric,raw_index=index,definition_checksum=record['checksum'],
                    width=record['width'],source=source,compiled_point=mapped[index],hit726=False,
                    DVE_native_selector_qualified=False)
                (extra if instance=='controller_i' and metric=='branch' and index in (33,36) else targets).append(row)
    result=dict(status='SOURCE_REVIEW_ONLY_NOT_BUILT_NOT_RUN',baseline=str(BASE),baseline_seal=BASE_SHA,
        app=str(ROOT/'apps/fence_t_u_padding_successor'),legacy_checks=458,extra_checks=241,
        targets=targets,padding_predicate_branch_witnesses=extra,
        counts=dict(cond=11,branch=2,line=1),all_other_points_retained=True,
        source_path='CSR 7c3/7c4 -> cva6 connections -> controller U-exit load -> counter/delta_counter -> DRAIN ceil -> CSR 7c5; FENCE commit/no_st_pending -> flush/64-index scans -> PAD -> 16-cycle microreset -> PC+4 capture',
        observer=dict(rvfi_ecall='Unique event=retire, trap=1, exact ELF PC/opcode; cause8/MPP=U/TVAL0 via actual CSR-read/ledger stores',
            native_counter_window='UNAVAILABLE_NOT_QUALIFIED: no_fsdb=1; UCLI/PLI read route not validated; counter() accepts only future authenticated continuous native samples',
            cyclequalified=False, counter_source_model_only=True),
        boundary=dict(P=65536,proof_closed=False,
            equations=['e=D-L','ceil=e if 0<e<P else 0','PAD self-loops=max(P-e-1,0)',
                       'nonzero ceil requires e<P; PAD waiting requires e<=P-2'],
            reason='Final linked handler/C/probe prefix and response stalls have no proven finite H+Q bound. 64k is a fixed candidate, not an upper-bound theorem; do not tune/retry from failures.',
            runtime_policy='Software/retirement PASS and exact bitmap delta separately; ceil0 is target-not-observed, not automatically DUT FAIL. No exactcycleproof from CSR or mcycle delta.'),
        expected=dict(traps=1,cause=8,epc='padding_u_ecall ELF symbol',tval=0,MPP=0,
            fences=3,capture_stores=195,registers='All32 GPR/FPR third capture independently seeded as legacy round1; trap only clobbers caller-saved t0-t2 before reseeding',
            memory='64 warmed words, GPR/FPR seed arrays, capture and trap guards unchanged except exact intended ledger/capture stores',
            restore='All14 original CSRs plus mcause/mtval/CEIL, mstatus last; no vector traffic'),
        build_approved=False,VCS_approved=False,application_approval=False,pins=pins)
    for path,digest in pins.items():require(sha(path)==digest,'Input changed before sealing: '+path)
    output.mkdir()
    (output/'review.json').write_text(json.dumps(result,indent=2)+'\n')
    seal=sha(output/'review.json')
    (output/'seal.json').write_text(json.dumps(dict(review_sha256=seal),indent=2)+'\n')
    print(json.dumps(dict(output=str(output),seal=seal,pins=len(pins),counts=result['counts'])))


if __name__=='__main__':
    require(len(sys.argv)==2,'Only a fresh output positional argument is accepted')
    prepare(Path(sys.argv[1]).absolute())
