#!/usr/bin/env python3
"""Check compact full-target-comparison proofs, work and engine measurements."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
from build_support import digest, require, verify

HERE=Path(__file__).resolve().parent
PHASES=tuple('phase_'+name+'_cycles' for name in
    ('setup','activation','weight','compute','overlap','drain','scheduler','commit','fault','terminal'))
TIMES=('quant','pack','plan','execute','drain')


def fields(line,prefix,strings=()):
    require(line.startswith(prefix),'Wrong record prefix')
    result={}
    for token in line[len(prefix):].split():
        require(token.count('=')==1,'Malformed field')
        key,value=token.split('=')
        require(key and value and key not in result,'Duplicate/empty field')
        if key in strings:
            result[key]=value
        else:
            require(re.fullmatch('[0-9]+',value),'Not an unsigned decimal: '+key)
            result[key]=int(value)
    return result


def check_text(text,build):
    c=build['case']; m,n=c['m'],c['n']; native=c['backend']=='native'
    commands=build['plan']['commands'] if native else []
    ab,ib,wb=m*8*292,m*2048*4,n*8*144
    require(text.count('Core Test *** SUCCESS ***')==1,'Missing/duplicate firmware success')
    perf,records=[],{kind:{} for kind in ('TIME','CSR','WORK','PROOF')}
    meta=done=None
    for line in text.splitlines():
        if re.match(r'\s*UVM_(?:ERROR|FATAL)\b',line):
            require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*',line),'UVM failure')
        require(not re.search(r'(?i)(?:^\s*(?:Error[-:]|Fatal:)|Assertion failed|\$fatal|\bTIMEOUT\b|\bTIMED OUT\b)',line),
                'Simulation error/timeout')
        if line.startswith('[QBS_PERF] '):
            require(native and meta is None and len(perf)<2*len(commands),'Unexpected native work')
            p=fields(line,'[QBS_PERF] ')
            require(p['seq']==len(perf)+1 and p['success']==1 and all(p[k]==0 for k in
                ('fault','validation_fault','validation_error','read_fault','context_validation_fault_count')),
                'Command sequence/fault')
            require(sum(p[k] for k in PHASES)==p['busy_cycles']>0 and p['phase_fault_cycles']==0,
                    'Engine phases not exclusive/complete')
            require(p['probe_compute_without_dot_issue_cycles']+p['dot_active_cycles']==
                    p['phase_compute_cycles']+p['phase_overlap_cycles'],'Compute accounting')
            perf.append(p)
        elif line.startswith('QBR_META '):
            require(meta is None and done is None and len(perf)==2*len(commands),'Early/duplicate metadata')
            meta=fields(line,'QBR_META ',('id',))
            require(meta==dict(id=build['build_id'],m=m,n=n,k=2048,tile=c['tile'],
                rvv=int(not native),reuse=0,shared=int(c['shared']),trials=2),
                'Wrong workload/build identity')
        elif any(line.startswith('QBR_'+kind+' ') for kind in records):
            require(meta is not None and done is None,'Early/late trial record')
            kind=line.split()[0][4:]
            r=fields(line,'QBR_'+kind+' ')
            t=r.get('trial')
            require(t in (0,1) and t==len(records[kind]) and t not in records[kind],'Trial order/duplicate')
            records[kind][t]=r
        elif line.startswith('QBR_DONE '):
            require(done is None and all(set(v)=={0,1} for v in records.values()),'Early/duplicate footer')
            done=fields(line,'QBR_DONE ')
            require(done==dict(errors=0,trials=2),'Target validation failed')
        elif line.startswith('QBR_'):
            raise ValueError('Unknown compact-proof record')
    require(meta is not None and done is not None and all(set(v)=={0,1} for v in records.values()) and
            len(perf)==2*len(commands),'Incomplete proof evidence')
    trials=[]
    for t in range(2):
        timing,csr,work,proof=(records[k][t] for k in ('TIME','CSR','WORK','PROOF'))
        require(set(timing)=={'trial','status',*(f't{i}' for i in range(6))} and timing['status']==0,
                'Timing/status schema or admission failure')
        ts=[timing[f't{i}'] for i in range(6)]
        require(all(0<=a<b<2**64 for a,b in zip(ts,ts[1:])),'Bad software phase boundaries')
        if t:
            require(ts[0]>records['TIME'][0]['t5'],'Overlapping trials')
        require(set(csr)=={'trial',*(stage+'_'+reg for stage in ('before','quant','pack','after')
                                   for reg in ('f','v','s'))},'CSR schema')
        seed=8 if t else 0
        require(csr['before_f']==csr['before_s']==0 and csr['before_v']==(2 if c['shared'] and t else 0) and
                csr['quant_f']&~3==0 and csr['quant_v']==csr['pack_v']==csr['after_v']==2 and
                csr['quant_s']==csr['pack_s']==csr['after_s']==0 and
                csr['pack_f']==csr['quant_f'],'CSR/quant/pack preservation failure')
        require(csr['after_f']==(build['plans'][t]['flags']|seed) if native else
                csr['after_f'] in (seed,seed|1),'Execution/sticky flags failure')
        require(set(work)=={'trial','quant','pack','query','plan','execute','planned','actual',
            'eligible','context','coop','caps5','ctx_bytes','ctx_count','ctx_m','ctx_k'},'Work schema')
        count=len(commands) if native else n//32*(1 if m==1 else m//4)
        require(work['quant']==(0 if c['shared'] and t else m) and
                work['pack']==(0 if c['shared'] and t else (m//4 if c['tile']==4 else 1)) and
                work['execute']==1 and work['actual']==count and work['planned']==(count if native else 0),
                'Missing/extra software work')
        if native:
            require(work['query']==work['plan']==1 and work['coop'] in (0,1) and
                    work['coop']==work['caps5']&1 and work['context']==int(c['reuse']!='direct') and
                    work['eligible']==int(m==1) and work['ctx_bytes']==4672 and work['ctx_count']==1 and
                    work['ctx_m']==8 and work['ctx_k']==32,'Real capability/context admission mismatch')
        else:
            require(all(work[k]==0 for k in ('query','plan','eligible','context','coop','caps5',
                                             'ctx_bytes','ctx_count','ctx_m','ctx_k')),'RVV queried native state')
        if t:
            require(all(work[k]==records['WORK'][0][k] for k in ('eligible','context','coop','caps5',
                'ctx_bytes','ctx_count','ctx_m','ctx_k')),'Capabilities/admission changed between calls')
        lengths=dict(out=m*n,q8=ab,pack=ab,input=ib,weight=wb,guard=640,
                     identity=ib+wb+(2*ab if c['shared'] and t==1 else 0),work=count)
        wanted={'trial','csr_bad','first_output_bad'}|{key+suffix for key in lengths for suffix in ('_n','_bad')}
        require(set(proof)==wanted and all(proof[key+'_n']==value for key,value in lengths.items()) and
                all(proof[key+'_bad']==0 for key in lengths) and proof['csr_bad']==0 and
                proof['first_output_bad']==2**32-1,'Full target comparison/work proof failed or incomplete')
        observed=perf[t*len(commands):(t+1)*len(commands)]
        for i,(p,cmd) in enumerate(zip(observed,commands)):
            cm,cn=cmd['m'],cmd['n']
            require((p['m'],p['n'],p['lanes'],p['vlen'])==(cm,cn,4,1024) and
                p['weight_bytes']==cn*8*144 and p['activation_bytes']==cm*8*292 and
                p['useful_pairs']==cm*cn*2048 and p['tiles']==8*(cn//4)*(2 if cm>4 else 1),
                'Command geometry/logical work mismatch')
            capacity=64 if work['coop'] and cm==8 else 32
            require(p['pair_capacity']==capacity*p['dot_active_cycles']==p['useful_pairs'],
                    'Cooperative/noncooperative issue-rate mismatch')
            access=0
            if c['reuse']=='operation': access=1 if i==0 else (3 if i==len(commands)-1 else 2)
            elif c['reuse']=='cross_call': access=(1 if i==0 else 2) if t==0 else (3 if i==len(commands)-1 else 2)
            require(p['activation_access']==access and p['context_fill_count']==int(access==1) and
                p['context_reuse_count']==int(access in (2,3)) and
                p['activation_axi_bytes_saved']==(cm*8*292 if access in (2,3) else 0),
                'Actual hardware context lifecycle mismatch')
        cycles={key:ts[i+1]-ts[i] for i,key in enumerate(TIMES)}
        busy=sum(p['busy_cycles'] for p in observed)
        require(busy<=cycles['execute'],'Engine busy outside execute ROI')
        trials.append(dict(trial=t,label=('gate','up')[t],software_cycles=cycles,
            total_cycles=ts[5]-ts[0],native_busy_cycles=busy,execute_outside_engine=cycles['execute']-busy,
            csr=csr,work=work,target_proof=proof,commands=observed,
            native_phase_cycles={k:sum(p[k] for p in observed) for k in PHASES},
            native_cooperation_used=bool(native and work['coop'] and c['tile']==8)))
    return dict(state='PASS',metrics=dict(case_id=c['id'],backend=c['backend'],m=m,n=n,k=2048,
        baseline_kind=c['baseline_kind'],primary_eligible=True,trials=trials,
        numeric_proof='Sealed target performs every output-element and Q8/pack/input/weight/guard-byte comparison outside ROI; no numeric hash',
        full_host_tensor_dump_checked=False,target_comparator_host_mutation_tested=True,
        protocol_checked=False,current_image_checked=False,whole_model=False,
        scope='Directed complete SDK invocation of a real projection slice, not model/backend integration',
        timing='quant/pack/plan/execute/drain; native command record-tap overhead retained; commit-marker ROI distinct; no cache residency assertion'))


def check_run(log,build):
    path=Path(build); path=path if path.name=='build.json' else path/'build.json'
    b=json.loads(path.read_text())
    require(b['state']=='BUILT_NOT_EXECUTED' and not b['rtl_executed'] and not b['performance_measured'],
            'Wrong build state')
    pin_path=Path(b['input_pins'])
    require(digest(pin_path)==b['input_pins_sha256'],'Input inventory drift')
    pins=json.loads(pin_path.read_text()); verify(pins)
    outer=json.loads((path.parent.parent/'source-pins.json').read_text())
    require(outer.get(str(path.resolve()))==digest(path) and
            pins.get(str(Path(__file__).resolve()))==digest(__file__),'Build/checker not sealed')
    verify(outer)
    require(digest(b['elf'])==b['elf_sha256'],'ELF drift')
    before=digest(log)
    result=check_text(Path(log).read_text(),b)
    verify(pins); verify(outer); require(digest(log)==before,'Log changed during check')
    result.update(build=str(path.resolve()),build_sha256=digest(path),log=str(Path(log).resolve()),
                  log_sha256=before,elf_sha256=b['elf_sha256'],input_pins_sha256=b['input_pins_sha256'])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',required=True,type=Path)
    p.add_argument('--log',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args(); require(not a.output.exists(),'Refusing to overwrite evidence')
    try:
        result=check_run(a.log,a.build)
    except (ValueError,KeyError,OSError,TypeError) as e:
        a.output.write_text(json.dumps(dict(state='FAIL',metrics={},error=str(e)),indent=2)+'\n')
        raise SystemExit(str(e)) from e
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); print(result['state'])


if __name__=='__main__':
    main()
