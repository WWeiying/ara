"""Full5985 source oracle over actual RVFI, plus lossless six-event protocol."""
from functools import lru_cache
import csv
import importlib.util
from pathlib import Path
import re
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REF=HERE.parent/'full_e64_m4_block_prepare01/reference_entry01'
SOFT=HERE.parent/'full_e64_m4_block_prepare01/software02'
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
CAP=64
SHAPE='rvv_matrix_e64_m4'
SHAPES=(SHAPE,)
ID='arithmetic_original_e64_m4_full5985_sticky'
READY_SHA='156d039c5009f31b4ae4e6928ccf57e3284f2153926522aa01b84a02dd8e8737'
ELF_SHA='7ad99ec2e99b1eab9183e82934f09f29b3322a9c82093935dea3771f6d7d1620'
VETO=re.compile(common.BAD.pattern+r'|\b(?:FAIL|FAILED|ERROR|TRAP|MISMATCH|UNSUPPORTED|ABORTED)\b',re.I)

@lru_cache(maxsize=1)
def model():
    ctx=load('immutable_e64_m4_reference_context',REF/'context.py')
    _,_,_,rows=ctx.artifacts();result=[]
    for row in rows:
        raw=b''.join(v.to_bytes(8,'little') for v in row['words'])
        result.append(dict(row,ordinal=row['ordinal']-1,vstart=row['start'],
            a=list(b''.join(v.to_bytes(8,'little') for v in row['a'])),
            b=list(b''.join(v.to_bytes(8,'little') for v in row['b'])),raw=raw))
    require(len(result)==5985,'Original full5985, no prefix')
    return result

def marker(p=None):
    return 'RVV_MATRIX_PASS sew=64 vlmax=64 cases=5985 elements=383040 errors=0 seeds=3 guard_tail_mask_vstart=checked'

@lru_cache(maxsize=1)
def specification(shape=SHAPE):
    require(shape==SHAPE and sha(REF/'READY.json')==READY_SHA,'Exact actual full5985 READY')
    linked=read(HERE/'soc_spec.json');elf=SOFT/'soc/program.elf'
    require(linked['elf_sha256']==ELF_SHA and sha(elf)==ELF_SHA,'Actual SoC ELF')
    symbols=linked['symbols'];code={int(k):v for k,v in linked['code'].items()};helpers=linked['helpers']
    for n,w in helpers.items():require(len(w)==(3 if n=='capacity' else 13) and all(code[i['pc']]==i['insn'] for i in w),'458 actual original helpers')
    startup=[pc for pc in sorted(code) if symbols['_start']<=pc<symbols['trap_entry'] and is_csr(code[pc])]
    require([code[p] for p in startup]==[0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073],'Actual five bootstrap CSRs')
    init=[[pc,code[pc],8,8*i] for i,pc in enumerate(linked['output_stores'])]
    reads={str(e['word']*8):e['pc'] for e in linked['comparator']['loads'] if e['kind']=='actual'}
    require(len(init)==len(reads)==66,'Full66 initializer and actual reads')
    bss,=[p for p in code if p<symbols['trap_entry'] and code[p]==0x0002b023]
    exit_pc,=[p for p in code if symbols['replay_exit']<=p<symbols['replay_write'] and code[p]==0x00a2b023]
    require(code[exit_pc+4]==0xa001 and 'tohost' not in symbols and 'replay_log' not in symbols,'Actual CTRL, not HTIF')
    backend=dict(elf=str(elf),sha256=ELF_SHA,code=linked['code'],symbols=symbols,helpers=helpers)
    return dict(config=dict(id=SHAPE,sew=64,lmul='m4',cap=64,calls=5985),backend=backend,
        csr_prelude=startup,bss_store=bss,exit_store=exit_pc,park=exit_pc+4,uart=0xc0000000,ctrl=0xd0000000,
        failure_pcs=linked['failure_pcs'],body_start=symbols['arithmetic_main'],body_end=symbols['capacity'],
        init_stores=init,output_reads=reads,source_lifecycle=linked)

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


source_lifecycle=load('e64_m4_soc_source_lifecycle',HERE/'worker_lifecycle.py')
@lru_cache(maxsize=1)
def source_rows():
    return load('immutable_e64_m4_source_rows_for_lifecycle',REF/'context.py').artifacts()[3]


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
        self.life=source_lifecycle.Lifecycle(self.s,self.code,[self.helpers[f'op_{i}'][0]['pc'] for i in range(35)],source_rows())

    def value(self,address,size):
        require(all(address+i in self.memory for i in range(size)),'Missing actual initialized byte')
        return sum(self.memory[address+i]<<(8*i) for i in range(size))

    def finish_call(self):
        if self.active:
            require(self.helper is None and self.active['reads']==set(range(66)) and self.active['returned_vstart']==0,
                'Missing full66word/guard/status read coverage')

    def begin_call(self,name):
        self.finish_call();ordinal=len(self.calls);require(ordinal<5985,'Extra original call')
        g=self.gold[ordinal];require(name==f'op_{g["op"]}','Original helper/seed/length/mask/start order')
        require([self.regs.get(r) for r in range(10,17)]==[self.s['a'],self.s['b'],self.s['out']+8,g['vl'],64,self.s['mask'],g['vstart']],
            'Actual full source arguments')
        previous=self.gold[ordinal-1] if ordinal else None
        seed_first=previous is None or previous['seed']!=g['seed']
        group_first=previous is None or any(previous[k]!=g[k] for k in ('seed','op','li','mode'))
        for name,values in (('a',g['a']),('b',g['b']),('mask',g['mask']),('out',list((91).to_bytes(8,'little')*66))):
            require([self.value(self.s[name]+i,1) for i in range(len(values))]==values,'Actual source initialized values '+name)
            if name=='out' or name=='mask' and group_first or name in ('a','b') and (seed_first or g['op']>=25):
                require(self.fresh[name]==set(range(len(values))),'Deleted fresh source initialization '+name)
                self.fresh[name]=set()
        # Lifecycle rejects any later write outside the owned source footprints;
        # exact helper arguments bound vector accesses to those same footprints.
        if ordinal==0:
            for name in ('a','b'):
                require(all(self.value(self.s[name]+i,1)==0 for i in range(512,8192)),
                    'Unused physical input backing must begin BSS zero '+name)
            require(all(self.value(self.s['out']+i,1)==0 for i in range(528,8208)),
                'Unused physical output backing must begin BSS zero')
        require(not any(g['mask'][8:]),'Original physical predicate upper120 zero')
        require(self.init_index==66,'Every-call exact528 initializer store ledger');self.init_index=0
        require(self.value(self.s['checks'],8)==ordinal and self.value(self.s['elements'],8)==ordinal*64 and self.value(self.s['errors'],8)==0,
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
        self.life.enter(pc,self.regs)
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
            if name=='capacity' and j==1:require((rd,result)==(10,64),'Actual VLMAX256')
            if name!='capacity':
                g=self.gold[self.active['ordinal']]
                if j in (0,5,10):require((rd,result)==(5,g['vl'] if j==5 else 64),'Original vset VL')
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
                elif site[1]==8:
                    kind='target';required=target_required(insn,self.gold[call])
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
                elif addr<self.s['out']+8208 and addr+size>self.s['out']:
                    require(self.body_entered and self.spec['body_start']<=pc<self.spec['body_end'] and self.init_index<66,
                        'Output write owner/extra init')
                    index=self.init_index;want=self.spec['init_stores'][index]
                    require((pc,insn,size)==tuple(want[:3]) and addr==self.s['out']+want[3] and
                        size==8 and wd==0x5b,'Exact528 u64 0x5b initializer PC/order/data')
                    self.init_index+=1
                self.life.store(pc,insn,addr,size,wd)
                for i in range(size):self.memory[addr+i]=(wd>>(8*i))&255
                if self.body_entered:
                    for name,length in (('a',512),('b',512),('mask',128),('out',528)):
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
                self.life.read(pc,addr,size,result & ((1<<(8*size))-1))
                if self.s['out']<=addr<self.s['out']+528:
                    require(self.active is not None and self.helper is None,'Output oracle phase')
                    offset=addr-self.s['out'];chunk=offset//8
                    require(offset%8==0 and size==8 and self.spec['output_reads'].get(str(offset))==pc and chunk not in self.active['reads'],
                        'Full66word u64 oracle read/drop/duplicate')
                    raw=self.gold[self.active['ordinal']]['raw'];expected=int.from_bytes(raw[offset:offset+size],'little')
                    if result!=loaded_value(expected,size,desc['signed']):
                        delta=(result^expected)&((1<<(8*size))-1);byte=next((i for i in range(size) if (delta>>(8*i))&255),0)
                        position=offset+byte;g=self.gold[self.active['ordinal']]
                        category='guard' if position//8 in (0,65) else 'tail' if position//8-1>=g['vl'] else 'prestart' if position//8-1<g['vstart'] else 'result'
                        raise ValueError(f'call={self.active["original_ordinal"]} {category} byte={position} element={position//8-1} cycle={cycle} pc={pc:08x} insn={insn:08x} '
                            f'expected=0x{expected:x} actual=0x{result:x}')
                    self.active['reads'].add(chunk)
        elif not is_vector(insn):require(rm==wm==0,'Unclassified scalar memory effect')
        self.life.effect(pc,(rd,result) if rd else None)
        if rd and insn&127 not in (7,0x53,0x43,0x47,0x4b,0x4f):self.regs[rd]=result
        self.regs[0]=0
        self.life.leave(pc,self.regs)

    def finish(self):
        self.finish_call();self.life.finish()
        require(self.exited and self.capacity==1 and len(self.calls)==5985 and self.counts==[5985]*13 and self.csr_count==5,
            'Complete full5985 original ledger')
        require(self.value(self.s['checks'],8)==5985 and self.value(self.s['elements'],8)==383040 and self.value(self.s['errors'],8)==0,
            'Actual final original counters')
        console_gate(self.console.decode('ascii'),simulator=False)
        return dict(status='FULL5985_ACTUAL_RVFI_ACCEPTED_NOT_LINUX',calls=5985,results=383040,guards=11970,
            returned_vstart_zero=5985,helper_instructions=77805,routine_counts=self.counts,packed_output_reads=395010,expected_dictionary_reads=self.life.expected_reads,dictionary_ID_reads=self.life.id_reads,sticky_equal_BEQ=self.life.beq_count,
            fresh_output_bytes_each_call=528,typed_sentinel='000000000000005b',tail_read_bytes=0,physical_registers_each_group=4,vtype=26,FP_calls=self.life.fp_calls,FP_input_stores=self.life.fp_stores,mask_groups=self.life.mask_groups,mask_clear_stores=self.life.mask_clear_stores,mask_bit_stores=self.life.mask_bit_stores,source_seed_stores=self.life.seed_cursor,mask_initialization='Original per-group reuse',seed_initialization='Original once per seed',
            rows=self.rows,retired=self.retired,last_cycle=self.cycle,parking=self.parking,firmware_through_ctrl=self.exit_retire,
            full_order=True,partitioned=False,fflags_oracle='Original source has no explicit fflags oracle; history not reset',
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
            if state.rows%4096==0:require(not abort.is_set(),'Late abort during full5985 checks')
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

def artifacts(result,case,ledger,spec,abort):
    require(result.status=='PASS' and type(result.returncode)is int and result.returncode==0 and not abort.is_set(),'Actual numeric outcome')
    common.check_artifacts(result,dict(case,original_name=case['id']),ledger)
    for name in ('console.log','work/run.vcs.log'):console_gate((result.artifact_dir/name).read_text())
    return audit(result.artifact_dir/'commit_trace.csv',spec,abort)
