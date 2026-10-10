"""Offline GAP112 exact scalar/FOF-defined bytes/SID qualification; no EDA/admission."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

import gap112_fof_flush as g
import qualify_queue_mask_source_lifetime_terminal as sid
from qualify_store_fault_flush_terminal import elf_instruction
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log

life, require, common, bitmap = g.life, g.require, g.strict, sid.bitmap
RUN = life.OUT/'gap112-fof-flush-old-image-740-agent-20261007-01'
RUN_SEAL = '6dc796b89c673fa46cd82d520926bdbe70474e9101a0a94f3fa1c03d33002d73'
PRE = life.OUT/'gap112-fof-flush-preflight-740-agent-20261007-02'
PRE_SEAL = 'd187315aff4ff38048a158ee46ead4e5037c4179bd32f7dd7ec0933122587d0d'
G_SHA = '57beea3850e3f7745f80b61b8d1203862e58df623441e7cbfa6794bda63ea9cb'
SPEC = 'https://docs.riscv.org/reference/isa/unpriv/v-st-ext'


def inputs():
    require(life.digest(Path(g.__file__))==G_SHA,'Frozen runner drift')
    record=life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),RUN_SEAL)
    pre=life.read_bound(PRE/'preflight-manifest.json',PRE_SEAL)
    require(record['preflight']==str(PRE/'preflight-manifest.json') and record['preflight_seal']==PRE_SEAL and
        record['output']==str(RUN) and record['case']==g.NAME and record['timeout_s']==180 and
        record['image_sha256']==g.IMAGE_SHA and record['elf_sha256']==pre['elf_sha256'] and
        record['old_image_files_checked']==66 and record['automatic_retry'] is False and
        record['terminal_oracle_verified'] is False and record['coverage_admitted'] is False and
        record['admission_performed'] is False and record['foreground_lifetime'] is True,
        'Exact reviewed run contract required')
    require(pre['status']=='GAP112_HOST_SPIKE_PREFLIGHT_PASS_NOT_DUT' and
        pre['baseline_seal']==g.BASE_SEAL and pre['VCS_started'] is False and
        g.validate(g.shared.parse_spike_commits(PRE/'spike.trace'),pre['symbols'])==pre['validation'],
        'Sealed complete software oracle differs')
    require(record['target']==pre['target']==g.binding()[1] and
        all(record['pins'].get(k)==v for k,v in pre['pins'].items()),'Missing source/target/preflight pins')
    return record,pre


def terminal(state,actual,started,record):
    require(state.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and type(state.get('returncode')) is int and
        state['returncode']==0 and state['timeout'] is False and state['case']==g.NAME and
        state['coverage_admitted'] is False and state['admission_performed'] is False and
        state['terminal_oracle_verified'] is False,'HOLD: successful actual OS receipt required')
    require(actual==record and started['command']==record['command'] and
        started['input_elf']==str(PRE/'input.elf') and started['elf_sha256']==record['elf_sha256'] and
        started['image']==str(life.IMAGE) and started['image_sha256']==g.IMAGE_SHA and
        type(started['pid']) is int and started['pid']>0 and
        started['pid']==started['process_group']==state['pid'] and started['budget_s']==180 and
        started['foreground_lifetime'] is True and started['coverage_admitted'] is False,
        'Actual process/image/command identity differs')
    require(type(state['wall_seconds']) in (int,float) and math.isfinite(state['wall_seconds']) and
        0<=state['wall_seconds']<240,'Invalid wall receipt')


def observed(rows,symbols,blob):
    retired=[r for r in rows if r['event']=='retire']
    require(len(retired)==3002 and [int(r['order']) for r in retired]==list(range(3002)),
        'Full contiguous3002 retirement prefix required')
    ranges=[(symbols[n],symbols[n]+4*len(v)) for n,v in g.expected().items()]
    ranges += [(0x801ffffc,0x80200000)]
    memory,reads,terminals={},set(),[]
    for r in retired:
        pc,word=int(r['pc'],16),int(r['insn'],16)
        require(int(r['trap'])==0 and pc!=symbols['trap_fail'] and
            elf_instruction(blob,pc,2 if word&3!=3 else 4)==word,'ELF/trap mismatch')
        addr,rm,wm=int(r['mem_addr'],16),int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        access=common.scalar_memory(word)
        if access is None:
            require(not rm and not wm,'Unexpected scalar memory effect');continue
        kind,size=access;mask=((1<<size)-1)<<(addr&7)
        require(addr%size==0 and rm==(mask if kind=='read' else 0) and
            wm==(mask if kind=='write' else 0),'Scalar mask/alignment mismatch')
        if kind=='write':
            value=int(r['mem_wdata'],16)&((1<<(size*8))-1)
            if addr==symbols['tohost']:terminals.append((r,value))
        elif any(a<=addr and addr+size<=b for a,b in ranges):
            require(int(r['rd'])!=0,'Unobservable signature read')
            value=int(r['rd_wdata'],16)&((1<<(size*8))-1);reads.update(range(addr,addr+size))
        else:continue
        memory.update({addr+i:(value>>(8*i))&255 for i in range(size)})
    require(terminals==[(retired[-1],1)],'Exact final successful tohost required')
    def read(addr,size=4):
        require(all(addr+i in memory for i in range(size)),'Missing oracle bytes')
        return int.from_bytes(bytes(memory[addr+i] for i in range(size)),'little')
    for name,values in g.expected().items():
        require([read(symbols[name]+4*i) for i in range(len(values))]==values,'Independent footprint differs: '+name)
    required={i for a,b in ranges for i in range(a,b)}
    # Four CSR values are stored from observed reads, not reloaded by the C checker.
    csr=set(range(symbols['gf_csr'],symbols['gf_csr']+16))
    require(required-csr<=reads,'Incomplete explicit array/boundary readback')
    require(read(0x801ffffc)==g.WORD and read(symbols['g75_result'])==194 and
        read(symbols['g75_result']+4)==read(symbols['num_failed'])==0 and
        all(read(symbols['g75_trap']+i,8)==0 for i in (0,8,16)),'Signature/trap/CSR result differs')
    return dict(checks=194,defined_array_bytes=772,csr_values=4,explicit_readback_bytes=len(reads),
        elf_matched_retirements=3002,traps=0,fof_VL=1,vstart=0)


def checked_native(reference,activities,mapping,symbols):
    state={};records=[];kinds=Counter();strict_bytes=0;permitted=0
    require(all(s in mapping for s in activities),'Unmapped native request')
    wanted={s for s,i in mapping.items() if reference[i].vector_writes}
    require(len(wanted)==6,'Exact6 architectural writers required')
    for seq,i in sorted(mapping.items()):
        c=reference[i];a=activities.get(seq)
        if a is None:
            require(seq not in wanted,'Missing native writer');continue
        require(a.instruction==c.instruction and a.allocations==a.completions and a.allocations>0,
            'Opcode/incomplete native request')
        require(all(w.be&~w.known_be==0 for w in a.writes),'Unknown accepted native byte')
        actual=vc._architectural_bytes(a.writes,4,1024)
        gold={}
        if seq not in wanted:
            if not actual:continue
            require(c.instruction&127==0x27 and all(w.source==3 for w in a.writes),
                'Unclassified nonarchitectural transport')
            kind='IDENTITY_TRANSPORT'
        elif c.pc==symbols['gf_fof']:
            require(a.eew==2 and a.vstart==0 and a.vl==4 and a.allocations==1 and
                all(w.source==4 for w in a.writes),'Exact FOF native context differs')
            gold={(8,b):(g.WORD>>(8*b))&255 for b in range(4)};kind='FOF_DEFINED_PREFIX'
        elif c.pc==symbols['gf_recovery']:
            require(a.allocations==8 and all(w.source==4 for w in a.writes),'Exact eight segment microloads required')
            gold={(reg,b):(value>>(8*b))&255 for reg,value in c.vector_writes.items() for b in range(16)}
            kind='SEGMENT_RECOVERY'
        elif c.instruction==0x7e002057:
            require(a.vl==64 and a.vstart==0 and all(w.source==2 for w in a.writes),'Exact mask source differs')
            gold={(0,b):255 for b in range(8)};kind='MASK_ACTIVE64'
        else:
            require(c.instruction&127==7 or c.pc==symbols['gf_long_div'],'Unexpected vector writer')
            producer=1 if c.pc==symbols['gf_long_div'] else 4
            require(a.eew==2 and a.vstart==0 and a.vl==c.vector_vl and
                all(w.source==producer for w in a.writes),'Load/DIV context/producer differs')
            gold={(reg,b):(value>>(8*b))&255 for reg,value in c.vector_writes.items() for b in range(128)}
            kind='DIV' if producer==1 else 'FULL_LOAD'
        require(all(k in actual and actual[k][0]==v for k,v in gold.items()),'Missing/incorrect defined destination bytes')
        before=dict(state)
        for w in a.writes:
            individual=vc._architectural_bytes([w],4,1024)
            for (reg,b),(value,owner) in individual.items():
                key=reg,b
                if kind=='FOF_DEFINED_PREFIX' and reg==8 and 4<=b<16:
                    permitted+=1
                elif kind=='MASK_ACTIVE64' and reg==0 and b>=8:
                    require(value==255 or key in before and value|before[key]==value,
                        'Unproved mask-tail old/1 policy')
                elif key in gold:
                    require(value==gold[key],'Earlier corrupt accepted byte cannot be hidden')
                else:
                    require(key in before and value==before[key],
                        'HOLD: unproved tail/non-destination/transport prestate')
        state.update({k:v for k,(v,w) in actual.items()})
        strict_bytes+=len(gold);kinds[kind]+=1
        records.append(dict(arch_seq=seq,pc=c.pc,instruction=c.instruction,kind=kind,
            allocations=a.allocations,defined_bytes=len(gold),accepted_bytes=len(actual)))
    require(kinds['FULL_LOAD']==2 and kinds['DIV']==kinds['FOF_DEFINED_PREFIX']==
        kinds['MASK_ACTIVE64']==kinds['SEGMENT_RECOVERY']==1,'Complete vector writer population differs')
    return dict(status='GAP112_NATIVE_DEFINED_FOF_AND_GROUP_PASS',primary_writers=6,
        defined_compared_bytes=strict_bytes,unknown_accepted_bytes=0,whole_instruction_skipped=0,
        fof_spurious_byte_events=permitted,fof_spurious_allowed='Only original active elements1..3 (bytes4..15 of v8)',
        no_prestart_elements_claimed=True,non_destination_known_bytes_preserved=True,
        whole_VRF_initial_state_qualified=False,records=records,spec=SPEC)


def native(run,reference,symbols,vector_rows):
    lanes,vlen,activities=vc._parse_vector_trace(run/'vector_trace.csv')
    starts,retires,rejected=vc._parse_architecture_mapping(run/'commit_trace.csv')
    require((lanes,vlen)==(4,1024) and not rejected,'Wrong geometry/rejected request')
    arch=vc._map_architecture_retires(starts,retires,rejected)
    mapping=vc._map_spike_commits(arch,reference)
    require(all(arch[s].pc==reference[i].pc and arch[s].instruction==reference[i].instruction
        for s,i in mapping.items()),'Exact arch_seq/PC/opcode mapping differs')
    recover=[r for r in vector_rows if r['event']=='alloc' and int(r['insn'],16)==
        next(c.instruction for c in reference if c.pc==symbols['gf_recovery'])]
    require(Counter((int(r['vd']),int(r['vl']),int(r['vstart']),int(r['eew'])) for r in recover)==
        Counter((reg,i+1,i,2) for reg in (12,13) for i in range(4)), 'Segment field/element allocation geometry differs')
    return checked_native(reference,activities,mapping,symbols)


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh standalone plan required')
    record,pre=inputs()
    deps=[Path(__file__).resolve(),Path(__file__).with_name('test_qualify_gap112_fof_flush.py'),
        Path(sid.__file__).resolve(),Path(sid.previous.__file__).resolve(),Path(bitmap.__file__).resolve(),
        Path(__file__).with_name('qualify_store_fault_flush_terminal.py')]
    pins=life.merge_pins(record['pins'],{str(x):life.digest(x) for x in deps})
    pins=life.merge_pins(pins,{str(RUN.with_name(RUN.name+'.prepared.json')):RUN_SEAL})
    life.check(pins);out.mkdir()
    life.save(out/'plan.json',dict(status='GAP112_POSTRUN_PLAN_NOT_EXECUTED',pins=pins,
        run=str(RUN),prepared_seal=RUN_SEAL,preflight=str(PRE),preflight_seal=PRE_SEAL,
        simulations_started=False,coverage_admitted=False))
    print(json.dumps(dict(plan=str(out/'plan.json'),seal=life.digest(out/'plan.json'),pins=len(pins))))


def collect(planpath,seal,out):
    plan=life.read_bound(planpath,seal)
    require(plan['status']=='GAP112_POSTRUN_PLAN_NOT_EXECUTED' and plan['run']==str(RUN) and
        plan['prepared_seal']==RUN_SEAL and plan['preflight_seal']==PRE_SEAL and
        plan['simulations_started'] is False and plan['coverage_admitted'] is False,'Exact plan required')
    life.check(plan['pins']);record,pre=inputs()
    require((RUN/'simulation-status.json').is_file(),'No terminal receipt: do not read active trace')
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh collection required')
    pins=life.merge_pins(plan['pins'],{str(planpath):seal})
    def read(path):
        require(path.resolve()==path and not path.is_symlink(),'Aliased evidence')
        data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
        require(life.digest(path)==sha,'Evidence changed while reading');pins[str(path)]=sha;return data
    terminal(json.loads(read(RUN/'simulation-status.json')),json.loads(read(RUN/'manifest.json')),
        json.loads(read(RUN/'started.json')),record)
    out.mkdir()
    try:
        rows=common.read_csv(read(RUN/'commit_trace.csv'),common.COMMIT_FIELDS)
        vectors=common.read_csv(read(RUN/'vector_trace.csv'),common.VECTOR_FIELDS)
        control=sid.lifecycle(rows,vectors)
        memory=observed(rows,pre['symbols'],(PRE/'input.elf').read_bytes())
        console,log=read(RUN/'console.log').decode(),read(RUN/'run.vcs.log').decode()
        sid.logs(console,log,control);require(not check_contract_log(RUN/'run.vcs.log'),'Protocol contract errors')
        scalar=common.spike_trace.compare_commit_prefix(PRE/'spike.trace',RUN/'commit_trace.csv',0x80000000,
            terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar,pre['reference_counts'])
        reference=g.shared.parse_spike_commits(PRE/'spike.trace')
        reference=reference[next(i for i,c in enumerate(reference) if c.pc==0x80000000):]
        vector=native(RUN,reference,pre['symbols'],vectors)
        tracer=read(RUN/'trace_hart_0.log').decode();read(RUN/'trace_hart_0_commit.log')
        pattern=re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
        actual=[m.groups() for line in tracer.splitlines() if (m:=pattern.match(line))]
        retired=[r for r in rows if r['event']=='retire']
        expected=[(str(int(r['cycle'])),'M','%016x'%int(r['pc'],16),'%08x'%int(r['insn'],16)) for r in retired]
        suffix=actual[len(expected):];pc=int(retired[-1]['pc'],16)+4
        word=elf_instruction((PRE/'input.elf').read_bytes(),pc,2)
        require(actual[:len(expected)]==expected and (not suffix or suffix==[(expected[-1][0],'M','%016x'%pc,'%08x'%word)])
            and 'Exception @' not in tracer and 'tval:' not in tracer,'Full tracer/retirement prefix differs')
        for f in sorted((RUN/'code.vdb').rglob('*')):
            require(not f.is_symlink(),'Aliased VDB member')
            if f.is_file():read(f)
        ledger=out/'singleton-inputs.txt';ledger.write_text(str(life.IMAGE)+'.vdb\n'+str(RUN/'code.vdb')+'\n')
        single=bitmap.collect(ledger)
        require(single['input_hashes'] and all(pins.get(k)==v for k,v in single['input_hashes'].items()),'Unpinned raw singleton')
        base=life.read_bound(g.BASE/'admission-manifest.json',g.BASE_SEAL)
        before=life.read_bound(g.BASE/'combined-bits.json',base['output_pins'][str(g.BASE/'combined-bits.json')])
        combined=bitmap.combine(before,single);delta=bitmap.delta(before,combined)
        require(len(before['tests'])==740 and combined['tests']==before['tests']+single['tests'] and
            len(set(combined['tests']))==741 and sum(len(x) for x in before['metrics'].values())==6162,'Full740+unique singleton required')
        row=single['metrics']['fsm'][g.SCOPE]
        require((row['width'],row['checksum'])==(92,'1099616778'),'Actual FSM shape differs')
        hits=dict(target=pre['target'],actual_single_hit=bool(int(row['bits'],16)>>(92-1-78)&1),
            DVE_native_transition_qualified=False,baseline=740,measured_delta=delta['metrics'])
        for name,obj in [('scalar-comparison.json',scalar),('vector-comparison.json',vector),
            ('memory-oracle.json',memory),('lifecycle.json',control),('target-hit.json',hits),
            ('single-bits.json',single),('raw-delta.json',delta)]:life.save(out/name,obj)
        life.check(pins);pins=life.merge_pins(pins,{str(f):life.digest(f) for f in out.iterdir() if f.is_file()})
        life.save(out/'qualification.json',dict(status='GAP112_SCALAR_DEFINED_VECTOR_MEMORY_CSR_CONTRACT_PASS_NOT_ADMITTED',
            pins=pins,checks=194,defined_array_bytes=772,vector_writers=6,raw78_hit=hits['actual_single_hit'],
            static_baseline=740,raw_delta=delta['metrics'],UVM_errors=0,OS_returncode=0,
            coverage_admitted=False,whole_ISA_qualified=False,native_cycle_qualified=False,
            simulations_started=False,simulation_retried=False,fof_spec=SPEC))
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'qualification.json'),raw78_hit=hits['actual_single_hit'],raw_delta=delta['metrics'])))
    except Exception as exc:
        life.save(out/'failure.json',dict(status='QUALIFICATION_HOLD_NOT_ADMITTED',reason=str(exc),pins=pins));raise


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=('prepare','collect'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--plan',type=Path);ap.add_argument('--seal')
    a=ap.parse_args()
    if a.mode=='prepare':require(not(a.plan or a.seal),'Prepare arguments');prepare(a.output.absolute())
    else:require(a.plan and a.seal,'Sealed plan required');collect(a.plan.absolute(),a.seal,a.output.absolute())
