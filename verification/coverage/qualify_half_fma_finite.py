"""Full architectural reference plus exact16-core finite FMA handshake audit."""
from collections import deque
import json
from pathlib import Path
import re
from types import FunctionType
import prepare_half_fma_finite as gold
import audit_gap115_axi_v2 as frozen_parser

life, require = gold.life, gold.require


def wave(path, scopes):
    # Discover only the two typed packed layouts emitted by the frozen converter.
    reader=FunctionType(frozen_parser.vcd.__code__,dict(frozen_parser.vcd.__globals__,ROOT='ara_tb',WIDTHS={}))
    iterator=iter(reader(path));_,decl=next(iterator)
    widths={'ara_tb.clk':1,'ara_tb.rst_n':1}
    simple={'in_valid_i':1,'in_ready_o':1,'out_valid_o':1,'out_ready_i':1,
            'mask_i':1,'mask_o':1,'op_i':5,'rnd_mode_i':3,'result_o':16}
    operands={};statuses={}
    for scope in scopes:
        for name,width in simple.items():widths[scope+'.'+name]=width
        if scope+'.operands_i' in decl:
            operands[scope]=[(scope+'.operands_i',48)]
        else:operands[scope]=[(scope+'.operands_i[%d]'%i,16) for i in range(3)]
        if scope+'.status_o' in decl:statuses[scope]=[(scope+'.status_o',5)]
        else:statuses[scope]=[(scope+'.status_o.'+name,1) for name in ('NX','UF','OF','DZ','NV')]
        widths.update(operands[scope]);widths.update(statuses[scope])
    require(all(decl.get(name,{}).get('width')==width for name,width in widths.items()),
            'Exact typed16-core waveform fields missing/drifted')
    codes={name:decl[name]['code'] for name in widths}
    def value(state,name):
        bits=state.get(codes[name],'x');require(set(bits)<=set('01'),'Unknown accepted field '+name)
        return int(bits,2)
    pending={s:deque() for s in scopes};counts={s:dict(accepted=0,completed=0) for s in scopes}
    phases=[(p,beat) for p in range(4) for beat in range(2 if p==3 else 4)]
    for time,before,after in iterator:
        if before.get(codes['ara_tb.clk'])!='0' or after.get(codes['ara_tb.clk'])!='1':continue
        if before.get(codes['ara_tb.rst_n'])!='1':continue
        for scope in scopes:
            def val(name):return value(before,scope+'.'+name)
            if val('in_valid_i') and val('in_ready_o'):
                ordinal=counts[scope]['accepted'];require(ordinal<len(phases),'Extra FMA acceptance')
                phase,beat=phases[ordinal];lane,simd=map(int,re.search(r'gen_lanes\[(\d+)\].*gen_num_lanes\[(\d+)\]',scope).groups())
                index=16*beat+4*lane+simd
                packed=sum(value(before,n)<<(16*i) for i,(n,w) in enumerate(operands[scope])) if len(operands[scope])==3 else value(before,operands[scope][0][0])
                actual=tuple(packed>>(16*i)&65535 for i in range(3));expected=gold.PATTERNS[index%8]
                require(actual==expected and val('op_i')==0 and val('rnd_mode_i')==int(phase==1),
                        'Actual accepted finite FMADD operands/op/round differ')
                mask=int(index<(31 if phase==3 else 64) and (phase!=2 or index%2==1))
                require(val('mask_i')==mask,'Accepted SIMD mask/tail differs')
                result,flags=gold.fused(*expected,int(phase==1))
                pending[scope].append((result,flags,mask));counts[scope]['accepted']+=1
            if val('out_valid_o') and val('out_ready_i'):
                require(pending[scope],'Orphan FMA completion');result,flags,mask=pending[scope].popleft()
                status=sum(value(before,n)<<i for i,(n,w) in enumerate(statuses[scope])) if len(statuses[scope])==5 else value(before,statuses[scope][0][0])
                require((val('result_o'),status,val('mask_o'))==(result,flags,mask),
                        'Actual finite result/flags/mask differs')
                counts[scope]['completed']+=1
    require(all(not pending[s] and counts[s]==dict(accepted=14,completed=14) for s in scopes),
            'Incomplete/missing16-core exact four-phase observations')
    return dict(status='ACTUAL16_HALF_FMA_FINITE_OPERANDS_RESULT_FLAGS_PASS',cores=16,
                accepted=224,completed=224,per_scope=counts,no_internal_force=True)


def collect(out,record):
    life.check(record['pins']);pre=record['preflight'];symbols=pre['symbols']
    require(json.loads((out/'simulation-status.json').read_bytes())['returncode']==0,'Terminal return')
    log=(out/'run.vcs.log').read_text()
    require(log.count('Core Test *** SUCCESS ***')==1 and not re.search(
        r'(?m)^UVM_(ERROR|FATAL)\b|\[ARA_CONTRACT_ERROR\]|tohost\s*=\s*3\b',log), 'DUT functional/error terminal')
    shared=gold.reused.old.shared.shared
    scalar=shared.spike_trace.compare_commit_prefix(gold.PRE/'spike.trace',out/'commit_trace.csv',
        0x80000000,terminal_tohost_address=symbols['tohost'],rvfi_store_data_layout='unshifted')
    shared.scalar_exact(scalar,pre['counts'])
    vector=shared.compare_vector_commits(gold.PRE/'spike.trace',out/'commit_trace.csv',out/'vector_trace.csv',0x80000000)
    require(vector['status']=='PASS' and all(vector[k]==0 for k in
        ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions')) and
        not vector['incomplete_requests'] and not vector['unretired_requests'] and
        all(r['unknown_write_bytes']==r['skipped_unknown_bytes']==r['mismatch_count']==0 for r in vector['instructions']),
        'Complete native vector comparison')
    import csv
    memory={}
    for row in csv.DictReader((out/'commit_trace.csv').open()):
        if row['event']=='retire':
            store=shared.scalar_store(row)
            if store:memory.update({store[0]+i:b for i,b in enumerate(store[1])})
    def value(name,offset=0,size=8):
        address=symbols[name]+offset
        require(all(address+i in memory for i in range(size)),'Missing full oracle bytes')
        return int.from_bytes(bytes(memory[address+i] for i in range(size)),'little')
    gold.oracle(value)
    observations=wave(out/'half-fma.vcd',record['scopes'])
    life.save(out/'scalar-comparison.json',scalar);life.save(out/'vector-comparison.json',vector)
    life.save(out/'fma-wave-audit.json',observations)
    pins=life.merge_pins(record['pins'],{str(p):life.digest(p) for p in out.iterdir() if p.is_file() and p.name!='worker.log'})
    result=dict(status='FOUR_PHASE_HALF_FMA_FUNCTIONALLY_QUALIFIED_NOT_ADMITTED',
        software_checks=2900,full_vrf_bytes=16384,csr_words=20,scalar_counts=pre['counts'],
        vector_bytes=vector['compared_bytes'],FMA_observations=observations,source_guard_contract=True,
        no_exhaustive_IEEE_claim=True,coverage_admitted=False,native_exclusion_qualified=False,pins=pins)
    life.save(out/'qualification.json',result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(out/'qualification.json'))),flush=True)
