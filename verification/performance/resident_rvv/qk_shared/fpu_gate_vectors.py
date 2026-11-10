"""Independent ordered SoftFloat vectors for one real shared PV/QK lane."""
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'ordered_reference.py'
spec = importlib.util.spec_from_file_location('ordered_qk_gate', REF)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def pack(values, width):
    return sum(x << (i * width) for i, x in enumerate(values))


def reencode(sf, bits):
    if bits & 0x7c00 == 0x7c00 and bits & 0x3ff:
        return (bits & 0x8000) << 16 | 0x7f800000 | (bits & 0x3ff) << 13
    return sf.evaluate('cast', 16, 32, 0, bits)[0]


def qk_case(ref, tokens, heads, dim, lane, rm, kind='finite', action=0):
    q = [[0x3c00 + ((h * 7 + d * 3) % 24) for d in range(dim)] for h in range(heads)]
    k = [[0x3800 + ((t * 11 + d * 5) % 31) for d in range(dim)] for t in range(tokens)]
    if kind in ('masked', 'qnan', 'snan', 'invalid', 'subnormal', 'rounding'):
        q = [[0x3c00] * dim for _ in range(heads)]
        k = [[0x3c00] * dim for _ in range(tokens)]
    if kind == 'qnan':
        q[heads - 1][1] = 0x7e01
    elif kind == 'snan':
        q[heads - 1][1] = 0xfc01
    elif kind == 'invalid':
        q[0][0], k[lane][0] = 0, 0x7c00
    elif kind == 'subnormal':
        q = [[1 if d % 2 else 0x8001 for d in range(dim)] for _ in range(heads)]
        k = [[0x8000 if d % 5 == 0 else 1 for d in range(dim)] for _ in range(tokens)]
    elif kind == 'rounding':
        q[0] = [0x7bff, 0x3c00, 0xfbff] + [0] * (dim - 3)
        k[0] = [0x7bff, 0x3c00, 0x7bff] + [0x3c00] * (dim - 3)
    local = list(range(lane, tokens, 4))
    elements, words = len(local), (len(local) + 1) // 2
    case = dict(mode=1, elements=elements, heads=heads, iterations=dim, rm=rm,
                action=action, name=f'qk_{tokens}_{heads}_{dim}_l{lane}_{kind}_rm{rm}',
                seeds=[], packets=[], operations=[], writes=[], flags=0)
    if not elements:
        return case
    expected = ref.qk(q, [k[t] for t in local], rm)
    sums = [[0] * elements for _ in range(heads)]
    case['seeds'] = [(8 * h + w, 0) for h in range(heads) for w in range(words)]
    flags = 0
    for d in range(dim):
        # An unused head and every inactive raw halfword deliberately contain sNaN.
        case['packets'].append((0, q[0][d] | (q[1][d] if heads == 2 else 0x7c01) << 16))
        for p in range((elements + 3) // 4):
            indices = [16 * p + lane + x for x in (0, 8, 4, 12)]
            case['packets'].append((1, pack([k[t][d] if t < tokens else 0x7c01 for t in indices], 16)))
        for w in range(words):
            mask = 1 if 2 * w + 1 == elements else 3
            for h in range(heads):
                qa, qf = ref.sf.evaluate('cast', 16, 32, rm, q[h][d])
                a = pack([reencode(ref.sf, q[h][d])] * 2, 32)
                keys, before, result, ex = [], [], [], 0
                for e in range(2):
                    i = 2 * w + e
                    raw = k[local[i]][d] if i < elements else 0x7c01
                    keys.append(reencode(ref.sf, raw))
                    before.append(sums[h][i] if i < elements else 0)
                    if i < elements:
                        kb, kf = ref.sf.evaluate('cast', 16, 32, rm, raw)
                        value, ff = ref.sf.evaluate('fma', 32, 32, rm, qa, kb, sums[h][i])
                        sums[h][i] = value
                        ex |= qf | kf | ff
                        result.append(value)
                    else:
                        result.append(0)
                case['operations'].append((8 * h + w, mask, a, pack(keys, 32),
                                           pack(before, 32), pack(result, 32), ex))
                flags |= ex
    if sums != expected['output'] or flags != expected['fflags']:
        raise ValueError('Per-word stream diverged from independent ordered QK reference')
    case['flags'] = flags
    for h in range(heads):
        for w in range(words):
            values = sums[h][2 * w:2 * w + 2]
            case['writes'].append((8 * h + w, 0x0f if len(values) == 1 else 0xff, pack(values, 32)))
    return case


def pv_case(ref, kind):
    heads, elements, tokens, rm = (2, 16, 9, 0) if kind == 'finite' else (1, 16, 1, 3)
    probability = [[0x3f800000] * tokens for _ in range(heads)]
    seed = [[0x3400 + e + 3 * h for e in range(elements)] for h in range(heads)]
    values = [[0x3800 + (t + e) % 16 for e in range(elements)] for t in range(tokens)]
    if kind == 'invalid':
        probability, seed, values = [[0]], [[0] * elements], [[0x7c00] * elements]
    elif kind == 'underflow':
        probability, seed, values = [[0x3f000000]], [[0] * elements], [[1] * elements]
    gold = ref.pv(probability, [0x3f800000] * heads, seed, values, rm)
    if gold['prepared_fflags'] != 0:
        raise ValueError('Prepared flags must not mask newly raised PV flags')
    sums = [row[:] for row in gold['prepared_seed']]
    case = dict(mode=0, elements=elements, heads=heads, iterations=tokens, rm=rm, action=0,
                name='pv_' + kind, seeds=[], packets=[], operations=[], writes=[], flags=0)
    words = elements // 4
    case['seeds'] = [(8 * h + w, pack(sums[h][4 * w:4 * w + 4], 16))
                     for h in range(heads) for w in range(words)]
    for t in range(tokens):
        coeff = [gold['coefficient'][h][t] for h in range(heads)]
        case['packets'].append((0, coeff[0] | (coeff[1] if heads == 2 else 0x7c01) << 16))
        case['packets'] += [(1, pack(values[t][4 * w:4 * w + 4], 16)) for w in range(words)]
        for w in range(words):
            for h in range(heads):
                before = sums[h][4 * w:4 * w + 4]
                result, flags = [], 0
                for e in range(4):
                    value, ff = ref.sf.evaluate('fma', 16, 16, rm, coeff[h], values[t][4 * w + e], before[e])
                    result.append(value)
                    flags |= ff
                sums[h][4 * w:4 * w + 4] = result
                case['operations'].append((8 * h + w, 15, pack([coeff[h]] * 4, 16),
                    pack(values[t][4 * w:4 * w + 4], 16), pack(before, 16), pack(result, 16), flags))
                case['flags'] |= flags
    if sums != gold['output'] or case['flags'] != gold['fflags']:
        raise ValueError('PV private FMA flags/order differ from independent reference')
    case['writes'] = [(8 * h + w, 255, pack(sums[h][4 * w:4 * w + 4], 16))
                      for h in range(heads) for w in range(words)]
    return case


def cases(library):
    ref = reference.OrderedReference(library)
    result = [pv_case(ref, 'finite')]
    shapes = [(1, 1, 64, 1, 0), (1, 1, 64, 0, 0), (2, 2, 96, 0, 1),
              (2, 2, 96, 2, 1), (3, 1, 128, 2, 2), (9, 2, 64, 0, 3),
              (17, 2, 96, 0, 4), (17, 2, 96, 1, 0),
              (63, 1, 128, 3, 1), (64, 2, 128, 0, 0)]
    result += [qk_case(ref, *s) for s in shapes]
    result += [qk_case(ref, 9, 1, 64, 0, 0, 'masked'),
               qk_case(ref, 9, 2, 64, 0, 0, 'qnan'),
               qk_case(ref, 17, 2, 64, 0, 0, 'snan'),
               qk_case(ref, 1, 1, 64, 0, 0, 'invalid'),
               qk_case(ref, 9, 1, 64, 0, 2, 'subnormal')]
    result += [qk_case(ref, 1, 1, 64, 0, rm, 'rounding') for rm in range(5)]
    result += [qk_case(ref, 17, 2, 64, 0, 0, action=1),
               qk_case(ref, 9, 2, 64, 0, 0, action=2),
               qk_case(ref, 9, 2, 64, 0, 0), pv_case(ref, 'invalid'), pv_case(ref, 'underflow')]
    return result, ref.identity()


def generate(directory, library):
    rows, identity = cases(library)
    directory = Path(directory)
    with (directory / 'vectors.txt').open('x') as f:
        f.write('QKFPU1\n')
        for i, c in enumerate(rows):
            numbers = (i, c['mode'], c['elements'], c['heads'], c['iterations'], c['rm'], c['action'],
                       len(c['seeds']), len(c['packets']), len(c['operations']), len(c['writes']), c['flags'])
            f.write('C ' + ' '.join(map(str, numbers)) + '\n')
            for slot, value in c['seeds']:
                f.write(f'S {slot} {value:016x}\n')
            for kind, value in c['packets']:
                f.write(f'P {kind} {value:016x}\n')
            for slot, mask, a, b, addend, value, flags in c['operations']:
                f.write(f'F {slot} {mask:x} {a:016x} {b:016x} {addend:016x} {value:016x} {flags}\n')
            for slot, be, value in c['writes']:
                f.write(f'W {slot} {be:02x} {value:016x}\n')
            f.write('E\n')
        f.write('END\n')
    summary = dict(cases=[{k: v for k, v in c.items() if k not in ('seeds', 'packets', 'operations', 'writes')}
                          | dict(seeds=len(c['seeds']), packets=len(c['packets']),
                                 issued=len(c['operations']), writes=len(c['writes'])) for c in rows],
                   oracle_identity=identity, scope='One controller and real VMFPU; no group/ABI/SoC acceptance')
    (directory / 'expected.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('SOFTFLOAT_VECTORS cases=' + str(len(rows)), flush=True)


if __name__ == '__main__':
    generate(Path(sys.argv[1]), Path(sys.argv[2]))
