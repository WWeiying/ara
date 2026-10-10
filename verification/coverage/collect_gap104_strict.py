"""Terminal parent GAP104 evidence and exact721 raw diagnostic, no admission or EDA."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

import run_gap104_simulation as runner
import collect_gap103_strict as shared
from ara_verify.vector_commit import VectorWrite, _architectural_bytes, _write_data

life, proof, require = runner.life, runner.proof, runner.proof.require
bitmap = shared.bitmap
RUN = life.OUT/'gap104-whole-nf-reserved-old-image-parent-20261006-01'
PREPARED_SEAL = '294f161ac541db2b366717e6349e640526266eef7ff32d0c68488b95cc824ea0'
BASE = life.OUT/'akv-column-boundary-offline-admitted-721-20261006-01'
BASE_SEAL = 'eda7720583e3232e97cd4486d7790a678abc108018f6acbd56d0b1c287e20c8b'
DESIGN = shared.DESIGN
SCALAR_COUNTS = dict(matched_instructions=22479,matched_scalar_writes=12107,
                     matched_floating_writes=0,matched_scalar_memory_accesses=2629)


def lifecycle(rows,vectors):
    starts,pending,uops={}, {}, {}
    requests,replies,rejected=[],[],[]
    allocations,completions=Counter(),Counter()
    for row in rows:
        event,tid,seq=row['event'],int(row['trans_id']),int(row['order'])
        insn=int(row['insn'],16)
        require(insn not in (0xe2050827,0x22050fa7),'Original GAP101 phase mixed')
        if event=='arch_start':
            require(seq not in starts and tid not in pending,'Duplicate start/live transaction')
            starts[seq]=row;pending[tid]=[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1],'Unknown/duplicate request')
            arch=pending[tid][0]
            require(insn==int(starts[arch]['insn'],16) and int(row['cycle'])>=int(starts[arch]['cycle']),
                    'Request identity/time differs')
            pending[tid][1]=True;requests.append(arch)
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1],'Unknown/duplicate response')
            require(insn==0 and int(row['pc'],16)==0 and seq==-1 and int(row['trap']) in (0,1),
                    'Frozen response placeholder differs')
            arch=pending.pop(tid)[0];replies.append(arch)
            require(int(row['cycle'])>=int(starts[arch]['cycle']),'Response before start')
            if int(row['trap']):rejected.append(arch)
        elif event in ('uop_alloc','uop_done'):
            require(seq in starts and insn==int(starts[seq]['insn'],16),'Unowned/opcode-mismatched backend activity')
            key=(seq,int(row['port']))
            require(int(row['cycle'])>=int(starts[seq]['cycle']),'Backend before start')
            if event=='uop_alloc':
                require(key not in uops,'VID reused before done');uops[key]=row;allocations[key]+=1
            else:
                require(key in uops and int(row['cycle'])>=int(uops[key]['cycle']),'Unallocated/premature completion')
                uops.pop(key);completions[key]+=1
        else:require(event=='retire' and not int(row['trap']),'Unknown event/trapped retirement')
    require(not pending and Counter(requests)==Counter(starts.keys())==Counter(replies),'CVX conservation differs')
    require(not uops and allocations==completions,'Incomplete backend')
    bad=[seq for seq,row in starts.items() if int(row['insn'],16) in proof.WORDS]
    require(len(bad)==2 and [int(starts[seq]['insn'],16) for seq in bad]==list(proof.WORDS) and rejected==bad,
            'Exact two illegal requests/responses differ')
    require(not any(seq in bad for seq,_ in allocations),'Rejected instruction allocated backend uop')
    va,vd=Counter(),Counter();pending,last_done={},{}
    for row in vectors:
        require(int(row['nr_lanes'])==4 and int(row['vlen_bits'])==1024,'Vector configuration differs')
        if row['event']=='config':continue
        seq,event=int(row['arch_seq']),row['event'];key=(seq,int(row['vid']))
        require(seq in starts and seq not in bad and event in ('alloc','done','write'),'Unowned/rejected vector activity')
        require(int(row['insn'],16)==int(starts[seq]['insn'],16),'Vector opcode identity differs')
        if event=='alloc':
            require(key not in pending and int(row['cycle'])>=int(starts[seq]['cycle']),'Invalid vector allocation')
            pending[key]=row;va[key]+=1
        else:
            alloc=pending.get(key)
            if alloc is None:
                alloc=last_done.get(key)
                require(event=='write' and alloc is not None and int(row['cycle'])==int(alloc['cycle']),
                        'Vector outside allocated/completing uop')
            require(int(row['cycle'])>=int(alloc['cycle']) and all(row[k]==alloc[k] for k in
                    ('insn','use_vd','vd','eew','vl','vstart')),'Vector metadata/time differs')
            if event=='done':pending.pop(key);last_done[key]=row;vd[key]+=1
    require(not pending and va==vd==allocations,'Commit/vector lifecycle differs')
    return dict(requests=len(requests),responses=len(replies),exceptions=2,exception_arch_seqs=bad,
                backend_uops=sum(allocations.values()),rejected_backend_uops=0,rejected_vrf_activities=0,
                arch_start_pc_is_monitor_placeholder=True)


def observed(rows,symbols):
    retired=[r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retired]==list(range(len(retired))),'Retirement prefix incomplete')
    badpcs=[symbols['g104_bad_a'],symbols['g104_bad_b'],symbols['trap_fail']]
    require(not any(int(r['trap']) or int(r['pc'],16) in badpcs or int(r['insn'],16) in proof.WORDS
                    for r in retired),'Illegal instruction/unexpected trap retired')
    memory={}
    for row in retired:
        store=shared.scalar_store(row)
        if store:
            address,data=store;memory.update({address+i:v for i,v in enumerate(data)})
    def value(name,offset=0,size=8):
        address=symbols[name]+offset
        require(all(address+i in memory for i in range(size)),'Unobserved byte: '+name)
        return int.from_bytes(bytes(memory[address+i] for i in range(size)),'little')
    for (name,offset),expected in proof.expected_words().items():
        require(value(name,offset)==expected,'Canonical VRF/guard/CSR/recovery differs: %s+%d'%(name,offset))
    ledgers=[]
    for phase in range(2):
        ledger=[value('g104_ledger',phase*80+i*8) for i in range(8)]
        require(ledger==[2,symbols['g104_bad_a' if phase==0 else 'g104_bad_b'],proof.WORDS[phase],1,0,0,0,phase+1],
                'Precise trap ledger differs');ledgers.append(ledger)
    restored=[value('g104_restore',i*8) for i in range(4)]
    require(restored[0]==restored[1] and restored[2]==restored[3],'Handler CSR restoration differs')
    require(value('g75_result',size=4)==1309 and value('g75_result',4,4)==value('num_failed',size=4)==0 and
            value('tohost')==1,'1309 checks failed')
    terminal=[r for r in retired if int(r['mem_addr'],16)==symbols['tohost'] and int(r['mem_wmask'],16)]
    require(len(terminal)==1 and terminal[0]==retired[-1],'Missing/duplicate/post-terminal retire')
    return dict(checks=1309,failed_checks=0,illegal_traps=2,trap_ledgers=ledgers,restored_handler_csrs=restored,
                unchanged_vrf_bytes=8192,target_guard_bytes=1024,recovery_guard_bytes=1024,
                full_recovery_csr_words=10,complete_retirement_rows=len(retired))


def tracer_exact(text,rows,symbols):
    pattern=re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual=[m.groups() for line in text.splitlines() if (m:=pattern.match(line))]
    expected=[(str(int(r['cycle'])),'M',r['pc'],r['insn']) for r in rows if r['event']=='retire']
    require(expected and actual[:len(expected)]==expected,'Independent tracer prefix differs')
    tail=actual[len(expected):]
    require(not tail or tail==[(expected[-1][0],'M','%016x'%(int(expected[-1][2],16)+4),'0000a001')],
            'Unknown tracer tail')
    events=re.findall(r'Exception @\s*(\d+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)',text)
    require(len(events)==text.count('Exception @')==2 and
            [(int(e[0],16),e[2]) for e in events]==[(symbols[name],'Illegal Instruction')
                 for name in ('g104_bad_a','g104_bad_b')] and
            re.findall(r'tval: ([0-9a-fA-F]+)',text)==['%016x'%word for word in proof.WORDS],
            'Independent exact exception identity differs')
    return dict(exception_pcs=[hex(symbols[name]) for name in ('g104_bad_a','g104_bad_b')],
                causes=[2,2],tvals=[hex(w) for w in proof.WORDS],tracer_tail=tail)


def transport_exact(rows):
    pending,last_done={},{};groups=[]
    for number,row in enumerate(rows):
        if row['event']=='config':continue
        key=(int(row['arch_seq']),int(row['vid']));event=row['event']
        if event=='alloc':
            require(key not in pending,'Duplicate transport allocation')
            pending[key]=dict(alloc=row,writes=[],done=False);groups.append(pending[key])
        elif event=='done':
            require(key in pending,'Unknown transport done')
            item=pending.pop(key);item['done']=True;last_done[key]=item
        elif event=='write':
            item=pending.get(key) or last_done.get(key)
            require(item is not None,'Unowned physical write')
            data,known=_write_data(row['wdata']);be=int(row['be'],16)
            require(0<=be<=255 and 0<=int(row['lane'])<4 and not be&~known,'Unknown/invalid granted byte')
            if be:
                alloc=item['alloc'];reg=int(alloc['vd']);insn=int(alloc['insn'],16)
                require(tuple(int(alloc[k]) for k in ('use_vd','eew','vl','vstart'))==(1,0,128,0) and
                        insn==(0x5e02c057|(reg<<7)),'Non-initialization VRF write')
                w=VectorWrite(row=number,cycle=int(row['cycle']),arch_seq=key[0],vid=key[1],
                    lane=int(row['lane']),source=int(row['source']),instruction=int(row['insn'],16),
                    eew=int(row['eew']),addr=int(row['addr']),be=be,data=data,known_be=known)
                for (rd,byte),(value,_) in _architectural_bytes([w],4,1024).items():
                    require(rd==reg and value==0x40+reg,'Canonical initialization granted byte differs')
                item['writes'].append(w)
        else:require(False,'Unknown transport event')
    require(not pending,'Incomplete transport')
    records=[]
    for item in groups:
        require(item['done'],'Missing transport completion')
        if not item['writes']:continue
        alloc=item['alloc'];actual=_architectural_bytes(item['writes'],4,1024);reg=int(alloc['vd'])
        require(set(actual)=={(reg,b) for b in range(128)},'Missing initialization byte')
        records.append(dict(arch_seq=int(alloc['arch_seq']),instruction='0x%08x'%int(alloc['insn'],16),
                            register=reg,compared_bytes=128,uops=1,write_events=len(item['writes'])))
    require(len(records)==64 and Counter(r['register'] for r in records)==Counter({r:2 for r in range(32)}) and
            len({r['arch_seq'] for r in records})==64,'Wrong physical initialization population')
    return dict(status='ALL_GRANTED_BYTES_CANONICAL_EXACT',records=records,unknown_bytes=0,
                compared_bytes=8192,skipped_bytes=0,physical_traffic_inferred_from_spike=False)


def vector_exact(result,control,transport):
    fixed=dict(status='PASS',compared_instructions=64,compared_bytes=8192,skipped_unknown_bytes=0,
        non_bit_exact_instructions=0,unobservable_instructions=0,nr_lanes=4,vlen_bits=1024,
        selected_index=None,stopped_at_spike_index=None,trapped_requests=control['exception_arch_seqs'],
        incomplete_requests=[],unretired_requests=[],first_mismatch=None)
    require(transport['status']=='ALL_GRANTED_BYTES_CANONICAL_EXACT' and transport['unknown_bytes']==0,
            'Missing transport oracle')
    for key,value in fixed.items():
        require(key in result and type(result[key]) is type(value) and result[key]==value,'Exact vector differs: '+key)
    records=result.get('instructions',[])
    require(len(records)==64,'Missing per-record vector evidence')
    for row,actual in zip(records,transport['records']):
        fields=dict(status='PASS',unknown_write_bytes=0,mismatch_count=0,first_mismatch=None,
            skipped_unknown_bytes=0,compared_bytes=128,arch_seq=actual['arch_seq'],instruction=actual['instruction'],
            uops=actual['uops'],write_events=actual['write_events'])
        require(all(k in row and type(row[k]) is type(v) and row[k]==v for k,v in fields.items()),
                'Per-record exact vector differs')


def measure_targets(before,single,targets):
    hits=[]
    for target in targets['targets']:
        metric,scope,index=target['metric'],target['scope'],target['point']['raw_index']
        a,b=before['metrics'][metric][scope],single['metrics'][metric][scope]
        require((a['width'],a['checksum'])==(b['width'],b['checksum'])==(target['width'],target['checksum']),
                'Latest target shape differs')
        bit=1<<(a['width']-1-index)
        oldhit,newhit=bool(int(a['bits'],16)&bit),bool(int(b['bits'],16)&bit)
        hits.append(dict(metric=metric,scope=scope,raw_index=index,hit_before=oldhit,hit_single=newhit,
                         fresh_latest_hit=newhit and not oldhit))
    return hits


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args(argv).output.absolute()
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh direct output required')
    out.mkdir();pins={}
    def read(path,expected=None):
        path=Path(path).absolute();require(path.resolve()==path and not path.is_symlink(),'Aliased evidence')
        raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        require(expected is None or digest==expected,'Expected evidence hash differs: '+str(path))
        pins.update(life.merge_pins(pins,{str(path):digest}));return raw
    try:
        prepared=json.loads(read(RUN.with_name(RUN.name+'.prepared.json'),PREPARED_SEAL))
        runtime=json.loads(read(RUN/'manifest.json'))
        require(runtime==prepared and runtime['case']==runner.NAME and runtime['command']==runner.command(RUN) and
                runtime['timeout_s']==600 and runtime['old_image_files_checked']==66,'Frozen parent run differs')
        runner.validate(runtime['preflight']);pins.update(life.merge_pins(pins,runtime['pins']));life.check(pins)
        terminal=json.loads(read(RUN/'simulation-status.json'))
        require(terminal['status']=='SIMULATION_EXITED_NOT_ADMITTED' and terminal['returncode']==0 and
                terminal['case']==runner.NAME and terminal['coverage_admitted'] is False,'Not terminal SUCCESS')
        admission=json.loads(read(BASE/'admission-manifest.json',BASE_SEAL))
        base_raw={p:read(p,h) for p,h in admission['output_pins'].items()}
        require(all(Path(p).parent==BASE for p in admission['output_pins']),'Foreign baseline product')
        before=json.loads(base_raw[str(BASE/'combined-bits.json')]);state=json.loads(base_raw[str(BASE/'status.json')])
        require(state['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and state['aggregate_passed']==721 and
                len(before['tests'])==len(set(before['tests']))==721,'Wrong formal721 population')
        require(base_raw[str(BASE/'combined-inputs.txt')].decode().splitlines()==[str(DESIGN),*before['tests']],
                'Exact721 membership/order differs')
        pins.update(life.merge_pins(pins,json.loads(base_raw[str(BASE/'evidence-pins.json')])));life.check(pins)
        pre=runtime['preflight'];commits=proof.s.parse_spike_commits(Path(pre['input_spike_trace']))
        require(proof.validate(commits,pre['symbols'],read(pre['input_spike_trace']).decode())==pre['validation'],
                'Independent sealed Spike reference differs')
        counts=shared.reference_counts(commits,pre['symbols']);require(counts==SCALAR_COUNTS,'Reference scalar counts differ')
        rows=list(csv.DictReader(io.StringIO(read(RUN/'commit_trace.csv').decode())))
        vectors=list(csv.DictReader(io.StringIO(read(RUN/'vector_trace.csv').decode())))
        control=lifecycle(rows,vectors);data=observed(rows,pre['symbols'])
        traps=tracer_exact(read(RUN/'trace_hart_0.log').decode(),rows,pre['symbols'])
        for name,obj in (('lifecycle.json',control),('observed-data.json',data),('trap-ledger.json',traps)):
            life.save(out/name,obj)
        console=read(RUN/'console.log').decode();log=read(RUN/'run.vcs.log').decode()
        contracts=re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',console)
        require(len(contracts)==1 and tuple(map(int,contracts[0]))==(control['requests'],control['responses'],2,0,0) and
                not shared.check_contract_log(RUN/'run.vcs.log') and log.count('Core Test *** SUCCESS ***')==1,
                'Contract/software SUCCESS differs')
        scalar=shared.spike_trace.compare_commit_prefix(Path(pre['input_spike_trace']),RUN/'commit_trace.csv',0x80000000,
            terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        life.save(out/'scalar-comparison.json',scalar);shared.scalar_exact(scalar,counts)
        vector=shared.compare_vector_commits(Path(pre['input_spike_trace']),RUN/'commit_trace.csv',RUN/'vector_trace.csv',0x80000000)
        life.save(out/'vector-comparison.json',vector)
        transport=transport_exact(vectors);life.save(out/'transport-byte-audit.json',transport);vector_exact(vector,control,transport)
        targets=json.loads(read(runner.PRE/'target-before.json'))
        require(targets==proof.target_evidence(),'Frozen720 source/shape target evidence differs')
        for path in sorted((RUN/'code.vdb').rglob('*')):
            if path.is_file():read(path)
        for path in (Path(__file__).resolve(),Path(__file__).with_name('test_collect_gap104_strict.py'),
                     *sorted((proof.ROOT/'verification/ara_verify').glob('*.py'))):read(path)
        for module in tuple(sys.modules.values()):
            filename=getattr(module,'__file__',None)
            if filename and str(proof.ROOT/'verification') in filename:read(Path(filename).resolve())
        life.check(pins)
        with (out/'diagnostic-inputs.txt').open('x') as stream:stream.write(str(DESIGN)+'\n'+str(RUN/'code.vdb')+'\n')
        single=bitmap.collect(out/'diagnostic-inputs.txt')
        require(single['tests']==[str(RUN/'code.vdb')] and str(RUN/'code.vdb') not in before['tests'],'Wrong/duplicate single VDB')
        union=bitmap.combine(before,single);delta=bitmap.delta(before,union);hits=measure_targets(before,single,targets)
        qualified=all(h['hit_single'] for h in hits) and any(h['fresh_latest_hit'] for h in hits)
        life.check(pins)
        for name,obj in (('single-raw-bits.json',single),('raw-union.proposed.json',union),('raw-bitmap-delta.json',delta),
                         ('target-hits.json',hits),('evidence-pins.json',pins)):life.save(out/name,obj)
        life.save(out/'status.json',dict(status='GAP104_STRICT_CANDIDATE_NOT_ADMITTED' if qualified else
            'GAP104_ARCHITECTURE_PASS_TARGET_NOT_FRESH_NOT_ADMITTED',architecture_oracle_pass=True,
            baseline_tests=721,static_target_baseline_tests=720,coverage_candidate_qualified=qualified,
            target_hit_verified=all(h['hit_single'] for h in hits),fresh_target_gain_verified=qualified,
            coverage_admitted=False,aggregate_admission=False,official_DVE_report=False,rtl_changed=False,
            simulations_started=False,raw_delta=delta['metrics']))
    except Exception as error:
        if not (out/'evidence-pins.json').exists():life.save(out/'evidence-pins.json',pins)
        life.save(out/'failure.json',dict(status='GAP104_COLLECTOR_REJECTED_NOT_ADMITTED',reason=str(error),
                                        coverage_admitted=False,simulations_started=False));raise


if __name__=='__main__':main()
