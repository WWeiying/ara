import re


def check_log(text,golden):
    if len(golden)!=7008:raise ValueError('Golden size')
    signature=14695981039346656037
    for byte in golden:signature=((signature^byte)*1099511628211)&((1<<64)-1)
    lines=text.splitlines()
    if lines.count('M4_SUMS_SCOPE rows=4 k=1536 bytes=7008 whole_prepare=1 trials=4')!=1 or lines.count('M4_SUMS_RESULT trials=4 errors=0')!=1:
        raise ValueError('Scope/completion')
    rows=[]
    for line in lines:
        if not line.startswith('M4_SUMS_TRIAL '):continue
        m=re.fullmatch(r'M4_SUMS_TRIAL id=(\d+) candidate=(\d+) cycles=(\d+) vector=(\d+) fcsr=(\d+) vcsr=(\d+) errors=(\d+) signature=([0-9a-f]{16})',line)
        if not m:raise ValueError('Malformed trial')
        trial,candidate,cycles,vector,fc,vc,errors=map(int,m.groups()[:7])
        if trial!=len(rows) or trial>=4 or candidate!=(0,1,1,0)[trial] or not cycles or vector!=1 or fc>31 or not fc&8 or vc!=5 or errors or int(m[8],16)!=signature:
            raise ValueError('Trial identity/result')
        if rows and fc!=rows[0]['fcsr']:raise ValueError('Flags differ')
        rows.append(dict(candidate=candidate,cycles=cycles,fcsr=fc))
    if len(rows)!=4:raise ValueError('Incomplete trials')
    trial_lines=[i for i,l in enumerate(lines) if l.startswith('M4_SUMS_TRIAL ')]
    if not (lines.index('M4_SUMS_SCOPE rows=4 k=1536 bytes=7008 whole_prepare=1 trials=4')<trial_lines[0]
            and trial_lines[-1]<lines.index('M4_SUMS_RESULT trials=4 errors=0')):
        raise ValueError('Scope/trial/completion order')
    old=(rows[0]['cycles']+rows[3]['cycles'])/2
    new=(rows[1]['cycles']+rows[2]['cycles'])/2
    return dict(baseline_cycles=old,candidate_cycles=new,speedup=old/new,
        trials=rows,bytes_per_trial=7008,scope='Complete M4 activation preparation only; not projection or model',
        golden_signature=f'{signature:016x}',paired_bitexact=True)
