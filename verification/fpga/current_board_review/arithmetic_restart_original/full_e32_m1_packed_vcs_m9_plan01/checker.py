"""Full5985 source oracle over actual RVFI, plus lossless six-event protocol."""
from functools import lru_cache
import csv
import importlib.util
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent/'full_e32_m1_packed_prepare01'
REF=ROOT/'reference_entry01'
SOFT=ROOT/'software02'
import lifecycle
G=HERE.parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m

mature=load('full5985_mature_memory_protocol',HERE.parent/'macc_disjoint482/full482_optimized_prepare01/vcs_m8_plan03/checker.py')
common=mature.common
read,require=common.read,common.require
def sha(path):return common.sha(Path(path))
memory_op,loaded_value,is_vector,is_csr=mature.memory_op,mature.loaded_value,mature.is_vector,mature.is_csr
MASK64=(1<<64)-1
CAP=32
SHAPE='rvv_matrix_e32_m1'
SHAPES=(SHAPE,)
ID='arithmetic_original_e32_m1_full5985_packed'
READY_SHA='d1f70125ab071283390749323120204356e07da6a3a420f450e46c58e5859691'
ELF_SHA='8b6c67293ad57aff6ddeaf478aa4c94bd07d44421f3c6eb901378fe4cf23db5c'
VETO=re.compile(common.BAD.pattern+r'|\b(?:FAIL|FAILED|ERROR|TRAP|MISMATCH|UNSUPPORTED|ABORTED)\b',re.I)

@lru_cache(maxsize=1)
def model():
    rows=read(SOFT/'sequence.json')
    result=[dict(row,ordinal=row['ordinal']-1,vstart=row['start'],
        raw=b''.join(word.to_bytes(8,'little') for word in row['words'])) for row in rows]
    require(len(result)==5985 and all(len(r['raw'])==136 for r in result),'Original full sequence/17 words')
    return result

def target_required(insn,row,spec=None):
    spec=specification() if spec is None else spec
    expected=spec['backend']['helpers'][f'op_{row["op"]}'][8]['insn']
    require(insn==expected,'Target encoding differs from actual original helper')
    if row['op']==19:
        require(insn==0x38813c57 and insn&127==0x57 and (insn>>12)&7==3 and insn>>26==14,
            'No-op restricted to original VSLIDEUP.VI')
        offset=(insn>>15)&31
        require(offset==2,'Original unsigned offset2')
        if offset>=row['vl']:return False
    return row['vstart']<row['vl']

@lru_cache(maxsize=1)
def owner_counts():
    gold=model()
    spec=specification()
    targets=sum(target_required(spec['backend']['helpers'][f'op_{g["op"]}'][8]['insn'],g,spec) for g in gold)
    return dict(compulsory_memory_owners=len(gold)*5,required_target_owners=targets,
        required_op24_memory_targets=sum(g['op']==24 and g['vstart']<g['vl'] for g in gold),
        minimum_required_owners=len(gold)*5+targets)


def marker(p=None):
    return 'RVV_MATRIX_PASS sew=32 vlmax=32 cases=5985 elements=191520 errors=0 seeds=3 guard_tail_mask_vstart=checked'

@lru_cache(maxsize=1)
def specification(shape=SHAPE):
    require(shape==SHAPE and sha(REF/'READY.json')==READY_SHA,'Actual full5985 READY identity')
    proof=read(SOFT/'proof.json');backend=dict(proof['backends']['soc'])
    require(backend['sha256']==ELF_SHA and sha(backend['elf'])==ELF_SHA,'Actual sealed SoC ELF')
    require(proof['scope']['calls']==5985 and proof['scope']['ops']==35,'Source order/fallback')
    dis=(SOFT/'soc/program.dis').read_text()
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',dis,re.M)}
    symbols=read(SOFT/'soc/symbols.json')
    helpers=backend['helpers'];hp={x['pc'] for window in helpers.values() for x in window}
    require(set(helpers)=={'capacity'}|{f'op_{i}' for i in range(35)},'All36 original routines')
    for name,window in helpers.items():
        require(len(window)==(3 if name=='capacity' else 13) and all(code[x['pc']]==x['insn'] for x in window),'Original actual helper bytes')
        if name=='capacity':require(window[1]['insn']==0x0102f557,'Actual e32m1 capacity vtype16')
        else:
            require([window[j]['insn'] for j in (0,1,2,3,4,5,7,9,10,11)]==
                [0x010772d7,0x02056407,0x0205e807,0x02066c07,0x02b78007,
                 0x0106f2d7,0x00881073,0x00802573,0x010772d7,0x02066c27],
                'Exact e32m1 vtype16/group1/mask128buffer-vlm4bytes/helper memory/CSR')
    startup=[pc for pc in sorted(code) if symbols['_start']<=pc<symbols['trap_entry'] and is_csr(code[pc])]
    require([code[pc] for pc in startup]==[0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073],
        'Actual five startup CSRs, no invented vlenb')
    require(not [pc for pc,i in code.items() if is_csr(i) and pc not in hp and pc not in startup and pc<symbols['trap_entry']],
        'Unexpected startup CSR')
    functions={name:int(address,16) for address,name in re.findall(r'^([0-9a-f]+) <([^>]+)>:',dis,re.M)}
    start=symbols['arithmetic_main'];end=min(v for v in functions.values() if v>start)
    init=[[pc,code[pc],8,i*8] for i,pc in enumerate(lifecycle.INIT_PC)]
    oracle=[[pc,code[pc],8,i*8] for i,pc in enumerate(lifecycle.READ_PC)]
    for entries,kind in ((init,'write'),(oracle,'read')):
        for pc,insn,size,offset in entries:
            desc=memory_op(insn)
            require(desc and desc['kind']==kind and desc['size']==8 and desc['base']==22 and desc['offset']==offset,
                'Actual full17 SD/LD exact136 bytes; no tail truncation')
    lifecycle.Lifecycle(symbols,code,[helpers[f'op_{i}'][0]['pc'] for i in range(35)],model())
    uart_start=symbols['replay_write'];uart_end=min(v for v in functions.values() if v>uart_start)
    uart_store,=[pc for pc in sorted(code) if uart_start<=pc<uart_end and
        (desc:=memory_op(code[pc])) and desc['kind']=='write' and desc['size']==1 and
        desc['base']==14 and desc['register']==15]
    require(code[uart_store]==0x00f70023,'Actual normal replay_write UART store, not syscall-error path')
    bss,=[pc for pc in code if pc<symbols['trap_entry'] and code[pc]==0x0002b023]
    exit_pc,=[pc for pc in code if symbols['replay_exit']<=pc<symbols['number'] and code[pc]==0x00a2b023]
    require(code[exit_pc+4]==0xa001 and 'tohost' not in symbols and 'replay_log' not in symbols,'Actual CTRL0, not HTIF')
    failures=[v for k,v in symbols.items() if k=='failure' or k.startswith('failure.')]
    require(failures,'Real failure.part PC must be forbidden')
    backend.update(code={str(pc):i for pc,i in code.items()},symbols=symbols)
    return dict(config=dict(id=SHAPE,sew=32,lmul='m1',cap=32,calls=5985,vtype=16,physical_group_registers=1,observed_group_bytes=128,mask_bytes=128,vlm_bytes=4),backend=backend,
        csr_prelude=startup,bss_store=bss,exit_store=exit_pc,park=exit_pc+4,ctrl=0xd0000000,uart=0xc0000000,
        body_start=start,body_end=end,init_stores=init,oracle_reads=oracle,mask_store=lifecycle.CLEAR_PC[0],uart_store=uart_store,failure_pcs=failures)

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
        'Exact original full5985 marker; no invented BEGIN')
    if simulator:require(text.splitlines().count(common.SUCCESS)==1 and '$finish' in text,'Actual CoreSuccess/$finish')

class Strict:
    def __init__(self,spec,gold=None):
        self.spec=spec;self.gold=model() if gold is None else gold
        require(len(self.gold)==5985,'No prefix substitute')
        self.s=spec['backend']['symbols'];self.code={int(k):v for k,v in spec['backend']['code'].items()}
        self.regs=validate_reset(spec);self.memory={}
        self.helpers=spec['backend']['helpers']
        self.lookup={x['pc']:(name,j) for name,window in self.helpers.items() for j,x in enumerate(window)}
        self.rows=self.retired=self.csr_count=self.capacity=self.parking=0;self.cycle=-1
        self.main_entered=self.body_entered=self.exited=False;self.bss_next=self.s['__bss_start']
        self.helper=None;self.index=0;self.active=None;self.calls=[];self.counts=[0]*13;self.offloads=[]
        self.console=bytearray();self.exit_retire=None
        self.fresh={n:set() for n in ('a','b','mask','out')};self.init_index=0
        self.life=lifecycle.Lifecycle(self.s,self.code,[self.helpers[f'op_{i}'][0]['pc'] for i in range(35)],self.gold)

    def value(self,address,size):
        require(all(address+i in self.memory for i in range(size)),'Missing actual initialized byte')
        return sum(self.memory[address+i]<<(8*i) for i in range(size))

    def finish_call(self):
        if self.active:
            require(self.helper is None and self.active['reads']==set(range(17)) and self.active['returned_vstart']==0,
                'Missing full17word/32bitguards/status read coverage')

    def begin_call(self,name):
        self.finish_call();ordinal=len(self.calls);require(ordinal<5985,'Extra original call')
        g=self.gold[ordinal];require(name==f'op_{g["op"]}','Original helper/seed/length/mask/start order')
        require([self.regs.get(r) for r in range(10,17)]==[self.s['a'],self.s['b'],self.s['out']+4,g['vl'],32,self.s['mask'],g['vstart']],
            'Actual full source arguments')
        for name,values in (('a',list(lifecycle.words(g['a']))),('b',list(lifecycle.words(g['b']))),
                ('mask',g['mask']),('out',list(lifecycle.words([91]*34)))):
            require([self.value(self.s[name]+i,1) for i in range(len(values))]==values,'Actual source initialized values '+name)
            if name=='out' or name=='mask' and g['si']==0 or name in ('a','b') and (g['op']>=25 or ordinal%1995==0):
                require(self.fresh[name]==set(range(len(values))),'Deleted fresh source initialization '+name)
                self.fresh[name]=set()
        require(self.init_index==17,'Every-call exact136 initializer store ledger');self.init_index=0
        require(self.value(self.s['checks'],8)==ordinal and self.value(self.s['elements'],8)==ordinal*32 and self.value(self.s['errors'],8)==0,
            'Actual original ordinal/counters')
        self.active=dict(ordinal=ordinal,original_ordinal=ordinal+1,op=g['op'],seed=g['seed'],vl=g['vl'],mode=g['mode'],
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
        self.life.enter(pc)
        site=self.lookup.get(pc)
        if site:
            name,j=site
            if j==0:
                require(self.helper is None and self.body_entered and self.csr_count==5,'Helper phase/overlap')
                if name=='capacity':require(not self.calls and self.capacity==0,'Capacity repeated');self.capacity=1
                else:require(self.capacity==1,'Capacity missing');self.begin_call(name)
                self.helper=name;self.index=0
            require(self.helper==name and self.index==j,'Exact contiguous original helper window')
            if name=='capacity' and j==1:require((rd,result)==(10,32),'Actual VLMAX32')
            if name!='capacity':
                g=self.gold[self.active['ordinal']]
                if j in (0,5,10):require((rd,result)==(5,g['vl'] if j==5 else 32),'Original vset VL')
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
                elif site[1]==8:kind='target';required=target_required(insn,self.gold[call],self.spec)
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
                self.life.store(pc,insn,addr,size,wd & bits)
                if pc==self.spec['bss_store']:
                    require(not self.main_entered and size==8 and wd==0 and addr==self.bss_next and addr+8<=self.s['__bss_end'] and
                        self.regs.get(6)==self.s['__bss_end'],'Exact pre-main ordered BSS zero');self.bss_next+=8
                elif addr<self.s['out']+4104 and addr+size>self.s['out']:
                    require(self.body_entered and self.spec['body_start']<=pc<self.spec['body_end'] and self.init_index<17,
                        'Output write owner/extra init')
                    index=self.init_index;want=self.spec['init_stores'][index]
                    require((pc,insn,size)==tuple(want[:3]) and addr==self.s['out']+want[3] and
                        wd==lifecycle.SENTINEL,'Exact136 initializer PC/order/data')
                    self.init_index+=1
                for i in range(size):self.memory[addr+i]=(wd>>(8*i))&255
                if self.body_entered and self.spec['body_start']<=pc<self.spec['body_end']:
                    for name,length in (('a',128),('b',128),('mask',128),('out',136)):
                        base=self.s[name]
                        backing=128 if name=='mask' else 4104 if name=='out' else 4096
                        if addr<base+backing and addr+size>base:
                            require(base<=addr and addr+size<=base+length,'Business input/output footprint')
                            self.fresh[name].update(range(addr-base,addr-base+size))
                if addr==self.spec['uart']:
                    require(self.main_entered and size==1 and len(self.console)<8192,'UART real byte protocol');self.console.append(wd&255)
                if addr==self.spec['ctrl']:
                    require(pc==self.spec['exit_store'] and size==8 and wd==0 and self.regs.get(10)==0,'Actual CTRL raw exit0')
                    self.finish_call();self.exited=True;self.exit_retire=self.retired
            else:
                require(rm==enable and wm==0 and rd==desc['register'],'Scalar read BE/destination')
                self.life.read(pc,addr,size)
                if self.s['out']<=addr<self.s['out']+4104:
                    require(self.active is not None and self.helper is None,'Output oracle phase')
                    offset=addr-self.s['out'];chunk=offset//8
                    require(offset+size<=136 and offset%8==0 and size==8 and chunk not in self.active['reads'],
                        'Full17word+uint32guards oracle read/drop/duplicate')
                    require([pc,insn,size,offset]==self.spec['oracle_reads'][chunk],'Actual oracle load PC/code/offset')
                    raw=self.gold[self.active['ordinal']]['raw'];expected=int.from_bytes(raw[offset:offset+size],'little')
                    if result!=loaded_value(expected,size,desc['signed']):
                        delta=(result^expected)&((1<<(8*size))-1);byte=next((i for i in range(size) if (delta>>(8*i))&255),0)
                        position=offset+byte;g=self.gold[self.active['ordinal']]
                        category='guard' if position<4 or position>=132 else 'tail' if (position-4)//4>=g['vl'] else 'prestart' if (position-4)//4<g['vstart'] else 'result'
                        raise ValueError(f'call={self.active["original_ordinal"]} {category} byte={position} pc={pc:08x} insn={insn:08x} '
                            f'expected=0x{expected:x} actual=0x{result:x}')
                    self.active['reads'].add(chunk)
        elif not is_vector(insn):require(rm==wm==0,'Unclassified scalar memory effect')
        if rd and insn&127 not in (7,0x53,0x43,0x47,0x4b,0x4f):self.regs[rd]=result
        self.regs[0]=0

    def finish(self):
        self.finish_call();self.life.finish()
        require(self.exited and self.capacity==1 and len(self.calls)==5985 and self.counts==[5985]*13 and self.csr_count==5,
            'Complete full5985 original ledger')
        require(self.value(self.s['checks'],8)==5985 and self.value(self.s['elements'],8)==191520 and self.value(self.s['errors'],8)==0,
            'Actual final original counters')
        console_gate(self.console.decode('ascii'),simulator=False)
        return dict(status='FULL5985_ACTUAL_RVFI_ACCEPTED_NOT_LINUX',calls=5985,results=191520,guards=11970,
            returned_vstart_zero=5985,helper_instructions=77805,routine_counts=self.counts,packed_output_reads=101745,
            fresh_output_bytes_each_call=136,mask_initialization='Original per-group reuse',seed_initialization='Original once per seed',FP_calls=self.life.fp_calls,FP_input_scalar_writes=self.life.fp_stores,
            mask_clear_stores=self.life.mask_clear_stores,mask_bit_stores=self.life.mask_bit_stores,
            rows=self.rows,retired=self.retired,last_cycle=self.cycle,parking=self.parking,firmware_through_ctrl=self.exit_retire,
            full_order=True,partitioned=False,fflags_oracle='Original source has no explicit fflags oracle',
            call_ledger=[dict(call,reads=sorted(call['reads'])) for call in self.calls])

class OwnerObserver(mature.OwnerObserver):
    def owner_coverage(self,ledger,gold):
        require([r['insn'] for r in ledger]==self.retvec,'Actual retired offload ledger differs')
        spec=specification()
        index=0;owners=[];replays=[]
        for order,insn in enumerate(self.arch):
            if index<len(ledger) and insn==ledger[index]['insn']:
                item=dict(ledger[index],arch_order=order,
                    alloc=self.owner_alloc[order],done=self.owner_done[order])
                require(item['alloc']==item['done'],'Owner alloc/done mismatch')
                if item['kind']=='target':
                    require(item['required']==target_required(insn,gold['rows'][item['call']],spec),
                        'Target required differs from actual opcode/VL')
                if item['required']:
                    require(item['alloc']>0,'Missing necessary architectural owner '+str(item))
                if item['kind']=='configuration':
                    require(item['alloc']==0,'Configuration cannot own backend data uop')
                owners.append(item);index+=1
            else:
                # Exactly the frozen generic side-effect-free CSR-read replay rule.
                csr=insn>>20;funct3=(insn>>12)&7;rs1=(insn>>15)&31;rd=(insn>>7)&31
                replay=(insn&127==0x73 and funct3 in (2,3) and rs1==0 and
                    csr in (8,9,10,15,0xc20,0xc21,0xc22) and
                    (rd==0 or order>0 and insn==self.arch[order-1]))
                require(replay and self.owner_alloc[order]==self.owner_done[order]==0,
                    'Non-configuration replay or replay backend owner')
                replays.append(order)
        require(index==len(ledger),'Missing architectural offload owner')
        memories=[r for r in owners if r['kind']=='memory']
        targets=[r for r in owners if r['kind']=='target']
        expected_targets=sum(target_required(spec['backend']['helpers'][f'op_{g["op"]}'][8]['insn'],g,spec) for g in gold['rows'])
        require(len(memories)==len(gold['rows'])*5 and len(targets)==len(gold['rows']) and
                sum(r['required'] for r in targets)==expected_targets,'Natural helper owner scope differs')
        for call in range(len(gold['rows'])):
            per_call=[r for r in memories if r['call']==call]
            require([r['helper_index'] for r in per_call]==[1,2,3,4,11] and
                all(r['required'] for r in per_call),
                'Missing/duplicate per-call compulsory memory owner')
        return dict(status='EVERY_NECESSARY_RETIRED_OWNER_COMPLETED',
            compulsory_memory_owners=len(memories),required_target_owners=expected_targets,
            required_alloff_target_owners=sum(target_required(spec['backend']['helpers'][f'op_{r["op"]}'][8]['insn'],r,spec) and not any(gold['masks'][r['mode']])
                for r in gold['rows']),
            elidable_target_owners=len(targets)-expected_targets,
            minimum_required_owners=len(memories)+expected_targets,
            required_op24_memory_targets=sum(r['op']==24 and target_required(spec['backend']['helpers']['op_24'][8]['insn'],r,spec) for r in gold['rows']),
            harmless_configuration_replay_arch_orders=replays,owner_ledger=owners)

def audit(path,spec,abort):
    _,_,(base,_,_,_)=common.image_context(Path(read(HERE/'reset_profile.json')['image']).parent)
    protocol=sys.modules['ara_verify.trace']
    state=Strict(spec);observer=OwnerObserver(protocol)
    with Path(path).open(newline='') as stream:
        for row in observer.rows(csv.DictReader(stream)):
            if state.rows%4096==0:require(not abort.is_set(),'Late abort during full5985 checks')
            try:state.consume(row)
            except Exception as error:
                raise ValueError(f'CSV firstcause row={state.rows} call={state.active["original_ordinal"] if state.active else None} '
                    f'cycle={row.get("cycle")} event={row.get("event")} pc={row.get("pc")} insn={row.get("insn")}: {error}') from error
    generic=observer.finish();mature.protocol_presence(generic)
    strict=state.finish();coverage=observer.owner_coverage(state.offloads,dict(rows=state.gold,masks=[state.gold[i]['mask'] for i in (0,3,6)]))
    require((strict['rows'],strict['retired'],strict['last_cycle'])==(generic['rows'],generic['retire_count'],generic['last_cycle']),
        'Generic/strict full trace counts differ')
    op24=sum(x['op']==24 and x['vstart']<x['vl'] for x in state.gold)
    require(coverage['compulsory_memory_owners']==len(state.gold)*5 and
        coverage['required_target_owners']==owner_counts()['required_target_owners'],
        'All actual-model helper/nonempty target owners, including op24')
    coverage['required_op24_memory_targets']=op24
    return dict(strict=strict,generic=generic,owner_coverage=coverage,actual_csv_sha256=sha(path),strict_csv_parses=1)

def artifacts(result,case,ledger,spec,abort):
    require(result.status=='PASS' and type(result.returncode)is int and result.returncode==0 and not abort.is_set(),'Actual numeric outcome')
    common.check_artifacts(result,dict(case,original_name=case['id']),ledger)
    for name in ('console.log','work/run.vcs.log'):console_gate((result.artifact_dir/name).read_text())
    return audit(result.artifact_dir/'commit_trace.csv',spec,abort)
