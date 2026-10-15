"""Actual-ELF, complete raw-reference checker for fixed-old unboxed full17920."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
sys.dont_write_bytecode = True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
W=ROOT.parents[3]
DECODER=W/'verification/coverage/scoped_rv64c_memory.py'
_spec=importlib.util.spec_from_file_location('full17920_memory',DECODER)
_mem=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_mem)
MASK=(1<<64)-1
LINE=re.compile(r'core[ \t]+0:[ \t]+([0-3])[ \t]+0x([0-9a-f]+)[ \t]+\(0x([0-9a-f]+)\)(.*)')
TOKEN=re.compile(r'(?:([xfv])[ \t]*(\d+)[ \t]+0x([0-9a-f]+)|c(\d+)_(\w+)[ \t]+0x([0-9a-f]+)|mem[ \t]+0x([0-9a-f]+)(?:[ \t]+0x([0-9a-f]+))?|e(\d+)[ \t]+(m[f]?\d+)[ \t]+l(\d+))')
VETO=re.compile(r'RVV_FP_COMPARE_(?:DETAIL|FAIL|CAPACITY_FAIL)|BOARD_\w*(?:FAIL|TRAP|MISMATCH)|\b(?:ABORTED|FAILED|MISMATCH|TRAP)\b')
BOOT=[(0x1000,0x297),(0x1004,0x02028593),(0x1008,0xf1402573),(0x100c,0x0182b283),(0x1010,0x28067)]
ALIASES=['zero','ra','sp','gp','tp','t0','t1','t2','s0','s1','a0','a1','a2','a3','a4','a5','a6','a7','s2','s3','s4','s5','s6','s7','s8','s9','s10','s11','t3','t4','t5','t6']

def require(ok,why):
    if not ok:raise ValueError(why)

def parse_line(line):
    m=LINE.fullmatch(line.rstrip('\n'));require(m is not None,'Unparsed complete raw record')
    require(m[1]=='3','Unexpected privilege/trap')
    r=dict(pc=int(m[2],16),insn=int(m[3],16),x={},f={},v={},csr={},mem=[],cfg=None,rest=m[4])
    end=0
    for t in TOKEN.finditer(m[4]):
        require(not m[4][end:t.start()].strip(),'Unparsed side effect')
        if t[1]:
            n=int(t[2]);require(n<32 and n not in r[t[1]],'Duplicate/invalid register')
            r[t[1]][n]=int(t[3],16)
        elif t[4]:
            require(t[5] not in r['csr'],'Duplicate CSR');r['csr'][t[5]]=int(t[6],16)
        elif t[7]:r['mem'].append((int(t[7],16),int(t[8],16) if t[8] else None))
        else:
            require(r['cfg'] is None,'Duplicate vector context');r['cfg']=(int(t[9]),t[10],int(t[11]))
        end=t.end()
    require(not m[4][end:].strip(),'Unparsed trailing side effect')
    require(len(r['x'])<=1 and len(r['f'])<=1,'Multiple scalar destinations')
    return r

def memory_desc(insn):
    d=_mem.decode(insn)
    if d:return d
    op=insn&127;f=(insn>>12)&7
    if op not in (3,35):return None
    require(f in ((0,1,2,3,4,5,6) if op==3 else (0,1,2,3)),'Scalar memory encoding')
    imm=(insn>>20) if op==3 else (((insn>>25)<<5)|((insn>>7)&31))
    if imm&2048:imm-=4096
    return dict(kind='read' if op==3 else 'write',size=1<<(f&3),base=(insn>>15)&31,
                register=(insn>>7)&31 if op==3 else (insn>>20)&31,offset=imm,expanded=insn)

def elf_image(path):
    raw=path.read_bytes();require(raw[:6]==b'\x7fELF\x02\x01','Actual ELF64LE')
    offset=struct.unpack_from('<Q',raw,32)[0];size,n=struct.unpack_from('<HH',raw,54)
    memory={}
    for i in range(n):
        kind,_,off,va,_,count,_,_=struct.unpack_from('<IIQQQQQQ',raw,offset+i*size)
        if kind==1:memory.update((va+j,b) for j,b in enumerate(raw[off:off+count]))
    return memory

def word(memory,address,width):
    require(all(address+i in memory for i in range(width)),'Missing initialized byte '+hex(address))
    return sum(memory[address+i]<<(8*i) for i in range(width))

def full_config():
    s=json.loads((HERE/'spec.json').read_text())
    s['code']={int(k):v for k,v in s['code'].items()}
    gold=json.loads((ROOT/'source_model02/model.json').read_text())['rows']
    return s,gold

class Checker:
    def __init__(self,s,gold):
        self.s,self.gold=s,gold;self.a=s['symbols'];self.code=s['code']
        self.memory=elf_image(Path(s['elf']));self.regs={0:0};self.vec={};self.fp={};self.csr={}
        self.lookup={r['pc']:(op,i) for op,rs in enumerate(s['helpers']) for i,r in enumerate(rs)}
        self.capmap={r['pc']:i for i,r in enumerate(s['capacity'])}
        self.freshmap={r['pc']:i for i,r in enumerate(s['stores'])}
        self.inputmap={r['pc']:i for i,r in enumerate(s['input_loads'])}
        self.opaque=set(s['opaque_initial_spills'])
        self.boot=self.bss=self.pre=self.cap=self.calls=self.fresh=self.input_reads=0
        self.step=0;self.active=None;self.record_index=None;self.record_loads=0
        self.retired=self.total=self.parks=0;self.exited=False;self.nextpc=None
        self.console=bytearray();self.counts=Counter();self.current_context={};self.exit_count=None
        self.helper_counts=Counter();self.raw_scalar_seeds=Counter();self.saved_flags=None
    def current(self):
        require(self.calls<len(self.gold),'Extra call');return self.gold[self.calls]
    def expected_setup(self,g):
        a=self.a;out=[]
        out += [(a['mask']+o,int.from_bytes(bytes([g['mask_byte']])*8,'little'),8) for o in range(0,128,8)]
        for k in range(0,16,4):
            for name in ('a','b'):out.append((a[name]+2*k,sum(g[name][k+j]<<(16*j) for j in range(4)),8))
        out += [(a['output']+o,0x5b5b5b5b5b5b5b5b,8) for o in range(0,128,8)]
        out.append((a['output']+128,0x5b5b,2));return out
    def setup_store(self,pc,address,value,width):
        require(self.cap==3 and self.pre==6 and self.step==0 and self.active is None,'Fresh store phase')
        g=self.current();i=self.freshmap[pc]
        require(i==self.fresh and (address,value,width)==self.expected_setup(g)[i],'Exact41 fresh store PC/order/value/width')
        self.fresh+=1;self.counts['fresh_stores']+=1
    def input_load(self,pc,address,value,width):
        g=self.current();i=self.inputmap[pc]
        require(self.active is None and i==self.input_reads and width==8,'Eight input LD order/width')
        require(self.fresh==16+i and self.record_index==g['record_index'],'Input LD interleaved with each fresh SD')
        record=word(self.memory,self.a['oracle_records']+8*g['record_index'],8)
        row=(record>>(48 if i%2==0 else 56))&255
        expected_address=self.a['input_periods']+32*row+(i//2)*8
        values=g['a' if i%2==0 else 'b'];k=(i//2)*4
        require(address==expected_address and value==sum(values[k+j]<<(16*j) for j in range(4)),'Actual input period LD/value')
        self.input_reads+=1;self.counts['input_LD']+=1
    def record_load(self,address,value,width):
        g=self.current();require(self.calls%8==0 and self.fresh==0 and self.active is None,'Record hoist phase')
        require(self.record_loads==g['record_index'],'2240 record LD exact order')
        require(width==8 and address==self.a['oracle_records']+8*g['record_index'],'Actual oracle record address')
        require(value==word(self.memory,address,8),'Actual oracle record contents')
        self.record_index=g['record_index'];self.record_loads+=1
    def oracle(self,address,value,width):
        require(self.active is not None and self.step==0 and not self.active['read'],'Output oracle phase/order')
        g=self.current();require(address==self.a['output'] and width==4 and value<=0xffffffff,'Full aligned output LWU')
        require((value&255)==91 and value>>24==91,'Both original guards')
        require(all((value>>(8+i))&1 in g['allowed'][i] for i in range(16)),'Original all16 allowed result bits')
        require(self.active['vstart']==0 and self.active['flags']==g['flags'],'Full original CSR checks')
        require(self.fresh==41 and self.input_reads==8,'Full original per-call freshness')
        self.active['read']=True;self.calls+=1;self.active=None;self.fresh=self.input_reads=0
        self.counts['output_LWU']+=1
    def next_address(self,r):
        ins=self.code[r['pc']];op=ins['op'];args=ins['args'].split(' #')[0]
        nxt=r['pc']+len(ins['insn'])//2
        def reg(name):
            index=ALIASES.index(name);require(index in self.regs,'Unknown control register '+name);return self.regs[index]
        if op=='ret':return reg('ra')&~1
        if op=='j':return int(args.split()[0],16)
        if op=='jal':return int(args.split(',')[-1].split()[0],16)
        if op=='jalr':
            require(args=='t2','Unexpected indirect control');return reg('t2')&~1
        parts=args.split(',')
        if op in ('beqz','bnez','bltz','bgez'):
            x=reg(parts[0]);z=(x==0) if op=='beqz' else (x!=0) if op=='bnez' else bool(x>>63) if op=='bltz' else not(x>>63)
            return int(parts[-1].split()[0],16) if z else nxt
        if op in ('beq','bne','bltu','bgeu','blt','bge'):
            x,y=reg(parts[0]),reg(parts[1])
            if op in ('blt','bge'):
                x=x-(1<<64) if x>>63 else x;y=y-(1<<64) if y>>63 else y
            z=x==y if op=='beq' else x!=y if op=='bne' else x<y if op in ('blt','bltu') else x>=y
            return int(parts[-1].split()[0],16) if z else nxt
        return nxt
    def consume(self,r):
        pc,c=r['pc'],r['insn'];self.total+=1
        require(self.total<=4000000,'Raw4M ceiling')
        self.current_context=dict(line=self.total,firmware=self.retired,completed=self.calls,pc=hex(pc),helper_step=self.step,fresh=self.fresh)
        if pc<0x80000000:
            require(self.retired==0 and self.boot<5 and (pc,c)==BOOT[self.boot],'Exact reset-ROM sequence')
            expected_x=({5:0x1000},{11:0x1020},{10:0},{5:0x80000000},{})[self.boot]
            require(r['x']==expected_x and r['mem']==([(0x1018,None)] if self.boot==3 else []) and not(r['v'] or r['f'] or r['csr'] or r['cfg']),'Exact reset side effects')
            self.regs.update(r['x']);self.boot+=1;return
        require(self.boot==5,'Missing reset-ROM')
        if self.exited:
            require(pc==self.s['park'] and c==0xa001 and not r['rest'].strip(),'EOF pure park only')
            self.parks+=1;return
        self.retired+=1
        require(pc in self.code and c==int(self.code[pc]['insn'],16),'Actual ELF PC/code')
        require(pc==(0x80000000 if self.nextpc is None else self.nextpc),'Actual scalar/helper control-flow discontinuity')
        require(pc not in self.s['failure_pcs'],'Failure/diagnostic path entered')
        pair=self.lookup.get(pc)
        if pc==0x80000236:
            require(self.active is not None and self.regs.get(22)==word(self.memory,self.a['oracle_records']+8*self.current()['record_index'],8),'Caller record s6 preserved')
        if pc==0x80000240:
            require(self.active is not None and r['x']=={14:self.current()['flags']},'Caller flags record/sticky OR')
        if self.step:require(pair==(self.current()['op'],self.step),'Contiguous exact original helper')
        if 0<self.cap<3:require(pc==self.s['capacity'][self.cap]['pc'],'Contiguous capacity')
        is_csr=c&127==0x73 and ((c>>12)&7)!=0
        if is_csr and pair is None and pc not in self.capmap:
            require(self.pre<6 and pc==self.s['prelude'][self.pre] and not self.calls and self.cap==0,'Bootstrap CSR exact phase')
            src=(c>>15)&31;operand=src if c&(1<<14) else self.regs.get(src)
            if self.pre<5:
                require(operand==[0,self.a['trap_entry'],0x6600,0,0][self.pre] and not r['x'],'Bootstrap CSR operand')
                if self.pre==3:self.csr['fflags']=0;self.csr['frm']=0
                if self.pre==4:self.csr['vstart']=0
            else:require(r['x']=={(c>>7)&31:128},'Actual vlenb128')
            self.pre+=1
        if pc in self.capmap:
            i=self.capmap[pc];require(i==self.cap and self.pre==6 and self.calls==0,'Capacity once')
            if i==0:require(r['x']=={5:MASK},'Capacity AVL')
            if i==1:require(r['x']=={10:16},'Capacity16')
            self.cap+=1
        if c&127==0x57 or (c&127 in (7,39) and (c>>12)&7 in (0,5,6,7)):
            require(pair is not None or pc==self.s['capacity'][1]['pc'],'Unexpected RVV')
        if r['cfg'] is not None:require(r['cfg']==(16,'mf4',self.csr.get('vl')),'Actual vector trace configuration')
        if pair is not None:self.helper(r,pair)
        desc=memory_desc(c)
        if desc:
            require(len(r['mem'])==1,'Scalar access schema')
            address,value=r['mem'][0];width=desc['size'];base=self.regs.get(desc['base'])
            require(base is not None and address==(base+desc['offset'])&MASK,'Scalar effective address')
            if desc['kind']=='write':
                require(value is not None and not r['x'],'Scalar store payload')
                source=self.regs.get(desc['register']);lowmask=(1<<(8*width))-1
                if source is None:
                    require(pc in self.opaque and not self.calls and self.fresh==0,'Unknown scalar store source outside exact initial ABI spill')
                else:require(value&lowmask==source&lowmask,'Scalar store source operand')
                if pc==0x80000046:
                    require(address==self.a['__bss_start']+8*self.bss and width==8 and value==0 and self.pre==5 and self.cap==0,'Exact ordered zero BSS')
                    require(address+8<=self.a['__bss_end'],'BSS overrun');self.bss+=1
                elif pc in self.freshmap:self.setup_store(pc,address,value&lowmask,width)
                else:
                    protected=[(self.a[n],self.a[n]+size) for n,size in [('a',2048),('b',2048),('mask',128),('output',130)]]
                    require(not any(address<hi and address+width>lo for lo,hi in protected),'Unexpected original array write')
                if self.a['replay_log']<=address<self.a['replay_log']+8192 and pc!=0x80000046:
                    require(width==1 and address==self.a['replay_log']+len(self.console),'Runtime console byte/order')
                    self.console.append(value&255);require(not VETO.search(self.console.decode('ascii')),'Original raw failure veto')
                for j in range(width):self.memory[address+j]=(value>>(8*j))&255
                if address==self.a['tohost']:
                    require(pc==self.s['exit_store'] and width==8 and value==1 and self.regs.get(10)==1,'Actual HTIF success1')
                    self.validate_complete();self.exited=True;self.exit_count=self.retired
            else:
                require(value is None and r['x'].keys()=={desc['register']},'Scalar load destination/schema')
                observed=r['x'][desc['register']];expected=word(self.memory,address,width)
                funct=(desc['expanded']>>12)&7
                if funct<4 and width<8 and expected>>(8*width-1):expected|=MASK^((1<<(8*width))-1)
                require(observed==expected,'Actual scalar read payload vs initialized memory')
                if pc in self.inputmap:self.input_load(pc,address,observed,width)
                elif pc==self.s['record_load']:self.record_load(address,observed,width)
                elif pc==self.s['output_read']:self.oracle(address,observed,width)
                elif self.a['output']<=address<self.a['output']+130:
                    require(False,'Unexpected scalar output read')
        elif pair is None:require(not r['mem'],'Unclassified memory event')
        if pc==0x8000004e:require(self.bss*8==self.a['__bss_end']-self.a['__bss_start'],'Full BSS before main')
        if r['f']:require(pair is not None and pair[0]>=4 and pair[1]==7,'FP write only original fmv.d.x')
        if r['v']:require(pair is not None,'Vector write only helper')
        self.vec.update(r['v']);self.fp.update(r['f']);self.csr.update(r['csr'])
        if pair is not None and pair[1]==8+(2 if pair[0]>=4 else 0):
            g=self.current();require(self.csr.get('vstart')==0,'Target resets vstart')
            require(all((self.vec.get(24,-1)>>i)&1 in g['allowed'][i] for i in range(16)),'Full target allowed result bits')
        nxt=self.next_address(r)
        self.regs.update(r['x']);self.regs[0]=0;self.nextpc=nxt
    def helper(self,r,pair):
        op,i=pair;g=self.current();delta=2 if op>=4 else 0
        require(op==g['op'] and i==self.step and self.cap==3 and self.pre==6,'Actual17920 helper order')
        if i==0:
            require(self.active is None and self.fresh==41 and self.input_reads==8 and self.record_index==g['record_index'],'Complete setup/record before helper')
            args=[self.a['a'],self.a['b'],self.a['output']+1,g['vl'],16,self.a['mask'],0,g['sticky']]
            require([self.regs.get(x) for x in range(10,18)]==args,'Eight original arguments')
            require(self.regs.get(22)==word(self.memory,self.a['oracle_records']+8*g['record_index'],8) and self.regs.get(23)==g['sticky'],'Actual record/sticky caller ABI')
            require(r['x']=={30:0} and self.csr.get('fflags')==0,'Save actual prior fflags0')
            for name,values,width in [('a',g['a'],2),('b',g['b'],2),('mask',[g['mask_byte']]*128,1),('output',[91]*130,1)]:
                require(all(word(self.memory,self.a[name]+j*width,width)==v for j,v in enumerate(values)),'Full initialized bytes '+name)
            require(all(self.memory.get(self.a[n]+j)==0 for n in ('a','b') for j in range(32,2048)),'Unused original backing BSS')
            self.active=dict(read=False,vstart=None,flags=None);self.saved_flags=0
        if i in (1,6+delta,14+delta):require(r['x']=={5:g['vl'] if i==6+delta else 16},'Original vset returned VL')
        if i in (2,3,4,5):
            name='a' if i==2 else 'b' if i==3 else 'output' if i==4 else 'mask'
            base=self.a[name]+int(i==4);width=2 if i in (2,3) else 1;count=16 if i in (2,3) else 2
            require(r['mem']==[(base+j*width,None) for j in range(count)],'Full original helper load addresses')
        if op>=4 and i==6:require(r['x']=={7:g['b'][0]},'Raw scalar LHU all32seeds')
        if op>=4 and i==7:
            require(self.regs.get(7)==g['b'][0] and r['f']=={0:g['b'][0]},'Exact fmv.d.x malformed NaN boxing')
            self.raw_scalar_seeds[g['seed']]+=1
        if i==7+delta:
            require(self.regs.get(17)==g['sticky'],'Sticky CSR source operand');self.csr['fflags']=g['sticky']
        if i==8+delta:
            require((self.csr.get('vl'),self.csr.get('vtype'),self.csr.get('vstart'))==(g['vl'],14,0),'Target actual CSR context')
            for n,vals in ((8,g['a']),(16,g['b'])):
                require(n in self.vec and all((self.vec[n]>>(16*j))&65535==v for j,v in enumerate(vals)),'Full actual source vector')
            require(self.vec.get(24,-1)&65535==0x5b5b and self.vec.get(0,-1)&65535==g['mask_byte']*257,'DK0 old/mask exact')
            if op>=4:require(self.fp.get(0)==g['b'][0],'Target raw unboxed ft0')
        if i==9+delta:require(r['x']=={10:0},'Actual returned vstart');self.active['vstart']=0
        if i==10+delta:require(r['x']=={6:g['flags']},'Original full flag oracle');self.active['flags']=g['flags']
        if i==12+delta:require(r['x']=={10:g['flags']<<32},'Packed return status')
        if i==13+delta:
            require(self.regs.get(30)==self.saved_flags,'Actual saved fflags restore source');self.csr['fflags']=self.saved_flags
        if i==15+delta:
            require(len(r['mem'])==2,'Original result store2bytes')
            for j,(address,value) in enumerate(r['mem']):
                require(address==self.a['output']+1+j and value is not None and 0<=value<256,'Packed result store address/data')
                require(all((value>>k)&1 in g['allowed'][8*j+k] for k in range(8)),'Stored result allowed sets')
                require(value==(self.vec[24]>>(8*j))&255,'Stored result vs actual vector')
                self.memory[address]=value
        self.helper_counts[op,i]+=1;self.step=(self.step+1)%len(self.s['helpers'][op])
    def validate_complete(self):
        require(self.calls==17920 and self.active is None and self.step==0 and self.fresh==self.input_reads==0,'Full17920 complete, not prefix')
        require(self.pre==6 and self.cap==3 and self.record_loads==2240,'Full bootstrap/capacity/hoisted records')
        require(self.counts==dict(fresh_stores=734720,input_LD=143360,output_LWU=17920),'Exact source access totals')
        require(all(self.helper_counts[op,i]==1792 for op in range(10) for i in range(len(self.s['helpers'][op]))),'All original helpers full multiplicity')
        require(sum(self.helper_counts.values())==326144 and self.raw_scalar_seeds=={i:336 for i in range(32)},'Dynamic helper/raw scalar full counts')
        name='fp_compare_unboxed_e16_mf4_full17920'
        expected='BOARD_CASE_BEGIN '+name+'\nRVV_FP_COMPARE_PASS sew=16 cases=17920 errors=0\nBOARD_CASE_PASS '+name+'\nBOARD_REPLAY_PASS\n'
        require(self.console.decode('ascii')==expected,'Exact full original success console')
        require(self.retired<=3000000,'Firmware3M cost gate')
    def finish(self):
        require(self.exited,'EOF without full actual HTIF success');self.validate_complete()
        return dict(status='REFERENCE_FULL17920_PASS_SOURCE_ONLY_NOT_DUT',calls=self.calls,result_bits=286720,guards=35840,
             flags=17920,vstarts=17920,helper_instructions=sum(self.helper_counts.values()),capacity_instructions=3,
             stores=self.counts['fresh_stores'],input_LD=self.counts['input_LD'],output_LWU=self.counts['output_LWU'],record_LD=self.record_loads,
             raw_scalar_seed_counts=dict(self.raw_scalar_seeds),firmware_to_HTIF=self.exit_count,whole_raw_rows=self.total,
             park_rows=self.parks,EOF_pure_park=True,console=self.console.decode('ascii'),closed_raw_parses=1)

def audit(path):
    spec,gold=full_config();check=Checker(spec,gold)
    try:
        with path.open() as f:
            for line in f:check.consume(parse_line(line))
        return check.finish()
    except BaseException as error:
        raise ValueError(str(error)+' context='+repr(check.current_context)) from error
