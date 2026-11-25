#!/usr/bin/env python3
"""Strict compact target-proof check for two QBS SDK boundary workloads."""
import argparse
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
from build_support import digest,require,verify
PHASES=tuple('phase_'+x+'_cycles' for x in
    ('setup','activation','weight','compute','overlap','drain','scheduler','commit','fault','terminal'))
TIMES=('quant','pack','plan','execute','drain')

def fields(line,prefix,strings=()):
    out={}
    for token in line[len(prefix):].split():
        require(token.count('=')==1,'Malformed field')
        key,value=token.split('='); require(key and value and key not in out,'Duplicate/empty field')
        if key in strings: out[key]=value
        else:
            require(re.fullmatch('[0-9]+',value),'Nondecimal field'); out[key]=int(value)
    return out

def check_text(text,b):
    case,plan=b['case'],b['plan']; m=case['m']; seg=case['segment']; commands=plan['commands']
    ab,ib,wb,ws=m*8*292,m*8192,36*8*144,max(plan['workspace_bytes'],4)
    require(text.count('Core Test *** SUCCESS ***')==1,'Missing/duplicate firmware success')
    perf=[]; records={k:{} for k in ('TIME','CSR','WORK','PROOF')}; meta=reject=done=None
    for line in text.splitlines():
        if re.match(r'\s*UVM_(?:ERROR|FATAL)\b',line):
            require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*',line),'UVM failure')
        require(not re.search(r'(?i)(?:^\s*(?:Error[-:]|Fatal:)|Assertion failed|\$fatal|\bTIMEOUT\b|\bTIMED OUT\b)',line),
                'Simulator failure/timeout')
        if line.startswith('[QBS_PERF] '):
            require(meta is None and len(perf)<2*len(commands),'Unexpected native command')
            p=fields(line,'[QBS_PERF] ')
            require(p['seq']==len(perf)+1 and p['success']==1 and all(p[k]==0 for k in
                ('fault','validation_fault','validation_error','read_fault','context_validation_fault_count')),
                'Native sequence/fault')
            require(sum(p[k] for k in PHASES)==p['busy_cycles']>0 and p['phase_fault_cycles']==0,
                    'Engine phase partition')
            require(p['probe_compute_without_dot_issue_cycles']+p['dot_active_cycles']==
                p['phase_compute_cycles']+p['phase_overlap_cycles'],'Compute accounting')
            perf.append(p)
        elif line.startswith('QBB_META '):
            require(meta is None and len(perf)==2*len(commands) and done is None,'Early/duplicate metadata')
            meta=fields(line,'QBB_META ',('id',))
            require(meta==dict(id=b['build_id'],m=m,n=35,k=2048,stride=38,segment=seg,trials=2),'Wrong build/scope')
        elif any(line.startswith('QBB_'+k+' ') for k in records):
            require(meta is not None and reject is None and done is None,'Early/late trial')
            kind=line.split()[0][4:]; r=fields(line,'QBB_'+kind+' '); t=r.get('trial')
            require(t in (0,1) and t==len(records[kind]) and t not in records[kind],'Trial order/duplicate')
            records[kind][t]=r
        elif line.startswith('QBB_REJECT '):
            require(reject is None and done is None and all(set(v)=={0,1} for v in records.values()),'Early/duplicate rejection proof')
            reject=fields(line,'QBB_REJECT ')
        elif line.startswith('QBB_DONE '):
            require(done is None and reject is not None,'Early/duplicate footer')
            done=fields(line,'QBB_DONE '); require(done==dict(errors=0,trials=2),'Target failed')
        elif line.startswith('QBB_'): raise ValueError('Unknown boundary proof record')
    require(meta is not None and reject is not None and done is not None and
        all(set(v)=={0,1} for v in records.values()) and len(perf)==2*len(commands),'Incomplete evidence')
    expected=dict(plan['reject'],calls=0,bytes=m*38*4+2*ab+ib+wb+ws+768,bad=0,
                  fcsr=8,vcsr=2,vstart=0,csr_bad=0)
    require(reject==expected,'Rejection did not preserve full memory/CSR or reached executor')
    trials=[]
    for t in range(2):
        time,csr,work,proof=(records[k][t] for k in ('TIME','CSR','WORK','PROOF'))
        require(set(time)=={'trial','status','fallback',*(f't{i}' for i in range(6))} and
                time['status']==0 and time['fallback']==t,'Explicit caller DIRECT fallback/status')
        ts=[time[f't{i}'] for i in range(6)]
        require(all(0<=a<z<2**64 for a,z in zip(ts,ts[1:])),'Bad phase stamps')
        if t: require(ts[0]>records['TIME'][0]['t5'],'Overlapping trials')
        require(set(csr)=={'trial',*(s+'_'+r for s in ('before','quant','pack','after') for r in ('f','v','s'))},'CSR schema')
        require(csr['before_f']==csr['before_v']==csr['before_s']==0 and csr['quant_f']&~3==0 and
            csr['quant_v']==csr['pack_v']==csr['after_v']==2 and
            csr['quant_s']==csr['pack_s']==csr['after_s']==0 and csr['pack_f']==csr['quant_f'] and
            csr['after_f']==plan['flags']|(8 if t else 0),'Exact flags/VCSR/VSTART failure')
        require(set(work)=={'trial','planned','actual','eligible','split','gather','workspace','snapshots','coop'} and
            work['planned']==work['actual']==len(commands) and work['eligible']==0 and
            work['split']==work['gather']==int(bool(seg)) and work['workspace']==plan['workspace_bytes'] and
            work['snapshots']==plan['snapshot_bytes'] and work['coop'] in (0,1),'SDK plan/work mismatch')
        if t: require(work['coop']==records['WORK'][0]['coop'],'Capability drift')
        lengths=dict(out=m*38,q8=ab,act=ab,input=ib,weight=wb,ws=ws,snap=plan['snapshot_bytes'],guard=768)
        require(set(proof)=={'trial','work_bad','csr_bad'}|{k+s for k in lengths for s in ('_n','_bad')} and
            all(proof[k+'_n']==v and proof[k+'_bad']==0 for k,v in lengths.items()) and
            proof['work_bad']==proof['csr_bad']==0,'Full target numeric/byte/guard/command proof failed')
        observed=perf[t*len(commands):(t+1)*len(commands)]
        for p,c in zip(observed,commands):
            n,kb=c['n'],c['kb']; k_per=4 if m==2 else 2
            require((p['m'],p['n'],p['lanes'],p['vlen'])==(m,n,4,1024) and
                p['weight_bytes']==n*kb*144 and p['activation_bytes']==m*kb*292 and
                p['tiles']==kb*((n+3)//4) and p['useful_pairs']==m*n*kb*256 and
                p['dot_active_cycles']==kb*((n+3)//4)*(256//k_per) and
                p['pair_capacity']==n*kb*256*8//k_per,'M2/M3 N-tail K-segment work accounting')
            require(p['activation_access']==p['context_fill_count']==p['context_reuse_count']==
                    p['activation_axi_bytes_saved']==0,'Unexpected context commands')
        cycles={key:ts[i+1]-ts[i] for i,key in enumerate(TIMES)}; busy=sum(p['busy_cycles'] for p in observed)
        require(busy<=cycles['execute'],'Busy outside execute ROI')
        trials.append(dict(trial=t,software_cycles=cycles,total_cycles=ts[-1]-ts[0],
            native_busy_cycles=busy,execute_residual=cycles['execute']-busy,csr=csr,work=work,
            target_proof=proof,commands=observed,native_phase_cycles={k:sum(p[k] for p in observed) for k in PHASES}))
    return dict(state='PASS',metrics=dict(case_id=case['id'],m=m,n=35,k=2048,segment=seg,trials=trials,
        rejection_contract=reject,fallback='Explicit SDK DIRECT qbs_execute after unsupported context; not automatic RVV fallback',
        full_target_comparison=True,host_full_tensor_readback=False,protocol_checked=False,image_checked=False,
        scope='Current-SDK boundary workload only; parent owns current-image execution and protocol acceptance',
        counter_semantics='Issue capacity includes inactive fourth M3 slot, uses actual N tail rows, not physical lane utilization'))

def check_run(log,build):
    path=Path(build); path=path if path.name=='build.json' else path/'build.json'
    b=json.loads(path.read_text()); require(b['state']=='BUILT_NOT_EXECUTED' and not b['rtl_executed'],'Wrong build state')
    pins_path=Path(b['input_pins']); require(digest(pins_path)==b['input_pins_sha256'],'Input inventory changed')
    pins=json.loads(pins_path.read_text()); outer=json.loads((path.parent.parent/'source-pins.json').read_text())
    require(pins.get(str(Path(__file__).resolve()))==digest(__file__) and outer.get(str(path.resolve()))==digest(path),
            'Checker/build not sealed')
    verify(pins); verify(outer); before=digest(log)
    result=check_text(Path(log).read_text(),b)
    verify(pins); verify(outer); require(digest(log)==before,'Log changed during check')
    result.update(build=str(path.resolve()),build_sha256=digest(path),log=str(Path(log).resolve()),
        log_sha256=before,elf_sha256=digest(b['elf']))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--build',required=True,type=Path)
    p.add_argument('--log',required=True,type=Path); p.add_argument('--output',required=True,type=Path)
    a=p.parse_args(); require(not a.output.exists(),'Refusing to overwrite evidence')
    try: result=check_run(a.log,a.build)
    except (ValueError,KeyError,OSError,TypeError) as e:
        a.output.write_text(json.dumps(dict(state='FAIL',metrics={},error=str(e)),indent=2)+'\n'); raise SystemExit(str(e)) from e
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); print(result['state'])
