"""Full original reduction source events; shared raw/ISA/control-flow reader."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
G=HERE.parents[1]
SOFTWARE=HERE.parent/'full6720_e16_mf4_software01'
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
BASE_PATH=G/'fp_compare_unboxed_full17920_prepare01/reference_entry02/checker.py'
base=load('shared_reference_isa',BASE_PATH)
require=base.require
parse_line=base.parse_line
MASK=base.MASK
NAME='fp_redspecial_e16_mf4_full6720'

def config():
    parser=load('actual_linked_parser',G/'fp_compare_unboxed_full17920_prepare01/compile01/inspect_linked.py')
    parser.RUN=SOFTWARE/'execution01'
    d,code,func,sym,sizes=parser.parse('spike')
    linked=json.loads((SOFTWARE/'linked01/spike.json').read_text())
    original=SOFTWARE/'execution01/software/original'
    bits=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',(original/'input_bits.h').read_text())]
    fixtures=[(int(a,16),int(b)) for a,b in re.findall(r'\{UINT64_C\(0x([0-9a-f]+)\),\s*(\d+)\}',(original/'fixtures.h').read_text())]
    require(len(bits)==16 and len(fixtures)==6720,'Exact original tables')
    return dict(elf=str(d/'program.elf'),code=code,func=func,symbols=sym,sizes=sizes,linked=linked,bits=bits,fixtures=fixtures)

def original_input(bits,scenario,i):
    if scenario==0:return bits[i%2]
    if scenario==1:return bits[14]
    if scenario==2:return bits[2 if i%2 else 15]
    if scenario==3:return bits[13 if i%2 else 12]
    if scenario==4:return bits[(2,7,3,7,11,11)[i%6]]^(0x8000 if i%6 in (3,5) else 0)
    if scenario==5:return bits[(8,9,10,8,9,10)[i%6]]^(0x8000 if i%6>=3 else 0)
    return bits[(15 if scenario==6 else 7) if i%2 else 2]

def original_call(s,n):
    require(0<=n<6720,'Extra original call')
    row,sticky=divmod(n,2);scenario,t=divmod(row,420);l,t=divmod(t,60);mode,t=divmod(t,15);rm,op=divmod(t,3)
    bits,flags=s['fixtures'][3360+row]
    return dict(scenario=scenario,l=l,mode=mode,rm=rm,op=op,sticky=sticky,vl=(0,1,2,3,8,15,16)[l],
                row=row,bits=bits,flags=flags|sticky,mask=(255,0,0x55,0x24)[mode],
                seed=s['bits'][(1,14,2,12,2,8,1,12)[scenario]])

class Checker(base.Checker):
    # Inherit actual branch/jump calculation, not another ISA interpreter.
    def __init__(self,s):
        self.s=s;self.a=s['symbols'];self.code=s['code'];self.memory=base.elf_image(Path(s['elf']))
        self.regs={0:0};self.vec={};self.csr={};self.console=bytearray()
        self.helpers=[s['func']['op_'+str(i)] for i in range(3)]
        self.lookup={r['pc']:(op,i) for op,rows in enumerate(self.helpers) for i,r in enumerate(rows)}
        self.capmap={r['pc']:i for i,r in enumerate(s['func']['capacity'])}
        self.stores={}
        for name,lo,hi in [('seed',0x288,0x2a6),('mask',0x374,0x382),('output',0x3ba,0x3dc)]:
            for i,r in enumerate(x for x in s['func'][NAME+'_main'] if 0x80000000+lo<=x['pc']<=0x80000000+hi):self.stores[r['pc']]=(name,i)
        self.readmap={r['pc']:i for i,r in enumerate(x for x in s['func'][NAME+'_main'] if 0x80000444<=x['pc']<=0x800004ae and x['op']=='ld')}
        require(len(self.readmap)==18 and len(self.stores)==42,'Actual packed PC extents')
        self.failure={int(k,16) for k,label in s['linked']['zero_success_PCs'].items() if label!='VLEN512'}
        self.failure.update(r['pc'] for r in s['func']['trap_entry']+s['func']['replay_trap'])
        self.opaque={r['pc'] for name in ('main',NAME+'_main') for r in s['func'][name]
                     if r['pc']<s['func'][name][0]['pc']+32 and r['op']=='sd' and re.match(r's(?:[0-9]|1[01]),\d+\(sp\)',r['args'])}
        self.counts=Counter();self.hcounts=Counter();self.calls=self.step=self.reads=self.fresh=0
        self.total=self.retired=self.parks=self.boot=self.bss=self.pre=self.cap=0
        self.active=None;self.nextpc=None;self.exited=False;self.exit_count=None;self.flags_seen=0;self.current_context={}
    def g(self):return original_call(self.s,self.calls)
    def next_address(self,r):
        ins=self.code[r['pc']]
        if ins['op']=='jr':
            require(r['pc']==0x800001f2 and ins['args']=='a5','Actual input switch only')
            require(15 in self.regs,'Unknown switch target');return self.regs[15]&~1
        return super().next_address(r)
    def setup_store(self,pc,address,value,width):
        require(self.active is None and self.step==0 and self.cap==3,'Source setup phase')
        g=self.g();a=self.a
        if pc==0x80000246:
            n=self.counts['input_SH'];scenario,i=divmod(n,16)
            require(self.calls==scenario*840 and scenario<8 and width==2 and address==a['input']+2*i and value==original_input(self.s['bits'],scenario,i),'Exact scenario-only input16 SH')
            self.counts['input_SH']+=1;return
        name,i=self.stores[pc]
        if name=='seed':
            require(self.calls%840==0 and self.counts['input_SH']==16*(g['scenario']+1) and self.counts['seed_SD']==16*g['scenario']+i,'Seed original scenario order')
            expected=g['seed']*0x1000100010001
        elif name=='mask':
            require(self.calls%2==0 and self.counts['fixture_fields']==2*(g['row']+1) and self.counts['mask_SD']==8*g['row']+i,'Mask once per original op row, before sticky0')
            expected=g['mask']*0x101010101010101
        else:
            require(i==self.fresh and self.counts['mask_SD']==8*(g['row']+1),'Output complete new-call order')
            expected=0x5b5b5b5b5b5b5b5b;self.fresh+=1
        require((address,value,width)==(a[name]+8*i,expected,8),'Exact setup address/data/width '+name)
        self.counts[name+'_SD']+=1
    def fixture_read(self,pc,address,value,width):
        g=self.g();field=0 if pc==0x8000033e else 1
        require(self.active is None and self.calls%2==0 and self.fresh==0 and self.counts['fixture_fields']==g['row']*2+field,'Fixture once per original row')
        require((address,value,width)==(self.a['fixtures']+16*(3360+g['row'])+8*field,self.s['fixtures'][3360+g['row']][field],8 if field==0 else 4),'Actual bank1 fixture address/value/width')
        self.counts['fixture_fields']+=1
    def result_bytes(self,g):
        v=bytearray([91]*144)
        if g['vl']:v[8:10]=g['bits'].to_bytes(2,'little')
        return bytes(v)
    def oracle(self,pc,address,value,width):
        require(self.active is not None and self.step==0 and self.readmap[pc]==self.reads,'18 complete ordered output reads after helper')
        want=self.result_bytes(self.g());i=self.reads
        require((address,value,width)==(self.a['output']+8*i,int.from_bytes(want[8*i:8*i+8],'little'),8),'Original all144B oracle including tail/guards')
        self.reads+=1;self.counts['output_LD']+=1
        if self.reads==18:
            require(self.active==dict(vstart=0,flags=self.g()['flags']) and self.fresh==18,'Complete original status and freshness')
            self.calls+=1;self.active=None;self.reads=self.fresh=0
    def helper(self,r,pair):
        op,i=pair;g=self.g();a=self.a
        require((op,i)==(g['op'],self.step) and self.cap==3 and self.pre==6,'Original6720 helper order')
        if i==0:
            require(self.active is None and self.fresh==18 and self.counts['input_SH']==16*(g['scenario']+1) and self.counts['seed_SD']==16*(g['scenario']+1),'Original scenario setup and full output freshness')
            require([self.regs.get(x) for x in range(10,18)]==[a['input'],a['seed'],a['output']+8,g['vl'],16,a['mask'],g['rm'],g['sticky']],'Eight source arguments')
            for name,vals,w in [('input',[original_input(self.s['bits'],g['scenario'],j) for j in range(16)]+[0]*496,2),('seed',[g['seed']]*64,2),('mask',[g['mask']]*64,1),('output',[91]*144,1)]:
                require(all(base.word(self.memory,a[name]+j*w,w)==v for j,v in enumerate(vals)),'Full setup/backing '+name)
            self.active=dict(vstart=None,flags=None)
        if i in (0,3,6,18):
            vl,typ=(64,8) if i in (0,18) else (16 if i==3 else g['vl'],14)
            require(r['x']=={5:vl} and r['csr'].get('vl')==vl and r['csr'].get('vstart')==0 and r['csr'].get('vtype',self.csr.get('vtype'))==typ,'Actual vset SEW/LMUL/VL')
        if i in (1,2,4,5):
            name='seed' if i==1 else 'output' if i==2 else 'input' if i==4 else 'mask'
            n,w,reg=(64,2,16) if i==1 else (64,2,24) if i==2 else (16,2,8) if i==4 else (2,1,0)
            address=a[name]+(8 if i==2 else 0)
            require(r['mem']==[(address+w*j,None) for j in range(n)],'Full helper vector load footprint')
            require(set(r['v'])=={reg} and r['v'][reg]&((1<<(8*n*w))-1)==base.word(self.memory,address,n*w),'Actual vector initialized payload')
        if i in (7,8):require(r['x']=={29 if i==7 else 30:0} and self.csr.get('frm' if i==7 else 'fflags')==0,'Save original CSR value')
        if i in (9,10):
            k='frm' if i==9 else 'fflags';v=g['rm'] if i==9 else g['sticky']
            require(self.regs.get(16 if i==9 else 17)==v and r['csr'].get(k)==v,'Set requested CSR')
        if i==11:
            require((self.csr.get('vl'),self.csr.get('vtype'),self.csr.get('vstart'),self.csr.get('frm'),self.csr.get('fflags'))==(g['vl'],14,0,g['rm'],g['sticky']),'Reduction context')
            require(not r['mem'] and not r['x'] and set(r['v'])<= {24},'Reduction result schema')
            require(r['csr'].get('vstart',self.csr.get('vstart'))==0 and r['csr'].get('fflags',self.csr.get('fflags'))==g['flags'],'Actual target NV/sticky flags')
            result=r['v'].get(24,self.vec.get(24))
            require(result==int.from_bytes(self.result_bytes(g)[8:136],'little'),'Full target128B result (VL0 included)')
        if i in (12,13,14,15):
            reg,v=(10,0) if i==12 else (6,g['flags']) if i==13 else (6,g['flags']<<32) if i==14 else (10,g['flags']<<32)
            require(r['x']=={reg:v},'Returned vstart/flags packed status')
            if i==12:self.active['vstart']=0
            if i==13:self.active['flags']=g['flags'];self.flags_seen|=g['flags']
        if i in (16,17):
            require(self.regs.get(29 if i==16 else 30)==0 and r['csr'].get('frm' if i==16 else 'fflags')==0,'Restore saved original CSR')
        if i==19:
            data=self.result_bytes(g)[8:136]
            require(r['mem']==[(a['output']+8+j,int.from_bytes(data[j:j+2],'little')) for j in range(0,128,2)],'Full128B destination store')
            require(self.vec.get(24)==int.from_bytes(data,'little'),'Store vs actual vector')
            self.memory.update({a['output']+8+j:v for j,v in enumerate(data)})
        self.hcounts[op,i]+=1;self.step=(self.step+1)%21
    def consume(self,r):
        pc,c=r['pc'],r['insn'];self.total+=1
        self.current_context=dict(line=self.total,firmware=self.retired,completed=self.calls,pc=hex(pc),step=self.step,reads=self.reads,fresh=self.fresh)
        require(self.total<=2000000,'Raw2M bound')
        if pc<0x80000000:
            require(not self.retired and self.boot<5 and (pc,c)==base.BOOT[self.boot],'Exact reset ROM')
            require(r['x']==({5:0x1000},{11:0x1020},{10:0},{5:0x80000000},{})[self.boot] and r['mem']==([(0x1018,None)] if self.boot==3 else []) and not(r['v'] or r['f'] or r['csr'] or r['cfg']),'Reset side effects')
            self.regs.update(r['x']);self.boot+=1;return
        require(self.boot==5,'Complete reset')
        if self.exited:
            require(pc==0x8000007e and c==0xa001 and not r['rest'].strip(),'Only original pure park after HTIF');self.parks+=1;return
        self.retired+=1
        require(pc in self.code and c==int(self.code[pc]['insn'],16),'Actual new ELF PC/code')
        require(pc==(0x80000000 if self.nextpc is None else self.nextpc),'Actual branch/call/return flow')
        require(pc not in self.failure,'Original failure/diagnostic/trap entered')
        pair=self.lookup.get(pc)
        if self.step:require(pair==(self.g()['op'],self.step),'Contiguous21 helper window')
        if 0<self.cap<3:require(self.capmap.get(pc)==self.cap,'Contiguous original capacity')
        if c&127==0x73 and ((c>>12)&7) and pair is None and pc not in self.capmap:
            prelude=(0x80000010,0x8000001c,0x80000026,0x8000002a,0x8000002e,0x800000fc)
            require(self.pre<6 and pc==prelude[self.pre] and self.calls==self.cap==0,'Original bootstrap CSR phase')
            src=(c>>15)&31;operand=src if c&(1<<14) else self.regs.get(src)
            if self.pre<5:
                require(operand==(0,self.a['trap_entry'],0x6600,0,0)[self.pre] and not r['x'],'Bootstrap CSR operand')
                if self.pre==3:self.csr.update(frm=0,fflags=0)
                if self.pre==4:self.csr['vstart']=0
            else:require(r['x']=={8:128},'Actual vlenb128')
            self.pre+=1
        if pc in self.capmap:
            i=self.capmap[pc];require(i==self.cap and self.pre==6 and not self.calls,'Capacity once')
            if i==0:require(r['x']=={5:MASK},'Capacity AVL')
            if i==1:require(r['x']=={10:16},'Actual capacity16')
            self.cap+=1
        if r['cfg'] is not None:
            require(r['cfg']==(16,'m1' if self.csr.get('vtype')==8 else 'mf4',self.csr.get('vl')),'Actual vector trace context')
        if c&127==0x57 or (c&127 in (7,39) and (c>>12)&7 in (0,5,6,7)):
            require(pair is not None or pc==self.s['func']['capacity'][1]['pc'],'No extra RVV')
        if pair is not None:self.helper(r,pair)
        desc=base.memory_desc(c)
        if desc:
            require(len(r['mem'])==1,'Scalar memory schema');address,value=r['mem'][0];w=desc['size'];b=self.regs.get(desc['base'])
            require(b is not None and address==(b+desc['offset'])&MASK,'Actual scalar effective address')
            if desc['kind']=='write':
                require(value is not None and not r['x'],'Scalar store payload');mask=(1<<(8*w))-1;source=self.regs.get(desc['register'])
                if source is None:require(pc in self.opaque and not self.calls and not self.fresh,'Exact initial opaque ABI spill only')
                else:require(value&mask==source&mask,'Actual scalar store source')
                if pc==0x80000046:
                    require((address,value,w)==(self.a['__bss_start']+8*self.bss,0,8) and address+8<=self.a['__bss_end'] and self.pre==5 and self.cap==0,'Ordered zero BSS phase');self.bss+=1
                elif pc in self.stores or pc==0x80000246:self.setup_store(pc,address,value&mask,w)
                else:
                    require(not any(address<self.a[n]+size and address+w>self.a[n] for n,size in [('input',1024),('seed',128),('mask',64),('output',144)]),'Unexpected business array store')
                if self.a['replay_log']<=address<self.a['replay_log']+8192 and pc!=0x80000046:
                    require(w==1 and address==self.a['replay_log']+len(self.console),'Console SB/order only')
                    self.console.append(value&255);require(not re.search(r'DETAIL|FAIL|TRAP|MISMATCH',self.console.decode('ascii')),'Raw failure veto')
                self.memory.update({address+j:(value>>(8*j))&255 for j in range(w)})
                if address==self.a['tohost']:
                    require(pc==0x8000007a and w==8 and value==1 and self.regs.get(10)==1,'Actual HTIF1 success')
                    self.validate_complete();self.exited=True;self.exit_count=self.retired
            else:
                require(value is None and set(r['x'])=={desc['register']},'Scalar load schema')
                observed=r['x'][desc['register']];expected=base.word(self.memory,address,w)
                if ((desc['expanded']>>12)&7)<4 and w<8 and expected>>(8*w-1):expected|=MASK^((1<<(8*w))-1)
                require(observed==expected,'Scalar load vs actual initialized bytes')
                if pc in (0x8000033e,0x80000340):self.fixture_read(pc,address,observed,w)
                elif pc in self.readmap:self.oracle(pc,address,observed,w)
                elif self.a['output']<=address<self.a['output']+144:require(False,'Unexpected output load')
        elif pair is None:require(not r['mem'],'Unclassified memory effect')
        if pc==0x8000004e:require(self.bss*8==self.a['__bss_end']-self.a['__bss_start'],'Full BSS before main')
        require(not r['f'],'No scalar FPR instruction in original reduction')
        if r['v']:require(pair is not None and pair[1] in (1,2,4,5,11),'Only actual helper vector writes')
        nxt=self.next_address(r)
        self.vec.update(r['v']);self.csr.update(r['csr']);self.regs.update(r['x']);self.regs[0]=0;self.nextpc=nxt
    def validate_complete(self):
        require(self.calls==6720 and self.active is None and self.step==self.reads==self.fresh==0,'Full6720 complete, not prefix')
        require(self.pre==6 and self.cap==3 and self.flags_seen==21,'Capacity/bootstrap/flags_seen')
        require(self.counts==dict(input_SH=128,seed_SD=128,mask_SD=26880,output_SD=120960,output_LD=120960,fixture_fields=6720),'Complete original source event counts')
        require(self.hcounts=={(op,i):2240 for op in range(3) for i in range(21)},'All3 original21 helpers full multiplicity')
        expected=f'BOARD_CASE_BEGIN {NAME}\nRVV_FP_REDSPECIAL_PASS sew=16 cases=6720 flags_seen=21 errors=0\nBOARD_CASE_PASS {NAME}\nBOARD_REPLAY_PASS\n'
        require(self.console.decode('ascii')==expected,'Full original summary and runtime markers')
        require(self.retired<=2000000,'Finite firmware budget')
    def finish(self):
        require(self.exited,'EOF without complete original HTIF success');self.validate_complete()
        return dict(status='REFERENCE_FULL6720_PASS_SOURCE_ONLY_NOT_DUT',calls=self.calls,output_bytes=967680,flags=6720,vstarts=6720,
                    helper_instructions=sum(self.hcounts.values()),capacity_instructions=3,events=dict(self.counts),flags_seen=self.flags_seen,
                    firmware_to_HTIF=self.exit_count,whole_raw_rows=self.total,park_rows=self.parks,EOF_pure_park=True,console=self.console.decode('ascii'))

def audit(path):
    check=Checker(config())
    try:
        with path.open() as f:
            for line in f:check.consume(parse_line(line))
        return check.finish()
    except BaseException as e:raise ValueError(str(e)+' context='+repr(check.current_context)) from e
