"""Bounded architectural QK matrix, not a Cartesian-product coverage claim."""
SCHEMA = 'resident-qk-boundary-v1'
QK = 0x0605705b
PV = 0x0485705b
FILL = 0x00b5605b
RELEASE = 0x0000505b
QBS = 0x00b5045b
VADD = 0x0300b857
WORDS = {'qk_fault_pc': QK, 'qk_bad_rd_pc': 0x0605715b,
         'qk_bad_rs2_pc': 0x0615705b, 'qk_rd28_pc': 0x06057e5b}


def control(d, h, t, base):
    if d not in (64, 96, 128) or h not in (1, 2) or not 1 <= t <= 64 or not 0 <= base <= 7:
        raise ValueError('Invalid QK geometry')
    return (t - 1) | ((h - 1) << 6) | ({64: 0, 128: 1, 96: 2}[d] << 7) | (base << 9)


def scenarios():
    shapes = ((1, 64, 1, 7, 0), (2, 96, 2, 6, 1), (3, 128, 1, 5, 2),
              (9, 64, 2, 3, 3), (17, 96, 2, 5, 4), (64, 128, 2, 6, 0))
    result = [dict(tokens=t, dimension=d, heads=h, query_base=b, rm=rm, kind='finite')
              for t, d, h, b, rm in shapes]
    for kind in ('invalid', 'qnan', 'snan', 'poison_subnormal', 'rounding'):
        result.append(dict(tokens=1 if kind == 'invalid' else 17 if kind == 'poison_subnormal' else 3,
                           dimension=128 if kind in ('poison_subnormal', 'rounding') else 64,
                           heads=1 if kind in ('invalid', 'poison_subnormal') else 2,
                           query_base=7 if kind in ('invalid', 'poison_subnormal') else 6,
                           rm=4 if kind == 'rounding' else 0, kind=kind))
    frontend = ('fs_off', 'vs_off', 'vstart', 'frm', 'rs2', 'rd_align', 'upper', 'dcode')
    for kind in (*frontend, 'no_context', 'context_d', 'context_t', 'query_bounds'):
        result.append(dict(tokens=9, dimension=128, heads=2, query_base=6, rm=0, kind=kind))
    for i, row in enumerate(result):
        kind = row['kind']
        row.update(id=i, initial_flags=8 if kind in ('invalid', 'snan') else 0,
                   rejection='frontend' if kind in frontend else 'backend' if i >= 19 else None,
                   mode={0: 1, 1: 2, 5: 7}.get(i, 0),
                   bad_mode={'fs_off': 3, 'vs_off': 4, 'rd_align': 5, 'rs2': 6}.get(kind, 0),
                   context_dimension=64 if kind == 'context_d' else row['dimension'],
                   context_tokens=8 if kind == 'context_t' else row['tokens'],
                   context_queries=7 if kind == 'query_bounds' else 8)
        row['control'] = control(row['dimension'], row['heads'], row['tokens'], row['query_base'])
        row['bad_control'] = (row['control'] | 4096 if kind == 'upper' else
                              (row['control'] & ~384) | 384 if kind == 'dcode' else
                              row['control'])
        row['bad_instruction'] = WORDS['qk_bad_rd_pc'] if kind == 'rd_align' else (
            WORDS['qk_bad_rs2_pc'] if kind == 'rs2' else QK)
        row['instruction'] = WORDS['qk_rd28_pc'] if row['mode'] == 7 else QK
    assert len(result) == 23 and sum(bool(r['rejection']) for r in result) == 12
    return result


def attempts(rows):
    result = []
    for row in rows:
        if row['rejection']:
            result.append(dict(row, phase=0, error=1, instruction=row['bad_instruction'],
                               issue_control=row['bad_control'], query_base=(row['bad_control'] >> 9) & 7,
                               mode=row['bad_mode']))
            result.append(dict(row, **row['recovery'], phase=1, error=0, instruction=QK, mode=0))
        else:
            result.append(dict(row, phase=1, error=0))
    return result


def destination():
    return [(0x13579bdf ^ ((i + 1) * 0x01030507)) & 0xffffffff for i in range(384)]


def geometry(spec):
    local = [len(range(lane, spec['tokens'], 4)) for lane in range(4)]
    words = [((n + 1) // 2) * spec['heads'] for n in local]
    return dict(active=sum((n > 0) << lane for lane, n in enumerate(local)),
                seed_words=sum(words), coefficients=spec['dimension'] * sum(n > 0 for n in local),
                value_words=spec['dimension'] * sum((n + 3) // 4 for n in local),
                result_words=sum(words), final_acks=sum(words), source_words=0,
                query_reads=spec['dimension'] // 16 * spec['heads'], columns=spec['dimension'] // 4)


def writes(spec):
    """Natural EW32 order; no reuse of reader/lane packing helpers."""
    values = spec['expected']
    base = 28 if spec.get('instruction') == WORDS['qk_rd28_pc'] else 0
    result = {}
    for h in range(spec['heads']):
        for lane in range(4):
            for w in range((len(range(lane, spec['tokens'], 4)) + 1) // 2):
                lo, hi = 8 * w + lane, 8 * w + lane + 4
                result[lane, base * 4 + h * 8 + w] = (
                    values[h * spec['tokens'] + lo] |
                    ((values[h * spec['tokens'] + hi] << 32) if hi < spec['tokens'] else 0),
                    255 if hi < spec['tokens'] else 15)
    return result
