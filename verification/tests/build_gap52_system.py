#!/usr/bin/env python3
"""Build and independently precheck gap52 in new output files. Never launch VCS."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
LEGACY = ROOT / 'verification/tests/build_gap38_i8_f16_lane3.py'
spec = importlib.util.spec_from_file_location('gap52_immutable_build', LEGACY)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
sha, save, read, pins, verify, require = (getattr(helpers,n) for n in
    ('sha','save','read','pins','verify','require'))
sys.path.insert(0, str(ROOT/'verification/coverage'))
import audit_gap52_system as audit
import coverage_evidence as evidence
import run_gap52_system_checked_extension as adapter

NAME = audit.NAME.split(':')[1]
SOURCE = ROOT / 'apps/riscv-tests/isa/rv64uv' / (NAME+'.c')
UNIT = ROOT / 'verification/tests/test_gap52_system.py'
BASE = ROOT / 'verification/out/gap48-current-20261004-01'
HISTORY = ROOT / 'verification/out/gap52-system-analysis-20261004-01'
FROZEN = ROOT / 'verification/out/repaired-aligned-build-20260930-01'
PATH_SOURCES = ('hardware/src/ara_soc.sv','hardware/src/ara_system.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv','hardware/deps/cva6/core/csr_regfile.sv',
    'hardware/deps/cva6/core/pmp/src/pmp.sv','hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv',
    'hardware/deps/cva6/core/cva6_mmu/cva6_tlb.sv','hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv',
    'hardware/deps/cva6/core/ex_stage.sv','hardware/deps/cva6/core/controller.sv')


def baseline_audit():
    checkpoint, collection = read(BASE/'checkpoint.json'), read(BASE/'collection.json')
    require(checkpoint['coverage_status']=='COMPLETE' and checkpoint['aggregate_passed']==645 and
            collection['status'] in ('PASS','COMPLETE_WITH_FAILURES') and collection['passed']==645,
            'need final COMPLETE645 passing aggregate')
    checked = pins([BASE/'checkpoint.json',BASE/'collection.json',FROZEN/'build-source-pins.json'])
    for rel in ('combined-bits.json','all-passed-outcomes.json','combined-dve/inputs.txt','combined-dve/summary.csv'):
        path = BASE/rel
        require(sha(path)==collection['reports'][str(path)],'baseline report hash differs')
        checked[str(path)] = sha(path)
    frozen = read(FROZEN/'build-source-pins.json')
    selected_sources = {str(ROOT/p):frozen[str(ROOT/p)] for p in PATH_SOURCES}
    verify(selected_sources); checked.update(selected_sources)
    require('cfg.NrPMPEntries          = 0;' in (ROOT/PATH_SOURCES[0]).read_text(),'PMP0 override missing')
    cfg = (ROOT/'hardware/deps/cva6/core/include/build_config_pkg.sv').read_text()
    require('cfg.ASID_WIDTH = (CVA6Cfg.XLEN == 64) ? 16 : 1;' in cfg,'ASID width derivation changed')
    history_seal = read(HISTORY/'analysis-validation.json')
    verify(history_seal['files'])
    checked.update(history_seal['files']); checked[str(HISTORY/'analysis-validation.json')] = sha(HISTORY/'analysis-validation.json')
    inventory = read(HISTORY/'inventory.json')
    verify(inventory['pins']); checked.update(inventory['pins'])
    rows, bits = read(BASE/'all-passed-outcomes.json'), read(BASE/'combined-bits.json')
    inputs = (BASE/'combined-dve/inputs.txt').read_text().splitlines()
    old_rows = read(Path(inventory['baseline'])/'all-passed-outcomes.json')
    require(len(rows)==645 and rows[:641]==old_rows and bits['tests']==inputs[1:]==[r['vdb'] for r in rows],
            '645 membership/order differs from final 641 plus four PASS')
    require(all(r['status']=='PASS' and r['passed_only'] and r['vdb_valid'] for r in rows),
            'non-PASS member admitted')
    require(not any(r['name'] in (NAME,audit.NAME) for r in rows),'duplicate candidate')
    for rel,digest in bits['design'].items():
        path = Path(inputs[0])/'snps/coverage/db'/rel
        require(sha(path)==digest,'design shape changed'); checked[str(path)] = digest
    mapper = ROOT/'verification/coverage/reviewed_20261004/audit_readonly.py'
    spec = importlib.util.spec_from_file_location('gap52_native',mapper)
    native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
    scopes = [s for s in inventory['instances'] if s.endswith(('.i_itlb','.i_dtlb'))]
    merged = {(s,m):int(inventory['instances'][s]['metrics'][m]['bits'],2)
              for s in scopes for m in ('line','cond')}
    for row in rows[641:]:
        for metric in ('line','cond'):
            files = list(Path(row['vdb']).glob('snps/coverage/db/testdata/*/%s.verilog.data.xml'%metric))
            require(len(files)==1,'ambiguous raw file')
            path = files[0]; digest = sha(path)
            require(digest==row['vdb_files'][str(path)],'new PASS raw file drift')
            checked[str(path)] = digest
            seen = set()
            for node in native.xml(path).iter('instance_data'):
                scope = node.get('name')
                if scope in scopes:
                    require(scope not in seen,'duplicate raw scope'); seen.add(scope)
                    old = inventory['instances'][scope]['metrics'][metric]
                    require(len(node.get('value'))==old['width'],'raw width differs')
                    merged[scope,metric] |= int(node.get('value'),2)
            require(seen==set(scopes),'missing raw scope')
    for (scope,metric),value in merged.items():
        row = bits['metrics'][metric][scope]
        require(value==int(row['bits'],16),'645 cache does not match 641 plus four raw PASS files')
    targets = read(HISTORY/'candidate-points.json')['native_zero_targets']
    missing = [p for p in targets if format(int(bits['metrics'][p['metric']][p['scope']]['bits'],16),
               '0%db'%bits['metrics'][p['metric']][p['scope']]['width'])[p['raw_index']]=='0']
    return dict(status='PASS',baseline=str(BASE),passed=645,coverage_status='COMPLETE',
        prior_passed=641,raw_delta_cases=4,targets=missing,
        remaining_counts={m:sum(p['metric']==m for p in missing) for m in ('line','cond')},
        checked_files=checked,measured_gain=None,coverage_gain_required=False,waivers_applied=False)


def metadata(b,elf,label):
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],label+'.disassembly')
    result = b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',
                    '--program-headers',elf],label+'.metadata')
    info = audit.metadata(json.loads(result.stdout)[0],elf.read_bytes())
    return dict(elf=str(elf),elf_sha256=sha(elf),metadata=info)


def host_oracle(b):
    obj = b.compile(SOURCE,'host-oracle',['-DGAP52_ORACLE_HOST=1'],host=True)
    exe = b.out/'host-oracle'
    b.link([b.host,obj,'-o',exe],'host-oracle.link')
    run = b.run([exe],'host-oracle.results',timeout=30)
    pages = audit.expected_pages(0x80040000)
    expected = [('D',p,w,value) for p in range(2) for w,value in enumerate(pages[3+p])]
    expected += [('T',p,w,value) for p in range(3) for w,value in enumerate(pages[p])]
    actual = [(k,int(p),int(w),int(value,16)) for k,p,w,value in
              (line.split() for line in run.stdout.decode().splitlines())]
    require(actual==expected,'compiled C oracle differs from independent Python page model')
    save(b.out/'oracle-check.json',dict(status='PASS',rows=2560,data_words=1024,pte_words=1536,
        reference='Independent Python sparse page construction vs compiled C expectation functions',
        binary=str(exe),binary_sha256=sha(exe)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--development',action='store_true',help='new scratch directory; no draft or seals')
    args = parser.parse_args()
    out = args.output.resolve()
    prefix = 'gap52-system-development-' if args.development else 'gap52-system-preflight-'
    require(ROOT==Path('/home/wangwy/openproject/ara_dsa_signoff_integration'),'wrong worktree')
    require(out.parent==ROOT/'verification/out' and out.name.startswith(prefix) and not out.exists(),
            'require a new independent output directory')
    baseline = baseline_audit()
    pin_plan = ROOT/'verification/out/repaired-aligned-600-20260930-01/plan.json'
    old = next(c for c in read(pin_plan)['cases'] if c.get('spike'))
    spike = Path(old['spike'])
    require(sha(spike)==old['spike_sha256'],'pinned Spike changed')
    spike_sources = [spike.parent.parent/p for p in ('riscv/insns/sfence_vma.h','riscv/mmu.cc',
                     'riscv/mmu.h','riscv/csrs.cc','riscv/processor.cc','spike_main/spike.cc')]
    protected = dict(baseline['checked_files'])
    protected.update(pins([LEGACY,pin_plan,SOURCE.with_name('vgap35_common.h'),Path(evidence.__file__),
                          ROOT/'verification/coverage/run_checked_extension.py',*spike_sources]))
    out.mkdir()
    save(out/'baseline-targets.json',baseline); save(out/'protected-inputs.json',protected)
    (out/'source.snapshot').write_bytes(SOURCE.read_bytes())
    b = helpers.Build(out)
    b.sources = pins([SCRIPT,SOURCE,LEGACY,UNIT,adapter.SCRIPT,Path(audit.__file__)])
    b.tools.update(pins([spike,ROOT/'verification/tools/soc-venv/bin/python']))
    print('COMPLETE645 verified; building only the new system case',flush=True)
    b.run([sys.executable,'-B',UNIT],'unit-tests')
    host_oracle(b)
    objects = [b.compile(b.common/n,'dut-'+n) for n in
               ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects.insert(0,b.compile(SOURCE,'dut-test',['-Wall','-Wextra','-Wno-unused-function','-Wno-unused-parameter']))
    elf = out/(NAME+'.elf'); b.bind_sources([b.common/'link.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
            '-Wl,-Map='+str(out/'dut.map'),'-T'+str(b.common/'link.ld'),*objects,'-lm',
            '-L'+str(b.llvm/'lib/generic'),'-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    fit = ROOT/'verification/coverage/check_elf_fit.py'; b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',elf,'--ram-bytes','0x200000',
           '--output',out/'elf-fit.json'],'elf-fit')
    dut = metadata(b,elf,'dut')
    runtime = ROOT/'apps/riscv-tests/benchmarks/common'
    extra = ['-D__SPIKE__=1','-DPREALLOCATE=1','-I'+str(runtime),'-I'+str(ROOT/'apps/riscv-tests/env'),
             '-fno-function-sections','-fno-data-sections']
    objects = [b.compile(src,label,extra) for src,label in
        ((runtime/'crt.S','spike-crt'),(runtime/'syscalls.c','spike-syscalls'),(SOURCE,'spike-test'))]
    spike_elf = out/(NAME+'.spike'); b.bind_sources([runtime/'test.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostdlib','-T'+str(runtime/'test.ld'),
            *objects,'-o',spike_elf],'spike.link')
    spike_info = metadata(b,spike_elf,'spike')
    require(dut['metadata']['s_payload_sha256']==spike_info['metadata']['s_payload_sha256'],
            'DUT and Spike S-mode instruction bytes differ')
    dts = b.run([spike,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                 '--dump-dts',spike_elf],'spike-config')
    audit.validate_pmp_dts(dts.stdout.decode())
    parts = dict(setup=5,trap_records=5*13,trap_count_and_abi=2,full_regions_and_guards=7,
                 unchanged_vector_fp_csrs=5,restored_csrs_and_status_alias=21,main=2,harness_flags=3)
    require(sum(parts.values())==audit.CHECKS,'independent check-count derivation differs')
    save(out/'config-audit.json',dict(status='PASS',pmp_regions=0,asid_width=16,rvh=0,xlen=64,
        private_tlb_entries=16,use_shared_tlb=False,translation='Sv39',pmp_csr_accesses=0,
        dts_log=str(out/'spike-config.log'),dts_sha256=sha(out/'spike-config.log'),count_parts=parts,
        frozen_rtl=pins(ROOT/p for p in PATH_SOURCES),spike_source_review=pins(spike_sources),
        semantics='Leaf A/D set, nonleaf V-only; no PMP CSR probes and no overflush-retention oracle.'))
    command = audit.expected_command(str(spike),str(spike_elf))
    run = b.run(command,'case.spike',timeout=30)
    audit.check_log(run.stdout.decode(),str(SOURCE))
    trace = audit.trace_check(run.stderr.decode(),spike_info['metadata'])
    save(out/'execution-proof.json',dict(status='PASS',dut=dut,spike=spike_info,spike_tool=str(spike),
        trace=trace,checks=audit.CHECKS,retired_limit=audit.MAX_RETIRED,
        vcs_timeout_s=300,vcs_launched=False,measured_gain=None,coverage_gain_required=False))
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and str(Path(m.__file__).resolve()).startswith(str(ROOT/'verification'))])
    for hashes in (b.sources,b.tools,b.link_inputs,protected): verify(hashes)
    save(out/'source_hashes.json',b.sources); save(out/'tool_hashes.json',b.tools)
    save(out/'link-inputs.json',b.link_inputs)
    if args.development:
        print('DEVELOPMENT ONLY: Spike PASS',trace,flush=True)
        return
    row = dict(test=audit.NAME,status='PASS',returncode=0,command=command,seconds=b.commands[-1]['seconds'],
        binary=str(elf),binary_sha256=sha(elf),spike_binary=str(spike_elf),spike_sha256=sha(spike_elf),
        spike_tool_sha256=sha(spike),source_hashes=b.sources,tool_hashes=b.tools,link_inputs=b.link_inputs,
        log=str(out/'case.spike.log'),log_sha256=sha(out/'case.spike.log'),
        trace_log=str(out/'case.spike.stderr.log'),trace_sha256=sha(out/'case.spike.stderr.log'),
        checks=audit.CHECKS,retired=trace['retired'],vcs_launched=False,measured_coverage_gain=None)
    save(out/'spike_results.json',[row])
    artifacts = pins(p for p in out.iterdir() if p.is_file())
    save(out/'artifact_hashes.json',artifacts)
    item = dict(name=audit.NAME,binary=str(elf),binary_sha256=sha(elf),sources=sorted(b.sources),
        source_hashes=b.sources,evidence=sorted([*artifacts,str(out/'artifact_hashes.json')]),
        source_audit='Independent Python/C full-page oracle, all 1536 PTE and 1024 data words plus 16 guards. '
            'Spike commit proof of 64 distinct superpage hops, 74 exact selective SFENCE operands, '
            'A/B/A remap values, five complete S trap records, scalar ABI and CSR restoration. '
            'Zero PMP entries and no PMP CSR access; <=45000 retired; no retention or measured-gain oracle.',
        targets=sorted({p['scope'] for p in baseline['targets']}),timeout_s=300,
        rationale='645 native missing TLB selective-flush lines and per-slot superpage conditions. '
            'Predicted coverage only; speculative fill may reduce gains and is not functional PASS criteria.',
        precheck=dict(format='rvv-spike-v1',record=str(out/'spike_results.json'),log=row['log']))
    draft = out/'selection.checked-draft.json'
    save(draft,dict(status='CHECKED_DRAFT_SPIKE_ONLY_NOT_SUBMITTED',baseline=str(BASE),cases=[item],
                    vcs_launched=False,waivers_applied=False,measured_candidate_gain=None))
    proof = evidence.Evidence(); proof.pin(draft)
    for hashes in (b.tools,b.link_inputs,protected,artifacts): proof.hashes(hashes)
    result = evidence.precheck(read(draft)['cases'][0],proof)
    save(out/'checked-precheck.json',dict(status='PASS',result=result,checked_files=proof.files,
        entrypoint='coverage_evidence.precheck',read_only_validation=True,vcs_launched=False))
    save(out/'draft.sha256.json',pins([draft,out/'checked-precheck.json',out/'artifact_hashes.json']))
    adapter.install_hooks(); outer = evidence.Evidence()
    sealed = evidence.precheck(read(draft)['cases'][0],outer)
    require(sealed==result,'sealed result differs')
    save(out/'sealed-replay.json',dict(status='PASS',result=sealed,checked_files=outer.files,
        exact_original_checked_files=len(proof.files),outer_pins=len(outer.files),
        checked_script_unchanged=True,vcs_launched=False))
    verify(protected)
    print('PASS: Spike %d checks, %d retired; five ecalls; all 2576 region words checked' %
          (audit.CHECKS,trace['retired']),flush=True)
    print('PASS: %d native / %d sealed outer pins; no VCS'%(len(proof.files),len(outer.files)),flush=True)
    print(draft,flush=True)


if __name__=='__main__': main()
