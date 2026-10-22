"""One fixed ordinary DIV/indexed-load pure WAR: host and Spike, never VCS."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

import build_opivx_vsbc_preflight as shared
import collect_opivx_vsbc_strict as strict
from inventory_operand_debug import Design, points
from closure_point_inventory import definition, read_xml

life, require = shared.life, shared.require
ROOT, OUT, LLVM, SPIKE = shared.ROOT, shared.OUT, shared.LLVM, shared.SPIKE
NAME = 'vpure_war_div_indexed_load'
APP = ROOT / 'apps/riscv-tests/isa/rv64uv' / (NAME + '.c')
BASE = OUT / 'gap106-offline-admitted-727-parent-20261006-01'
BASE_SEAL = '918a5cb4b471e1106a10b4e1c76eb996e9803a44c8d4566c0a038d3b697e29d2'
REVIEW = OUT / 'rvv-operand-pure-war-static-727-20261006-01.json'
REVIEW_SEAL = 'af1bd02059106e0b429b47028aba1805c08d1317c9d8fc03e3192df14a1c048a'
STATUS = 'PURE_WAR_FULL_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS'
CHECKS, DIV, LOAD = 1765, 0x8282EC57, 0x07050407
SYMBOLS = ('tohost', 'g75_result', 'num_failed', 'trap_fail', 'gpw_seed', 'gpw_dump',
           'gpw_base', 'gpw_cfg', 'gpw_restore', 'gpw_div', 'gpw_load', 'gpw_init_begin', 'gpw_init_end')


def expected_register(reg, phase=0):
    require(0 <= reg < 32 and phase in (0, 1), 'Oracle range')
    if 8 <= reg < 16:
        start = (reg - 8) * 128
        return bytes(((73 * ((29 * i + 7) % 128) + 41) % 256) if phase else
                     (17 * i + 193) % 256 for i in range(start, start + 128))
    if 16 <= reg < 24:
        return bytes((29 * i + 7) % 128 for i in range((reg - 16) * 128, (reg - 15) * 128))
    if phase and reg >= 24:
        return bytes(((17 * i + 193) % 256) // 3 for i in range((reg - 24) * 128, (reg - 23) * 128))
    return bytes((reg * 29 + b * 13 + ((b // 8) ^ reg) * 7 + 0x35) % 256 for b in range(128))


def target_binding():
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    for name in ('combined-bits.json', 'status.json', 'evidence-pins.json'):
        p = BASE / name
        life.read_bound(p, manifest['output_pins'][str(p)])
    bits = json.loads((BASE / 'combined-bits.json').read_bytes())
    require(len(bits['tests']) == len(set(bits['tests'])) == 727, 'Not exact727')
    status = json.loads((BASE / 'status.json').read_bytes())
    require(status['coverage_admitted'] is True and status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY', 'Base not formal')
    review = life.read_bound(REVIEW, REVIEW_SEAL)
    design = Design(Path(str(life.IMAGE) + '.vdb'))
    life.check({str(design.db / p): h for p, h in bits['design'].items()})
    cond = read_xml(design.db / 'shape/cond.verilog.shape.xml')
    targets = review['zero_targets']
    scopes = {f'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[{i}].i_lane.i_operand_requester' for i in range(4)}
    require(len(targets) == 4 and {t['scope'] for t in targets} == scopes, 'Not exact four requester lanes')
    for t in targets:
        require((t['metric'], t['raw_index'], t['width'], t['checksum']) ==
                ('cond', 1059, 1256, '1592560956'), 'Target metric/shape')
        row = bits['metrics']['cond'][t['scope']]
        require((row['width'], row['checksum']) == (1256, '1592560956'), '727 shape drift')
        require(not int(row['bits'], 16) & (1 << (1256 - 1 - 1059)), 'Target already hit727')
        node = definition(cond, design.hierarchy[t['scope']], row['checksum'])
        match = [p for p in points('cond', node, 1256) if p['raw_index'] == 1059]
        require(match == [t['point']], 'Exact compiled point/expression drift')
        require((match[0]['native_id'], match[0]['file_id'], match[0]['line'], match[0]['row'], match[0]['vector']) ==
                ('402', '552', '496', 2, '010'), 'Wrong requester port/predicate')
    return targets, bits


def verify_elf(blob, symbols):
    require(blob[:6] == b'\x7fELF\x02\x01', 'Not ELF64 LE')
    h = struct.unpack_from('<HHIQQQIHHHHHH', blob, 16)
    require(h[:3] == (2, 243, 1) and h[10] == 64 and h[5] + h[11] * 64 <= len(blob), 'ELF header')
    require(symbols['gpw_load'] == symbols['gpw_div'] + 4, 'DIV/load not exactly adjacent')
    for name, word in (('gpw_div', DIV), ('gpw_load', LOAD)):
        pc, owners = symbols[name], []
        require(pc % 4 == 0, 'PC alignment')
        for i in range(h[11]):
            sec = struct.unpack_from('<IIQQQQIIQQ', blob, h[5] + i * 64)
            if sec[1] == 1 and sec[2] & 4 and sec[3] <= pc and pc + 4 <= sec[3] + sec[5]:
                owners.append(struct.unpack_from('<I', blob, sec[4] + pc - sec[3])[0])
        require(owners == [word], 'Exact executable word differs: ' + name)


def signatures(read, symbols):
    require(read('g75_result', width=4) == CHECKS and
            read('g75_result', 4, 4) == read('num_failed', width=4) == 0, 'Checks/failure signature')
    for phase in range(2):
        require([read('gpw_cfg', (phase * 6 + i) * 8) for i in range(6)] ==
                [1024, 3, 0, 4, 117, 128], 'VL/vtype/vstart/vcsr/fcsr/vlenb differs')
        for reg in range(32):
            actual = b''.join(read('gpw_dump', ((phase * 32 + reg) * 18 + w) * 8).to_bytes(8, 'little') for w in range(18))
            require(actual == b'\xa5' * 8 + expected_register(reg, phase) + b'\xa5' * 8, 'Full VRF/guard differs')
    for reg in range(32):
        actual = b''.join(read('gpw_seed', (reg * 18 + w) * 8).to_bytes(8, 'little') for w in range(18))
        require(actual == b'\xa5' * 8 + expected_register(reg) + b'\xa5' * 8, 'Source seed/guard differs')
    base = b''.join(read('gpw_base', w * 8).to_bytes(8, 'little') for w in range(18))
    require(base == b'\xa5' * 8 + bytes((73 * i + 41) % 256 for i in range(128)) + b'\xa5' * 8, 'Load base/source guard differs')
    wanted = [0, 0, 0, 0, 0, symbols['trap_fail'], 0]
    require([read('gpw_restore', i * 16) for i in range(7)] == wanted and
            [read('gpw_restore', i * 16 + 8) for i in range(7)] == wanted, 'CSR/mtvec/mscratch restoration differs')


def validate(commits, symbols, trace):
    require('exception ' not in trace and not any(c.pc == symbols['trap_fail'] for c in commits), 'Unexpected exception/fatal handler')
    memory, reads, terminal, gpr, pair = {}, set(), [], {}, []
    for pos, c in enumerate(commits):
        if c.pc in (symbols['gpw_div'], symbols['gpw_load']):
            pair.append((pos, c))
            if c.pc == symbols['gpw_div']:
                require(gpr.get(5) == 3, 'DIV scalar divisor differs')
            else:
                require(gpr.get(10) == symbols['gpw_base'] + 8, 'Indexed load base differs')
        gpr.update(c.gpr_writes)
        for address, value in c.memory_accesses:
            if value is None:
                access = strict.scalar_memory(c.instruction)
                if access and access[0] == 'read':
                    reads.update(range(address, address + access[1]))
                else:
                    require(c.instruction & 127 == 7 and (c.instruction >> 12) & 7 == 0, 'Unknown memory read instruction')
                continue
            width = shared.store_width(c.instruction)
            require(0 <= value < 1 << (8 * width), 'Store value/width')
            for i in range(width):
                memory[address + i] = (value >> (8 * i)) & 255
            if address == symbols['tohost']:
                terminal.append(value)
    require(terminal == [1], 'Terminal tohost is not exact PASS')
    require(len(pair) == 2 and pair[1][0] == pair[0][0] + 1 and
            [(c.pc, c.instruction) for _, c in pair] ==
            [(symbols['gpw_div'], DIV), (symbols['gpw_load'], LOAD)], 'Retired DIV/load pair identity/adjacency')
    def read(name, offset=0, width=8):
        address = symbols[name] + offset
        require(all(address + i in memory for i in range(width)), 'Missing signature bytes: ' + name)
        return int.from_bytes(bytes(memory[address + i] for i in range(width)), 'little')
    signatures(read, symbols)
    for name, size in (('gpw_dump', 2 * 32 * 144), ('gpw_seed', 32 * 144), ('gpw_base', 144)):
        require(set(range(symbols[name], symbols[name] + size)) <= reads, 'Full software readback absent: ' + name)
    init = [c for c in commits if symbols['gpw_init_begin'] <= c.pc < symbols['gpw_init_end'] and c.vector_writes]
    require(len(init) == 32, 'Not full32 initialization')
    for reg, c in enumerate(init):
        require(c.vector_writes == {reg: int.from_bytes(expected_register(reg), 'little')}, 'Initial VRF value/identity differs')
    require(all(commits.index(c) < pair[0][0] for c in init), 'Initialization after DIV')
    require(pair[0][1].vector_writes == {r: int.from_bytes(expected_register(r, 1), 'little') for r in range(24, 32)},
            'DIV old source quotient differs')
    require(pair[1][1].vector_writes == {r: int.from_bytes(expected_register(r, 1), 'little') for r in range(8, 16)},
            'Indexed load full group differs')
    require(sum(bool(c.vector_writes) for c in commits) == 34, 'Extra/missing vector writer')
    return dict(status='PURE_WAR_SPIKE_FULL_ORACLE_PASS_NOT_DUT', checks=CHECKS,
                exceptions=0, snapshots=2, full_vrf_registers=32, observed_vrf_bytes=8192,
                vrf_guard_bytes=1024, source_bytes=4224, source_guard_bytes=528,
                vector_write_instructions=34, known_vector_write_bytes=6144,
                DIV_old_source_bytes=1024, indexed_load_bytes=1024, VL=1024, vstart=0,
                CSR_restoration=True, skipped_unknown_bytes=0, coverage_admitted=False)


def verify(out, seal):
    pre = life.read_bound(out / 'preflight-manifest.json', seal)
    require(pre['status'] == STATUS and pre['case'] == NAME and pre['baseline_tests'] == 727 and
            pre['coverage_admitted'] is False and pre['vcs_started'] is False and pre['ZCC_executed'] is False and
            pre['backend_budget_seconds'] == 600, 'Preflight contract')
    life.check(pre['pins'])
    require(pre['targets'] == target_binding()[0], '727 target binding differs')
    require(not any('ZCC' in p or 'Terapines' in p for p in pre['pins']), 'Forbidden tool pin')
    symbols = {n: shared._elf_symbol(out / 'input.elf', LLVM / 'llvm-readelf', n) for n in SYMBOLS}
    require(symbols == pre['symbols'], 'ELF symbol drift')
    verify_elf((out / 'input.elf').read_bytes(), symbols)
    commits = shared.parse_spike_commits(out / 'spike.trace')
    require(validate(commits, symbols, (out / 'spike.trace').read_text()) == pre['validation'], 'Complete oracle replay differs')
    require(strict.reference_counts(commits, symbols) == pre['reference_counts'], 'Full scalar population differs')
    return pre


def build(out):
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct directory required')
    targets, bits = target_binding()
    review = life.read_bound(REVIEW, REVIEW_SEAL)
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66 and plan['image'][str(life.IMAGE)] ==
            '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3', 'Frozen simv66 differs')
    pins = life.merge_pins(review['pins'], plan['image'])
    pins = life.merge_pins(pins, {str(REVIEW): REVIEW_SEAL, str(life.PLAN): life.PLAN_SEAL})
    includes = ROOT / 'verification/tests'
    paths = [APP, includes / 'pure_war_reference.h', includes / 'pure_war_host.c',
        includes / 'gap75_start.S', includes / 'gap75.ld', Path(__file__).resolve(),
        Path(__file__).with_name('test_pure_war_preflight.py'), Path(shared.__file__).resolve(),
        Path(strict.__file__).resolve(), Path(life.__file__).resolve(), LLVM / 'clang', LLVM / 'ld.lld',
        LLVM / 'llvm-readelf', SPIKE, Path('/usr/bin/cc'), Path('/usr/bin/cc').resolve(),
        ROOT / 'verification/ara_verify/random_rvv.py', ROOT / 'verification/ara_verify/spike_trace.py',
        ROOT / 'verification/ara_verify/trace.py', ROOT / 'verification/ara_verify/vector_commit.py',
        Path(__file__).with_name('inventory_operand_debug.py'), Path(__file__).with_name('closure_point_inventory.py')]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in paths})
    require(not any('ZCC' in p or 'Terapines' in p for p in pins), 'Forbidden tool pin')
    life.check(pins)
    out.mkdir(); life.save(out / 'input-pins.json', pins); life.save(out / 'target-before.json', targets)
    try:
        host = ['/usr/bin/cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(includes / 'pure_war_host.c'), '-o', str(out / 'host-reference')]
        life.save(out / 'host-command.json', host)
        with (out / 'host.log').open('x') as log:
            subprocess.run(host, check=True, timeout=60, stdout=log, stderr=subprocess.STDOUT)
            subprocess.run([str(out / 'host-reference')], check=True, timeout=10, stdout=log, stderr=subprocess.STDOUT)
        command = [str(LLVM / 'clang'), '--target=riscv64-unknown-elf', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
            '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-O2', '-fno-vectorize', '-fno-slp-vectorize',
            '-ffreestanding', '-DVLEN=1024', '-DNR_LANES=4', '-I' + str(includes), '-fuse-ld=lld', '-nostdlib',
            '-T' + str(includes / 'gap75.ld'), str(includes / 'gap75_start.S'), str(APP), '-o', str(out / 'input.elf')]
        life.save(out / 'compile-command.json', command)
        with (out / 'compile.log').open('x') as log:
            subprocess.run(command, check=True, timeout=120, stdout=log, stderr=subprocess.STDOUT)
        symbols = {n: shared._elf_symbol(out / 'input.elf', LLVM / 'llvm-readelf', n) for n in SYMBOLS}
        verify_elf((out / 'input.elf').read_bytes(), symbols)
        require(symbols['tohost'] == 0x80001000, 'Terminal address drift')
        elf_hash = life.digest(out / 'input.elf')
        evidence = json.loads((BASE / 'evidence-pins.json').read_bytes())
        elfs = {p: h for p, h in evidence.items() if p.endswith('.elf')}
        require(elf_hash not in elfs.values(), 'Duplicate727 ELF')
        life.save(out / 'elf-dedup.json', dict(baseline=727, baseline_elf_pins=len(elfs),
            input_elf_sha256=elf_hash, duplicate_elf=False))
        spike = [str(SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0', '-l', '--log-commits', str(out / 'input.elf')]
        life.save(out / 'spike-command.json', spike)
        with (out / 'spike.stdout').open('x') as stdout, (out / 'spike.trace').open('x') as trace:
            subprocess.run(spike, check=True, timeout=180, stdout=stdout, stderr=trace)
        commits = shared.parse_spike_commits(out / 'spike.trace')
        result = validate(commits, symbols, (out / 'spike.trace').read_text())
        counts = strict.reference_counts(commits, symbols)
        life.save(out / 'spike-validation.json', result); life.save(out / 'reference-counts.json', counts)
        life.check(pins)
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in out.iterdir() if p.is_file()})
        pre = dict(status=STATUS, case=NAME, baseline_tests=727, baseline_manifest_sha256=BASE_SEAL,
            pins=pins, symbols=symbols, targets=targets, validation=result, reference_counts=counts,
            input_elf=str(out / 'input.elf'), checks=CHECKS, old_image_files_checked=66,
            backend_budget_seconds=600, coverage_admitted=False, vcs_started=False, rtl_changed=False,
            ZCC_executed=False, measured_raw_increment=None, dut_diff_executed=False,
            native_DVE_selector_binding=False, instruction_pair=[hex(DIV), hex(LOAD)],
            gold_source='Independent source/index/base byte formula; never DUT snapshot values',
            terminal_required='full scalar/GPR/memory exact, full vector exact with zero unknown, zero exceptions/protocol/fails, tohost1',
            unhit_policy='Preserve measured zero gain; no trial tuning or artificial delays')
        life.save(out / 'preflight-manifest.json', pre)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'preflight-manifest.json'),
                             elf_sha256=elf_hash, counts=counts, validation=result)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='PURE_WAR_PREFLIGHT_FAILED_NOT_VCS', reason=str(error))); raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('build', 'verify'))
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--seal')
    a = p.parse_args()
    require((a.mode == 'verify') == bool(a.seal), 'Only verify requires seal')
    if a.mode == 'build':
        build(a.output.absolute())
    else:
        pre = verify(a.output.absolute(), a.seal)
        print(json.dumps(dict(status='VERIFY_PASS', seal=a.seal, checks=pre['checks'], vcs_started=False)))


if __name__ == '__main__':
    main()
