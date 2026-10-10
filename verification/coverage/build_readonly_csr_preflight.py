"""Exact twelve vector CSR write attempts; sealed old-image host/Spike preflight only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess

import build_opivx_vsbc_preflight as shared
from inventory_operand_debug import Design, points
from closure_point_inventory import read_xml
from build_store_fifo_burst_preflight import elf_word

life, require = shared.life, shared.require
ROOT, OUT, LLVM, SPIKE = shared.ROOT, shared.OUT, shared.LLVM, shared.SPIKE
NAME = 'vreadonly_csr_trap_recovery'
APP = ROOT / ('apps/riscv-tests/isa/rv64uv/' + NAME + '.c')
BASE = OUT / 'store-fault-flush-offline-admitted-733-parent-20261006-01'
BASE_SEAL = 'ff12f5b191546e814fde60a4e71e1112e07c769ece72bdb9a0706d512ce83a81'
SOURCE = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
SOURCE_SEAL = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
COMPILE = SOURCE.parent / 'compile.command.json'
COMPILE_SHA = '30cdd93809c183f5004767d6190ca33d1d78aed68e73dcf42d6fef793269cbb1'
BOOK = OUT / 'gap100-offline-admitted-715-20261006-01/seals.json'
BOOK_SHA = '069e9e7717e915c18ce921f583fa33bf18e7670a3f13ec12073e8bba1998a283'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
RAM = '-m0x80000000:0x200000'
CHECKS, SENTINEL = 733, 0x7193a65bc24de80f
CONFIG = [8, 0, 128, 0, 1, 2, 5, 0, 0, 0]
CONDS = (570, 572, 574, 582, 584, 586, 594, 596, 598, 606, 608, 610)
LINES = (1374, 1377, 1380, 1389, 1392, 1395, 1410, 1413, 1416, 1425, 1428, 1431)
SRC_LINES = (4677, 4682, 4687, 4715, 4720, 4725, 4778, 4783, 4788, 4819, 4824, 4829)
FAULTS = tuple('rc_fault_' + str(i) for i in range(12))
SYMBOLS = ('_start', '_end', 'tohost', 'g75_result', 'num_failed', 'trap_fail', 'g75_trap',
    'rc_handler_begin', 'rc_handler_end', 'rc_recovery', 'rc_before', 'rc_after', 'rc_rd',
    'rc_traps', 'rc_count', 'rc_index', 'rc_pc', 'rc_opcode', 'rc_source', 'rc_dump', 'rc_result') + FAULTS
STATUS = 'READONLY_CSR_HOST_SPIKE_PASS_NOT_DUT_NOT_ADMITTED'


def opcode(i):
    require(0 <= i < 12, 'Invalid case index')
    return ((0xc21, 0xc20, 0xc22)[i % 3] << 20 | (5 if i < 6 else 1) << 15 |
            (2, 3, 6, 7)[i // 3] << 12 | 28 << 7 | 0x73)


def buffer(which):
    require(which in ('rc_source', 'rc_dump', 'rc_result'), 'Unknown buffer')
    return bytes(((i - 8) * 13 + 0x27 + (3 if which == 'rc_result' else 0)) & 255
        if 8 <= i < (16 if which == 'rc_result' else 136) else 0xa5 for i in range(144))


def image_inputs():
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66 and
            plan['image'].get(str(life.IMAGE)) == IMAGE_SHA, 'Expected frozen image66 differs')
    book = life.read_bound(BOOK, BOOK_SHA)
    require(book['pins'].get(str(COMPILE)) == COMPILE_SHA, 'Historical compile identity differs')
    return life.merge_pins(plan['image'], {str(life.PLAN): life.PLAN_SEAL,
        str(BOOK): BOOK_SHA, str(COMPILE): COMPILE_SHA})


def static():
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    pins = {str(BASE / 'admission-manifest.json'): BASE_SEAL, str(SOURCE): SOURCE_SEAL}
    for name in ('combined-bits.json', 'combined-inputs.txt', 'status.json', 'evidence-pins.json'):
        pins[str(BASE / name)] = manifest['output_pins'][str(BASE / name)]
        life.read_bound(BASE / name, pins[str(BASE / name)]) if name.endswith('.json') else require(
            life.digest(BASE / name) == pins[str(BASE / name)], 'Formal input-list drift')
    bits = json.loads((BASE / 'combined-bits.json').read_bytes())
    require(len(bits['tests']) == len(set(bits['tests'])) == 733 and
            sum(map(len, bits['metrics'].values())) == 6162 and
            not any(NAME in t for t in bits['tests']), 'Formal733/universe/dedup differs')
    require(json.loads((BASE / 'status.json').read_bytes())['coverage_admitted'] is True and
        (BASE / 'combined-inputs.txt').read_text().splitlines() == [str(life.IMAGE) + '.vdb', *bits['tests']],
        'Formal733 status/prefix differs')
    sources = life.read_bound(SOURCE, SOURCE_SEAL)
    for rel in ('hardware/src/cva6_accel_first_pass_decoder.sv', 'hardware/deps/cva6/core/decoder.sv',
                'hardware/include/rvv_pkg.sv', 'hardware/include/ara_pkg.sv',
                'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv'):
        pins[str(ROOT / rel)] = sources[str(ROOT / rel)]
    snapshot = OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pins[str(snapshot)] = sources[str(ROOT / 'hardware/src/ara_dispatcher.sv')]
    d = Design(Path(str(life.IMAGE) + '.vdb'))
    pins.update({str(d.db / p): h for p, h in bits['design'].items()})
    pins[str(d.db / 'auxiliary/verilog.sourceinfo.xml')] = life.digest(d.db / 'auxiliary/verilog.sourceinfo.xml')
    require(d.hierarchy[SCOPE].get('chksum') == '1448229316', 'Dispatcher module differs')
    rows = []
    for metric, indices in (('cond', CONDS), ('line', LINES)):
        record = bits['metrics'][metric][SCOPE]
        if metric == 'cond':
            require((record['width'], record['checksum']) == (1140, '1370170966'), 'Condition shape differs')
            shape = read_xml(d.db / 'shape/cond.verilog.shape.xml')
            nodes = [n for n in shape if n.get('id') == d.hierarchy[SCOPE].get('id') and
                     n.get('chksum') == record['checksum']]
            require(len(nodes) == 1, 'Ambiguous condition shape')
            definition = nodes[0]
        else:
            definition = d.definition(SCOPE, metric)
            require(record['checksum'] == definition.get('chksum'), 'Line checksum differs')
        ps = {p['raw_index']: p for p in points(metric, definition, record['width'])}
        for case, idx in enumerate(indices):
            p = ps[idx]
            require(p['line'] == str(SRC_LINES[case] + (metric == 'line')) and
                    not int(record['bits'], 16) & (1 << (record['width'] - 1 - idx)), 'Target binding/not-zero differs')
            if metric == 'cond':
                require(p['expression'] == "(instr.itype.rs1 == '0)" and p['vector'] == '0' and
                        p['attributes']['optype'] == '16', 'CSR field predicate differs')
            rows.append(dict(case=case, scope=SCOPE, metric=metric, width=record['width'],
                checksum=record['checksum'], module_checksum='1448229316', point=p, hit733=False))
    pins = life.merge_pins(pins, image_inputs()); life.check(pins)
    return dict(baseline=733, baseline_seal=BASE_SEAL, targets=rows, target_count=24,
        branch_gain_not_assumed=True, pbit_source_unrelated=True, simulation_timeout_s=600,
        coverage_admitted=False, pins=pins)


def verify_elf(elf, symbols):
    blob = elf.read_bytes()
    require(blob[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', blob, 18)[0] == 243 and
            symbols['_start'] == 0x80000000 and symbols['tohost'] == 0x80001000 and
            0x80000000 < symbols['_end'] < 0x80100000, 'ELF ISA/entry/tohost/range differs')
    for i, name in enumerate(FAULTS):
        require(symbols[name] % 4 == 0 and elf_word(blob, symbols[name]) == opcode(i), 'Fault opcode/PC differs')
    require(elf_word(blob, symbols['rc_recovery']) == 0x0281b557, 'Recovery opcode differs')


def validate(commits, symbols, trace):
    events = re.findall(r'exception ([^,\n]+), epc (0x[0-9a-fA-F]+)', trace)
    require([(n, int(pc, 16)) for n, pc in events] ==
            [('trap_illegal_instruction', symbols[n]) for n in FAULTS] and
            trace.count('exception ') == 12, 'Exact twelve trap PCs/order required')
    require(not any(c.pc in [symbols[n] for n in FAULTS] + [symbols['trap_fail']] or
                    c.fpr_writes for c in commits), 'Illegal retirement/fatal trap/implicit FP')
    memory, terminal, handler_stores, vectors = {}, [], [], []
    handler = [c for c in commits if symbols['rc_handler_begin'] <= c.pc < symbols['rc_handler_end']]
    require(sum(c.pc == symbols['rc_handler_begin'] for c in handler) == 12, 'Handler entry count differs')
    for c in commits:
        for a, v in c.memory_accesses:
            if v is None: continue
            width = shared.store_width(c.instruction)
            require(0 <= v < 1 << (8 * width), 'Store width overflow')
            for i in range(width): memory[a + i] = (v >> (8 * i)) & 255
            if a == symbols['tohost']: terminal.append(v)
            if symbols['rc_handler_begin'] <= c.pc < symbols['rc_handler_end']:
                handler_stores.append((a, width, c.instruction))
        vectors.extend((c.pc, reg, value) for reg, value in c.vector_writes.items())
    def read(name, off=0, width=8):
        address = symbols[name] + off
        require(all(address + i in memory for i in range(width)), 'Missing oracle bytes: ' + name)
        return int.from_bytes(bytes(memory[address + i] for i in range(width)), 'little')
    require(terminal == [1] and read('g75_result', width=4) == CHECKS and
            read('g75_result', 4, 4) == read('num_failed', width=4) == 0, 'Incomplete software result')
    for i, name in enumerate(FAULTS):
        require([read('rc_traps', (i * 4 + j) * 8) for j in range(4)] ==
                [1, 2, symbols[name], opcode(i)], 'Trap ledger differs')
        require(read('rc_rd', i * 8) == SENTINEL, 'Illegal CSR changed destination')
        for array in ('rc_before', 'rc_after'):
            require([read(array, (i * 10 + j) * 8) for j in range(10)] == CONFIG, 'CSR preservation differs')
    require(read('rc_count') == 12, 'Trap count differs')
    for name in ('rc_source', 'rc_dump', 'rc_result'):
        require(bytes(read(name, i, 1) for i in range(144)) == buffer(name), 'Full memory/guard differs: ' + name)
    require(Counter(reg for _, reg, _ in vectors) == Counter({8: 1, 10: 2}), 'Vector write population differs')
    require([v for _, reg, v in vectors if reg == 8] == [int.from_bytes(buffer('rc_source')[8:136], 'little')] and
        [v for _, reg, v in vectors if reg == 10] == [int.from_bytes(bytes([0xa5] * 128), 'little'),
            int.from_bytes(buffer('rc_result')[8:136], 'little')] and
        [pc for pc, reg, _ in vectors if reg == 10][-1] == symbols['rc_recovery'], 'Vector recovery/source oracle differs')
    ledger = Counter((symbols['rc_traps'] + i * 32 + j * 8, 8) for i in range(12) for j in range(4))
    ledger[(symbols['rc_count'], 8)] = 12
    actual, frames = Counter(), []
    for a, width, word in handler_stores:
        if word & 127 == 0x23 and word >> 15 & 31 == 2:
            require(width == 8 and 0x80100000 <= a < 0x80200000, 'Handler stack write differs')
            frames.append(a)
        else: actual[(a, width)] += 1
    require(actual == ledger and len(frames) == 36 and len(set(frames)) == 3, 'Handler exact footprint differs')
    require(all(not c.vector_writes and not c.fpr_writes and set(c.gpr_writes) <= {2, 5, 6, 7} and
                set(c.csr_writes) <= {0x300, 0x341} for c in handler), 'Handler protected registers/CSRs modified')
    return dict(status='TWELVE_CSR_SPIKE_FULL_ORACLE_PASS_NOT_DUT', checks=CHECKS,
        exact_traps=12, cause=2, exact_tval_and_mepc=True, preserved_csrs_per_case=10,
        rd_preserved=True, full_buffer_bytes=432, full_vrf_bytes=384, handler_store_words=96,
        coverage_admitted=False, native_cycle_qualified=False)


def spike_command(out):
    return [str(SPIKE), '--isa=rv64gcv_zvl1024b', '--priv=msu', '--pmpregions=0', RAM,
            '-l', '--log-commits', str(out / 'input.elf')]


def verify(out, seal):
    pre = life.read_bound(out / 'preflight-manifest.json', seal)
    require(pre['status'] == STATUS and pre['case'] == NAME and pre['baseline'] == 733 and
            pre['baseline_seal'] == BASE_SEAL and pre['checks'] == CHECKS and
            pre['coverage_admitted'] is False and pre['vcs_started'] is False and
            pre['measured_raw_increment'] is None and pre['timeout_s'] == 600, 'Preflight contract differs')
    life.check(pre['pins'])
    symbols = {n: shared._elf_symbol(out / 'input.elf', LLVM / 'llvm-readelf', n) for n in SYMBOLS}
    require(symbols == pre['symbols'] and life.digest(out / 'input.elf') == pre['elf_sha256'], 'ELF identity differs')
    verify_elf(out / 'input.elf', symbols)
    require(json.loads((out / 'spike-command.json').read_bytes()) == spike_command(out), 'Spike command/RAM differs')
    require(json.loads((out / 'target-receipt.json').read_bytes()) == static(), 'Static binding replay differs')
    require(validate(shared.parse_spike_commits(out / 'spike.trace'), symbols,
                     (out / 'spike.trace').read_text()) == pre['validation'], 'Full oracle replay differs')
    return pre


def build(out):
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    receipt = static(); inc = ROOT / 'verification/tests'
    deps = [APP, inc / 'gap75_start.S', inc / 'gap75.ld', Path(__file__).resolve(),
        Path(__file__).with_name('test_readonly_csr_preflight.py'), Path(shared.__file__).resolve(),
        Path(life.__file__).resolve(), LLVM / 'clang', LLVM / 'ld.lld', LLVM / 'llvm-readelf', SPIKE]
    deps += [Path(__file__).parent / n for n in ('inventory_operand_debug.py', 'closure_point_inventory.py',
        'closure_scorecard.py', 'reviewed_20261004/audit_readonly.py', 'build_store_fifo_burst_preflight.py',
        'collect_opivx_vsbc_strict.py')]
    deps += [ROOT / 'verification/ara_verify' / n for n in ('spike_trace.py', 'trace.py', 'random_rvv.py', 'vector_commit.py')]
    pins = life.merge_pins(receipt['pins'], {str(p): life.digest(p) for p in deps})
    life.check(pins); out.mkdir(); life.save(out / 'target-receipt.json', receipt)
    command = [str(LLVM / 'clang'), '--target=riscv64-unknown-elf', '-march=rv64gcv', '-mabi=lp64d',
        '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-O2', '-fno-unroll-loops',
        '-fno-vectorize', '-fno-slp-vectorize', '-ffreestanding', '-DVLEN=1024', '-DNR_LANES=4',
        '-fuse-ld=lld', '-nostdlib', '-T' + str(inc / 'gap75.ld'), str(inc / 'gap75_start.S'),
        str(APP), '-o', str(out / 'input.elf')]
    try:
        life.save(out / 'compile-command.json', command)
        with (out / 'compile.log').open('x') as log:
            subprocess.run(command, check=True, timeout=120, stdout=log, stderr=subprocess.STDOUT)
        symbols = {n: shared._elf_symbol(out / 'input.elf', LLVM / 'llvm-readelf', n) for n in SYMBOLS}
        verify_elf(out / 'input.elf', symbols)
        old = json.loads((BASE / 'evidence-pins.json').read_bytes())
        require(life.digest(out / 'input.elf') not in {h for p, h in old.items() if p.endswith('.elf')}, 'Duplicate admitted ELF')
        life.save(out / 'linked-proof.json', dict(symbols=symbols, opcodes=[opcode(i) for i in range(12)],
            march='rv64gcv', mabi='lp64d', privilege='bare M/VS enabled/MPRV0/mie0/PMP0',
            no_implicit_FP=True, memory_option=RAM))
        life.save(out / 'spike-command.json', spike_command(out))
        with (out / 'spike.stdout').open('x') as stdout, (out / 'spike.trace').open('x') as trace:
            subprocess.run(spike_command(out), check=True, timeout=180, stdout=stdout, stderr=trace)
        result = validate(shared.parse_spike_commits(out / 'spike.trace'), symbols, (out / 'spike.trace').read_text())
        life.save(out / 'spike-validation.json', result); life.check(pins)
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in out.iterdir() if p.is_file()})
        pre = dict(status=STATUS, case=NAME, baseline=733, baseline_seal=BASE_SEAL, checks=CHECKS,
            pins=pins, symbols=symbols, validation=result, targets=receipt['targets'],
            elf_sha256=life.digest(out / 'input.elf'), timeout_s=600, old_image_files_checked=66,
            coverage_admitted=False, vcs_started=False, measured_raw_increment=None,
            rtl_changed=False, native_cycle_qualified=False)
        life.save(out / 'preflight-manifest.json', pre)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'preflight-manifest.json'), validation=result)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='PREFLIGHT_FAILED_PRESERVED_NO_RETRY', reason=str(error)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('static', 'build', 'verify'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    a = parser.parse_args(); require((a.mode == 'verify') == bool(a.seal), 'Verify alone requires seal')
    if a.mode == 'build': build(a.output.absolute())
    elif a.mode == 'verify': verify(a.output.absolute(), a.seal); print('VERIFY_PASS NO_VCS NOT_ADMITTED')
    else: life.save(a.output.absolute(), static()); print('STATIC_ONLY seal=' + life.digest(a.output.absolute()))
