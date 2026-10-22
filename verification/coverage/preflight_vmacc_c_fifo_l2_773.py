"""One changed startup literal; reuse frozen numeric oracle, audit actual runtime."""
import argparse
import difflib
import json
import subprocess
from types import FunctionType, SimpleNamespace

import preflight_vmacc_c_fifo773 as old

ROOT, OUT, require, life = old.ROOT, old.OUT, old.require, old.life
START = ROOT / 'verification/tests/vmacc_c_fifo_l2_start.S'
TEMPLATE = ROOT / 'verification/tests/vmacc_c_fifo_l2_compile.json'
ORIGINAL = ROOT / 'verification/tests/gap75_start.S'
LOW, TOP, STACK_LOW = 0x80000000, 0x80040000, 0x8003f000


def source_transform(original, successor):
    before, after = 'li sp, 0x80200000', 'li sp, 0x80040000'
    require(original.count(before) == 1 and successor == original.replace(before, after),
            'Startup must differ by only one stack literal')
    return ''.join(difflib.unified_diff(original.splitlines(True), successor.splitlines(True),
                                      fromfile=str(ORIGINAL), tofile=str(START)))


def runtime(commits, symbols, segments):
    require(segments and all(LOW <= a < b <= STACK_LOW for a, b in segments),
            'Segments/BSS overlap reserved4096-byte stack or leave envelope')
    terminal = [i for i, c in enumerate(commits) if any(a == symbols['tohost'] and v is not None
                                                      for a, v in c.memory_accesses)]
    require(len(terminal) == 1 and (symbols['tohost'], 1) in commits[terminal[0]].memory_accesses,
            'Unique successful tohost')
    end = terminal[0]
    require(all(c.pc == commits[end].pc + 4 and c.instruction == 0xa001 and
                not (c.gpr_writes or c.fpr_writes or c.vector_writes or c.csr_writes or c.memory_accesses)
                for c in commits[end + 1:]), 'Only effect-free terminal spin allowed')
    entry = next((i for i, c in enumerate(commits) if c.pc == LOW), None)
    require(entry is not None and [c.pc for c in commits[:entry]] ==
            [0x1000, 0x1004, 0x1008, 0x100c, 0x1010], 'Exact reference boot prefix')
    require([(c.pc, c.instruction, c.gpr_writes) for c in commits[entry:entry + 2]] ==
            [(LOW, 0x02001137, {2: 0x02001000}), (LOW + 4, 0x011a, {2: TOP})] and
            not any(c.memory_accesses for c in commits[entry:entry + 2]),
            'Exact two-instruction stack materialization, no intervening memory')
    boot_reads = [(c.pc, c.instruction, a, v) for c in commits[:entry] for a, v in c.memory_accesses]
    require(boot_reads == [(0x100c, 0x0182b283, 0x1018, None)], 'Only explicit reference boot-ROM read')
    registers = {0: 0}
    seen_sp, ranges, stack, scalar, vector = [], [], [], 0, 0
    for c in commits[entry:end + 1]:
        decode = old.rvc.decode(c.instruction)
        for address, value in c.memory_accesses:
            writing = value is not None
            if decode:
                require((decode['kind'] == 'write') == writing, 'Compressed memory effect kind')
                width, base, offset = decode['size'], decode['base'], decode['offset']
            elif c.instruction & 0x7f in (0x03, 0x23):
                insn, op = c.instruction, c.instruction & 0x7f
                f3 = insn >> 12 & 7
                require((op == 0x23) == writing and f3 <= (3 if writing else 6), 'Scalar memory opcode/width')
                width, base = 1 << (f3 & 3), insn >> 15 & 31
                imm = (((insn >> 25) << 5) | ((insn >> 7) & 31)) if writing else insn >> 20
                offset = imm - 4096 if imm & 2048 else imm
            else:
                require(c.instruction & 0x7f == (0x27 if writing else 0x07), 'Unknown runtime memory operation')
                width, base, offset = 1, None, None
                vector += 1
            if base is not None:
                require(base in registers and address == ((registers[base] + offset) & ((1 << 64) - 1)),
                        'Memory effective address differs from exact instruction/GPR prestate')
                scalar += 1
            require(LOW <= address and address + width <= TOP, 'Runtime access outside conservative envelope')
            in_segment = any(a <= address and address + width <= b for a, b in segments)
            in_stack = STACK_LOW <= address and address + width <= TOP
            require(in_segment != in_stack, 'Runtime access in unallocated gap/overlap')
            if in_stack:
                require(base == 2 and width in (4, 8), 'Only exact SP-relative scalar stack access')
                stack.append((address, address + width))
            ranges.append((address, address + width))
        for reg, value in c.gpr_writes.items():
            if reg:
                registers[reg] = value
            if reg == 2:
                if c.pc == LOW:
                    continue
                require(STACK_LOW <= value <= TOP and value % 16 == 0, 'SP bounds/alignment')
                seen_sp.append(value)
    require(seen_sp and seen_sp[0] == seen_sp[-1] == TOP and stack, 'Stack initialization/restoration/evidence')
    return dict(entry_to_tohost_instructions=end - entry + 1, reference_prefix_instructions=end + 1,
                terminal_spin_instructions=len(commits) - end - 1, scalar_memory_events=scalar,
                vector_byte_events=vector, runtime_min_address=min(a for a, _ in ranges),
                runtime_end_exclusive=max(b for _, b in ranges), stack_min=min(seen_sp),
                stack_top=TOP, stack_depth=TOP - min(seen_sp), stack_accesses=len(stack),
                reserved_stack_bytes=TOP - STACK_LOW, segment_end=max(b for _, b in segments),
                segment_to_reserved_stack_gap=STACK_LOW - max(b for _, b in segments),
                reference_boot_ROM_read=[list(v) for v in boot_reads],
                stack_materialization=dict(first_instruction=0x02001137, second_instruction=0x011a,
                                           intermediate=0x02001000, final=TOP, intervening_memory=0),
                all_runtime_memory_widths_decoded=True)


def vector_gold(commits):
    writers = [c for c in commits if c.vector_writes]
    require(len(writers) == 19, 'Exact4seeds+2loads+12VMACC+1recovery')
    a = bytes((i ^ 0xa5) & 255 for i in range(1024))
    b = bytes((2 * i + 1) & 255 for i in range(1024))
    register_group = lambda base, data, count: {
        base + r: int.from_bytes(data[128*r:128*(r+1)], 'little') for r in range(count)}
    for c, base in zip(writers[:4], (0, 8, 16, 24)):
        require(c.vector_writes == register_group(base, bytes([0x5a]) * 1024, 8), 'Full seed group')
    for c, base, data in zip(writers[4:6], (8, 16), (a, b)):
        require(c.vector_writes == register_group(base, data, 8), 'Full source load group')
    accumulator = [0x5a] * 1024
    for index, c in enumerate(writers[6:]):
        recovery = index == 12
        for i in range(4 if recovery else 1020 if 4 <= index < 8 else 1024):
            accumulator[i] = (accumulator[i] + (1 if recovery else a[i] * b[i])) & 255
        # VL4 recovery writes only v24; its128-byte tail must still match prestate.
        require(c.vector_writes == register_group(24, bytes(accumulator), 1 if recovery else 8),
                'Every numerical vector result/known preserved tail')
    return dict(writers=19, result_bytes=sum(128 * len(c.vector_writes) for c in writers),
                recovery_declared_registers=[24], recovery_preserved_tail_bytes=124,
                untouched_recovery_group_verified_by_full_snapshot=True)


def prepare(out, existing=None):
    transform = source_transform(ORIGINAL.read_text(), START.read_text())
    original_command = json.loads(old.shared.TEMPLATE.read_bytes())
    changed_command = json.loads(TEMPLATE.read_bytes())
    require(changed_command == [str(START) if v == str(ORIGINAL) else v for v in original_command],
            'Template differs beyond startup path')
    # Reuse the sealed build/oracle body without changing its module globals.
    prepare_old = FunctionType(old.prepare.__code__, dict(old.prepare.__globals__,
                               shared=SimpleNamespace(TEMPLATE=TEMPLATE)), argdefs=old.prepare.__defaults__)
    if existing is None:
        prepare_old(out)
    else:
        require(not out.exists() and out.parent == OUT and existing.parent == OUT, 'Fresh offline audit output')
        out.mkdir()
    artifact = existing or out
    preflight = json.loads((artifact / 'preflight.json').read_bytes())
    life.check(preflight['input_pins'])
    require(preflight['baseline'] == 773 and preflight['baseline_seal'] == old.SEAL and
            json.loads((artifact / 'compile-command.json').read_bytes()).count(str(START)) == 1,
            'Exact773 build and independent startup path')
    pins = dict(preflight['input_pins'])
    for p in (START, ORIGINAL, old.shared.TEMPLATE, old.Path(old.__file__).resolve(),
              old.Path(__file__).resolve(), old.Path(__file__).with_name('test_preflight_vmacc_c_fifo_l2_773.py')):
        pins[str(p)] = life.digest(p)
    compile_book = OUT / 'repaired-aligned-build-20260930-01/compile.command.json'
    require('sim_l2_mb=2' in json.loads(compile_book.read_bytes())['command'], 'Frozen image L2 size binding')
    pins[str(compile_book)] = life.digest(compile_book)
    life.save(out / 'startup.diff', transform)
    from elftools.elf.elffile import ELFFile
    with (artifact / 'input.elf').open('rb') as stream:
        segments = [(p['p_paddr'], p['p_paddr'] + p['p_memsz'])
                    for p in ELFFile(stream).iter_segments() if p['p_type'] == 'PT_LOAD']
    dis = subprocess.run([str(old.build.LLVM / 'llvm-objdump'), '-d', str(artifact / 'input.elf')],
                         capture_output=True, text=True, timeout=30, check=True)
    (out / 'disassembly.txt').write_text(dis.stdout)
    commits = old.build.parse_spike_commits(artifact / 'spike.trace')
    runtime_result = runtime(commits, preflight['symbols'], segments)
    vectors = vector_gold(commits)
    dedup = json.loads((artifact / 'elf-dedup.json').read_bytes())
    require(dedup['ledger_members'] == 773 and dedup['duplicate'] is False, 'Actual773 ELF dedup')
    life.save(out / 'dedup773.json', dict(actual_population=773, candidate_ELF_sha=life.digest(artifact / 'input.elf'),
                                        legacy_label_not_population=dedup['baseline'], duplicate=False))
    for p in (out / 'startup.diff', out / 'disassembly.txt', out / 'dedup773.json', old.build.LLVM / 'llvm-objdump'):
        pins[str(p)] = life.digest(p)
    pins[str(artifact / 'preflight.json')] = life.digest(artifact / 'preflight.json')
    life.check(pins)
    result = dict(preflight, status='VMACC_FIFO_L2_RUNTIME_AND_EVERY_VECTOR_GOLD_PREFLIGHT_PASS_NOT_DUT',
                  input_pins=pins, runtime=runtime_result, numerical_vectors=vectors,
                  startup_diff='ONLY 0x80200000 -> 0x80040000',
                  address_scope=dict(frozen_compiled_L2_bytes=2 * 1024 * 1024,
                      conservative_case_end=TOP, clarification='256KiB is a conservative case envelope, NOT the frozen2MiB L2 size. Prior stack-invalid claim was incorrect.'))
    life.save(out / 'runtime-qualified.json', result)
    print('RUNTIME_PREFLIGHT_PASS', life.digest(out / 'runtime-qualified.json'), runtime_result, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=old.Path, required=True)
    parser.add_argument('--existing-build', type=old.Path)
    args = parser.parse_args()
    prepare(args.output.resolve(), args.existing_build.resolve() if args.existing_build else None)
