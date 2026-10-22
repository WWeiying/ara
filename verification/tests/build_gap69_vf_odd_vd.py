#!/usr/bin/env python3
"""Build/precheck gap69 with install/riscv-llvm and real Spike. Never start VCS."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
LEGACY = ROOT/'verification/tests/build_gap38_i8_f16_lane3.py'
spec = importlib.util.spec_from_file_location('gap69_readonly_build_helpers', LEGACY)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
sha, save, read, pins, verify, require = (getattr(helpers,n) for n in
    ('sha','save','read','pins','verify','require'))
sys.path.insert(0, str(ROOT/'verification/coverage'))
import audit_gap69_vf as audit
import coverage_evidence as evidence

NAME = audit.NAME.split(':')[1]
SOURCE = ROOT/'apps/riscv-tests/isa/rv64uv'/(NAME+'.c')
UNIT = ROOT/'verification/tests/test_gap69_vf.py'
WRAPPER = ROOT/'verification/coverage/run_gap69_vf_checked_extension.py'


def baseline_audit(directory):
    checkpoint, collection = read(directory/'checkpoint.json'), read(directory/'collection.json')
    require(checkpoint['coverage_status'] == 'COMPLETE' and checkpoint['aggregate_passed'] == 650 and
            collection['status'] == 'PASS' and collection['passed'] == 650, 'need completed650 baseline')
    verify(collection['reports'])
    bits, rows = read(directory/'combined-bits.json'), read(directory/'all-passed-outcomes.json')
    inputs = (directory/'combined-dve/inputs.txt').read_text().splitlines()
    require(len(rows) == 650 and bits['tests'] == inputs[1:] == [r['vdb'] for r in rows] and
            all(r['status'] == 'PASS' and r['passed_only'] and r['vdb_valid'] for r in rows),
            'baseline membership is not exact passing650')
    require(not any(r['name'] in (NAME,audit.NAME) for r in rows), 'duplicate case')
    design = Path(inputs[0])
    design_pins = {str(design/'snps/coverage/db'/p): h for p,h in bits['design'].items()}
    verify(design_pins)
    targets = audit.target_shapes(design,bits)
    checked = pins([directory/'checkpoint.json',directory/'collection.json'])
    checked.update(collection['reports']); checked.update(design_pins)
    rtl = ROOT/'hardware/src/ara_dispatcher.sv'
    lines = rtl.read_text().splitlines()
    require('LMUL_2' in lines[4057] and 'illegal_insn = ara_req.use_vd' in lines[4058],
            'frozen dispatcher target source differs')
    checked.update(pins([rtl]))
    return dict(status='PASS',baseline=str(directory),passed=650,coverage_status='COMPLETE',
                targets=targets,checked_files=checked,measured_gain=None,
                historical_baseline_full_reaudit=False,waivers_applied=False)


def metadata(b, elf, label):
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],label+'.disassembly')
    result = b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',
                   '--program-headers',elf],label+'.metadata')
    return dict(elf=str(elf),elf_sha256=sha(elf),metadata=audit.metadata(json.loads(result.stdout)[0],elf.read_bytes()))


def host_oracle(b):
    obj = b.compile(SOURCE,'host-oracle',['-DGAP69_ORACLE_HOST=1'],host=True)
    exe = b.out/'host-oracle'
    b.link([b.host,obj,'-o',exe],'host-oracle.link')
    result = b.run([exe],'host-oracle.results',timeout=30)
    lines = result.stdout.decode().splitlines()
    expected = ['H %d %d %04x %04x'%(r,i,audit.expected_half(r,i),audit.expected_half(r,i,True))
                for r in audit.REGS for i in range(64)]
    negative = 2*(9*64+16)+6+9
    require(lines == expected+['NEGATIVE %d PASS'%negative], 'C/independent IEEE half or negative oracle differs')
    save(b.out/'oracle-check.json',dict(status='PASS',halfword_pairs=len(expected),negative_mutations=negative,
        reference='Independent Python struct IEEE binary16 packing of real numerical inputs and products',
        negatives='Same C checker: every register halfword and guard in both phases; all CSR/trap fields',
        binary=str(exe),binary_sha256=sha(exe),log_sha256=sha(b.out/'host-oracle.results.log')))


def bind_toolchain(b, spike):
    for name in ('cc1','as','ld'):
        result = b.run([b.host,'-print-prog-name='+name],'host-'+name+'.path')
        path = result.stdout.decode().strip()
        resolved = Path(path if Path(path).is_absolute() else shutil.which(path)).resolve(strict=True)
        b.tools.update(pins([resolved]))
    ldd = Path(shutil.which('ldd')).resolve(strict=True)
    b.tools.update(pins([ldd]))
    libraries = {}
    for i,path in enumerate(sorted(b.tools)):
        if Path(path) == ldd: continue
        # Executables used above are ELF binaries; dependency listing is evidence only.
        with Path(path).open('rb') as stream:
            magic = stream.read(4)
        if magic != b'\x7fELF': continue
        result = b.run([ldd,path],'tool-%02d.dependencies'%i)
        for match in re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(',result.stdout.decode(),re.M):
            resolved = Path(match).resolve(strict=True)
            libraries[str(resolved)] = sha(resolved)
    b.tools.update(libraries)
    spike_root = spike.resolve().parents[1]
    b.bind_sources([spike_root/'riscv/insns/vfmul_vf.h',spike_root/'riscv/v_ext_macros.h',
                    spike_root/'riscv/decode.h'])
    save(b.out/'toolchain-binding.json',dict(status='PASS',tools=b.tools,
        compiler=str(b.cc),linker=str(b.llvm/'bin/ld.lld'),spike=str(spike),
        reference_source_scope='Read-only Spike alignment/FP instruction semantics; tool binary independently pinned',
        method='Compile depfiles + --trace link inputs + all invoked compiler/linker utilities and ldd libraries'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--baseline',type=Path,default=ROOT/'verification/out/gap67-current-20261004-01')
    args = parser.parse_args()
    out = args.output.resolve()
    require(ROOT == Path('/home/wangwy/openproject/ara_dsa_signoff_integration'), 'wrong worktree')
    require(out.parent == ROOT/'verification/out' and out.name.startswith('gap69-vf-preflight-') and
            not out.exists(), 'require a new independent gap69-vf-preflight-* output directory')
    baseline = baseline_audit(args.baseline.resolve())
    plan = ROOT/'verification/out/repaired-aligned-600-20260930-01/plan.json'
    oracle = next(c for c in read(plan)['cases'] if c.get('spike'))
    spike = Path(oracle['spike'])
    require(sha(spike) == oracle['spike_sha256'], 'pinned Spike differs')
    protected = dict(baseline['checked_files'])
    protected.update(pins([LEGACY,plan,SOURCE.with_name('vgap35_common.h'),Path(evidence.__file__),
                          ROOT/'verification/coverage/run_checked_extension.py']))
    # Freeze all RTL sources, not just the particular legality check.
    protected.update(pins(p for d in ('src','include','tb') for p in (ROOT/'hardware'/d).rglob('*')
                          if p.suffix in ('.sv','.svh')))
    out.mkdir()
    save(out/'baseline-targets.json',baseline); save(out/'protected-inputs.json',protected)
    b = helpers.Build(out)
    b.sources = pins([SCRIPT,SOURCE,LEGACY,UNIT,WRAPPER,Path(audit.__file__)])
    b.tools.update(pins([spike,ROOT/'verification/tools/soc-venv/bin/python']))
    print('COMPLETE650 target shapes matched; gap69 only; no RTL/checker edits or VCS',flush=True)
    b.run([sys.executable,'-B',UNIT,'-v'],'unit-tests')
    for tool,label in ((b.cc,'clang'),(b.llvm/'bin/ld.lld','lld'),(b.host,'host-cc')):
        b.run([tool,'--version'],label+'.version')
    bind_toolchain(b,spike)
    host_oracle(b)
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
    command = list(map(str,[spike,'--isa=rv64gcv_zfh_zvfh_zvl1024b','-l','--log-commits',spike_elf]))
    run = b.run(command,'case.spike',timeout=30)
    seconds = b.commands[-1]['seconds']
    audit.check_log(run.stdout.decode(),str(SOURCE))
    trace = audit.trace_check(run.stderr.decode(),spike_info['metadata'])
    save(out/'execution-proof.json',dict(status='PASS',dut=dut,spike=spike_info,trace=trace,
        checks=audit.CHECKS,check_parts=audit.CHECK_PARTS,vcs_timeout_s=300,vcs_launched=False,
        scope='Spike-only. Same C body, DUT M-mode rvtest_init then U-mode PASS; Spike M-mode main.',
        measured_gain=None,vcs_runtime_measured=False))
    save(out/'runtime-contract.json',dict(schema='gap69-vf-stdout-vector-trap-v1',
        adapter=str(WRAPPER),install='install_hooks(): evidence.precheck and Evidence.baseline_row only',
        checked_script_mutated=False,parent_worker_entrypoint='runtime_proof(output, plan, row)',
        required_plusarg='+VECTOR_TRACE=<artifact>/work/vector_trace.csv',
        required_bound_files=['<artifact>/work/run.vcs.log','<artifact>/work/vector_trace.csv',
                              '<artifact>/commit_trace.csv','<artifact>/input.elf'],
        stdout_checks='1815 selfchecks, unique absolute PASS, tohost0, finish, zero UVM errors/fatals, balanced contract and one exception',
        trace_checks='Exact illegal operand decoder; no backend allocation/write; legal v8 VL8 EEW16; '
                     'full VRF byte oracle and source/neighbors/tail; trapped cause2/EPC/tval and immediate CSR stores',
        vcs_timeout_s=300,vcs_launched=False))
    b.run([sys.executable,'-B',UNIT,'--preflight',out,'-v'],'real-trace-unit-tests',timeout=120)
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and str(Path(m.__file__).resolve()).startswith(str(ROOT/'verification'))])
    for hashes in (b.sources,b.tools,b.link_inputs,protected): verify(hashes)
    save(out/'source_hashes.json',b.sources); save(out/'tool_hashes.json',b.tools)
    save(out/'link-inputs.json',b.link_inputs)
    row = dict(test=audit.NAME,status='PASS',returncode=0,command=command,seconds=seconds,
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
        source_audit='1815 C selfchecks plus independent full Spike trace oracle: exact raw vfmul.vf '
            'v9,v16,f0 illegal trap cause2/EPC/tval, no retirement, complete unchanged v7-v11/v15-v18; '
            'legal v8 recovery, eight exact halves, 120 group tail halves, full source/neighbors, '
            'three guarded buffers, immediate CSRs and boxed f0. EEW16 setup and capture throughout. '
            'Compiled C checker also rejects 1199 independent single-field mutations.',
        targets=[audit.SCOPE],timeout_s=300,
        rationale='dispatcher_vf_m2_odd_vd_reject: completed650 Block1137/raw1145 and '
            'Branch25(659)/raw470 zero. e16/m2 VL8 with aligned v16 and boxed f0 isolates vd alignment. '
            'Predicted +1 line/+1 branch only; no measured coverage claim. Parent may compose into651.',
        precheck=dict(format='rvv-spike-v1',record=str(out/'spike_results.json'),log=row['log']))
    draft = out/'selection.checked-draft.json'
    save(draft,dict(status='CHECKED_DRAFT_SPIKE_ONLY_NOT_SUBMITTED',baseline=baseline['baseline'],
        baseline_bits=str(Path(baseline['baseline'])/'combined-bits.json'),cases=[item],
        vcs_launched=False,waivers_applied=False,measured_candidate_gain=None))
    proof = evidence.Evidence(); proof.pin(draft)
    for hashes in (b.tools,b.link_inputs,protected,artifacts): proof.hashes(hashes)
    result = evidence.precheck(read(draft)['cases'][0],proof)
    save(out/'checked-precheck.json',dict(status='PASS',result=result,checked_files=proof.files,
        entrypoint='coverage_evidence.precheck',read_only_validation=True,vcs_launched=False))
    save(out/'draft.sha256.json',pins([draft,out/'checked-precheck.json',out/'artifact_hashes.json']))
    import run_gap69_vf_checked_extension as wrapper
    wrapper.install_hooks()
    outer = evidence.Evidence()
    sealed = evidence.precheck(read(draft)['cases'][0],outer)
    require(sealed == result,'sealed result differs')
    save(out/'sealed-replay.json',dict(status='PASS',result=sealed,checked_files=outer.files,
        checked_script_unchanged=True,vcs_launched=False))
    verify(protected)
    print('PASS: Spike %d checks, %d retired; one exact illegal word and legal recovery'%(audit.CHECKS,trace['retired']),flush=True)
    print('PASS: standard rvv-spike-v1 and sealed read-only replay; no VCS',flush=True)
    print(draft,flush=True)


if __name__ == '__main__': main()
