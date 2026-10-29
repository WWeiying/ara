"""Check paired graph schedules and existing cache counters, not elapsed time."""
from run_census import census_check


def check(text):
    result = census_check(text)
    modes = [[], []]
    mode = None
    current = None
    for line in text.replace('\r', '').splitlines():
        if line.startswith('GRAPH_CYCLES_MODEL_BEGIN '):
            mode = int(line.split('enabled=')[1])
        elif line.startswith('GRAPH_CYCLES_MODEL_END '):
            if current is not None:
                raise ValueError('Incomplete graph schedule')
            mode = None
        elif line.startswith(('GRAPH_SCHEDULE ', 'GRAPH_SCHEDULE_GROUP ', 'GRAPH_CACHE ')):
            if mode not in (0, 1):
                raise ValueError('Schedule outside paired mode')
            fields = {k: int(v) for k, v in (p.split('=') for p in line.split()[1:])}
            if line.startswith('GRAPH_SCHEDULE '):
                if current is not None or set(fields) != {'epoch', 'nodes', 'groups'}:
                    raise ValueError('Invalid schedule header')
                if not 0 < fields['groups'] <= fields['nodes'] <= 16384:
                    raise ValueError('Invalid schedule capacity')
                current = dict(header=fields, groups=[])
            elif line.startswith('GRAPH_SCHEDULE_GROUP '):
                if current is None or set(fields) != {'epoch', 'first', 'last', 'op'}:
                    raise ValueError('Group without schedule')
                previous = current['groups'][-1]['last'] if current['groups'] else -1
                if (fields['epoch'] != current['header']['epoch'] or
                        not previous < fields['first'] <= fields['last'] < current['header']['nodes'] or fields['op'] < 0):
                    raise ValueError('Invalid fused group')
                current['groups'].append(fields)
            else:
                if (current is None or set(fields) != {'epoch'} | {f's{i}' for i in range(14)}
                        or fields['epoch'] != current['header']['epoch']
                        or len(current['groups']) != current['header']['groups']):
                    raise ValueError('Incomplete graph/cache record')
                if any(fields[f's{i}'] < 0 for i in range(14)) or fields['s0'] != fields['s1'] + fields['s2']:
                    raise ValueError('Invalid cache statistics')
                current['cache'] = fields
                modes[mode].append(current)
                current = None
    if current is not None or len(modes[0]) != result['graphs'] or modes[0] != modes[1]:
        raise ValueError('Paired schedules/cache statistics differ')
    previous = None
    for item in modes[0]:
        fields = item['cache']
        if previous is not None and (fields['epoch'] <= previous['epoch'] or
                any(fields[f's{i}'] < previous[f's{i}'] for i in range(12))):
            raise ValueError('Counters or epochs went backwards')
        previous = fields
    if previous is None or previous['s1'] == 0 or previous['s10'] == 0:
        raise ValueError('No real cache/producer activity')
    return dict(result, graph_schedule_verified=True, reuse_counts_verified=True,
                schedule_groups_per_mode=sum(len(g['groups']) for g in modes[0]),
                cache_final=previous)
