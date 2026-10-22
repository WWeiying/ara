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
CAP, SEW, MASK, SIGN, SENTINEL = 128, 32, (1 << 32) - 1, 1 << 31, 0x5b
RNG_MASK = (1 << 64) - 1
LENGTHS = (0, 1, 2, 3, 64, 127, 128)
STATIC = A / 'full_e32_m4_static_feasibility01'
REVIEW = A / 'full_e32_m4_static_review01/REVIEW.json'
PINS = {
    STATIC / 'PLAN.md': '6f5c84473b9c7ef7ee30e7df61d4b37d278f64bfa91348bad3b22039769b0b98',
    STATIC / 'SOURCE_PINS.json': '859975428067f9f8635bac88137a7a3372ded3bf0a8c4295d3aa26ea07bdeb02',
    REVIEW: '2377a847cfa82822816620ba4a1e3e617c0b922b0f4a993274eb8f7b268da17d',
}



def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def u32s(values):
    return b''.join(struct.pack('<I', value) for value in values)


def selected(mode, i):
    return mode == 0 or (bool(i & 1) if mode == 1 else i % 7 == 2)


def signed(value):
    return value - (1 << SEW) if value & SIGN else value


def source_value(op, x, y):
    if op == 0: value = x + y
    elif op == 1: value = x - y
    elif op == 2: value = x & y
    elif op == 3: value = x | y
    elif op == 4: value = x ^ y
    elif op == 5: value = x << (y & (SEW - 1))
    elif op == 6: value = x >> (y & (SEW - 1))
    elif op == 7: value = signed(x) >> (y & (SEW - 1))
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
    for bit in range(SEW - 1, -1, -1):
        remainder = remainder * 2 + ((numerator >> bit) & 1)
        if remainder >= denominator:
            remainder -= denominator
            quotient += 1 << bit
    return quotient, remainder


def math_value(op, x, y):
    modulus = 2 ** SEW
    sx = x if x < SIGN else x - modulus
    sy = y if y < SIGN else y - modulus
    if op in (0, 1, 17, 18):
        return (x + {0: y, 1: -y, 17: 7, 18: 3}[op]) % modulus
    if op in (2, 3, 4):
        return sum((1 << bit) for bit in range(SEW)
                   if ((x // (1 << bit)) % 2 + (y // (1 << bit)) % 2)
                   in ({2: (2,), 3: (1, 2), 4: (1,)}[op]))
    if op == 5: return (x * 2 ** (y % SEW)) % modulus
    if op == 6: return x // 2 ** (y % SEW)
    if op == 7: return (sx // 2 ** (y % SEW)) % modulus
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
    aa, bb, writes = [], [], []
    for i in range(CAP):
        random ^= (random << 13) & RNG_MASK
        random ^= random >> 7
        random ^= (random << 17) & RNG_MASK
        x, y = random & MASK, (random >> 19) & MASK
        writes.extend(((2 * i, x), (2 * i + 1, y)))
        if i % 8 == 0: x = y = 0
        elif i % 8 == 1: x, y = MASK, 1
        elif i % 8 == 2: x, y = SIGN, MASK
        elif i % 8 == 3: y = SEW
        if i % 8 in (0, 1, 2):
            writes.extend(((2 * i, x), (2 * i + 1, y)))
        elif i % 8 == 3:
            writes.append((2 * i + 1, y))
        aa.append(x); bb.append(y)
    return aa, bb, random, writes


def math_seed(seed):
    bits = [(0x937ad68de41c725f ^ seed) >> k & 1 for k in range(64)]
    aa, bb, writes = [], [], []
    for i in range(CAP):
        for shift, left in ((13, True), (7, False), (17, True)):
            old = bits
            bits = [old[k] ^ (old[k - shift] if left and k >= shift else
                              old[k + shift] if not left and k + shift < 64 else 0)
                    for k in range(64)]
        value = sum(bit * (2 ** k) for k, bit in enumerate(bits))
        writes.extend(((2 * i, value % (2 ** SEW)),
                       (2 * i + 1, (value // (2 ** 19)) % (2 ** SEW))))
        pair = {0: (0, 0), 1: (MASK, 1), 2: (SIGN, MASK),
                3: (value, SEW)}.get(i % 8, (value, value // (2 ** 19)))
        aa.append(pair[0] % (2 ** SEW)); bb.append(pair[1] % (2 ** SEW))
        if i % 8 < 3:
            writes.extend(((2 * i, aa[-1]), (2 * i + 1, bb[-1])))
        elif i % 8 == 3:
            writes.append((2 * i + 1, SEW))
    return aa, bb, value, writes


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
    predicate = (set(range(CAP)), set(range(1, CAP, 2)), set(range(2, CAP, 7)))[mode]
    active = sorted(predicate.intersection(range(vl)))
    output = [91] * CAP
    if op == 22:
        if vl > 0: output[0] = (bb[0] + sum(aa[i] for i in active)) % (2 ** SEW)
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


def reuse_analysis(rows, blocks, gold):
    # Compare immutable expected-cache reconstruction with EVERY original output byte.
    hist_full, hist_nine = {}, {}
    totals = dict(actual_output_LD=0, baseline_expected_LD=0, ideal_expected_LD=0,
                  adjacent_expected_LD=0, chosen_single_cache_expected_LD=0,
                  adjacent_full_hits=0, adjacent_last_hits=0, ideal_full_hits=0)
    by_op = {}
    for row in rows:
        ids = row['ids']
        require(len(ids) == 9, 'Nine block IDs per original call')
        distinct = len(set(ids[:8]))
        hist_full[distinct] = hist_full.get(distinct, 0) + 1
        hist_nine[len(set(ids))] = hist_nine.get(len(set(ids)), 0) + 1
        expected = bytes(gold[(row['ordinal'] - 1) * 520:row['ordinal'] * 520])
        # Ideal all-unique-block cache is an upper benefit bound, not a register allocation.
        cache, reconstructed, ideal = {}, bytearray(), 0
        for i, block_id in enumerate(ids):
            nbytes = 64 if i < 8 else 8
            if block_id not in cache:
                cache[block_id] = blocks[block_id][:nbytes]
                ideal += nbytes // 8
            reconstructed.extend(cache[block_id][:nbytes])
        require(bytes(reconstructed) == expected, 'Ideal expected cache lost data')
        last_id, last_block, reconstructed, adjacent = None, None, bytearray(), 0
        full_hits = last_hits = 0
        for i, block_id in enumerate(ids):
            nbytes = 64 if i < 8 else 8
            if block_id != last_id:
                last_block = blocks[block_id][:nbytes]
                last_id = block_id
                adjacent += nbytes // 8
            elif i < 8:
                full_hits += 1
            else:
                last_hits += 1
            reconstructed.extend(last_block[:nbytes])
        require(bytes(reconstructed) == expected, 'Last-block expected cache lost data')
        # One chosen persistent block costs an extra per-call ID if implemented.
        best = 65
        for chosen in set(ids[:8]):
            cost, cached, rebuilt = 0, None, bytearray()
            for i, block_id in enumerate(ids):
                nbytes = 64 if i < 8 else 8
                if block_id != chosen or cached is None:
                    cost += nbytes // 8
                    value = blocks[block_id][:nbytes]
                    if block_id == chosen:
                        cached = value
                else:
                    value = cached[:nbytes]
                rebuilt.extend(value)
            require(bytes(rebuilt) == expected, 'Chosen-block cache lost data')
            best = min(best, cost)
        values = dict(actual_output_LD=65, baseline_expected_LD=65,
                      ideal_expected_LD=ideal, adjacent_expected_LD=adjacent,
                      chosen_single_cache_expected_LD=best, adjacent_full_hits=full_hits,
                      adjacent_last_hits=last_hits, ideal_full_hits=8-distinct)
        row['expected_cache_counts'] = values
        for key, value in values.items():
            totals[key] += value
            by_op.setdefault(row['op'], {}).setdefault(key, 0)
            by_op[row['op']][key] += value
    for name in ('ideal', 'adjacent', 'chosen_single_cache'):
        totals[name + '_expected_LD_saved'] = totals['baseline_expected_LD'] - totals[name + '_expected_LD']
    return dict(totals=totals, distinct_first8_histogram=hist_full,
                distinct_all9_histogram=hist_nine, by_op=by_op,
                additional_chosen_ID_bytes=len(rows) * 2,
                cost_scope='Counts only. No GCC code, measured cost, actual output reuse, or fresh-input-write removal.',
                all_calls_reconstructed=True)


def main():
    begin = time.monotonic()
    out = HERE / 'generated01'
    out.mkdir(exist_ok=False)
    require(all(sha(p.read_bytes()) == h for p, h in PINS.items()), 'Static approval drift')
    require(json.loads(REVIEW.read_text())['source_plan_no_blocker'] is True, 'Missing source approval')
    PINS.update({Path(p): h for p, h in json.loads((STATIC / 'SOURCE_PINS.json').read_text())['source_pins'].items()})
    pins = {str(p): sha(p.read_bytes()) for p in PINS}
    require(all(pins[str(p)] == h for p, h in PINS.items()), 'Original input drift')
    pins[str(Path(__file__).resolve())] = sha(Path(__file__).read_bytes())
    (out / 'input_pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    header = (C / 'e32/operations.h').read_text()
    kinds = list(map(int, re.search(r'^#define OPERATION_KINDS\s+(.+)$', header, re.M)[1].split(',')))
    require(kinds == [0] * 19 + [1, 1, 1, 2, 3, 0] + [0] * 10, 'Actual operation kinds')
    def table(pattern):
        return [int(v, 16) for v in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)', re.search(pattern, header, re.S)[1])]
    inputs = table(r'fp_inputs\[8\]\s*=\s*\{(.*?)\};')
    fp = table(r'fp_expected\[10\]\[64\]\s*=\s*\{(.*?)\};')
    elf = (C / 'overlay/opt/ara-tests/rvv_matrix_e32_m4').read_bytes()
    require(len(inputs) == 8 and len(fp) == 640, 'Original FP dimensions')
    require(elf[0x1590:0x15b0] == u32s(inputs) and elf[0x15b0:0x1fb0] == u32s(fp), 'Actual ELF original bit tables')
    require(elf.count(u32s(fp)) == 1, 'Unique original640 table')
    # Independent tuple expansion does not use kinds or the source nesting.
    catalog = [(seed, op, li, mode, si, vl, (0, vl // 2, min(vl, CAP - 1))[si])
               for seed, op, li, mode in itertools.product(range(3), range(35), range(7), range(3))
               for vl in [LENGTHS[li]] for si in range(1 if 19 <= op <= 23 else 3)]
    gold, ids, blocks, lookup, rows, seed_records = bytearray(), [], [], {}, [], []
    source_writes, math_writes = hashlib.sha256(), hashlib.sha256()
    fp_ledger = bytearray()
    write_count = fp_calls = compared = 0
    periods = []
    mask_source, mask_math = bytearray(), bytearray()
    mask_groups = selected_writes = 0
    masks = [bytes(sum(1 << (i % 8) for i in range(j * 8, min(j * 8 + 8, CAP)) if selected(mode, i))
                   for j in range(128)) for mode in range(3)]
    for seed in range(3):
        aa, bb, rng, seed_writes = source_seed(seed)
        ma, mb, mrng, independent_writes = math_seed(seed)
        require((aa, bb, rng, seed_writes) == (ma, mb, mrng, independent_writes), 'Independent seed RNG/write mismatch')
        seed_records.append(dict(seed=seed, rng_exit=f'{rng:016x}', a=aa[:], b=bb[:],
                                 source_order_assignments=seed_writes))
        period = [(inputs[(j + seed) % 8], inputs[(3 * j + seed) % 8]) for j in range(8)]
        periods.extend(value for _ in range(CAP // 8) for pair in period for value in pair)
        for op in range(35):
            for li, vl in enumerate(LENGTHS):
                for mode in range(3):
                    mask_groups += 1
                    actual_mask = bytearray(128)
                    independent_mask = bytearray([255] * 128)
                    # Source SB clear ledger; future packed lowering must cover the same 128 bytes.
                    for offset in range(128):
                        mask_source.extend(struct.pack('<IHHB', mask_groups, 0, offset, 0))
                        independent_mask[offset] = 0
                        mask_math.extend(struct.pack('<IHHB', mask_groups, 0, offset, 0))
                    for i in range(CAP):
                        if selected(mode, i):
                            actual_mask[i // 8] |= 1 << (i % 8)
                            mask_source.extend(struct.pack('<IHHB', mask_groups, 1, i // 8, actual_mask[i // 8]))
                            selected_writes += 1
                    positions = (range(CAP), range(1, CAP, 2), range(2, CAP, 7))[mode]
                    for i in positions:
                        independent_mask[i // 8] += 2 ** (i % 8)
                        mask_math.extend(struct.pack('<IHHB', mask_groups, 1, i // 8, independent_mask[i // 8]))
                    require(actual_mask == independent_mask == masks[mode] and not any(actual_mask[16:]), 'Full128B mask')
                    for si in range(3 if kinds[op] == 0 else 1):
                        start = 0 if si == 0 else vl // 2 if si == 1 else vl if vl < CAP else CAP - 1
                        ordinal = len(rows) + 1
                        require(catalog[ordinal - 1] == (seed, op, li, mode, si, vl, start), 'Full history order')
                        if op >= 25:
                            fp_calls += 1
                            for i in range(CAP):
                                aa[i] = inputs[(i + seed) % 8]
                                record = struct.pack('<III', ordinal, 2 * i, aa[i])
                                source_writes.update(record); fp_ledger.extend(record)
                                bb[i] = inputs[(3 * i + seed) % 8]
                                record = struct.pack('<III', ordinal, 2 * i + 1, bb[i])
                                source_writes.update(record); fp_ledger.extend(record)
                                write_count += 2
                            pairs = period * (CAP // 8)
                            ma, mb = [p[0] for p in pairs], [p[1] for p in pairs]
                            for index, value in enumerate(v for pair in pairs for v in pair):
                                math_writes.update(struct.pack('<III', ordinal, index, value))
                        require(aa == ma and bb == mb, f'Full input/history mismatch call{ordinal}')
                        values = source_output(op, kinds[op], seed, vl, mode, start, aa, bb, fp)
                        independent = math_output(op, seed, vl, mode, start, ma, mb, fp)
                        require(len(values) == len(independent) == 130, 'Full result/guard lengths')
                        for i, (left, right) in enumerate(zip(values, independent)):
                            require(left == right, f'Oracle mismatch call{ordinal} word{i}: {left} != {right}')
                            compared += 1
                        raw = u32s(values)
                        require(len(raw) == 520, 'All65 packed words, including both typed32 guards')
                        row_ids = []
                        for offset in range(0, 520, 64):
                            block = raw[offset:offset + 64].ljust(64, b'\0')
                            if block not in lookup:
                                lookup[block] = len(blocks); blocks.append(block)
                            row_ids.append(lookup[block])
                        rebuilt = b''.join(blocks[index] for index in row_ids)
                        require(rebuilt[:520] == raw and rebuilt[520:] == bytes(56), 'Lossless9IDs/last8B')
                        gold.extend(raw); ids.extend(row_ids)
                        rows.append(dict(ordinal=ordinal, seed=seed, op=op, li=li, vl=vl, mode=mode,
                                         trial=si, start=start, ids=row_ids, returned_vstart=0,
                                         input_sha256=sha(u32s(aa) + u32s(bb)),
                                         output_sha256=sha(raw), fp_ordered_writes=256 if op >= 25 else 0))
    require(len(rows) == len(catalog) == 5985 and fp_calls == 1890, 'Full5985 scope')
    require(compared == 778050 and write_count == 483840, 'Full word/write comparison')
    require(sum(len(r['source_order_assignments']) for r in seed_records) == 1104, 'All seed assignments')
    require(source_writes.digest() == math_writes.digest(), 'Ordered per-call FP write ledger')
    require(len(blocks) <= 8856, 'Static pool upper bound and uint16 block IDs')
    require(mask_groups == 2205 and selected_writes == 154350, 'Full mask-write scope')
    require(mask_source == mask_math, 'Exact ordered mask clear/selected SB ledger')
    reuse = reuse_analysis(rows, blocks, gold)
    boundary_checks = 0
    for x, y in itertools.product((0, 1, 31, 32, SIGN - 1, SIGN, MASK), repeat=2):
        for op in range(19):
            require(source_value(op, x, y) == math_value(op, x, y), 'Mathematical corner mismatch')
            boundary_checks += 1
    binaries = {'gold_u32le.bin': bytes(gold), 'dictionary64.bin': b''.join(blocks),
                'indices_u16le.bin': struct.pack('<' + 'H' * len(ids), *ids),
                'masks128.bin': b''.join(masks), 'fp_expected640_u32le.bin': u32s(fp),
                'fp_inputs8_u32le.bin': u32s(inputs), 'fp_ordered_periods3_u32le.bin': u32s(periods)}
    binaries['mask_source_ledger.bin'] = bytes(mask_source)
    binaries['fp_source_ledger.bin'] = bytes(fp_ledger)
    for name, data in binaries.items(): (out / name).write_bytes(data)
    (out / 'calls.json').write_text(json.dumps(rows, separators=(',', ':')) + '\n')
    (out / 'seed_inputs.json').write_text(json.dumps(seed_records, indent=2) + '\n')
    (out / 'reuse.json').write_text(json.dumps(reuse, indent=2) + '\n')
    require(all(sha(Path(p).read_bytes()) == h for p, h in pins.items()), 'Post input drift')
    rom = len(blocks) * 64 + 107730 + 384 + 2560 + 32
    artifacts = {p.name: dict(bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
                 for p in sorted(out.iterdir()) if p.is_file()}
    result = dict(status='FULL5985_SOURCE_MATH_MODEL_AGREE_NOT_COMPILED_NOT_SPIKE_NOT_DUT',
                  shape=dict(sew=32, lmul='m4', vtype=18, cap=128, physical_group=4),
                  calls=5985, integer_calls=4095, fp_calls=1890, results=766080, guards=11970,
                  vstart_required=5985, dynamic_helper_instructions=77805,
                  compared_words=compared, output_bytes_per_call=520, words_per_call=65,
                  dictionary_blocks=len(blocks), dictionary_bytes=len(blocks) * 64,
                  index_count=len(ids), index_bytes=len(ids) * 2, last_block_valid_bytes=8,
                  rom_components_bytes=rom, envelope_with_168096_reserved=rom + 168096,
                  one_mib_slack=1048576 - rom - 168096,
                  fp_ordered_write_count=write_count, fp_ordered_write_bytes=write_count * 4,
                  fp_ordered_writes_sha256=source_writes.hexdigest(),
                  seed_source_assignments=1104, original_fflags_oracle=False,
                  mask_groups=mask_groups, mask_clear_source_SB=mask_groups * 128,
                  mask_clear_proposed_SD=mask_groups * 16, selected_mask_SB=selected_writes,
                  mask_ordered_ledger_sha256=sha(mask_source), actual_output_reads_required=5985 * 65,
                  mathematical_integer_corner_checks=boundary_checks,
                  input_pins_unchanged=True, first_call=rows[0], last_call=rows[-1],
                  elapsed_model_seconds=time.monotonic() - begin, artifacts=artifacts,
                  limitation='Two Python source/math models, same archival FP table. Not compiled-C equivalence or independent agent acceptance. No measured firmware cost or returned CSR.')
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'calls', 'dictionary_blocks', 'dictionary_bytes',
                                           'rom_components_bytes', 'one_mib_slack', 'elapsed_model_seconds')}))


if __name__ == '__main__':
    main()

