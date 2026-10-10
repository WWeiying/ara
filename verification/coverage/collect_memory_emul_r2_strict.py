"""Offline parent-terminal R2 full architecture/raw audit against722; no launch, waiver or admission."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import run_memory_emul_r2_simulation as runner
import collect_opivx_vsbc_strict as common
import coverage_bitmap_delta as bitmap
from ara_verify import vector_commit as vc

p, life, require = runner.preflight, runner.life, runner.require
PRE_SEAL = '1f3ae5b8faf7195a6eca0f29688ed8d8b4e03c90ee09fc6f7fc806fd76514245'
RUN_SEAL = '04367aceccce9e5d60f5a72319164acee39b3ebe628d7590032b230c994e8761'
RUN = life.OUT/'memory-emul-r2-old-image-parent-20261006-01'
BASE = life.OUT/'gap104-offline-admitted-722-20261006-02'
BASE_SEAL = 'b9ad9d11e0eeb709ebcf3e4bd6d5ccbdd94d4a229e9c80b144ef10cf8213415a'
DESIGN = p.old.review.VDB


def terminal(state, actual, prepared):
    require(state.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and type(state.get('returncode')) is int and
            state['returncode']==0 and state.get('case')==p.NAME and state.get('coverage_admitted') is False and
            state.get('admission_performed') is False,'Nonterminal/failed simulation')
    require(actual==prepared,'Actual run contract/command differs')


def lifecycle(rows,vectors,s):
    starts,pending,uops,done={}, {}, {}, {}
    requests,responses,rejected=[],[],[]
    allocations,completions=Counter(),Counter()
    retires=[]
    for r in rows:
        event,seq,tid=r['event'],int(r['order']),int(r['trans_id'])
        if event=='arch_start':
            require(seq not in starts and tid not in pending,'Duplicate arch/live transaction')
            starts[seq],pending[tid]=r,[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1],'Unknown/duplicate request')
            a=pending[tid][0];require(int(r['insn'],16)==int(starts[a]['insn'],16),'Request opcode differs')
            pending[tid][1]=True;requests.append(a)
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1],'Unknown/duplicate response')
            require(seq==-1 and int(r['pc'],16)==int(r['insn'],16)==0,'Frozen response placeholder differs')
            a=pending.pop(tid)[0];responses.append(a)
            require(int(r['trap']) in (0,1),'Invalid response trap')
            if int(r['trap']):rejected.append(a)
        elif event in ('uop_alloc','uop_done'):
            key=seq,int(r['port'])
            require(seq in starts and int(r['insn'],16)==int(starts[seq]['insn'],16) and
                    int(r['cycle'])>=int(starts[seq]['cycle']),'Backend ownership/opcode/time differs')
            if event=='uop_alloc':
                require(key not in uops,'Live backend VID reused');uops[key]=r;allocations[key]+=1
            else:
                require(key in uops and int(r['cycle'])>=int(uops[key]['cycle']),'Unallocated backend done')
                uops.pop(key);completions[key]+=1
        else:
            require(event=='retire' and not int(r['trap']),'Unknown event/RVFI trap')
            if vc.is_vector_instruction(int(r['insn'],16)):
                retires.append(vc.VectorRetire(pc=int(r['pc'],16),instruction=int(r['insn'],16)))
    require(not pending and Counter(requests)==Counter(responses)==Counter(starts.keys()),'Request/response conservation')
    require(not uops and allocations==completions,'Incomplete backend activity')
    # Legal initialization/boundaries/recovery share all three rejected opcodes.
    # Only actual response exceptions identify bad arch_seq; PC binding comes from oracle/tracer.
    require(len(rejected)==3 and [int(starts[a]['insn'],16) for a in rejected]==p.BAD_WORDS,
            'Not exact ordered3 rejected encodings')
    require(not any(a in rejected for a,_ in allocations),'Illegal backend/VLSU allocation')
    mapping=vc._map_architecture_retires([(a,int(r['insn'],16)) for a,r in starts.items()],retires,set(rejected))
    legal=[]
    for name,word in p.PAIRS[3:]:
        owners=[a for a,r in mapping.items() if r.pc==s[name] and r.instruction==word]
        require(len(owners)==1 and any(a==owners[0] for a,_ in allocations),'Legal boundary/recovery absent: '+name)
        legal.append(dict(name=name,arch_seq=owners[0],pc=s[name],instruction=word))
    va,vd,vpending=Counter(),Counter(),{}
    for r in vectors:
        event,a,key=r['event'],int(r['arch_seq']),(int(r['arch_seq']),int(r['vid']))
        require(int(r['nr_lanes'])==4 and int(r['vlen_bits'])==1024,'Vector configuration differs')
        require(a not in rejected,'Illegal vector activity including config')
        if event=='config':continue
        require(a in starts and event in ('alloc','done','write') and
                int(r['insn'],16)==int(starts[a]['insn'],16),'Vector ownership/opcode differs')
        if event=='alloc':
            require(key not in vpending,'Live vector VID reused');vpending[key]=r;va[key]+=1
        else:
            alloc=vpending.get(key)
            if alloc is None and event=='write':
                alloc=done.get(key)
                require(alloc is not None and int(r['cycle'])==int(alloc['cycle']),'Write outside completion')
            require(alloc is not None and int(r['cycle'])>=int(alloc['cycle']) and
                    all(r[k]==alloc[k] for k in ('insn','use_vd','vd','eew','vl','vstart')),'Vector metadata/time differs')
            if event=='done':vpending.pop(key);done[key]=r;vd[key]+=1
    require(not vpending and va==vd==allocations,'Commit/vector lifecycle differs')
    return dict(requests=len(requests),responses=len(responses),exceptions=3,rejected_arch_seqs=rejected,
                legal_operations=legal,backend_uops=sum(allocations.values()),rejected_backend_uops=0,
                rejected_vrf_activities=0,classification='Actual exception arch_seq, not shared opcode or response placeholder',
                illegal_memory_issue_proof='No backend allocation including VLSU, static reject chain, unchanged buffers; no bus-address probe claimed')


def observed(rows,s):
    retired=[r for r in rows if r['event']=='retire']
    require(retired and [int(r['order']) for r in retired]==list(range(len(retired))),'Incomplete retirement order')
    memory,loads,stores,terminals={},set(),[],[]
    ranges=[(s['gmr_dump'],7*32*18*8),(s['gmr_input'],3*18*8),(s['gmr_output'],3*18*8)]
    expected_loads={a+i for a,size in ranges for i in range(size)}
    badpcs={s['gmr_bad_%02d'%n] for n in range(3)}
    entries=0
    for r in retired:
        insn,pc,addr=int(r['insn'],16),int(r['pc'],16),int(r['mem_addr'],16)
        require(not int(r['trap']) and pc not in badpcs|{s['trap_fail']},'Illegal/fatal retirement')
        handler=s['gmr_handler']<=pc<s['gmr_handler_end'];entries+=pc==s['gmr_handler']
        if handler:
            require(int(r['rd']) in (0,5,6,7),'Protected handler register modified')
            if insn&127==0x73 and (insn>>12)&7:
                fn,rs=(insn>>12)&7,(insn>>15)&31
                writes=fn in (1,5) or (fn in (2,3,6,7) and rs!=0)
                require(not writes or insn>>20 in (0x300,0x340,0x341),'Protected handler CSR modified')
        rm,wm=int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        access=common.scalar_memory(insn)
        if access:
            kind,width=access;mask=((1<<width)-1)<<(addr&7)
            require(addr%width==0 and rm==(mask if kind=='read' else 0) and wm==(mask if kind=='write' else 0),
                    'Scalar memory mask/alignment differs')
            if kind=='write':
                value=int(r['mem_wdata'],16)&((1<<(8*width))-1)
                memory.update({addr+i:b for i,b in enumerate(value.to_bytes(width,'little'))})
                if handler:stores.append((addr,width))
                if addr==s['tohost']:terminals.append(r)
            elif addr in expected_loads:
                require(int(r['rd'])!=0 and all(addr+i in expected_loads for i in range(width)), 'Unobservable buffer/dump load')
                value=int(r['rd_wdata'],16)&((1<<(8*width))-1)
                memory.update({addr+i:b for i,b in enumerate(value.to_bytes(width,'little'))});loads.update(range(addr,addr+width))
        else:require(not rm and not wm,'Unknown memory effects')
    require(entries==3 and terminals==[retired[-1]],'Handler/terminal population differs')
    require(loads==expected_loads,'Incomplete full snapshot/input/output guard readback')
    def read(name,offset=0,width=8):
        addr=s[name]+offset;require(all(addr+i in memory for i in range(width)),'Missing signature bytes: '+name)
        return int.from_bytes(bytes(memory[addr+i] for i in range(width)),'little')
    p.signatures(read,s);require(read('tohost')==1,'NonPASS terminal')
    allowed=Counter({(s['gmr_ledger']+i*8,8):1 for i in range(36)});allowed[s['gmr_traps'],8]=3
    require(Counter(stores)==allowed,'Handler39-word footprint differs')
    return dict(checks=4229,snapshots=7,illegal_traps=3,handler_store_words=39,observed_vrf_bytes=28672,
                vrf_guard_bytes=3584,memory_buffer_bytes=864,explicit_read_bytes=len(expected_loads),
                prefault_vtypes=p.VTYPES,prefault_vls=p.VLS,context_restored=True,failed_checks=0)


def tracer_exact(text,rows,s):
    regex=re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual=[m.groups() for line in text.splitlines() if (m:=regex.match(line))]
    wanted=[(str(int(r['cycle'])),'M',r['pc'],r['insn']) for r in rows if r['event']=='retire']
    require(wanted and actual[:len(wanted)]==wanted,'Full tracer/scalar prefix differs')
    tail=actual[len(wanted):]
    require(not tail or tail==[(wanted[-1][0],'M','%016x'%(int(wanted[-1][2],16)+4),'0000a001')],'Postterminal tracer tail')
    events=re.findall(r'Exception @\s*([0-9a-fA-F]+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)',text)
    require(len(events)==text.count('Exception @')==3 and [(int(e[1],16),e[2]) for e in events]==
            [(s['gmr_bad_%02d'%n],'Illegal Instruction') for n in range(3)] and
            [int(v,16) for v in re.findall(r'tval: ([0-9a-fA-F]+)',text)]==p.BAD_WORDS,'Precise3 PC/cause/tval differs')
    return dict(illegal_exceptions=3,cause=2,pcs=[s['gmr_bad_%02d'%n] for n in range(3)],tvals=p.BAD_WORDS)


def vector_exact(result,control,reference,s):
    fixed=dict(status='PASS',compared_instructions=35,skipped_unknown_bytes=0,non_bit_exact_instructions=0,
               nr_lanes=4,vlen_bits=1024,selected_index=None,stopped_at_spike_index=None,
               trapped_requests=control['rejected_arch_seqs'],first_mismatch=None,unobservable_instructions=0,
               incomplete_requests=[],unretired_requests=[])
    for k,v in fixed.items():require(k in result and type(result[k]) is type(v) and result[k]==v,'Full vector gate differs: '+k)
    records=result['instructions'];expected=[(c.pc,c.instruction) for c in reference if c.vector_writes]
    require(len(records)==len(expected)==35 and [(int(r['pc'],16),int(r['instruction'],16)) for r in records]==expected,'Vector identity/population differs')
    require(all(r['compared_bytes']==128 for r in records[:32]) and
            all(records[32+n]['compared_bytes']>=width for n,width in enumerate((4,32,4))) and
            result['compared_bytes']==sum(r['compared_bytes'] for r in records),'Incomplete vector bytes')
    require(all(r['status']=='PASS' and r['skipped_unknown_bytes']==r['unknown_write_bytes']==r['mismatch_count']==0 and
                r['first_mismatch'] is None for r in records),'Vector byte mismatch/unknown')
    for n,r in enumerate(records[-3:]):
        owner=next(x for x in control['legal_operations'] if x['name']=='gmr_load_%d'%n)
        require(r['arch_seq']==owner['arch_seq'] and int(r['pc'],16)==s['gmr_load_%d'%n],'Shared opcode legal arch identity differs')


def target_hits(before,single,targets):
    require(single['tests']==[str(RUN/'code.vdb')] and str(RUN/'code.vdb') not in before['tests'],'Duplicate candidate VDB')
    hits=[]
    for t in targets:
        metric,scope,i=t['metric'],t['scope'],t['point']['raw_index']
        a,b=before['metrics'][metric][scope],single['metrics'][metric][scope]
        require((a['width'],a['checksum'])==(b['width'],b['checksum'])==(t['bitmap_width'],t['metric_checksum']),'Target shape drift')
        bit=1<<(a['width']-1-i);require(not int(a['bits'],16)&bit,'Not zero in722')
        hits.append(dict(metric=metric,scope=scope,point=t['point'],hit721=False,hit722=False,hit_single=bool(int(b['bits'],16)&bit),
                         upper_candidate=t['expected_case']==2,lower_status='PROTECTED_HOLD_NOT_QUALIFIED' if t['expected_case']!=2 else None))
    qualified=sum(h['upper_candidate'] and h['hit_single'] for h in hits)==2 and not any(
        not h['upper_candidate'] and h['hit_single'] for h in hits)
    return hits,qualified


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh prepare directory')
    path=RUN.with_name(RUN.name+'.prepared.json');prepared=life.read_bound(path,RUN_SEAL)
    pre=life.read_bound(runner.PRE/'preflight-manifest.json',PRE_SEAL);runner.validate(pre)
    require(prepared['command']==runner.command(RUN) and prepared['timeout_s']==1200 and
            prepared['output']==str(RUN) and prepared['preflight_seal']==PRE_SEAL,'Prepared binding differs')
    paths=[Path(__file__).resolve(),Path(__file__).with_name('test_collect_memory_emul_r2_strict.py'),
           Path(bitmap.__file__).resolve(),*sorted((life.ROOT/'verification/ara_verify').glob('*.py'))]
    pins=life.merge_pins(prepared['pins'],{str(path):RUN_SEAL})
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    pins=life.merge_pins(pins,base['output_pins'])
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL})
    pins=life.merge_pins(pins,{str(path):life.digest(path) for path in paths});life.check(pins)
    bits=json.loads((BASE/'combined-bits.json').read_text())
    require(len(bits['tests'])==len(set(bits['tests']))==722 and
            (BASE/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*bits['tests']],'722 membership/order differs')
    for t in pre['targets']:
        r=bits['metrics'][t['metric']][t['scope']]
        require((r['width'],r['checksum'])==(t['bitmap_width'],t['metric_checksum']) and
                not int(r['bits'],16)&(1<<(r['width']-1-t['point']['raw_index'])),'722 target shape/zero drift')
    plan=dict(status='R2_STRICT_COLLECTOR_PREPARED_NOT_EXECUTED',run=str(RUN),baseline=str(BASE),baseline_tests=722,
              preflight_seal=PRE_SEAL,prepared_run_seal=RUN_SEAL,pins=pins,targets=pre['targets'],reference_counts=pre['reference_counts'],
              coverage_admitted=False,simulations_started=False,exclusions_generated=False,
              baseline_policy='Diagnostic722 only; formal admission requires latest authorized base prefix/dedup/new delta.',
              parent_run_binding='PARENT_AGENT_PREPARED_ACTUAL_EXECUTION_DIRECTORY_NOT_THIS_AGENT_OLD_PREPARED')
    out.mkdir();life.save(out/'plan.json',plan)
    print(json.dumps(dict(plan=str(out/'plan.json'),seal=life.digest(out/'plan.json'),pins=len(pins))))


def collect(plan_path,seal,out):
    plan=life.read_bound(plan_path,seal);life.check(plan['pins'])
    require(plan['status']=='R2_STRICT_COLLECTOR_PREPARED_NOT_EXECUTED' and plan['run']==str(RUN) and
            plan['baseline']==str(BASE),'Plan binding differs')
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh audit directory')
    require((RUN/'simulation-status.json').is_file(),'HOLD no terminal status; audit not started')
    pins=life.merge_pins(plan['pins'],{str(plan_path):seal})
    def read(path):
        path=Path(path).absolute();require(path.resolve()==path and not path.is_symlink(),'Aliased evidence')
        pins.update(life.merge_pins(pins,{str(path):life.digest(path)}));return path.read_bytes()
    out.mkdir()
    try:
        state=json.loads(read(RUN/'simulation-status.json'))
        prepared=life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),RUN_SEAL)
        terminal(state,json.loads(read(RUN/'manifest.json')),prepared)
        pre=life.read_bound(runner.PRE/'preflight-manifest.json',PRE_SEAL);runner.validate(pre)
        require(plan['targets']==pre['targets'] and plan['reference_counts']==pre['reference_counts'],'Plan oracle gate drift')
        before=json.loads(read(BASE/'combined-bits.json'))
        require(len(before['tests'])==len(set(before['tests']))==722 and
                read(BASE/'combined-inputs.txt').decode().splitlines()==[str(DESIGN),*before['tests']],'722 full prefix/order differs')
        rows=common.read_csv(read(RUN/'commit_trace.csv'),common.COMMIT_FIELDS)
        vectors=common.read_csv(read(RUN/'vector_trace.csv'),common.VECTOR_FIELDS)
        console,log=read(RUN/'console.log').decode(),read(RUN/'run.vcs.log').decode()
        tracer=read(RUN/'trace_hart_0.log').decode();read(RUN/'trace_hart_0_commit.log')
        for path in sorted((RUN/'code.vdb').rglob('*')):
            if path.is_file():read(path)
        control=lifecycle(rows,vectors,pre['symbols']);data=observed(rows,pre['symbols']);trap=tracer_exact(tracer,rows,pre['symbols'])
        contracts=re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',console)
        require(len(contracts)==1 and tuple(map(int,contracts[0]))==(control['requests'],control['responses'],3,0,0) and
                not common.check_contract_log(RUN/'run.vcs.log'),'Contract/conservation differs')
        require(log.count('Core Test *** SUCCESS ***')==1,'Missing software SUCCESS')
        scalar=common.spike_trace.compare_commit_prefix(runner.PRE/'spike.trace',RUN/'commit_trace.csv',0x80000000,
                    terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar,plan['reference_counts'])
        reference=p.old.shared.parse_spike_commits(runner.PRE/'spike.trace')
        vector=common.compare_vector_commits(runner.PRE/'spike.trace',RUN/'commit_trace.csv',RUN/'vector_trace.csv',0x80000000)
        vector_exact(vector,control,reference,pre['symbols']);life.check(pins)
        with (out/'diagnostic-inputs.txt').open('x') as stream:stream.write(str(DESIGN)+'\n'+str(RUN/'code.vdb')+'\n')
        single=bitmap.collect(out/'diagnostic-inputs.txt');pins=life.merge_pins(pins,single['input_hashes'])
        hits,qualified=target_hits(before,single,pre['targets']);proposed=bitmap.combine(before,single);delta=bitmap.delta(before,proposed)
        life.check(pins)
        for name,value in [('scalar-comparison.json',scalar),('vector-comparison.json',vector),('observed-signatures.json',data),
                           ('lifecycle.json',control),('trap-proof.json',trap),('single-raw-bits.json',single),
                           ('raw-union.proposed.json',proposed),('raw-bitmap-delta.json',delta),('target-hits.json',hits),('evidence-pins.json',pins)]:
            life.save(out/name,value)
        outputs={str(path):life.digest(path) for path in out.iterdir() if path.is_file()}
        status=dict(status='R2_STRICT_UPPER_CANDIDATE_VERIFIED_NOT_ADMITTED' if qualified else
                    'R2_STRICT_ARCHITECTURE_PASS_TARGET_HOLD_NOT_ADMITTED',pins=life.merge_pins(pins,outputs),
                    baseline_tests=722,candidate_tests=1,new_admitted=0,raw_delta=delta['metrics'],upper_targets_qualified=qualified,
                    lower_targets_qualified=False,coverage_admitted=False,rtl_changed=False,simulations_started=False,
                    exclusions_generated=False,official_DVE_report=False,baseline_policy=plan['baseline_policy'])
        life.save(out/'status.json',status)
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'status.json'),status=status['status'],raw_delta=delta['metrics'])))
    except Exception as error:
        for path in sorted(RUN.rglob('*')):
            if path.is_file() and not path.is_symlink() and path.resolve()==path and str(path) not in pins:pins[str(path)]=life.digest(path)
        drift=None
        try:life.check(pins)
        except Exception as e:drift=str(e)
        life.save(out/'failure.json',dict(status='STRICT_AUDIT_FAIL_NOT_ADMITTED',reason=str(error),pin_error=drift,pins=pins,
                                        coverage_admitted=False,rtl_changed=False,simulations_started=False,retry_performed=False))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','verify','collect'))
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--seal');a=parser.parse_args()
    if a.mode=='prepare':
        require(a.output and not a.plan and not a.seal,'Prepare arguments');prepare(a.output.absolute())
    else:
        require(a.plan and a.seal,'Sealed plan required')
        if a.mode=='verify':
            require(not a.output,'Read-only verify');plan=life.read_bound(a.plan,a.seal);life.check(plan['pins'])
            print('VERIFY_PASS R2_STRICT_COLLECTOR NOT_EXECUTED_NOT_ADMITTED')
        else:
            require(a.output,'Fresh audit output required');collect(a.plan.absolute(),a.seal,a.output.absolute())


if __name__=='__main__':main()
