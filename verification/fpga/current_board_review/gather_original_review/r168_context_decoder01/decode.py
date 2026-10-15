#!/usr/bin/env python3
"""Decode supplied R168 register/stack evidence; never infer from snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ELF = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_permute_partitions01/release/binaries/rvv_permute_restart_e8_m4_ops3')
ELF_SHA = 'a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b'
SOURCE = 'rvv_permute_restart_e8_m4_ops3'
MASK = (1 << 64) - 1
ALIASES = {'sp': 'x2', 'ra': 'x1', 's4': 'x20', 's7': 'x23', 's8': 'x24',
           's9': 'x25', 'a3': 'x13', 'a4': 'x14', 'a6': 'x16', 'a7': 'x17'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def number(value):
    require(type(value) in (int, str), 'Captured value must be an integer or integer string')
    if isinstance(value, str):
        value = int(value, 16 if value.startswith(('0x', '0X')) else 10)
    require(0 <= value <= MASK, 'Captured value outside RV64 range')
    return value


def binding(path=ELF):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ELF_SHA, 'Not the exact original R168 ELF')
    require(raw[:6] == b'\x7fELF\x02\x01', 'Original ELF format')
    phoff = struct.unpack_from('<Q', raw, 32)[0]
    size, count = struct.unpack_from('<HH', raw, 54)
    checks = {0x103ca: (4, 0x256000ef), 0x104d2: (2, 0x67e2),
              0x104d4: (2, 0x2785), 0x104d6: (2, 0xec3e),
              0x1063e: (4, 0x308fbc57), 0x10642: (4, 0x00802573)}
    for pc, (width, code) in checks.items():
        actual = None
        for i in range(count):
            kind, _, off, va, _, filesz, _, _ = struct.unpack_from('<IIQQQQQQ', raw, phoff + size*i)
            if kind == 1 and va <= pc and pc+width <= va+filesz:
                actual = int.from_bytes(raw[off+pc-va:off+pc-va+width], 'little')
                break
        require(actual == code, 'Original caller/helper byte binding at '+hex(pc))
    return {'path': str(Path(path).resolve()), 'sha256': ELF_SHA, 'source_label': SOURCE}


def decode(context, source_binding):
    require(isinstance(context, dict) and context.get('schema') == 'R168_REGS_STACK_V1', 'Input schema')
    require(context.get('source_elf_sha256') == ELF_SHA, 'Dump must identify exact original ELF')
    require(isinstance(context.get('capture_id'), str) and context['capture_id'].strip(), 'Capture identity missing')
    require(context.get('same_context_regs_stack') is True, 'Registers and stack must share a captured context')
    regs, stack = context.get('regs'), context.get('stack')
    require(isinstance(regs, dict) and isinstance(stack, dict), 'Real regs and stack required; no snapshot fallback')

    def reg(name):
        values = [number(regs[k]) for k in (name, ALIASES.get(name)) if k in regs]
        require(values and len(set(values)) == 1, 'Missing/conflicting captured register '+name)
        return values[0]

    pc, sp, ra = reg('pc'), reg('sp'), reg('ra')
    require(pc in (0x1063e, 0x10642) and ra == 0x103ce, 'Not the captured original helper/caller context')
    require(sp > 0 and sp % 16 == 0 and sp+336 <= MASK, 'Original aligned caller SP')
    require(stack.get('byte_order') == 'little' and number(stack.get('address')) == sp, 'Stack byte order/address')
    require(isinstance(stack.get('data_hex'), str), 'Actual stack bytes missing')
    data = bytes.fromhex(stack['data_hex'])
    require(len(data) >= 32, 'Need actual SP..SP+31 bytes')
    mode, seed, cap_plus_one, completed = struct.unpack_from('<QQQQ', data)
    require(completed < 2688, 'No unreturned source call after completed2688')
    cap = reg('a4')
    require(32 <= cap <= 1024 and cap & (cap-1) == 0, 'Original e8/m4 legal capacity')
    require(cap_plus_one == cap+1, 'Stack capacity and captured a4 disagree')
    s = (completed % 896) // 112
    l = (completed % 112) // 16
    m, t = (completed % 16) // 4, completed % 4
    require(seed == completed // 896 and mode == m, 'Seed/mode disagree with actual completed count')
    require(reg('s8') == 3 and reg('s4') == t, 'Original opcode/trial context disagreement')
    require(reg('s7') == sp+160+s*8 and reg('s9') == sp+128+l*4, 'Original scalar/length slot pointers')
    vl = (0, 1, 2, 3, cap//2, cap-1, cap)[l]
    scalar = (0, 1, cap-1, cap, cap+1, MASK, 1 << 63, (1 << 63)-1)[s]
    vstart = (1, vl//2, vl, cap-1)[t]
    require([reg(n) for n in ('a3', 'a6', 'a7')] == [vl, scalar, vstart], 'Captured helper arguments disagree')
    csr = context.get('csrs', {})
    require(isinstance(csr, dict), 'CSR schema')
    if 'vlenb' in csr:
        require(number(csr['vlenb'])*4 == cap, 'Captured vlenb/capacity disagreement')
    return dict(status='DECODED_SUPPLIED_R168_CONTEXT_NOT_AUTHENTICATED',
        source_elf=source_binding, capture_id=context['capture_id'],
        completed_original_calls=completed, unreturned_original_ordinal=completed+1,
        original_tuple=[seed, 3, s, l, m, t],
        vl=vl, capacity=cap, scalar=scalar, vstart=vstart,
        preceding_original_ordinals={'first': 1, 'last': completed, 'count': completed},
        register_context={'pc': hex(pc), 'sp': hex(sp), 'ra': hex(ra)},
        consumed_stack_sha256=hashlib.sha256(data[:32]).hexdigest(),
        captured_vlenb=number(csr['vlenb']) if 'vlenb' in csr else None,
        supplied_capture_authenticity_independently_verified=False,
        backend_acceptance_or_stall_cause_proven=False, historical_stall_closed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--elf', type=Path, default=ELF)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        result = decode(json.loads(raw), binding(args.elf))
        result['input_path'] = str(args.input.resolve())
        result['input_sha256'] = hashlib.sha256(raw).hexdigest()
        code = 0
    except (ValueError, TypeError, KeyError, OSError, struct.error) as error:
        result, code = {'status': 'REJECTED_NO_TUPLE', 'error': str(error)}, 1
    encoded = json.dumps(result, indent=2)+'\n'
    if args.out:
        with args.out.open('x') as stream:
            stream.write(encoded)
    else:
        sys.stdout.write(encoded)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
