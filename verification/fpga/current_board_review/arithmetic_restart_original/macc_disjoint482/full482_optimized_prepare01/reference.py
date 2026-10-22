#!/usr/bin/env python3
"""One bounded Spike execution and one strict raw full482 source-oracle audit."""
import re
import resource
import subprocess
import time
from pathlib import Path
import prepare as p


def memory_width(code,write):
    if code&3!=3:
        quadrant,kind=code&3,(code>>13)&7
        if quadrant in (0,2) and kind in ((6,7) if write else (2,3)):
            return 4 if kind in (2,6) else 8
        return None
    if code&127==(35 if write else 3):
        return 1<<(((code>>12)&7)&3)
    return None


def audit(path,program,gold):
    dis=(p.HERE/'spike/program.dis').read_text()
    routine=p.instructions(dis,'op_0')
    lookup={r['pc']:i for i,r in enumerate(routine)}
    addresses={k:program['symbols'][k]['address'] for k in ('a','b','out','mask','replay_log','tohost')}
    exit_code=p.instructions(dis,'replay_exit')
    exit_store,=[r for r in exit_code if r['text'].startswith('sd\t')]
    main_pcs={r['pc'] for r in p.instructions(dis,'macc_main')}
    line_re=re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    rd_re=re.compile(r'\bx(\d+)\s+(0x[0-9a-f]+)')
    write_re=re.compile(r'\bmem\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s*$')
    read_re=re.compile(r'\bmem\s+(0x[0-9a-f]+)\s*$')
    vec_re=re.compile(r'\bv(\d+)\s+0x([0-9a-f]+)')
    csr_re=re.compile(r'\bc\d+_(vstart|vl|vtype)\s+0x([0-9a-f]+)')
    memory,regs,vectors,csr={}, {0:0}, {}, {}
    counts,calls=[0]*13,[]
    fresh={name:{} for name in ('a','b','out','mask')}
    fresh_byte_writes={name:set() for name in fresh}
    ranges={name:(addresses[name],512 if name in ('a','b') else 514 if name=='out' else 128) for name in fresh}
    step,current,retired,boot=0,None,0,0
    vlenb,capacities=[],[]
    console=bytearray(8192)
    exit_entry_retired=None

    def group(first):
        p.require(all(n in vectors for n in range(first,first+4)),'Missing actual vector group')
        return list(b''.join(vectors[n].to_bytes(128,'little') for n in range(first,first+4)))

    def finish():
        if current is not None:
            p.require(step==0 and current['reads']==set(range(65)) and current['returned_vstart']==0,
                      'Missing65 actual packed reads/full13/returned vstart')
            current.pop('reads')

    with path.open() as stream:
        for lineno,line in enumerate(stream,1):
            p.require('trap_' not in line,'Unexpected reference trap')
            match=line_re.match(line)
            if not match:continue
            pc,code,rest=int(match[1],16),int(match[2],16),match[3]
            if pc<0x80000000:
                boot+=1;continue
            retired+=1
            p.require(retired<=8000000,'Reference retired limit')
            rd,write,load=rd_re.search(rest),write_re.search(rest),read_re.search(rest)
            if pc==program['symbols']['replay_exit']['address']:
                exit_entry_retired=retired-1
                p.require(regs.get(10)==0,'Actual original return not0')
            if code&127==115 and code>>20==0xc22:
                p.require(rd and int(rd[2],16)==128,'Actual vlenb !=128')
                vlenb.append(dict(pc=pc,value=128))
            if pc==p.instructions(dis,'capacity')[1]['pc']:
                p.require(rd and int(rd[1])==10 and int(rd[2],16)==512,'Actual capacity !=512')
                capacities.append(dict(pc=pc,value=512))
            if write and memory_width(code,True):
                address,value=int(write[1],16),int(write[2],16)
                width=memory_width(code,True)
                p.require(width<=8,'Invalid scalar store width')
                for byte in range(width):
                    memory[address+byte]=(value>>(byte*8))&255
                if width==1 and addresses['replay_log']<=address<addresses['replay_log']+8192:
                    console[address-addresses['replay_log']]=value&255
                if pc in main_pcs:
                    for name,(base,length) in ranges.items():
                        if base<=address<base+length:
                            p.require(address+width<=base+length,'Setup write extends initialized range')
                            if width==8:
                                fresh[name][address-base]=dict(value=value,pc=pc)
                            fresh_byte_writes[name].update(range(address-base,address-base+width))
            i=lookup.get(pc)
            if i is not None:
                p.require(i==step and code==int(routine[i]['insn'],16),'Original13 order/encoding')
                if i==0:
                    finish()
                    ordinal=len(calls)
                    p.require(ordinal<482,'Extra original call')
                    row=gold['rows'][ordinal]
                    args=[addresses['a'],addresses['b'],addresses['out']+1,row['vl'],512,addresses['mask'],row['vstart'],0]
                    p.require([regs.get(n) for n in range(10,18)]==args,'Actual helper arguments/ordinary input drift')
                    want={'a':gold['a'],'b':gold['b'],'mask':gold['masks'][row['mode']],
                          'out':[91]+row['old']+[91]}
                    for name,values in want.items():
                        base=addresses[name]
                        p.require(fresh_byte_writes[name]==set(range(len(values))),'Missing fresh complete setup: '+name)
                        p.require([memory.get(base+j) for j in range(len(values))]==values,'Actual setup values: '+name)
                        chunks=16 if name=='mask' else 64
                        p.require(set(fresh[name])==set(range(0,chunks*8,8)),'Missing fresh64-bit setup stores: '+name)
                        for offset,store in fresh[name].items():
                            p.require(store['value']==int.from_bytes(bytes(values[offset:offset+8]),'little'),
                                      'Actual fresh setup store data: '+name)
                    current=dict(trial=ordinal,original_ordinal=ordinal+1,vl=row['vl'],vstart=row['vstart'],
                                 accumulator=row['accumulator'],mode=row['mode'],fresh_setup_bytes=1666,
                                 reads=set(),returned_vstart=None)
                    calls.append(current)
                    fresh={name:{} for name in fresh};fresh_byte_writes={name:set() for name in fresh}
                if i in (0,5,10):
                    p.require(rd and int(rd[1])==5 and int(rd[2],16)==(row['vl'] if i==5 else 512),'Actual vset return')
                if i==8:
                    p.require((csr.get('vl'),csr.get('vtype'),csr.get('vstart'))==(row['vl'],2,row['vstart']),
                              'Actual target CSR state')
                    p.require(group(8)==gold['a'] and group(16)==gold['b'] and group(24)==row['old'],
                              'Actual target full source/old vd')
                    p.require(0 in vectors and vectors[0]&((1<<512)-1)==
                              int.from_bytes(bytes(gold['masks'][row['mode']][:64]),'little'),'Actual target predicate')
                    p.require(regs.get(28)==0 and regs.get(16)==row['vstart'] and regs.get(17)==0,'Actual scalar/start/rm')
                    current['target']=dict(pc=pc,opcode='b5042c57',retired=retired,trace_line=lineno)
                if i==9:
                    p.require(rd and int(rd[1])==10 and int(rd[2],16)==0,'Actual returned vstart')
                    current['returned_vstart']=0
                if i==11:
                    p.require(group(24)==row['output'] and csr.get('vl')==512,'Actual full vector result store')
                counts[i]+=1;step=(step+1)%13
            for n,value in vec_re.findall(rest):vectors[int(n)]=int(value,16)
            for name,value in csr_re.findall(rest):csr[name]=int(value,16)
            if i==8:
                p.require(group(24)==row['output'] and csr.get('vstart')==0,'Actual target full result/reset')
            if current is not None and load and memory_width(code,False):
                address=int(load[1],16)
                if addresses['out']<=address<addresses['out']+520:
                    p.require(step==0 and rd and memory_width(code,False)==8 and
                              (address-addresses['out'])%8==0,'Oracle must be actual aligned scalar LD')
                    chunk=(address-addresses['out'])//8
                    p.require(chunk not in current['reads'],'Duplicate actual oracle read')
                    expected=[91]+row['output']+[91]
                    want=int.from_bytes(bytes(expected[chunk*8:chunk*8+8]),'little')
                    value=int(rd[2],16)
                    mask=0xffff if chunk==64 else (1<<64)-1
                    p.require((value&mask)==want,'Full oracle/guard mismatch call'+str(len(calls)))
                    current['reads'].add(chunk)
            if rd:regs[int(rd[1])]=int(rd[2],16)
            if pc==exit_store['pc']:
                p.require(write and int(write[1],16)==addresses['tohost'] and int(write[2],16)==1,'Actual HTIF exit not0')
                finish()
                p.require(len(calls)==482 and counts==[482]*13 and len(vlenb)==2 and len(capacities)==1,
                          'Full482/13/vlenb/capacity coverage missing')
                text=console.split(b'\0',1)[0].decode('ascii')
                for marker in program['pass_markers']:
                    p.require(text.splitlines().count(marker)==1,'Raw oracle marker absent/ambiguous')
                p.require(not re.search(r'FAIL|TRAP|UNSUPPORTED|MISMATCH|DETAIL',text),'Raw console veto')
                traces=re.findall(r'RVV_TRIAL seed=(\d+) vl=(\d+) mask=(\d+) vstart=(\d+) completed=(\d+)',text)
                expected_traces=[('0',str(r['vl']),'0',str(r['vstart']),str(r['trial'])) for r in gold['rows']
                                 if r['mode']==0 and r['accumulator']==0]
                p.require(traces==expected_traces and len(traces)==26,'Original26 boundary prints changed')
                return dict(status='PASS_SPIKE_FULL482_FRESH_SETUP_ORIGINAL13_COMPLETE_ORACLE_NOT_DUT',
                    actual_calls=482,predecessors=481,results=246784,guards=964,packed_output_reads=65*482,
                    returned_vstart_zero=482,actual_helper_retire_counts=counts,helper_instructions=sum(counts),
                    actual_setup_bytes_each_call=1666,actual_vlenb=vlenb,actual_capacity=capacities,
                    raw_firmware_retired_to_exit_entry=exit_entry_retired,raw_firmware_retired_to_HTIF=retired,
                    boot_retired=boot,original_boundary_prints=traces,reconstructed_console=text,calls=calls,
                    actual_HTIF_store_value=1,ignored_final_word_high_bytes=6,raw_commit_parses=1)
    raise ValueError('Reference never reached full-oracle architectural exit0')


def main():
    folder=p.HERE/'reference'
    try:
        p.require(not folder.exists(),'Exactly one fresh reference; no retry')
        ready=p.read(p.HERE/'PRE_REFERENCE.json')
        for path,digest in ready['pins'].items():p.require(p.sha(path)==digest,'Static/Host/build input drift '+path)
        program=ready['programs']['spike'];folder.mkdir()
        symbols=program['symbols'];commands=folder/'spike.cmd'
        commands.write_text(f'until pc 0 {symbols["replay_exit"]["address"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {symbols["replay_log"]["address"]:x}\nrs 16\nquit\n')
        command=[str(p.SPIKE),'-d','--debug-cmd='+str(commands),'--isa='+p.ISA,'-m2',
                 '--log-commits','--log='+str(folder/'commits.log'),program['path']]
        p.save(folder/'command.json',dict(command=command,timeout_s=120,max_raw_bytes=768*1024*1024,
            max_audited_retired=8000000,reference_invocations=1,no_new_vstart_probe=True))
        started=time.monotonic()
        def bound():resource.setrlimit(resource.RLIMIT_FSIZE,(768*1024*1024,768*1024*1024))
        with (folder/'spike.log').open('x') as stream:
            result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=120,preexec_fn=bound)
        execution=dict(command=command,actual_child_returncode=result.returncode,elapsed_s=time.monotonic()-started,
                       timeout_s=120,retries=0)
        p.save(folder/'execution.json',execution)
        p.require(type(result.returncode) is int and result.returncode==0,'Reference actual child nonzero')
        text=(folder/'spike.log').read_text()
        values=re.findall(r'^0x([0-9a-f]{16})$',text,re.M)
        p.require(len(values)==3 and int(values[0],16)==0,'Reference actual return/counter receipts')
        report=audit(folder/'commits.log',program,p.read(p.HERE/'model.json'))
        report.update(actual_execution=execution,minstret_to_replay_exit=int(values[1],16),mcycle_at_exit=int(values[2],16),
                      raw_commit_sha256=p.sha(folder/'commits.log'),raw_commit_bytes=(folder/'commits.log').stat().st_size)
        p.require(report['minstret_to_replay_exit']==report['raw_firmware_retired_to_exit_entry']+report['boot_retired'],
                  'Counter vs actual raw retirement mismatch')
        p.save(folder/'status.json',report)
        p.require(all(p.sha(path)==digest for path,digest in ready['pins'].items()),'Prepared inputs changed')
        base_cost=16438522
        retired=report['minstret_to_replay_exit']
        # Use the slow archived cross-suite proxy; this is not a measured M8 bound.
        proxy=retired*0.001330
        with_margin=proxy*1.5+600
        status=dict(status='READY_SOURCE_EQUIVALENT_FULL482_OPTIMIZED_REFERENCE_ONLY_NOT_DUT',
            source_label='rvv_integer_macc_accumulators_restart_e8_m4',runtime_id=p.ID,
            calls=482,predecessors=481,results=246784,guards=964,helper_instructions=6266,
            capacity=512,vlenb=128,physical_mask_bytes=128,patterns=5,
            original_linux_ELF_sha256='608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d',
            optimized_ELF_not_original_linux=True,programs=ready['programs'],reference_sha256=p.sha(folder/'status.json'),
            actual_reference_child_returncode=result.returncode,actual_min_stret_to_exit=retired,
            original_reference_retired=base_cost,retired_reduction_fraction=1-retired/base_cost,
            budget_projection=dict(archived_proxy_s_per_instruction=0.001330,estimated_DUT_s=proxy,
                safety_factor=1.5,extra_margin_s=600,estimated_s_including_margin=with_margin,
                fits_10800s_case=with_margin<=10800,not_M8_cycle_or_wall_evidence=True),
            M8_plan_proposed_only_if_budget_fits=with_margin<=10800,DUT_runs=0,VCS_started=False,
            full22400_accepted=False,original_Linux_history_closed=False,
            input_pins_unchanged=True,pins={str(path):p.sha(path) for path in p.HERE.rglob('*') if path.is_file()})
        p.save(p.HERE/'READY.json',status)
        print('FULL482_REFERENCE_PASS',retired,'retired; margin_s',round(with_margin,3),flush=True)
    except BaseException as error:
        p.save(p.HERE/'REFERENCE_STOPPED.json',dict(status='REFERENCE_FAILED_NO_RETRY',error=repr(error),DUT_runs=0))
        raise


if __name__=='__main__':main()
