#!/usr/bin/env python3
"""Source-only generator. No compiler, subprocess, reference, or DUT entry point.

Not executed during source preparation. Future execution requires separate
authorization and an exclusive new output directory.
"""
import argparse
import collections
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / 'recovery01'
PINNED = {
    'successor_oracle.c': 'ab82b4891f9e926e37ef4d9f10fc44b0f953136deef2173b84427c0447e81006',
    'scenario.S': '9b4552c734a6f456d094bf77dd1510495df3c5421b6bb05bc3492b5e5ecac2c0',
    'operations.h': 'adec2fb8c81bc1b2f9173c7928dd2d3dabbae932596cb139e058b6f11cb98fb9',
    'rvv_fixed_restart_e8_m4': 'ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc',
    'report.json': '6be6737a103c80b1ee317751f73edb000f2042eedd53537d8dbed96aa50da07d',
}
CAP, CALLS, MASK_BYTES, OUTPUT_BYTES = 512, 10752, 128, 514
VL_ORDER = (0, 1, 2, 3, 256, 511, 512)
U64 = (1 << 64) - 1
SENTINEL = bytes([0x5b]) * OUTPUT_BYTES


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    with path.open('x') as f:
        f.write(data if isinstance(data, str) else json.dumps(data, indent=2) + '\n')


def replace_once(text, old, new):
    require(text.count(old) == 1, 'Unique original source anchor: ' + old[:90])
    return text.replace(old, new, 1)


def selected(mode, i):
    return mode == 0 or mode == 1 and i & 1 or mode == 2 and i % 7 == 2


def seed_inputs(seed):
    """Preserve original assignment order, including overwritten RNG bytes."""
    a, b, writes = bytearray(CAP), bytearray(CAP), []
    state = 0x937ad68de41c725f ^ seed

    def put(bank, i, value):
        value &= 255
        (a if bank == 'a' else b)[i] = value
        writes.append([bank, i, value])

    for i in range(CAP):
        state ^= (state << 13) & U64
        state ^= state >> 7
        state ^= (state << 17) & U64
        put('a', i, state)
        put('b', i, state >> 19)
        if i % 8 == 0:
            put('a', i, 0); put('b', i, 0)
        elif i % 8 == 1:
            put('a', i, 255); put('b', i, 1)
        elif i % 8 == 2:
            put('a', i, 128); put('b', i, 255)
        elif i % 8 == 3:
            put('b', i, 8)
    require(len(writes) == 1472, 'Every initial and override assignment')
    return a, b, writes, state


def value(op, x, y, control):
    """Integer-only specialization of original extra_value/rounded at SEW8."""
    sx, sy = (x if x < 128 else x-256), (y if y < 128 else y-256)
    if op == 0:
        q, residue = divmod(sx * sy, 128)
        rm = control & 3
        increment = (rm == 0 and residue >= 64 or
                     rm == 1 and (residue > 64 or residue == 64 and q & 1) or
                     rm == 3 and residue != 0 and not q & 1)
        z = q + int(bool(increment))
        return (min(z, 127) & 255), int(z > 127)
    if op == 2:
        z = x + y
        return min(z, 255), int(z > 255)
    require(op in (1, 3), 'Original four operators only')
    z = sx + sy if op == 1 else sx - sy
    return max(-128, min(z, 127)) & 255, int(z < -128 or z > 127)


def mask_sequence(mode):
    mask, writes = bytearray(MASK_BYTES), []
    for i in range(CAP):
        if selected(mode, i):
            mask[i//8] |= 1 << (i % 8)
            writes.append([i//8, mask[i//8]])
    require(not any(mask[64:]), 'Physical upper64 mask bytes stay zero')
    return mask, writes


def make_model():
    """All original tuples are emitted; only immutable byte values are interned."""
    full_sentinel = bytes([0x5b])*64
    tail_sentinel = bytes([0x5b])*2 + bytes(62)
    blocks = [full_sentinel, tail_sentinel]
    block_ids = {b: i for i,b in enumerate(blocks)}
    rows = [(0,)*8+(1,)]
    row_ids = {rows[0]: 0}
    row_keys = {('sentinel',): SENTINEL}
    block_keys = {}
    calls, indices, sats, seeds, boundaries = [], [], [], [], []
    counts = collections.Counter()
    masks = [mask_sequence(mode) for mode in range(4)]

    def intern_block(raw):
        require(len(raw) == 64, 'ROM blocks have fixed representation size')
        if raw not in block_ids:
            block_ids[raw] = len(blocks); blocks.append(raw)
        return block_ids[raw]

    for seed in range(3):
        a, b, writes, final_state = seed_inputs(seed)
        seeds.append(dict(seed=seed, a_hex=a.hex(), b_hex=b.hex(), writes=writes,
                          final_random=final_state))
        counts['rng_iterations'] += CAP
        counts['source_SB'] += len(writes)
        for op in range(4):
            for li, vl in enumerate(VL_ORDER):
                for mode in range(4):
                    counts['mask_epochs'] += 1
                    counts['mask_clear_SD'] += 16
                    counts['mask_selected_SB'] += len(masks[mode][1])
                    for si, start in enumerate((1, vl//2, vl, CAP-1)):
                        for control in range(8):
                            active = tuple(i for i in range(start, vl) if selected(mode, i))
                            raw = bytearray(SENTINEL)
                            sat = control >> 2
                            for i in active:
                                raw[i+1], raised = value(op, a[i], b[i], control)
                                sat |= raised
                            raw = bytes(raw)
                            identity = (seed, op, control & 3 if op == 0 else 0)
                            key = identity + (active,) if active else ('sentinel',)
                            require(key not in row_keys or row_keys[key] == raw,
                                    'Equal symbolic source keys must have equal bytes')
                            row_keys[key] = raw
                            ids = []
                            for block in range(9):
                                lo, hi = block*64, min(block*64+64, OUTPUT_BYTES)
                                piece = raw[lo:hi] + bytes(64-(hi-lo))
                                affected = tuple(i for i in active if lo <= i+1 < hi)
                                bk = identity + (block, affected) if affected else ('sentinel', block == 8)
                                require(bk not in block_keys or block_keys[bk] == piece,
                                        'Block source-key equality')
                                block_keys[bk] = piece
                                ids.append(intern_block(piece))
                            descriptor = tuple(ids)
                            if descriptor not in row_ids:
                                row_ids[descriptor] = len(rows); rows.append(descriptor)
                            row = row_ids[descriptor]
                            decoded = b''.join(blocks[i] for i in descriptor)[:OUTPUT_BYTES]
                            require(decoded == raw, 'Lossless complete514 byte oracle')
                            require((row == 0) == (raw == SENTINEL), 'Exact sentinel row qualification')
                            ordinal = len(calls)
                            calls.append(dict(ordinal=ordinal+1, seed=seed, op=op, li=li, vl=vl,
                                mode=mode, si=si, start=start, control=control, expected_sat=sat,
                                expected_hex=raw.hex(), row=row, block_ids=ids,
                                target_required=start < vl))
                            indices.append(row); sats.append(sat)
                            counts['calls'] += 1
                            counts['result_bytes'] += CAP
                            counts['guards'] += 2
                            counts['helper_instructions'] += 24
                            counts['actual_output_reads'] += 65
                            counts['fresh_output_stores'] += 65
                            counts['memory_owners'] += 5
                            counts['target_required'] += int(start < vl)
                            counts['active_elements'] += len(active)
                            counts['active_calls'] += bool(active)
                            if seed == 0 and op == 0 and mode == 0 and control == 0:
                                boundaries.append(dict(seed=seed,vl=vl,mode=mode,start=start,completed=ordinal))
    expected_counts = dict(calls=10752,result_bytes=5505024,guards=21504,
        helper_instructions=258048,actual_output_reads=698880,fresh_output_stores=698880,
        rng_iterations=1536,source_SB=4416,mask_epochs=336,mask_clear_SD=5376,
        mask_selected_SB=70644,memory_owners=53760,target_required=4608,
        active_elements=303744,active_calls=2976)
    require(dict(counts) == expected_counts, 'Full source-domain geometry')
    require(len(boundaries) == 28, 'All original boundary diagnostics')
    require(len(row_keys) <= 442 and len(block_keys) <= 716, 'Symbolic geometry bounds')
    require(len(rows) <= 442 and len(blocks) <= 716, 'Value dedup cannot exceed symbolic bound')
    require(max(indices) < 65536 and len(blocks) < 65536, 'uint16 ROM IDs')
    model = dict(status='GENERATED_UNTESTED_NOT_HOST_OR_REFERENCE', counts=dict(counts),
        seeds=seeds,masks=[dict(mode=i,hex=m.hex(),writes=w) for i,(m,w) in enumerate(masks)],
        calls=calls,boundaries=boundaries,symbolic_rows=len(row_keys),symbolic_blocks=len(block_keys),
        value_rows=len(rows),value_blocks=len(blocks),
        ROM_bytes=len(blocks)*64+len(rows)*18+CALLS*3)
    return model, blocks, rows, indices, sats


def expected_header(blocks, rows, indices, sats):
    lines = ['#ifndef FIXED10752_EXPECTED_H', '#define FIXED10752_EXPECTED_H',
             '#include <stdint.h>', '#define FIXED_SENTINEL_BLOCK 0', '#define FIXED_SENTINEL_TAIL 1',
             'static const uint64_t fixed_expected_blocks[][8] __attribute__((aligned(8))) = {']
    for b in blocks:
        words = [int.from_bytes(b[i:i+8], 'little') for i in range(0,64,8)]
        lines.append('{' + ','.join('UINT64_C(0x%016x)' % w for w in words) + '},')
    lines += ['};', 'static const uint16_t fixed_expected_rows[][9] = {']
    lines += ['{' + ','.join(map(str,row)) + '},' for row in rows]
    lines += ['};']
    for ctype, name, values in [('uint16_t','fixed_expected_index',indices),
                                ('uint8_t','fixed_expected_sat',sats)]:
        lines += [f'static const {ctype} {name}[10752] = {{']
        lines += [','.join(map(str,values[i:i+32]))+',' for i in range(0,CALLS,32)]
        lines += ['};']
    return '\n'.join(lines+['#endif',''])


def mask_header():
    lines = ['#ifndef FIXED10752_MASK_STORES_H', '#define FIXED10752_MASK_STORES_H',
             'FIXED_INLINE void fixed_build_mask(uint8_t *p, unsigned mode) {']
    lines += [f'    fixed_store64(p+{offset}, UINT64_C(0));' for offset in range(0,128,8)]
    lines += ['    switch (mode) {']
    for mode in range(3):
        lines += [f'    case {mode}:']
        lines += [f'        fixed_store8(p+{offset}, UINT8_C({value}));'
                  for offset,value in mask_sequence(mode)[1]]
        lines += ['        break;']
    lines += ['    case 3: break;', '    default: __builtin_trap();', '    }', '}', '#endif', '']
    return '\n'.join(lines)


def port_source(original):
    """Runtime substitutions only, common to scalar-original and packed ports."""
    start = original.index('static long syscall3(')
    end = original.index('static void text(', start)
    text = original[:start] + '#include "port.h"\n' + original[end:]
    text = replace_once(text, 'static void finish(long code) {\n    syscall3(94,code,0,0);for(;;){}\n}\n', '')
    startup = text.index('__asm__(".global _start')
    text = text[:startup]
    text = replace_once(text, 'void probe_main(void)', 'int fixed_full_main(void)')
    text = text.replace('finish(2);', 'return 2;')
    text = replace_once(text, 'finish(errors ? 1:0);', 'return errors ? 1:0;')
    text = replace_once(text, 'if(!cap || cap>1024)', 'if(cap!=512)')
    text = replace_once(text, '    __asm__ volatile("csrr %0,vlenb":"=r"(max_start));',
        '#if defined(__riscv)\n    __asm__ volatile("csrr %0,vlenb":"=r"(max_start));\n'
        '#else\n    max_start=fixed_host_vlenb();\n#endif\n'
        '    if(max_start!=128){text("RVV_MATRIX_UNSUPPORTED_VLENB\\n");return 2;}')
    return text


def packed_source(ported):
    text = replace_once(ported, 'static word a[1024], b[1024], out[1026];',
        'static word a[1024] __attribute__((aligned(8)));\n'
        'static word b[1024] __attribute__((aligned(8)));\n'
        'static word out[1026] __attribute__((aligned(8)));')
    text = replace_once(text, 'static uint8_t mask[128];',
                        'static uint8_t mask[128] __attribute__((aligned(8)));')
    text = replace_once(text, 'int fixed_full_main(void)', '#include "packed.h"\n\nint fixed_full_main(void)')
    # Preserve all three xorshift statements and every overwritten source byte.
    for old,new in [
        ('a[i]=random;b[i]=random>>19;', 'fixed_store8(a+i,(word)random);fixed_store8(b+i,(word)(random>>19));'),
        ('case 0:a[i]=0;b[i]=0;break;', 'case 0:fixed_store8(a+i,0);fixed_store8(b+i,0);break;'),
        ('case 1:a[i]=(word)-1;b[i]=1;break;', 'case 1:fixed_store8(a+i,(word)-1);fixed_store8(b+i,1);break;'),
        ('case 2:a[i]=(word)(UINT64_C(1)<<(SEW-1));b[i]=(word)-1;break;',
         'case 2:fixed_store8(a+i,(word)(UINT64_C(1)<<(SEW-1)));fixed_store8(b+i,(word)-1);break;'),
        ('case 3:b[i]=SEW;break;', 'case 3:fixed_store8(b+i,SEW);break;')]:
        text = replace_once(text, old, new)
    mask = ('                for(unsigned i=0;i<128;++i)mask[i]=0;\n'
            '                for(unsigned i=0;i<cap;++i)\n'
            '                    if(selected(mode,i))mask[i/8]|=1u<<(i%8);')
    text = replace_once(text, mask, '                fixed_build_mask(mask,mode);')
    init = ('                    for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;\n'
            '                    for(unsigned i=0;i<cap;++i)\n'
            '                        out[i+1]=initial_destination(accumulator,i);')
    text = replace_once(text, init, '                    fixed_initialize(out);')
    begin = text.index('                    unsigned packed=0;')
    end = text.index('                    ++checks;', begin)
    fallback = text[begin:end]
    # vstart check precedes this unchanged original block. It is never counted twice.
    replacement = ('                    if(fixed_mismatch((unsigned)checks,out)) {\n' + fallback +
        '                    } else {\n'
        '                        elements += cap;\n'
        '                        unsigned saturation=fixed_expected_sat[checks];\n'
        '                        if((vs>>32)!=saturation)\n'
        '                            failure(op,seed,vl,mode,start,cap+3,saturation,vs>>32);\n'
        '                    }\n')
    text = text[:begin] + replacement + text[end:]
    require(text.count(fallback) == 1, 'Full original error loop retained byte-for-byte')
    return text, fallback


def generate(out):
    inputs = {str(ORIGINAL/name):digest for name,digest in PINNED.items()}
    inputs.update({str(HERE/name):sha(HERE/name) for name in ('generate.py','packed.h','port.h','README.md')})
    for path,digest in inputs.items():
        require(sha(Path(path)) == digest, 'Input identity '+path)
    out.mkdir(parents=False, exist_ok=False)
    save(out/'inputs_before.json', inputs)
    try:
        original = (ORIGINAL/'successor_oracle.c').read_text()
        ported = port_source(original)
        packed, fallback = packed_source(ported)
        model, blocks, rows, indices, sats = make_model()
        for name in ('scenario.S','operations.h'):
            with (out/name).open('xb') as f:
                f.write((ORIGINAL/name).read_bytes())
            require(sha(out/name) == PINNED[name], 'Original assembly/header copy')
        save(out/'original_port.c', ported)
        save(out/'case.c', packed)
        save(out/'original_error_loop.c.fragment', fallback)
        save(out/'expected.h', expected_header(blocks, rows, indices, sats))
        save(out/'mask_stores.h', mask_header())
        for name in ('packed.h','port.h'):
            save(out/name, (HERE/name).read_text())
        save(out/'model.json', model)
        save(out/'source.diff', ''.join(difflib.unified_diff(ported.splitlines(True),packed.splitlines(True),
              fromfile='full_original_runtime_port',tofile='full10752_packed_port')))
        for path,digest in inputs.items():
            require(sha(Path(path)) == digest, 'Input changed during generation '+path)
        save(out/'inputs_after.json', inputs)
        artifacts = {str(p):sha(p) for p in out.iterdir() if p.is_file()}
        save(out/'GENERATED.json', dict(status='SOURCE_GENERATED_UNTESTED_NO_COMPILE_REFERENCE_DUT',
            input_pins=inputs, artifacts=artifacts, full_scope=model['counts'],
            actual_cost=None, original_Linux_replay=False, original_C_text_recovered=False))
    except Exception as exc:
        save(out/'GENERATION_FAILED.json', dict(status='FAILED', error=repr(exc)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--authorize-generate', action='store_true', required=True)
    args = parser.parse_args()
    generate(args.out.resolve())
