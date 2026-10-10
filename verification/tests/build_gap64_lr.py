#!/usr/bin/env python3
"""Build and independently precheck gap64 in new output files. Never launch VCS."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
LEGACY = ROOT / 'verification/tests/build_gap38_i8_f16_lane3.py'
spec = importlib.util.spec_from_file_location('gap64_immutable_build', LEGACY)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
sha, save, read, pins, verify, require = (getattr(helpers,n) for n in
    ('sha','save','read','pins','verify','require'))
sys.path.insert(0, str(ROOT/'verification/coverage'))
import audit_gap64_lr as audit
import coverage_evidence as evidence
import run_gap64_lr_checked_extension as adapter

NAME = audit.NAME.split(':')[1]
SOURCE = ROOT / 'apps/riscv-tests/isa/rv64uv' / (NAME+'.c')
UNIT = ROOT / 'verification/tests/test_gap64_lr.py'
BASE = ROOT / 'verification/out/gap55-current-20261004-03'
HISTORY = ROOT / 'verification/out/gap60-cache-atomic-analysis-20261004-01'


def baseline_audit():
    seal = read(HISTORY/'analysis-validation.json')
    require(seal['status']=='PASS_FINAL_READ_ONLY_ANALYSIS' and seal['baseline_passed']==647,
            'need reviewed completed647 analysis')
    checked = pins([HISTORY/'analysis-validation.json'])
    checked.update(seal['files'])
    inventory = read(HISTORY/'inventory.json')
    checked.update(inventory['pins'])
    overlay = read(HISTORY/'completed647-overlay.json')
    checked.update(overlay['pins'])
    for name in ('semantic-evidence.json','frozen-system-chain.json'):
        obj = read(HISTORY/name)
        checked.update(obj['additional_frozen_source_pins'])
        checked.update(obj.get('spike_source_pins',{}))
    verify(checked)
    checkpoint,collection = read(BASE/'checkpoint.json'),read(BASE/'collection.json')
    require(checkpoint['coverage_status']=='COMPLETE' and checkpoint['aggregate_passed']==647
            and collection['status']=='PASS' and collection['passed']==647, 'baseline not COMPLETE647')
    rows,bits = read(BASE/'all-passed-outcomes.json'),read(BASE/'combined-bits.json')
    require(len(rows)==647 and all(r['status']=='PASS' and r['passed_only'] and r['vdb_valid'] for r in rows),
            'not exact passing aggregate')
    require(not any(r['name'] in (NAME,audit.NAME) for r in rows),'duplicate candidate')
    targets = read(HISTORY/'candidate-points.json')
    for point in targets['points']:
        row = bits['metrics'][point['metric']][point['scope']]
        raw = format(int(row['bits'],16),'0%db'%row['width'])
        require(raw[point['point']['raw_index']]=='0','ordinary LR target no longer missing')
    fsm = targets['fsm']
    row = bits['metrics']['fsm'][fsm['scope']]
    raw = format(int(row['bits'],16),'0%db'%row['width'])
    require(all(raw[p['raw_index']]=='0' for p in fsm['points']),'FSM LR target no longer missing')
    return dict(status='PASS',baseline=str(BASE),passed=647,coverage_status='COMPLETE',
        targets=targets['points'],fsm=fsm,expected_diagnostic_gains=targets['expected_selected_raw_gains'],
        checked_files=checked,no_old_raw_corpus_rehash=True,measured_gain=None,
        coverage_gain_required=False,reservation_claim=False,ordering_claim=False,waivers_applied=False)


def metadata(b,elf,label):
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],label+'.disassembly')
    result = b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',
                    '--program-headers',elf],label+'.metadata')
    info = audit.metadata(json.loads(result.stdout)[0],elf.read_bytes())
    return dict(elf=str(elf),elf_sha256=sha(elf),metadata=info)


def host_oracle(b):
    obj = b.compile(SOURCE,'host-oracle',['-DGAP64_ORACLE_HOST=1'],host=True)
    exe = b.out/'host-oracle'
    b.link([b.host,obj,'-o',exe],'host-oracle.link')
    run = b.run([exe],'host-oracle.results',timeout=30)
    expected = [('L',p,i,v) for p in range(2) for i,v in enumerate(audit.expected_values(p))]
    expected += [('R',0,i,audit.seed_word(i)) for i in range(544)]
    actual = [(k,int(p),int(i),int(value,16)) for k,p,i,value in
              (line.split() for line in run.stdout.decode().splitlines())]
    require(actual==expected,'compiled C oracle differs from independent signed-byte Python model')
    save(b.out/'oracle-check.json',dict(status='PASS',lr_values=24,register_words=544,
        reference='Python signed little-endian byte decoding vs C bitwise LR.W sign extension',
        binary=str(exe),binary_sha256=sha(exe)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--development',action='store_true',help='new scratch directory; no draft or seals')
    args = parser.parse_args()
    out = args.output.resolve()
    prefix = 'gap64-lr-development-' if args.development else 'gap64-lr-preflight-'
    require(ROOT==Path('/home/wangwy/openproject/ara_dsa_signoff_integration'),'wrong worktree')
    require(out.parent==ROOT/'verification/out' and out.name.startswith(prefix) and not out.exists(),
            'require a new independent output directory')
    baseline = baseline_audit()
    pin_plan = ROOT/'verification/out/repaired-aligned-600-20260930-01/plan.json'
    old = next(c for c in read(pin_plan)['cases'] if c.get('spike'))
    spike = Path(old['spike'])
    require(sha(spike)==old['spike_sha256'],'pinned Spike changed')
    spike_sources = list(map(Path,read(HISTORY/'semantic-evidence.json')['spike_source_pins']))
    protected = dict(baseline['checked_files'])
    protected.update(pins([LEGACY,pin_plan,SOURCE.with_name('vgap35_common.h'),Path(evidence.__file__),
                          ROOT/'verification/coverage/run_checked_extension.py',*spike_sources]))
    out.mkdir()
    save(out/'baseline-targets.json',baseline); save(out/'protected-inputs.json',protected)
    (out/'source.snapshot').write_bytes(SOURCE.read_bytes())
    b = helpers.Build(out)
    b.sources = pins([SCRIPT,SOURCE,LEGACY,UNIT,adapter.SCRIPT,Path(audit.__file__)])
    b.tools.update(pins([spike,ROOT/'verification/tools/soc-venv/bin/python']))
    print('COMPLETE647 verified; building only the new LR-only case',flush=True)
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
    require(dut['metadata']['payload_sha256']==spike_info['metadata']['payload_sha256'],
            'DUT and Spike LR payload instruction bytes differ')
    dts = b.run([spike,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                 '--dump-dts',spike_elf],'spike-config')
    audit.validate_pmp_dts(dts.stdout.decode())
    parts = dict(setup=3,phase_checks=2*11,restored_csrs=21,main=2,harness_flags=3)
    require(sum(parts.values())==audit.CHECKS,'independent check-count derivation differs')
    save(out/'config-audit.json',dict(status='PASS',pmp_regions=0,rvh=0,xlen=64,
        translation='Bare',pmp_csr_accesses=0,lr_only=True,reservation_claim=False,ordering_claim=False,
        dts_log=str(out/'spike-config.log'),dts_sha256=sha(out/'spike-config.log'),count_parts=parts,
        spike_source_review=pins(spike_sources),
        semantics='Only locked AR loads; frozen L2 ignores reservation, returns SRAM data. '
                  'SC/RMW and error propagation remain unclosed. No successful-AMO claims.'))
    command = audit.expected_command(str(spike),str(spike_elf))
    run = b.run(command,'case.spike',timeout=30)
    spike_seconds = b.commands[-1]['seconds']
    audit.check_log(run.stdout.decode(),str(SOURCE))
    trace = audit.trace_check(run.stderr.decode(),spike_info['metadata'])
    save(out/'execution-proof.json',dict(status='PASS',dut=dut,spike=spike_info,spike_tool=str(spike),
        trace=trace,checks=audit.CHECKS,retired_limit=audit.MAX_RETIRED,
        vcs_timeout_s=240,vcs_launched=False,measured_gain=None,coverage_gain_required=False))
    b.run([sys.executable,'-B',UNIT,'--preflight',out,'-v'],'real-trace-unit-tests',timeout=180)
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and str(Path(m.__file__).resolve()).startswith(str(ROOT/'verification'))])
    for hashes in (b.sources,b.tools,b.link_inputs,protected): verify(hashes)
    save(out/'source_hashes.json',b.sources); save(out/'tool_hashes.json',b.tools)
    save(out/'link-inputs.json',b.link_inputs)
    if args.development:
        print('DEVELOPMENT ONLY: Spike PASS',trace,flush=True)
        return
    row = dict(test=audit.NAME,status='PASS',returncode=0,command=command,seconds=spike_seconds,
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
        source_audit='24 LR.W/LR.D commits checked against independent signed-byte load oracle. '
            'Two phases with four ordinary stores immediately before each 12-LR sweep, full memory '
            'and all guards, every GPR/FP/vector register, complete ABI restore and 22 CSR snapshots. '
            'MSU/PMP0 Spike <=45000 retired; zero traps; no reservation/SC/RMW/order or measured-gain claim.',
        targets=sorted({p['scope'] for p in baseline['targets']}),timeout_s=240,
        rationale='647 native missing LR request/drain/AMO/ack paths, 25 line/44 cond/29 branch '
            'and two states/three transitions predicted only, never a functional PASS gate.',
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
    print('PASS: Spike %d checks, %d retired; 24 LR, full register/CSR/buffer checks' %
          (audit.CHECKS,trace['retired']),flush=True)
    print('PASS: %d native / %d sealed outer pins; no VCS'%(len(proof.files),len(outer.files)),flush=True)
    print(draft,flush=True)


if __name__=='__main__': main()
