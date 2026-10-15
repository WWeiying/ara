"""Independent byte oracle for the natural seed0/op0 first482 calls."""
CAP, COUNT = 512, 482
MASK64 = (1 << 64) - 1


def fnv(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & MASK64
    return f'{value:016x}'


def generate():
    rng, a, b = 0x937ad68de41c725f, [], []
    for i in range(CAP):
        rng ^= (rng << 13) & MASK64
        rng ^= rng >> 7
        rng ^= (rng << 17) & MASK64
        x, y = rng & 255, (rng >> 19) & 255
        if i % 8 == 0:
            x = y = 0
        elif i % 8 == 1:
            x, y = 255, 1
        elif i % 8 == 2:
            x, y = 128, 255
        elif i % 8 == 3:
            y = 8
        a.append(x);b.append(y)
    b[0] = 0
    patterns = [[0 if p == 0 else 255 if p == 1 else 128 if p == 2 else
                 (170 if i & 1 else 85) if p == 3 else
                 (0x937ad68de41c725f + 0x9e3779b97f4a7c15 * i) & 255
                 for i in range(CAP)] for p in range(5)]
    masks = []
    for mode in range(4):
        mask = bytearray(128)
        for i in range(CAP):
            if mode == 0 or (mode == 1 and i & 1) or (mode == 2 and i % 7 == 2):
                mask[i // 8] |= 1 << (i % 8)
        masks.append(list(mask))
    rows = []
    for vl in (0, 1, 2, 3, 256, 511, 512):
        for accumulator in range(5):
            for mode in range(4):
                for start in (1, vl // 2, vl, 511):
                    old, mask = patterns[accumulator], masks[mode]
                    result = list(old)
                    for i in range(start, vl):
                        if (mask[i // 8] >> (i % 8)) & 1:
                            result[i] = (old[i] + a[i] * b[i]) & 255
                    rows.append(dict(trial=len(rows),seed=0,op=0,vl=vl,accumulator=accumulator,
                        mode=mode,vstart=start,rm=0,old=list(old),output=result,
                        input_fnv64=fnv(bytes(a+b+mask+[91]+old+[91])),
                        output_fnv64=fnv(bytes([91]+result+[91]))))
                    if len(rows) == COUNT:
                        return dict(capacity=CAP,a=a,b=b,patterns=patterns,masks=masks,rows=rows)
    raise ValueError('Missing original prefix boundary')


def words(data):
    raw = bytes(data)
    raw += b'\0' * ((-len(raw)) % 8)
    return [int.from_bytes(raw[i:i+8], 'little') for i in range(0,len(raw),8)]


def c_tables(gold):
    lines = ['/* Generated independent byte oracle; not a vector implementation. */',
             '#if SEW != 8 || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__',
             '#error This table is only for original e8/m4 little-endian prefix482', '#endif',
             'typedef uint64_t packed64 __attribute__((may_alias));',
             'struct prefix_shape { uint16_t vl, start; uint8_t accumulator, mode; };',
             'static const struct prefix_shape prefix_shapes[482] = {']
    lines += ['{%d,%d,%d,%d},' % (r['vl'],r['vstart'],r['accumulator'],r['mode']) for r in gold['rows']]
    lines.append('};')
    for name, rows in (
        ('prefix_inputs', [words(gold['a']),words(gold['b'])]),
        ('prefix_masks', [words(m) for m in gold['masks']]),
        ('prefix_initial', [words([91]+p+[91]) for p in gold['patterns']]),
        ('prefix_expected', [words([91]+r['output']+[91]) for r in gold['rows']])):
        lines.append(f'static const uint64_t {name}[{len(rows)}][{len(rows[0])}] = {{')
        lines += ['{'+','.join(f'UINT64_C(0x{v:016x})' for v in row)+'},' for row in rows]
        lines.append('};')
    return '\n'.join(lines)+'\n'
