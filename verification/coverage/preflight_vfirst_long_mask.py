"""Independent eight-mask scalar oracle and bounded software-only preflight."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import preflight_vmacc_c_fifo_l2_773 as template

old = template.old
life, require, build = old.life, old.require, old.build
ROOT, OUT = life.ROOT, life.OUT
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vfirst_long_mask_scalar.c'
POSITIONS = (2, 4, 128, 256, 512, 1023, None, 0)
GUARD = 0x9696969696969696
SYMBOLS = ('tohost', 'num_failed', 'g75_result', 'trap_fail', 'vfirst_checks',
           'vfirst_source', 'vfirst_snapshot', 'vfirst_ledger', 'vfirst_mask_load',
           'vfirst_scalar_op', 'vfirst_whole_readback')


def mask(position):
    require(position is None or 0 <= position < 1024, 'Mask position outside VL')
    data = bytearray(128)
    if position is not None: data[position // 8] = 1 << (position % 8)
    return bytes(data)


def first_set(data):
    require(len(data) == 128, 'Whole mask register required')
    return next((i for i in range(1024) if data[i // 8] & (1 << (i % 8))), (1 << 64) - 1)


def ledger_gold(position):
    return [first_set(mask(position)), 1024, 0, 1024, 3, 0, 0, 0]


def source_pins():
    book = ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    require(life.digest(book) == '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b',
            'Frozen build-source book')
    pins = {str(book): life.digest(book)}; original = json.loads(book.read_bytes())
    for rel in ('hardware/src/masku/masku.sv', 'hardware/src/masku/masku_operands.sv'):
        pins[str(ROOT / rel)] = original[str(ROOT / rel)]
    life.check(pins)
    return pins


def linked(disassembly):
    # No implicit compiler-generated vector memory/copy operations.
    mnemonics = re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{8}|[0-9a-f]{4}|(?:[0-9a-f]{2}\s+){1,3}[0-9a-f]{2})\s+([\w.]+)', disassembly, re.M)
    vector = [m for m in mnemonics if m.startswith('v')]
    require(sorted(vector) == sorted(('vsetvli', 'vlm.v', 'vfirst.m', 'vs1r.v')),
            'Exact four explicit static RVV instructions required: ' + repr(vector))
    return vector


def validate(path, symbols):
    commits = build.parse_spike_commits(path)
    require('exception ' not in path.read_text() and not any(c.pc == symbols['trap_fail'] for c in commits),
            'Unexpected software/Spike trap')
    memory = {}; readback = {}; snapshot = {}; operations = []; loads = []
    for c in commits:
        for address, value in c.memory_accesses:
            if value is not None:
                decoded = old.rvc.decode(c.instruction)
                if decoded:
                    require(decoded['kind'] == 'write', 'Store effect on read opcode'); width = decoded['size']
                elif c.instruction & 0x7f == 0x23:
                    require(c.instruction >> 12 & 7 <= 3, 'Unsupported scalar store'); width = 1 << (c.instruction >> 12 & 7)
                else:
                    require(c.instruction & 0x7f == 0x27, 'Unknown memory writer'); width = 1
                for i in range(width): memory[address + i] = value >> (8 * i) & 255
                if c.pc == symbols['vfirst_whole_readback']:
                    require(address not in snapshot and width == 1, 'Duplicate/non-byte whole snapshot')
                    snapshot[address] = value
            elif symbols['vfirst_source'] <= address < symbols['vfirst_source'] + 1280:
                decoded = old.rvc.decode(c.instruction)
                if decoded or c.instruction & 0x7f == 3:
                    require((decoded and decoded['kind'] == 'read' and decoded['size'] == 8 or
                             not decoded and c.instruction >> 12 & 7 == 3) and len(c.gpr_writes) == 1,
                            'Whole scalar source word read')
                    readback[address] = next(iter(c.gpr_writes.values()))
        if c.pc == symbols['vfirst_scalar_op']: operations.append(c)
        if c.pc == symbols['vfirst_mask_load']: loads.append(c)
    require(len(operations) == len(loads) == 8, 'Exactly eight mask loads/scalar operations')
    writers = [c for c in commits if c.vector_writes]
    require(writers == loads, 'Only vlm writes VRF; vfirst does not')
    def observed(address, size):
        require(all(address + i in memory for i in range(size)), 'Missing independent memory witness')
        return int.from_bytes(bytes(memory[address + i] for i in range(size)), 'little')
    for phase, position in enumerate(POSITIONS):
        image = GUARD.to_bytes(8, 'little') * 2 + mask(position) + GUARD.to_bytes(8, 'little') * 2
        for name in ('vfirst_source', 'vfirst_snapshot'):
            start = symbols[name] + 160 * phase
            require(bytes(memory[start + i] for i in range(160)) == image, 'Full source/snapshot including guards')
        src = symbols['vfirst_source'] + 160 * phase
        require(all(readback.get(src + i) == int.from_bytes(image[i:i + 8], 'little')
                    for i in range(0, 160, 8)), 'Every immutable scalar source/guard read')
        dst = symbols['vfirst_snapshot'] + 160 * phase + 16
        require(all(snapshot.get(dst + i) == v for i, v in enumerate(mask(position))), 'Every whole-v0 byte')
        require([observed(symbols['vfirst_ledger'] + phase * 64 + i * 8, 8) for i in range(8)] ==
                ledger_gold(position), 'Exact rd/config/prestart/post CSR ledger')
        c = operations[phase]; rd = c.instruction >> 7 & 31
        require(rd != 0 and c.gpr_writes == {rd: first_set(mask(position))} and not c.vector_writes,
                'vfirst exact rd and no VRF write')
        require(loads[phase].vector_writes == {0: int.from_bytes(mask(position), 'little')}, 'Full vlm writer gold')
    require(len(snapshot) == 1024 and len(readback) == 160, 'No missing/extra snapshot or source reads')
    require([observed(symbols['g75_result'], 4), observed(symbols['g75_result'] + 4, 4),
             observed(symbols['num_failed'], 4), observed(symbols['vfirst_checks'], 4),
             observed(symbols['tohost'], 8)] == [384, 0, 0, 384, 1], 'Strict 384-check successful terminal')
    return dict(checks=384, cases=8, target_scalar_results=8, CSR_and_configuration_values=56,
                whole_v0_bytes=1024, source_and_guard_bytes=1280,
                source_writers=8, vfirst_VRF_writers=0, retirements=len(commits))


def prepare(out, existing=None):
    require(out.parent == OUT and not out.exists(), 'Fresh software preflight only')
    pins = source_pins()
    command = json.loads(template.TEMPLATE.read_bytes())
    command = [str(APP) if a.endswith('/vgap99_csr_satp_mprv.c') else
               str(out / 'input.elf') if a.endswith('/input.elf') else a for a in command]
    command += ['-fno-unroll-loops']
    for p in (APP, template.TEMPLATE, template.START, ROOT / 'verification/tests/gap75.ld',
              Path(__file__).resolve(), Path(__file__).with_name('test_preflight_vfirst_long_mask.py'),
              Path(old.__file__), Path(template.__file__), Path(build.__file__), Path(old.rvc.__file__),
              Path(command[0]), build.SPIKE, build.LLVM / 'llvm-objdump', build.LLVM / 'llvm-readelf'):
        pins[str(p.resolve())] = life.digest(p)
    life.check(pins); out.mkdir()
    life.save(out / 'compile-command.json', command)
    if existing is None:
        with (out / 'build.log').open('x') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
    else:
        require(existing.parent == OUT and existing != out and (existing / 'failure.json').exists(),
                'Explicit preserved failed software preflight only')
        prior = json.loads((existing / 'compile-command.json').read_bytes())
        require(prior == [str(existing / 'input.elf') if a == str(out / 'input.elf') else a for a in command],
                'Same source/flags command; only output path may differ')
        require(json.loads((existing / 'failure.json').read_bytes())['error'] ==
                'Exact four explicit static RVV instructions required: []', 'Only known objdump-reader failure')
        for name in ('input.elf', 'compile-command.json', 'build.log', 'failure.json', 'disassembly.txt'):
            pins[str(existing / name)] = life.digest(existing / name)
        shutil.copyfile(existing / 'input.elf', out / 'input.elf')
        require(life.digest(existing / 'input.elf') == life.digest(out / 'input.elf'), 'Same ELF bytes required')
        life.save(out / 'build-reuse.json', dict(source=str(existing), ELF_sha=life.digest(out / 'input.elf'),
            compiler_reexecuted=False, preserved_failure=True, reason='Objdump word-format reader only'))
    from elftools.elf.elffile import ELFFile
    with (out / 'input.elf').open('rb') as stream:
        segments = [(p['p_paddr'], p['p_paddr'] + p['p_memsz']) for p in ELFFile(stream).iter_segments() if p['p_type'] == 'PT_LOAD']
    require(segments and all(0x80000000 <= a < b <= 0x8003f000 for a, b in segments), 'RAM/stack fit')
    symbols = {n: build._elf_symbol(out / 'input.elf', build.LLVM / 'llvm-readelf', n) for n in SYMBOLS}
    require(symbols['tohost'] == 0x80001000, 'Frozen tohost ABI')
    dis = subprocess.check_output([str(build.LLVM / 'llvm-objdump'), '-d', str(out / 'input.elf')], text=True, timeout=30)
    (out / 'disassembly.txt').write_text(dis)
    vector = linked(dis)
    spike = [str(build.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
             '-m0x80000000:0x200000', '-l', '--log-commits', str(out / 'input.elf')]
    life.save(out / 'spike-command.json', spike)
    with (out / 'spike.trace').open('x') as stream:
        subprocess.run(spike, stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
    counts = validate(out / 'spike.trace', symbols)
    commits = build.parse_spike_commits(out / 'spike.trace')
    counts['runtime'] = template.runtime(commits, symbols, segments)
    life.check(pins)
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in out.iterdir() if p.is_file()})
    result = dict(status='VFIRST_LONG_MASK_HOST_SPIKE_PASS_NOT_DUT', input_pins=pins, symbols=symbols,
        ELF=str(out / 'input.elf'), reference=str(out / 'spike.trace'), counts=counts,
        actual_static_vector_instructions=vector, target='MASKU vfirst_count_d/q bits1,2,7,8,9',
        target_serialized_slots=20, measured_gain=None, coverage_admitted=False, VCS_started=False,
        baseline_note='Source hypothesis checked against773; any future gain must use latest formal population')
    life.save(out / 'preflight.json', result)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'preflight.json'),
                         ELF_sha=life.digest(out / 'input.elf'), counts=counts, VCS_started=False)), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--existing-build', type=Path)
    a = p.parse_args(); out = a.output.resolve()
    try: prepare(out, a.existing_build.resolve() if a.existing_build else None)
    except Exception as error:
        if out.exists() and not (out / 'failure.json').exists():
            life.save(out / 'failure.json', dict(error=str(error), type=type(error).__name__,
                                                VCS_started=False, no_retry=True))
        raise
