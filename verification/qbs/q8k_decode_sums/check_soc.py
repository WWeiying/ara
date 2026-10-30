"""Strict ABBA records and optional independent QEMU digest comparison."""
import re


def check(text, golden=None):
    lines=[line.strip() for line in text.splitlines() if line.startswith('DECODE_SUMS')]
    if len(lines)!=9 or lines[-1]!='DECODE_SUMS_RESULT errors=0 trials=8':
        raise ValueError('Missing, duplicate or failed result')
    rows=[]
    for i,line in enumerate(lines[:-1]):
        match=re.fullmatch(r'DECODE_SUMS k=(\d+) trial=(\d+) candidate=(\d+) cycles=(\d+) fcsr=(\d+) vcsr=(\d+) digest=([0-9a-f]{16})',line)
        if not match: raise ValueError('Malformed trial')
        k,t,c,cycles,f,v,h=match.groups()
        row=dict(k=int(k),trial=int(t),candidate=int(c),cycles=int(cycles),fcsr=int(f),vcsr=int(v),digest=h)
        if (row['k']!=(1536 if i<4 else 8960) or row['trial']!=i%4 or
            row['candidate']!=int(i%4 in (1,2)) or row['cycles']<=0 or
            not 0<=row['fcsr']<=31 or not 0<=row['vcsr']<=7):
            raise ValueError('Invalid trial identity or CSR')
        if i%4 and any(row[key]!=rows[i-i%4][key] for key in ('fcsr','vcsr','digest')):
            raise ValueError('ABBA output mismatch')
        rows.append(row)
    if golden is not None:
        if len(golden)!=8 or any({k:v for k,v in row.items() if k!='cycles'}!=
                                {k:v for k,v in ref.items() if k!='cycles'} for row,ref in zip(rows,golden)):
            raise ValueError('Independent QEMU result mismatch')
    return rows
