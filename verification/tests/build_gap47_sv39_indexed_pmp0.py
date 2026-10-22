#!/usr/bin/env python3
"""New gap47 ELFs, independent host oracle and genuine Spike; never launch VCS."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
NAME = 'vgap47_sv39_indexed_pmp0'
SOURCE = ROOT / 'apps/riscv-tests/isa/rv64uv' / (NAME + '.c')
ANALYSIS = ROOT / 'verification/out/gap42-rvv-reachable-analysis-20261004-01'
BASELINE = ROOT / 'verification/out/gap37-control-current-20261004-01'
LEGACY = ROOT / 'verification/tests/build_gap38_i8_f16_lane3.py'
UNIT_TEST = ROOT / 'verification/tests/test_gap47_rvv_pmp0_sealed_precheck.py'
PATH_SOURCES = ('hardware/src/ara_soc.sv', 'hardware/src/ara_system.sv',
                'hardware/src/ara.sv', 'hardware/deps/cva6/core/load_store_unit.sv',
                'hardware/deps/cva6/core/csr_regfile.sv', 'hardware/deps/cva6/core/pmp/src/pmp.sv',
                'hardware/deps/cva6/core/include/build_config_pkg.sv',
                'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
                'hardware/deps/cva6/core/cva6.sv', 'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv')
spec = importlib.util.spec_from_file_location('immutable_gap38_build', LEGACY)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
sha, save, read, pins, verify, require = (getattr(helpers, n) for n in
    ('sha', 'save', 'read', 'pins', 'verify', 'require'))
sys.path.insert(0, str(ROOT / 'verification/coverage'))
import coverage_evidence
import run_gap47_rvv_checked_extension_v2 as adapter


def baseline_audit():
    inventory = read(ANALYSIS / 'inventory.json')
    verify(inventory['pins'])
    raw = read(ANALYSIS / 'raw640-corroboration.json')
    require(raw['status'] == 'PASS' and raw['tests'] == 640 and raw['raw_files'] == 1280,
            'missing independently corroborated raw640')
    collection = read(BASELINE / 'collection.json')
    checkpoint = read(BASELINE / 'checkpoint.json')
    require(collection['status'] == 'PASS' and collection['passed'] == 640 and
            checkpoint['coverage_status'] == 'COMPLETE' and checkpoint['aggregate_passed'] == 640,
            'not formal COMPLETE640')
    frozen_sources = read(ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json')
    verify({str(ROOT / p): frozen_sources[str(ROOT / p)] for p in PATH_SOURCES})
    require('cfg.NrPMPEntries          = 0;' in (ROOT / PATH_SOURCES[0]).read_text(),
            'DUT PMP configuration differs')
    scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen'
    row = inventory['instances'][scope]['metrics']['branch']
    targets = [p for p in row['missing'] if p['spec_id'] == '9' and p['vector']['id'] in ('25', '30')]
    require(len(targets) == 2 and {p['raw_index'] for p in targets} == {74, 69}, 'wrong native targets')
    for point in targets:
        require(point['raw_index'] == 52 + 48 - 1 - int(point['vector']['id']) and
                row['bits'][point['raw_index']] == '0', 'native target no longer zero')
    return dict(status='PASS', baseline=str(BASELINE), passed=640, scope=scope, targets=targets,
                measured_gain=None, expected_primary_branch_bits=2, waivers_applied=False)


def metadata(b, elf, label):
    b.run([b.llvm / 'bin/llvm-objdump', '-d', elf], label + '.disassembly')
    result = b.run([b.llvm / 'bin/llvm-readobj', '--elf-output-style=JSON', '--sections',
                    '--symbols', '--program-headers', elf], label + '.metadata')
    obj = json.loads(result.stdout)[0]
    symbols = {r['Symbol']['Name']['Name']: r['Symbol'] for r in obj['Symbols']}
    blob, sites = elf.read_bytes(), {}
    for name, expected in adapter.WORDS.items():
        address = symbols[name]['Value']
        words = []
        for row in obj['Sections']:
            sec = row['Section']
            if sec['Flags']['Value'] & 4 and sec['Address'] <= address and address + 4 <= sec['Address'] + sec['Size']:
                offset = sec['Offset'] + address - sec['Address']
                words.append(int.from_bytes(blob[offset:offset + 4], 'little'))
        require(words == [expected], 'indexed site word differs: ' + name)
        sites[name] = dict(pc=hex(address), word=hex(expected))
    return dict(status='PASS', elf=str(elf), elf_sha256=sha(elf), sites=sites)


def host_oracle(b):
    obj = b.compile(SOURCE, 'host-oracle', ['-DGAP47_ORACLE_HOST=1'], host=True)
    exe = b.out / 'host-oracle'
    b.link([b.host, obj, '-o', exe], 'host-oracle.link')
    result = b.run([exe], 'host-oracle.results', timeout=30)
    # Independent address-table expansion, not a translation of the C search loop.
    offsets = (0x300, 0x1040, 0x98, 0x1084, 0x1f0, 0x1130, 0x404, 0x1208)
    reg = [[0x6c000000 ^ (r << 16) ^ (i * 0x030507) for i in range(32)] for r in range(32)]
    reg[16][:8] = offsets
    pages = [[0x91e00000 ^ (p * 0x13570000) ^ (w * 0x10203) for w in range(1024)] for p in range(3)]
    after_reg = [r[:] for r in reg]
    after_pages = [p[:] for p in pages]
    for i, offset in enumerate(offsets):
        page, byte = divmod(offset, 4096)
        after_reg[8][i] = pages[(0, 2)[page]][byte // 4]
        page, byte = divmod(offset + 0x800, 4096)
        after_pages[(0, 2)[page]][byte // 4] = reg[12][i]
    expected = [('R', r, w, reg[r][w], after_reg[r][w]) for r in range(32) for w in range(32)]
    expected += [('P', p, w, pages[p][w], after_pages[p][w]) for p in range(3) for w in range(1024)]
    actual = []
    for line in result.stdout.decode().splitlines():
        kind, a, w, before, after = line.split()
        actual.append((kind, int(a), int(w), int(before, 16), int(after, 16)))
    require(actual == expected, 'independent full-memory/register oracle differs')
    save(b.out / 'oracle-check.json', dict(status='PASS', rows=len(expected),
        scalar_comparisons=8192, register_words=1024, physical_page_words=3072,
        reference='Independent Python address-table expansion vs compiled C oracle, all before/after words',
        binary=str(exe), binary_sha256=sha(exe)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(ROOT == Path('/home/wangwy/openproject/ara_dsa_signoff_integration'), 'wrong worktree')
    out = args.output.resolve()
    require(out.parent == ROOT / 'verification/out' and
            out.name.startswith('gap47-sv39-indexed-pmp0-preflight-') and not out.exists(), 'need NEW output')
    audit = baseline_audit()
    plan_path = ROOT / 'verification/out/repaired-aligned-600-20260930-01/plan.json'
    oracle = next(c for c in read(plan_path)['cases'] if c.get('spike'))
    spike = Path(oracle['spike'])
    require(sha(spike) == oracle['spike_sha256'], 'pinned Spike differs')
    archived = [ROOT / 'apps/riscv-tests/isa/rv64uv/vgap47_sv39_indexed.c',
                ROOT / 'verification/tests/build_gap47_sv39_indexed.py',
                ROOT / 'verification/coverage/run_gap47_rvv_checked_extension.py',
                ROOT / 'verification/tests/test_gap47_rvv_sealed_precheck.py']
    for suffix in ('01', '02'):
        directory = ROOT / ('verification/out/gap47-sv39-indexed-preflight-20261004-' + suffix)
        archived += [p for p in directory.iterdir() if p.is_file()]
    spike_source_root = spike.parent.parent
    spike_sources = [spike_source_root / p for p in
                     ('spike_main/spike.cc', 'riscv/csrs.cc', 'riscv/mmu.cc', 'riscv/cfg.cc')]
    protected = pins(archived + spike_sources + [p for p in ANALYSIS.iterdir() if p.is_file()] +
        [LEGACY, plan_path, SOURCE.with_name('vgap35_common.h'), Path(coverage_evidence.__file__),
         ROOT / 'verification/coverage/reviewed_20261004/audit_readonly.py',
         BASELINE / 'collection.json', BASELINE / 'checkpoint.json'] +
        list(map(Path, read(ANALYSIS / 'inventory.json')['pins'])) +
        [ROOT / p for p in PATH_SOURCES])
    out.mkdir()
    save(out / 'baseline-targets.json', audit)
    save(out / 'archived-inputs.json', pins(archived))
    save(out / 'protected-inputs.json', protected)
    b = helpers.Build(out)
    b.sources = pins([SCRIPT, SOURCE, LEGACY, adapter.SCRIPT, UNIT_TEST])
    b.tools.update(pins([spike, ROOT / 'verification/tools/soc-venv/bin/python']))
    save(out / 'tool_hashes.json', b.tools)
    print('COMPLETE640 two native zeros verified; building gap47 only', flush=True)
    b.run([sys.executable, '-B', UNIT_TEST], 'adapter-unit-tests')
    host_oracle(b)
    objects = [b.compile(b.common / n, 'dut-' + n) for n in
               ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    objects.insert(0, b.compile(SOURCE, NAME, ['-Wall', '-Wextra', '-Wno-unused-function']))
    elf = out / (NAME + '.elf')
    b.bind_sources([b.common / 'link.ld'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostartfiles', '-Wl,--gc-sections',
            f'-Wl,-Map={out / (NAME + ".map")}', f'-T{b.common / "link.ld"}', *objects, '-lm',
            f'-L{b.llvm / "lib/generic"}', '-lclang_rt.builtins-riscv64', '-o', elf], NAME + '.link')
    fit = ROOT / 'verification/coverage/check_elf_fit.py'
    b.bind_sources([fit])
    b.run([ROOT / 'verification/tools/soc-venv/bin/python', fit, '--elf', elf,
           '--ram-bytes', '0x200000', '--output', out / 'elf-fit.json'], 'elf-fit')
    dut_proof = metadata(b, elf, NAME)
    runtime = ROOT / 'apps/riscv-tests/benchmarks/common'
    extra = ['-D__SPIKE__=1', '-DPREALLOCATE=1', f'-I{runtime}',
             f'-I{ROOT / "apps/riscv-tests/env"}', '-fno-function-sections', '-fno-data-sections']
    objects = [b.compile(src, label, extra) for src, label in
        ((runtime / 'crt.S', 'spike-crt'), (runtime / 'syscalls.c', 'spike-syscalls'), (SOURCE, 'spike-test'))]
    spike_elf = out / (NAME + '.spike')
    b.bind_sources([runtime / 'test.ld'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostdlib', f'-T{runtime / "test.ld"}',
            *objects, '-o', spike_elf], NAME + '.spike-link')
    spike_proof = metadata(b, spike_elf, NAME + '.spike')
    dts = b.run([spike, '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu',
                 '--pmpregions=0', '--dump-dts', spike_elf], 'spike-pmp0-config')
    adapter.validate_pmp_dts(dts.stdout.decode())
    count_parts = dict(setup_common=3, s_state_and_two_csr_snapshots=22,
                       full_vector_and_seed_registers=64, full_buffer_guards=4,
                       full_physical_pages=3, full_page_tables=3,
                       common_csr_restoration=15, completion_and_count=2, harness_flags=3)
    require(sum(count_parts.values()) == adapter.CHECKS == 119 and
            sum(count_parts.values()) + 6 == adapter.DUT_CHECKS == 125, 'independent count mismatch')
    save(out / 'config-audit.json', dict(status='PASS', dut_pmp_regions=0, spike_pmp_regions=0,
        spike_pmp_csr_policy='ABSENT', dut_pmp_csr_policy='READ_ZERO_WRITE_IGNORED',
        dts_log=str(out / 'spike-pmp0-config.log'), dts_sha256=sha(out / 'spike-pmp0-config.log'),
        frozen_path_hashes=pins(ROOT / p for p in PATH_SOURCES),
        spike_source_review_hashes=pins(spike_sources), count_parts=count_parts,
        spike_checks=adapter.CHECKS, dut_checks=adapter.DUT_CHECKS,
        dut_only_pmp_checks=dict(initial_cfg_and_addr_zero=2, written_cfg_and_addr_ignored=2,
                                 restored_cfg_and_addr_zero=2),
        reasoning=['ara_soc:545 sets zero PMP; build_config:118 propagates it.',
                   'csr_regfile:3012-3033 forces PMP next arrays zero; legal CSR reads return zero.',
                   'pmp.sv:77 allows every access with zero regions, independently of Sv39 PTE checks.',
                   'S mode plus satp.MODE=8 enables real translation; MPRV=0, SUM=0, MXR=0.',
                   'RVV S body uses legal aligned e32/m1 VL8 addresses in two mapped 4KiB pages.',
                   'PTE A/D set; source/read and store targets disjoint; RAM code identity mapped.',
                   'Spike pmp_ok returns true with zero regions; its PMP CSR accessors raise illegal.',
                   'Spike omits absent PMP CSR probes only; no fake zero values or emulated PASS.']))
    command = adapter.expected_command(str(spike), str(spike_elf))
    run = b.run(command, NAME + '.spike', timeout=30)
    log, trace = run.stdout.decode(), run.stderr.decode()
    require(re.findall(r'^gap35 checks=(\d+) failures=0$', log, re.M) == [str(adapter.CHECKS)] and
            log.splitlines().count('PASSED: ' + str(SOURCE) + '!') == 1, 'Spike selfcheck failed')
    trace_proof = adapter.trace_check(trace, spike_proof['sites'])
    save(out / 'execution-proof.json', dict(status='PASS', dut=dut_proof, spike=spike_proof,
        spike_tool=str(spike), trace=trace_proof, checks=adapter.CHECKS,
        dut_checks=adapter.DUT_CHECKS, pmp_regions=0, vl=8,
        vector_register_words_checked=1024, unchanged_seed_words_checked=1024,
        memory_page_words_checked=3072, page_table_entries_checked=1536,
        guard_words_checked=64, fcsr=117, vcsr=5, vstart=0,
        scope='Same S-mode body and data oracle in both ELFs; DUT M-hook vs Spike M-mode main. '
              'Both models have zero PMP regions. DUT alone probes its implemented zero-valued '
              'PMP CSRs (6 checks); Spike PMP CSRs are absent and never accessed. '
              'Common Sv39/RVV/data/guard/CSR body is identical; no fault injection.',
        vcs_timeout_s=300, vcs_runtime_measured=False, vcs_launched=False))
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and str(Path(m.__file__).resolve()).startswith(str(ROOT / 'verification'))])
    for hashes in (b.sources, b.tools, b.link_inputs, protected):
        verify(hashes)
    save(out / 'source_hashes.json', b.sources)
    save(out / 'tool_hashes.json', b.tools)
    save(out / 'link-inputs.json', b.link_inputs)
    row = dict(test='rvv:' + NAME, status='PASS', returncode=0, command=list(map(str, command)),
        seconds=b.commands[-1]['seconds'], binary=str(elf), binary_sha256=sha(elf),
        spike_binary=str(spike_elf), spike_sha256=sha(spike_elf), spike_tool_sha256=sha(spike),
        log=str(out / (NAME + '.spike.log')), trace_log=str(out / (NAME + '.spike.stderr.log')),
        source_hashes=b.sources, tool_hashes=b.tools, link_inputs=b.link_inputs,
        checks=adapter.CHECKS, dut_checks=adapter.DUT_CHECKS, pmp_regions=0,
        vcs_launched=False, measured_coverage_gain=None)
    row['log_sha256'], row['trace_sha256'] = sha(row['log']), sha(row['trace_log'])
    save(out / 'spike_results.json', [row])
    artifacts = pins(p for p in out.iterdir() if p.is_file())
    save(out / 'artifact_hashes.json', artifacts)
    item = dict(name='rvv:' + NAME, binary=str(elf), binary_sha256=sha(elf),
        sources=sorted(b.sources), source_hashes=b.sources,
        evidence=sorted([*artifacts, str(out / 'artifact_hashes.json')]),
        source_audit='Independent host-validated integer/address oracle; full v0-v31 and source buffer, '
                     '24 destination tail words, all physical pages and page tables, full guards, '
                     'immediate vector/FP CSRs and 15 common restored CSRs, plus 2 DUT-only PMP restores. '
                     'Exactly two S-mode indexed commits and one expected supervisor ECALL in genuine Spike.',
        targets=[audit['scope']], timeout_s=300,
        rationale='COMPLETE640 addrgen Branch9(25) raw74 and Branch9(30) raw69 are zero. '
                  'S/Sv39 VL8 e32m1 ordered indexed load/store across nonadjacent physical pages. '
                  'Expected two primary branch bits, no claimed line/condition/FSM gain; no VCS run.',
        precheck=dict(format='rvv-spike-v1', record=str(out / 'spike_results.json'), log=row['log']))
    draft = out / 'selection.checked-draft.json'
    save(draft, dict(status='CHECKED_DRAFT_SPIKE_ONLY_NOT_SUBMITTED', baseline=str(BASELINE),
        cases=[item], vcs_launched=False, waivers_applied=False, measured_candidate_gain=None))
    proof = coverage_evidence.Evidence()
    proof.pin(draft)
    for hashes in (b.tools, b.link_inputs, protected, artifacts):
        proof.hashes(hashes)
    result = coverage_evidence.precheck(read(draft)['cases'][0], proof)
    save(out / 'checked-precheck.json', dict(status='PASS', result=result, checked_files=proof.files,
        entrypoint='coverage_evidence.precheck(item, Evidence())', read_only_validation=True,
        vcs_launched=False, waivers_applied=False))
    save(out / 'draft.sha256.json', pins([draft, out / 'checked-precheck.json', out / 'artifact_hashes.json']))
    adapter.install_hooks()
    outer = coverage_evidence.Evidence()
    sealed = coverage_evidence.precheck(read(draft)['cases'][0], outer)
    require(sealed == result, 'sealed outer result differs')
    save(out / 'sealed-replay.json', dict(status='PASS', result=sealed, checked_files=outer.files,
        exact_original_checked_files=len(proof.files), outer_pins=len(outer.files),
        checked_script_unchanged=True, vcs_launched=False))
    verify(protected)
    print(f'PASS: 4096 host oracle rows; genuine Spike {adapter.CHECKS} checks; 2 S-mode indexed commits', flush=True)
    print(f'PASS: original {len(proof.files)} pins / sealed outer {len(outer.files)} pins; no VCS', flush=True)
    print(draft, flush=True)


if __name__ == '__main__':
    main()
