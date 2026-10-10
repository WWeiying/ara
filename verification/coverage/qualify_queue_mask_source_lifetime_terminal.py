"""Offline terminal collector: exact scalar plus native-state mask-tail set proof."""
import argparse
from collections import Counter
import hashlib
import inspect
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

import run_queue_mask_source_lifetime_simulation as runner
import queue_mask_tail_vector_oracle as tail
import qualify_narrow_source_group_terminal as previous
import collect_opivx_vsbc_strict as common
import coverage_bitmap_delta as bitmap
from qualify_store_fault_flush_terminal import elf_instruction
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log,parse_contract_summary

life,require=runner.life,runner.require
STATUS='QUEUE_MASK_TERMINAL_PLAN_NOT_EXECUTED'
ELF_RETIREMENTS=96974

def reference_prefix():
    commits=runner.p.shared.parse_spike_commits(runner.PRE/'spike.log')
    counts=runner.reference_counts(commits,0x80001000)
    require(counts['matched_instructions']==96979,'Sealed complete Spike prefix differs')
    start=next(i for i,c in enumerate(commits) if c.pc==0x80000000)
    require(start==5,'Exact5 Spike boot-ROM records required')
    prefix=commits[start:96979]
    counts=common.reference_counts(prefix,json.loads((runner.PRE/'symbols.json').read_bytes()))
    require(counts['matched_instructions']==96974 and counts['matched_scalar_writes']==64696 and
            counts['matched_scalar_memory_accesses']==18624 and counts['matched_floating_writes']==0 and
            sum(len(c.memory_accesses) for c in prefix)==21386 and
            sum(len(c.memory_accesses) for c in prefix if c.instruction&127 in (7,0x27))==2762,
            'ELF-entry architectural scalar/vector memory counts differ')
    return prefix

def lifecycle(rows,vectors):
    # Exact zero-fault adaptation of the already reviewed SID interval checks.
    source=inspect.getsource(previous.lifecycle)
    recovery="""    recovered = [r for r in rows if r['event'] == 'retire' and int(r['pc'], 16) == symbols['ng_recovery']]
    require(len(recovered) == 1 and int(recovered[0]['insn'], 16) == 0x0341bc57 and not int(recovered[0]['trap']),
            'Missing exact recovery retirement')
"""
    require(source.count('for i in range(1):')==1 and source.count(recovery)==1 and
            source.count('exceptions=1')==1,'Reviewed lifecycle adapter drift')
    source=source.replace('for i in range(1):','for i in range(0):').replace(recovery,'').replace('exceptions=1','exceptions=0')
    ns=dict(previous.__dict__)
    exec(compile(source,__file__+':zero-fault-SID','exec'),ns)
    result=ns['lifecycle'](rows,vectors,{})
    require(result['requests']>0 and result['backend_uops']>0,'No backend traffic')
    return result

def native_state(reference,activities,mapping,symbols):
    state,last_write={},{}
    primary,transport,records,active,agnostic=0,0,[],0,0
    wanted={seq for seq,i in mapping.items() if reference[i].vector_writes}
    require(len(wanted)==32,'Exact32 architectural primary writer mapping required')
    require(all(seq in mapping for seq in activities),'Unmapped native request')
    for seq,i in sorted(mapping.items()):
        c=reference[i];a=activities.get(seq)
        if a is None:
            require(not c.vector_writes,'Missing primary native activity');continue
        require(a.instruction==c.instruction and a.allocations==a.completions and a.allocations>0,
                'Native opcode/incomplete allocation differs')
        tail.audit_known_writes(a.writes)
        actual=vc._architectural_bytes(a.writes,4,1024)
        if not c.vector_writes:
            if not actual:continue
            require(c.instruction&127==0x27 and all(w.source==3 for w in a.writes),
                    'Unclassified additional transport writer')
            require(all(reg in state for reg,byte in actual),'Unproved transport prestate')
            for w in a.writes:
                individual=vc._architectural_bytes([w],4,1024)
                require(all(reg in state and value==(state[reg]>>(8*byte)&255)
                            for (reg,byte),(value,owner) in individual.items()),
                        'Accepted transport byte is not logical identity')
            after=tail.apply_known_architectural_bytes(state,actual)
            tail.check_identity_transport(state,after)
            transport+=1
            records.append(dict(arch_seq=seq,pc=c.pc,opcode=c.instruction,kind='IDENTITY_TRANSPORT',
                accepted_write_events=len(a.writes),actual_tail_preserved=True))
        else:
            require(actual and a.vstart==0 and a.vl==c.vector_vl,'Missing writer/wrong native context')
            cell=next((n for n in range(8) if c.pc==symbols['qv_pair_'+str(n)]+4),None)
            if cell is not None:
                context=tail.case_context(cell)
                require(c.instruction>>26==26 and c.instruction>>12&7==4 and
                        c.instruction>>7&31==8 and c.instruction>>20&31==24 and
                        c.instruction>>25&1==1 and a.vl==context['vl'] and
                        all(w.source==2 for w in a.writes),'Exact MASKU compare identity differs')
                require(8 in last_write and last_write[8]<min(w.cycle for w in a.writes),
                        'No ordered actual native pre-v8 state')
                before=dict(state)
                after=tail.apply_known_architectural_bytes(before,actual)
                proof=tail.check_case(cell,before,after)
                active+=proof['active_bits_strict'];agnostic+=proof['tail_bits_set_checked']
                state=after;kind='MASK_COMPARE_SET_PROOF'
            else:
                opcode=c.instruction&127
                require(opcode==7 or opcode==0x57 and c.instruction>>26==32 and
                        c.instruction>>12&7==6,'Unexpected architectural vector writer')
                producer=4 if opcode==7 else 1
                require(all(w.source==producer for w in a.writes),'Wrong primary producer')
                gold={(reg,b):(value>>(8*b))&255 for reg,value in c.vector_writes.items() for b in range(128)}
                require({k:v for k,(v,w) in actual.items()}==gold,'Full load/DIV known-byte differential mismatch')
                # These actual native bytes, not a reference assignment, establish prestate.
                for reg in c.vector_writes:
                    state[reg]=int.from_bytes(bytes(actual[reg,b][0] for b in range(128)),'little')
                kind='STRICT_LOAD' if opcode==7 else 'STRICT_DIV'
            primary+=1
            records.append(dict(arch_seq=seq,pc=c.pc,opcode=c.instruction,kind=kind,
                accepted_write_events=len(a.writes),accepted_bytes=len(actual)))
        for reg,byte in actual:
            last_write[reg]=max(w.cycle for (r,b),(v,w) in actual.items() if r==reg)
    require(primary==32 and active==720 and agnostic==7472 and
            Counter(r['kind'] for r in records if r['kind']!='IDENTITY_TRANSPORT')==
            Counter(STRICT_LOAD=16,STRICT_DIV=8,MASK_COMPARE_SET_PROOF=8),'Full writer/bit population differs')
    return dict(status='FULL_NATIVE_STATE_MASK_SET_PASS',primary_writers=32,
        identity_transport_requests=transport,active_bits_strict=active,tail_bits_set_checked=agnostic,
        native_prestate_proved=True,whole_vd_skipped=False,unknown_accepted_bytes=0,
        v9_preserved=True,instructions=records)

def native(run,reference,symbols):
    lanes,vlen,activities=vc._parse_vector_trace(run/'vector_trace.csv')
    starts,retires,rejected=vc._parse_architecture_mapping(run/'commit_trace.csv')
    require((lanes,vlen)==(4,1024) and not rejected,'Wrong geometry/trapped request')
    arch=vc._map_architecture_retires(starts,retires,rejected)
    mapping=vc._map_spike_commits(arch,reference)
    require(all(arch[s].pc==reference[i].pc and arch[s].instruction==reference[i].instruction
                for s,i in mapping.items()),'Dynamic arch_seq/PC/opcode mapping differs')
    return native_state(reference,activities,mapping,symbols)

def observed(rows,symbols):
    retired=[r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retired]==list(range(ELF_RETIREMENTS)),
            'Full contiguous terminal-prefix retirements required')
    blob=runner.ELF.read_bytes();memory={};reads=set();terminals=[]
    sizes=dict(qv_source=2304,qv_div=2304,qv_vid=2304,qv_csr=192)
    ranges=[(symbols[n],symbols[n]+size) for n,size in sizes.items()]
    for r in retired:
        pc,word=int(r['pc'],16),int(r['insn'],16)
        require(word&3==3 and elf_instruction(blob,pc,4)==word and int(r['trap'])==0,
                'ELF/ISA/trap retirement differs')
        rm,wm,addr=int(r['mem_rmask'],16),int(r['mem_wmask'],16),int(r['mem_addr'],16)
        access=common.scalar_memory(word)
        if access is None:
            require(not rm and not wm,'Unexpected scalar memory effect');continue
        kind,size=access;mask=((1<<size)-1)<<(addr&7)
        require(addr%size==0 and rm==(mask if kind=='read' else 0) and
                wm==(mask if kind=='write' else 0),'Scalar memory alignment/mask differs')
        if kind=='write':
            value=int(r['mem_wdata'],16)&((1<<(8*size))-1)
            if addr==symbols['tohost']:terminals.append((r,value))
        elif any(a<=addr and addr+size<=b for a,b in ranges):
            require(int(r['rd'])!=0,'Unobservable footprint read')
            value=int(r['rd_wdata'],16)&((1<<(8*size))-1);reads.update(range(addr,addr+size))
        else:continue
        for j in range(size):memory[addr+j]=(value>>(8*j))&255
    require(len(terminals)==1 and terminals[0]==(retired[-1],1),'Terminal not exact final successful store')
    def read(name,off,size):
        addr=symbols[name]+off
        require(all(addr+j in memory for j in range(size)),'Missing signature bytes '+name)
        return bytes(memory[addr+j] for j in range(size))
    require(read('g75_result',0,4)==(6936).to_bytes(4,'little') and
            read('g75_result',4,4)==read('num_failed',0,4)==bytes(4),'Software selfchecks differ')
    for n,(sew,lmul) in enumerate(runner.p.CELLS):
        for kind in ('source','div','vid'):
            tail.software.compare_buffer(n,kind,read('qv_'+kind,n*288,288))
        values=(128*lmul//(sew//8),(sew.bit_length()-4)*8+(lmul==2),0)
        require(read('qv_csr',n*24,24)==b''.join(v.to_bytes(8,'little') for v in values),'CSR footprint differs')
    # Every buffer byte is explicitly read by the app. CSR values are stored;
    # scalar differential additionally checks all individual csrr results.
    required={a for n in ('qv_source','qv_div','qv_vid') for a in range(symbols[n],symbols[n]+sizes[n])}
    require(required<=reads,'Incomplete full buffer readback')
    return dict(checks=6936,strict_memory_bytes=6912,csr_values=24,traps=0,
                ELF_matched_retirements=len(retired),explicit_buffer_readback_bytes=len(required))

def terminal(state,actual,started,record):
    require(state.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and
            type(state.get('returncode')) is int and state['returncode']==0 and
            state.get('timeout') is False and state.get('case')==runner.NAME and
            state.get('terminal_oracle_verified') is False and state.get('coverage_admitted') is False and
            state.get('admission_performed') is False,
            'Successful exact OS terminal receipt required')
    require(actual==record and started['command']==record['command'] and
            started['input_elf']==str(runner.ELF) and started['elf_sha256']==runner.ELF_SHA and
            started['image']==str(life.IMAGE) and started['image_sha256']==runner.IMAGE_SHA and
            type(started['pid']) is int and started['pid']>0 and
            started['pid']==started['process_group']==state['pid'] and
            started['budget_s']==600 and started['foreground_lifetime'] is True and
            started['coverage_admitted'] is False,
            'Actual launch identity differs')
    require(type(state['wall_seconds']) in (int,float) and math.isfinite(state['wall_seconds']) and
            0<=state['wall_seconds']<660,'Invalid wall receipt')

def logs(console,log,control):
    for text in (console,log):
        require(not re.search(r'\b(FAIL|FAILED|TIMEOUT)\b|Error-|Fatal-',text),'Failure log tag')
        for line in text.splitlines():
            if re.search(r'\bUVM_(ERROR|FATAL)\b',line):
                require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0+\s*',line),'Unexpected UVM error')
    require(log.count('Core Test *** SUCCESS ***')==1,'Exact CoreSUCCESS required')
    summaries=[parse_contract_summary(s.strip()) for s in console.splitlines() if '[ARA_CONTRACT]' in s]
    require(len(summaries)==1 and summaries[0] is not None,'One protocol summary required')
    summary=summaries[0]
    require(summary['requests']==summary['responses']==control['requests'] and summary['exceptions']==0 and
            all(summary[k]==0 for k in ('protocol_errors','outstanding','req_stalled','resp_stalled')),
            'Protocol summary differs')

def tracer_exact(text,rows):
    pattern=re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual=[m.groups() for line in text.splitlines() if (m:=pattern.match(line))]
    retired=[r for r in rows if r['event']=='retire']
    wanted=[(str(int(r['cycle'])),'M','%016x'%int(r['pc'],16),'%08x'%int(r['insn'],16)) for r in retired]
    require(actual[:len(wanted)]==wanted,'Full tracer/RVFI prefix mismatch')
    suffix=actual[len(wanted):]
    if suffix:
        pc=int(retired[-1]['pc'],16)+4;word=elf_instruction(runner.ELF.read_bytes(),pc,4)
        require(len(suffix)==1 and suffix[0]==(wanted[-1][0],'M','%016x'%pc,'%08x'%word),
                'Unexplained post-terminal tracer suffix')
    require('Exception @' not in text and 'tval:' not in text,'Unexpected tracer exception')
    return dict(ELF_entry_prefix=len(wanted),post_terminal_records=len(suffix),exceptions=0)

def prepare(out,run,runseal):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh direct collector plan required')
    recordpath=run.with_name(run.name+'.prepared.json');record=life.read_bound(recordpath,runseal)
    require(record==runner.manifest(run),'Existing run prepared contract differs')
    deps=[Path(__file__).resolve(),Path(__file__).with_name('test_qualify_queue_mask_source_lifetime_terminal.py'),
          Path(tail.__file__),Path(previous.__file__),Path(common.__file__),Path(bitmap.__file__),
          Path(__file__).with_name('qualify_store_fault_flush_terminal.py'),
          Path(tail.__file__).with_name('test_queue_mask_tail_vector_oracle.py')]
    pins=life.merge_pins(record['pins'],{str(f.resolve()):life.digest(f) for f in deps})
    pins=life.merge_pins(pins,{str(recordpath):runseal});life.check(pins)
    sourcebook=runner.p.BUILD/'build-source-pins.json'
    require(life.digest(sourcebook)=='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b',
            'Known source book identity differs')
    book=json.loads(sourcebook.read_bytes())
    sourcepaths=[life.ROOT/rel for rel in ('hardware/tb/ara_commit_monitor.sv','hardware/tb/ara_tb.sv',
                 'hardware/src/lane/operand_requester.sv','hardware/deps/common_cells/src/rr_arb_tree.sv')]
    pins=life.merge_pins(pins,{str(path):book[str(path)] for path in sourcepaths});life.check(pins)
    out.mkdir();plan=dict(status=STATUS,run=str(run),prepared=str(recordpath),prepared_seal=runseal,
                         pins=pins,coverage_admitted=False,simulation_started=False)
    life.save(out/'plan.json',plan)
    print(json.dumps(dict(plan=str(out/'plan.json'),seal=life.digest(out/'plan.json'),pins=len(pins))))

def collect(planpath,seal,out):
    plan=life.read_bound(planpath,seal);run=Path(plan['run'])
    require(plan['status']==STATUS and plan['coverage_admitted'] is False and
            plan['simulation_started'] is False,'Collector plan contract differs')
    life.check(plan['pins'])
    require((run/'simulation-status.json').is_file(),'No terminal receipt: do not read active trace')
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh direct result required')
    pins=life.merge_pins(plan['pins'],{str(planpath):seal})
    def read(path):
        require(path.resolve()==path and not path.is_symlink(),'Evidence alias')
        raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest()
        require(life.digest(path)==h,'Evidence changed during read');pins[str(path)]=h;return raw
    record=life.read_bound(Path(plan['prepared']),plan['prepared_seal'])
    require(record==runner.manifest(run),'Sealed existing run inputs differ')
    terminal(json.loads(read(run/'simulation-status.json')),json.loads(read(run/'manifest.json')),
             json.loads(read(run/'started.json')),record)
    out.mkdir()
    try:
        symbols=json.loads((runner.PRE/'symbols.json').read_bytes())
        reference=reference_prefix()
        rows=common.read_csv(read(run/'commit_trace.csv'),common.COMMIT_FIELDS)
        vectors=common.read_csv(read(run/'vector_trace.csv'),common.VECTOR_FIELDS)
        control=lifecycle(rows,vectors);memory=observed(rows,symbols)
        logs(read(run/'console.log').decode(),read(run/'run.vcs.log').decode(),control)
        require(not check_contract_log(run/'run.vcs.log'),'Protocol contract log error')
        tracer=read(run/'trace_hart_0.log').decode();read(run/'trace_hart_0_commit.log')
        tracerproof=tracer_exact(tracer,rows)
        scalar=common.spike_trace.compare_commit_prefix(runner.PRE/'spike.log',run/'commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar,common.reference_counts(reference,symbols))
        vector=native(run,reference,symbols)
        db=run/'code.vdb';files=sorted(f for f in db.rglob('*') if f.is_file())
        require(files and all(any(f.name==m+'.verilog.data.xml' for f in files)
                             for m in ('line','cond','branch','fsm')),'Complete VDB witness required')
        for f in files:read(f)
        inputs=out/'singleton-inputs.txt';inputs.write_text(str(life.IMAGE)+'.vdb\n'+str(db)+'\n')
        singleton=bitmap.collect(inputs)
        require(singleton['tests']==[str(db)] and singleton['input_hashes'] and
                all(pins.get(k)==v for k,v in singleton['input_hashes'].items()),'Unpinned singleton inputs')
        pre=life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL);hits=[]
        for t in pre['targets']:
            r=singleton['metrics']['cond'][t['scope']]
            require((r['width'],r['checksum'])==(1256,'1592560956') and t['before'] is False and
                    t['point']['raw_index']==665 and t['point']['vector']=='010','Frozen primary drift')
            hits.append(dict(scope=t['scope'],raw_index=665,actual_hit=bool(int(r['bits'],16)>>(1256-1-665)&1)))
        require(len(hits)==4,'Exact4 lane primary targets required')
        life.check(pins)
        for name,obj in [('scalar-comparison.json',scalar),('vector-tail-comparison.json',vector),
                         ('observed-memory.json',memory),('lifecycle.json',control),('actual-target-hits.json',hits)]:
            life.save(out/name,obj)
        life.save(out/'tracer-comparison.json',tracerproof)
        outputs={str(f):life.digest(f) for f in out.iterdir() if f.is_file()}
        life.save(out/'qualification.json',dict(status='QUEUE_MASK_FULL_TERMINAL_PASS_NOT_ADMITTED',
            pins=life.merge_pins(pins,outputs),checks=6936,strict_memory_bytes=6912,csr_values=24,
            primary_native_writers=32,mask_active_bits=720,mask_tail_set_bits=7472,UVM_errors=0,OS_returncode=0,
            all_primary_hit=all(h['actual_hit'] for h in hits),coverage_admitted=False,raw_gain_collected=False,
            ELF_entry_reference_counts=common.reference_counts(reference,symbols),
            all_reference_memory_accesses=21386,vector_reference_memory_accesses=2762,
            raw_gain_gate='positive actual latest-formal full6162 OR/exactprefix; separate reviewed step',
            native_cycle_qualified=False,whole_ISA_qualified=False))
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'qualification.json'),coverage_admitted=False)))
    except Exception as exc:
        life.save(out/'failure.json',dict(status='QUALIFICATION_HOLD_NOT_ADMITTED',reason=str(exc),pins=pins));raise

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('prepare','collect'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--run',type=Path)
    ap.add_argument('--prepared-seal');ap.add_argument('--plan',type=Path);ap.add_argument('--seal')
    a=ap.parse_args()
    if a.mode=='prepare':
        require(a.run is not None and a.prepared_seal and not a.plan and not a.seal,'Prepare arguments')
        prepare(a.output.resolve(),a.run.resolve(),a.prepared_seal)
    else:
        require(a.plan is not None and a.seal and not a.run and not a.prepared_seal,'Collect arguments')
        collect(a.plan.resolve(),a.seal,a.output.resolve())
