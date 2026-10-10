#!/usr/bin/env python3
"""New gap70 build, genuine bounded Spike, sealed read-only draft; no VCS."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
LEGACY = ROOT/'verification/tests/build_gap38_i8_f16_lane3.py'
spec = importlib.util.spec_from_file_location('gap70_immutable_build',LEGACY)
helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
sha,save,read,pins,verify,require = (getattr(helpers,n) for n in ('sha','save','read','pins','verify','require'))
sys.path.insert(0,str(ROOT/'verification/coverage'))
import audit_gap70_indexed as audit
import coverage_evidence as evidence
import run_gap70_indexed_checked_extension as adapter

NAME = audit.NAME.split(':')[1]
SOURCE = ROOT/'apps/riscv-tests/isa/rv64uv'/(NAME+'.c')
UNIT = ROOT/'verification/tests/test_gap70_indexed.py'
BASE650 = ROOT/'verification/out/gap67-current-20261004-01'
BASE = ROOT/'verification/out/gap65-late-fault-runtime-20261004-02'
RECOVERY = ROOT/'verification/out/gap65-report-only-recovery-20261005-01/reports'
INVENTORY = ROOT/'verification/out/gap42-rvv-reachable-analysis-20261004-01/inventory.json'
FROZEN = ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
PATH_SOURCES = ('hardware/src/ara_soc.sv','hardware/src/ara_system.sv','hardware/src/ara.sv',
    'hardware/src/ara_dispatcher.sv','hardware/src/ara_sequencer.sv','hardware/src/vlsu/addrgen.sv',
    'hardware/src/vlsu/vlsu.sv','hardware/src/vlsu/vldu.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/csr_regfile.sv','hardware/deps/cva6/core/pmp/src/pmp.sv',
    'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv','hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv')


def baseline_audit():
    completion = read(RECOVERY/'completion.json')
    checkpoint = read(RECOVERY/'checkpoint.json')
    require(completion['status']=='PASS' and completion['aggregate_passed']==651 and
            completion['source_runtime']==str(BASE) and completion['simulations_started'] is False and
            checkpoint['coverage_status']=='COMPLETE' and checkpoint['aggregate_passed']==651,
            'independent report-only COMPLETE651 missing')
    require(checkpoint['completion_sha256']==sha(RECOVERY/'completion.json'), 'recovery completion seal differs')
    checked = pins([RECOVERY/'completion.json',RECOVERY/'checkpoint.json',INVENTORY,FROZEN])
    frozen = read(FROZEN)
    rtl = {str(ROOT/p):frozen[str(ROOT/p)] for p in PATH_SOURCES}
    verify(rtl); checked.update(rtl)
    require('cfg.NrPMPEntries          = 0;' in (ROOT/PATH_SOURCES[0]).read_text(), 'PMP0 override missing')
    c = read(BASE/'collection.json')
    require(c['status']=='PASS' and c['passed']==651 and c['baseline_passed']==650 and
            c['new_passed']==1 and c['cross_image_reuse'] is False, 'wrong recovered collection')
    for directory in (BASE650,BASE):
        for n in ('collection.json','combined-bits.json','all-passed-outcomes.json','combined-dve/inputs.txt'):
            p = directory/n
            require(str(p) in completion['files'] and sha(p)==completion['files'][str(p)], 'recovered evidence drift')
            checked[str(p)] = sha(p)
    rows650,rows = read(BASE650/'all-passed-outcomes.json'),read(BASE/'all-passed-outcomes.json')
    require(len(rows650)==650 and len(rows)==651 and rows[:650]==rows650 and
            all(r['status']=='PASS' and r['passed_only'] and r['vdb_valid'] for r in rows), 'wrong membership')
    bits650,bits = read(BASE650/'combined-bits.json'),read(BASE/'combined-bits.json')
    require(bits['tests']==(BASE/'combined-dve/inputs.txt').read_text().splitlines()[1:]==
            [r['vdb'] for r in rows], 'bitmap/ledger membership differs')
    require(not any(r['name'] in (NAME,audit.NAME) for r in rows), 'duplicate gap70')
    scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen'
    inventory = read(INVENTORY)['instances'][scope]['metrics']
    targets = []
    for metric,index in (('line',102),('branch',4),('branch',56)):
        candidates = [p for p in inventory[metric]['missing'] if p['raw_index']==index]
        require(len(candidates)==1, 'ambiguous native mapping')
        target = candidates[0]
        if metric=='line': require(target['id']=='95' and target['line_num']=='521', 'wrong block')
        else:
            spec,vector = ('0','31') if index==4 else ('9','43')
            require(target['spec_id']==spec and target['vector']['id']==vector and
                    index==target['spec_base']+target['spec_width']-1-int(vector), 'wrong branch reversal')
        for b in (bits650,bits):
            row = b['metrics'][metric][scope]
            require(row['width']==inventory[metric]['width'] and
                    format(int(row['bits'],16),'0%db'%row['width'])[index]=='0', 'target not stillzero650/651')
        targets.append(dict(scope=scope,metric=metric,raw_index=index,native=target))
    return dict(status='PASS',baseline=str(BASE),passed=651,coverage_status='COMPLETE_REPORT_ONLY_RECOVERY',
        recovery=str(RECOVERY/'completion.json'),targets=targets,checked_files=checked,
        measured_gain=None,waivers_applied=False,
        hypothesis='First V=0 leaf faults before any element; len=VL8*4, vstart=0, '
            'mmu_exception_i.valid -> exception queue -> IDX_OP_END mmu_exception_q.valid -> '
            'load drain/completion -> dispatcher/CVA6 trap. Original EPC retry becomes legal after repair.',
        discriminating_signals=['mmu_exception_i.valid/cause/tval','axi_addrgen_q.len',
            'idx_final_vaddr_q','axi_ar_valid_o','axi_aw_valid_o','axi_addrgen_queue.is_exception',
            'state_q==ADDRGEN_IDX_OP_END','mmu_exception_q.valid','addrgen_ack_o',
            'addrgen_exception_vstart_o','ara_resp_o.exception','csr_vstart_q'])


def metadata(b,elf,label):
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],label+'.disassembly')
    r = b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',
               '--program-headers',elf],label+'.metadata')
    return dict(elf=str(elf),elf_sha256=sha(elf),metadata=audit.metadata(json.loads(r.stdout)[0],elf.read_bytes()))


def host_oracle(b):
    obj = b.compile(SOURCE,'host-oracle',['-DGAP70_ORACLE_HOST=1'],host=True)
    exe = b.out/'host-oracle'; b.link([b.host,obj,'-o',exe],'host-oracle.link')
    r = b.run([exe],'host-oracle.results',timeout=30)
    seed,result = audit.expected_vectors()
    expected = ['R %d %d %08x %08x'%(r,w,seed[r][w],result[r][w]) for r in range(6) for w in range(32)]
    expected += ['D %d %08x'%(w,0x91700000 ^ w) for w in range(1024)]
    expected += ['P %d %016x'%(w,((0x91700000 ^ (2*w+1)) << 32) | (0x91700000 ^ (2*w)))
                 for w in range(512)]
    require(r.stdout.decode().splitlines()==expected,'independent Python/C whole-region oracle differs')
    save(b.out/'oracle-check.json',dict(status='PASS',rows=len(expected),register_words=192,data_words=1024,
        reference='Independent Python address expansion vs compiled shared C expectation functions',
        binary=str(exe),binary_sha256=sha(exe)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args(); out = args.output.resolve()
    require(ROOT==Path('/home/wangwy/openproject/ara_dsa_signoff_integration'), 'wrong worktree')
    require(out.parent==ROOT/'verification/out' and out.name.startswith('gap70-indexed-preflight-') and
            not out.exists(), 'need new gap70 output directory')
    baseline = baseline_audit()
    plan_path = ROOT/'verification/out/repaired-aligned-600-20260930-01/plan.json'
    old = next(c for c in read(plan_path)['cases'] if c.get('spike'))
    spike = Path(old['spike']); require(sha(spike)==old['spike_sha256'],'pinned Spike changed')
    spike_sources = [spike.parent.parent/p for p in ('riscv/mmu.cc','riscv/mmu.h','riscv/csrs.cc','riscv/execute.cc',
        'riscv/processor.cc','riscv/insns/vloxei32_v.h','riscv/insns/sfence_vma.h','spike_main/spike.cc')]
    protected = dict(baseline['checked_files'])
    protected.update(pins([LEGACY,plan_path,SOURCE.with_name('vgap35_common.h'),Path(evidence.__file__),
        ROOT/'verification/coverage/run_checked_extension.py',*spike_sources,
        ROOT/'apps/riscv-tests/isa/rv64uv/vgap47_sv39_indexed_pmp0.c',
        ROOT/'verification/tests/build_gap47_sv39_indexed_pmp0.py',
        ROOT/'verification/tests/build_gap52_system.py',ROOT/'verification/coverage/audit_gap52_system.py']))
    out.mkdir(); save(out/'baseline-targets.json',baseline); save(out/'protected-inputs.json',protected)
    b = helpers.Build(out)
    # Use the real GCC driver, not the site's cc/ccache wrapper.
    b.host = Path('/usr/bin/gcc').resolve()
    b.sources = pins([SCRIPT,SOURCE,UNIT,LEGACY,adapter.SCRIPT,Path(audit.__file__)])
    b.tools.update(pins([spike,ROOT/'verification/tools/soc-venv/bin/python',b.host,
                        Path('/usr/bin/as').resolve(),Path('/usr/bin/ld').resolve()]))
    for name in ('cc1','collect2'):
        r = b.run([b.host,'-print-prog-name='+name],'host-tool-'+name)
        p = Path(r.stdout.decode().strip()).resolve(strict=True)
        b.tools.update(pins([p]))
    save(out/'source-snapshot.json',dict(path=str(SOURCE),sha256=sha(SOURCE),text=SOURCE.read_text()))
    print('Static native stillzero650/651 verified; build gap70 only',flush=True)
    b.run([sys.executable,'-B',UNIT],'unit-tests'); host_oracle(b)
    objects = [b.compile(b.common/n,'dut-'+n) for n in
               ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects.insert(0,b.compile(SOURCE,'dut-test',['-Wall','-Wextra','-Wno-unused-function']))
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
    require(audit.payload_identity(dut['metadata'])==audit.payload_identity(spike_info['metadata']),
            'DUT/Spike normalized S and handler instruction bytes differ')
    dts = b.run([spike,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                 '--dump-dts',spike_elf],'spike-config')
    audit.validate_pmp_dts(dts.stdout.decode())
    parts = dict(setup=3,trap_count=1,trap_records=24,post_csrs=5,full_vectors=18,vector_guards=6,
        full_data=1,page_guards=2,full_tables=5,restored_csrs=15,main=2,harness=3)
    require(sum(parts.values())==audit.CHECKS,'independent check-count derivation differs')
    save(out/'config-audit.json',dict(status='PASS',pmp_regions=0,translation='Sv39',vl=8,vtype=16,
        dts_log=str(out/'spike-config.log'),dts_sha256=sha(out/'spike-config.log'),count_parts=parts,
        frozen_path_hashes=pins(ROOT/p for p in PATH_SOURCES),spike_source_review=pins(spike_sources),
        semantics='S mode; identity code superpage; single aligned data leaf initially exactly zero; '
            'repair RWAD/V, sfence.vma data-VA/zero ASID, unchanged original EPC; no PMP CSR accesses.'))
    print('ELF/static/oracle/unit audits passed; one bounded genuine Spike execution',flush=True)
    command = audit.expected_command(str(spike),str(spike_elf))
    run = b.run(command,'case.spike',timeout=30)
    audit.check_log(run.stdout.decode(),str(SOURCE))
    trace = audit.trace_check(run.stderr.decode(),spike_info['metadata'])
    save(out/'execution-proof.json',dict(status='PASS',dut=dut,spike=spike_info,spike_tool=str(spike),
        trace=trace,checks=audit.CHECKS,retired_limit=35000,vcs_timeout_s=300,vcs_launched=False,
        vcs_runtime_measured=False,measured_gain=None))
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values()) if getattr(m,'__file__',None)
        and str(Path(m.__file__).resolve()).startswith(str(ROOT/'verification'))])
    for hashes in (b.sources,b.tools,b.link_inputs,protected): verify(hashes)
    save(out/'source_hashes.json',b.sources); save(out/'tool_hashes.json',b.tools)
    save(out/'link-inputs.json',b.link_inputs)
    row = dict(test=audit.NAME,status='PASS',returncode=0,command=command,seconds=b.commands[-1]['seconds'],
        binary=str(elf),binary_sha256=sha(elf),spike_binary=str(spike_elf),spike_sha256=sha(spike_elf),
        spike_tool_sha256=sha(spike),source_hashes=b.sources,tool_hashes=b.tools,link_inputs=b.link_inputs,
        log=str(out/'case.spike.log'),log_sha256=sha(out/'case.spike.log'),
        trace_log=str(out/'case.spike.stderr.log'),trace_sha256=sha(out/'case.spike.stderr.log'),
        checks=audit.CHECKS,retired=trace['retired'],vcs_launched=False,measured_coverage_gain=None)
    save(out/'spike_results.json',[row])
    artifacts = pins(p for p in out.iterdir() if p.is_file()); save(out/'artifact_hashes.json',artifacts)
    item = dict(name=audit.NAME,binary=str(elf),binary_sha256=sha(elf),sources=sorted(b.sources),
        source_hashes=b.sources,evidence=sorted([*artifacts,str(out/'artifact_hashes.json')]),
        source_audit='Python/C independent full integer/address oracle; exact cause13/EPC/VA/vstart0 '
            'and S ecall records; pre-repair snapshots of v7-v9/v15-v17; full recovered destination, '
            '24 tail and 32 source-index words, all 1024 data words and 1536 PTEs, 128 guard words; '
            '15 CSR restores; precise younger store order; raw opcodes and normalized S/handler identity.',
        targets=sorted({t['scope'] for t in baseline['targets']}),timeout_s=300,
        rationale='Native addrgen Block95/raw102, Branch0(31)/raw4 and Branch9(43)/raw56 stillzero650/651. '
            'Predicted indexed first-element Sv39 fault gain only; no measured RTL gain or runtime claim.',
        precheck=dict(format='rvv-spike-v1',record=str(out/'spike_results.json'),log=row['log']))
    draft = out/'selection.checked-draft.json'
    save(draft,dict(status='CHECKED_DRAFT_SPIKE_ONLY_NOT_SUBMITTED',baseline=str(BASE),cases=[item],
                    vcs_launched=False,waivers_applied=False,measured_candidate_gain=None))
    proof = evidence.Evidence(); proof.pin(draft)
    for hashes in (b.tools,b.link_inputs,protected,artifacts): proof.hashes(hashes)
    result = evidence.precheck(item,proof)
    save(out/'checked-precheck.json',dict(status='PASS',result=result,checked_files=proof.files,
        entrypoint='coverage_evidence.precheck',read_only_validation=True,vcs_launched=False))
    save(out/'draft.sha256.json',pins([draft,out/'checked-precheck.json',out/'artifact_hashes.json']))
    original_script = adapter.checked.SCRIPT; adapter.install_hooks(); outer = evidence.Evidence()
    sealed = evidence.precheck(item,outer)
    require(sealed==result and adapter.checked.SCRIPT==original_script,'hook changed result/checked runner')
    save(out/'sealed-replay.json',dict(status='PASS',result=sealed,checked_files=outer.files,
        original_pins=len(proof.files),outer_pins=len(outer.files),checked_script_unchanged=True,vcs_launched=False))
    verify(protected)
    print('PASS: genuine Spike %d checks, %d retired; sealed draft; no VCS' % (audit.CHECKS,trace['retired']),flush=True)
    print(draft,flush=True)


if __name__=='__main__': main()
