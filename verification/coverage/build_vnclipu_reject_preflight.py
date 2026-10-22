"""Single VNCLIPU rejection: independent host/Spike oracle, no VCS or admission."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess

import build_opivx_vsbc_preflight as shared
import collect_opivx_vsbc_strict as strict
from inventory_operand_debug import Design, points
from closure_point_inventory import definition, read_xml

life, require = shared.life, shared.require
ROOT, OUT, LLVM, SPIKE = shared.ROOT, shared.OUT, shared.LLVM, shared.SPIKE
NAME = 'vnclipu_wx_width_alignment_reject'
APP = ROOT / 'apps/riscv-tests/isa/rv64uv' / (NAME + '.c')
BASE = OUT / 'gap105-offline-admitted-725-parent-20261006-01'
BASE_SEAL = '0f49638e8cea36b28b5832e7eaeea39ee9b5249a162de3f3732c0fcd13a5a397'
REVIEW = OUT / 'rvv-system-static-targets-723-20261006-01.json'
REVIEW_SEAL = '9ed0be7c9cbc98854fb52883e4b9942f473c51ed6351367972236404e901fc03'
PRE = OUT / 'vnclipu-reject-preflight-725-20261006-01'
STATUS = 'VNCLIPU_REJECT_FULL_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS'
CHECKS, BAD, RECOVERY = 2346, 0xBAA04857, 0xBA804857
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
SYMBOLS = ('tohost', 'g75_result', 'num_failed', 'trap_fail', 'gvc_ledger', 'gvc_post',
           'gvc_restore', 'gvc_traps', 'gvc_cfg', 'gvc_recovery_cfg', 'gvc_dump', 'gvc_seed',
           'gvc_bad', 'gvc_recovery', 'gvc_handler', 'gvc_handler_end', 'gvc_init_begin', 'gvc_init_end')


def expected_register(reg, phase=0):
    data = bytearray((reg * 29 + b * 13 + ((b >> 3) ^ reg) * 7 + 0x35) & 255 for b in range(128))
    if reg == 8:
        data[:8] = (0x1234).to_bytes(4, 'little') + (0x10001).to_bytes(4, 'little')
    if phase == 2 and reg == 16:
        data[:4] = min(0x1234, 65535).to_bytes(2, 'little') + min(0x10001, 65535).to_bytes(2, 'little')
    return bytes(data)


def target_binding():
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    for name in ('combined-bits.json', 'status.json', 'evidence-pins.json'):
        p = BASE / name
        life.read_bound(p, manifest['output_pins'][str(p)])
    bits = json.loads((BASE / 'combined-bits.json').read_bytes())
    require(len(bits['tests']) == len(set(bits['tests'])) == 725, 'Not exact725')
    status = json.loads((BASE / 'status.json').read_bytes())
    require(status['coverage_admitted'] is True and status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY', 'Base not formal')
    review = life.read_bound(REVIEW, REVIEW_SEAL)
    design = Design(Path(str(life.IMAGE) + '.vdb'))
    life.check({str(design.db / p): h for p, h in bits['design'].items()})
    cond = read_xml(design.db / 'shape/cond.verilog.shape.xml')
    results = []
    for target in review['target_points']:
        metric, raw = target['metric'], target['raw_index']
        require(target['scope'] == SCOPE and target['source']['file_id'] == '547', 'Wrong target scope/source')
        row = bits['metrics'][metric][SCOPE]
        require((row['width'], row['checksum']) == (target['width'], target['checksum']), '725 shape drift')
        require(not int(row['bits'], 16) & (1 << (row['width'] - 1 - raw)), 'Target already hit725')
        node = (definition(cond, design.hierarchy[SCOPE], row['checksum']) if metric == 'cond'
                else design.definition(SCOPE, metric))
        matches = [p for p in points(metric, node, row['width']) if p['raw_index'] == raw]
        require(len(matches) == 1, 'Missing/ambiguous raw point')
        p = matches[0]
        require((p['native_id'], p['file_id'], p['vector'], p['line']) ==
                (target['compiled_id'], target['file_id'], target['vector'], target['line']), 'Native compiled identity drift')
        if metric == 'branch':
            selected = [e for e in p['expressions'] if e['id'] in ('2251', '2254')
                        and p['native_vector']['vector'][-int(e['index'])] == '1']
            require(selected == target['branch_predicates'], 'Branch source predicate drift')
            import hashlib
            require(hashlib.sha256(p['native_vector']['vector'].encode()).hexdigest() ==
                    target['branch_full_vector_sha256'], 'Branch full signature drift')
        else:
            require(p['expression'] == target['expression'], 'Source expression drift')
        results.append(dict(target, hit725=False))
    require({(t['metric'], t['raw_index']) for t in results} ==
            {('line', 557), ('line', 564), ('branch', 921), ('branch', 925), ('cond', 265)}, 'Not exact five targets')
    return results, bits


def verify_elf(blob, symbols):
    require(blob[:6] == b'\x7fELF\x02\x01', 'Not ELF64 LE')
    h = struct.unpack_from('<HHIQQQIHHHHHH', blob, 16)
    require(h[:3] == (2, 243, 1) and h[10] == 64 and h[5] + h[11] * 64 <= len(blob), 'ELF header')
    require(symbols['gvc_bad'] != symbols['gvc_recovery'], 'Aliased fault/recovery')
    for name, word in (('gvc_bad', BAD), ('gvc_recovery', RECOVERY)):
        pc, owners = symbols[name], []
        require(pc % 4 == 0, 'PC alignment')
        for i in range(h[11]):
            sec = struct.unpack_from('<IIQQQQIIQQ', blob, h[5] + i * 64)
            if sec[1] == 1 and sec[2] & 4 and sec[3] <= pc and pc + 4 <= sec[3] + sec[5]:
                owners.append(struct.unpack_from('<I', blob, sec[4] + pc - sec[3])[0])
        require(owners == [word], 'Executable fault/recovery word differs: ' + name)


def signatures(read, symbols):
    require(read('g75_result', width=4) == CHECKS and
            read('g75_result', 4, 4) == read('num_failed', width=4) == 0, 'Checks/failure signature')
    restore = [read('gvc_restore', i * 8) for i in range(18)]
    require(all(restore[i] == restore[i + 1] for i in range(0, 18, 2)) and
            restore[0] == symbols['trap_fail'] and restore[2] == 0 and
            0x80100000 <= restore[4] < 0x80200000 and restore[4] % 16 == 0 and
            restore[6:] == [0] * 12, 'Context restoration differs')
    sp = restore[4]
    require([read('gvc_ledger', i * 8) for i in range(12)] ==
            [2, symbols['gvc_bad'], BAD, 2, 25, 1, 4, 1, 0x2222, 0x3333, 117, sp], 'Precise trap ledger')
    require([read('gvc_post', i * 8) for i in range(9)] ==
            [0x1111, 0x2222, 0x3333, sp, 1, 2, 25, 4, 117], 'Handler/post-trap side effects')
    require([read('gvc_cfg', i * 8) for i in range(5)] == [2, 25, 1, 4, 117], 'Actual pre-fault config')
    require([read('gvc_recovery_cfg', i * 8) for i in range(5)] == [2, 9, 0, 5, 117], 'Actual recovery/saturation config')
    require(read('gvc_traps') == 1, 'Not one trap')
    for phase in range(3):
        for reg in range(32):
            actual = b''.join(read('gvc_dump', ((phase * 32 + reg) * 18 + w) * 8).to_bytes(8, 'little') for w in range(18))
            require(actual == b'\xa5' * 8 + expected_register(reg, phase) + b'\xa5' * 8, 'Full VRF/tail/guard differs')
    for reg in range(32):
        actual = b''.join(read('gvc_seed', (reg * 18 + w) * 8).to_bytes(8, 'little') for w in range(18))
        require(actual == b'\xa5' * 8 + expected_register(reg) + b'\xa5' * 8, 'Independent source buffer/guard differs')


def validate(commits, symbols, trace):
    events = re.findall(r'exception ([^,\n]+), epc (0x[0-9a-fA-F]+)', trace)
    require([(name, int(pc, 16)) for name, pc in events] == [('trap_illegal_instruction', symbols['gvc_bad'])]
            and trace.count('exception ') == 1, 'Not exactly one illegal exception at exact PC')
    require(not any(c.pc in (symbols['gvc_bad'], symbols['trap_fail']) for c in commits), 'Bad/fatal PC retired')
    handler = [c for c in commits if symbols['gvc_handler'] <= c.pc < symbols['gvc_handler_end']]
    require(handler and sum(c.pc == symbols['gvc_handler'] for c in handler) == 1, 'Handler entry population')
    memory, terminal, stores, reads = {}, [], [], set()
    for c in commits:
        for address, value in c.memory_accesses:
            if value is None:
                access = strict.scalar_memory(c.instruction)
                if access and access[0] == 'read':
                    reads.update(range(address, address + access[1]))
                continue
            width = shared.store_width(c.instruction)
            require(0 <= value < 1 << (width * 8), 'Store width/value')
            for i in range(width):
                memory[address + i] = (value >> (8 * i)) & 255
            if address == symbols['tohost']:
                terminal.append(value)
            if symbols['gvc_handler'] <= c.pc < symbols['gvc_handler_end']:
                stores.append((address, width))

    def read(name, offset=0, width=8):
        address = symbols[name] + offset
        require(all(address + i in memory for i in range(width)), 'Missing signature: ' + name)
        return int.from_bytes(bytes(memory[address + i] for i in range(width)), 'little')

    require(terminal == [1], 'Terminal tohost is not exact PASS')
    signatures(read, symbols)
    for name, size in (('gvc_dump', 3 * 32 * 144), ('gvc_seed', 32 * 144)):
        require(set(range(symbols[name], symbols[name] + size)) <= reads, 'Full source/dump software readback absent')
    allowed = {(symbols['gvc_ledger'] + i * 8, 8) for i in range(12)} | {(symbols['gvc_traps'], 8)}
    require(Counter(stores) == Counter(allowed), 'Handler exact memory footprint')
    require(all(not c.vector_writes and not c.fpr_writes and set(c.gpr_writes) <= {5, 6, 7}
                and set(c.csr_writes) <= {0x300, 0x340, 0x341} for c in handler), 'Handler protected state touched')
    init = [c for c in commits if symbols['gvc_init_begin'] <= c.pc < symbols['gvc_init_end'] and c.vector_writes]
    require(len(init) == 32, 'Not full32 initialization')
    for reg, c in enumerate(init):
        require(c.vector_writes == {reg: int.from_bytes(expected_register(reg), 'little')}, 'Independent initial VRF differs')
    recovery = [c for c in commits if c.pc == symbols['gvc_recovery']]
    require(len(recovery) == 1 and set(recovery[0].vector_writes) == {16}, 'Recovery write identity differs')
    require(recovery[0].vector_writes[16] == int.from_bytes(expected_register(16, 2), 'little'), 'Independent recovery/tail differs')
    require(sum(bool(c.vector_writes) for c in commits) == 33, 'Unexpected vector writer')
    return dict(status='VNCLIPU_REJECT_SPIKE_FULL_ORACLE_PASS_NOT_DUT', checks=CHECKS,
                illegal_traps=1, trap_vstart=1, post_mret_vstart=1, snapshots=3, full_vrf_registers=32,
                observed_vrf_bytes=12288, vrf_guard_bytes=1536, source_bytes=4096, source_guard_bytes=512,
                handler_store_words=13, vector_write_instructions=33, illegal_vector_write_bytes=0,
                recovery_modified_bytes=4, restored_vector_CSRs=True, coverage_admitted=False)


def verify(out, seal):
    pre = life.read_bound(out / 'preflight-manifest.json', seal)
    require(pre['status'] == STATUS and pre['case'] == NAME and pre['baseline_tests'] == 725 and
            pre['coverage_admitted'] is False and pre['vcs_started'] is False and pre['ZCC_executed'] is False,
            'Preflight contract')
    life.check(pre['pins'])
    require(pre['targets'] == target_binding()[0], 'Exact725 target binding differs')
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
    pins = life.merge_pins(pins, {str(REVIEW): REVIEW_SEAL, str(life.PLAN): life.PLAN_SEAL,
        str(BASE / 'admission-manifest.json'): BASE_SEAL})
    paths = [BASE / n for n in ('combined-bits.json', 'status.json', 'evidence-pins.json')]
    paths += [APP, OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json',
        ROOT / 'verification/tests/vnclipu_reject_reference.h', ROOT / 'verification/tests/vnclipu_reject_host.c',
        ROOT / 'verification/tests/gap75_start.S', ROOT / 'verification/tests/gap75.ld', Path(__file__).resolve(),
        Path(__file__).with_name('test_vnclipu_reject_preflight.py'), Path(__file__).with_name('run_vnclipu_reject_simulation.py'),
        Path(__file__).with_name('test_run_vnclipu_reject_simulation.py'), Path(shared.__file__).resolve(),
        Path(strict.__file__).resolve(), Path(life.__file__).resolve(), LLVM / 'clang', LLVM / 'ld.lld',
        LLVM / 'llvm-readelf', SPIKE, Path('/usr/bin/cc'), Path('/usr/bin/cc').resolve(),
        ROOT / 'verification/ara_verify/random_rvv.py', ROOT / 'verification/ara_verify/spike_trace.py',
        ROOT / 'verification/ara_verify/trace.py', ROOT / 'verification/ara_verify/vector_commit.py']
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in paths})
    require(not any('ZCC' in p or 'Terapines' in p for p in pins), 'Forbidden tool pin')
    life.check(pins)
    out.mkdir(); life.save(out / 'input-pins.json', pins); life.save(out / 'target-before.json', targets)
    try:
        includes = ROOT / 'verification/tests'
        host = ['/usr/bin/cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(includes / 'vnclipu_reject_host.c'), '-o', str(out / 'host-reference')]
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
        require(elf_hash not in elfs.values(), 'Duplicate725 ELF')
        life.save(out / 'elf-dedup.json', dict(baseline=725, baseline_elf_pins=len(elfs),
            input_elf_sha256=elf_hash, duplicate_elf=False, exact_target_context_new=True))
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
        pre = dict(status=STATUS, case=NAME, baseline_tests=725, baseline_manifest_sha256=BASE_SEAL,
            pins=pins, symbols=symbols, targets=targets, validation=result, reference_counts=counts,
            input_elf=str(out / 'input.elf'), checks=CHECKS, old_image_files_checked=66,
            coverage_admitted=False, vcs_started=False, rtl_changed=False, ZCC_executed=False,
            measured_raw_increment=None, dut_diff_executed=False, native_DVE_selector_binding=False,
            gold_source='Independent static byte formula and saturation; never DUT snapshot values',
            full_scalar_vector_diff_entry='build_vnclipu_reject_preflight.py compare',
            terminal_strict_lifecycle_required_before_admission=True)
        life.save(out / 'preflight-manifest.json', pre)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'preflight-manifest.json'), elf_sha256=elf_hash,
                             counts=counts, validation=result)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='VNCLIPU_PREFLIGHT_FAILED_NOT_VCS', reason=str(error))); raise


def compare(out, seal, dut, result_path):
    pre = verify(out, seal)
    require(result_path is not None and not result_path.exists(), 'Fresh comparison output required')
    scalar = strict.spike_trace.compare_commit_prefix(out / 'spike.trace', dut / 'commit_trace.csv', 0x80000000,
        terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
    strict.scalar_exact(scalar, pre['reference_counts'])
    vector = strict.compare_vector_commits(out / 'spike.trace', dut / 'commit_trace.csv', dut / 'vector_trace.csv', 0x80000000)
    for k, v in dict(status='PASS', compared_instructions=33, vector_destination_requests=33,
        skipped_unknown_bytes=0, non_bit_exact_instructions=0, unobservable_instructions=0,
        incomplete_requests=[], unretired_requests=[], first_mismatch=None).items():
        require(vector.get(k) == v, 'Incomplete vector diff: ' + k)
    require(len(vector['instructions']) == 33 and all(x['status'] == 'PASS' and x['compared_bytes'] == 128
        for x in vector['instructions'][:32]) and 4 <= vector['instructions'][-1]['compared_bytes'] <= 256,
        'Not full initialization plus recovery')
    require(len(vector['trapped_requests']) == 1, 'Illegal request population differs')
    life.save(result_path, dict(status='FULL_SCALAR_VECTOR_DIFF_PASS_NOT_ADMISSION', scalar=scalar, vector=vector,
        preflight_seal=seal, input_pins={str(dut / n): life.digest(dut / n) for n in ('commit_trace.csv', 'vector_trace.csv')},
        coverage_admitted=False, lifecycle_and_rawdelta_still_required=True))
    print('FULL_DIFF_PASS_NOT_ADMISSION')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('build', 'verify', 'compare')); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal'); p.add_argument('--dut', type=Path); p.add_argument('--comparison', type=Path)
    a = p.parse_args(); require((a.mode != 'build') == bool(a.seal), 'Replay requires fixed seal')
    if a.mode == 'build': build(a.output.absolute())
    elif a.mode == 'verify': verify(a.output.absolute(), a.seal); print('VERIFY_PASS FULL32VRF/CSR/TRAP/RECOVERY 725 NO_VCS')
    else:
        require(a.dut is not None, 'Existing DUT traces required')
        compare(a.output.absolute(), a.seal, a.dut.absolute(), a.comparison)


if __name__ == '__main__': main()
