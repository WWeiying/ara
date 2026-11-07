"""Original strict compute goldens plus scale-port ownership and cycle pairing."""
from collections import defaultdict
import re

from audit import require
from run_wide_compute import check_log, parse_vectors, fields, COUNTERS
from mixed_scale_model_census import eligible


def timing(text, events, clone, mixed, episodes):
    config=[];rows={}
    keys=set('episode cycles mixed_issue mixed_return mixed_nx multi_return union_nx legacy_mul'.split())
    for line in text.splitlines():
        if line.startswith('MC_CONFIG '):config.append(fields(line,'MC_CONFIG'))
        elif line.startswith('MC_TIME '):
            row=fields(line,'MC_TIME');eid=row.get('episode')
            require(set(row)==keys and eid in episodes and eid not in rows and row['cycles']>0,'Timing identity/schema')
            rows[eid]=row
        elif line.startswith('MC_'):
            raise ValueError('Unexpected mixed-compute record')
    require(config==[dict(clone=clone,mixed=mixed,width=128)] and set(rows)==set(episodes),
            'Elaborated mixed configuration/timed episodes incomplete')
    for eid,row in rows.items():
        total=fast=nx=0
        for (episode,acc), records in events.items():
            if episode!=eid:continue
            for r in records:
                if r['kind']!=1 or r['state'] not in (2,3):continue
                require(r['op']==3,'Scale event is not MUL')
                total+=1
                if mixed and eligible(r['b'],r['a'],True):
                    fast+=1
                    product=(0x800000|(r['b']&0x7fffff))*(1024|((r['a']>>13)&1023))
                    shift=11 if product&(1<<34) else 10
                    nx+=bool(product&((1<<shift)-1))
        require(row['mixed_issue']==row['mixed_return']==fast and row['legacy_mul']==total-fast and
                row['mixed_nx']==nx and 0<=row['multi_return']<=fast and
                0<=row['union_nx']<=min(nx,row['multi_return']), 'Physical scale issue/return/NX differs from raw operands')
    return rows


def check(base, off, on, vector):
    shapes=parse_vectors(vector)
    results=[];events=[];times=[]
    order=[1000+i for i in range(5)]+list(range(len(shapes)))
    for text,clone,mixed in ((base,0,0),(off,1,0),(on,1,1)):
        result,ev=check_log(text,shapes,0)
        tm=timing(text,ev,clone,mixed,order)
        results.append(result);events.append(ev);times.append(tm)
    require(events[0]==events[1]==events[2],'Per-accumulator operand/block/order changed')
    require(results[0]==results[1] and times[0]==times[1],'Disabled candidate must preserve all observed cycles/work/flags')
    enabled=times[2]
    require(sum(r['mixed_issue'] for r in enabled.values())>0 and
            sum(r['mixed_nx'] for r in enabled.values())>0 and
            sum(r['multi_return'] for r in enabled.values())>0,'New scale/flags/concurrent-return path not exercised')
    cases=[]
    for s in shapes:
        eid=s['case'];a=times[0][eid];b=enabled[eid]
        cases.append(dict(case=eid,profile=s['profile'],m=s['m'],n=s['n'],kb=s['kb'],
                          baseline_cycles=a['cycles'],candidate_cycles=b['cycles'],
                          component_ratio=a['cycles']/b['cycles'],physical=b))
    return dict(state='MIXED_SCALE_COMPUTE_NUMERICAL_ORDER_AND_DISABLED_CYCLE_PASS',
        normal_per_image=len(shapes),recovery_per_image=5,faults_per_image=5,
        fp_events_per_image=sum(map(len,events[0].values())),cases=cases,
        disabled_cycle_identical=True,operands_flags_outputs_identical=True,
        mixed_issues=sum(r['mixed_issue'] for r in enabled.values()),
        mixed_nx=sum(r['mixed_nx'] for r in enabled.values()),
        simultaneous_returns=sum(r['multi_return'] for r in enabled.values()),
        both_ports_nx=sum(r['union_nx'] for r in enabled.values()),
        whole_model=False,limits=['Component service includes deterministic stimulus transport, not GGML/SDK or model time'])


def fault_check(text, vector, baseline):
    require(not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:FATAL|ERROR)',text),'Fault simulation diagnostic')
    shapes=parse_vectors(vector);s=shapes[0];records=defaultdict(list)
    allowed={'WC_CONFIG','WC_FP','WC_OUTPUT','WC_CASE','WC_FAULT','MC_CONFIG','MC_TIME','MC_FAULT_TRIGGER','MC_FAULT_PASS'}
    for line in text.splitlines():
        if not line.startswith(('MC_','WC_')):continue
        tag=line.split()[0];require(tag in allowed,'Unexpected fault record')
        records[tag].append(fields(line,tag,('a','b','c') if tag=='WC_FP' else ('bits',) if tag=='WC_OUTPUT' else ()))
    require(records['WC_CONFIG']==[dict(version=1,wide=0,weight_bits=128,matrix=1)] and
            records['MC_CONFIG']==[dict(clone=1,mixed=1,width=128)] and
            records['MC_FAULT_PASS']==[dict(recovery=2,faults=2,drain_before_clear=1)],'Fault scope/completion')
    require(len(records['WC_FAULT'])==len(records['MC_FAULT_TRIGGER'])==2,'Both mixed pipeline faults required')
    for i,(fault,trigger) in enumerate(zip(records['WC_FAULT'],records['MC_FAULT_TRIGGER']),5):
        require(set(fault)=={'kind','pending','drain'} and fault['kind']==i and fault['pending']==0 and
                0<fault['drain']<=2048,'Mixed fault did not drain')
        require(set(trigger)=={'kind','issue','response','mixed_busy','entries'} and trigger['kind']==i and
                trigger['entries']>0 and (trigger['issue']==1 if i==5 else trigger['response']==trigger['mixed_busy']==1),
                'Mixed fault not injected in claimed active stage')
    require([r['episode'] for r in records['WC_CASE']]==[1005,1006],'Fault recoveries missing/order')
    output=defaultdict(dict);ev=defaultdict(list)
    for r in records['WC_OUTPUT']:
        require(set(r)=={'episode','index','bits'} and r['episode'] in (1005,1006) and
                r['index'] not in output[r['episode']],'Fault recovery output ownership')
        output[r['episode']][r['index']]=r['bits']
    _,original=check_log(baseline,shapes,0)
    for r in records['WC_FP']:
        require(r['episode'] in (1005,1006),'FP work outside recovery')
        ev[r['episode'],r['acc']].append(r)
    wanted_fields=set('episode acc block kind state op mod rm a b c'.split())
    for eid in (1005,1006):
        require(output[eid]==s['outputs'],'Recovered output differs from independent C oracle')
        for acc in s['outputs']:
            require(all(set(r)==wanted_fields for r in ev[eid,acc]),'FP recovery fields')
            projected=[{**r,'episode':1000} for r in ev[eid,acc]]
            require(projected==original[1000,acc],'Recovered per-block FP sequence/operands differ from baseline')
    require(set(ev)=={(eid,acc) for eid in (1005,1006) for acc in s['outputs']},'Extra/missing recovery FP owner')
    for row in records['WC_CASE']:
        expected=dict(episode=row['episode'],case=0,recovery=1,
                      **{k:s[k] for k in ('profile','m','n','kb','wl','al','flags')},
                      **dict(zip(COUNTERS,s['counters'])),accepted=s['counters'][1],
                      act_accepted=s['counters'][2],result_wait=5,probe_edges=0,probe_bytes=0)
        require(set(row)==set(expected)|{'beats','stalls','overlap'} and
                all(row[k]==v for k,v in expected.items()) and 0<row['beats']<=row['accepted']<=16*row['beats'],
                'Recovery counters/result hold differ')
    # Preserve actual MC timing/ownership checks without projecting faults as
    # ordinary successes. Only the two additional fault marker families differ.
    time_text='\n'.join(l for l in text.splitlines() if not l.startswith(('MC_FAULT_TRIGGER','MC_FAULT_PASS')))
    tm=timing(time_text,ev,1,1,[1005,1006])
    return dict(state='MIXED_PIPELINE_FAULT_DRAIN_RECOVERY_PASS',faults=records['WC_FAULT'],
                triggers=records['MC_FAULT_TRIGGER'],recovery_episodes=list(tm),
                recovery_outputs=2*len(s['outputs']),full_fp_sequence_retained=True)
