#!/usr/bin/env python3
"""One complete bounded Spike measurement; no DUT admission or retry."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import time
import prepare as p
from model import generate
HERE=Path(__file__).resolve().parent

def width(code,write):
    if code&3!=3:
        quadrant,kind=code&3,(code>>13)&7
        if quadrant in (0,2) and kind in ((6,7) if write else (2,3)):
            return 4 if kind in (2,6) else 8
        return None
    if code&127==(35 if write else 3):return 1<<(((code>>12)&7)&3)
    return None

def require(ok,why):
    if not ok:raise ValueError(why)

def audit(raw):
    seeds,rows,dictionary,masks=generate()
    symbols=json.loads((HERE/'spike/symbols.json').read_text())
    proof=json.loads((HERE/'proof.json').read_text())['backends']['spike']
    helpers=proof['helpers'];lookup={i['pc']:(op,j,i['insn']) for op in range(25)
        for j,i in enumerate(helpers[f'op_{op}'])}
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
        (HERE/'spike/program.dis').read_text(),re.M)}
    regex=re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    rd_regex=re.compile(r'\bx\s*(\d+)\s+(0x[0-9a-f]+)')
    mem_regex=re.compile(r'\bmem\s+(0x[0-9a-f]+)(?:\s+(0x[0-9a-f]+))?')
    vec_regex=re.compile(r'\bv\s*(\d+)\s+0x([0-9a-f]+)')
    csr_regex=re.compile(r'\bc\d+_(vstart|vl|vtype)\s+0x([0-9a-f]+)')
    regs={0:0};memory={};vectors={};csrs={};fresh=set();reads=set()
    ordinal=0;step=0;counts=[0]*13;retired=0;boot=0;capacity=0;row=None
    exit_entry=None;read_count=0;context=None
    a,b,out,mask=(symbols[n] for n in ('a','b','out','mask'))
    expected=None
    def group(first):
        require(all(n in vectors for n in range(first,first+4)),'Missing physical vector group')
        return b''.join(vectors[n].to_bytes(128,'little') for n in range(first,first+4))
    def finish_call():
        if row is not None:require(step==0 and reads==set(range(65)),f'call{ordinal}: incomplete13/full65 oracle reads')
    with raw.open() as stream:
        for lineno,line in enumerate(stream,1):
            require('trap_' not in line,f'Unexpected reference trap line{lineno}')
            match=regex.match(line)
            if not match:continue
            pc,insn,rest=int(match[1],16),int(match[2],16),match[3]
            if pc<0x80000000:boot+=1;continue
            retired+=1
            require(retired<=6000000,'Hard reference instruction bound')
            require(code.get(pc)==insn,f'PC/code mismatch pc{pc:x}')
            rd=rd_regex.search(rest);mem=mem_regex.findall(rest)
            context=dict(line=lineno,retired=retired,call=ordinal,pc=f'{pc:08x}',insn=f'{insn:08x}')
            if pc==symbols['replay_exit']:
                require(regs.get(10)==0,'Original software return nonzero');exit_entry=retired-1
            if pc==helpers['capacity'][1]['pc']:
                require(rd and int(rd[2],16)==512,'Capacity not512');capacity+=1
            w=width(insn,True)
            if w:
                require(len(mem)==1 and mem[0][1],'Scalar store log schema')
                address,value=int(mem[0][0],16),int(mem[0][1],16)
                for j in range(w):memory[address+j]=(value>>(8*j))&255
                if out<=address<out+514:
                    require(address+w<=out+514,'Output setup writes beyond exact514')
                    fresh.update(range(address-out,address-out+w))
            h=lookup.get(pc)
            if h is not None:
                op,j,want_insn=h
                require(j==step and insn==want_insn,'Original helper PC/order/machine code')
                if j==0:
                    finish_call();require(ordinal<4095,'Extra helper call')
                    row=rows[ordinal];ordinal+=1;reads=set()
                    require(op==row['op'],'Original helper order')
                    require([regs.get(n) for n in range(10,17)]==[a,b,out+1,row['vl'],512,mask,row['start']],
                        'Actual helper arguments/source context')
                    for base,want in ((a,seeds[row['seed']]['a']),(b,seeds[row['seed']]['b']),
                        (out,[91]*514),(mask,list(masks[row['mode']]))):
                        require([memory.get(base+k) for k in range(len(want))]==want,'Actual initialized bytes '+str(base))
                    require(fresh==set(range(514)),'Every call fresh exact514 setup');fresh=set()
                    expected=b''.join(dictionary[ix].to_bytes(8,'little') for ix in row['indices'])[:514]
                else:require(row and op==row['op'],'Cross-helper replay')
                if j in (0,5,10):
                    require(rd and int(rd[1])==5 and int(rd[2],16)==(row['vl'] if j==5 else 512),'vsetvl result')
                if j==8:
                    require((csrs.get('vl'),csrs.get('vtype'),csrs.get('vstart'))==(row['vl'],2,row['start']),
                        'Target CSR context')
                    require(group(8)==bytes(seeds[row['seed']]['a']) and group(16)==bytes(seeds[row['seed']]['b']) and
                        group(24)==bytes([91]*512),'Actual physical inputs/old vd')
                    require(0 in vectors and (vectors[0]&((1<<512)-1))==int.from_bytes(masks[row['mode']][:64],'little'),
                        'Actual predicate used')
                    require(regs.get(28)==7,'Original immediate scalar t3')
                if j==9:require(rd and int(rd[1])==10 and int(rd[2],16)==0,'Returned vstart')
                if j==11:require(group(24)==expected[1:513] and csrs.get('vl')==512,'Complete stored vector output')
                counts[j]+=1;step=(step+1)%13
            for n,v in vec_regex.findall(rest):vectors[int(n)]=int(v,16)
            for name,v in csr_regex.findall(rest):csrs[name]=int(v,16)
            if h and h[1]==8:
                require(group(24)==expected[1:513] and csrs.get('vstart')==0,'Target full bitwise output/reset')
            rwidth=width(insn,False)
            if rwidth and mem:
                require(len(mem)==1 and not mem[0][1],'Scalar read log schema')
                address=int(mem[0][0],16)
                if out<=address<out+514:
                    require(row is not None and step==0 and rd,'Output read outside scalar oracle')
                    offset=address-out;chunk=offset//8
                    require(offset%8==0 and rwidth==(2 if offset==512 else 8) and chunk not in reads,
                        'Oracle exact aligned64+tail2 reads')
                    require(int(rd[2],16)==int.from_bytes(expected[offset:offset+rwidth],'little'),
                        f'call{ordinal} full bitwise output/guard mismatch offset{offset} line{lineno}')
                    reads.add(chunk);read_count+=1
            if rd:
                n=int(rd[1]);regs[n]=int(rd[2],16) if n else 0
            if w and mem and int(mem[0][0],16)==symbols['tohost']:
                require(int(mem[0][1],16)==1 and exit_entry is not None,'Actual HTIF not success1')
                finish_call();require(ordinal==4095 and counts==[4095]*13 and capacity==1,'Incomplete full4095/helper coverage')
                console=bytes(memory.get(symbols['replay_log']+k,0) for k in range(8192)).split(b'\0',1)[0].decode('ascii')
                marker='RVV_MATRIX_PASS sew=8 vlmax=512 cases=4095 elements=2096640 errors=0 seeds=3 guard_tail_mask_vstart=checked'
                require(console.splitlines()==[marker] and not re.search('FAIL|TRAP|UNSUPPORTED',console),'Raw full original console veto')
                return dict(status='ACCEPTED_FULL4095_SPIKE_SOURCE_ONLY_NOT_DUT',calls=ordinal,results=2096640,
                    guards=8190,vstart_zero=4095,helper_instruction_counts=counts,helper_instructions=sum(counts),
                    packed_output_reads=read_count,per_call_fresh_output_bytes=514,physical_mask_bytes=128,
                    firmware_to_exit=exit_entry,firmware_to_HTIF=retired,boot=boot,console=console,closed_raw_parses=1,
                    final_context=context)
    raise ValueError('Reference ended without architectural full4095 exit: '+repr(context))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--review-sha',required=True);args=parser.parse_args()
    require(p.sha(args.review)==args.review_sha,'Independent review hash')
    review=json.loads(args.review.read_text())
    require(review['status']=='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT' and
        review['pins_sha256']==p.sha(HERE/'pins.json') and
        review['proof_sha256']==p.sha(HERE/'proof.json') and
        review['software_status_sha256']==p.sha(HERE/'software_status.json') and
        review['reference_authorization']['one_attempt'] is True and
        review['reference_authorization']['DUT_authorized'] is False,
        'Actual independent software review binding')
    pins=json.loads((HERE/'pins.json').read_text())
    pins.update({str(HERE/'pins.json'):p.sha(HERE/'pins.json'),str(__file__):p.sha(__file__),
        str(args.review):args.review_sha,str(HERE/'software_status.json'):p.sha(HERE/'software_status.json')})
    require(all(p.sha(path)==digest for path,digest in pins.items()),'Prepared source/ELF pin drift')
    folder=HERE/'reference01';folder.mkdir()
    p.save(folder/'preflight_pins.json',pins)
    symbols=json.loads((HERE/'spike/symbols.json').read_text())
    commands=folder/'spike.cmd'
    p.emit(commands,f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {symbols["replay_log"]:x}\nrs 16\nquit\n')
    command=[str(p.old.SPIKE),'-d','--debug-cmd='+str(commands),'--isa=rv64gcv_zvl1024b','-m2',
        '--instructions=6000000','--log-commits','--log='+str(folder/'commits.log'),str(HERE/'spike/program.elf')]
    p.save(folder/'command.json',dict(command=command,timeout_s=120,hard_steps=6000000,
        admission_target=3000000,max_raw_bytes=768*1024**2,reference_invocations=1,
        review=str(args.review),review_sha256=args.review_sha,executor_sha256=p.sha(__file__)))
    start=time.monotonic();timeout=False
    def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(768*1024**2,768*1024**2))
    with (folder/'spike.log').open('x') as stream:
        child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,preexec_fn=limits)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timeout=True;child.kill();rc=child.wait()
        p.save(folder/'execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
            elapsed_s=time.monotonic()-start,timed_out=timeout,retries=0,validated=False))
    try:
        require(rc==0 and not timeout,'Actual reference numeric outcome')
        values=re.findall(r'^0x([0-9a-f]{16})$',(folder/'spike.log').read_text(),re.M)
        require(len(values)==3 and int(values[0],16)==0,'Actual counter/return receipts')
        report=audit(folder/'commits.log')
        require(int(values[1],16)==report['firmware_to_exit']+report['boot'],'Actual firmware counter vs raw')
        unchanged=all(p.sha(path)==digest for path,digest in pins.items())
        require(unchanged,'Post-reference source pin drift')
        report.update(raw_sha256=p.sha(folder/'commits.log'),raw_bytes=(folder/'commits.log').stat().st_size,
            actual_counter=int(values[1],16),execution_sha256=p.sha(folder/'execution.json'),pins_pre_post_unchanged=unchanged)
        p.save(folder/'result.json',report)
        within=report['firmware_to_exit']<=3000000
        p.save(HERE/('READY.json' if within else 'HOLD.json'),dict(
            status='READY_SOFTWARE_REFERENCE_ONLY_NO_DUT' if within else 'HOLD_ACTUAL_REFERENCE_COST_OVER_3M',
            firmware=report['firmware_to_exit'],reference_sha256=p.sha(folder/'result.json'),
            source_pins_sha256=p.sha(HERE/'pins.json'),review_sha256=args.review_sha,
            full_calls=4095,results=2096640,guards=8190,DUT_runs=0,
            cost_proxy_retire_per_s=403.97,projection_s_with_20_percent_margin=report['firmware_to_exit']/403.97*1.2,
            projection_not_DUT_guarantee=True))
        print('READY' if within else 'HOLD',report['firmware_to_exit'],flush=True)
    except BaseException as error:
        p.save(folder/'STOPPED.json',dict(status='REFERENCE_OR_OBSERVER_FAILURE_NO_RETRY',first_cause=repr(error),
            execution_sha256=p.sha(folder/'execution.json'),DUT_runs=0))
        raise

if __name__=='__main__':main()
