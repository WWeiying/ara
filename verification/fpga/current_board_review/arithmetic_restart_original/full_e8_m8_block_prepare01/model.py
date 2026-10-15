"""Exact e8/m8 full4095 sequence; deduplicate64B values, never calls."""
import importlib.util
from pathlib import Path

CAP = 1024
CALLS = 4095
GROUPS = 17
KINDS = [0]*19 + [1, 1, 1, 2, 3, 0]
spec = importlib.util.spec_from_file_location('accepted_integer_model',
    Path(__file__).resolve().parent.parent/'full_e16_mf4_prepare01/model.py')
integer_model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integer_model)
integer = integer_model.integer
selected = integer_model.selected

def generate():
    seeds, rows, dictionary, lookup = [], [], [], {}
    for seed in range(3):
        rng = 0x937ad68de41c725f ^ seed
        a, b = [], []
        for i in range(CAP):
            rng ^= (rng << 13) & ((1 << 64)-1)
            rng ^= rng >> 7
            rng ^= (rng << 17) & ((1 << 64)-1)
            x, y = rng & 255, (rng >> 19) & 255
            if i % 8 == 0: x = y = 0
            elif i % 8 == 1: x, y = 255, 1
            elif i % 8 == 2: x, y = 128, 255
            elif i % 8 == 3: y = 8
            a.append(x); b.append(y)
        seeds.append(dict(a=a, b=b, rng_final=rng))
        for op in range(25):
            for li, vl in enumerate((0, 1, 2, 3, 512, 1023, 1024)):
                for mode in range(3):
                    for si in range(3 if KINDS[op] == 0 else 1):
                        start = (0, vl//2, vl if vl < CAP else CAP-1)[si]
                        out = [91]*CAP
                        if op == 22:
                            if vl: out[0] = (b[0]+sum(a[i] for i in range(vl) if selected(mode, i))) & 255
                        elif op == 23:
                            packed = [a[i] for i in range(vl) if selected(mode, i)]
                            out[:len(packed)] = packed
                        else:
                            for i in range(start, vl):
                                if not selected(mode, i): continue
                                if op < 19: out[i] = integer(op, a[i], b[i], 8)
                                elif op == 19:
                                    if i >= 2: out[i] = a[i-2]
                                elif op == 20: out[i] = a[i+2] if i+2 < CAP else 0
                                elif op == 21: out[i] = a[b[i]] if b[i] < CAP else 0
                                elif op == 24: out[i] = a[i]
                        raw = bytes([91] + out + [91])
                        indices = []
                        for offset in range(0, 1026, 64):
                            value = int.from_bytes(raw[offset:offset+64], 'little')
                            if value not in lookup:
                                lookup[value] = len(dictionary); dictionary.append(value)
                            indices.append(lookup[value])
                        assert len(indices) == GROUPS
                        rows.append(dict(ordinal=len(rows)+1, seed=seed, op=op, li=li,
                            mode=mode, si=si, vl=vl, start=start, indices=indices))
    assert len(rows) == CALLS and len(dictionary) <= 65536
    masks = [bytes(sum((1 << (i%8)) for i in range(j*8, min(j*8+8, CAP))
        if selected(mode, i)) for j in range(128)) for mode in range(3)]
    assert all(len(m) == 128 for m in masks)
    return seeds, rows, dictionary, masks

def headers(seeds, rows, dictionary, masks):
    table = '#include <stdint.h>\n#define FULL_CALLS 4095u\n'
    table += 'static const uint64_t expected_dictionary[] __attribute__((aligned(64))) = {\n' + ',\n'.join(
        'UINT64_C(0x%016x)' % ((v >> shift) & ((1 << 64)-1)) for v in dictionary for shift in range(0,512,64)) + '\n};\n'
    table += 'static const uint16_t expected_indices[4095][17] = {\n' + ',\n'.join(
        '{'+','.join(map(str, r['indices']))+'}' for r in rows) + '\n};\n'
    table += 'static const uint8_t physical_masks[3][128] = {\n' + ',\n'.join(
        '{'+','.join(map(str, m))+'}' for m in masks) + '\n};\n'
    host = 'struct fixture_row {unsigned seed,op,vl,mode,start;};\n'
    host += 'static const struct fixture_row fixture_rows[4095] = {\n' + ',\n'.join(
        '{'+','.join(str(r[k]) for k in ('seed','op','vl','mode','start'))+'}' for r in rows)+'\n};\n'
    for key in ('a','b'):
        host += f'static const uint8_t fixture_{key}[3][1024] = {{\n' + ',\n'.join(
            '{'+','.join(map(str,s[key]))+'}' for s in seeds)+'\n};\n'
    return table, host

