#!/usr/bin/env python3
"""Additive gap72 build/software-reference preflight. Never launches RTL tools."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification/coverage'), str(Path(__file__).resolve().parent)]
from build_gap38_i8_f16_lane3 import Build, pins, read, require, save, sha, verify
import coverage_evidence as evidence
import audit_gap72_lifecycle as audit

APP = ROOT / 'apps/gap72_custom_lifecycle'
SCRIPT = Path(__file__).resolve()
ADAPTER = ROOT / 'verification/coverage/run_gap72_lifecycle_checked_extension.py'
UNIT = ROOT / 'verification/tests/test_gap72_lifecycle.py'
REFS = [ROOT / 'verification/qbs/qbs_ref.c', ROOT / 'software/akv/src/akv_v2_reference.c']


def metadata(b, elf, label):
    b.run([b.llvm / 'bin/llvm-objdump', '-d', elf], label + '.disassembly')
    result = b.run([b.llvm / 'bin/llvm-readobj', '--elf-output-style=JSON', '--sections',
                    '--symbols', '--program-headers', elf], label + '.metadata')
    return json.loads(result.stdout)[0]


def build_case(b, name, ref, spike):
    label = 'qbs' if name == audit.CASE_NAMES[0] else 'akv'
    define = ['-DGAP72_QBS=1'] if label == 'qbs' else []
    extra = [*define, '-fno-strict-aliasing', '-fno-builtin-fmaf', '-fno-builtin-calloc']
    h = ['-DGAP72_REFERENCE=1', *extra]
    objects = [b.compile(APP / 'main.c', label + '-host-main', h, host=True),
               b.compile(ref, label + '-host-reference', h, host=True)]
    host = b.out / (name + '.host')
    b.link([b.host, *objects, '-lm', '-o', host], label + '-host.link')
    stdout = b.run([host], label + '-host', timeout=30).stdout.decode()
    host_result = audit.validate_log(stdout, name, host=True)
    negative = b.run([host, '--negative'], label + '-negative', timeout=30).stdout.decode()
    audit.validate_log(negative, name, host=True, negative=True)
    expected_bytes = 10232 if label == 'qbs' else 9792
    require(f'G72_NEGATIVE bytes={expected_bytes} errors=0' in negative, 'exhaustive negative cardinality differs')
    objects = [b.compile(b.common / n, label + '-dut-' + n) for n in
               ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    objects += [b.compile(APP / n, label + '-dut-' + n, extra) for n in ('main.c', 'entry.S', 'execute.S')]
    elf = b.out / (name + '.elf')
    b.bind_sources([APP / 'link.ld'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostartfiles', '-Wl,--gc-sections',
            '-Wl,--orphan-handling=error', '-Wl,--build-id=none', '-Wl,-Map=' + str(b.out / (label + '-dut.map')),
            '-T' + str(APP / 'link.ld'), *objects, '-lm', '-L' + str(b.llvm / 'lib/generic'),
            '-lclang_rt.builtins-riscv64', '-o', elf], label + '-dut.link')
    fit = ROOT / 'verification/coverage/check_elf_fit.py'
    b.bind_sources([fit])
    b.run([ROOT / 'verification/tools/soc-venv/bin/python', fit, '--elf', elf, '--ram-bytes', '0x200000',
           '--output', b.out / (label + '-elf-fit.json')], label + '-elf-fit')
    meta = metadata(b, elf, label + '-dut')
    elf_result = audit.elf_audit(meta, elf.read_bytes(), name)
    save(b.out / (label + '-elf-audit.json'), elf_result)
    runtime = ROOT / 'apps/riscv-tests/benchmarks/common'
    s = ['-D__SPIKE__=1', '-DPREALLOCATE=1', '-I' + str(runtime),
         '-I' + str(ROOT / 'apps/riscv-tests/env'), *h]
    objects = [b.compile(source, label + '-spike-' + source.name,
               [*s, '-fno-function-sections', '-fno-data-sections']) for source in
               (runtime / 'crt.S', runtime / 'syscalls.c', APP / 'main.c')]
    objects.append(b.compile(ref, label + '-spike-reference', s))
    if label == 'qbs':
        objects.append(b.compile(APP / 'reference_support.c', label + '-spike-support', s))
    b.bind_sources([runtime / 'test.ld'])
    reference_elf = b.out / (name + '.software-reference.elf')
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostdlib', '-Wl,--gc-sections',
            '-T' + str(runtime / 'test.ld'), *objects, '-L' + str(b.llvm / 'lib/generic'),
            '-lclang_rt.builtins-riscv64', '-o', reference_elf], label + '-spike.link')
    metadata(b, reference_elf, label + '-software-reference')
    command = [str(spike), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
               '-l', '--log-commits', str(reference_elf)]
    result = b.run(command, label + '-software-spike', timeout=30)
    require(result.stdout.decode().splitlines() == [f'PASSED: {name} SOFTWARE_REFERENCE_ONLY'],
            'software Spike final marker differs')
    software = audit.software_trace(result.stderr.decode(), name)
    save(b.out / (label + '-software-spike-proof.json'), dict(software,
         elf=str(reference_elf), elf_sha256=sha(reference_elf), command=command,
         spike_sha256=sha(spike), stdout=str(b.out / (label + '-software-spike.log')),
         trace=str(b.out / (label + '-software-spike.stderr.log'))))
    return dict(name=name, label=label, binary=str(elf), binary_sha256=sha(elf),
                host_reference=str(ref), host_log=str(b.out / (label + '-host.log')),
                host_result=stdout.strip(), host=host_result, elf_audit=elf_result,
                metadata=str(b.out / (label + '-dut.metadata.log')),
                software_spike=str(b.out / (label + '-software-spike-proof.json')),
                negative_byte_mutations=expected_bytes,
                custom_instruction_execution_prechecked=False, vcs_launched=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--vcs-timeout', type=int, choices=(300,1800), default=300)
    args = parser.parse_args()
    out = args.output.resolve()
    require(ROOT == Path('/home/wangwy/openproject/ara_dsa_signoff_integration') and
            out.parent == ROOT / 'verification/out' and out.name.startswith('gap72-') and not out.exists(),
            'require a NEW gap72-* output directory in integration worktree')
    proof = evidence.Evidence()
    targets = audit.native_targets(proof)
    frozen = read(ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json')
    for path, digest in frozen.items():
        if any(s in path for s in ('/qbs/', '/akv/', '/include/qbs_pkg.sv', '/include/akv_pkg.sv',
                                 '/vlsu/vlsu.sv', '/ara_commit_monitor.sv', '/ara_soc.sv', '/ara_system.sv')):
            proof.pin(path, digest)
    protected = dict(proof.files)
    plan_path = ROOT / 'verification/out/repaired-aligned-600-20260930-01/plan.json'
    plan = read(plan_path)
    spike = Path(plan['cases'][0]['spike'])
    require(sha(spike) == plan['cases'][0]['spike_sha256'], 'pinned Spike drift')
    protected.update(pins([plan_path, ROOT / 'verification/tests/build_gap38_i8_f16_lane3.py',
        ROOT / 'verification/coverage/coverage_evidence.py', ROOT / 'verification/coverage/run_checked_extension.py',
        ROOT / 'verification/coverage/run_targeted_extension.py',
        ROOT / 'verification/ara_verify/vector_commit.py', ROOT / 'verification/ara_verify/trace.py',
        ROOT / 'verification/ara_verify/spike_trace.py',
        *[spike.parent.parent / p for p in ('riscv/execute.cc', 'riscv/processor.cc',
                                           'riscv/mmu.cc', 'spike_main/spike.cc')]]))
    out.mkdir()
    b = Build(out)
    b.sources = pins([SCRIPT, UNIT, ADAPTER, Path(audit.__file__), *APP.iterdir(), *REFS])
    b.host = Path('/usr/bin/gcc').resolve(strict=True)
    b.tools.update(pins([b.host, spike, ROOT / 'verification/tools/soc-venv/bin/python',
                        Path('/usr/bin/as').resolve(), Path('/usr/bin/ld').resolve()]))
    for name in ('cc1', 'collect2'):
        r = b.run([b.host, '-print-prog-name=' + name], 'host-tool-' + name)
        b.tools.update(pins([Path(r.stdout.decode().strip()).resolve(strict=True)]))
    save(out / 'native-targets.json', targets)
    save(out / 'source-audit.json', dict(status='STATIC_CAUSAL_REVIEW_ONLY', files=protected,
        qbs='FILL begin invalidates generation71; row-major N5 requests activation292 then weights'
            '144x4 at bffffdc0..bfffffff, fifth at c0000000 -> PMA5 -> COMPUTE_FAULT_DRAIN'
            ' (done0/101), compute FAULT_CLEAR(done1/111) -> context_fill_abort -> no COMMIT;'
            ' REUSE generation71 must CONTEXT_INVALID18; refill generation73 restores512;'
            ' altered external activation3 must not change cached REUSE/RELEASE512.',
        akv='V2FULL version1/D64/Q1/KV3 -> ready1/versionV2; V2REFILL start3 matchesversion'
            ' and bounds>=3 -> C59/001 -> TILE_RANGE11, accepted command clearsready -> LOAD'
            ' CONTEXT12; V2FULL start1 rebuilds -> K row0 equals original token1.',
        scope='Host/Spike execute existing numerical SOFTWARE references, NOT custom opcodes.',
        reference_semantic_differences=['QBS software buffer-size failure is not RTL late PMA timing.',
            'AKV numerical refill API retains ready on range error; additive command shim releases it.'],
        payload_ranges=dict(qbs_valid=[hex(0xbffffdc0), hex(0xc0000000)], qbs_bytes=576,
            fault_first_byte=hex(0xc0000000), prefix_guard_bytes=64,
            akv_q_rows=1, akv_kv_rows=3, akv_row_bytes=128),
        vcs_launched=False, measured_gain=None))
    print('gap72 latest654 stillzero/static causal checks PASS; software builds only', flush=True)
    b.run([sys.executable, '-B', UNIT], 'unit-tests', timeout=30)
    records = [build_case(b, audit.CASE_NAMES[i], REFS[i], spike) for i in (1, 0)]
    verify(protected); verify(b.sources); verify(b.tools); verify(b.link_inputs)
    save(out / 'source_hashes.json', b.sources)
    save(out / 'tool_hashes.json', b.tools)
    save(out / 'link-inputs.json', b.link_inputs)
    save(out / 'protected-inputs.json', protected)
    save(out / 'cost-analysis.json', dict(status='BOUNDED_STATIC_ONLY_DUT_NOT_TIMED', timeout_s=args.vcs_timeout,
        qbs=dict(commands=6, k_blocks=1, m=1, successful_outputs=4, fault_prefix_weight_rows=4,
                 total_payload_bytes=2124, complete_vrf_images=6),
        akv=dict(commands=7, fulls=2, row_loads=2, faults=2, total_payload_bytes=1664,
                 complete_vrf_images=7), no_timeout_enlargement=args.vcs_timeout == 300, vcs_launched=False))
    for record in records:
        record.update(source_hashes=dict(b.sources), sources=sorted(b.sources), schema=audit.SCHEMA)
        save(out / (record['name'] + '.precheck.json'), record)
    artifact_paths = [p for p in out.iterdir() if p.is_file()]
    save(out / 'artifact_hashes.json', pins(artifact_paths))
    items = []
    source_review = read(out / 'source-audit.json')
    for record in records:
        items.append(dict(name='app:' + record['name'], binary=record['binary'],
            binary_sha256=record['binary_sha256'], timeout_s=args.vcs_timeout, sources=sorted(b.sources),
            evidence=sorted(map(str, [*artifact_paths, out / 'artifact_hashes.json'])),
            rationale=source_review[record['label']],
            targets=sorted({point['scope'] for point in targets['targets']
                            if point['module'] == record['label'] + '_engine'}),
            source_audit=str(out / 'source-audit.json'), runtime_contract=audit.SCHEMA,
            precheck=dict(format='accel-host-v1', record=str(out / (record['name'] + '.precheck.json')))))
    draft = out / 'selection.checked-draft.json'
    save(draft, dict(status='SEALED_DRAFT_SOFTWARE_REFERENCE_PASS_RTL_NOT_RUN', baseline=str(audit.BASE),
                    cases=items, vcs_launched=False, measured_gain=None))
    saved = {}
    for item in items:
        native = evidence.Evidence(); native.pin(draft)
        for name in ('tool_hashes.json', 'link-inputs.json', 'protected-inputs.json', 'artifact_hashes.json'):
            native.hashes(native.read(out / name))
        result = evidence.precheck(item, native)
        saved[item['name']] = dict(result=result, checked_files=native.files)
    save(out / 'checked-precheck.json', dict(status='PASS', read_only_validation=True,
         scope='host-reference-only', vcs_launched=False, cases=saved))
    save(out / 'draft.sha256.json', pins([draft, out / 'checked-precheck.json', out / 'artifact_hashes.json']))
    import run_gap72_lifecycle_checked_extension as adapter
    script = adapter.checked.SCRIPT
    adapter.install_hooks()
    require(adapter.checked.SCRIPT == script, 'install_hooks changed parent SCRIPT')
    for item in items:
        replay = evidence.precheck(item, evidence.Evidence())
        require(replay['runtime_contract'] == audit.SCHEMA, 'sealed adapter replay failed')
    verify(protected); verify(b.sources); verify(b.tools); verify(b.link_inputs)
    print('SEALED gap72: two exact software-reference/ELF prechecks PASS; custom RTL NOT RUN: ' + str(draft), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
