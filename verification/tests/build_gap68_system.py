#!/usr/bin/env python3
"""Build one gap68 case and a checked Spike-only draft. Never launch RTL."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
LEGACY = ROOT/'verification/tests/build_gap38_i8_f16_lane3.py'
spec = importlib.util.spec_from_file_location('gap68_immutable_build',LEGACY)
helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
sha,save,read,pins,verify,require = (getattr(helpers,n) for n in ('sha','save','read','pins','verify','require'))
sys.path.insert(0,str(ROOT/'verification/coverage'))
import audit_gap68_system as audit
import coverage_evidence as evidence
import run_gap68_system_checked_extension as adapter

NAME = audit.NAME.split(':')[1]
SOURCE = ROOT/'apps/riscv-tests/isa/rv64uv'/(NAME+'.c')
UNIT = ROOT/'verification/tests/test_gap68_system.py'
BASE = ROOT/'verification/out/gap67-current-20261004-01'
HISTORY = ROOT/'verification/out/gap66-ptw-analysis-20261004-01'
FROZEN = ROOT/'verification/out/repaired-aligned-build-20260930-01'

def baseline_audit():
    # Existing Evidence.plan seal and gap66's bounded manifest/cache preflight pattern.
    # Full historic admission and image hashing belong to the parent runner.
    proof=evidence.Evidence(); plan=proof.plan(BASE)
    collection=proof.read(BASE/'collection.json'); cp=proof.read(BASE/'checkpoint.json')
    image=proof.read(FROZEN/'build-image.json')
    require(cp['coverage_status']=='COMPLETE' and cp['aggregate_passed']==650 and
        collection['status']=='PASS' and collection['passed']==650,'need COMPLETE650/PASS650')
    require(collection['image']==plan['image']==image and not collection['cross_image_reuse'],'image map differs')
    for rel in ('all-passed-outcomes.json','combined-bits.json','combined-dve/inputs.txt','combined-dve/summary.csv'):
        proof.pin(BASE/rel,collection['reports'][str(BASE/rel)])
    rows=read(BASE/'all-passed-outcomes.json'); bits=read(BASE/'combined-bits.json')
    inputs=(BASE/'combined-dve/inputs.txt').read_text().splitlines()
    old=proof.read(ROOT/'verification/out/gap59-current-20261004-01/all-passed-outcomes.json')
    require(len(rows)==650 and rows[:648]==old and len({r['name'] for r in rows})==650,'650 ledger lineage differs')
    require(all(r['status']=='PASS' and r['passed_only'] and r['vdb_valid'] for r in rows),'non-PASS member')
    require(bits['tests']==inputs[1:]==[r['vdb'] for r in rows] and inputs[0]==plan['design_vdb'],'cache membership differs')
    require(not any(r['name'] in (NAME,audit.NAME) for r in rows),'duplicate candidate')
    ledger_hashes={p:h for r in rows for p,h in r['vdb_files'].items()}
    require(all(ledger_hashes.get(p)==h for p,h in bits['input_hashes'].items()),'raw cache pins differ from ledger')
    candidate=proof.read(HISTORY/'candidate-points.json')
    require([(p['label'],p['point']['raw_index']) for p in candidate['targets']]==[('mmu',102),('mmu',105),('ptw',62)],
            'target set differs')
    source_pins=proof.read(FROZEN/'build-source-pins.json')
    config=proof.read(ROOT/'verification/out/gap52-system-preflight-20261004-01/config-audit.json')
    selected=dict(config['frozen_rtl'])
    for point in candidate['targets']:
        p=point['source']['source_path']; selected[p]=source_pins[p]
        row=bits['metrics']['cond'][point['scope']]
        require(str(row['checksum'])==point['metric_checksum'] and
            format(int(row['bits'],16),'0%db'%row['width'])[point['point']['raw_index']]=='0','target no longer zero/shape drift')
    require(all(source_pins[p]==h for p,h in selected.items()),'source freeze manifests differ')
    proof.hashes(selected)
    require('cfg.NrPMPEntries          = 0;' in (ROOT/'hardware/src/ara_soc.sv').read_text(),'PMP0 override missing')
    for rel in ('HANDOFF.md','validation.json'):
        proof.pin(HISTORY/rel)
    return dict(status='PASS_LIGHTWEIGHT_PREPARATION_ONLY',baseline=str(BASE),passed=650,
        coverage_status='COMPLETE',checked_files=proof.files,targets=candidate['targets'],
        full_admission_deferred=True,image_bytes_rehashed=False,historical_raw_rehashed=False,
        measured_gain=None,coverage_gain_required=False,waivers_applied=False)

def metadata(b,elf,label):
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],label+'.disassembly')
    result=b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols','--program-headers',elf],label+'.metadata')
    return dict(elf=str(elf),elf_sha256=sha(elf),metadata=audit.metadata(json.loads(result.stdout)[0],elf.read_bytes()))

def host_oracle(b):
    obj=b.compile(SOURCE,'host-oracle',['-DGAP68_ORACLE_HOST=1'],host=True)
    exe=b.out/'host-oracle'; b.link([b.host,obj,'-o',exe],'host-oracle.link')
    run=b.run([exe],'host-oracle.results',timeout=30)
    pages=audit.expected_pages(0x80040000)
    expected=[('D',p,w,v) for p in range(2) for w,v in enumerate(pages[3+p])]
    expected += [('T',p,w,v) for p in range(3) for w,v in enumerate(pages[p])]
    actual=[(k,int(p),int(w),int(v,16)) for k,p,w,v in (line.split() for line in run.stdout.decode().splitlines())]
    require(actual==expected,'C/Python complete-page oracle differs')
    save(b.out/'oracle-check.json',dict(status='PASS',rows=2560,data_words=1024,pte_words=1536,
         reference='Sparse independent Python PPN/flags construction vs compiled C expectations',binary=str(exe),binary_sha256=sha(exe)))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(); out=args.output.resolve()
    require(ROOT==Path('/home/wangwy/openproject/ara_dsa_signoff_integration'),'wrong worktree')
    require(out.parent==ROOT/'verification/out' and out.name.startswith('gap68-system-preflight-') and not out.exists(),'fresh gap68 output required')
    baseline=baseline_audit()
    pin_plan=ROOT/'verification/out/repaired-aligned-600-20260930-01/plan.json'
    old=next(c for c in read(pin_plan)['cases'] if c.get('spike')); spike=Path(old['spike'])
    require(sha(spike)==old['spike_sha256'],'pinned Spike changed')
    spike_sources=[spike.parent.parent/p for p in ('riscv/mmu.cc','riscv/csr_init.cc','riscv/csrs.cc',
        'riscv/processor.cc','riscv/insns/sfence_vma.h','spike_main/spike.cc')]
    protected=dict(baseline['checked_files']); protected.update(pins([LEGACY,pin_plan,*spike_sources]))
    out.mkdir(); save(out/'baseline-targets.json',baseline); save(out/'protected-inputs.json',protected)
    (out/'source.snapshot').write_bytes(SOURCE.read_bytes())
    b=helpers.Build(out); b.sources=pins([SCRIPT,SOURCE,LEGACY,UNIT,adapter.SCRIPT,Path(audit.__file__)])
    b.tools.update(pins([spike,ROOT/'verification/tools/soc-venv/bin/python']))
    b.run([sys.executable,'-B',UNIT,'-v'],'unit-tests'); host_oracle(b)
    objects=[b.compile(b.common/n,'dut-'+n) for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects.insert(0,b.compile(SOURCE,'dut-test',['-Wall','-Wextra','-Wno-unused-function','-Wno-unused-parameter']))
    elf=out/(NAME+'.elf'); b.bind_sources([b.common/'link.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
        '-Wl,-Map='+str(out/'dut.map'),'-T'+str(b.common/'link.ld'),*objects,'-lm',
        '-L'+str(b.llvm/'lib/generic'),'-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    fit=ROOT/'verification/coverage/check_elf_fit.py'; b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',elf,'--ram-bytes','0x200000','--output',out/'elf-fit.json'],'elf-fit')
    dut=metadata(b,elf,'dut')
    runtime=ROOT/'apps/riscv-tests/benchmarks/common'
    extra=['-D__SPIKE__=1','-DPREALLOCATE=1','-I'+str(runtime),'-I'+str(ROOT/'apps/riscv-tests/env'),
           '-fno-function-sections','-fno-data-sections']
    objects=[b.compile(src,label,extra) for src,label in
        ((runtime/'crt.S','spike-crt'),(runtime/'syscalls.c','spike-syscalls'),(SOURCE,'spike-test'))]
    spike_elf=out/(NAME+'.spike'); b.bind_sources([runtime/'test.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostdlib','-T'+str(runtime/'test.ld'),*objects,'-o',spike_elf],'spike.link')
    spike_info=metadata(b,spike_elf,'spike')
    require(dut['metadata']['payload_sha256']==spike_info['metadata']['payload_sha256'],'DUT/Spike probe bytes differ')
    dts=b.run([spike,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','--dump-dts',spike_elf],'spike-config')
    audit.validate_pmp_dts(dts.stdout.decode())
    parts=dict(setup=9,post_probe_status=2,trap_count_and_abi=2,trap_records=20,full_regions_and_guards=7,
               unchanged_fp_vector_csrs=5,restored_csrs_and_status_alias=21,main=2,harness=3)
    require(sum(parts.values())==audit.CHECKS,'check-count derivation differs')
    save(out/'config-audit.json',dict(status='PASS',pmp_regions=0,rvh=0,xlen=64,translation='Sv39',
        asid=0x68,count_parts=parts,spike_source_review=pins(spike_sources),
        dts_log=str(out/'spike-config.log'),dts_sha256=sha(out/'spike-config.log'),
        automatic_ad_updates=False,pmp_csr_accesses=0,actual_execution='M',data_effective_privilege='S'))
    command=audit.expected_command(str(spike),str(spike_elf)); run=b.run(command,'case.spike',timeout=30)
    seconds=b.commands[-1]['seconds']; audit.check_log(run.stdout.decode(),str(SOURCE))
    trace=audit.trace_check(run.stderr.decode(),spike_info['metadata'])
    save(out/'execution-proof.json',dict(status='PASS',dut=dut,spike=spike_info,spike_tool=str(spike),trace=trace,
        checks=audit.CHECKS,retired_limit=audit.MAX_RETIRED,vcs_timeout_s=300,vcs_launched=False,measured_gain=None))
    b.run([sys.executable,'-B',UNIT,'--preflight',out,'-v'],'real-trace-unit-tests',timeout=120)
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values()) if getattr(m,'__file__',None)
        and str(Path(m.__file__).resolve()).startswith(str(ROOT/'verification'))])
    for hashes in (b.sources,b.tools,b.link_inputs,protected): verify(hashes)
    save(out/'source_hashes.json',b.sources); save(out/'tool_hashes.json',b.tools); save(out/'link-inputs.json',b.link_inputs)
    row=dict(test=audit.NAME,status='PASS',returncode=0,command=command,seconds=seconds,
        binary=str(elf),binary_sha256=sha(elf),spike_binary=str(spike_elf),spike_sha256=sha(spike_elf),
        spike_tool_sha256=sha(spike),source_hashes=b.sources,tool_hashes=b.tools,link_inputs=b.link_inputs,
        log=str(out/'case.spike.log'),log_sha256=sha(out/'case.spike.log'),
        trace_log=str(out/'case.spike.stderr.log'),trace_sha256=sha(out/'case.spike.stderr.log'),
        checks=audit.CHECKS,retired=trace['retired'],vcs_launched=False,measured_coverage_gain=None)
    save(out/'spike_results.json',[row]); artifacts=pins(p for p in out.iterdir() if p.is_file())
    save(out/'artifact_hashes.json',artifacts)
    item=dict(name=audit.NAME,binary=str(elf),binary_sha256=sha(elf),sources=sorted(b.sources),source_hashes=b.sources,
        evidence=sorted([*artifacts,str(out/'artifact_hashes.json')]),timeout_s=300,
        source_audit='Independent sparse PPN/flag oracle; 1536 PTE + 1024 data + 16 guards. '
            'Exactly two M-executed store faults with MPRV/S, MPP=M traps, register-only MPRV clear, '
            'ABI/CSR restore and ELF-bound dependent load/XOR/store sequences. Spike <=35000 retired/PMP0.',
        targets=sorted({p['scope'] for p in baseline['targets']}),
        rationale='COMPLETE650 zero condition rows MMU102/105 and PTW62; predicted only, not warm-hit coverage proof.',
        precheck=dict(format='rvv-spike-v1',record=str(out/'spike_results.json'),log=row['log']))
    draft=out/'selection.checked-draft.json'
    save(draft,dict(status='CHECKED_DRAFT_SPIKE_ONLY_NOT_SUBMITTED',baseline=str(BASE),
        baseline_bits=str(BASE/'combined-bits.json'),cases=[item],vcs_launched=False,waivers_applied=False,
        full_admission_deferred=True,measured_candidate_gain=None))
    proof=evidence.Evidence(); proof.pin(draft)
    for hashes in (b.tools,b.link_inputs,protected,artifacts): proof.hashes(hashes)
    result=evidence.precheck(item,proof)
    save(out/'checked-precheck.json',dict(status='PASS',result=result,checked_files=proof.files,
        read_only_validation=True,entrypoint='coverage_evidence.precheck',vcs_launched=False))
    save(out/'draft.sha256.json',pins([draft,out/'checked-precheck.json',out/'artifact_hashes.json']))
    adapter.install_hooks(); outer=evidence.Evidence(); sealed=evidence.precheck(item,outer)
    require(sealed==result,'sealed result differs')
    save(out/'sealed-replay.json',dict(status='PASS',result=sealed,checked_files=outer.files,
        exact_original_checked_files=len(proof.files),vcs_launched=False,full_admission_deferred=True))
    verify(protected)
    print('PASS: Spike %d checks, %d retired; two store traps; no RTL simulation'%(audit.CHECKS,trace['retired']),flush=True)
    print(draft,flush=True)

if __name__=='__main__': main()
