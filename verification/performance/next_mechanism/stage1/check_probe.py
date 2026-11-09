#!/usr/bin/env python3
"""Check archived probe results; never infer board identity or native work."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import struct

from audit import phases, read, require, sha


def qbs_census(text):
    result={}
    for line in text.splitlines():
        if not line.startswith('GGML_RISCV_QBS_EXEC '):
            continue
        pairs=[part.split('=',1) for part in line.split()[1:]]
        require(all(len(p)==2 for p in pairs), 'Malformed QBS census')
        fields=dict(pairs)
        require(len(fields)==len(pairs), 'Duplicate QBS field')
        fmt=fields.pop('type')
        require(fmt not in result, 'Duplicate QBS format report')
        require(all(v.isdecimal() for v in fields.values()), 'Invalid QBS counter')
        counters={k:int(v) for k,v in fields.items()}
        require(counters['native_qbexec']>0 and counters['emulated_commands']==0,
                'QBS native path not established')
        require(sum(counters[f'commands_m{i}'] for i in range(1,9))==counters['native_qbexec'],
                'QBS command count mismatch')
        require(counters['command_dot_elements']==counters['dot_elements']>0,
                'QBS work count mismatch')
        result[fmt]=counters
    require(result, 'Missing QBS exit census')
    return result


def node_phase(r, phase_id, active):
    require(r['schema']=='stage1-node-ns-v1' and r['valid'] is True and r['errors']==0,
            'Invalid probe report')
    require(r['active'] is active and r['phase_id']==phase_id and
            r['phase']==('prefill' if phase_id==0 else 'decode'), 'Wrong phase/mode')
    require(r['clock']=='CLOCK_MONOTONIC' and
            r['semantics']=='software_node_elapsed_ns_no_added_sync', 'Wrong clock semantics')
    records=r['records']
    require(len(records)==r['members'] and len(records)>0, 'Missing compute records')
    units=defaultdict(list)
    graphs=set()
    path=[]
    prev=(0,-1)
    for v in records:
        require(1<=v['graph']<=r['graphs'] and
                0<=v['first']<=v['member']<=v['last']<v['nodes'], 'Invalid fused span')
        require((v['graph'],v['member'])>prev, 'Duplicate or unordered node')
        prev=(v['graph'],v['member'])
        require(len(v['ne'])==4 and all(isinstance(x,int) and x>=0 for x in v['ne']), 'Invalid shape')
        graphs.add(v['graph'])
        units[v['graph'],v['first'],v['last']].append(v)
        path.append({k:v[k] for k in ('graph','nodes','first','last','member','op','op_name','type','name','ne')})
    require(len(units)==r['units'], 'Unit count mismatch')
    total=0
    categories=defaultdict(int)
    for (_,first,last), members in units.items():
        require([x['member'] for x in members]==list(range(first,last+1)), 'Missing fused follower')
        require(all(x['nodes']==members[0]['nodes'] for x in members), 'Inconsistent graph geometry')
        require(all(x['elapsed_ns'] is None for x in members[1:]), 'Fused follower double counted')
        elapsed=members[0]['elapsed_ns']
        if active:
            require(type(elapsed)==int and elapsed>=0, 'Missing unit duration')
            total+=elapsed
            # Preserve fused operations as one category; do not assign their
            # interval to individual followers or assume every MUL_MAT is QBS.
            category='+'.join(x['op_name'] for x in members)
            categories[category]+=elapsed
        else:
            require(elapsed is None, 'Metadata-only report contains timing')
    if active:
        require(total==r['unit_ns'] and r['unattributed_ns']>=0 and
                r['phase_ns']==total+r['unattributed_ns'], 'Phase accounting mismatch')
    else:
        require(all(r[k] is None for k in ('phase_ns','unit_ns','unattributed_ns')),
                'OFF timing must be absent')
    return path,dict(categories)


def logits(path, metrics, inputs):
    require(metrics['logits_records']==metrics['single_token_evaluations']+1, 'Logit count mismatch')
    n=metrics['vocabulary']
    history=inputs['fixed_history_tokens']
    require(n==inputs['vocabulary'] and n>0 and len(history)==metrics['single_token_evaluations'],
            'Vocabulary/history mismatch')
    with path.open('rb') as f:
        for step in range(len(history)+1):
            raw=f.read(24)
            require(len(raw)==24, 'Truncated logits header')
            header=struct.unpack('<6I',raw)
            target=history[step] if step<len(history) else 0xffffffff
            require(header==(0x5142534c,2,step,n,target,0), 'Wrong logits header or history')
            raw=f.read(4*n)
            require(len(raw)==4*n, 'Truncated logits values')
            values=struct.unpack('<'+str(n)+'f',raw)
            require(all(math.isfinite(v) for v in values), 'Nonfinite logits')
            require(max(range(n),key=values.__getitem__)==metrics['greedy_tokens_including_final_prediction'][step],
                    'Greedy index does not match full logits')
        require(not f.read(1), 'Trailing logits records')
    return sha(path)


def trial(directory, mode):
    require((directory/'exit_code').read_text().strip()=='0', 'Nonzero exit')
    m=read(directory/'metrics.json')
    i=read(directory/'inputs.json')
    phases(m,(directory/'stdout.log').read_text())
    require(m['arm']=='qbs_akv' and len(i['prompt_tokens'])==m['prompt_tokens'], 'Wrong model input')
    digest=logits(directory/'logits.bin',m,i)
    count=m['single_token_evaluations']+1
    nodes=[]
    actual=set(p.name for p in directory.glob('nodes_*.jsonl'))
    if mode=='plain':
        require(not actual and not m.get('node_metadata_capture'), 'Plain has probe data')
    else:
        require(actual=={f'nodes_{j}.jsonl' for j in range(count)}, 'Missing/extra node files')
        require(m['node_metadata_capture'] is True and m['node_timing_active']==(mode=='timed') and
                m['inference_window_includes_probe_export'] is True, 'Wrong probe metadata')
        nodes=[node_phase(read(directory/f'nodes_{j}.jsonl'),j,mode=='timed') for j in range(count)]
    return dict(metrics=m,inputs=i,logits_sha256=digest,nodes=nodes,
                qbs_census=qbs_census((directory/'stderr.log').read_text()))


def check(directories):
    modes=('plain','metadata','timed','plain')
    trials=[trial(d,m) for d,m in zip(directories,modes)]
    base=trials[0]
    for t in trials[1:]:
        require(t['inputs']==base['inputs'] and t['logits_sha256']==base['logits_sha256'],
                'Input or complete logits changed')
        require([p['paths'] for p in t['metrics']['phases']]==[p['paths'] for p in base['metrics']['phases']],
                'AKV completed path counts changed')
        require(t['qbs_census']==base['qbs_census'], 'QBS completed work changed')
    require([p for p,_ in trials[1]['nodes']]==[p for p,_ in trials[2]['nodes']],
            'Metadata and timed execution/fusion paths differ')
    overhead={}
    for key in ('prefill_compute_ns','decode_compute_ns'):
        a,b=trials[0]['metrics'][key],trials[3]['metrics'][key]
        mean=(a+b)/2
        overhead[key]=dict(plain_mean_ns=mean,plain_spread_fraction=abs(a-b)/mean,
                          metadata_delta_fraction=trials[1]['metrics'][key]/mean-1,
                          timed_delta_fraction=trials[2]['metrics'][key]/mean-1)
    perturbation_ok=all(abs(r['timed_delta_fraction'])<=.02 and
                        abs(r['metadata_delta_fraction'])<=.02 and r['plain_spread_fraction']<=.02
                        for r in overhead.values())
    return dict(state='LOCAL_DATA_CHECKED_EXTERNAL_IDENTITY_PENDING',
                bitwise_logits_equal=True,probe_paths_equal=True,akv_leaf_counts_equal=True,
                qbs_software_native_work_equal=True,qbs_census=base['qbs_census'],
                perturbation_within_target=perturbation_ok,overhead=overhead,
                timed_categories_per_phase=[c for _,c in trials[2]['nodes']],
                units='software node elapsed nanoseconds; fused groups not split',
                open_gates=['Independent board/bitstream/model/ELF/environment identity',
                            'Representative model attribution and final mechanism selection'],
                measurement_accepted=False,
                evidence={str(p):sha(p) for d in directories for p in d.iterdir() if p.is_file()})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trials',nargs=4,type=Path,required=True,
                   metavar=('PLAIN_A','METADATA','TIMED','PLAIN_B'))
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    result=dict(state='FAIL',measurement_accepted=False)
    try:
        result=check(args.trials)
    except BaseException as exc:
        result['error']=repr(exc)
        raise
    finally:
        (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('state','perturbation_within_target','open_gates')},indent=2))


if __name__=='__main__':
    main()
