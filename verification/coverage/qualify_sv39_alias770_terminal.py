"""Offline S-mode alias qualification; no simulator launch or admission."""
import argparse
from collections import Counter, defaultdict, deque
import json
from pathlib import Path
import re
import subprocess
from types import FunctionType

import run_sv39_rvv_alias770_bounded as runner
import run_sv39_rvv_alias770 as run
import collect_opivx_vsbc_strict as common
import audit_gap115_axi_v2 as wave
import coverage_bitmap_delta as bitmap
import audit_toggle_stimulus769 as toggle
from ara_verify import vector_commit as vc
from ara_verify.contract import parse_contract_summary

life, require = run.life, run.require
RUN = life.OUT / 'sv39-rvv-alias-smode-old-image770-agent-20261007-02'
RUN_SEAL = '09197a827b1f674d1e3f220bc2083715a57d8fbf250cb097e771b9b89ee8f037'
ROOT = wave.ROOT
FIFO = 'i_vlsu.i_vstu.i_store_b_metadata.'
WIDTHS = dict(clk_i=1, rst_ni=1, acc_mmu_en_q=1)
WIDTHS.update({FIFO+k: v for k,v in dict(push_i=1,full_o=1,flush_i=1,
    write_pointer_q=4,**{'data_i.slot':2,'data_i.vaddr':128,'data_i.elem_start':11}).items()})
for prefix, fields in (
    ('axi_req_o.', {'aw_valid':1,'w_valid':1,'b_ready':1,'ar_valid':1,'r_ready':1,
        'aw.id':4,'aw.addr':64,'aw.len':8,'aw.size':3,'aw.burst':2,
        'w.data':128,'w.strb':16,'w.last':1,'ar.id':4,'ar.addr':64,'ar.len':8,
        'ar.size':3,'ar.burst':2}),
    ('axi_resp_i.', {'aw_ready':1,'w_ready':1,'b_valid':1,'b.id':4,'b.resp':2,
        'ar_ready':1,'r_valid':1,'r.id':4,'r.data':128,'r.resp':2,'r.last':1}),
    ('i_vlsu.i_addrgen.axi_addrgen_req_o.', {'vaddr':128,'elem_start':16})):
    WIDTHS.update({prefix+k:v for k,v in fields.items()})


def scalar_exact(result, reference, symbols):
    expected = common.reference_counts(reference,symbols)
    # ECALL is an RVFI trap event, not a Spike committed instruction.
    fixed = dict(status='TERMINAL_TOHOST_MATCH', rvfi_store_data_layout='unshifted',
        skipped_unobservable_register_values=0, stopped_at_unobservable=None,
        aligned_vector_faults=[], ara_trap_events=48, mismatch=None, terminal_ecall=None,
        ara_retired_instructions=expected['matched_instructions']+48,
        ara_committed_instructions=expected['matched_instructions'])
    fixed.update(expected)
    for k,v in fixed.items():
        require(k in result and type(result[k]) is type(v) and result[k]==v,
                'Complete scalar comparison differs: '+k)


def lifecycle(rows, vectors, symbols):
    traps = run.trap_contract(rows,symbols)
    starts, pending, current, history = {}, {}, {}, defaultdict(list)
    requested, responded, alloc, done = Counter(), Counter(), Counter(), Counter()
    previous = -1
    for r in rows:
        event, cycle, seq, tid = r['event'],int(r['cycle']),int(r['order']),int(r['trans_id'])
        require(cycle>=previous,'Commit cycle order'); previous=cycle
        if event=='arch_start':
            require(seq>=0 and seq not in starts and tid not in pending,'Duplicate architecture/transaction')
            starts[seq]=r;pending[tid]=[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1],'Unknown/duplicate request')
            owner=pending[tid][0]
            require(r['insn']==starts[owner]['insn'],'Request opcode')
            pending[tid][1]=True;requested[owner]+=1
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1] and not int(r['trap']) and seq==-1,
                    'Unknown/rejected response')
            responded[pending.pop(tid)[0]]+=1
        elif event in ('uop_alloc','uop_done'):
            vid=int(r['port'])
            require(seq in starts and 0<=vid<8 and tid==int(starts[seq]['trans_id']) and
                    r['insn']==starts[seq]['insn'],'Backend owner/SID/opcode')
            if event=='uop_alloc':
                require(vid not in current,'Live SID reuse')
                current[vid]=[seq,cycle,None];history[vid].append(current[vid]);alloc[seq,vid,cycle]+=1
            else:
                require(vid in current and current[vid][0]==seq and cycle>=current[vid][1],
                        'Unallocated/wrong owner completion')
                current.pop(vid)[2]=cycle;done[seq,vid,cycle]+=1
        else: require(event=='retire','Unknown commit event')
    require(not pending and requested==responded==Counter(starts.keys()) and not current,
            'Unfinished request/backend')
    require(Counter((s,v) for s,v,c in alloc.elements())==Counter((s,v) for s,v,c in done.elements()),
            'Backend conservation')
    va,vd,metadata=Counter(),Counter(),{}
    previous=-1
    for r in vectors:
        event,cycle,seq,vid=r['event'],int(r['cycle']),int(r['arch_seq']),int(r['vid'])
        require(cycle>=previous and int(r['nr_lanes'])==4 and int(r['vlen_bits'])==1024,'Vector configuration/order')
        previous=cycle
        if event=='config':continue
        require(seq in starts and r['insn']==starts[seq]['insn'],'Native owner/opcode')
        if event=='alloc':
            key=seq,vid,cycle
            require(key not in metadata,'Duplicate native allocation');metadata[key]=r;va[key]+=1
        else:
            require(event in ('done','write'),'Unknown native event')
            eligible=[h for h in history[vid] if h[1]<cycle]
            if not eligible:eligible=[h for h in history[vid] if h[1]==cycle]
            require(bool(eligible),'Native SID history missing');owner=eligible[-1]
            key=owner[0],vid,owner[1]
            require(owner[0]==seq and owner[1]<=cycle<=owner[2] and key in metadata,'Native current SID owner')
            require(all(r[k]==metadata[key][k] for k in ('insn','use_vd','vd','eew','vl','vstart')),
                    'Native metadata drift')
            if event=='done':vd[seq,vid,cycle]+=1
            else:require(int(r['use_vd'])==1 and 0<=int(r['source'])<5 and 0<=int(r['lane'])<4,
                         'Native write source/lane')
    require(va==alloc and vd==done,'Commit/native lifecycle mismatch')
    return dict(traps=traps,requests=sum(requested.values()),responses=sum(responded.values()),
                exceptions=0,backend_uops=sum(alloc.values()),current_SID_owner_checked=True)


def vector_exact(result, reference):
    expected=[c for c in reference if c.vector_writes]
    fixed=dict(status='PASS',compared_instructions=len(expected),compared_bytes=10624,
        skipped_unknown_bytes=0,non_bit_exact_instructions=0,nr_lanes=4,vlen_bits=1024,
        selected_index=None,stopped_at_spike_index=None,trapped_requests=[],first_mismatch=None,
        unobservable_instructions=0,incomplete_requests=[],unretired_requests=[])
    for k,v in fixed.items():
        require(k in result and type(result[k]) is type(v) and result[k]==v,'Full vector gate differs: '+k)
    records=result['instructions']
    require(len(records)==len(expected) and
        [(int(r['pc'],16),int(r['instruction'],16),r['compared_bytes']) for r in records]==
        [(c.pc,c.instruction,128*len(c.vector_writes)) for c in expected],'Full vector identity/width')
    require(all(r['status']=='PASS' and r['skipped_unknown_bytes']==r['unknown_write_bytes']==
        r['mismatch_count']==0 and r['first_mismatch'] is None for r in records),'Unknown/mismatching vector record')


def native_exact(activities, mapping, reference):
    wanted={s:reference[i] for s,i in mapping.items() if reference[i].vector_writes}
    require({s for s,a in activities.items() if a.writes}==set(wanted),'Native writer population')
    total=0
    for s,c in wanted.items():
        a=activities[s];require(a.instruction==c.instruction,'Native instruction')
        seen=set()
        for w in a.writes:
            require(w.arch_seq==s and w.instruction==c.instruction and w.be&~w.known_be==0 and
                    0<=w.source<5 and w.eew in (0,3),'Native unknown/source/EEW')
            for b in range(8):
                if w.be&(1<<b):
                    key=w.addr,w.lane,b;require(key not in seen,'Duplicate native byte');seen.add(key)
        actual=vc._architectural_bytes(a.writes,4,1024)
        expect={(r,b):(v>>(8*b))&255 for r,v in c.vector_writes.items() for b in range(128)}
        require({k:v for k,(v,_) in actual.items()}==expect,'Native full result/seed/tail differs')
        total+=len(expect)
    require(total==10624,'Native full byte population')
    return dict(known_bytes=total,writers=len(wanted),unknown_bytes=0,duplicate_bytes=0)


def observed(rows, symbols):
    retired=[r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retired]==list(range(len(retired))),'Incomplete retirement order')
    stores=Counter();reads=Counter();terminals=[]
    for r in retired:
        if int(r['trap']):continue
        insn=int(r['insn'],16);addr=int(r['mem_addr'],16)
        rm,wm=int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        access=common.scalar_memory(insn)
        if access is None:
            require(not rm and not wm,'Unmodeled scalar memory effect');continue
        kind,width=access;mask=((1<<width)-1)<<(addr&7)
        require(addr%width==0 and rm==(mask if kind=='read' else 0) and
                wm==(mask if kind=='write' else 0),'Scalar memory shape')
        if kind=='read':reads.update(range(addr,addr+width))
        else:
            require(not (symbols['alias_source']<=addr<symbols['alias_source']+40),'Immutable source modified')
            stores[addr]=int(r['mem_wdata'],16)&((1<<(width*8))-1)
            if addr==symbols['tohost']:terminals.append(r)
    require(terminals==[retired[-1]] and stores.get(symbols['tohost'])==1 and
            stores.get(symbols['num_failed'])==0 and stores.get(symbols['g75_result'])==3113 and
            stores.get(symbols['g75_result']+4)==0,'Exact terminal/failure/check signature')
    for name,size in (('alias_vrf',12384),('alias_source',40),('alias_page',4096),('alias_csr',168)):
        require(all(a in reads for a in range(symbols[name],symbols[name]+size)),
                'Missing complete raw readback: '+name)
    return dict(checks=3113,failed_checks=0,full_VRF_bytes=12288,full_page_phase_bytes=12288,
                CSR_words=21,immutable_source_bytes=40,full_guard_readback=True)


def metadata_frames(frames, codes, physical):
    def value(state,name):
        bits=state.get(codes[name],'x')
        require(set(bits)<=set('01'),'Unknown active field: '+name)
        return int(bits,2)
    aw=deque();ar=defaultdict(deque);bq=defaultdict(deque)
    records=[];loads=0;target_aw=0;active=False;previous_pointer=None;end=0
    for time,before,after in frames:
        end=time
        if before.get(codes['clk_i'])!='0' or after.get(codes['clk_i'])!='1':continue
        if before.get(codes['rst_ni'])!='1':
            require(not active,'Unexpected post-start reset');continue
        active=True
        require(value(before,FIFO+'flush_i')==0,'Unexpected metadata flush')
        pointer=value(before,FIFO+'write_pointer_q')
        if previous_pointer is not None:require(pointer==previous_pointer,'Preedge FIFO pointer drift')
        push=value(before,FIFO+'push_i');full=value(before,FIFO+'full_o')
        require(not(push and full),'Push while full')
        previous_pointer=(pointer+push)%16
        if value(before,'axi_req_o.aw_valid') and value(before,'axi_resp_i.aw_ready'):
            address=value(before,'axi_req_o.aw.addr');target=address==physical
            row=dict(id=value(before,'axi_req_o.aw.id'),address=address,
                length=value(before,'axi_req_o.aw.len')+1,received=0,target=target)
            if target:
                require(target_aw<48 and row['length']==4 and value(before,'axi_req_o.aw.size')==4 and
                        value(before,'axi_req_o.aw.burst')==1,'Target AW shape/count')
                row['phase']=target_aw//16;target_aw+=1
            aw.append(row)
        completed=None
        if value(before,'axi_req_o.w_valid') and value(before,'axi_resp_i.w_ready'):
            require(bool(aw),'Orphan W');row=aw[0]
            require(value(before,'axi_req_o.w.last')==int(row['received']==row['length']-1),'WLAST shape')
            if row['target']:
                pattern=run.reference.prior.PATTERNS[row['phase']]
                require(value(before,'axi_req_o.w.strb')==65535 and
                        value(before,'axi_req_o.w.data')==pattern|(pattern<<64),'Exact target W bytes')
            row['received']+=1
            if row['received']==row['length']:
                completed=aw.popleft();bq[completed['id']].append(completed)
        require(bool(push)==bool(completed),'FIFO push must equal accepted final W')
        if push:
            vaddr=value(before,FIFO+'data_i.vaddr')
            if completed['target']:
                phase=completed['phase']
                require(value(before,'acc_mmu_en_q')==1 and vaddr==run.reference.prior.address(phase) and
                    value(before,FIFO+'data_i.elem_start')==0 and
                    value(before,'i_vlsu.i_addrgen.axi_addrgen_req_o.vaddr')==vaddr and
                    value(before,'i_vlsu.i_addrgen.axi_addrgen_req_o.elem_start')==0,'Target translated metadata')
                records.append(dict(time_100fs=time,phase=phase,pointer=pointer,vaddr=vaddr,
                                    owner_slot=value(before,FIFO+'data_i.slot'),physical_address=physical))
            else:require(vaddr not in [run.reference.prior.address(p) for p in range(3)],'Extra alias push')
        if value(before,'axi_resp_i.b_valid') and value(before,'axi_req_o.b_ready'):
            ident=value(before,'axi_resp_i.b.id')
            require(bool(bq[ident]) and value(before,'axi_resp_i.b.resp')==0,'Orphan/error B');bq[ident].popleft()
        if value(before,'axi_req_o.ar_valid') and value(before,'axi_resp_i.ar_ready'):
            address=value(before,'axi_req_o.ar.addr');target=address==physical
            row=dict(length=value(before,'axi_req_o.ar.len')+1,received=0,target=target)
            if target:
                require(loads<48 and row['length']==4 and value(before,'axi_req_o.ar.size')==4 and
                    value(before,'axi_req_o.ar.burst')==1,'Target AR shape');row['phase']=loads//16;loads+=1
            ar[value(before,'axi_req_o.ar.id')].append(row)
        if value(before,'axi_resp_i.r_valid') and value(before,'axi_req_o.r_ready'):
            ident=value(before,'axi_resp_i.r.id');require(bool(ar[ident]),'Orphan R');row=ar[ident][0]
            require(value(before,'axi_resp_i.r.resp')==0 and
                value(before,'axi_resp_i.r.last')==int(row['received']==row['length']-1),'R response/RLAST')
            if row['target']:
                pattern=run.reference.prior.PATTERNS[row['phase']]
                require(value(before,'axi_resp_i.r.data')==pattern|(pattern<<64),'Exact target read data')
            row['received']+=1
            if row['received']==row['length']:ar[ident].popleft()
    require(active and not aw and not any(ar.values()) and not any(bq.values()) and
            target_aw==loads==len(records)==48,'Incomplete target/AXI drain')
    for phase in range(3):
        selected=[r for r in records if r['phase']==phase]
        require(len(selected)==16 and {r['pointer'] for r in selected}==set(range(16)),
                'Actual16 metadata slots per phase')
    for slot in range(16):
        require([r['vaddr'] for r in records if r['pointer']==slot]==
                [run.reference.prior.address(p) for p in range(3)],'Actual slot low/high/low sequence')
    return dict(status='ACTUAL48_TRANSLATED_PUSHES_AND_READ_WRITE_DATA_PASS',preedge_sampling=True,
                pushes=records,stores=48,loads=48,all16slots_both_virtual_directions=True,end_time_100fs=end)


def metadata(path,physical):
    parse=FunctionType(wave.vcd.__code__,dict(wave.vcd.__globals__,ROOT=ROOT,WIDTHS=WIDTHS))
    iterator=iter(parse(path));_,decl=next(iterator)
    codes={n:decl[ROOT+'.'+n]['code'] for n in WIDTHS}
    result=metadata_frames(iterator,codes,physical)
    result['field_mapping']={n:decl[ROOT+'.'+n] for n in WIDTHS}
    return result


def bound_run():
    path=RUN.with_name(RUN.name+'.prepared.json')
    prepared=life.read_bound(path,RUN_SEAL);life.check(prepared['pins'])
    require(prepared['output']==str(RUN) and prepared['command']==run.command(RUN) and
        prepared['case']==run.NAME and prepared['timeout_s']==600 and
        prepared['formal770_fixed_seal']==runner.BASE_SEAL and
        prepared['elf_sha256']==run.ELF_SEAL and prepared['preflight_seal']==run.PRE_SEAL and
        prepared['coverage_admitted'] is False and prepared['automatic_retry'] is False,'Prepared binding differs')
    return prepared


def terminal(state,actual,started,prepared):
    require(state['status']=='SIMULATION_EXITED_NOT_ADMITTED' and type(state['returncode']) is int and
        state['returncode']==0 and state['timeout'] is False and state['case']==run.NAME and
        state['coverage_admitted'] is False and state['admission_performed'] is False and
        state['terminal_oracle_verified'] is False,'Failed/nonterminal simulation')
    require(actual==dict(prepared,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL') and
        started['command']==prepared['command'] and started['budget_s']==600 and
        type(started['pid']) is int and started['pid']>0 and
        started['pid']==started['process_group']==state['pid'] and started['elf_sha256']==run.ELF_SEAL and
        started['image_sha256']==run.frozen.IMAGE_SEAL and started['input_elf']==str(run.PRE/'input.elf') and
        started['image']==str(life.IMAGE) and started['foreground_lifetime'] is True and
        started['coverage_admitted'] is False,'Runtime command/image/ELF/lifetime identity')


def logs_exact(logs,control):
    for text in logs:
        require(not re.search(r'Fatal:|Error:|Fatal-\[|Error-\[|\[ARA_CONTRACT_ERROR\]|Core Test \*\*\* FAILED',text),
                'Failure/protocol diagnostic')
        require(not re.search(r'^UVM_(?:ERROR|FATAL)\s+[^:\s]',text,re.M),'UVM error/fatal')
        require(all(int(n)==0 for n in re.findall(r'UVM_(?:ERROR|FATAL)\s*:\s*(\d+)',text)),
                'Nonzero UVM error/fatal count')
    require(logs[1].count('Core Test *** SUCCESS ***')==1,'Unique SUCCESS')
    summaries=[parse_contract_summary(line.strip()) for line in logs[0].splitlines() if '[ARA_CONTRACT]' in line]
    require(len(summaries)==1 and summaries[0] is not None,'One actual contract summary');counts=summaries[0]
    require(counts['requests']==counts['responses']==control['requests']>0 and counts['exceptions']==0 and
        all(counts[k]==0 for k in ('protocol_errors','outstanding','req_stalled','resp_stalled')),'Native protocol counts')
    return counts


def profile_exact(console):
    objects=['clk_i','rst_ni','acc_mmu_en_q','axi_req_o','axi_resp_i',
        *[FIFO+n for n in ('push_i','full_o','flush_i','write_pointer_q','data_i')],
        'i_vlsu.i_addrgen.axi_addrgen_req_o']
    lines=console.splitlines()
    require([s for s in lines if s.startswith('ALIAS_METADATA_OBJECT ')]==
        ['ALIAS_METADATA_OBJECT '+ROOT+'.'+n for n in objects] and
        lines.count('ALIAS_METADATA_PROFILE_READY_11')==1 and
        not any(s.startswith('ALIAS_METADATA_CAPTURE_ERROR') for s in lines),'Actual focused profile differs')


def tracer_exact(text,rows,symbols):
    pattern=re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual=[m.groups() for line in text.splitlines() if (m:=pattern.match(line))]
    retired=[r for r in rows if r['event']=='retire' and not int(r['trap'])]
    wanted=[(str(int(r['cycle'])),int(r['pc'],16),int(r['insn'],16)) for r in retired]
    require([(cycle,int(pc,16),int(insn,16)) for cycle,priv,pc,insn in actual[:len(wanted)]]==wanted,
            'Full tracer/nontrap retirement prefix differs')
    require(all(priv in ('M','S') for cycle,priv,pc,insn in actual),'Unexpected user privilege')
    targets=[priv for cycle,priv,pc,insn in actual if int(pc,16) in
             (symbols['alias_store_site'],symbols['alias_load_site'])]
    require(targets==['S']*96,'Actual96 target instructions must be supervisor')
    tail=actual[len(wanted):]
    require(not tail or tail==[(wanted[-1][0],'M','%016x'%(wanted[-1][1]+4),'0000a001')],
            'Unexpected tracer terminal tail')
    events=re.findall(r'Exception @\s*(\d+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)',text)
    require(len(events)==text.count('Exception @')==48 and all(int(pc,16)==symbols['alias_s_ecall'] and
        cause=='Environment Call Supervisor Mode' for time,pc,cause in events),'Exact48 tracer ECALL cause/PC')
    return dict(nontrap_retirements=len(wanted),expected_scalar_exceptions=48,target_supervisor_instructions=96)


def prepare(out):
    require(out.resolve()==out and out.parent==life.OUT and not out.exists(),'Fresh direct plan directory')
    prepared=bound_run()
    pins=life.merge_pins(prepared['pins'],{str(RUN.with_name(RUN.name+'.prepared.json')):RUN_SEAL})
    for m in (runner,run,common,wave,bitmap,toggle,toggle.t,toggle.frozen,life):
        path=Path(m.__file__).resolve();pins=life.merge_pins(pins,{str(path):life.digest(path)})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_qualify_sv39_alias770_terminal.py'),
                 toggle.frozen.CACHE):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    require(pins[str(toggle.frozen.CACHE)]==toggle.frozen.CACHE_SHA,'Cache identity')
    baseline=life.read_bound(run.BASE/'admission-manifest.json',runner.BASE_SEAL)
    pins=life.merge_pins(life.merge_pins(pins,baseline['input_pins']),baseline['output_pins'])
    life.check(pins);out.mkdir()
    record=dict(status='OFFLINE_PLAN_NOT_EXECUTED',run=str(RUN),run_seal=RUN_SEAL,
        baseline=770,baseline_seal=runner.BASE_SEAL,pins=pins,coverage_admitted=False,
        VCS_launched=False,EDA_launched=False,wave_limit_bytes=64*1024*1024)
    life.save(out/'plan.json',record);return record


def raw_gain(out):
    before=json.loads((run.BASE/'combined-bits.json').read_bytes())
    ledger=(run.BASE/'combined-inputs.txt').read_text().splitlines()
    require(before['tests']==ledger[1:] and len(ledger)==len(set(ledger))==771,'Exact770 bitmap prefix')
    with (out/'candidate-inputs.txt').open('x') as f:f.write(ledger[0]+'\n'+str(RUN/'code.vdb')+'\n')
    single=bitmap.collect(out/'candidate-inputs.txt');combined=bitmap.combine(before,single)
    four=bitmap.delta(before,combined)
    cache=json.loads(toggle.frozen.CACHE.read_bytes())
    prior=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(ledger[:742]==prior.read_text().splitlines(),'Exact cache prefix')
    life.check(cache['input_pins'])
    union={s:{k:r[k] for k in ('width','checksum','bits')} for s,r in cache['instances'].items()}
    scopes=list(union);pins={}
    for name in ledger[742:]:
        files=list((Path(name)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'One suffix Toggle data');p=files[0]
        sample,h=toggle.t.rows(p,scopes);pins[str(p)]=h;union=toggle.t.union(union,sample)
    files=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1,'One candidate Toggle data');sample,h=toggle.t.rows(files[0],scopes)
    pins[str(files[0])]=h;after=toggle.t.union(union,sample)
    gains=[]
    for s,r in union.items():
        bits=int(after[s]['bits'],16)&~int(r['bits'],16)
        if bits:gains.append(dict(scope=s,new_binary_positions=bin(bits).count('1'),
            width=r['width'],checksum=r['checksum'],positions=[i for i,c in enumerate(
            format(bits,'0%db'%r['width'])) if c=='1']))
    life.save(out/'candidate-bits.json',single);life.save(out/'combined-bits.json',combined)
    life.check(pins)
    return dict(baseline=770,four_metrics=four,toggle_binary_instances=gains,
        toggle_binary_new_positions=sum(r['new_binary_positions'] for r in gains),
        binary_scope_count=len(scopes),arrays='Not scored by this binary cache; official DVE required',
        official_percentage=None,input_pins=life.merge_pins(pins,single['input_hashes']))


def collect(plan_path,seal,out):
    plan=life.read_bound(plan_path,seal);life.check(plan['pins'])
    require(plan['run']==str(RUN) and plan['run_seal']==RUN_SEAL and
        plan['baseline_seal']==runner.BASE_SEAL,'Plan scope/baseline drift')
    require((RUN/'simulation-status.json').is_file() and out.parent==life.OUT and
            out.resolve()==out and not out.exists(),'Terminal required/fresh output')
    out.mkdir();pins=dict(plan['pins']);pins[str(plan_path)]=seal
    def read(name):
        path=RUN/name;require(path.resolve()==path and not path.is_symlink(),'Aliased evidence')
        raw=path.read_bytes();h=life.digest(path)
        import hashlib
        require(hashlib.sha256(raw).hexdigest()==h,'Evidence changed during read')
        pins[str(path)]=h;return raw
    try:
        prepared=bound_run()
        state=json.loads(read('simulation-status.json'));actual=json.loads(read('manifest.json'))
        started=json.loads(read('started.json'))
        terminal(state,actual,started,prepared)
        pre=life.read_bound(run.PRE/'preflight.json',run.PRE_SEAL)
        reference=run.reference.prior.build.parse_spike_commits(run.PRE/'spike.trace')
        require(run.reference.validate(reference,pre['symbols'])==pre['counts'],'Independent reference contract')
        run.reference.exception_gate((run.PRE/'spike.trace').read_text(),pre['symbols'])
        rows=common.read_csv(read('commit_trace.csv'),common.COMMIT_FIELDS)
        vectors=common.read_csv(read('vector_trace.csv'),common.VECTOR_FIELDS)
        control=lifecycle(rows,vectors,pre['symbols']);observations=observed(rows,pre['symbols'])
        tracer=tracer_exact(read('trace_hart_0.log').decode('utf-8'),rows,pre['symbols'])
        read('trace_hart_0_commit.log')
        logs=[read(n).decode('utf-8') for n in ('console.log','run.vcs.log')]
        counts=logs_exact(logs,control)
        scalar=run.scalar_compare(RUN/'commit_trace.csv',pre);scalar_exact(scalar['scalar'],reference,pre['symbols'])
        vector=common.compare_vector_commits(run.PRE/'spike.trace',RUN/'commit_trace.csv',RUN/'vector_trace.csv',0x80000000)
        vector_exact(vector,reference)
        starts,retires,rejected=vc._parse_architecture_mapping(RUN/'commit_trace.csv')
        require(not rejected,'Rejected vector request')
        mapping=vc._map_spike_commits(vc._map_architecture_retires(starts,retires,rejected),reference)
        lanes,vlen,activities=vc._parse_vector_trace(RUN/'vector_trace.csv')
        require((lanes,vlen)==(4,1024),'Native design');native=native_exact(activities,mapping,reference)
        profile_exact(logs[0])
        vpd=RUN/'alias-metadata.vpd'
        require(vpd.is_file() and 0<vpd.stat().st_size<=plan['wave_limit_bytes'],'VPD missing/oversized')
        pins[str(vpd)]=life.digest(vpd)
        with (out/'conversion.log').open('xb') as log:
            subprocess.run([str(run.capture.CONVERTER),'+splitpacked',str(vpd),str(out/'metadata.vcd')],
                stdout=log,stderr=subprocess.STDOUT,timeout=60,check=True)
        pins[str(out/'metadata.vcd')]=life.digest(out/'metadata.vcd')
        pins[str(out/'conversion.log')]=life.digest(out/'conversion.log')
        pushes=metadata(out/'metadata.vcd',pre['symbols']['alias_page']+64)
        gain=raw_gain(out);pins=life.merge_pins(pins,gain['input_pins']);life.check(pins)
        result=dict(status='FULL_ARCHITECTURE_TRAPS_TRANSLATION_METADATA_QUALIFIED_NOT_ADMITTED',
            baseline=770,run=str(RUN),elf_sha256=run.ELF_SEAL,scalar=scalar,vector=vector,native=native,
            lifecycle=control,tracer=tracer,protocol=counts,observations=observations,metadata=pushes,raw_gain=gain,
            coverage_admitted=False,admission_performed=False,pins=pins)
        life.save(out/'qualification.json',result);print('QUALIFIED',life.digest(out/'qualification.json'),flush=True)
        return result
    except Exception as exc:
        life.save(out/'failure.json',dict(status='FAIL_OR_HOLD_NOT_ADMITTED',error=type(exc).__name__+': '+str(exc),
            pins=pins,coverage_admitted=False,admission_performed=False))
        raise


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','verify','collect'))
    p.add_argument('--output',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--seal')
    a=p.parse_args()
    if a.action=='prepare':prepare(a.output.absolute());print('PLAN',life.digest(a.output/'plan.json'))
    elif a.action=='verify':life.check(life.read_bound(a.plan,a.seal)['pins']);print('VERIFY_PASS')
    else:collect(a.plan,a.seal,a.output.absolute())


if __name__=='__main__':main()
