"""One streaming original1134 Spike oracle audit. No execution or source edits."""
import argparse
import hashlib
import re
import sys
import time
from pathlib import Path
from coverage_gate import SetupLedger, word_read
from completion_cache import CompletionCache
from prepare import HERE, read, save, sha, require, pins_check, LIMIT
sys.dont_write_bytecode=True
sys.path.insert(0,str(HERE.parents[3]/'coverage'))
from scoped_rv64c_memory import decode as compressed

LINE=re.compile(rb'^core\s+0:\s+[0-3]\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$')
RD=re.compile(rb'\bx\s*(\d+)\s+0x([0-9a-f]+)')
MEM=re.compile(rb'\bmem\s+0x([0-9a-f]+)(?:\s+0x([0-9a-f]+))?')
MASK=(1<<64)-1

def descriptor(ins):
    if ins&3!=3:return compressed(ins)
    op=ins&127;f=(ins>>12)&7
    if op not in (3,35):return None
    require(f in ((0,1,2,3,4,5,6) if op==3 else (0,1,2,3)),'Scalar width')
    imm=ins>>20 if op==3 else (ins>>25<<5)|((ins>>7)&31)
    if imm&2048:imm-=4096
    return dict(kind='read' if op==3 else 'write',size=1<<(f&3),base=(ins>>15)&31,
                register=(ins>>(7 if op==3 else 20))&31,offset=imm)

def next_helper_pc(pc,ins,regs):
    size=4 if ins&3==3 else 2
    if ins==0x8082:return regs[1]&~1
    if ins&3!=3:
        # The exact original helpers use compressed J, BEQZ/BNEZ, and scalar LI.
        f=ins>>13
        if f==5:
            imm=((ins>>12)&1)<<11|((ins>>11)&1)<<4|((ins>>9)&3)<<8|((ins>>8)&1)<<10|((ins>>7)&1)<<6|((ins>>6)&1)<<7|((ins>>3)&7)<<1|((ins>>2)&1)<<5
            if imm&2048:imm-=4096
            return pc+imm
        if f in (6,7):
            imm=((ins>>12)&1)<<8|((ins>>10)&3)<<3|((ins>>5)&3)<<6|((ins>>3)&3)<<1|((ins>>2)&1)<<5
            if imm&256:imm-=512
            value=regs[8+((ins>>7)&7)]
            return pc+imm if (value==0)==(f==6) else pc+2
    if ins&127==0x63:
        f=(ins>>12)&7;require(f in (0,1),'Unexpected helper branch')
        imm=((ins>>31)&1)<<12|((ins>>7)&1)<<11|((ins>>25)&63)<<5|((ins>>8)&15)<<1
        if imm&4096:imm-=8192
        equal=regs[(ins>>15)&31]==regs[(ins>>20)&31]
        return pc+imm if equal==(f==0) else pc+4
    if ins&127==0x6f:
        imm=((ins>>31)&1)<<20|((ins>>12)&255)<<12|((ins>>20)&1)<<11|((ins>>21)&1023)<<1
        if imm&(1<<20):imm-=1<<21
        return pc+imm
    return pc+size

def audit(digest):
    bound=read(HERE/'reference_bound01.json')
    require(sha(HERE/'reference_bound01.json')==digest,'Reference bound identity')
    pins_check(bound['pins'])
    spec=read(HERE/'sourceproof.json')['backends']['spike'];s=spec['symbols'];code={int(k):v for k,v in spec['code'].items()}
    gold=read(HERE/'tuples.json')['cases'];entries={s['op_'+str(op)]:op for op in range(20)}
    lookup={x['pc']:int(op) for op,w in spec['helpers'].items() for x in w}
    targets={int(op):next(w[i-1]['pc'] for i,x in enumerate(w) if x['insn']==0x00802573) for op,w in spec['helpers'].items()}
    regs={0:0};memory={};calls=[];active=None;helper=None;nextpc=None
    counts=dict(steps=0,firmware=0,boot=0,parking=0,vlenb=0,helper_instructions=0)
    exited=False;through=None;numbers=[];exits=[];hasher=hashlib.sha256()
    trace=HERE/'reference01/commits.log';before=trace.stat();began=time.monotonic()
    def val(addr,n):
        require(all(addr+i in memory for i in range(n)),'Missing initialized memory')
        return sum(memory[addr+i]<<(i*8) for i in range(n))
    completion = CompletionCache()
    setup = SetupLedger(s['input'], s['output']); armed = False
    def finish_call():
        completion.finish(active)
    with trace.open('rb') as stream:
        for line_no,line in enumerate(stream,1):
            hasher.update(line)
            require(b'trap_' not in line,'Reference trap line '+str(line_no))
            m=LINE.match(line)
            if not m:
                require(not line.strip(),'Unrecognized commit line '+str(line_no))
                continue
            counts['steps']+=1;require(counts['steps']<=LIMIT,'40M instruction bound')
            pc,ins,tail=int(m[1],16),int(m[2],16),m[3]
            updates=RD.findall(tail);require(len(updates)<=1,'Multiple GPR updates')
            rd,value=(int(updates[0][0]),int(updates[0][1],16)) if updates else (0,0)
            if pc<0x80000000:
                require(counts['firmware']==0,'Boot after firmware');counts['boot']+=1
                if rd:regs[rd]=value
                continue
            counts['firmware']+=1;require(code.get(pc)==ins,'Actual ELF PC/code mismatch '+hex(pc))
            if exited:
                require(pc==park and ins in (0xa001,0x0000006f),'Nonparking after HTIF')
                counts['parking']+=1;continue
            require(pc!=s['trap_entry'],'Trap entry')
            if pc == s['whole_original_main']:
                require(not armed, 'Repeated main entry'); armed = True
            if pc in entries:
                finish_call();require(helper is None and len(calls)<1134,'Extra/overlap helper')
                require(armed, 'Helper before original main'); setup.enter()
                c=gold[len(calls)];require(entries[pc]==c['op'],'Original seed/op/mode/start order')
                require([regs.get(r) for r in range(10,14)]==[s['input'],s['output']+32,c['start'],c['mode']],'Original ABI arguments')
                require([val(s['input']+i,1) for i in range(1024)]==[(i*37+c['seed']*71+3)&255 for i in range(1024)],'Full input setup')
                require(all(val(s['output']+i,1)==91 for i in range(1088)),'Full output sentinel setup')
                active=dict(ordinal=len(calls),tuple=c,reads=set(),returned=False,csrs=[],preloads=0,stores=0,entry_step=counts['firmware'])
                calls.append(active);helper=c['op'];nextpc=pc
            if helper is not None:
                require(pc==nextpc and lookup.get(pc)==helper,'Original helper branch/path/window')
                nextpc=next_helper_pc(pc,ins,regs);counts['helper_instructions']+=1
                c=active['tuple']
                if pc in (s['op_'+str(helper)]+4,s['op_'+str(helper)]+8):active['preloads']+=1
                if pc==targets[helper]:
                    require(active['preloads']==2 and active['csrs']==[c['start']],'Target before setup')
                    active['target_pc']=pc;active['target_step']=counts['firmware']
                if ins&127==0x73 and ins>>20==8 and (ins>>12)&7==2:
                    require(rd in (28,10),'Unexpected vstart result destination')
                    expected=c['start'] if not active['csrs'] else 0
                    require(value==expected and len(active['csrs'])<2,'Actual vstart readback')
                    active['csrs'].append(value)
                if ins&127==39:
                    require(active['csrs']==[c['start'],0] and regs.get((ins>>15)&31)==s['output']+32,'Whole output store')
                    active['stores']+=1
                if ins==0x8082:
                    require(regs.get(10)==c['start']<<32 and active['stores']==1,'Original returned status')
                    active['returned']=True;helper=None
            else:
                require(pc not in lookup,'Interior helper entry')
            vector=ins&127==0x57 or ins&127 in (7,39) and (ins>>12)&7 in (0,5,6,7)
            require(not vector or pc in lookup,'Extra vector verification instruction')
            if ins&127==0x73 and ins>>20==0xc22:
                require(not calls and rd and value==128,'Actual vlenb128');counts['vlenb']+=1
            if pc==s.get('num'):
                numbers.append(regs.get(10))
            if pc==s['replay_exit']:
                require(regs.get(10)==0,'Nonzero raw firmware exit');exits.append(0)
            desc=descriptor(ins)
            if desc:
                mem=MEM.findall(tail);require(len(mem)==1,'Scalar memory evidence')
                addr=int(mem[0][0],16);size=desc['size']
                require(desc['base'] in regs and addr==(regs[desc['base']]+desc['offset'])&MASK,'Scalar effective address')
                if desc['kind']=='write':
                    require(mem[0][1],'Missing actual store payload');data=int(mem[0][1],16)
                    if armed and (s['input']<=addr<s['input']+1024 or s['output']<=addr<s['output']+1088):
                        require(helper is None and len(calls)<1134, 'Setup write phase')
                        finish_call()
                        setup.store(addr,size,data,gold[len(calls)])
                    for i in range(size):memory[addr+i]=(data>>(i*8))&255
                    if addr==s['tohost']:
                        require(size==8 and data==1 and regs.get(10)==1 and exits==[0],'Actual successful HTIF')
                        finish_call();require(len(calls)==1134,'Early HTIF')
                        exited=True;through=counts['firmware'];park=pc+(4 if ins&3==3 else 2)
                elif s['output']<=addr<s['output']+1088:
                    require(active is not None and helper is None and active['returned'] and addr+size<=s['output']+1088,'Output oracle phase/bounds')
                    require(rd==desc['register'],'Output read destination')
                    word_read(active,addr-s['output'],size,value)
            if rd:regs[rd]=value
            regs[0]=0
    finish_call();setup.finish();after=trace.stat()
    require((before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'Raw identity drift')
    require(exited and len(calls)==1134 and counts['vlenb']==2,'Incomplete original whole sequence')
    require(numbers==[1134,366,0],'Original final case/skip/error counters')
    console=bytes(val(s['replay_log']+i,1) for i in range(val(s['replay_log_count'],8))).decode('ascii')
    expected='RVV_WHOLE_PASS cases=1134 skips=366 errors=0\nBOARD_CASE_PASS whole_all\nBOARD_REPLAY_PASS\n'
    require(console==expected,'Exact full original console/failure veto')
    pins_check(bound['pins'])
    save(HERE/'reference01/reference.json',dict(status='FULL1134_PACKED_REFERENCE_PASS_NOT_DUT',calls=1134,exclusions=366,
        fresh_input_stores=setup.input_stores,fresh_output_stores=setup.output_stores,output_word_reads=1134*136,
        output_byte_checks=1134*1088,input_bytes_per_call=1024,output_bytes_per_call=1088,vstart_reads=2268,
        raw_exit=0,htif=1,firmware_through_htif=through,counts=counts,console=console,numbers=numbers,
        raw_sha256=hasher.hexdigest(),raw_bytes=after.st_size,raw_identity=dict(inode=after.st_ino,mtime_ns=after.st_mtime_ns,ctime_ns=after.st_ctime_ns),
        call_ledger=[{k:v for k,v in c.items() if k!='reads'} for c in calls],full_raw_parses=1,
        elapsed_s=time.monotonic()-began,original_source_order=True,partitioned=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bound-sha256',required=True);a=p.parse_args()
    try:audit(a.bound_sha256)
    except Exception as e:
        save(HERE/'reference01/first_audit_error.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=str(e)))
        raise


