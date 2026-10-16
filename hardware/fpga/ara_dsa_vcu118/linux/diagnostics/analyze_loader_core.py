"""Inspect captured bytes, not zero-filled absent pages, in a loader core."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from capture_metadata_core import core_segments, global_file_offset

LOADER_SHA = '3b4c54b64962c449f277bea8904fe0d52251e7b2c2531de994c2657129f816fd'
IMAGE_SHA = '716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285'


def notes(data):
    found = {}
    for p in core_segments(data):
        if p[0] != 4:
            continue
        pos, end = p[2], p[2]+p[5]
        if end > len(data):
            raise ValueError('Truncated core notes')
        while pos < end:
            if pos+12 > end:
                raise ValueError('Truncated note header')
            namesz, size, kind = struct.unpack_from('<III', data, pos)
            name = data[pos+12:pos+12+namesz].rstrip(b'\0')
            start = pos+12+(namesz+3)//4*4
            pos = start+(size+3)//4*4
            if pos > end:
                raise ValueError('Truncated note payload')
            found.setdefault((name, kind), []).append(data[start:start+size])
    return found


def captured(data, address, size):
    offset = global_file_offset(data, address, size)
    if offset+size > len(data):
        raise ValueError('Core file is truncated')
    return data[offset:offset+size]


def cat_stack(data):
    candidates = []
    for p in core_segments(data):
        if p[0] != 1 or not p[1] & 2:
            continue
        for offset in range(0, p[5]-32, 8):
            raw = captured(data, p[3]+offset, 32)
            argc, argv0, argv1, null = struct.unpack('<4Q', raw)
            if argc != 2 or null:
                continue
            try:
                if captured(data, argv0, 4) != b'cat\0':
                    continue
                if captured(data, argv1, 5) != b'/tmp/':
                    continue
            except ValueError:
                continue
            candidates.append(p[3]+offset)
    if len(candidates) != 1:
        raise ValueError('Cannot uniquely reconstruct the original cat startup stack')
    return candidates[0]


def analyze(data, loader):
    if hashlib.sha256(loader).hexdigest() != LOADER_SHA:
        raise ValueError('Wrong reference loader; offsets must not be guessed')
    ns = notes(data)
    status = ns.get((b'CORE', 1), [])
    aux = ns.get((b'CORE', 6), [])
    if len(status) != 1 or len(aux) != 1 or len(status[0]) != 376:
        raise ValueError('Expected one Linux RV64 thread and auxiliary vector')
    regs = struct.unpack_from('<32Q', status[0], 112)
    av = dict(struct.iter_unpack('<QQ', aux[0]))
    base = av[7]
    delta = regs[0]-base
    signal = struct.unpack_from('<H', status[0], 12)[0]
    if signal != 11 or delta not in (0xf750, 0x11c4c):
        raise ValueError('Not a reviewed loader SIGSEGV site')
    stack = cat_stack(data)
    globals_ = {}
    for name, offset, expected, fmt in (
        ('__libc_stack_end', 0x22cb0, stack, '<Q'),
        ('_dl_argv', 0x22cb8, stack+8, '<Q'),
        ('_dl_argc', 0x22cc0, 2, '<I'),
        ('__environ', 0x24238, stack+32, '<Q'),
    ):
        value = struct.unpack(fmt, captured(data, base+offset, struct.calcsize(fmt)))[0]
        globals_[name] = dict(address=hex(base+offset), saved=hex(value),
                             startup_expected=hex(expected), differs=value != expected)
    comparisons = []
    for va, file_offset in ((0x21000, 0x20000), (0x22000, 0x21000), (0x23000, 0x22000)):
        memory = captured(data, base+va, 4096)
        original = loader[file_offset:file_offset+4096]
        changed = [i for i, (a, b) in enumerate(zip(memory, original)) if a != b]
        comparisons.append(dict(address=hex(base+va), elf_file_offset=hex(file_offset),
                                compared_bytes=len(original), different_bytes=len(changed),
                                changed_offsets=[hex(i) for i in changed]))
    result = dict(core_sha256=hashlib.sha256(data).hexdigest(), loader_sha256=LOADER_SHA,
                  scope='post_fault_core_evidence_not_cycle_level_rtl_attribution',
                  pid=struct.unpack_from('<i', status[0], 32)[0], signal=signal,
                  loader_base=hex(base), pc=hex(regs[0]), loader_offset=hex(delta),
                  startup_stack=hex(stack), globals=globals_, file_page_comparisons=comparisons,
                  registers=[hex(r) for r in regs],
                  limitations=['Core reads use the kernel page-table/memory path after the fault.',
                               'This does not prove when writes disappeared or whether the dump path is correct.',
                               'Registers prove a null dereference, not the identity of the RTL defect.'])
    if delta == 0xf750:
        result['environment_cursor'] = dict(address=hex(regs[10]),
            saved=hex(struct.unpack('<Q', captured(data, regs[10], 8))[0]),
            consumed_in_a5=hex(regs[15]),
            fault_instruction='ld a0,0(a5)', producer='ld a5,0(a0) at loader+0xf74c')
    else:
        result['argv_fault'] = dict(consumed_in_s11=hex(regs[27]),
                                   fault_instruction='ld a3,0(s11)')
    return result


def page_directory_evidence(uart, image):
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA:
        raise ValueError('Wrong board kernel image')
    # Verified against the reconstructed kallsyms ELF whose .kernel == Image.
    for offset, opcode in ((0x58ee, bytes.fromhex('1461')),
                           (0x590a, bytes.fromhex('23b00400'))):
        if image[offset:offset+len(opcode)] != opcode:
            raise ValueError('Kernel pmd_clear_bad instructions do not match')
    fault = re.search(r'unhandled signal 11[^\n]*ld-linux-riscv64-lp64d.so.1', uart)
    bad = list(re.finditer(r'\[\s*([0-9.]+)\] mm/pgtable-generic.c:56: bad pmd ([0-9a-f]+)', uart))
    result = dict(kernel_sha256=IMAGE_SHA,
                  kernel_error_reads_pmd_at='0xffffffff800058ee: ld a3,0(a0)',
                  kernel_error_clears_pmd_at='0xffffffff8000590a: sd zero,0(s1)',
                  bad_pmd=[])
    for match in bad:
        value = int(match[2], 16)
        physical = ((value >> 10) & ((1 << 44)-1)) << 12
        result['bad_pmd'].append(dict(timestamp=match[1], value=hex(value),
            precedes_loader_fault=bool(fault and match.start() < fault.start()),
            flags=hex(value & 1023), physical_base=hex(physical),
            has_leaf_permissions=bool(value & 0xe),
            aligned_for_2m_leaf=physical % (2*1024*1024) == 0))
    result['limitation'] = ('UART does not contain the PMD pointer or caller. '
        'It cannot distinguish corrupted stored bytes, wrong read data, or a wrong address, '
        'or establish which virtual range was cleared.')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core', type=Path, required=True)
    p.add_argument('--loader', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--uart', type=Path)
    p.add_argument('--image', type=Path)
    a = p.parse_args()
    result = analyze(a.core.read_bytes(), a.loader.read_bytes())
    if a.uart or a.image:
        if not (a.uart and a.image):
            p.error('Use --uart and --image together')
        result['page_directory_evidence'] = page_directory_evidence(
            a.uart.read_text(), a.image.read_bytes())
    with a.out.open('x') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
