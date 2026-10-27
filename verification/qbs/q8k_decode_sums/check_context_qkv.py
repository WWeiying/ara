"""Strict ABBA acceptance for the captured mixed-profile Q/V/K pair."""
import re


def check(text,golden=None):
    lines=[s.strip() for s in text.splitlines() if s.startswith('CONTEXT_QKV')]
    if len(lines)!=5 or lines[-1]!='CONTEXT_QKV_RESULT errors=0 trials=4 k=1536 outputs=2048 commands=256':
        raise ValueError('Missing complete Q/V/K acceptance')
    rows=[]
    for i,line in enumerate(lines[:-1]):
        m=re.fullmatch(r'CONTEXT_QKV trial=(\d+) reuse=(\d+) prep=(\d+) execute=(\d+) total=(\d+) fcsr=(\d+) vcsr=(\d+) digest=([0-9a-f]{16})',line)
        if not m: raise ValueError('Malformed trial')
        row=dict(zip(('trial','reuse','prep','execute','total','fcsr','vcsr'),map(int,m.groups()[:-1])))
        row['digest']=m.group(8)
        if row['trial']!=i or row['reuse']!=int(i in (1,2)) or min(row['prep'],row['execute'])<=0:
            raise ValueError('ABBA identity/cycles')
        # Total also includes loop control and the nested sampling overhead.
        if row['total']<row['prep']+row['execute']: raise ValueError('Inconsistent cycle partitions')
        if not 0<=row['fcsr']<=31 or row['vcsr']!=3: raise ValueError('Invalid CSR')
        if rows and any(row[k]!=rows[0][k] for k in ('digest','fcsr','vcsr')):
            raise ValueError('Numerical/CSR mismatch')
        rows.append(row)
    if golden is not None and (len(golden)!=4 or any(
        any(row[k]!=ref[k] for k in ('trial','reuse','digest','fcsr','vcsr')) for row,ref in zip(rows,golden))):
        raise ValueError('Independent golden mismatch')
    return rows
