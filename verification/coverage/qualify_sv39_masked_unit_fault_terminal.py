"""Terminal-only scalar/RVC/vector/trap/gold qualification; no raw OR/admission."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

import run_sv39_masked_unit_fault_simulation as runner
import check_operand_index_snapshot_offline_v2 as reset_proof
import collect_opivx_vsbc_strict as common
from scoped_rv64c_memory import decode
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log, parse_contract_summary

p, life, require = runner.p, runner.life, runner.require
STATUS='SV39_MASKED_UNIT_FAULT735_TERMINAL_PLAN_NO_VCS'
MASK64=(1<<64)-1


def reference_prefix(commits, symbols):
    prefix=[]
    for c in commits:
        if not prefix and c.pc!=0x80000000: continue
        prefix.append(c)
        if (symbols['tohost'],1) in c.memory_accesses: break
    require(prefix and prefix[-1].memory_accesses==((symbols['tohost'],1),),'Incomplete reference terminal')
    partial=[i for i,c in enumerate(prefix) if c.pc==symbols['smuf_masked_load'] and
             not (c.gpr_writes or c.fpr_writes or c.vector_writes or c.memory_accesses)]
    require(len(partial)==1 and prefix[partial[0]].instruction==p.WORDS['smuf_masked_load'],
            'Exact zero-effect fault reference missing')
    return prefix,partial[0]


def scalar_gate(result, reference, symbols, partial):
    commits=[c for i,c in enumerate(reference) if i!=partial]
    expected=dict(status='TERMINAL_TOHOST_MATCH',entry='0x0000000080000000',
        rvfi_store_data_layout='unshifted',skipped_unobservable_register_values=0,
        stopped_at_unobservable=None,mismatch=None,terminal_ecall=None,
        matched_instructions=len(commits),ara_committed_instructions=len(commits),
        matched_scalar_writes=sum(len({r:v for r,v in c.gpr_writes.items() if r}) for c in commits),
        matched_floating_writes=sum(len(c.fpr_writes) for c in commits),
        matched_scalar_memory_accesses=sum(bool(c.memory_accesses) and
            common.spike_trace._scalar_memory_access(c.instruction) is not None for c in commits))
    runner.exact(result,expected,'Incomplete full scalar differential')
    require(type(result['ara_trap_events']) is int and result['ara_trap_events'] in (1,2) and
            result['ara_retired_instructions']==len(commits)+result['ara_trap_events'],
            'Native trap/retirement conservation differs')
    faults=result['aligned_vector_faults']
    require(len(faults)==1 and faults[0]['pc']=='0x%016x'%symbols['smuf_masked_load'] and
            faults[0]['instruction']=='0x%08x'%p.WORDS['smuf_masked_load'] and
            faults[0]['fault_handler_returned'] is True and
            faults[0]['matched_fault_csrs']=={'0x341':symbols['smuf_masked_load'],'0x342':13,'0x343':0x40000300} and
            not faults[0].get('invalidated_fault_csrs'), 'Exact fault CSR/return alignment differs')


def compressed_audit(rows, reference, partial, symbols):
    retired=[r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retired]==list(range(len(retired))),'Retirement order differs')
    traps=[r for r in retired if int(r['trap'])]
    require(len(traps) in (1,2) and len({int(r['pc'],16) for r in traps})==len(traps) and
            any(int(r['pc'],16)==symbols['smuf_ecall'] for r in traps) and
            all((int(r['pc'],16),int(r['insn'],16)) in
                ((symbols['smuf_masked_load'],p.WORDS['smuf_masked_load']),(symbols['smuf_ecall'],0x73))
                and int(r['rd'])==int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0 for r in traps),
            'Unexpected native precise trap')
    clean=[r for r in retired if not int(r['trap'])]
    expected=[c for i,c in enumerate(reference) if i!=partial]
    require(len(clean)==len(expected),'Partial scalar alignment')
    registers={i:0 for i in range(32)}; counts=Counter()
    for row,c in zip(clean,expected):
        require(int(row['pc'],16)==c.pc and int(row['insn'],16)==c.instruction,'Scalar/RVC PC/opcode alignment differs')
        rm,wm,addr=int(row['mem_rmask'],16),int(row['mem_wmask'],16),int(row['mem_addr'],16)
        if c.instruction&3!=3:
            d=decode(c.instruction)
            if d is None:
                require(not c.memory_accesses and rm==wm==0,'Unknown compressed memory effect')
            else:
                size,reg=d['size'],d['register']; address=(registers[d['base']]+d['offset'])&MASK64
                mask=((1<<size)-1)<<(address&7)
                require(address%size==0 and addr==address,'Compressed address/alignment differs')
                if d['kind']=='write':
                    value=registers[reg]&((1<<(8*size))-1)
                    require(c.memory_accesses==((address,value),) and not c.gpr_writes and
                            rm==0 and wm==mask and int(row['rd'])==0 and
                            int(row['mem_wdata'],16)&((1<<(8*size))-1)==value,'Compressed store data/mask differs')
                else:
                    require(c.memory_accesses==((address,None),) and set(c.gpr_writes)=={reg},
                            'Reference compressed load differs')
                    value=c.gpr_writes[reg]
                    if size==4:
                        low=value&0xffffffff
                        require(value==(low | (0xffffffff00000000 if low&0x80000000 else 0)),
                                'C.LW sign extension differs')
                    require(rm==mask and wm==0 and int(row['rd'])==reg and int(row['rd_wdata'],16)==value,
                            'Compressed load data/mask differs')
                counts[d['kind']]+=1
        registers.update({reg:value for reg,value in c.gpr_writes.items() if reg})
        registers[0]=0
    return dict(status='ALL_SCALAR_RVC_MEMORY_ALIGNED_EXACT',matched_retirements=len(clean),
        compressed_loads=counts['read'],compressed_stores=counts['write'],skipped_memory_events=0,
        expected_from='sealed Spike prior GPRs plus frozen FF zero reset, never DUT feedback')


def observed_gold(rows,symbols):
    expected=p.expected_memory(symbols); memory={}; reads=set(); terminals=[]
    status_bytes={symbols['records']+phase*96+24+i for phase in range(2) for i in range(8)}
    for r in rows:
        if r['event']!='retire' or int(r['trap']):continue
        ins=int(r['insn'],16); d=decode(ins) if ins&3!=3 else None
        access=(d['kind'],d['size']) if d is not None else common.spike_trace._scalar_memory_access(ins)
        rm,wm=int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        if access is None:
            require(rm==wm==0,'Unknown scalar memory effect');continue
        kind,size=access; address=int(r['mem_addr'],16); mask=((1<<size)-1)<<(address&7)
        require(address%size==0 and rm==(mask if kind=='read' else 0) and wm==(mask if kind=='write' else 0),
                'Scalar oracle memory mask/alignment differs')
        if kind=='read':
            if not any(address+i in expected or address+i in status_bytes for i in range(size)):continue
            require(int(r['rd'])!=0,'Unobservable oracle readback')
            value=int(r['rd_wdata'],16);reads.update(range(address,address+size))
        else:
            value=int(r['mem_wdata'],16)
            if address==symbols['tohost']:
                require(size==8 and value==1,'Failure/partial terminal store');terminals.append(r)
        for i,b in enumerate((value&((1<<(8*size))-1)).to_bytes(size,'little')):memory[address+i]=b
    retired=[r for r in rows if r['event']=='retire']
    require(terminals==[retired[-1]],'Duplicate/nonfinal/missing terminal')
    require(all(memory.get(a)==v for a,v in expected.items()),'Independent full memory/VRF/CSR/guards mismatch')
    required={symbols['smuf_pages']+i for i in range(16384)}
    for n in ('seed','fault','result'):required.update(range(symbols[n],symbols[n]+896))
    for n in ('smuf_guard_lo','smuf_guard_hi'):required.update(range(symbols[n],symbols[n]+64))
    for n,size in (('post',40),('records',192)):required.update(range(symbols[n],symbols[n]+size))
    require(required<=reads,'Incomplete explicit oracle readback')
    for phase in range(2):
        status=int.from_bytes(bytes(memory[symbols['records']+phase*96+24+i] for i in range(8)),'little')
        require(status&0x8000031888==0x800,'Trap privilege/interrupt state differs')
    return dict(checks=85,independent_gold_bytes=len(expected),required_readback_bytes=len(required),
                traps=2,cause13_tval=0x40000300,original_PC_retry=True,whole_mask_tail_guards=True)


def log_gate(text):
    require(text.count('Core Test *** SUCCESS ***')==1 and not re.search(
        r'Fatal:|Error:|Fatal-\[|Error-\[|\[ARA_CONTRACT_ERROR\]|Core Test \*\*\* FAILED',text),
        'Missing SUCCESS/error diagnostic')
    for line in text.splitlines():
        if re.search(r'\bUVM_(ERROR|FATAL)\b',line):
            require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0+\s*',line),'Actual UVM error')


def prepared_contract(run,manifest):
    # Reconstruct the reviewed runner contract without its fresh-launch guard.
    # This is a read-only consumer; the run directory may already exist.
    require(run.parent==life.OUT and run.resolve()==run,'Direct run required')
    pre,pins=runner.verify_preflight()
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(image['simv']==str(life.IMAGE) and len(image['image'])==66 and
            image['image'][str(life.IMAGE)]==runner.IMAGE_SEAL,'Fixed simv66 differs')
    required=life.merge_pins(pins,image['image'])
    required=life.merge_pins(required,{str(runner.PRE/'preflight-manifest.json'):runner.PRE_SEAL,
        str(life.PLAN):life.PLAN_SEAL,str(Path(life.__file__).resolve()):runner.LIFE_SEAL,
        str(Path(runner.frozen.__file__).resolve()):runner.FROZEN_SEAL})
    for path in (Path(runner.__file__).resolve(),Path(runner.__file__).with_name('test_run_sv39_masked_unit_fault_simulation.py')):
        required=life.merge_pins(required,{str(path):life.digest(path)})
    expected=dict(case=runner.NAME,output=str(run),preflight=str(runner.PRE/'preflight-manifest.json'),
        preflight_seal=runner.PRE_SEAL,pins=required,command=runner.command(run),timeout_s=180,
        baseline_tests=735,baseline=str(runner.BASE),baseline_seal=runner.BASE_SEAL,old_image_files_checked=66,
        elf_sha256=required[str(runner.PRE/'input.elf')],image_sha256=runner.IMAGE_SEAL,software_checks=85,
        expected_traps=2,expected_CVX_exceptions=1,foreground_lifetime=True,automatic_retry=False,
        no_FSDB=True,parent_review_required=True,dut_self_check_verified=False,
        terminal_oracle_verified=False,coverage_admitted=False,admission_performed=False,
        rtl_changed=False,new_RTL_signoff=False,systemd_policy=dict(RuntimeMaxSec=240,
            TimeoutStopSec=10,KillMode='control-group'))
    require(set(manifest)==set(expected),'Unknown/missing execution contract field')
    runner.exact(manifest,expected,'Exact735 prepared consumer contract differs')
    life.check(required)
    return pre


def prepare(run,runseal,output):
    record=run.with_name(run.name+'.prepared.json'); manifest=life.read_bound(record,runseal)
    prepared_contract(run,manifest)
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(),'Fresh qualification plan required')
    files=[Path(__file__).resolve(),Path(__file__).with_name('test_qualify_sv39_masked_unit_fault_terminal.py'),
           Path(reset_proof.__file__).resolve(),Path(common.__file__).resolve(),
           Path(__file__).with_name('scoped_rv64c_memory.py'),*sorted((life.ROOT/'verification/ara_verify').rglob('*.py'))]
    pins=life.merge_pins(manifest['pins'],{str(x):life.digest(x) for x in files})
    pins=life.merge_pins(pins,{str(record):runseal})
    sources=json.loads((p.BUILD/'build-source-pins.json').read_bytes())
    for rel in ('hardware/tb/ara_commit_monitor.sv','verification/uvm/ara_acc_contract_monitor.sv'):
        path=life.ROOT/rel;pins=life.merge_pins(pins,{str(path):sources[str(path)]})
    # Bind the compiled source mapping consumed by source_contract, not just
    # the RTL file and module checksum. No invented historical mapping hash.
    ledger=json.loads((runner.BASE/'evidence-pins.json').read_bytes())
    mapping=p.BUILD/'sim/simv.vdb/snps/coverage/db/auxiliary/verilog.sourceinfo.xml'
    require(str(mapping) in ledger,'Missing historical compiled source-map pin')
    pins=life.merge_pins(pins,{str(mapping):ledger[str(mapping)]})
    pins,proof=reset_proof.source_contract(pins);life.check(pins)
    output.mkdir()
    plan=dict(status=STATUS,run=str(run),prepared=str(record),prepared_seal=runseal,
              pins=pins,source_contract=proof,baseline=735,baseline_seal=runner.BASE_SEAL,
              coverage_admitted=False,bitmap_not_collected=True,parent_review_required=True)
    life.save(output/'plan.json',plan)
    print(json.dumps(dict(plan=str(output/'plan.json'),seal=life.digest(output/'plan.json'),VCS_started=False)))


def collect(planpath,seal,out):
    plan=life.read_bound(planpath,seal);require(plan['status']==STATUS,'Plan family differs');life.check(plan['pins'])
    run=Path(plan['run']); manifest=life.read_bound(Path(plan['prepared']),plan['prepared_seal'])
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh output required')
    pins=life.merge_pins(plan['pins'],{str(planpath):seal})
    def read(name):
        path=run/name;require(path.resolve()==path and path.is_file(),'Missing/aliased terminal evidence')
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        require(life.digest(path)==sha,'Changing terminal evidence');pins[str(path)]=sha;return raw
    state=json.loads(read('simulation-status.json'))
    runner.exact(state,dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,case=runner.NAME,
        timeout=False,coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False),
        'Failure/timeout/nonterminal OS receipt')
    require(json.loads(read('manifest.json'))==manifest,'Executed prepared differs')
    started=json.loads(read('started.json'))
    runner.exact(started,dict(command=manifest['command'],budget_s=180,input_elf=str(runner.PRE/'input.elf'),
        elf_sha256=manifest['elf_sha256'],image=str(life.IMAGE),image_sha256=runner.IMAGE_SEAL,
        foreground_lifetime=True,coverage_admitted=False),'OS startup identity differs')
    require(type(started['pid']) is type(state['pid']) is int and started['pid']>0 and
            started['pid']==started['process_group']==state['pid'],
            'Process/terminal identity differs')
    require(type(state['wall_seconds']) in (int,float) and state['wall_seconds']>=0,'Missing wall lifetime receipt')
    out.mkdir()
    try:
        pre,_=runner.verify_preflight(); symbols=pre['symbols']
        rows=common.read_csv(read('commit_trace.csv'),common.COMMIT_FIELDS)
        vectors=common.read_csv(read('vector_trace.csv'),common.VECTOR_FIELDS)
        # Use the already audited fault lifecycle with only the symbol contract
        # generalized. The ECALL is the second exact architectural trap.
        control=lifecycle(rows,vectors,symbols)
        console=read('console.log').decode();log=read('run.vcs.log').decode()
        log_gate(console);log_gate(log)
        require(not check_contract_log(run/'run.vcs.log'),'Contract/checker diagnostic')
        summaries=[parse_contract_summary(l.strip()) for l in log.splitlines() if '[ARA_CONTRACT]' in l]
        require(len(summaries)==1 and summaries[0] is not None,'Missing/duplicate complete contract')
        counts=summaries[0]
        require(counts['requests']==counts['responses']==control['requests'] and counts['exceptions']==1 and
                all(counts[k]==0 for k in ('protocol_errors','outstanding','req_stalled','resp_stalled')),
                'Native request/error/stall contract differs')
        tracer=read('trace_hart_0.log').decode();read('trace_hart_0_commit.log')
        exceptions=re.findall(r'^Exception @\s+\d+, PC: ([0-9a-fA-F]+),.*$',tracer,re.M)
        require(Counter(int(x,16) for x in exceptions)==Counter((symbols['smuf_masked_load'],symbols['smuf_ecall'])),
                'Exact DUT exception tracer differs')
        reference,partial=reference_prefix(p.shared.parse_spike_commits(runner.PRE/'spike.trace'),symbols)
        scalar=common.spike_trace.compare_commit_prefix(runner.PRE/'spike.trace',run/'commit_trace.csv',0x80000000,
            terminal_tohost_address=symbols['tohost'],rtl_exception_log=run/'trace_hart_0.log',rvfi_store_data_layout='unshifted')
        life.save(out/'scalar-comparison.json',scalar);scalar_gate(scalar,reference,symbols,partial)
        compressed=compressed_audit(rows,reference,partial,symbols)
        gold=observed_gold(rows,symbols)
        vector=vc.compare_vector_commits(runner.PRE/'spike.trace',run/'commit_trace.csv',run/'vector_trace.csv',
                                        0x80000000,aligned_vector_faults=scalar['aligned_vector_faults'])
        life.save(out/'vector-comparison.json',vector)
        expected_writers=sum(bool(c.vector_writes) for c in reference)
        require(vector['status']=='PASS' and vector['compared_instructions']==expected_writers and
                vector['trapped_requests']==[control['fault_arch_seq']] and
                all(vector[k]==0 for k in ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions')) and
                not vector['first_mismatch'] and not vector['incomplete_requests'] and not vector['unretired_requests'],
                'Complete known vector/fault comparison differs')
        vdb=run/'code.vdb';members=sorted(x for x in vdb.rglob('*') if x.is_file())
        require(members and not any(x.is_symlink() for x in vdb.rglob('*')),'Missing/aliased VDB')
        pins=life.merge_pins(pins,{str(x):life.digest(x) for x in members})
        for name,value in (('compressed-memory-audit.json',compressed),('architecture-audit.json',gold),
                           ('lifecycle.json',control),('contract-summary.json',counts)):
            life.save(out/name,value)
        require(members==sorted(x for x in vdb.rglob('*') if x.is_file()),'VDB membership changed');life.check(pins)
        result=dict(status='SV39_MASKED_UNIT_FAULT_FULL_SCALAR_RVC_NATIVE_GOLD_PASS_NOT_ADMITTED',
            checks=85,baseline=735,baseline_seal=runner.BASE_SEAL,whole_scalar_memory_qualified=True,
            full_scalar_differential_qualified=True,native_DUT_vector_qualified=True,
            target_hit_verified=False,bitmap_not_collected=True,coverage_admitted=False,rtl_changed=False)
        life.save(out/'status.json',result)
        life.save(out/'qualification-seal.json',dict(input_pins=pins,
            output_pins={str(x):life.digest(x) for x in out.iterdir() if x.is_file()},result=result))
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'qualification-seal.json'))))
    except Exception as error:
        life.save(out/'failure.json',dict(status='SV39_MASKED_QUALIFICATION_HOLD_NOT_ADMITTED',reason=str(error)))
        raise


def lifecycle(rows,vectors,symbols):
    starts,pending,live,intervals={}, {}, {},defaultdict(list)
    req,resp,alloc,done=Counter(),Counter(),Counter(),Counter();rejected=[];previous=-1
    for row in rows:
        event,cycle,seq,tid=row['event'],int(row['cycle']),int(row['order']),int(row['trans_id'])
        require(cycle>=previous,'Reversed event time');previous=cycle
        if event=='arch_start':
            require(seq>=0 and seq not in starts and tid not in pending,'Duplicate architecture/transaction')
            starts[seq]=row;pending[tid]=[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1] and row['insn']==starts[pending[tid][0]]['insn'],
                    'Unknown/duplicate/different CVX request')
            pending[tid][1]=True;req[pending[tid][0]]+=1
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1] and seq==-1 and
                    int(row['pc'],16)==int(row['insn'],16)==0 and int(row['trap']) in (0,1),'Unknown response')
            owner=pending.pop(tid)[0];resp[owner]+=1
            if int(row['trap']):rejected.append(owner)
        elif event in ('uop_alloc','uop_done'):
            vid=int(row['port'])
            require(seq in starts and 0<=vid<8 and tid==int(starts[seq]['trans_id']) and
                    row['insn']==starts[seq]['insn'] and cycle>=int(starts[seq]['cycle']),'Backend owner drift')
            if event=='uop_alloc':
                require(vid not in live,'Live VID reused')
                item=dict(seq=seq,start=cycle,end=None);live[vid]=item;intervals[vid].append(item);alloc[seq,vid,cycle]+=1
            else:
                require(vid in live and live[vid]['seq']==seq and cycle>=live[vid]['start'],'Unowned/early completion')
                live.pop(vid)['end']=cycle;done[seq,vid,cycle]+=1
        else:require(event=='retire','Unknown commit event')
    require(not pending and not live and req==resp==Counter(starts.keys()) and
            Counter((s,v) for s,v,c in alloc.elements())==Counter((s,v) for s,v,c in done.elements()),
            'Incomplete CVX/backend lifecycle')
    faultword=p.WORDS['smuf_masked_load']
    fault=[seq for seq,row in starts.items() if int(row['insn'],16)==faultword]
    require(len(fault)==2 and rejected==[fault[0]] and any(seq==fault[0] for seq,vid,cycle in alloc),
            'Missing exact fault and successful original-opcode retry')
    va,vd,metadata=Counter(),Counter(),{};previous=-1
    for row in vectors:
        cycle,seq,vid,event=int(row['cycle']),int(row['arch_seq']),int(row['vid']),row['event']
        require(cycle>=previous and (int(row['nr_lanes']),int(row['vlen_bits']))==(4,1024),'Native time/geometry')
        previous=cycle
        if event=='config':continue
        require(seq in starts and row['insn']==starts[seq]['insn'] and event in ('alloc','done','write'),'Native owner/opcode')
        if event=='alloc':
            key=seq,vid,cycle;require(key not in metadata,'Duplicate native allocation');metadata[key]=row;va[key]+=1
        else:
            eligible=[a for a in intervals[vid] if a['start']<cycle]
            if not eligible:eligible=[a for a in intervals[vid] if a['start']==cycle]
            require(eligible,'Missing VID history');owner=eligible[-1];key=seq,vid,owner['start']
            require(owner['seq']==seq and owner['start']<=cycle<=owner['end'] and key in metadata and
                    all(row[k]==metadata[key][k] for k in ('insn','use_vd','vd','eew','vl','vstart')),'Native metadata/lifetime drift')
            if event=='done':vd[seq,vid,cycle]+=1
            else:require(int(row['use_vd'])==1 and 0<=int(row['lane'])<4,'Invalid native writer')
    require(va==alloc and vd==done,'Commit/native allocation and completion mismatch')
    return dict(requests=sum(req.values()),responses=sum(resp.values()),exceptions=1,
                fault_arch_seq=fault[0],retry_arch_seq=fault[1],backend_uops=sum(alloc.values()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify','collect'))
    parser.add_argument('--run',type=Path);parser.add_argument('--run-seal')
    parser.add_argument('--plan',type=Path);parser.add_argument('--seal');parser.add_argument('--output',type=Path)
    a=parser.parse_args()
    if a.mode=='prepare':
        require(a.run and a.run_seal and a.output,'Run/seal/output required')
        prepare(a.run.absolute(),a.run_seal,a.output.absolute())
    else:
        require(a.plan and a.seal,'Plan/seal required')
        if a.mode=='collect':
            require(a.output,'Fresh result required');collect(a.plan.absolute(),a.seal,a.output.absolute())
        else:
            plan=life.read_bound(a.plan,a.seal);require(plan['status']==STATUS,'Plan family differs');life.check(plan['pins'])
            print('VERIFY_PASS NO_DUT_READ NO_VCS')


if __name__=='__main__':main()
