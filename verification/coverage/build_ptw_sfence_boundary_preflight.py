"""Software-only preflight; PTW raw21/25 require a separate DUT window witness."""
import argparse
import json
from pathlib import Path
import subprocess

import build_cache_port1_sv39_crossline_preflight as geometry
import build_gap98_preflight as shared
import run_gap95_simulation as life

ROOT, OUT, require = shared.ROOT, shared.OUT, shared.require
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vptw_sfence_boundary.c'
BASE = OUT / 'narrow-source-group-offline-admitted-737-parent-20261006-01'
BITS_SHA = '271bcd1f154b3bf88351f9bc89370cb7889d2be59ac78286e5537842bd90b387'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_ptw'
SOURCES = (
    'hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv',
    'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv',
    'hardware/deps/cva6/core/controller.sv',
    'hardware/deps/cva6/core/commit_stage.sv',
    'hardware/deps/cva6/core/ex_stage.sv',
    'hardware/deps/cva6/core/load_store_unit.sv',
    'hardware/deps/cva6/core/cva6.sv',
    'hardware/deps/cva6/core/frontend/frontend.sv',
    'hardware/deps/cva6/core/issue_read_operands.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/src/ara_soc.sv',
)


def expected_words():
    w = geometry.word
    return [(w(8) // 3 + w(16)) & ((1 << 64) - 1), w(4), w(8), 3,
            w(16), w(20), w(24), w(28)]


def window_target(raw, state, flush, grant=False, rvalid=False):
    require(raw in (21, 25), 'Unknown PTW target')
    return bool(flush and ((raw == 21 and state == 'WAIT_GRANT' and not grant) or
                           (raw == 25 and state == 'WAIT_RVALID' and rvalid)))


def targets(bitmap):
    require(len(bitmap['tests']) == 737 and len(set(bitmap['tests'])) == 737, 'Not unique737')
    row = bitmap['metrics']['fsm'][SCOPE]
    require(row['checksum'] == '3345966803' and row['width'] == 35, 'PTW compiled shape drift')
    result = []
    for raw, state, predicate in ((21, 'WAIT_GRANT', 'flush_i && !req_port_i.data_gnt'),
                                  (25, 'WAIT_RVALID', 'flush_i && data_rvalid_q')):
        require(not int(row['bits'], 16) & (1 << (34 - raw)), 'Target already hit737')
        result.append(dict(scope=SCOPE, metric='fsm', raw_index=raw, width=35,
            checksum=row['checksum'], source_state=state, destination_state='LATENCY',
            predicate=predicate, hit_before=False, runtime_window_verified=False))
    return result


def validate(commits, symbols):
    require(symbols['gpf_sfence'] == symbols['gcb_page'] + 4092 and
            symbols['gcb_entry'] == symbols['gcb_page'] + 3840 and
            symbols['gcb_page'] % 4096 == 0 and symbols['gcb_second'] == symbols['gcb_page'] + 4096 and
            symbols['gcb_s_ecall'] == symbols['gcb_second'] + 32, 'Wrong linked SFENCE boundary')
    require(not any(c.vector_writes or c.pc == symbols['trap_fail'] for c in commits),
            'Unexpected vector/default trap')
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    require([v for c in commits for a, v in c.memory_accesses if a == symbols['tohost'] and v is not None] == [1],
            'Wrong/duplicate tohost')
    require(writes.get(symbols['g75_result']) == 35 and writes.get(symbols['g75_result'] + 4) == 0 and
            writes.get(symbols['num_failed']) == 0 and writes.get(symbols['gcb_count']) == 2,
            'Incomplete signature')
    linked = geometry.linked_geometry(symbols, writes)
    for phase, slot in enumerate((3, 35)):
        va = 0x40000000 + slot * 4096
        pcs = [c.pc for c in commits if va <= c.pc < va + 8192]
        require(pcs == list(range(va + 3840, va + 4096 + 32, 4)), 'Incomplete aliased retirement')
        sfence = [c for c in commits if c.pc == va + 4092]
        require(len(sfence) == 1 and sfence[0].instruction == 0x12000073, 'Wrong SFENCE opcode/owner')
        require([writes.get(symbols['gcb_out'] + phase * 80 + i * 8) for i in range(10)] ==
                [geometry.GUARD, *expected_words(), geometry.GUARD], 'Output/guards mismatch')
        trap = [writes.get(symbols['gcb_traps'] + phase * 32 + i * 8) for i in range(4)]
        require(trap[:3] == [9, va + 4096 + 32, 0] and trap[3] is not None and
                trap[3] & 0x1800 == 0x800, 'Wrong S-ECALL ledger')
    causes = [v for c in commits if c.instruction >> 20 == 0x342 and c.instruction & 127 == 0x73
              for v in c.gpr_writes.values()]
    require(causes == [9, 9], 'Unexpected/missing trap cause')
    return dict(status='SPIKE_ARCHITECTURE_PASS_NOT_PTW_WINDOW_PROOF', checks=35,
        output_bytes=160, trap_ledger_bytes=64, expected_traps=2, exact_sfence_owners=2,
        vector_destination_instructions=0, linked_geometry=linked,
        speculative_cold_walk_verified=False, runtime_window_verified=False,
        target_hit_claimed=False, coverage_admitted=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reuse-spike', type=Path)
    args = p.parse_args()
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    template = OUT / 'gap99-csr-satp-mprv-preflight-707-20261006-01/compile-command.json'
    command = json.loads(template.read_bytes())
    old = str(ROOT / 'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')
    require(command.count(old) == 1 and command[-2] == '-o', 'Compile template drift')
    command = [str(APP) if a == old else a for a in command]
    command[-1] = str(out / 'input.elf')
    source_manifest = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    historical = json.loads(source_manifest.read_bytes())
    files = [APP, Path(__file__).resolve(), Path(__file__).with_name('test_build_ptw_sfence_boundary_preflight.py'),
             Path(geometry.__file__).resolve(), Path(shared.__file__).resolve(), Path(life.__file__).resolve(),
             source_manifest, template, ROOT / 'verification/tests/gap75_start.S', ROOT / 'verification/tests/gap75.ld',
             shared.LLVM / 'clang', shared.LLVM / 'llvm-readelf', shared.LLVM / 'llvm-objdump', shared.SPIKE]
    files += [f for f in (ROOT / 'apps/riscv-tests/isa/macros').rglob('*') if f.is_file()]
    pins = {str(f): shared.sha(f) for f in files}
    pins = life.merge_pins(pins, {str(ROOT / rel): historical[str(ROOT / rel)] for rel in SOURCES})
    pins = life.merge_pins(pins, {str(BASE / 'combined-bits.json'): BITS_SHA})
    shared.check(pins)
    bitmap = json.loads((BASE / 'combined-bits.json').read_bytes())
    target = targets(bitmap)
    config = geometry.configuration_proof()
    out.mkdir()
    shared.save(out / 'target-before.json', dict(baseline_tests=737, targets=target))
    shared.save(out / 'configuration-proof.json', config)
    shared.save(out / 'control-window-contract.json', dict(
        gate='HOLD_UNTIL_DUT_WINDOW_WITNESS',
        raw21='state_q=WAIT_GRANT && flush_i && !data_gnt -> LATENCY',
        raw25='state_q=WAIT_RVALID && flush_i && data_rvalid_q -> LATENCY',
        required_signals=['state_q', 'state_d', 'flush_i', 'data_rvalid_q', 'req_port_i.data_gnt',
                          'is_instr_ptw_q', 'vaddr_q'],
        SFENCE_alias_PCs=[0x40003ffc, 0x40023ffc],
        unknown_cache_coldness=True, guaranteed_coverage_gain=False,
        ordinary_fault_matrix=False, warm_DTLB_candidate=False, VCS_authorized=False))
    shared.save(out / 'compile-command.json', command)
    try:
        with (out / 'compile.log').open('x') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
        elf = out / 'input.elf'
        symbols = {k: shared._elf_symbol(elf, shared.LLVM / 'llvm-readelf', k)
                   for k in (*geometry.SYMBOLS, 'gpf_sfence')}
        with (out / 'input.disasm').open('x') as stream:
            subprocess.run([str(shared.LLVM / 'llvm-objdump'), '-d', str(elf)], stdout=stream, check=True, timeout=30)
        spike = [str(shared.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
                 '-l', '--log-commits', str(elf)]
        trace_path = out / 'spike.trace'
        if args.reuse_spike:
            reuse = args.reuse_spike.absolute()
            require(reuse.parent == OUT and reuse.resolve() == reuse and reuse != out, 'Invalid reference path')
            require(shared.sha(elf) == shared.sha(reuse / 'input.elf'), 'Reference ELF differs')
            expected_command = [*spike[:-1], str(reuse / 'input.elf')]
            require(json.loads((reuse / 'spike-command.json').read_bytes()) == expected_command,
                    'Reference Spike command differs')
            files = [reuse / name for name in ('input.elf', 'spike.trace', 'spike.stdout',
                                              'spike-command.json', 'compile-command.json', 'failure.json')]
            pins = life.merge_pins(pins, {str(f): shared.sha(f) for f in files})
            trace_path = reuse / 'spike.trace'
            shared.save(out / 'spike-reference.json', dict(source=str(reuse), same_ELF=True, reexecuted=False))
        else:
            shared.save(out / 'spike-command.json', spike)
            with (out / 'spike.stdout').open('x') as stdout, trace_path.open('x') as trace:
                subprocess.run(spike, stdout=stdout, stderr=trace, check=True, timeout=60)
        result = validate(shared.parse_spike_commits(trace_path), symbols)
        shared.save(out / 'spike-validation.json', result)
        shared.check(pins)
        outputs = {str(f): shared.sha(f) for f in out.iterdir() if f.is_file()}
        shared.save(out / 'preflight-manifest.json', dict(status=result['status'], pins=pins, output_pins=outputs,
            symbols=symbols, baseline_tests=737, input_elf=str(elf), input_spike_trace=str(trace_path),
            runtime_window_verified=False, VCS_authorized=False, coverage_admitted=False))
        print(json.dumps(dict(output=str(out), seal=shared.sha(out / 'preflight-manifest.json'), result=result)))
    except Exception as error:
        shared.save(out / 'failure.json', dict(status='PREFLIGHT_FAILED', reason=str(error)))
        raise


if __name__ == '__main__':
    main()
