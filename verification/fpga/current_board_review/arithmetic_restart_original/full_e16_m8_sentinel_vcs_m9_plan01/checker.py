"""Full4095 source oracle over actual RVFI, plus lossless six-event protocol."""
from functools import lru_cache
import csv
import importlib.util
from pathlib import Path
import re
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REF=HERE.parent/'full_e16_m8_block_unrolled01'
SOURCE=HERE.parent/'full_e16_m8_sentinel_mask_software02'
REFERENCE=HERE.parent/'full_e16_m8_sentinel_mask_reference_entry01'
G=HERE.parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m

mature=load('full4095_mature_memory_protocol',HERE.parent/'macc_disjoint482/full482_optimized_prepare01/vcs_m8_plan03/checker.py')
common=mature.common
read,require=common.read,common.require
def sha(path):return common.sha(Path(path))
memory_op,loaded_value,is_vector,is_csr=mature.memory_op,mature.loaded_value,mature.is_vector,mature.is_csr
MASK64=(1<<64)-1
CAP=512
SHAPE='rvv_matrix_e16_m8'
SHAPES=(SHAPE,)
ID='arithmetic_original_e16_m8_full4095_sentinel'
READY_SHA='bc6dc1ba90bd6906d16f2c2111380947ce0d92bf3aa3f49c2eabec044f754b87'
ELF_SHA='8ae4c10e852a545ca61b5e4371c399cc6337360292d87ae2da2f5e4787b89b0a'
VETO=re.compile(common.BAD.pattern+r'|\b(?:FAIL|FAILED|ERROR|TRAP|MISMATCH|UNSUPPORTED|ABORTED)\b',re.I)

@lru_cache(maxsize=1)
def model():
    original=load('full4095_sealed_source_model',REF/'model.py')
    seeds,rows,dictionary,masks=original.generate()
    result=[]
    for row in rows:
        raw=b''.join(dictionary[ix].to_bytes(64,'little') for ix in row['indices'])[:1028]
        result.append(dict(row,ordinal=row['ordinal']-1,vstart=row['start'],a=list(original.words(seeds[row['seed']]['a'])),
            b=list(original.words(seeds[row['seed']]['b'])),mask=list(masks[row['mode']]),expected=[int.from_bytes(raw[i:i+2],'little') for i in range(2,1026,2)],raw=raw))
    require(len(result)==4095,'Original full sequence')
    return result

def marker(p=None):
    return 'RVV_MATRIX_PASS sew=16 vlmax=512 cases=4095 elements=2096640 errors=0 seeds=3 guard_tail_mask_vstart=checked'

@lru_cache(maxsize=1)
def rom():
    cfg=load('sentinel_soc_readonly_ROM',SOURCE/'linked_cfg_cost02.py')
    require(sha(SOURCE/'soc/program.elf')==ELF_SHA,'Actual immutable SoC ROM')
    return cfg.Machine(SOURCE/'soc')

@lru_cache(maxsize=1)
def specification(shape=SHAPE):
    require(shape==SHAPE and sha(REFERENCE/'READY.json')==READY_SHA,'Actual new full reference')
    profile=read(HERE/'soc_profile.json')
    common.base.verify_pins(profile['source_inputs'])
    require(profile['elf_sha256']==ELF_SHA and sha(SOURCE/'soc/program.elf')==ELF_SHA,'Exact new SoC, not Spike PC')
    dis=(SOURCE/'soc/program.dis').read_text()
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',dis,re.M)}
    symbols=profile['symbols'];helpers=profile['helpers']
    hp={x['pc'] for window in helpers.values() for x in window}
    require(all(len(w)==(3 if n=='capacity' else 13) and all(code[x['pc']]==x['insn'] for x in w) for n,w in helpers.items()),'Full original helper machine bytes')
    startup=[pc for pc in sorted(code) if symbols['_start']<=pc<symbols['trap_entry'] and is_csr(code[pc])]
    require([code[pc] for pc in startup]==[0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073],'Exact original startup CSR phase')
    require(not [pc for pc,i in code.items() if is_csr(i) and pc not in hp and pc not in startup and pc<symbols['trap_entry']],'No extra startup CSR')
    functions={name:int(address,16) for address,name in re.findall(r'^([0-9a-f]+) <([^>]+)>:',dis,re.M)}
    start=symbols['arithmetic_main'];end=min(v for v in functions.values() if v>start)
    init=[[e['pc'],e['insn'],e['size'],e['offset']] for e in profile['initializer']]
    require(len(init)==129 and sum(e[2] for e in init)==1028 and all(code[e[0]]==e[1] for e in init),'Actual scheduled128SD+SW')
    bss,=[pc for pc in code if pc<symbols['trap_entry'] and code[pc]==0x0002b023]
    exit_pc,=[pc for pc in code if symbols['replay_exit']<=pc<symbols['number'] and code[pc]==0x00a2b023]
    require(code[exit_pc+4]==0xa001 and 'tohost' not in symbols and 'replay_log' not in symbols,'Actual SoCCTRL, not SpikeHTIF')
    failures=[v for k,v in symbols.items() if k=='failure' or k.startswith('failure.')]
    backend=dict(elf=str(SOURCE/'soc/program.elf'),sha256=ELF_SHA,helpers=helpers,
        code={str(pc):i for pc,i in code.items()},symbols=symbols)
    return dict(config=dict(id=SHAPE,sew=16,lmul='m8',cap=512,calls=4095),backend=backend,
        csr_prelude=startup,bss_store=bss,exit_store=exit_pc,park=exit_pc+4,ctrl=0xd0000000,uart=0xc0000000,
        body_start=start,body_end=end,init_stores=init,comparator_paths=profile['comparator_paths'],
        source_seed=profile['seed_profiles'],source_mask=profile['mask_profiles'],failure_pcs=failures,
        ABI_frame_bytes=profile['ABI_frame_bytes'])


def validate_reset(spec):
    profile=read(HERE/'reset_profile.json')
    authority=HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json'
    require(profile['authority_sha256']==sha(authority),'Reviewed M9 reset authority')
    old=read(authority)
    require(profile['initial_gpr_values']==old['initial_gpr_values']==[0]*32 and profile['FpgaEn']==old['FpgaEn']==0 and
        profile['allowed_shape']==SHAPE and profile['original_soc_elf_sha256']==ELF_SHA,'Image-proven reset, not unknown GPR default')
    for key in ('image','image_sha256','snapshot_sha256','compiled_manifest_sha256','configuration_sha256','rtl_pins','source_profile_sha256'):
        require(profile[key]==old[key],'Same frozen M9 reset fact '+key)
    require(sha(profile['image'])==profile['image_sha256'],'Frozen reset image')
    common.base.verify_pins(profile['rtl_pins'])
    require(spec==specification(),'Exact actual ELF spec')
    return dict(enumerate(profile['initial_gpr_values']))

def console_gate(text,p=None,simulator=True):
    require(not VETO.search(text),'Raw failure veto')
    require([line for line in text.splitlines() if line.startswith('RVV_MATRIX_PASS')]==[marker()],
        'Exact original full4095 marker; no invented BEGIN')
    if simulator:require(text.splitlines().count(common.SUCCESS)==1 and '$finish' in text,'Actual CoreSuccess/$finish')

class Strict:
    def __init__(self,spec,gold=None):
        self.spec=spec;self.gold=model() if gold is None else gold
        require(len(self.gold)==4095,'No prefix substitute')
        self.s=spec['backend']['symbols'];self.code={int(k):v for k,v in spec['backend']['code'].items()}
        self.regs=validate_reset(spec);self.memory={}
        self.helpers=spec['backend']['helpers']
        self.lookup={x['pc']:(name,j) for name,window in self.helpers.items() for j,x in enumerate(window)}
        self.rows=self.retired=self.csr_count=self.capacity=self.parking=0;self.cycle=-1
        self.main_entered=self.body_entered=self.exited=False;self.bss_next=self.s['__bss_start']
        self.helper=None;self.index=0;self.active=None;self.calls=[];self.counts=[0]*13;self.offloads=[]
        self.console=bytearray();self.exit_retire=None
        self.fresh={n:set() for n in ('a','b','mask','out')};self.init_index=0
        self.seed_index=self.mask_index=self.dynamic_gold_reads=self.dynamic_ID_reads=0
        self.seed_events=tuple(e for s in spec['source_seed'] for e in s['events'])

    def value(self,address,size):
        require(all(address+i in self.memory for i in range(size)),'Missing actual initialized byte')
        return sum(self.memory[address+i]<<(8*i) for i in range(size))

    def finish_call(self):
        if self.active:
            require(self.helper is None and self.active['reads']==set(range(129)) and self.active['returned_vstart']==0 and self.active['ID_index']==17 and
                self.active['gold_index']==len(self.spec['comparator_paths'][self.active['ordinal']]['gold']),
                'Missing full128word/tail4/guard/status read coverage')

    def begin_call(self,name):
        self.finish_call();ordinal=len(self.calls);require(ordinal<4095,'Extra original call')
        g=self.gold[ordinal];require(name==f'op_{g["op"]}','Original helper/seed/length/mask/start order')
        require([self.regs.get(r) for r in range(10,17)]==[self.s['a'],self.s['b'],self.s['out']+2,g['vl'],512,self.s['mask'],g['vstart']],
            'Actual full source arguments')
        previous=self.gold[ordinal-1] if ordinal else None
        seed_first=previous is None or previous['seed']!=g['seed']
        group_first=previous is None or any(previous[k]!=g[k] for k in ('seed','op','li','mode'))
        for name,values in (('a',g['a']),('b',g['b']),('mask',g['mask']),('out',list(bytes([91,0])*514))):
            require([self.value(self.s[name]+i,1) for i in range(len(values))]==values,'Actual source initialized values '+name)
            if name=='out' or name=='mask' and group_first or name in ('a','b') and seed_first:
                require(self.fresh[name]==set(range(len(values))),'Deleted fresh source initialization '+name)
                self.fresh[name]=set()
        for name in ('a','b'):
            require(all(self.value(self.s[name]+i,1)==0 for i in range(1024,2048)),
                'Physical unused upper typed16 input must remain BSS zero '+name)
        require(all(self.value(self.s['out']+i,1)==0 for i in range(1028,2052)),
            'Physical unused upper output BSS zero')
        require(not any(g['mask'][64:]),'Original physical predicate upper64 zero')
        require(self.init_index==129,'Every-call exact1028 initializer store ledger');self.init_index=0
        require(self.value(self.s['checks'],8)==ordinal and self.value(self.s['elements'],8)==ordinal*512 and self.value(self.s['errors'],8)==0,
            'Actual original ordinal/counters')
        require(self.seed_index==1472*(g['seed']+1) and self.mask_index==(16 if group_first else 0),'Exact original RNG/mask store epochs')
        self.mask_index=0
        self.active=dict(ID_index=0,gold_index=0,ordinal=ordinal,original_ordinal=ordinal+1,op=g['op'],seed=g['seed'],vl=g['vl'],mode=g['mode'],
            vstart=g['vstart'],reads=set(),returned_vstart=None,entry_retire=self.retired)
        self.calls.append(self.active)

    def consume(self,row):
        self.rows+=1;cycle=int(row['cycle'])
        require(cycle>=self.cycle and row['event'] in ('retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done') and int(row['trap'])==0,
            'Cycle/unknown event/trap');self.cycle=cycle
        if row['event']!='retire':return
        require(int(row['order'])==self.retired,'Retire order/drop/duplicate');self.retired+=1
        pc,insn=int(row['pc'],16),int(row['insn'],16);rd,result=int(row['rd']),int(row['rd_wdata'],16)
        addr,rm,wm,wd=(int(row[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        require(self.code.get(pc)==insn and (self.retired!=1 or pc==self.s['_start']),'Actual ELF/startup PC/code')
        if self.exited:
            require(pc==self.spec['park'] and insn==0xa001 and rd==rm==wm==0,'Post-exit only parking');self.parking+=1;return
        require(pc!=self.s['trap_entry'] and pc not in self.spec['failure_pcs'],'Original actual failure/trap PC')
        if pc==self.s['main']:
            require(not self.main_entered and self.bss_next==self.s['__bss_end'] and self.csr_count==5,'Complete startup/BSS/main phase')
            self.main_entered=True
        if pc==self.spec['body_start']:
            require(self.main_entered and not self.body_entered,'Actual arithmetic main once');self.body_entered=True
        site=self.lookup.get(pc)
        if site:
            name,j=site
            if j==0:
                require(self.helper is None and self.body_entered and self.csr_count==5,'Helper phase/overlap')
                if name=='capacity':require(not self.calls and self.capacity==0,'Capacity repeated');self.capacity=1
                else:require(self.capacity==1,'Capacity missing');self.begin_call(name)
                self.helper=name;self.index=0
            require(self.helper==name and self.index==j,'Exact contiguous original helper window')
            if name=='capacity':
                if j==0:require((rd,result)==(5,MASK64),'Actual capacity li t0=-1')
                if j==1:require(self.regs.get(5)==MASK64 and (rd,result)==(10,512),'Actual VLMAX512 source/result')
                if j==2:require(rd==rm==wm==0,'Actual capacity ret no side effects')
            if name!='capacity':
                g=self.gold[self.active['ordinal']]
                if j in (0,5,10):require((rd,result)==(5,g['vl'] if j==5 else 512),'Original vset VL')
                if j==6:require((rd,result)==(28,7),'Original scalar7 instruction')
                if j in (7,8):require(self.regs.get(16)==g['vstart'] and rd==0,'Actual vstart operand')
                if j==8:
                    require(self.regs.get(28)==7,'Target scalar operand')
                    self.active.update(target_pc=pc,target_insn=insn,target_cycle=cycle,target_retire=self.retired)
                if j==9:require((rd,result)==(10,0),'Actual returned vstart');self.active['returned_vstart']=0
                if j in (1,2,3,4,11,12):require(rd==0,'Unexpected helper integer destination')
                self.counts[j]+=1
            self.index+=1
            if self.index==len(self.helpers[name]):self.helper=None;self.index=0
        else:require(self.helper is None,'Escaped original helper window')
        if mature.transport.transport.vector(insn):
            kind='configuration';required=False;call=None
            if site and site[0]!='capacity':
                call=self.active['ordinal']
                if site[1] in (1,2,3,4,11):kind='memory';required=True
                elif site[1]==8:kind='target';required=target_required(insn,self.gold[call])
            self.offloads.append(dict(insn=insn,pc=pc,retire_order=self.retired-1,call=call,
                helper_index=site[1] if site else None,kind=kind,required=required))
        if is_vector(insn):require(site is not None,'RVV outside original helpers')
        if is_csr(insn) and site is None:
            require(not self.main_entered and self.csr_count<5 and pc==self.spec['csr_prelude'][self.csr_count],
                'CSR outside exact original phase');self.csr_count+=1
        desc=memory_op(insn)
        if desc:
            size=desc['size'];require(desc['base'] in self.regs and addr==(self.regs[desc['base']]+desc['offset'])&MASK64,'Decoded scalar address/base')
            enable=((1<<size)-1)<<(addr%8);require(addr%size==0 and enable<=255,'Scalar alignment/byte enables')
            if desc['kind']=='write':
                bits=(1<<(8*size))-1
                require(wm==enable and rm==0 and desc['register'] in self.regs and wd&bits==self.regs[desc['register']]&bits,
                    'Actual scalar store BE/source GPR/value')
                if pc==self.spec['bss_store']:
                    require(not self.main_entered and size==8 and wd==0 and addr==self.bss_next and addr+8<=self.s['__bss_end'] and
                        self.regs.get(6)==self.s['__bss_end'],'Exact pre-main ordered BSS zero');self.bss_next+=8
                elif addr<self.s['out']+2052 and addr+size>self.s['out']:
                    require(self.body_entered and self.spec['body_start']<=pc<self.spec['body_end'] and self.init_index<129,
                        'Output write owner/extra init')
                    index=self.init_index;want=self.spec['init_stores'][index]
                    require((pc,insn,size)==tuple(want[:3]) and addr==self.s['out']+want[3] and
                        wd&bits==(0x005b005b if size==4 else 0x005b005b005b005b),'Exact1028 typed005b initializer PC/order/data')
                    self.init_index+=1
                if self.body_entered and self.spec['body_start']<=pc<self.spec['body_end']:
                    nextcall=len(self.calls)
                    if any(self.s[n]<=addr<self.s[n]+2048 for n in ('a','b')):
                        require(nextcall in (0,1365,2730) and self.init_index==self.mask_index==0,'Original source RNG phase')
                        events=self.seed_events
                        require(self.seed_index<len(events),'Extra source RNG store')
                        e=events[self.seed_index]
                        require((pc,insn,addr,size,wd&bits)==(e['pc'],e['insn'],self.s[e['bank']]+e['offset'],e['size'],e['value']),'Exact source RNG PC/order/width/value')
                        self.seed_index+=1
                    if self.s['mask']<=addr<self.s['mask']+128:
                        require(nextcall<4095 and self.gold[nextcall]['si']==0 and self.init_index==0 and self.mask_index<16,'Original sixteen mask stores per group')
                        e=self.spec['source_mask'][self.gold[nextcall]['mode']]['events'][self.mask_index]
                        require((pc,insn,addr,size,wd)==(e['pc'],e['insn'],self.s['mask']+e['offset'],e['size'],e['value']),'Actual mask PC/order/width/value')
                        self.mask_index+=1
                for i in range(size):self.memory[addr+i]=(wd>>(8*i))&255
                if self.body_entered and self.spec['body_start']<=pc<self.spec['body_end']:
                    for name,length in (('a',1024),('b',1024),('mask',128),('out',1028)):
                        base=self.s[name]
                        if base<=addr<base+length:
                            require(addr+size<=base+length,'Business input/output footprint')
                            self.fresh[name].update(range(addr-base,addr-base+size))
                if addr==self.spec['uart']:
                    require(self.main_entered and size==1 and len(self.console)<8192,'UART real byte protocol');self.console.append(wd&255)
                if addr==self.spec['ctrl']:
                    require(pc==self.spec['exit_store'] and size==8 and wd==0 and self.regs.get(10)==0,'Actual CTRL raw exit0')
                    self.finish_call();self.exited=True;self.exit_retire=self.retired
            else:
                require(rm==enable and wm==0 and rd==desc['register'],'Scalar read BE/destination')
                if self.s['_start']<=addr and addr+size<=self.s['__bss_start']:
                    require(result==loaded_value(rom().initial(addr,size),size,desc['signed']),'Actual immutable ELF scalar read bits')
                for name,length,key in (('expected_indices',4095*34,'IDs'),('expected_dictionary',3598*64,'gold')):
                    if self.s[name]<=addr<self.s[name]+length:
                        require(self.active is not None and self.helper is None,'Dictionary/ID comparison phase')
                        cursor='ID_index' if key=='IDs' else 'gold_index'
                        events=self.spec['comparator_paths'][self.active['ordinal']][key];index=self.active[cursor]
                        require(index<len(events),'Duplicate dictionary/ID load')
                        e=events[index]
                        require((pc,addr,size,result)==(e['pc'],e['address'],e['size'],loaded_value(e['value'],size,desc['signed'])),'Actual ID0/nonzero dictionary load PC/order/value')
                        self.active[cursor]+=1
                        if key=='IDs':self.dynamic_ID_reads+=1
                        else:self.dynamic_gold_reads+=1
                if self.s['out']<=addr<self.s['out']+1028:
                    require(self.active is not None and self.helper is None,'Output oracle phase')
                    offset=addr-self.s['out'];chunk=offset//8
                    require(offset%8==0 and size==(4 if offset==1024 else 8) and self.spec['comparator_paths'][self.active['ordinal']]['output'].get(str(offset))==pc and chunk not in self.active['reads'],
                        'Full128word+actual LW tail4 oracle read/drop/duplicate')
                    raw=self.gold[self.active['ordinal']]['raw'];expected=int.from_bytes(raw[offset:offset+size],'little')
                    if result!=loaded_value(expected,size,desc['signed']):
                        delta=(result^expected)&((1<<(8*size))-1);byte=next((i for i in range(size) if (delta>>(8*i))&255),0)
                        position=offset+byte;g=self.gold[self.active['ordinal']]
                        category='guard' if position//2 in (0,513) else 'tail' if position//2-1>=g['vl'] else 'prestart' if position//2-1<g['vstart'] else 'result'
                        raise ValueError(f'call={self.active["original_ordinal"]} {category} byte={position} element={position//2} cycle={cycle} pc={pc:08x} insn={insn:08x} '
                            f'expected=0x{expected:x} actual=0x{result:x}')
                    self.active['reads'].add(chunk)
        elif not is_vector(insn):require(rm==wm==0,'Unclassified scalar memory effect')
        if rd and insn&127 not in (7,0x53,0x43,0x47,0x4b,0x4f):self.regs[rd]=result
        self.regs[0]=0

    def finish(self):
        self.finish_call()
        require(self.exited and self.capacity==1 and len(self.calls)==4095 and self.counts==[4095]*13 and self.csr_count==5,
            'Complete full4095 original ledger')
        require(self.value(self.s['checks'],8)==4095 and self.value(self.s['elements'],8)==2096640 and self.value(self.s['errors'],8)==0,
            'Actual final original counters')
        require(self.seed_index==4416 and self.dynamic_ID_reads==69615 and self.dynamic_gold_reads==109575,'Complete actual RNG/ID/gold load ledgers')
        console_gate(self.console.decode('ascii'),simulator=False)
        return dict(status='FULL4095_ACTUAL_RVFI_ACCEPTED_NOT_LINUX',calls=4095,results=2096640,guards=8190,
            returned_vstart_zero=4095,helper_instructions=53235,routine_counts=self.counts,packed_output_reads=528255,
            fresh_output_bytes_each_call=1028,typed_sentinel='005b',tail_read_bytes=4,physical_registers_each_group=8,vtype=11,mask_initialization='Original per-group reuse',seed_initialization='Original once per seed',
            rows=self.rows,retired=self.retired,last_cycle=self.cycle,parking=self.parking,firmware_through_ctrl=self.exit_retire,
            full_order=True,partitioned=False,fflags_oracle='Original integer source has no explicit fflags oracle',
            original_RNG_stores=self.seed_index,mask_stores=25200,dynamic_ID_reads=self.dynamic_ID_reads,dynamic_gold_reads=self.dynamic_gold_reads,
            call_ledger=[dict(call,reads=sorted(call['reads'])) for call in self.calls])

eligibility=load('immutable_typed16_source_owner_eligibility',HERE/'owner_policy.py')

def target_required(insn,g):
    return eligibility.required_target(insn,g['vl'],g['vstart'])

@lru_cache(maxsize=1)
def owner_contract():
    spec=specification();rows=model()
    targets=[(spec['backend']['helpers'][f'op_{g["op"]}'][8]['insn'],g) for g in rows]
    return dict(compulsory_memory_owners=len(rows)*5,
        required_target_owners=sum(target_required(i,g) for i,g in targets),
        required_op24_memory_targets=sum(g['op']==24 and target_required(i,g) for i,g in targets),
        optional_slideup_targets=sum(eligibility.no_work_reason(i,g['vl'],g['vstart'])==
            'unsigned_vslideup_vi_offset_ge_vl' for i,g in targets),
        elidable_target_owners=sum(not target_required(i,g) for i,g in targets))

class OwnerObserver(mature.OwnerObserver):
    def owner_coverage(self,ledger,gold):
        # The mature exact token/replay protocol is unchanged. Only the actual
        # source instruction eligibility differs from its old vstart<VL shortcut.
        require([r['insn'] for r in ledger]==self.retvec,'Actual retired offload ledger differs')
        index=0;owners=[];replays=[]
        for order,insn in enumerate(self.arch):
            if index<len(ledger) and insn==ledger[index]['insn']:
                item=dict(ledger[index],arch_order=order,alloc=self.owner_alloc[order],done=self.owner_done[order])
                require(item['alloc']==item['done'],'Owner alloc/done mismatch')
                if item['required']:require(item['alloc']>0,'Missing necessary architectural owner '+str(item))
                if item['kind']=='configuration':require(item['alloc']==0,'Configuration cannot own backend data uop')
                owners.append(item);index+=1
            else:
                csr=insn>>20;funct3=(insn>>12)&7;rs1=(insn>>15)&31;rd=(insn>>7)&31
                replay=(insn&127==0x73 and funct3 in (2,3) and rs1==0 and
                    csr in (8,9,10,15,0xc20,0xc21,0xc22) and
                    (rd==0 or order>0 and insn==self.arch[order-1]))
                require(replay and self.owner_alloc[order]==self.owner_done[order]==0,
                    'Non-configuration replay or replay backend owner')
                replays.append(order)
        require(index==len(ledger),'Missing architectural offload owner')
        memories=[r for r in owners if r['kind']=='memory'];targets=[r for r in owners if r['kind']=='target']
        expected_targets=sum(target_required(specification()['backend']['helpers'][f'op_{g["op"]}'][8]['insn'],g)
            for g in gold['rows'])
        require(len(memories)==len(gold['rows'])*5 and len(targets)==len(gold['rows']) and
            sum(r['required'] for r in targets)==expected_targets,'Natural helper owner scope differs')
        by_call={}
        for item in memories:by_call.setdefault(item['call'],[]).append(item['helper_index'])
        require(by_call=={call:[1,2,3,4,11] for call in range(len(gold['rows']))},
            'Missing/duplicate per-call compulsory memory owner')
        return dict(status='EVERY_NECESSARY_RETIRED_OWNER_COMPLETED',compulsory_memory_owners=len(memories),
            required_target_owners=expected_targets,elidable_target_owners=len(targets)-expected_targets,
            required_alloff_target_owners=sum(target_required(specification()['backend']['helpers'][f'op_{g["op"]}'][8]['insn'],g)
                and not any(gold['masks'][g['mode']]) for g in gold['rows']),
            minimum_required_owners=len(memories)+expected_targets,
            harmless_configuration_replay_arch_orders=replays,owner_ledger=owners)

def audit(path,spec,abort):
    start=time.monotonic();print('PHASE strict+generic closedCSV START',flush=True)
    _,_,(base,_,_,_)=common.image_context(Path(read(HERE/'reset_profile.json')['image']).parent)
    protocol=sys.modules['ara_verify.trace']
    state=Strict(spec);observer=OwnerObserver(protocol)
    with Path(path).open(newline='') as stream:
        for row in observer.rows(csv.DictReader(stream)):
            if state.rows%4096==0:require(not abort.is_set(),'Late abort during full4095 checks')
            try:state.consume(row)
            except Exception as error:
                raise ValueError(f'CSV firstcause row={state.rows} call={state.active["original_ordinal"] if state.active else None} '
                    f'cycle={row.get("cycle")} event={row.get("event")} pc={row.get("pc")} insn={row.get("insn")}: {error}') from error
            if state.rows%1000000==0:
                print(f'PHASE strict+generic rows={state.rows} calls={len(state.calls)} elapsed={time.monotonic()-start:.3f}s',flush=True)
    generic=observer.finish();mature.protocol_presence(generic)
    strict=state.finish();coverage=observer.owner_coverage(state.offloads,dict(rows=state.gold,masks=[state.gold[i]['mask'] for i in (0,3,6)]))
    require((strict['rows'],strict['retired'],strict['last_cycle'])==(generic['rows'],generic['retire_count'],generic['last_cycle']),
        'Generic/strict full trace counts differ')
    contract=owner_contract()
    op24=contract['required_op24_memory_targets']
    require(coverage['compulsory_memory_owners']==contract['compulsory_memory_owners'] and
        coverage['required_target_owners']==contract['required_target_owners'],'Model-derived owner scope')
    coverage['required_op24_memory_targets']=op24
    coverage['optional_slideup_targets']=contract['optional_slideup_targets']
    print(f'PHASE strict+generic ACCEPTED elapsed={time.monotonic()-start:.3f}s',flush=True)
    return dict(strict=strict,generic=generic,owner_coverage=coverage,actual_csv_sha256=sha(path),strict_csv_parses=1)

def check_run_artifacts(result,case,ledger):
    require(result.returncode==0 and 0<=result.elapsed_s<=case['timeout_s'],'Actual exit/budget')
    root=result.artifact_dir
    console_gate((root/'console.log').read_text())
    console_gate((root/'work/run.vcs.log').read_text())
    require(sha(root/'input.elf')==case['sha256'],'Private actual SoC ELF')
    inputs=read(root/'inputs.json')
    require(inputs['binary']==dict(sha256=case['sha256'],source=case['elf'],path=str(root/'input.elf')),'Private ELF provenance')
    require(inputs['simv']==dict(path=ledger['simv'],image_sha256=ledger['files']),'Actual frozen image provenance')
    command=read(root/'command.json')
    require(command==dict(cwd=str(root/'work'),command=[ledger['simv'],'-l','run.vcs.log',
        '+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),'+TESTCASE='+case['id'],
        '+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv'),'+COMMIT_WATCHDOG=1000000']),
        'Exact diagnostic real-command gate')
    require((root/'commit_trace.csv').stat().st_size>0 and read(root/'trace_summary.json')['status']=='VALID','Frozen generic complete trace')

def artifacts(result,case,ledger,spec,abort):
    require(result.status=='PASS' and type(result.returncode)is int and result.returncode==0 and not abort.is_set(),'Actual numeric outcome')
    check_run_artifacts(result,case,ledger)
    for name in ('console.log','work/run.vcs.log'):console_gate((result.artifact_dir/name).read_text())
    return audit(result.artifact_dir/'commit_trace.csv',spec,abort)
