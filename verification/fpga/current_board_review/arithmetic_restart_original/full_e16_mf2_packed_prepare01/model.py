"""Full source order; exact68-byte results, flat ROM, no call deduplication."""
import importlib.util
from pathlib import Path

CAP = 32
CALLS = 4095
KINDS = [0]*19 + [1, 1, 1, 2, 3, 0]
spec = importlib.util.spec_from_file_location('accepted_integer_model',
    Path(__file__).resolve().parent.parent/'full_e16_mf4_prepare01/model.py')
integer_model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integer_model)
integer, selected = integer_model.integer, integer_model.selected


def generate():
    seeds, rows = [], []
    for seed in range(3):
        rng = 0x937ad68de41c725f ^ seed
        a, b = [], []
        for i in range(CAP):
            rng ^= (rng << 13) & ((1 << 64)-1)
            rng ^= rng >> 7
            rng ^= (rng << 17) & ((1 << 64)-1)
            x, y = rng & 65535, (rng >> 19) & 65535
            if i % 8 == 0: x = y = 0
            elif i % 8 == 1: x, y = 65535, 1
            elif i % 8 == 2: x, y = 32768, 65535
            elif i % 8 == 3: y = 16
            a.append(x); b.append(y)
        seeds.append(dict(a=a, b=b, rng_final=rng))
        for op in range(25):
            for li, vl in enumerate((0, 1, 2, 3, CAP//2, CAP-1, CAP)):
                for mode in range(3):
                    for si in range(3 if KINDS[op] == 0 else 1):
                        start = (0, vl//2, vl if vl < CAP else CAP-1)[si]
                        out = [91]*CAP
                        if op == 22:
                            if vl: out[0] = (b[0]+sum(a[i] for i in range(vl) if selected(mode, i))) & 65535
                        elif op == 23:
                            packed = [a[i] for i in range(vl) if selected(mode, i)]
                            out[:len(packed)] = packed
                        else:
                            for i in range(start, vl):
                                if not selected(mode, i): continue
                                if op < 19: out[i] = integer(op, a[i], b[i], 16)
                                elif op == 19:
                                    if i >= 2: out[i] = a[i-2]
                                elif op == 20: out[i] = a[i+2] if i+2 < CAP else 0
                                elif op == 21: out[i] = a[b[i]] if b[i] < CAP else 0
                                elif op == 24: out[i] = a[i]
                        raw = b''.join(w.to_bytes(2,'little') for w in [91]+out+[91])
                        if op == 21 and mode == 0 and vl == CAP:
                            assert b[2] == 65535 and out[2] == 0
                        if op == 20 and mode == 0 and vl == CAP:
                            assert out[-2:] == [0, 0]
                        words = [int.from_bytes(raw[i:i+8], 'little') for i in range(0, len(raw), 8)]
                        assert len(raw) == 68 and len(words) == 9 and words[-1] < (1<<32)
                        rows.append(dict(ordinal=len(rows)+1, seed=seed, op=op, li=li,
                            mode=mode, si=si, vl=vl, start=start, words=words))
    masks = [bytes(sum((1 << (i%8)) for i in range(j*8, min(j*8+8, CAP))
        if selected(mode, i)) for j in range(128)) for mode in range(3)]
    assert len(rows) == CALLS == 3*7*3*(20*3+5)
    assert all(len(m) == 128 and m[4:] == bytes(124) for m in masks)
    return seeds, rows, masks


def headers(seeds, rows, masks):
    table = '#include <stdint.h>\n#define FULL_CALLS 4095u\n'
    table += 'static const uint64_t expected_words[4095][9] __attribute__((aligned(8))) = {\n' + ',\n'.join(
        '{'+','.join('UINT64_C(0x%016x)' % w for w in r['words'])+'}' for r in rows)+'\n};\n'
    table += 'static const uint8_t physical_masks[3][128] = {\n' + ',\n'.join(
        '{'+','.join(map(str, m))+'}' for m in masks)+'\n};\n'
    host = 'struct fixture_row {unsigned seed,op,vl,mode,start;};\n'
    host += 'static const struct fixture_row fixture_rows[4095] = {\n' + ',\n'.join(
        '{'+','.join(str(r[k]) for k in ('seed','op','vl','mode','start'))+'}' for r in rows)+'\n};\n'
    for key in ('a','b'):
        host += f'static const uint16_t fixture_{key}[3][32] = {{\n' + ',\n'.join(
            '{'+','.join(map(str,s[key]))+'}' for s in seeds)+'\n};\n'
    return table, host
