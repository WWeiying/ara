"""Complete-controller checks with independent balanced work accounting."""
import re

from audit import require
from run_wide_compute import parse_vectors, fields, BLOCKS
from check_balanced_compute import counts, vector as balanced_vector
from run_wide_complete_engine import TRAFFIC
from run_wide_default_engine import check_log, check_geometry

PHASES='setup activation weight compute overlap drain scheduler commit fault terminal'.split()
WORK_KEYS=set('case tiles weights activation pairs capacity dot uops updates flags words mixed nx'.split())


def check(text, original_vector, selected_vector, clone, balanced, gap, contexts):
    require(not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:FATAL|ERROR)',text),'Controller diagnostic')
    require(selected_vector==(balanced_vector(original_vector) if balanced else original_vector),
            'Changed payload/golden/flags or structural counters')
    shapes=parse_vectors(original_vector);count=len(shapes)
    require((count,contexts) in ((36,1),(12,12)),'Unexpected complete-controller suite')
    expected=dict(clone=clone,balanced=balanced,controller=balanced,compute=balanced,bits=256,matrix=1)
    configs=[fields(line,'BE_CONFIG') for line in text.splitlines() if line.startswith('BE_CONFIG ')]
    require(configs==[expected] and text.splitlines().count('WIDE_ENGINE_CONFIG bits=256 matrix=1')==1 and
            text.splitlines().count('MATRIX_ENGINE_CONFIG wide=1')==1,'Unmatched elaborated configuration')
    result=check_log(text,count,contexts,gap);check_geometry(original_vector,result['direct'])
    require([r[0] for r in result['direct']]==list(range(count)),'Reordered direct commands')
    work=[];phases=[]
    for line in text.splitlines():
        if line.startswith('BE_WORK '):work.append(fields(line,'BE_WORK'))
        elif line.startswith('BE_PHASE '):phases.append(fields(line,'BE_PHASE'))
        elif line.startswith('BE_') and not line.startswith('BE_CONFIG '):raise ValueError('Unknown controller marker')
    require(len(work)==len(phases)==count,'Missing direct work/phase observations')
    for s,row,p in zip(shapes,work,phases):
        require(set(row)==WORK_KEYS and row['case']==p['case']==s['case'],'Direct work identity/schema')
        c=counts(s,balanced)
        expect=dict(case=s['case'],flags=s['flags'],words=s['m']*((s['n']+7)//8 if s['m']>4 else 4),
                    **dict(zip(('tiles','weights','activation','pairs','capacity','dot','uops','updates'),c)))
        require(all(row[k]==v for k,v in expect.items()) and 0<=row['nx']<=row['mixed']<=row['uops'],
                'Controller work/flags/commit or scale accounting differs')
        if not balanced or s['m']<3 or BLOCKS[s['profile']][1]==32:
            require(row['mixed']==row['nx']==0,'Mixed path issued for an unqualified command')
        require(set(p)=={'case','cycles',*PHASES} and p['cycles']==result['direct'][s['case']][-1] and
                sum(p[k] for k in PHASES)==p['cycles']+1 and p['fault']==0,
                'Command phase accounting differs')
    traffic=[list(map(int,row)) for row in TRAFFIC.findall(text)]
    require(len(traffic)==count and [r[0] for r in traffic]==list(range(count)),'Traffic inventory')
    for s,row in zip(shapes,traffic):
        cid,ranges,ar,beats,payload,weight,activation=row
        expected_ranges=1+((s['n']+3)//4 if s['wl']==2 else s['n'])*s['kb']+(1 if s['al']>1 else s['m'])*s['kb']
        require(ranges==expected_ranges and ar>=ranges and beats>=ar and
                payload==16+weight+activation and (weight,activation)==tuple(s['counters'][1:3]),
                'Read bytes/ranges differ from native descriptors')
    bus=re.findall(r'^WIDE_ENGINE_BUS bits=(\d+) narrow=(\d+) wide=(\d+) upper=(\d+)$',text,re.M)
    require(len(bus)==1 and int(bus[0][0])==256 and all(int(v)>0 for v in bus[0][1:]),
            'Actual wide/narrow upper-half AXI service missing')
    result.update(work=work,phases=phases,traffic=traffic,bus=list(map(int,bus[0])))
    if balanced:require(sum(row['mixed'] for row in work)>0,'Enabled arithmetic path not exercised')
    return result


def pair(original, disabled, candidate):
    require(original==disabled,'Disabled full controller changes cycles/work/context behavior')
    require([r[:-1] for r in original['direct']]==[r[:-1] for r in candidate['direct']] and
            [r[:4] for r in original['contexts']]==[r[:4] for r in candidate['contexts']] and
            original['traffic']==candidate['traffic'],'Unequal command/context/logical or physical traffic work')
    rows=[]
    for a,b,wa,wb in zip(original['direct'],candidate['direct'],original['work'],candidate['work']):
        require(all(wa[k]==wb[k] for k in ('case','tiles','weights','activation','pairs','uops','updates','flags','words')),
                'Changed useful work or completion')
        if a[2]<=2 or BLOCKS[a[1]][1]==32:
            require(a==b,'Unqualified command changed full-controller timing')
        rows.append(dict(case=a[0],profile=a[1],m=a[2],n=a[3],kb=a[4],
                         baseline_cycles=a[-1],candidate_cycles=b[-1],controller_ratio=a[-1]/b[-1]))
    return dict(default_off_exact=True,unqualified_timing_identical=True,cases=rows,
                baseline_cycles=sum(r[-1] for r in original['direct']),
                candidate_cycles=sum(r[-1] for r in candidate['direct']),
                full_soc=False,whole_model=False,
                limits=['Synthetic AXI and translation/PMA model; not CVA6 MMU/PMP or SDK preparation'])
