"""One standalone software reference; no VCS/DVE or automatic admission."""
import argparse
import json
from pathlib import Path
import re
import subprocess

import build_opivx_vsbc_preflight as shared
from inventory_operand_debug import Design, points
from build_store_fifo_burst_preflight import elf_word

life, ROOT, OUT = shared.life, shared.ROOT, shared.OUT
require = shared.require
NAME = 'vstore_fault_flush_recovery'
APP = ROOT / ('apps/riscv-tests/isa/rv64uv/' + NAME + '.c')
BASE = OUT / 'pure-war-offline-admitted-731-parent-20261006-01'
BASE_SEAL = '79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
SYMBOLS = ('tohost', 'g75_result', 'num_failed', 'trap_fail', 'g75_trap', 'sff_fault',
           'sff_recovery', 'sff_a', 'sff_b', 'sff_dest', 'sff_dump_a', 'sff_dump_b',
           'sff_index', 'sff_trap', 'sff_count', 'sff_marker', 'sff_cfg', 'sff_env', '_end')
GUARD, BAD, CHECKS = 0xd6a52c7193e80fb4, 0xe0000000, 134
OFFSETS = (0, 6, 16, 24, 32, 40, 48, 56)


def expected(buffer, index):
    if index < 2 or index >= 18 or buffer == 2 and index >= 10:
        return GUARD
    source = buffer in (1, 2, 4)
    return (0x7928d60be14c953a if source else 0x136fe802a5974cdb) ^ (0x01030507090b0d0f * (index - 2))


def static():
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    pins = {str(BASE / 'admission-manifest.json'): BASE_SEAL}
    for name in ('combined-bits.json', 'combined-inputs.txt', 'status.json', 'evidence-pins.json'):
        pins[str(BASE / name)] = manifest['output_pins'][str(BASE / name)]
    life.check(pins)
    bits = json.loads((BASE / 'combined-bits.json').read_bytes())
    require(len(bits['tests']) == 731 and len(set(bits['tests'])) == 731 and
            sum(map(len, bits['metrics'].values())) == 6162, 'Not exact formal731')
    require(json.loads((BASE / 'status.json').read_bytes())['coverage_admitted'] is True,
            'Baseline not admitted')
    require((BASE / 'combined-inputs.txt').read_text().splitlines() == [str(life.IMAGE) + '.vdb', *bits['tests']],
            'Formal prefix differs')
    sources = life.read_bound(BUILD / 'build-source-pins.json',
                             '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    pins[str(BUILD / 'build-source-pins.json')] = life.digest(BUILD / 'build-source-pins.json')
    for rel in ('hardware/src/vlsu/vstu.sv', 'hardware/src/vlsu/vlsu.sv', 'hardware/src/vlsu/addrgen.sv',
                'hardware/src/ara_sequencer.sv', 'hardware/src/ara_soc.sv',
                'hardware/src/lane/operand_requester.sv', 'hardware/src/lane/operand_queues_stage.sv',
                'hardware/deps/axi/src/axi_xbar_unmuxed.sv', 'hardware/deps/axi/src/axi_err_slv.sv',
                'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv'):
        pins[str(ROOT / rel)] = sources[str(ROOT / rel)]
    for name in ('lane_sequencer.sv', 'ara_dispatcher.sv'):
        original = ROOT / 'hardware/src' / ('lane/' if name == 'lane_sequencer.sv' else '') / name
        pins[str(OUT / 'old-image-source-evidence-20261006-01' / name)] = sources[str(original)]
    for p in (BUILD / 'compile.command.json', life.IMAGE):
        pins[str(p)] = life.digest(p)
    d = Design(Path(str(life.IMAGE) + '.vdb'))
    pins.update({str(d.db / p): h for p, h in bits['design'].items()})
    p = d.db / 'auxiliary/verilog.sourceinfo.xml'; pins[str(p)] = life.digest(p)
    target = next(p for p in points('line', d.definition(SCOPE, 'line'), bits['metrics']['line'][SCOPE]['width'])
                  if p['raw_index'] == 54)
    row = bits['metrics']['line'][SCOPE]
    require(target['line'] == '583' and target['expression'] == "store_b_exception_d.valid = 1'b1;" and
            not int(row['bits'], 16) & (1 << (row['width'] - 1 - 54)), 'Primary target differs/already hit731')
    branch_row = bits['metrics']['branch'][SCOPE]
    branch = next(p for p in points('branch', d.definition(SCOPE, 'branch'), branch_row['width']) if p['raw_index'] == 43)
    existing = [t for t in bits['tests'] if any(n in t for n in
        ('vindexed_fault_vstart', 'vstore_axi_error', 'gap70_indexed_fault_recover', 'sv39_gap34_store'))]
    require(existing and not any(NAME in t for t in bits['tests']), 'Deduplication failed')
    life.check(pins)
    return dict(baseline=731, baseline_seal=BASE_SEAL, primary_target=dict(scope=SCOPE, metric='line',
        width=row['width'], checksum=row['checksum'], module_checksum=d.hierarchy[SCOPE].get('chksum'),
        point=target, hit731=False), conditional_branch_witness=dict(scope=SCOPE, metric='branch',
        width=branch_row['width'], checksum=branch_row['checksum'], point=branch,
        hit731=bool(int(branch_row['bits'], 16) & (1 << (branch_row['width'] - 1 - 43))),
        exact_case_vector_outcome_not_assumed=True), existing_related_VDBs=existing,
        FIFO_eight_points_targeted=False, expected_gain_not_guaranteed=True, simulation_timeout_s=600,
        native_internal_timing_observed=False, coverage_admitted=False, pins=pins)


def validate(commits, symbols, text):
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    require(not any(c.pc == symbols['trap_fail'] or c.fpr_writes for c in commits), 'Unexpected trap/FP writes')
    require([v for c in commits for a, v in c.memory_accesses if a == symbols['tohost'] and v is not None] == [1],
            'Missing/extra/failing tohost')
    require(writes.get(symbols['g75_result']) == CHECKS and writes.get(symbols['g75_result'] + 4) == 0 and
            writes.get(symbols['num_failed']) == 0 and writes.get(symbols['sff_count']) == 1 and
            writes.get(symbols['sff_marker']) == 1, 'Incomplete software signature')
    buffers = ('sff_a', 'sff_b', 'sff_dest', 'sff_dump_a', 'sff_dump_b')
    for b, name in enumerate(buffers):
        require(all(writes.get(symbols[name] + 8 * i) == expected(b, i) for i in range(20)),
                'Source/destination/VRF dump/guard differs: ' + name)
    require(all(writes.get(symbols['sff_index'] + 2 * i) == OFFSETS[i] for i in range(8)), 'Index footprint differs')
    trap = [writes.get(symbols['sff_trap'] + 8 * i) for i in range(10)]
    require(all(v is not None for v in trap), 'Incomplete trap ledger')
    trap[7] &= 0x21800
    require(trap == [1, 7, BAD, symbols['sff_fault'], 0, 8, 24, 0x1800, 0, 0], 'Wrong exact M trap/privilege contract')
    for slot in range(2):
        require([writes.get(symbols['sff_cfg'] + slot * 32 + i * 8) for i in range(4)] == [8, 24, 0, 128],
                'Wrong vector context')
        require([writes.get(symbols['sff_env'] + slot * 24 + i * 8) for i in range(3)] == [0, 0, 0],
                'Wrong bare-M/MPRV/interrupt environment')
    traps = [line for line in text.splitlines() if re.search(r'\bexception\b.*\btrap_', line)]
    require(len(traps) == 1 and 'trap_store_access_fault' in traps[0], 'Unexpected Spike trap inventory')
    recovery = [c for c in commits if c.pc == symbols['sff_recovery']]
    require(len(recovery) == 1 and recovery[0].vector_vl == 8 and recovery[0].vector_sew == 64 and
            recovery[0].vector_vstart == 0, 'Recovery context missing/different')
    return dict(status='HOST_SPIKE_ARCHITECTURE_PASS_NOT_DUT', checks=CHECKS, buffers_words=100,
        exact_traps=1, cause=7, tval=BAD, fault_vstart=0, recovery_words=8,
        trap_information_preserved=True, whole_ISA_qualified=False, native_B_error_plus_addr_fault_measured=False)


def build(out):
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh independent output required')
    receipt = static(); inc = ROOT / 'verification/tests'
    deps = [APP, inc / 'store_fault_flush_reference.h', inc / 'store_fault_flush_host.c',
        inc / 'gap75_start.S', inc / 'gap75.ld', Path(__file__).resolve(),
        Path(__file__).with_name('test_build_store_fault_flush_preflight.py'), Path(shared.__file__).resolve(),
        Path(life.__file__).resolve(), shared.LLVM / 'clang', shared.LLVM / 'ld.lld',
        shared.LLVM / 'llvm-readelf', shared.SPIKE, Path('/usr/bin/cc'), Path('/usr/bin/cc').resolve()]
    deps += [ROOT / 'verification/ara_verify' / n for n in ('spike_trace.py', 'trace.py', 'random_rvv.py', 'vector_commit.py')]
    deps += [Path(__file__).resolve().parent / n for n in ('build_store_fifo_burst_preflight.py', 'inventory_operand_debug.py',
              'closure_point_inventory.py', 'closure_scorecard.py', 'reviewed_20261004/audit_readonly.py')]
    pins = life.merge_pins(receipt['pins'], {str(p): life.digest(p) for p in deps})
    life.check(pins); out.mkdir()
    life.save(out / 'target-receipt.json', receipt)
    commands = {
        'host': ['/usr/bin/cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(inc / 'store_fault_flush_host.c'), '-o', str(out / 'host')],
        'compile': [str(shared.LLVM / 'clang'), '--target=riscv64-unknown-elf', '-march=rv64gcv', '-mabi=lp64d',
          '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-O2', '-fno-unroll-loops', '-fno-vectorize',
          '-fno-slp-vectorize', '-ffreestanding', '-DVLEN=1024', '-DNR_LANES=4', '-I' + str(inc),
          '-fuse-ld=lld', '-nostdlib', '-T' + str(inc / 'gap75.ld'), str(inc / 'gap75_start.S'), str(APP), '-o', str(out / 'input.elf')],
        'spike': [str(shared.SPIKE), '--isa=rv64gcv_zvl1024b', '--priv=msu', '--pmpregions=0', '-l', '--log-commits', str(out / 'input.elf')]}
    try:
        for name in ('host', 'compile'):
            life.save(out / (name + '-command.json'), commands[name])
            with (out / (name + '.log')).open('x') as log:
                subprocess.run(commands[name], check=True, timeout=120, stdout=log, stderr=subprocess.STDOUT)
        host = subprocess.run([str(out / 'host')], check=True, timeout=10, capture_output=True, text=True).stdout
        require(host.splitlines() == [f'B {b} {i} {expected(b,i):016x}' for b in range(5) for i in range(20)] +
                [f'I {i} {v}' for i,v in enumerate(OFFSETS)], 'Independent host oracle differs')
        (out / 'host-reference.txt').write_text(host)
        elf = out / 'input.elf'
        symbols = {n: shared._elf_symbol(elf, shared.LLVM / 'llvm-readelf', n) for n in SYMBOLS}
        blob = elf.read_bytes(); fault = elf_word(blob, symbols['sff_fault']); recovery = elf_word(blob, symbols['sff_recovery'])
        require(fault & 127 == 0x27 and fault >> 26 & 3 == 3 and fault >> 12 & 7 == 5 and
                fault >> 20 & 31 == 4 and fault >> 7 & 31 == 8 and fault >> 25 & 1 == 1,
                'Wrong legal ordered-indexed fault instruction')
        require(recovery & 127 == 0x27 and recovery >> 26 & 3 == 0 and recovery >> 12 & 7 == 7 and
                recovery >> 7 & 31 == 16, 'Wrong recovery store')
        require(0x80000000 <= symbols['_end'] < 0x80200000, 'Outside fixed 2MiB image RAM')
        evidence = json.loads((BASE / 'evidence-pins.json').read_bytes())
        require(life.digest(elf) not in {h for p,h in evidence.items() if p.endswith('.elf')}, 'Duplicate admitted ELF')
        life.save(out / 'linked-proof.json', dict(symbols=symbols, fault_opcode=fault, recovery_opcode=recovery,
            ELF_not_admitted=True, privilege='bare M, MPRV0, satp0, PMP0', trap_ledger_bytes=80))
        life.save(out / 'spike-command.json', commands['spike'])
        with (out / 'spike.stdout').open('x') as stdout, (out / 'spike.trace').open('x') as trace:
            subprocess.run(commands['spike'], check=True, timeout=180, stdout=stdout, stderr=trace)
        trace = (out / 'spike.trace').read_text()
        validation = validate(shared.parse_spike_commits(out / 'spike.trace'), symbols, trace)
        life.save(out / 'spike-validation.json', validation)
        life.check(pins)
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in out.iterdir() if p.is_file()})
        pre = dict(status='STORE_FAULT_FLUSH_HOST_SPIKE_PASS_NOT_DUT_NOT_ADMITTED', case=NAME,
            baseline=731, baseline_seal=BASE_SEAL, pins=pins, validation=validation, symbols=symbols,
            input_elf_sha256=life.digest(elf), simulation_timeout_s=600, vcs_started=False,
            coverage_admitted=False, raw_gain=None, native_timing_observed=False)
        life.save(out / 'preflight-manifest.json', pre)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'preflight-manifest.json'), validation=validation)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='PREFLIGHT_FAILED_PRESERVED_NO_RETRY', reason=str(error)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output.absolute())
