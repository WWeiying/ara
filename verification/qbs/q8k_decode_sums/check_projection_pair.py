import re


def check(text, golden=None):
    lines=[s.strip() for s in text.splitlines() if s.startswith('DECODE_PROJECTION')]
    if len(lines)!=5 or lines[-1]!='DECODE_PROJECTION_RESULT errors=0 trials=4 m=1 n=1536 k=1536 commands=192':
        raise ValueError('Missing complete projection acceptance')
    rows=[]
    for i,line in enumerate(lines[:-1]):
        m=re.fullmatch(r'DECODE_PROJECTION trial=(\d+) candidate=(\d+) prep=(\d+) execute=(\d+) total=(\d+) fcsr=(\d+) vcsr=(\d+) digest=([0-9a-f]{16})',line)
        if not m: raise ValueError('Malformed projection trial')
        row=dict(zip(('trial','candidate','prep','execute','total','fcsr','vcsr'),map(int,m.groups()[:-1])))
        row['digest']=m.group(8)
        if row['trial']!=i or row['candidate']!=int(i in (1,2)) or min(row['prep'],row['execute'])<=0 or row['total']!=row['prep']+row['execute']:
            raise ValueError('Invalid ABBA identity or cycles')
        if not 0<=row['fcsr']<=31 or row['vcsr']!=3: raise ValueError('Invalid CSR')
        if rows and any(row[k]!=rows[0][k] for k in ('digest','fcsr','vcsr')):
            raise ValueError('Numerical/CSR mismatch')
        rows.append(row)
    if golden is not None and (len(golden)!=4 or any(
            any(row[k]!=ref[k] for k in ('trial','candidate','digest','fcsr','vcsr'))
            for row,ref in zip(rows,golden))):
        raise ValueError('Independent golden mismatch')
    return rows
