"""Check real F16 native observations and actual AKV work, not model speedup."""
from pathlib import Path
from functools import lru_cache
import re
import sys

from audit import require
from check_projection_native import fields

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'akv/paired_heads'))
import attention_run as hardware
from native_runtime_check import expected_record

SCOPE='F16_REAL_SCOPE model=qwen3_1p7b layer=0 d=128 qheads=2 kvheads=1 capacity=256 prefill=64 decode_visible=137 full_ggml=0'
BINDING='F16_REAL_BINDINGS baseline=original_native candidate=observation_only pair_heads=1 pair_pv=1 scale_bits=1035273459'
TERMINAL='F16_REAL_SUITE_PASS phases=2 trials=8 words=66560'
ORDER=(0,1,1,0)
PHASE_NAMES=('preflight','init','query','kv_full','kv_refill','qk','softmax','pv',
             'release','normalize','schedule','barrier_subset','completed','rejected','errors')


@lru_cache(maxsize=2)
def work(phase):
    if phase==0:
        result=[]
        for tile,tokens in enumerate((64,64,9)):
            result.append((4 if not tile else 5,0,tokens))
            result.extend([(6,1,tokens)]*32)
            result.extend([(2,0,tokens)]*tokens)
    else:
        result=[(4,0,64)]
        for tokens in range(1,65):
            result.extend([(6,1,tokens)]*32)
            result.extend([(2,0,tokens)]*tokens)
    return tuple(result+[(3,0,0)])


def expected_calls(phase):
    return ((1,1,0,1,2,3,3,3,1,1,4,21,1,0,0) if not phase else
            (2,1,1,1,0,64,64,64,1,1,131,331,1,0,0))


def check(text):
    lines=text.replace('\r','').splitlines()
    require(not re.search(r'Fatal[-:]|Error[-:]|Assertion[^\n]*failed|^UVM_(?:ERROR|FATAL)\s+@',text,re.M),
            'Simulator diagnostic failure')
    require(lines.count(SCOPE)==lines.count(BINDING)==lines.count(TERMINAL)==1,'Unique real F16 scope/binding/terminal required')
    require(lines.index(SCOPE)<lines.index(BINDING)<lines.index(TERMINAL),'Scope/terminal order')
    require([line for line in lines if 'Core Test' in line]==['Core Test *** SUCCESS *** (tohost = 0)'],
            'Missing, contradictory or extra core completion')
    require(lines.index(TERMINAL)<lines.index('Core Test *** SUCCESS *** (tohost = 0)'),
            'Core completed before fixture')
    trials=[];active=None;group=[];phases=[];rows=[];records=[];summary=None;next_phase=next_trial=0
    row_pattern=re.compile(r'F16_REAL_ROW phase=([01]) trial=([0-3]) row=([0-9]+) hash=([0-9a-f]{16})')
    pending=None;severity=set()
    for line in lines:
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match=re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0',line)
            require(match is not None and match[1] not in severity,'Nonzero/duplicate UVM severity')
            severity.add(match[1])
        if line.startswith('[QBS_PERF] '):raise ValueError('Unexpected QBS work in F16 Attention')
        if line.startswith('F16_REAL_BEGIN '):
            require(active is None and pending is None and len(trials)<8,'Call overlaps unfinished result')
            r=fields(line,'F16_REAL_BEGIN')
            require(r==dict(phase=next_phase,trial=next_trial,probed=ORDER[next_trial]),'Wrong ABBA phase/trial order')
            active=r;group=[];phases=[];rows=[]
        elif line.startswith('[AKV_PERF] '):
            require(active is not None and pending is None,'Native command outside active call')
            r=hardware.numeric_fields(line[len('[AKV_PERF] '):],hardware.PERF_FIELDS)
            sequence=work(active['phase']);require(len(group)<len(sequence),'Extra native command')
            wanted=expected_record(dict(d=128,heads=2,kv=137 if not active['phase'] else 64),
                                   sequence[len(group)],len(records)+1)
            require(all(r.get(k)==v for k,v in wanted.items()),'Actual native command/work differs')
            require(r['id']<8 and r['busy_cycles']>0 and r['read_outstanding_max']<=2,'Command resource record invalid')
            if r['command'] in (4,5):
                require(r['ar']>=r['read_ranges'] and r['r_beats']>=r['ar'] and r['read_outstanding_max']>0,
                        'Missing physical KV/query reads')
            else:
                require(all(r[k]==0 for k in ('ar','r_beats','read_outstanding_max','read_outstanding_occ_sum',
                                             'read_outstanding_full_cycles')),'Local command unexpectedly reads memory')
            group.append(r);records.append(r)
        elif line.startswith('F16_REAL_RESULT '):
            require(active is not None and pending is None and len(group)==len(work(active['phase'])),
                    'Incomplete native work before result')
            r=fields(line,'F16_REAL_RESULT')
            require(set(r)=={'phase','trial','probed','cycles','preparation','words','fcsr','vcsr','vstart','errors'} and
                    all(r[k]==v for k,v in active.items()) and r['words']==(256 if not r['phase'] else 16384) and
                    r['errors']==r['vstart']==0 and r['vcsr']==5 and r['fcsr']<=31 and r['fcsr']&8 and
                    0<r['preparation']<r['cycles'],'Output, timing or completed CSR check failed')
            pending=r
        elif line.startswith('F16_REAL_PHASE '):
            require(pending is not None and not rows,'Phase outside result or after rows')
            r=fields(line,'F16_REAL_PHASE')
            require(set(r)=={'phase','trial','id','calls','cycles'} and r['phase']==pending['phase'] and
                    r['trial']==pending['trial'] and r['id']==len(phases)<15,'Phase record order')
            wanted=expected_calls(r['phase'])[r['id']] if pending['probed'] else 0
            require(r['calls']==wanted and (r['cycles']==0 if not wanted or r['id']>=12 else r['cycles']>0),
                    'Incorrect phase count/scope or uninstrumented control changed')
            phases.append(r)
        elif line.startswith('F16_REAL_ROW '):
            m=row_pattern.fullmatch(line)
            require(pending is not None and len(phases)==15 and m is not None,'Malformed/misordered output row')
            require((int(m[1]),int(m[2]),int(m[3]))==(pending['phase'],pending['trial'],len(rows)),
                    'Output row order/identity')
            rows.append(m[4]);wanted=1 if not pending['phase'] else 64
            require(len(rows)<=wanted,'Extra output row')
            if len(rows)==wanted:
                total=sum(r['cycles'] for r in phases[:11])
                require(total<pending['cycles'] and (total>0 if pending['probed'] else total==0),
                        'Impossible or missing exclusive inner interval')
                if pending['trial']:
                    base=trials[pending['phase']*4]
                    require(rows==base['row_hashes'] and pending['fcsr']==base['fcsr'],
                            'Observed original/candidate row fingerprint or FCSR differs')
                trials.append(dict(pending,phases=phases,row_hashes=rows,hardware_totals=hardware.totals(group)))
                active=pending=None;next_trial+=1
                if next_trial==4:next_phase+=1;next_trial=0
        elif line.startswith('[AKV_PERF_SUMMARY] '):
            require(len(trials)==8 and active is None and summary is None,'Premature/duplicate hardware summary')
            summary=hardware.numeric_fields(line[len('[AKV_PERF_SUMMARY] '):],hardware.SUMMARY_FIELDS)
        elif line.startswith('F16_REAL_'):
            require(line in (SCOPE,BINDING,TERMINAL),'Unknown fixture marker')
            if line==TERMINAL:require(len(trials)==8 and active is None,'Early fixture PASS')
    require(len(trials)==8 and active is None and summary==hardware.totals(records) and
            severity=={'UVM_ERROR','UVM_FATAL'},'Incomplete run or hardware summary')
    require(len(records)==sum(len(work(p)) for p in (0,1))*4,'Actual native command total mismatch')
    measured=[]
    for phase in (0,1):
        t=trials[phase*4:phase*4+4]
        b=(t[0]['cycles']+t[3]['cycles'])/2;c=(t[1]['cycles']+t[2]['cycles'])/2
        perturbations=[(t[1]['cycles']-t[0]['cycles'])/t[0]['cycles'],
                       (t[2]['cycles']-t[3]['cycles'])/t[3]['cycles']]
        allowed=all(abs(p)<=.05 for p in perturbations)
        measured.append(dict(phase=phase,baseline_mean_cycles=b,observed_mean_cycles=c,
            paired_perturbation=perturbations,quantitative_phase_fractions_allowed=allowed,
            exclusive_phase_means={PHASE_NAMES[i]:(t[1]['phases'][i]['cycles']+t[2]['phases'][i]['cycles'])/2
                                   for i in range(11)} if allowed else None))
    return dict(state='REAL_F16_RAW_OBSERVATION_CHECKED',trials=trials,measured=measured,
        native_commands=len(records),hardware_summary=summary,words_checked_on_target=66560,
        external_evidence='All per-query row fingerprints and exact paired CSR; every output checked on target',
        individual_output_words_dumped=False,independent_protocol_checked=False,whole_model=False,
        quantitative_phase_fractions_allowed=all(r['quantitative_phase_fractions_allowed'] for r in measured),
        hardware_speedup_claim=False)
