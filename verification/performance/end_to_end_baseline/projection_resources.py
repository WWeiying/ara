"""Audit actual RTL issue ports; report service bounds, not predicted speedups."""
import re

from audit import require


FIELDS = set('case dot pairs groups corrections requests main cast half scale min_scale '
             'accum_dot accum_min cast_dot cast_aux main_blocked cast_blocked '
             'request_blocked fp_occupied busy'.split())


def geometry(text):
    lines = text.splitlines()
    header = lines[0].split()
    require(len(header) == 2 and header[0] == 'QBSCMD1', 'Command header')
    count = int(header[1])
    result = {}
    current = None
    for line in lines[1:]:
        words = line.split()
        if not words:
            continue
        if words[0] == 'CMD':
            require(current is None and len(words) == 9, 'Command boundary')
            row = list(map(int, words[1:8]))
            index, profile, wl, al, m, n, kb = row
            require(index == len(result) and profile in range(1, 10) and
                    1 <= m <= 8 and 1 <= n <= (16 if m > 4 else 32) and kb > 0,
                    'Command geometry')
            current = dict(case=index, profile=profile, weight_layout=wl,
                           activation_layout=al, m=m, n=n, k_blocks=kb)
        elif words[0] == 'C':
            require(current is not None and len(words) == 9 and 'counters' not in current,
                    'Command counters')
            current['counters'] = list(map(int, words[1:]))
        elif words[0] == 'END':
            require(current is not None and 'counters' in current, 'Incomplete command')
            result[current['case']] = current
            current = None
    require(current is None and len(result) == count and count > 0, 'Command count')
    return result


def service_bound(row, dot_factor=1, correction_lanes=2):
    """Infinite-overlap lower bound with ideal II=1 ports; not a latency model.

    Faster dot is hypothetical. SRAM, dependency, burst, setup and drain costs
    are deliberately absent, so even a balanced bound does not prove feasibility.
    """
    require(dot_factor in (1, 2) and correction_lanes in (2, 4), 'Unknown scenario')
    terms = dict(dot=(row['dot'] + dot_factor - 1) // dot_factor,
                 correction=(row['corrections'] + correction_lanes - 1) // correction_lanes,
                 fp_arithmetic=row['main'], fp_cast=row['cast'], fp_half_scale=row['half'],
                 result_issue=row['requests'])
    lower = max(terms.values())
    return dict(terms=terms, lower_bound_cycles=lower,
                limiting_resources=[k for k, v in terms.items() if v == lower])


def check(text, vector_text):
    expected = geometry(vector_text)
    require(not re.search(r'Fatal:|Error:|UVM_ERROR|UVM_FATAL', text), 'Simulator error')
    passes = re.findall(r'^QBS command case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) '
                        r'Kb=(\d+) layouts=(\d+)/(\d+)$', text, re.M)
    require(len(passes) == len(expected), 'Missing command checks')
    seen = set()
    for words in passes:
        index, profile, m, n, kb, wl, al = map(int, words)
        require(index in expected and index not in seen, 'Duplicate/unexpected command')
        e = expected[index]
        require((profile, m, n, kb, wl, al) == tuple(e[k] for k in
                ('profile', 'm', 'n', 'k_blocks', 'weight_layout', 'activation_layout')),
                'Wrong executed geometry')
        seen.add(index)
    rows = {}
    for line in text.splitlines():
        if not line.startswith('QBS_RESOURCE '):
            continue
        row = {}
        for word in line.split()[1:]:
            key, sep, value = word.partition('=')
            require(sep and value.isdecimal() and key not in row, 'Malformed resource record')
            row[key] = int(value)
        require(set(row) == FIELDS, 'Resource schema')
        index = row['case']
        require(index in expected and index not in rows, 'Unexpected/duplicate resource case')
        counters = expected[index]['counters']
        require(row['dot'] == counters[5] and row['pairs'] == counters[3] and
                row['main'] + row['cast'] + row['half'] == counters[6] and
                row['requests'] == counters[7] and row['groups'] == row['corrections'] > 0,
                'Resource conservation')
        require(row['main'] == sum(row[k] for k in ('scale', 'min_scale', 'accum_dot', 'accum_min'))
                and row['cast'] == row['cast_dot'] + row['cast_aux'], 'FP port accounting')
        require(row['busy'] >= service_bound(row)['lower_bound_cycles'] and
                row['fp_occupied'] <= row['busy'], 'Impossible activity counts')
        rows[index] = dict(**row, geometry=expected[index],
                          current_service_bound=service_bound(row),
                          hypothetical_2x_dot_only=service_bound(row, 2, 2),
                          hypothetical_2x_dot_4_correction=service_bound(row, 2, 4))
    require(set(rows) == set(expected), 'Missing resource samples')
    require(text.splitlines().count(f'QBS command engine PASS: {len(expected)} functional cases') == 1
            and text.splitlines().count('QBS command fault discard PASS') == 1,
            'Missing terminal/fault verdict')
    faults = re.findall(r'^QBS pipeline fault stage ([0-3]) PASS drain_cycles=(\d+)$', text, re.M)
    require(len(faults) == 4 and {int(x[0]) for x in faults} == set(range(4)), 'Fault stage coverage')
    return list(rows.values())
