"""Authorized source-model construction, not execution of compiled C or RVV."""
import hashlib
import itertools
import json
from pathlib import Path
import re
import struct
import time

HERE = Path(__file__).resolve().parent
A = HERE.parent
C = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
CAP, MASK, SIGN, SENTINEL = 64, (1 << 64) - 1, 1 << 63, 0x5b
LENGTHS = (0, 1, 2, 3, 32, 63, 64)
PINS = {
    C / 'overlay/opt/ara-tests/rvv_matrix_e64_m4': 'c8e9bad5a0247cb63c9b908a316b5b0f775b242984e187d66f1aa7b3137720f6',
    A / 'recovery22/rvv_matrix_e64_m4': 'c8e9bad5a0247cb63c9b908a316b5b0f775b242984e187d66f1aa7b3137720f6',
    C / 'rvv_matrix_e64_m4.S': '197c07724fae208a10ef773f962d3f820d842d9449ad81b447121fdb52805b5f',
    C / 'e64/operations.h': 'bae4c627a4db226bd6a4a41601950aaf1401819933e9f568ce210a7c54922062',
    C / 'manifest.json': '6cabb1e462113d3e4c26b29622c6abcfba7cbedbc52fe7b3bfc860678b8a8ce6',
    C / 'resume03_report.json': '618569f7d0086f05ede82c5f8993c67dc9ed5c634d97d66b642058af648cc94e',
    A / 'recovery22/reconstructed_oracle.c': '7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91',
    A / 'recovery22/report.json': 'b11efd30ec97318d8d4cb37468ae39fea7085f6235fd79a68589e2a6455b8266',
    A / 'recovery22/rvv_matrix_e64_m4_decode/original.dis': 'd0cb511b8abc1523d4768e86e130efa025cb0f47ec0d5ef04d9fd52809bd0be3',
    A / 'full_e64_m4_static_feasibility01/STATIC_PLAN.md': '7895aaf7c148ef2f9515bd9f18c3f7974c47daf1b16a68cbeea3c83056f3d0d5',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def u64s(values):
    return b''.join(struct.pack('<Q', value) for value in values)


def selected(mode, i):
    return mode == 0 or (bool(i & 1) if mode == 1 else i % 7 == 2)


def signed(value):
    return value - (1 << 64) if value & SIGN else value


def source_value(op, x, y):
    if op == 0: value = x + y
    elif op == 1: value = x - y
    elif op == 2: value = x & y
    elif op == 3: value = x | y
    elif op == 4: value = x ^ y
    elif op == 5: value = x << (y & 63)
    elif op == 6: value = x >> (y & 63)
    elif op == 7: value = signed(x) >> (y & 63)
    elif op == 8: value = min(x, y)
    elif op == 9: value = max(x, y)
    elif op == 10: value = x if signed(x) < signed(y) else y
    elif op == 11: value = x if signed(x) > signed(y) else y
    elif op == 12: value = x * y
    elif op == 13: value = x // y if y else MASK
    elif op == 14: value = x % y if y else x
    elif op in (15, 16):
        sx, sy = signed(x), signed(y)
        if not sy: value = MASK if op == 15 else x
        elif x == SIGN and y == MASK: value = x if op == 15 else 0
        else:
            quotient = abs(sx) // abs(sy)
            if (sx < 0) != (sy < 0): quotient = -quotient
            value = quotient if op == 15 else sx - quotient * sy
    elif op == 17: value = x + 7
    elif op == 18: value = x + 3
    else: raise ValueError('Not an integer arithmetic operation')
    return value & MASK


def math_division(numerator, denominator):
    # Independent restoring division, rather than Python signed // semantics.
    quotient = remainder = 0
    for bit in range(63, -1, -1):
        remainder = remainder * 2 + ((numerator >> bit) & 1)
        if remainder >= denominator:
            remainder -= denominator
            quotient += 1 << bit
    return quotient, remainder


def math_value(op, x, y):
    modulus = 2 ** 64
    sx = x if x < 2 ** 63 else x - modulus
    sy = y if y < 2 ** 63 else y - modulus
    if op in (0, 1, 17, 18):
        return (x + {0: y, 1: -y, 17: 7, 18: 3}[op]) % modulus
    if op in (2, 3, 4):
        return sum((1 << bit) for bit in range(64)
                   if ((x // (1 << bit)) % 2 + (y // (1 << bit)) % 2)
                   in ({2: (2,), 3: (1, 2), 4: (1,)}[op]))
    if op == 5: return (x * 2 ** (y % 64)) % modulus
    if op == 6: return x // 2 ** (y % 64)
    if op == 7: return (sx // 2 ** (y % 64)) % modulus
    if op in (8, 9, 10, 11):
        xx, yy = (sx, sy) if op >= 10 else (x, y)
        choose_x = xx <= yy if op % 2 == 0 else xx >= yy
        return x if choose_x else y
    if op == 12: return (x * y) % modulus
    if op in (13, 14):
        if y == 0: return MASK if op == 13 else x
        q, r = math_division(x, y)
        return q if op == 13 else r
    if op in (15, 16):
        if sy == 0: return MASK if op == 15 else x
        q, r = math_division(abs(sx), abs(sy))
        return ((-q if (sx < 0) != (sy < 0) else q) if op == 15
                else (-r if sx < 0 else r)) % modulus
    raise ValueError('Unknown mathematical operation')


def source_seed(seed):
    random = 0x937ad68de41c725f ^ seed
    aa, bb = [], []
    for i in range(CAP):
        random ^= (random << 13) & MASK
        random ^= random >> 7
        random ^= (random << 17) & MASK
        x, y = random, random >> 19
        if i % 8 == 0: x = y = 0
        elif i % 8 == 1: x, y = MASK, 1
        elif i % 8 == 2: x, y = SIGN, MASK
        elif i % 8 == 3: y = 64
        aa.append(x); bb.append(y)
    return aa, bb, random


def math_seed(seed):
    bits = [(0x937ad68de41c725f ^ seed) >> k & 1 for k in range(64)]
    aa, bb = [], []
    for i in range(64):
        for shift, left in ((13, True), (7, False), (17, True)):
            old = bits
            bits = [old[k] ^ (old[k - shift] if left and k >= shift else
                              old[k + shift] if not left and k + shift < 64 else 0)
                    for k in range(64)]
        value = sum(bit * (2 ** k) for k, bit in enumerate(bits))
        pair = {0: (0, 0), 1: (MASK, 1), 2: (SIGN, MASK),
                3: (value, 64)}.get(i % 8, (value, value // (2 ** 19)))
        aa.append(pair[0]); bb.append(pair[1])
    return aa, bb, value


def source_output(op, kind, seed, vl, mode, start, aa, bb, fp):
    result, packed, reduced = [], 0, bb[0]
    if kind == 2:
        for i in range(vl):
            if selected(mode, i): reduced = (reduced + aa[i]) & MASK
    for i in range(CAP):
        expected = SENTINEL
        if kind == 2:
            if i == 0 and vl: expected = reduced
        elif kind == 3:
            while packed < vl and not selected(mode, packed): packed += 1
            if packed < vl:
                expected = aa[packed]; packed += 1
        elif i < vl and i >= start and selected(mode, i):
            if op < 19: expected = source_value(op, aa[i], bb[i])
            elif op == 19:
                if i >= 2: expected = aa[i - 2]
            elif op == 20: expected = aa[i + 2] if i + 2 < CAP else 0
            elif op == 21: expected = aa[bb[i]] if bb[i] < CAP else 0
            elif op == 24: expected = aa[i]
            elif op >= 25: expected = fp[(op - 25) * 64 + ((i + seed) % 8) * 8 + (3 * i + seed) % 8]
        result.append(expected)
    return [SENTINEL] + result + [SENTINEL]


def math_output(op, seed, vl, mode, start, aa, bb, fp):
    predicate = (set(range(64)), set(range(1, 64, 2)), set(range(2, 64, 7)))[mode]
    active = sorted(predicate.intersection(range(vl)))
    output = [91] * 64
    if op == 22:
        if vl > 0: output[0] = (bb[0] + sum(aa[i] for i in active)) % (2 ** 64)
    elif op == 23:
        output[:len(active)] = [aa[i] for i in active]
    else:
        for i in active:
            if i < start: continue
            if op <= 18: output[i] = math_value(op, aa[i], bb[i])
            elif op == 19:
                if i > 1: output[i] = aa[i - 2]
            elif op == 20: output[i] = (aa + [0, 0])[i + 2]
            elif op == 21: output[i] = dict(enumerate(aa)).get(bb[i], 0)
            elif op == 24: output[i] = aa[i]
            else:
                phase = i % 8
                row, column = (phase + seed) % 8, (phase * 3 + seed) % 8
                output[i] = fp[(op - 25) * 64: (op - 24) * 64][8 * row + column]
    return [91, *output, 91]


def main():
    begin = time.monotonic()
    out = HERE / 'generated01'
    out.mkdir(exist_ok=False)
    pins = {str(p): sha(p.read_bytes()) for p in PINS}
    require(all(pins[str(p)] == h for p, h in PINS.items()), 'Original input drift')
    pins[str(Path(__file__).resolve())] = sha(Path(__file__).read_bytes())
    (out / 'input_pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    header = (C / 'e64/operations.h').read_text()
    kinds = list(map(int, re.search(r'^#define OPERATION_KINDS\s+(.+)$', header, re.M)[1].split(',')))
    require(kinds == [0] * 19 + [1, 1, 1, 2, 3, 0] + [0] * 10, 'Actual operation kinds')
    def table(pattern):
        return [int(v, 16) for v in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)', re.search(pattern, header, re.S)[1])]
    inputs = table(r'fp_inputs\[8\]\s*=\s*\{(.*?)\};')
    fp = table(r'fp_expected\[10\]\[64\]\s*=\s*\{(.*?)\};')
    elf = (C / 'overlay/opt/ara-tests/rvv_matrix_e64_m4').read_bytes()
    require(len(inputs) == 8 and len(fp) == 640, 'Original FP dimensions')
    require(elf[0x1520:0x1560] == u64s(inputs) and elf[0x1560:0x2960] == u64s(fp), 'Actual ELF original bit tables')
    require(elf.count(u64s(fp)) == 1, 'Unique original640 table')
    # Independent tuple expansion does not use kinds or the source nesting.
    catalog = [(seed, op, li, mode, si, vl, (0, vl // 2, min(vl, 63))[si])
               for seed, op, li, mode in itertools.product(range(3), range(35), range(7), range(3))
               for vl in [LENGTHS[li]] for si in range(1 if 19 <= op <= 23 else 3)]
    gold, ids, blocks, lookup, rows, seed_records = bytearray(), [], [], {}, [], []
    source_writes, math_writes = hashlib.sha256(), hashlib.sha256()
    write_count = fp_calls = compared = 0
    periods = []
    masks = [bytes(sum(1 << (i % 8) for i in range(j * 8, min(j * 8 + 8, 64)) if selected(mode, i))
                   for j in range(128)) for mode in range(3)]
    for seed in range(3):
        aa, bb, rng = source_seed(seed)
        ma, mb, mrng = math_seed(seed)
        require((aa, bb, rng) == (ma, mb, mrng), 'Independent seed RNG mismatch')
        seed_records.append(dict(seed=seed, rng_exit=f'{rng:016x}', a=aa[:], b=bb[:]))
        period = [(inputs[(j + seed) % 8], inputs[(3 * j + seed) % 8]) for j in range(8)]
        periods.extend(value for _ in range(8) for pair in period for value in pair)
        for op in range(35):
            for li, vl in enumerate(LENGTHS):
                for mode in range(3):
                    actual_mask = bytearray(128)
                    for i in range(CAP):
                        if selected(mode, i): actual_mask[i // 8] |= 1 << (i % 8)
                    require(actual_mask == masks[mode] and not any(actual_mask[8:]), 'Full128B mask')
                    for si in range(3 if kinds[op] == 0 else 1):
                        start = 0 if si == 0 else vl // 2 if si == 1 else vl if vl < CAP else CAP - 1
                        ordinal = len(rows) + 1
                        require(catalog[ordinal - 1] == (seed, op, li, mode, si, vl, start), 'Full history order')
                        if op >= 25:
                            fp_calls += 1
                            for i in range(CAP):
                                aa[i] = inputs[(i + seed) % 8]
                                source_writes.update(struct.pack('<IIQ', ordinal, 2 * i, aa[i]))
                                bb[i] = inputs[(3 * i + seed) % 8]
                                source_writes.update(struct.pack('<IIQ', ordinal, 2 * i + 1, bb[i]))
                                write_count += 2
                            pairs = period * 8
                            ma, mb = [p[0] for p in pairs], [p[1] for p in pairs]
                            for index, value in enumerate(v for pair in pairs for v in pair):
                                math_writes.update(struct.pack('<IIQ', ordinal, index, value))
                        require(aa == ma and bb == mb, f'Full input/history mismatch call{ordinal}')
                        values = source_output(op, kinds[op], seed, vl, mode, start, aa, bb, fp)
                        independent = math_output(op, seed, vl, mode, start, ma, mb, fp)
                        for i, (left, right) in enumerate(zip(values, independent)):
                            require(left == right, f'Oracle mismatch call{ordinal} word{i}: {left} != {right}')
                            compared += 1
                        raw = u64s(values)
                        require(len(raw) == 528, 'All66 words, including both typed64 guards')
                        row_ids = []
                        for offset in range(0, 528, 64):
                            block = raw[offset:offset + 64].ljust(64, b'\0')
                            if block not in lookup:
                                lookup[block] = len(blocks); blocks.append(block)
                            row_ids.append(lookup[block])
                        rebuilt = b''.join(blocks[index] for index in row_ids)
                        require(rebuilt[:528] == raw and rebuilt[528:] == bytes(48), 'Lossless9IDs/last16B')
                        gold.extend(raw); ids.extend(row_ids)
                        rows.append(dict(ordinal=ordinal, seed=seed, op=op, li=li, vl=vl, mode=mode,
                                         trial=si, start=start, ids=row_ids, returned_vstart=0,
                                         input_sha256=sha(u64s(aa) + u64s(bb)),
                                         output_sha256=sha(raw), fp_ordered_writes=128 if op >= 25 else 0))
    require(len(rows) == len(catalog) == 5985 and fp_calls == 1890, 'Full5985 scope')
    require(compared == 395010 and write_count == 241920, 'Full word/write comparison')
    require(source_writes.digest() == math_writes.digest(), 'Ordered per-call FP write ledger')
    require(len(blocks) < 65536, 'uint16 block IDs')
    boundary_checks = 0
    for x, y in itertools.product((0, 1, 63, 64, SIGN - 1, SIGN, MASK), repeat=2):
        for op in range(19):
            require(source_value(op, x, y) == math_value(op, x, y), 'Mathematical corner mismatch')
            boundary_checks += 1
    binaries = {'gold_u64le.bin': bytes(gold), 'dictionary64.bin': b''.join(blocks),
                'indices_u16le.bin': struct.pack('<' + 'H' * len(ids), *ids),
                'masks128.bin': b''.join(masks), 'fp_expected640_u64le.bin': u64s(fp),
                'fp_inputs8_u64le.bin': u64s(inputs), 'fp_ordered_periods3_u64le.bin': u64s(periods)}
    for name, data in binaries.items(): (out / name).write_bytes(data)
    (out / 'calls.json').write_text(json.dumps(rows, separators=(',', ':')) + '\n')
    (out / 'seed_inputs.json').write_text(json.dumps(seed_records, indent=2) + '\n')
    require(all(sha(Path(p).read_bytes()) == h for p, h in pins.items()), 'Post input drift')
    rom = len(blocks) * 64 + 107730 + 384 + 5184
    artifacts = {p.name: dict(bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
                 for p in sorted(out.iterdir()) if p.is_file()}
    result = dict(status='FULL5985_SOURCE_MATH_MODEL_AGREE_NOT_COMPILED_NOT_SPIKE_NOT_DUT',
                  shape=dict(sew=64, lmul='m4', vtype=26, cap=64, physical_group=4),
                  calls=5985, integer_calls=4095, fp_calls=1890, results=383040, guards=11970,
                  vstart_required=5985, dynamic_helper_instructions=77805,
                  compared_words=compared, output_bytes_per_call=528, words_per_call=66,
                  dictionary_blocks=len(blocks), dictionary_bytes=len(blocks) * 64,
                  index_count=len(ids), index_bytes=len(ids) * 2, last_block_valid_bytes=16,
                  rom_components_bytes=rom, envelope_with_172200_reserved=rom + 172200,
                  one_mib_slack=1048576 - rom - 172200,
                  fp_ordered_write_count=write_count, fp_ordered_write_bytes=write_count * 8,
                  fp_ordered_writes_sha256=source_writes.hexdigest(),
                  mathematical_integer_corner_checks=boundary_checks,
                  input_pins_unchanged=True, first_call=rows[0], last_call=rows[-1],
                  elapsed_model_seconds=time.monotonic() - begin, artifacts=artifacts,
                  limitation='Two Python source/math models, same archival FP table. Not compiled-C equivalence or independent agent acceptance. No measured firmware cost or returned CSR.')
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'calls', 'dictionary_blocks', 'dictionary_bytes',
                                           'rom_components_bytes', 'one_mib_slack', 'elapsed_model_seconds')}))


if __name__ == '__main__':
    main()
