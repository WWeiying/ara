"""Validate the entire three-consumer preparation experiment before timing it."""
import re


def check_log(text, golden):
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    require(len(golden) == 7008, 'Wrong golden size')
    require(not re.search(r'UVM_(?:ERROR|FATAL)\s+(?!:\s*0\b)|CACHE_COST_FAIL|Fatal:', text),
            'Simulation error')
    rows = []
    signature = 14695981039346656037
    for byte in golden * 3:
        signature = ((signature ^ byte) * 1099511628211) & ((1 << 64) - 1)
    fields = ('id reuse total first second third producers hits misses stores '
              'compare_bytes copied_bytes fcsr vcsr errors signature').split()
    for line in text.splitlines():
        if not line.startswith('CACHE_COST_TRIAL '):
            continue
        tokens = line.split()[1:]
        require(len(tokens) == len(fields), 'Wrong field count')
        pairs = [token.split('=', 1) for token in tokens]
        require([p[0] for p in pairs] == fields, 'Wrong field order')
        row = {k: int(v, 16 if k == 'signature' else 10) for k, v in pairs}
        rows.append(row)
    require(len(rows) == 4, 'Missing or duplicate trials')
    require(text.count('CACHE_COST_RESULT trials=4 errors=0') == 1, 'No unique completion')
    for index, row in enumerate(rows):
        reuse = int(index in (1, 2))
        expected = dict(id=index, reuse=reuse, producers=1 if reuse else 3,
                        hits=2*reuse, misses=reuse, stores=reuse,
                        compare_bytes=49152*reuse, copied_bytes=45600*reuse,
                        fcsr=17, vcsr=5, errors=0, signature=signature)
        require(all(row[k] == v for k, v in expected.items()), 'Data/state/cache mismatch')
        require(all(row[k] > 0 for k in ('total', 'first', 'second', 'third')),
                'Invalid cycles')
        require(row['total'] >= sum(row[k] for k in ('first', 'second', 'third')),
                'Invalid phase accounting')
    direct = sum(rows[i]['total'] for i in (0, 3))/2
    cached = sum(rows[i]['total'] for i in (1, 2))/2
    return dict(state='PASS', trials=rows, direct_mean=direct, cache_mean=cached,
                speedup=direct/cached, cycle_reduction=1-cached/direct,
                whole_model=False, matrix_execution=False)
