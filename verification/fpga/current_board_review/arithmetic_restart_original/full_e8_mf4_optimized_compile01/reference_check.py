"""Read-only full Spike check: original helper windows, setup and every result."""
import re
import sys
from pathlib import Path
sys.dont_write_bytecode=True
from prepare import HERE,read,sha,require,marker,CAP
from bss_guard import BSSGuard
sys.path.insert(0,str(HERE.parents[3]/'coverage'))
from scoped_rv64c_memory import decode as compressed_memory

LINE=re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
RD=re.compile(r'\bx\s*(\d+)\s+(0x[0-9a-f]+)')
WRITE=re.compile(r'\bmem\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s*$')
READ=re.compile(r'\bmem\s+(0x[0-9a-f]+)\s*$')

def audit(root,trace):
    proof=read(root/'sourceproof.json');p=proof['case'];spec=proof['backends']['spike']
    require(sha(spec['elf'])==spec['sha256'],'Reference ELF drift')
    gold=read(root/'model.json');symbols=spec['symbols'];code={int(k):v for k,v in spec['code'].items()}
    failure_entries={address for name,address in symbols.items() if name=='failure' or name.startswith('failure.')}
    require(failure_entries,'Actual compiler failure entry required')
    helpers=spec['helpers'];lookup={r['pc']:(name,i) for name,window in helpers.items() for i,r in enumerate(window)}
    regs={0:0};memory={};steps=0;fw=0;parking=0;boot=0;calls=[];active=None;helper=None;index=0;capacity=0
    exited=False;through_htif=None;width=p['sew']//8;console=bytearray(8192);vlenb_reads=0
    boot_guard=BSSGuard(symbols,code)
    def value(addr,size):
        require(all(addr+i in memory for i in range(size)),'Missing initialized byte '+hex(addr))
        return sum(memory[addr+i]<<(8*i) for i in range(size))
    def finish_call():
        if active is not None:
            require(helper is None and active['reads']==set(range(CAP+2)) and active['returned_vstart']==0,
                    'Incomplete original helper/oracle/guards/CSR call '+str(active['ordinal']))
            active['reads']=sorted(active['reads'])
    with trace.open() as stream:
        for lineno,line in enumerate(stream,1):
            require('trap_' not in line,'Unexpected reference trap line'+str(lineno))
            m=LINE.match(line)
            if not m:continue
            steps+=1;require(steps<=p['steps'],'Step ceiling')
            pc,insn,rest=int(m[1],16),int(m[2],16),m[3]
            if pc<0x80000000:
                require(not fw,'Boot after firmware');boot+=1
            else:
                require(code.get(pc)==insn,'Actual firmware PC/code mismatch '+hex(pc));fw+=1
            if exited:
                require(insn in (0xa001,0x0000006f) and pc in code,'Nonparking after original HTIF')
                parking+=1;continue
            rd=RD.search(rest);write=WRITE.search(rest);readmem=READ.search(rest)
            if insn&127==0x73 and insn>>20==0xc22:
                require(not calls and capacity==0 and rd and int(rd[2],16)==128,'Exact initial vlenb128')
                vlenb_reads+=1
            boot_guard.pc(pc)
            if pc in failure_entries:
                raise ValueError('Original scalar oracle entered failure()')
            if pc in lookup:
                name,i=lookup[pc]
                if i==0:
                    require(helper is None,'Overlapping helper')
                    if name=='capacity':
                        require(not calls and capacity==0,'Capacity repeated');capacity+=1
                    else:
                        finish_call();ordinal=len(calls)
                        require(ordinal<len(gold),'Extra original call');g=gold[ordinal]
                        require(name==f'op_{g["op"]}','Original operation order')
                        args=[symbols['a'],symbols['b'],symbols['out']+width,g['vl'],CAP,symbols['mask'],g['vstart']]
                        require([regs.get(r) for r in range(10,17)]==args,'Original setup args '+str(ordinal))
                        for n,values,size in (('a',g['a'],width),('b',g['b'],width),('mask',g['mask'],1),('out',[91]*(CAP+2),width)):
                            require([value(symbols[n]+j*size,size) for j in range(len(values))]==values,'Full setup/RNG/FP transition '+n)
                        active=dict(ordinal=ordinal,op=g['op'],seed=g['seed'],vl=g['vl'],mode=g['mode'],vstart=g['vstart'],
                            entry_step=steps,args=args,reads=set(),returned_vstart=None)
                        calls.append(active)
                    helper=name;index=0
                require(helper==name and index==i,'Contiguous full helper window')
                if name=='capacity' and i==1:require(rd and int(rd[2],16)==CAP,'Actual VLMAX32')
                if name!='capacity':
                    g=gold[active['ordinal']]
                    if i in (0,5,10):require(rd and int(rd[1])==5 and int(rd[2],16)==(g['vl'] if i==5 else CAP),'Actual helper VL')
                    if i==8:
                        require(regs.get(28)==7 and regs.get(16)==g['vstart'],'Original scalar7/start at target')
                        active['target_step']=steps;active['target_pc']=pc;active['target_insn']=insn
                    if i==9:
                        require(rd and int(rd[1])==10 and int(rd[2],16)==0,'Returned vstart')
                        active['returned_vstart']=0
                index+=1
                if index==len(helpers[name]):helper=None;index=0
            elif helper is not None:raise ValueError('Execution left original helper window')
            if pc>=0x80000000 and (insn&127==0x57 or insn&127 in (7,39) and (insn>>12)&7 in (0,5,6,7)):
                require(pc in lookup,'Unexpected vector PC')
            if write:
                desc=compressed_memory(insn) if insn&3!=3 else None
                size=desc['size'] if desc and desc['kind']=='write' else (1<<((insn>>12)&7) if insn&127==35 else 0)
                if size:
                    require(size<=8,'Scalar write width')
                    addr,val=int(write[1],16),int(write[2],16)
                    boot_guard.store(pc,insn,addr,val,size,regs,len(calls))
                    for j in range(size):memory[addr+j]=(val>>(8*j))&255
                    if symbols['replay_log']<=addr<symbols['replay_log']+8192:
                        for j in range(size):console[addr-symbols['replay_log']+j]=(val>>(8*j))&255
                    if addr==symbols['tohost']:
                        require(val==1 and size==8 and regs.get(10)==1,'Actual HTIF zero exit')
                        finish_call();exited=True;through_htif=fw
            if active is not None and readmem and rd:
                addr=int(readmem[1],16)
                if symbols['out']<=addr<symbols['out']+(CAP+2)*width:
                    require(helper is None and (addr-symbols['out'])%width==0,'Scalar oracle address/window')
                    element=(addr-symbols['out'])//width
                    require(element not in active['reads'],'Duplicate result/guard scalar read')
                    expected=91 if element in (0,CAP+1) else gold[active['ordinal']]['expected'][element-1]
                    require(int(rd[2],16)&((1<<p['sew'])-1)==expected,'Actual scalar result mismatch')
                    active['reads'].add(element)
            if rd:regs[int(rd[1])]=int(rd[2],16)
    require(exited and capacity==1 and vlenb_reads==1 and len(calls)==p['calls'],'Missing HTIF/full calls/capacity/vlenb')
    require(value(symbols['checks'],8)==p['calls'] and value(symbols['elements'],8)==CAP*p['calls'] and
            value(symbols['errors'],8)==0,'Original final counter ledger')
    text=console.split(b'\0',1)[0].decode('ascii')
    for token in (marker(p),'ARITHMETIC_FULL_PASS '+p['id'],'BOARD_REPLAY_PASS'):
        require(text.count(token)==1,'Original full completion marker '+token)
    require(not re.search(r'FAIL|TRAP|MISMATCH|UNSUPPORTED',text),'Original raw failure veto')
    return dict(status='FULL_ORIGINAL_REFERENCE_PASS_NOT_DUT',shape=p['id'],calls=len(calls),results=len(calls)*CAP,
        guards=len(calls)*2,vstart_checks=len(calls),capacity_calls=capacity,helper_instructions=len(calls)*13,
        retired_records=steps,firmware_through_htif=through_htif,boot_records=boot,post_htif_parking=parking,
        console=text,call_ledger=calls,startup_bss=boot_guard.finish(),fflags_oracle='Original has no explicit fflags oracle; no invented acceptance',
        source_full_order=True,partitioned=False,vlenb=128,vlenb_reads=vlenb_reads)
