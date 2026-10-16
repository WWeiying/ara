"""Match original slide discrepancy tuples; failure alone is not equivalence."""
import re

KEYS={'op','seed','scalar','vl','mask','element','expected','actual'}


def details(output):
    found=[]
    for line in output.splitlines():
        if not line.startswith('RVV_PERMUTE_DETAIL '):
            continue
        pairs=re.findall(r'(\w+)=(\d+)',line)
        row={k:int(v) for k,v in pairs}
        if len(row)!=len(pairs) or not KEYS<=row.keys():
            raise ValueError('Incomplete or duplicate slide discrepancy fields')
        found.append(row)
    return found


def compare(original, small, measured_detail):
    selected=details(measured_detail)
    if len(selected)!=1:
        raise ValueError('Expected one measured original discrepancy')
    target=selected[0]
    keys=KEYS | ({'vstart'} if 'vstart' in target else set())
    def contains(result):
        return any(all(row.get(k)==target[k] for k in keys) for row in details(result['output']))
    confirmed=(original.get('status')=='failed' and original.get('exit_code')==1 and
               small.get('status')=='failed' and small.get('exit_code')==1 and
               contains(original) and contains(small))
    return dict(confirmed=confirmed,tuple=target,
                scope='Recorded trigger and wrong element/value; not internal cause or all output bytes')
