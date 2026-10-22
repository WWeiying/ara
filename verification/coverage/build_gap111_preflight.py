"""One same-PTE-line cache replay hypothesis; software-only preflight."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import build_gap98_preflight as shared
import run_gap95_simulation as life
from closure_point_inventory import read_xml
from inventory_ptw_pmp0_candidates import candidates

ROOT, OUT, require = shared.ROOT, shared.OUT, shared.require
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vgap111_pte_line_collision.c'
BASE = OUT / 'queue-mask-offline-admitted-740-agent-20261007-01'
BASE_SHA = '752d493c5fa8179ddd414d7810da479b1a56341a1600dff56c5b5afa0a3304b5'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
CACHE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_cache_wt.i_cache_subsystem.i_wt_dcache'
SOURCES = (
    'hardware/deps/cva6/core/cache_subsystem/wt_dcache_ctrl.sv',
    'hardware/deps/cva6/core/cache_subsystem/wt_dcache_missunit.sv',
    'hardware/deps/cva6/core/cache_subsystem/wt_dcache_mem.sv',
    'hardware/deps/cva6/core/cache_subsystem/wt_dcache.sv',
    'hardware/deps/cva6/core/load_store_unit.sv',
    'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv',
    'hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/src/ara_soc.sv',
)
SYMBOLS = ('tohost', 'g75_result', 'num_failed', 'g111_root', 'g111_mid', 'g111_leaf',
           'g111_page', 'g111_entry', 'g111_second', 'g111_ecall', 'g111_probe',
           'g111_warm', 'g111_out', 'g111_trap', 'g111_count')
GUARD = 0x5a3c719de4b208f6


def expected(symbols):
    pte = ((symbols['g111_second'] >> 12) << 10) | 0xcb
    return [pte, pte ^ 0x123, pte + 17, pte, 0, 0, symbols['g111_leaf'] + 32, 2]


def geometry(symbols):
    require(symbols['g111_leaf'] % 4096 == symbols['g111_page'] % 4096 == 0,
            'Unaligned table/code')
    require(symbols['g111_entry'] == symbols['g111_probe'] == symbols['g111_page'] + 4032
            and symbols['g111_second'] == symbols['g111_page'] + 4096
            and symbols['g111_ecall'] == symbols['g111_second'] + 40, 'Instruction layout drift')
    first, second, warm = (symbols['g111_leaf'] + i for i in (24, 32, 512))
    require(first // 32 != second // 32 and second // 32 != warm // 32, 'PTE warm-line overlap')
    return dict(line_bytes=32, instruction_PTE_slots=[3, 4], first_PTE=first, second_PTE=second,
                data_probe=second, warm_data_address=warm,
                architectural_same_line_proven=True, runtime_coldness_proven=False,
                runtime_overlap_proven=False)


def validate(commits, symbols):
    linked = geometry(symbols)
    require(not any(c.vector_writes for c in commits), 'Unexpected vector writer')
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a, v in c.memory_accesses if a == symbols['tohost'] and v is not None]
    require(terminal == [1], 'Wrong/duplicate terminal')
    require(writes.get(symbols['g75_result']) == 26 and writes.get(symbols['g75_result'] + 4) == 0
            and writes.get(symbols['num_failed']) == 0 and writes.get(symbols['g111_count']) == 1,
            'Incomplete signature')
    require([writes.get(symbols['g111_out'] + 8 * i) for i in range(10)] ==
            [GUARD, *expected(symbols), GUARD], 'Independent output/guards differ')
    trap = [writes.get(symbols['g111_trap'] + 8 * i) for i in range(4)]
    require(trap[:3] == [9, 0x40004028, 0] and trap[3] is not None
            and trap[3] & 0x1800 == 0x800, 'Trap ledger differs')
    causes = [v for c in commits if c.instruction >> 20 == 0x342 and c.instruction & 127 == 0x73
              for v in c.gpr_writes.values()]
    require(causes == [9], 'Unexpected trap')
    alias = [c for c in commits if 0x40003000 <= c.pc < 0x40005000]
    require([c.pc for c in alias] == list(range(0x40003fc0, 0x40004028, 4)),
            'Incomplete aliased instruction retirement')
    probe = alias[0]
    require(probe.instruction == 0x0202b503 and list(probe.gpr_writes.values()) == [expected(symbols)[0]],
            'Probe opcode/result differs')
    warm = [c for c in commits if c.pc == symbols['g111_warm']]
    require(len(warm) == 1 and list(warm[0].gpr_writes.values()) == [0], 'Data translation warm read differs')
    required = {symbols['g111_root'] + 8: ((symbols['g111_mid'] >> 12) << 10) | 1,
                symbols['g111_root'] + 16: ((0x80000000 >> 12) << 10) | 0xcf,
                symbols['g111_mid']: ((symbols['g111_leaf'] >> 12) << 10) | 1,
                symbols['g111_leaf'] + 24: ((symbols['g111_page'] >> 12) << 10) | 0xcb,
                symbols['g111_leaf'] + 32: expected(symbols)[0]}
    require(all(writes.get(a) == v for a, v in required.items()), 'Linked page-table bytes differ')
    prefix = []
    for c in commits:
        if not prefix and c.pc != 0x80000000:
            continue
        prefix.append(c)
        if (symbols['tohost'], 1) in c.memory_accesses:
            break
    require(prefix and (symbols['tohost'], 1) in prefix[-1].memory_accesses, 'No complete terminal prefix')
    return dict(status='GAP111_SPIKE_SOFTWARE_PASS_NOT_FSM_PROOF', checks=26, expected_traps=1,
                output_bytes=80, trap_bytes=32, vector_destination_instructions=0,
                scalar_counts=dict(instructions=len(prefix), GPR_writes=sum(len(c.gpr_writes) for c in prefix),
                                   memory_accesses=sum(len(c.memory_accesses) for c in prefix)),
                linked_geometry=linked, replay_observed=False, coverage_admitted=False)


def targets(bitmap, shape):
    require(len(bitmap['tests']) == len(set(bitmap['tests'])) == 740, 'Not unique formal740')
    result = []
    for port in (0, 1):
        scope = CACHE + '.gen_rd_ports[%d].genblk1.i_wt_dcache_ctrl' % port
        record = bitmap['metrics']['fsm'][scope]
        require(record['width'] == 28 and record['checksum'] == '3476102610', 'Target shape differs')
        nodes = [n for n in shape.iter('fsmdef') if n.get('chksum') == record['checksum']
                 and any(i.get('name') == scope for i in n.findall('fsminst'))]
        require(len(nodes) == 1, 'Missing/ambiguous compiled FSM scope')
        rows = candidates(nodes[0])
        require(len(rows) == 28, 'FSM offsets differ')
        for index in (6, 7, 16, 21, 23, 24, 27):
            row = rows[index]
            require(not int(record['bits'], 16) & (1 << (27 - index)), 'Target already covered')
            require(row.get('name') in ('REPLAY_READ', 'REPLAY_REQ') or
                    row.get('source') in ('READ', 'MISS_REQ', 'REPLAY_READ', 'REPLAY_REQ'),
                    'Unexpected target identity')
            result.append(dict(scope=scope, metric='fsm', checksum=record['checksum'], width=28,
                               compiled=row, hit_before=False, native_exclusion_identity_claimed=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    bitmap = life.read_bound(BASE / 'combined-bits.json', manifest['output_pins'][str(BASE / 'combined-bits.json')])
    status = life.read_bound(BASE / 'status.json', manifest['output_pins'][str(BASE / 'status.json')])
    require(status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and status['aggregate_passed'] == 740,
            'Not formal740 PASS')
    historical = json.loads((BUILD / 'build-source-pins.json').read_bytes())
    pins = {str(ROOT / s): historical[str(ROOT / s)] for s in SOURCES}
    template = OUT / 'gap99-csr-satp-mprv-preflight-707-20261006-01/compile-command.json'
    command = json.loads(template.read_bytes())
    previous = str(ROOT / 'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')
    require(command.count(previous) == 1 and command[-2] == '-o', 'Compile template differs')
    command = [str(APP) if x == previous else x for x in command]
    command[-1] = str(out / 'input.elf')
    for p in (APP, Path(__file__).resolve(), Path(__file__).with_name('test_build_gap111_preflight.py'),
              BASE / 'admission-manifest.json', BASE / 'combined-bits.json', BASE / 'status.json',
              BUILD / 'build-source-pins.json', template, ROOT / 'verification/tests/gap75_start.S',
              ROOT / 'verification/tests/gap75.ld', shared.SPIKE, shared.LLVM / 'clang',
              shared.LLVM / 'llvm-readelf', shared.LLVM / 'llvm-objdump', Path(shared.__file__).resolve(),
              Path(life.__file__).resolve()):
        digest = shared.sha(p)
        require(str(p) not in pins or pins[str(p)] == digest, 'Conflicting pin')
        pins[str(p)] = digest
    for p in (ROOT / 'apps/riscv-tests/isa/macros').rglob('*'):
        if p.is_file():
            pins[str(p)] = shared.sha(p)
    shape = BUILD / 'sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml'
    pins[str(shape)] = bitmap['design']['shape/fsm.verilog.shape.xml']
    shared.check(pins)
    selection = targets(bitmap, read_xml(shape))
    config_text = (ROOT / SOURCES[7]).read_text()
    require('CVA6ConfigDcacheLineWidth = 256;' in config_text, 'Not frozen 32-byte cache line')
    out.mkdir()
    shared.save(out / 'target-before.json', dict(baseline=740, manifest_sha256=BASE_SHA, targets=selection))
    shared.save(out / 'compile-command.json', command)
    with (out / 'compile.log').open('x') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=90, check=True)
    elf = out / 'input.elf'
    symbols = {k: shared._elf_symbol(elf, shared.LLVM / 'llvm-readelf', k) for k in SYMBOLS}
    with (out / 'input.disasm').open('x') as stream:
        subprocess.run([str(shared.LLVM / 'llvm-objdump'), '-d', str(elf)], stdout=stream, check=True, timeout=30)
    spike = [str(shared.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
             '-l', '--log-commits', str(elf)]
    shared.save(out / 'spike-command.json', spike)
    with (out / 'spike.stdout').open('x') as stdout, (out / 'spike.trace').open('x') as trace:
        subprocess.run(spike, stdout=stdout, stderr=trace, check=True, timeout=60)
    validation = validate(shared.parse_spike_commits(out / 'spike.trace'), symbols)
    shared.save(out / 'spike-validation.json', validation)
    shared.check(pins)
    outputs = {str(p): shared.sha(p) for p in out.iterdir() if p.is_file()}
    shared.save(out / 'preflight-manifest.json', dict(schema='GAP111_SAME_PTE_LINE_PREFLIGHT_V1',
        status=validation['status'], baseline_tests=740, baseline_manifest_sha256=BASE_SHA,
        pins=pins, output_pins=outputs, input_elf=str(elf), input_spike_trace=str(out / 'spike.trace'),
        symbols=symbols, validation=validation, VCS_authorized=False, coverage_admitted=False,
        runtime_overlap_proven=False, VCS_timeout_proposal_seconds=180,
        hypothesis='Port0 Iwalk and port1 scalar data read collide on the exact same leaf-PTE cache line.',
        differentiators=['mshr_rdrd_collision_d[0/1] and miss_replay_o[0/1]',
                         'wr_cl_vld_i or !rd_ack_q with READ/REPLAY_READ',
                         'compiled FSM replay targets versus independently checked architecture'],
        prior_case_difference='Previous crossline/SFENCE cases read separate data lines; no same-PTE-line ownership.',
        no_gain_action='Preserve functional diagnostic; do not vary timing/layout or admit zero gain.',
        checker_contract=dict(full_scalar_terminal=True, compressed_memory_no_skip=True,
            exact_traps=1, independent_signature_checks=26, output_bytes=80, trap_bytes=32,
            vector='Zero activity; retain UNOBSERVABLE, not PASS', CVX='Exact zero contract',
            FSM='Raw compiled targets only until observed; no native exclusion or percentage claim')))
    print(json.dumps(dict(output=str(out), seal=shared.sha(out / 'preflight-manifest.json'), validation=validation)))


if __name__ == '__main__':
    main()
