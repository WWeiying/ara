"""Independent accounting for the optional, format-qualified matrix dot path."""
import re

from audit import require
from projection_resources import FIELDS, geometry, service_bound


BLOCK_ELEMENTS = {1:256,2:256,3:32,4:256,5:256,6:32,7:256,8:32,9:32}


def counts(shape, wide):
    block = BLOCK_ELEMENTS[shape['profile']]
    m, n, kb = (shape[k] for k in ('m','n','k_blocks'))
    waves = [m] if m <= 4 else [4,m-4]
    cycles = 0
    for wave in waves:
        step = 8 if wave == 1 else 4 if wave == 2 else 2
        if wide and block == 256 and wave >= 3:
            step = 4
        cycles += block // step
    return dict(dot=kb*((n+3)//4)*cycles, capacity=kb*n*cycles*(16 if wide else 8))


def candidate_vectors(text):
    shapes = geometry(text)
    lines = []; current = None
    for line in text.splitlines():
        words = line.split()
        if words and words[0] == 'CMD': current = int(words[1])
        elif words and words[0] == 'C':
            require(current is not None, 'Missing vector owner')
            shape = shapes[current]; old = counts(shape,False)
            require((shape['counters'][4],shape['counters'][5]) == (old['capacity'],old['dot']),
                    'Baseline counter model differs from independent C oracle')
            new = counts(shape,True)
            words[5] = str(new['capacity']); words[6] = str(new['dot'])
            line = ' '.join(words)
        elif words and words[0] == 'END': current = None
        lines.append(line)
    return '\n'.join(lines)+'\n'


def check_mode(text, vector, wide):
    shapes = geometry(vector)
    require(not re.search(r'Fatal:|Error:|UVM_ERROR|UVM_FATAL',text),'Simulator failure')
    passes = re.findall(r'^QBS command case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) '
                        r'Kb=(\d+) layouts=(\d+)/(\d+)$',text,re.M)
    expect = [(i,*[s[k] for k in ('profile','m','n','k_blocks','weight_layout','activation_layout')])
              for i,s in shapes.items()]
    require([tuple(map(int,p)) for p in passes] == expect,'Missing/wrong numerical command verdict')
    rows = []
    for line in text.splitlines():
        if not line.startswith('QBS_RESOURCE '): continue
        row = {}
        for word in line.split()[1:]:
            k,sep,v = word.partition('=')
            require(sep and v.isdecimal() and k not in row,'Resource syntax')
            row[k] = int(v)
        require(set(row) == FIELDS and row['case'] == len(rows) and len(rows) < len(shapes),
                'Resource schema/order')
        shape = shapes[row['case']]; c = shape['counters']; theory = counts(shape,wide)
        require(row['dot'] == c[5] == theory['dot'] and c[4] == theory['capacity'] and
                row['pairs'] == c[3] and row['main']+row['cast']+row['half'] == c[6] and
                row['requests'] == c[7] and row['groups'] == row['corrections'] > 0,
                'Command resource conservation')
        require(row['main'] == sum(row[k] for k in ('scale','min_scale','accum_dot','accum_min'))
                and row['cast'] == row['cast_dot']+row['cast_aux'],'FP port conservation')
        require(row['busy'] >= service_bound(row,1,4 if wide else 2)['lower_bound_cycles'] and
                row['fp_occupied'] <= row['busy'],'Impossible activity counts')
        rows.append(row)
    require(len(rows) == len(shapes),'Incomplete resource observations')
    require(text.splitlines().count(f'QBS command engine PASS: {len(shapes)} functional cases') == 1 and
            text.splitlines().count('QBS command fault discard PASS') == 1,'Missing terminal/fault verdict')
    faults = re.findall(r'^QBS pipeline fault stage ([0-3]) PASS drain_cycles=(\d+)$',text,re.M)
    require(len(faults) == 4 and {int(x[0]) for x in faults} == set(range(4)), 'Incomplete pipeline abort checks')
    return rows


def pair(base_text, wide_text, base_vector, wide_vector):
    require(candidate_vectors(base_vector) == wide_vector,'Candidate altered payload or golden results')
    baseline = check_mode(base_text,base_vector,False)
    candidate = check_mode(wide_text,wide_vector,True)
    invariant = ('case','pairs','groups','corrections','requests','main','cast','half','scale',
                 'min_scale','accum_dot','accum_min','cast_dot','cast_aux')
    result = []
    for b,c,s in zip(baseline,candidate,geometry(base_vector).values()):
        require(all(b[k] == c[k] for k in invariant),'Candidate changed work/FP sequence counts')
        result.append(dict(shape=s,baseline=b,candidate=c,
                           compute_bench_ratio=b['busy']/c['busy']))
    return result
