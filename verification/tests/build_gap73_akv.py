#!/usr/bin/env python3
"""New gap73 only: LLVM DUT ELF, actual host reference, sealed checked draft; no VCS/Spike."""
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
spec = importlib.util.spec_from_file_location('gap73_readonly_build_helpers',LEGACY)
helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
sha,save,read,pins,verify,require = (getattr(helpers,n) for n in ('sha','save','read','pins','verify','require'))
sys.path.insert(0,str(ROOT/'verification/coverage'))
import audit_gap73_akv as audit
import coverage_evidence as evidence
import run_gap73_akv_checked_extension as wrapper

SOURCE = ROOT/'apps'/audit.NAME/'main.c'
UNIT = ROOT/'verification/tests/test_gap73_akv.py'
WRAPPER = Path(wrapper.__file__).resolve()


def bind_toolchain(b):
    for n in ('cc1','as','ld'):
        result = b.run([b.host,'-print-prog-name='+n],'host-'+n+'.path')
        path = result.stdout.decode().strip()
        path = Path(path if Path(path).is_absolute() else shutil.which(path)).resolve(strict=True)
        b.tools.update(pins([path]))
    ldd = Path(shutil.which('ldd')).resolve(strict=True); b.tools.update(pins([ldd]))
    libraries = {}
    for i,path in enumerate(sorted(b.tools)):
        if Path(path)==ldd: continue
        with Path(path).open('rb') as stream: magic = stream.read(4)
        if magic!=b'\x7fELF': continue
        result = b.run([ldd,path],'tool-%02d.dependencies'%i)
        for match in re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(',result.stdout.decode(),re.M):
            resolved = Path(match).resolve(strict=True); libraries[str(resolved)] = sha(resolved)
    b.tools.update(libraries)
    save(b.out/'toolchain-binding.json',dict(status='PASS',tools=b.tools,compiler=str(b.cc),
        linker=str(b.llvm/'bin/ld.lld'),method='Compile depfiles, --trace links, compiler utilities and ldd libraries',
        spike_invoked=False,vcs_launched=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--vcs-timeout',type=int,choices=(300,1800),default=300)
    parser.add_argument('--inventory',type=Path,default=ROOT/'verification/out/closure90-zero-inventory-654-20261005-01/inventory.json')
    args = parser.parse_args(); out = args.output.resolve()
    require(ROOT==Path('/home/wangwy/openproject/ara_dsa_signoff_integration'),'wrong worktree')
    require(out.parent==ROOT/'verification/out' and out.name.startswith('gap73-akv-preflight-') and
            not out.exists(),'require new gap73-akv-preflight-* directory')
    native_proof = evidence.Evidence(); targets = audit.native_targets(native_proof,args.inventory)
    protected = dict(native_proof.files)
    protected.update(pins([LEGACY,Path(evidence.__file__),ROOT/'verification/coverage/run_checked_extension.py',
                           ROOT/'apps/common/akv_abi.h',ROOT/'software/akv/include/akv/akv_abi.h']))
    protected.update(pins(p for d in ('src','include','tb') for p in (ROOT/'hardware'/d).rglob('*')
                          if p.suffix in ('.sv','.svh')))
    out.mkdir(); save(out/'native-targets.json',targets); save(out/'protected-inputs.json',protected)
    b = helpers.Build(out)
    b.sources = pins([SCRIPT,SOURCE,LEGACY,UNIT,WRAPPER,Path(audit.__file__)])
    b.tools.update(pins([ROOT/'verification/tools/soc-venv/bin/python']))
    print('Latest654 zero C47: six statically reachable v1 one-hot candidates; diagnostic only',flush=True)
    for tool,label in ((b.cc,'clang'),(b.llvm/'bin/ld.lld','lld'),(b.host,'host-cc')):
        b.run([tool,'--version'],label+'.version')
    bind_toolchain(b)
    host_obj = b.compile(SOURCE,'host',['-DGAP73_HOST=1','-I'+str(b.common),
        '-Wno-unused-function','-Wno-unused-const-variable'],host=True)
    host = out/'host'; b.link([b.host,host_obj,'-o',host],'host.link')
    run = b.run([host],'host-results',timeout=30)
    require(run.stdout.decode()=='PASSED: '+audit.NAME+' checks=%d errors=0\n'%audit.HOST_CHECKS,
            'actual host reference selfchecks differ')
    oracle = b.run([host,'--oracle'],'host-oracle',timeout=30)
    host_proof = audit.host_oracle(oracle.stdout.decode())
    objects = [b.compile(b.common/n,'dut-'+n) for n in
               ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects.insert(0,b.compile(SOURCE,'dut-test',['-Wall','-Wextra','-Werror','-Wno-unused-function']))
    elf = out/(audit.NAME+'.elf'); b.bind_sources([b.common/'link.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
            '-Wl,-Map='+str(out/'dut.map'),'-T'+str(b.common/'link.ld'),*objects,'-lm',
            '-L'+str(b.llvm/'lib/generic'),'-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    fit = ROOT/'verification/coverage/check_elf_fit.py'; b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',elf,'--ram-bytes','0x200000',
           '--output',out/'elf-fit.json'],'elf-fit')
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],'dut.disassembly')
    b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',
           '--program-headers',elf],'dut.metadata')
    info = audit.elf_audit(elf.read_bytes())
    save(out/'execution-proof.json',dict(status='HOST_PASS_ELF_STATIC_ONLY',host=host_proof,elf=info,
        host_checks=audit.HOST_CHECKS,dut_checks=audit.DUT_CHECKS,vcs_timeout_s=args.vcs_timeout,vcs_launched=False,
        custom_execution='PENDING_VCS',spike_custom_execution=False,measured_coverage_gain=None))
    save(out/'runtime-contract.json',dict(schema=audit.SCHEMA,name=audit.NAME,adapter=str(WRAPPER),
        api='NAME/CASE_NAMES and runtime_proof(output,plan,row,proof)',
        install='install_hooks(): evidence.precheck and Evidence.baseline_row only; gap65 installs first',
        checked_script_mutated=False,custom_execution_prechecked=False,
        required_plusargs=['+AKV_PERF','+VECTOR_TRACE=vector_trace.csv'],simulator_cwd='<artifact>/work',
        required_bound_files=['<artifact>/work/run.vcs.log','<artifact>/work/vector_trace.csv',
            '<artifact>/commit_trace.csv','<artifact>/input.elf','<artifact>/work/coverage.command.json'],
        actual_custom_checks=['11 exact v1 raw instructions and distinct ELF PCs',
            '6 distinct descriptor operands, exact 9-predicate one-hot and legal v1 prerequisites',
            '6 cause2/EPC/terminal tval0 records independently reconstructed from commit writes',
            'rejected commands: AR1 descriptor only, read_ranges1/read_bytes64, Q/K/V/replay0',
            'PERF id is backend VID (NOT CVX trans_id), joined to independent vector allocation',
            'no rejected FULL VRF writes or destination reservation; complete EEW16 seed, v7/v9 guards',
            'legal recovery FULL AR4/read448/Q128/KV256 plus Q/K/V LOAD exact 192 finite half results',
            'all initial/result/source/descriptor memory, guards, CSRs independently decoded from actual commit',
            'complete stdout tohost0/finish/UVM totals and balanced actual CVX conservation'],
        raw_mapping_scope='Diagnostic, not native-qualified; no automatic native gain claim',
        vcs_timeout_s=args.vcs_timeout,vcs_launched=False))
    save(out/'cost-analysis.json',dict(status='STATIC_BOUNDED_NOT_RUNTIME_PASS',custom_commands=11,
        illegal_full=6,legal_full=1,recovery_loads=3,release=1,recovery_halfwords=192,
        total_read_ranges=10,total_read_bytes=832,total_ar=10,total_r_beats_128bit=52,
        seeded_registers=33,diff64_word_iterations_per_phase=208,seed_halfword_comparisons_per_phase=192,
        no_delay_or_poll_loops=True,vcs_timeout_s=args.vcs_timeout,vcs_runtime_measured=False))
    b.run([sys.executable,'-B',UNIT,'--preflight',out,'--report',out/'unit-results.json','-v'],
          'unit-tests',timeout=120)
    unit = read(out/'unit-results.json'); require(unit['status']=='PASS' and not unit['skipped'],'unit gate failed/skipped')
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and str(Path(m.__file__).resolve()).startswith(str(ROOT/'verification'))])
    save(out/'source-audit.json',dict(status='STATIC_HOST_ONLY',input_hashes=dict(b.sources),
        source=str(SOURCE),runtime='frozen RVV SoC crt0/printf/string; M-mode trap installation then U-mode main',
        descriptors='6 one-hot mutations from legal descriptor: strides128->129 or bases+1, all other fields identical',
        eew='e16/m1 VL64 seed and capture v7/v8/v9 individually; custom LOAD head64 uses one register',
        trap='strict cause2/EPC/tval0, no rawword alternative; six distinct global ELF sites',
        oracle='actual host ABI/bounded snapshot checks and independent Python IEEE half oracle; custom not executed',
        custom_instruction_execution_prechecked=False,vcs_launched=False))
    for hashes in (b.sources,b.tools,b.link_inputs,protected): verify(hashes)
    save(out/'source_hashes.json',b.sources); save(out/'tool_hashes.json',b.tools); save(out/'link-inputs.json',b.link_inputs)
    record = dict(name=audit.NAME,binary=str(elf),binary_sha256=sha(elf),source_hashes=b.sources,
        sources=sorted(b.sources),host_reference=str(SOURCE),host_log=str(out/'host-results.log'),
        host_result=run.stdout.decode().strip(),custom_instruction_execution_prechecked=False,
        vcs_launched=False,host_binary=str(host),host_binary_sha256=sha(host),returncode=0)
    record_path = out/(audit.NAME+'.precheck.json'); save(record_path,record)
    artifacts = pins(p for p in out.iterdir() if p.is_file()); save(out/'artifact_hashes.json',artifacts)
    item = dict(name=audit.TEST,binary=str(elf),binary_sha256=sha(elf),sources=sorted(b.sources),
        source_hashes=b.sources,evidence=sorted([*artifacts,str(out/'artifact_hashes.json')]),
        source_audit=str(out/'source-audit.json'),targets=[audit.SCOPE],timeout_s=args.vcs_timeout,runtime_contract=audit.SCHEMA,
        rationale='Latest654 C47 one-hot diagnostic raw113-115/119-121 remain zero. V1 FULL isolates each odd '
            'stride/base; descriptor fetch allowed, no payload/VRF writes, exact cause2/EPC/tval0. '
            'Recovery full+Q/K/V finite half rows. Native qualification and measured coverage pending parent VCS/DVE.',
        precheck=dict(format='accel-host-v1',record=str(record_path),log=record['host_log']))
    draft = out/'selection.checked-draft.json'
    save(draft,dict(status='CHECKED_DRAFT_HOST_REFERENCE_ONLY_NOT_SUBMITTED',baseline=targets['baseline'],
        baseline_bits=str(Path(targets['baseline'])/'combined-bits.json'),cases=[item],
        vcs_launched=False,spike_custom_execution=False,waivers_applied=False,measured_candidate_gain=None))
    proof = evidence.Evidence(); proof.pin(draft)
    for hashes in (b.tools,b.link_inputs,protected,artifacts): proof.hashes(hashes)
    result = evidence.precheck(read(draft)['cases'][0],proof)
    save(out/'checked-precheck.json',dict(status='PASS',result=result,checked_files=proof.files,
        entrypoint='coverage_evidence.precheck(accel-host-v1)',custom_instruction_execution_prechecked=False,
        read_only_validation=True,vcs_launched=False))
    save(out/'draft.sha256.json',pins([draft,out/'checked-precheck.json',out/'artifact_hashes.json']))
    wrapper.install_hooks(); outer = evidence.Evidence()
    sealed = evidence.precheck(read(draft)['cases'][0],outer); require(sealed==result,'sealed replay differs')
    save(out/'sealed-replay.json',dict(status='PASS',result=sealed,checked_files=outer.files,
        checked_script_unchanged=True,custom_instruction_execution_prechecked=False,vcs_launched=False))
    verify(protected); verify(b.sources)
    print('PASS: host %d checks; independent192 halves, six one-hot descriptors, %d C negative mutations'%
          (audit.HOST_CHECKS,audit.NEGATIVES),flush=True)
    print('PASS: %d unit fixtures; standard accel-host-v1 plus sealed replay; custom execution PENDING_VCS'%unit['tests_run'],flush=True)
    print(draft,flush=True)


if __name__=='__main__': main()
