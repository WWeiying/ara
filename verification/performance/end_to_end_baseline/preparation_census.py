"""Count actual GGML preparation routes; never interpret QEMU time as cycles."""
from collections import Counter

from audit import require
from check_output_model import check as check_model


def fields(line):
    result = {}
    for word in line.split()[1:]:
        key, sep, value = word.partition('=')
        require(sep and key not in result, 'Malformed preparation trace')
        result[key] = value
    return result


def records(lines):
    mode = None
    step = 0
    groups = []
    cache = None
    sequence = 0
    rows = []
    for line in lines:
        if line.startswith('OUTPUT_MODEL_BEGIN '):
            require(mode is None and not groups and cache is None, 'Nested preparation scope')
            mode = int(fields(line)['enabled']); step = 0; sequence = 0
        elif line.startswith('GGML_RISCV_QBS_M4_CACHE '):
            require(mode in (0, 1) and cache is None, 'Unpaired cache event')
            cache = fields(line)
            require(int(cache['group']) == len(groups) < 8 and
                    cache['event'] in ('hit', 'compute_rvv', 'compute_generic') and
                    cache['fill'] in ('0', '1'), 'Unexpected cache group')
        elif line.startswith('GGML_RISCV_QBS_M4_SELECTED '):
            require(mode in (0, 1), 'Preparation outside model')
            selected = fields(line)
            require(selected['tag'] == '2' and int(selected['k']) > 0, 'Wrong producer')
            if selected['source'] == 'cache':
                require(cache is not None and selected['event'] == cache['event'], 'Cache event mismatch')
                groups.append(dict(route=selected['event'], k=int(selected['k']), epoch=int(cache['epoch']),
                                   fill=int(cache['fill'])))
                cache = None
            else:
                require(selected['source'] == 'direct' and cache is None and
                        selected['path'] in ('rvv', 'generic'), 'Unknown direct preparation')
                groups.append(dict(route='direct_'+selected['path'], k=int(selected['k'])))
        elif line.startswith('GGML_RISCV_QBS_LIFETIME '):
            require(mode in (0, 1) and cache is None, 'Unpaired lifetime event')
            row = fields(line)
            sequence += 1
            require(int(row['seq']) == sequence and row['activation_type'] == 'q8_K', 'Lifetime sequence/type')
            m, k, epoch = (int(row[name]) for name in ('m', 'k', 'graph_epoch'))
            require(len(groups) == m//4 and all(g['k'] == k and g.get('epoch', epoch) == epoch for g in groups),
                    'Missing/extra groups or wrong geometry')
            require(m in (1, 40) and k > 0 and k % 256 == 0 and
                    int(row['bytes']) == m*(k//256)*292, 'Unexpected model geometry')
            duplicate = int(row['reusable'])
            match = int(row['match_seq'])
            require(duplicate in (0, 1) and bool(match) == bool(duplicate), 'Duplicate linkage')
            if match:
                prior = next((r for r in reversed(rows) if r['mode'] == mode and r['seq'] == match), None)
                require(prior is not None and all(prior[name] == row[name] for name in
                        ('source_id', 'digest')) and prior['epoch'] == epoch and prior['m'] == m and prior['k'] == k,
                        'Duplicate has no matching prepared buffer')
            rows.append(dict(mode=mode, kind=step//3, step=step%3, seq=sequence, epoch=epoch,
                             op=row['op'], source=row['source'], source_id=row['source_id'], digest=row['digest'],
                             m=m, n=int(row['n']), k=k, duplicate_prepared_buffer=bool(duplicate),
                             groups=list(groups)))
            groups.clear()
        elif line.startswith('OUTPUT_MODEL_STEP '):
            row = fields(line)
            require(mode in (0, 1) and not groups and cache is None and
                    (int(row['enabled']), int(row['kind']), int(row['step'])) == (mode, step//3, step%3),
                    'Incomplete preparation at model step')
            step += 1
        elif line.startswith('OUTPUT_MODEL_END '):
            require(mode is not None and int(fields(line)['enabled']) == mode and step == 6 and
                    not groups and cache is None, 'Incomplete preparation model')
            mode = None
    require(mode is None and not groups and cache is None and rows, 'Incomplete preparation stream')
    return rows


def summarize(rows):
    totals = Counter()
    by_source = {}
    for row in rows:
        counts = Counter(g['route'] for g in row['groups'])
        counts['prepared_buffers'] = 1
        counts['m4_groups'] = len(row['groups'])
        counts['duplicate_prepared_buffers'] = int(row['duplicate_prepared_buffer'])
        # Equal packed buffers are not proof that all original FP32 bytes match.
        counts['direct_groups_in_duplicate_buffers'] = sum(
            g['route'].startswith('direct_') for g in row['groups']) if row['duplicate_prepared_buffer'] else 0
        counts['direct_groups_ge8'] = sum(
            i >= 8 and g['route'].startswith('direct_') for i, g in enumerate(row['groups']))
        totals.update(counts)
        category = ('prefill' if row['step'] == 0 else 'decode')+':'+row['source'].rsplit('-', 1)[0]
        by_source.setdefault(category, Counter()).update(counts)
    return dict(totals=dict(totals), by_source={k: dict(v) for k, v in sorted(by_source.items())})


def check(text):
    model = check_model(text)
    require(model['prompt_tokens'] == 40, 'Census prompt changed')
    rows = records(text.replace('\r', '').splitlines())
    modes = [summarize([r for r in rows if r['mode'] == mode]) for mode in (0, 1)]
    require(modes[0] == modes[1], 'Attention choice changed preparation routes')
    require(modes[0]['totals']['m4_groups'] > 0 and modes[0]['totals'].get('hit', 0) > 0,
            'No real preparation or cache activity')
    return dict(model=model, per_mode=modes[0], measured_modes=2, rows=rows,
                performance_measured=False, whole_model_hardware_cycles=False,
                limitations=['Counters count actual preparation routes, not hardware time or external traffic',
                             'Duplicate prepared bytes do not establish exact FP32 input equality',
                             'M1 hardware activation-context reuse is separate from this M4 byte-cache census'])
