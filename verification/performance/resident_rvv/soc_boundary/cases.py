"""Small discriminating SoC matrix, not a Cartesian-product coverage claim."""

SCHEMA = 'resident-pv-soc-boundary-v1'
OWN = ('README.md', 'cases.py', 'generate.py', 'main.c', 'pv.S', 'trap.S',
       'build.py', 'check.py', 'test_boundary.py', 'compat.c')
PV_INSN = 0x0485705b
QBS_INSN = 0x00b5045b
VADD_INSN = 0x0300b857
FILL_INSN = 0x00b5605b
RELEASE_INSN = 0x0000505b


def control(dimension, heads, tokens):
    if dimension not in (64, 96, 128) or heads not in (1, 2) or not 1 <= tokens <= 64:
        raise ValueError('Invalid legal PV geometry')
    return tokens-1 | (heads-1) << 6 | {64: 0, 128: 1, 96: 2}[dimension] << 7


def scenarios():
    rows = []
    for d, h, t, rm, tile in ((64, 1, 1, 0, 0), (64, 2, 64, 1, 0),
                              (96, 1, 9, 2, 2), (96, 2, 64, 3, 1),
                              (128, 1, 64, 4, 0), (128, 2, 9, 0, 2)):
        rows.append(dict(name=f'geometry_d{d}_h{h}_t{t}_rm{rm}', dimension=d,
                         heads=h, tokens=t, rm=rm, tile=tile, kind='normal'))
    rows += [dict(name='directed_nv_sticky_dz', dimension=128, heads=2, tokens=1,
                  rm=0, tile=0, kind='nv', initial_flags=8),
             dict(name='directed_tiny_h1_poison', dimension=64, heads=1, tokens=1,
                  rm=0, tile=0, kind='tiny')]
    for kind in ('upper', 'dcode', 'vstart', 'frm', 'no_context', 'context_d', 'context_t'):
        rows.append(dict(name='reject_'+kind+'_then_good', dimension=96, heads=2,
                         tokens=64 if kind == 'context_t' else 9,
                         rm=0, tile=0 if kind == 'context_t' else 2, kind=kind))
    rows.append(dict(name='prepared_mixed_source', dimension=96, heads=2, tokens=9,
                     rm=0, tile=2, kind='mixed'))
    for kind in ('fs_off', 'vs_off', 'rd_align', 'vs2_align', 'alias'):
        rows.append(dict(name='reject_'+kind+'_then_good', dimension=128, heads=2,
                         tokens=9, rm=0, tile=2, kind=kind, input_alias=5))
    for i, row in enumerate(rows):
        row.update(id=i, initial_flags=row.get('initial_flags', 0),
                   rejection=('frontend' if row['kind'] in ('upper', 'dcode', 'vstart', 'frm',
                                                           'fs_off', 'vs_off', 'rd_align', 'vs2_align', 'alias')
                              else 'backend' if row['kind'].startswith(('no_context', 'context_'))
                              else None))
        row['control'] = control(row['dimension'], row['heads'], row['tokens'])
        row['bad_control'] = row['control'] | 512 if row['kind'] == 'upper' else (
            (row['control'] & 127) | 384 if row['kind'] == 'dcode' else row['control'])
        row['vtype_mode'] = {0: 1, 2: 2}.get(i, 0)
        row['bad_mode'] = {'fs_off': 3, 'vs_off': 4, 'rd_align': 5, 'vs2_align': 6, 'alias': 7}.get(row['kind'], 0)
        row['bad_insn'] = {'rd_align': 0x0485715b, 'vs2_align': 0x0445705b,
                           'alias': 0x0485745b}.get(row['kind'], PV_INSN)
        row['context_dimension'] = 128 if row['kind'] == 'context_d' else row['dimension']
        row['context_tokens'] = 9 if row['kind'] == 'context_t' else row['tokens']
        row['context_heads'] = row['heads']
        row['recovery_reloads_context'] = row['kind'] == 'no_context'
    return rows


def attempts(rows):
    result = []
    for row in rows:
        for phase in ((0, 1) if row['rejection'] else (1,)):
            s = dict(row, phase=phase, error=int(phase == 0),
                     instruction=row['bad_insn'] if phase == 0 else PV_INSN)
            if phase and row['rejection']:
                s.update(row.get('recovery', dict(dimension=row['context_dimension'],
                    tokens=row['context_tokens'], heads=row['context_heads'],
                    control=control(row['context_dimension'], row['context_heads'], row['context_tokens']))))
            result.append(s)
    return result


def instruction_flow(rows):
    """Retired context commands are evidence: no hidden reload between bad/good."""
    flow = []
    for row in rows:
        flow.append(FILL_INSN)
        if row['rejection']:
            if row['recovery_reloads_context']:
                flow.append(RELEASE_INSN)
            flow.append(row['bad_insn'])
            if row['recovery_reloads_context']:
                flow.append(FILL_INSN)
        flow.extend((PV_INSN, RELEASE_INSN))
    return flow+[QBS_INSN, VADD_INSN]


def dest_pattern():
    return [(0x13579bdf ^ ((i+1)*0x01030507)) & 0xffffffff for i in range(128)]


def guard_pattern():
    return [(0xfedcba9876543210 ^ ((i+1)*0x0102030405060709)) & ((1 << 64)-1)
            for i in range(32)]


def native_indices(lane, word):
    return [16*word+lane+part for part in (0, 8, 4, 12)]
