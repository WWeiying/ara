"""Independent work accounting and raw replay for the balanced candidate."""
from collections import defaultdict
import re

from audit import require
from run_wide_compute import parse_vectors, check_log, fields, BLOCKS, COUNTERS
from mixed_scale_model_census import eligible

WIDTH=1


def counts(shape, balanced):
    if not balanced:return list(shape['counters'])
    block=BLOCKS[shape['profile']][1]
    m,n,k=(shape[key] for key in ('m','n','kb'))
    waves=[m] if m<=4 else [4,m-4]
    issues=sum(block//(8 if w==1 or (block==256 and w>=3) else 4 if w==2 or block==256 else 2)
               for w in waves)
    result=list(shape['counters'])
    result[4]=n*k*issues*32
    result[5]=((n+3)//4)*k*issues
    return result


def candidate_shapes(shapes):
    return [{**s,'counters':counts(s,True)} for s in shapes]


def vector(text):
    shapes=parse_vectors(text);out=[];owner=None
    for line in text.splitlines():
        row=line.split()
        if row[0]=='CMD':owner=int(row[1])
        elif row[0]=='C':
            require(list(map(int,row[1:]))==shapes[owner]['counters'],'Counter source changed')
            line='C '+' '.join(map(str,counts(shapes[owner],True)))
        elif row[0]=='END':owner=None
        out.append(line)
    return '\n'.join(out)+'\n'


def admitted(shape, acc):
    context=acc//(16 if shape['m']>4 else 32)
    return BLOCKS[shape['profile']][1]==256 and (shape['m']>=3 if context<4 else shape['m']>=7)


def observations(text, events, clone, balanced, episodes):
    config=[];times={};physical={}
    time_keys=set('episode cycles mixed_issue mixed_return mixed_nx multi_return union_nx legacy_mul'.split())
    physical_keys=set('episode dot_issues corrections last_correction fp_input_blocked fp_slot_blocked fp_acc_blocked correction_pending fp_no_uop'.split())
    for line in text.splitlines():
        if line.startswith('MC_CONFIG '):config.append(fields(line,'MC_CONFIG'))
        elif line.startswith('MC_TIME '):
            row=fields(line,'MC_TIME');eid=row.get('episode')
            require(set(row)==time_keys and eid in episodes and eid not in times and row['cycles']>0,
                    'Timing identity/schema');times[eid]=row
        elif line.startswith('BC_PHYSICAL '):
            row=fields(line,'BC_PHYSICAL');eid=row.get('episode')
            require(set(row)==physical_keys and eid in episodes and eid not in physical,
                    'Physical identity/schema');physical[eid]=row
        elif line.startswith(('MC_','BC_')):raise ValueError('Unexpected balanced marker')
    require(config==[dict(clone=clone,mixed=balanced,width=256)] and
            set(times)==set(physical)==set(episodes),'Elaborated configuration/episode inventory')
    for eid,shape in episodes.items():
        total=fast=nx=0
        for (episode,acc),records in events.items():
            if episode!=eid:continue
            for row in records:
                if row['kind']!=1 or row['state'] not in (2,3):continue
                require(row['op']==3,'Scale event must remain MUL');total+=1
                if balanced and admitted(shape,acc) and eligible(row['b'],row['a'],True):
                    fast+=1
                    product=(0x800000|(row['b']&0x7fffff))*(1024|((row['a']>>13)&1023))
                    shift=11 if product&(1<<34) else 10
                    nx+=bool(product&((1<<shift)-1))
        t=times[eid];p=physical[eid]
        require(t['mixed_issue']==t['mixed_return']==fast and t['mixed_nx']==nx and
                t['legacy_mul']==total-fast and 0<=t['multi_return']<=fast and
                0<=t['union_nx']<=min(nx,t['multi_return']),'Physical FP routes/NX differ from operand ownership')
        subgroup=8 if shape['profile'] in (1,4) else 16 if BLOCKS[shape['profile']][1]==256 else 1
        require(p['dot_issues']==counts(shape,balanced)[5] and
                p['corrections']==shape['m']*shape['n']*shape['kb']*subgroup,
                'Physical dot/correction work differs')
        require(p['dot_issues']<=t['cycles'] and p['corrections']<=8*t['cycles'] and
                0<=p['last_correction']<=p['corrections'] and
                ((balanced and shape['m']>=3 and BLOCKS[shape['profile']][1]==256) or
                 p['last_correction']==0) and
                p['fp_slot_blocked']+p['fp_acc_blocked']<=p['fp_input_blocked']<=t['cycles'] and
                all(0<=p[key]<=t['cycles'] for key in ('correction_pending','fp_no_uop')),
                'Impossible pressure observations')
    return times,physical


def check(base, off, on, original_vector, balanced_vector):
    require(vector(original_vector)==balanced_vector,'Candidate changes payload/golden/flags or wrong work counters')
    shapes=parse_vectors(original_vector);new=candidate_shapes(shapes)
    results=[];events=[];times=[];physical=[]
    for text,clone,mode,ss in ((base,0,0,shapes),(off,1,0,shapes),(on,1,1,new)):
        result,ev=check_log(text,ss,WIDTH)
        episodes={s['case']:s for s in ss};episodes.update({1000+i:ss[0] for i in range(5)})
        # Counts are computed from the frozen original work description.
        old_episodes={eid:shapes[0] if eid>=1000 else shapes[eid] for eid in episodes}
        t,p=observations(text,ev,clone,mode,old_episodes)
        results.append(result);events.append(ev);times.append(t);physical.append(p)
    require(events[0]==events[1]==events[2],'Per-accumulator operands/K-block/FP order changed')
    require(results[0]==results[1] and times[0]==times[1] and physical[0]==physical[1],
            'Disabled candidate changes original timing/work/pressure')
    for s in shapes:
        if s['m']<=2 or BLOCKS[s['profile']][1]==32:
            require(times[0][s['case']]==times[2][s['case']],
                    'M1/M2 or short-format execution changed')
    require(sum(t['mixed_issue'] for t in times[2].values())>0 and
            sum(t['mixed_nx'] for t in times[2].values())>0 and
            sum(p['last_correction'] for p in physical[2].values())>0,
            'New arithmetic/correction path unexercised')
    cases=[]
    for s in shapes:
        eid=s['case'];a=times[0][eid];b=times[2][eid]
        cases.append(dict(case=eid,profile=s['profile'],m=s['m'],n=s['n'],kb=s['kb'],
            baseline_cycles=a['cycles'],candidate_cycles=b['cycles'],component_ratio=a['cycles']/b['cycles'],
            baseline_physical=physical[0][eid],candidate_physical=physical[2][eid],candidate_fp=b))
    return dict(state='BALANCED_COMPUTE_ORDER_FLAGS_WORK_AND_DISABLED_CYCLES_PASS',
        normal_per_image=len(shapes),recovery_per_image=5,faults_per_image=5,
        disabled_cycle_identical=True,m1_m2_and_short_format_timing_identical=True,
        per_accumulator_fp_order_equal=True,cases=cases,
        mixed_issues=sum(t['mixed_issue'] for t in times[2].values()),
        mixed_nx=sum(t['mixed_nx'] for t in times[2].values()),
        last_correction_issues=sum(p['last_correction'] for p in physical[2].values()),
        whole_model=False,limits=['Component service includes deterministic transport, not SDK/GGML/model time'])


def fault_check(text, original_vector, baseline):
    require(not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:FATAL|ERROR)',text),'Fault simulation diagnostic')
    shapes=parse_vectors(original_vector);s=shapes[1];new={**s,'counters':counts(s,True)}
    require(s['m']>=3 and BLOCKS[s['profile']][1]==256,'Fault fixture lacks balanced wave')
    records=defaultdict(list)
    allowed={'WC_CONFIG','WC_FP','WC_OUTPUT','WC_CASE','WC_FAULT','MC_CONFIG','MC_TIME',
             'MC_FAULT_TRIGGER','MC_FAULT_PASS','BC_PHYSICAL','BC_FAULT_TRIGGER'}
    for line in text.splitlines():
        if not line.startswith(('MC_','WC_','BC_')):continue
        tag=line.split()[0];require(tag in allowed,'Unexpected fault marker')
        records[tag].append(fields(line,tag,('a','b','c') if tag=='WC_FP' else ('bits',) if tag=='WC_OUTPUT' else ()))
    require(records['WC_CONFIG']==[dict(version=1,wide=1,weight_bits=256,matrix=1)] and
            records['MC_CONFIG']==[dict(clone=1,mixed=1,width=256)] and
            records['MC_FAULT_PASS']==[dict(recovery=3,faults=3,drain_before_clear=1)],'Fault configuration/completion')
    require(len(records['WC_FAULT'])==3 and len(records['MC_FAULT_TRIGGER'])==2,
            'Missing mixed/last-correction faults')
    for index,row in enumerate(records['WC_FAULT'],5):
        require(set(row)=={'kind','pending','drain'} and row['kind']==index and row['pending']==0 and
                0<row['drain']<=2048,'Fault did not drain')
    for index,row in enumerate(records['MC_FAULT_TRIGGER'],5):
        require(set(row)=={'kind','issue','response','mixed_busy','entries'} and row['kind']==index and
                row['entries']>0 and (row['issue']==1 if index==5 else row['response']==row['mixed_busy']==1),
                'Claimed mixed fault stage not reached')
    require(records['BC_FAULT_TRIGGER']==[dict(kind=7,last_correction=1,lanes=8,integer_busy=1)],
            'Last correction lane not actually active')
    eids=(1005,1006,1007)
    require([r['episode'] for r in records['WC_CASE']]==list(eids),'Fault recovery inventory')
    output=defaultdict(dict);ev=defaultdict(list)
    for row in records['WC_OUTPUT']:
        require(set(row)=={'episode','index','bits'} and row['episode'] in eids and
                row['index'] not in output[row['episode']],'Recovery output ownership')
        output[row['episode']][row['index']]=row['bits']
    _,old=check_log(baseline,shapes,WIDTH)
    keys=set('episode acc block kind state op mod rm a b c'.split())
    for row in records['WC_FP']:
        require(set(row)==keys and row['episode'] in eids,'Recovery FP ownership')
        ev[row['episode'],row['acc']].append(row)
    for eid in eids:
        require(output[eid]==s['outputs'],'Recovery differs from independent C oracle')
        for acc in s['outputs']:
            require([{**r,'episode':1} for r in ev[eid,acc]]==old[1,acc],
                    'Recovered operand/K-block order differs from baseline')
    require(set(ev)=={(eid,acc) for eid in eids for acc in s['outputs']},'Missing/extra recovery FP work')
    for row in records['WC_CASE']:
        expected=dict(episode=row['episode'],case=1,recovery=1,
            **{k:s[k] for k in ('profile','m','n','kb','wl','al','flags')},
            **dict(zip(COUNTERS,new['counters'])),accepted=s['counters'][1],
            act_accepted=s['counters'][2],result_wait=5,probe_edges=0,probe_bytes=0)
        require(set(row)==set(expected)|{'beats','stalls','overlap'} and
                all(row[k]==v for k,v in expected.items()) and
                0<row['beats']<=row['accepted']<=32*row['beats'],'Recovered counters/hold differ')
    clean='\n'.join(line for line in text.splitlines() if not line.startswith(('MC_FAULT_','BC_FAULT_')))
    t,p=observations(clean,ev,1,1,{eid:s for eid in eids})
    return dict(state='BALANCED_MIXED_AND_LAST_CORRECTION_FAULT_DRAIN_RECOVERY_PASS',
        faults=records['WC_FAULT'],mixed_triggers=records['MC_FAULT_TRIGGER'],
        last_correction_trigger=records['BC_FAULT_TRIGGER'],recoveries=list(t),
        recovery_outputs=3*len(s['outputs']),full_fp_sequence_retained=True)
