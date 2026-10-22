"""Bounded software preflight for a715 cache-replay hypothesis; no RTL launch."""
import argparse
import json
import re
from pathlib import Path
import subprocess

import build_gap98_preflight as shared
import run_gap95_simulation as life

ROOT, OUT, require = shared.ROOT, shared.OUT, shared.require
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vcache_port1_sv39_boundary_crossline.c'
BASE = OUT / 'gap100-offline-admitted-715-20261006-01'
BASE_SEAL = '069e9e7717e915c18ce921f583fa33bf18e7670a3f13ec12073e8bba1998a283'
C = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_cache_wt.i_cache_subsystem.i_wt_dcache.gen_rd_ports[1].genblk1.i_wt_dcache_ctrl'
GUARD = 0x5a3c719de4b208f6
SYMBOLS = ('tohost', 'g75_result', 'g75_trap', 'num_failed', 'trap_fail', 'gcb_page', 'gcb_second',
           'gcb_entry', 'gcb_s_ecall', 'gcb_count', 'gcb_traps', 'gcb_data', 'gcb_out',
           'gcb_root', 'gcb_mid', 'gcb_leaf')


def word(i):
    return 0x13579bdf2468ace0 ^ ((0x0102030405060708 * i) & ((1 << 64) - 1))


def validate(commits, symbols):
    require(not any(c.vector_writes or c.pc == symbols['trap_fail'] for c in commits), 'Unexpected vector/default trap')
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    require([v for c in commits for a, v in c.memory_accesses if a == symbols['tohost'] and v is not None] == [1] and
            writes.get(symbols['g75_result']) == 35 and writes.get(symbols['g75_result'] + 4) == 0 and
            writes.get(symbols['num_failed']) == 0 and writes.get(symbols['gcb_count']) == 2,
            'Wrong complete software signature')
    require(symbols['gcb_page'] % 4096 == 0 and symbols['gcb_second'] == symbols['gcb_page'] + 4096 and
            symbols['gcb_entry'] == symbols['gcb_page'] + 3840 and
            symbols['gcb_s_ecall'] == symbols['gcb_second'] + 32, 'Wrong linked boundary layout')
    geometry = linked_geometry(symbols, writes)
    for p, slot in enumerate((3, 35)):
        values = [writes.get(symbols['gcb_out'] + p * 80 + i * 8) for i in range(10)]
        require(values == [GUARD, *[word(4 * i) for i in range(8)], GUARD], 'Wrong160-byte guarded output oracle')
        trap = [writes.get(symbols['gcb_traps'] + p * 32 + i * 8) for i in range(4)]
        require(trap[:3] == [9, 0x40000000 + slot * 4096 + 4096 + 32, 0] and
                trap[3] is not None and trap[3] & 0x1800 == 0x800, 'Wrong exact S-ECALL ledger')
        pcs = [c.pc for c in commits if 0x40000000 + slot * 4096 <= c.pc < 0x40000000 + (slot + 2) * 4096]
        require(pcs == list(range(0x40000000 + slot * 4096 + 3840,
                                 0x40000000 + (slot + 1) * 4096 + 32, 4)), 'Incomplete/different aliased S retirement')
    cause_reads = [v for c in commits if c.instruction >> 20 == 0x342 and c.instruction & 127 == 0x73
                   for v in c.gpr_writes.values()]
    require(cause_reads == [9, 9], 'Missing/extra/wrong handler cause')
    return dict(status='SPIKE_CACHE_BOUNDARY_ARCHITECTURE_PASS_NOT_REPLAY_WITNESS', checks=35,
        exact_output_bytes=160, trap_ledger_bytes=64, expected_S_ecalls=2, vector_destination_instructions=0,
        instruction_boundary_phases=2, linked_geometry=geometry, replay_observed=False, measured_raw_increment=None, coverage_admitted=False)


def configuration_proof():
    config = ROOT / 'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv'
    build = ROOT / 'hardware/deps/cva6/core/include/build_config_pkg.sv'
    soc = ROOT / 'hardware/src/ara_soc.sv'
    text = config.read_text()
    require(re.findall(r'localparam\s+CVA6ConfigDcacheLineWidth\s*=\s*(\d+)\s*;', text) == ['256'],
            'Unexpected frozen Dcache line width')
    require("DcacheLineWidth: unsigned'(CVA6ConfigDcacheLineWidth)" in text,
            'Missing config field propagation')
    require('cfg.DCACHE_LINE_WIDTH = CVA6Cfg.DcacheLineWidth;' in build.read_text(),
            'Missing built config propagation')
    override = soc.read_text().split('function automatic config_pkg::cva6_user_cfg_t gen_usr_cva6_config', 1)[1].split('endfunction', 1)[0]
    require(not re.search(r'cfg\s*\.\s*DcacheLineWidth\s*=', override),
            'Ara overrides line width')
    require('gen_usr_cva6_config(cva6_config_pkg::cva6_cfg)' in soc.read_text(),
            'Wrong config route')
    return dict(line_bits=256, line_bytes=32, PTE_bytes=8, first_slots=[3, 35],
                source_hashes={str(p): shared.sha(p) for p in (config, build, soc)},
                replay_timing_proven=False)


def linked_geometry(symbols, writes):
    require(symbols['gcb_leaf'] % 4096 == 0 and symbols['gcb_data'] % 32 == 0,
            'Unaligned linked PTE/data buffers')
    pairs = []
    for slot in (3, 35):
        addresses = [symbols['gcb_leaf'] + 8 * i for i in (slot, slot + 1)]
        require(addresses[0] // 32 != addresses[1] // 32, 'PTE pair shares Dcache line')
        expected = [((symbols[name] >> 12) << 10) | 0xcb for name in ('gcb_page', 'gcb_second')]
        require([writes.get(a) for a in addresses] == expected, 'Wrong linked instruction-page PTE')
        pairs.append(dict(slots=[slot, slot + 1], PTE_addresses=addresses,
                          Dcache_line_bases=[a // 32 * 32 for a in addresses],
                          mapped_pages=[symbols['gcb_page'], symbols['gcb_second']]))
    require(writes.get(symbols['gcb_root'] + 8) == ((symbols['gcb_mid'] >> 12) << 10) | 1 and
            writes.get(symbols['gcb_mid']) == ((symbols['gcb_leaf'] >> 12) << 10) | 1,
            'Wrong linked nonleaf PTE chain')
    return dict(line_bytes=32, pairs=pairs, data_stride_bytes=32, distinct_data_lines=8,
                second_PTE_cold_at_runtime_proven=False)


def targets(bitmap):
    out = []
    for metric, positions, checksum in [('fsm', (6, 7, 21, 27), '3476102610'),
                                       ('branch', (36,), '3466602542')]:
        row = bitmap['metrics'][metric][C]
        require(row['checksum'] == checksum and row['width'] == (28 if metric == 'fsm' else 43), 'Target shape drift')
        for raw in positions:
            require(not int(row['bits'], 16) & (1 << (row['width'] - 1 - raw)), 'Target already hit715')
            out.append(dict(scope=C, metric=metric, raw_index=raw, definition_checksum=checksum,
                            width=row['width'], hit_before=False, native_exclusion_identity_claimed=False))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    # Reuse the proven scalar build flags, not its target/oracle contract.
    template = OUT / 'gap99-csr-satp-mprv-preflight-707-20261006-01/compile-command.json'
    if not template.exists():
        matches = list(OUT.glob('gap99*preflight*/compile-command.json'))
        require(len(matches) == 1, 'Ambiguous compile template')
        template = matches[0]
    command = json.loads(template.read_bytes())
    old_app = str(ROOT / 'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')
    require(command.count(old_app) == 1 and command[-2] == '-o', 'Unexpected scalar compile template')
    command = [str(APP) if a == old_app else a for a in command]
    command[-1] = str(out / 'input.elf')
    pins = {str(p): shared.sha(p) for p in (APP, Path(__file__).resolve(),
        Path(__file__).with_name('test_build_cache_port1_sv39_crossline_preflight.py'), template,
        ROOT / 'verification/tests/gap75_start.S', ROOT / 'verification/tests/gap75.ld',
        shared.LLVM / 'clang', shared.LLVM / 'llvm-readelf', shared.LLVM / 'llvm-objdump', shared.SPIKE,
        Path(shared.__file__).resolve())}
    seals = life.read_bound(BASE / 'seals.json', BASE_SEAL)
    for p in (BASE / 'combined-bits.json', BASE / 'combined-inputs.txt', BASE / 'status.json'):
        pins = life.merge_pins(pins, {str(p): seals['pins'][str(p)]})
    pins = life.merge_pins(pins, {str(BASE / 'seals.json'): BASE_SEAL})
    source_manifest = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    historical = json.loads(source_manifest.read_bytes())
    for rel in ('hardware/deps/cva6/core/cache_subsystem/wt_dcache_ctrl.sv',
                'hardware/deps/cva6/core/cache_subsystem/wt_dcache_mem.sv',
                'hardware/deps/cva6/core/cache_subsystem/wt_dcache_missunit.sv',
                'hardware/deps/cva6/core/cache_subsystem/wt_dcache.sv', 'hardware/deps/cva6/core/cva6.sv',
                'hardware/src/ara_soc.sv',
                'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
                'hardware/deps/cva6/core/include/build_config_pkg.sv'):
        path = str(ROOT / rel)
        pins = life.merge_pins(pins, {path: historical[path]})
    pins = life.merge_pins(pins, {str(source_manifest): seals['pins'][str(source_manifest)]})
    for path in (ROOT / 'apps/riscv-tests/isa/macros').rglob('*'):
        if path.is_file():
            pins = life.merge_pins(pins, {str(path): shared.sha(path)})
    shared.check(pins)
    configuration = configuration_proof()
    bitmap = json.loads((BASE / 'combined-bits.json').read_bytes())
    require(len(bitmap['tests']) == 715 and (BASE / 'combined-inputs.txt').read_text().splitlines()[1:] == bitmap['tests'],
            'Not exact715 baseline')
    target = targets(bitmap)
    out.mkdir()
    shared.save(out / 'cache-configuration-proof.json', configuration)
    shared.save(out / 'target-before.json', dict(baseline_tests=715, targets=target, exclusions_generated=False))
    shared.save(out / 'compile-command.json', command)
    try:
        with (out / 'compile.log').open('x') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        elf = out / 'input.elf'
        symbols = {k: shared._elf_symbol(elf, shared.LLVM / 'llvm-readelf', k) for k in SYMBOLS}
        with (out / 'input.disasm').open('x') as stream:
            subprocess.run([str(shared.LLVM / 'llvm-objdump'), '-d', str(elf)], stdout=stream, check=True, timeout=30)
        command = [str(shared.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
                   '-l', '--log-commits', str(elf)]
        shared.save(out / 'spike-command.json', command)
        trace = out / 'spike.trace'
        with (out / 'spike.stdout').open('x') as stdout, trace.open('x') as stream:
            subprocess.run(command, stdout=stdout, stderr=stream, check=True, timeout=60)
        validation = validate(shared.parse_spike_commits(trace), symbols)
        shared.save(out / 'spike-validation.json', validation)
        shared.check(pins)
        pins = life.merge_pins(pins, {str(p): shared.sha(p) for p in out.iterdir() if p.is_file()})
        shared.save(out / 'preflight-manifest.json', dict(status='CACHE_BOUNDARY_SPIKE_PREFLIGHT_PASS_NOT_DUT',
            baseline_tests=715, baseline_seal=BASE_SEAL, pins=pins, input_elf=str(elf), input_spike_trace=str(trace), symbols=symbols,
            spike_validation=validation, expected_targets=5, coverage_admitted=False, rtl_changed=False,
            scalar_comparison_qualified=False, replay_observed=False, VCS_timeout_proposal_seconds=600))
        print(json.dumps(dict(output=str(out), seal=shared.sha(out / 'preflight-manifest.json'), validation=validation)))
    except Exception as error:
        shared.save(out / 'failure.json', dict(status='CACHE_BOUNDARY_PREFLIGHT_FAILED', reason=str(error)))
        raise


if __name__ == '__main__':
    main()
