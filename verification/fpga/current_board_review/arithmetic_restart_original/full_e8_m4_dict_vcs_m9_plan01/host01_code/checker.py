"""Full4095 source oracle over actual RVFI, plus lossless six-event protocol."""
from functools import lru_cache
import csv
import importlib.util
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REF=HERE.parent/'full_e8_m4_dict_prepare01'
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
SHAPE='rvv_matrix_e8_m4'
SHAPES=(SHAPE,)
ID='arithmetic_original_e8_m4_full4095_dict'
READY_SHA='d6e07cf6c0a4a3a193feaab29025987007ae2f22a645248d6aaa4bd9c8018555'
ELF_SHA='154def073e4bc0282b6b72103314dec2b3d6f4229ff3564228400fa4c89ecc14'
VETO=re.compile(common.BAD.pattern+r'|\b(?:FAIL|FAILED|ERROR|TRAP|MISMATCH|UNSUPPORTED|ABORTED)\b',re.I)

@lru_cache(maxsize=1)
def model():
    original=load('full4095_sealed_source_model',REF/'model.py')
    seeds,rows,dictionary,masks=original.generate()
    result=[]
    for row in rows:
        raw=b''.join(dictionary[ix].to_bytes(8,'little') for ix in row['indices'])[:514]
        result.append(dict(row,ordinal=row['ordinal']-1,vstart=row['start'],a=seeds[row['seed']]['a'],
            b=seeds[row['seed']]['b'],mask=list(masks[row['mode']]),expected=list(raw[1:513]),raw=raw))
    require(len(result)==4095,'Original full sequence')
    return result

def marker(p=None):
    return 'RVV_MATRIX_PASS sew=8 vlmax=512 cases=4095 elements=2096640 errors=0 seeds=3 guard_tail_mask_vstart=checked'

@lru_cache(maxsize=1)
def specification(shape=SHAPE):
    require(shape==SHAPE and sha(REF/'READY.json')==READY_SHA,'Actual full4095 READY identity')
    proof=read(REF/'proof.json');backend=dict(proof['backends']['soc'])
    require(backend['sha256']==ELF_SHA and sha(backend['elf'])==ELF_SHA,'Actual sealed SoC ELF')
    require(proof['full_order_calls']==4095 and proof['original_fallback_verbatim'],'Source order/fallback')
    dis=(REF/'soc/program.dis').read_text()
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',dis,re.M)}
    symbols=read(REF/'soc/symbols.json')
    helpers=backend['helpers'];hp={x['pc'] for window in helpers.values() for x in window}
    for name,window in helpers.items():
        require(len(window)==(3 if name=='capacity' else 13) and all(code[x['pc']]==x['insn'] for x in window),'Original actual helper bytes')
    startup=[pc for pc in sorted(code) if symbols['_start']<=pc<symbols['trap_entry'] and is_csr(code[pc])]
    require([code[pc] for pc in startup]==[0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073],
        'Actual five startup CSRs, no invented vlenb')
    require(not [pc for pc,i in code.items() if is_csr(i) and pc not in hp and pc not in startup and pc<symbols['trap_entry']],
        'Unexpected startup CSR')
    functions={name:int(address,16) for address,name in re.findall(r'^([0-9a-f]+) <([^>]+)>:',dis,re.M)}
    start=symbols['arithmetic_main'];end=min(v for v in functions.values() if v>start)
    init=[(0x80000508,0xe380,8),(0x8000050a,0xe780,8),(0x8000050c,0xeb80,8),
        (0x8000050e,0xef80,8),(0x8000051e,0x20f71023,2)]
    require(all(code.get(pc)==insn for pc,insn,_ in init),'Exact SoC initializer SD/SH sites')
    bss,=[pc for pc in code if pc<symbols['trap_entry'] and code[pc]==0x0002b023]
    exit_pc,=[pc for pc in code if symbols['replay_exit']<=pc<symbols['number'] and code[pc]==0x00a2b023]
    require(code[exit_pc+4]==0xa001 and 'tohost' not in symbols and 'replay_log' not in symbols,'Actual CTRL0, not HTIF')
    failures=[v for k,v in symbols.items() if k=='failure' or k.startswith('failure.')]
    require(failures,'Real failure.part PC must be forbidden')
    backend.update(code={str(pc):i for pc,i in code.items()},symbols=symbols)
    return dict(config=dict(id=SHAPE,sew=8,lmul='m4',cap=512,calls=4095),backend=backend,
        csr_prelude=startup,bss_store=bss,exit_store=exit_pc,park=exit_pc+4,ctrl=0xd0000000,uart=0xc0000000,
        body_start=start,body_end=end,init_stores=init,failure_pcs=failures)

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

    def value(self,address,size):
        require(all(address+i in self.memory for i in range(size)),'Missing actual initialized byte')
        return sum(self.memory[address+i]<<(8*i) for i in range(size))

    def finish_call(self):
        if self.active:
            require(self.helper is None and self.active['reads']==set(range(65)) and self.active['returned_vstart']==0,
                'Missing full64word/tail2/guard/status read coverage')

    def begin_call(self,name):
        self.finish_call();ordinal=len(self.calls);require(ordinal<4095,'Extra original call')
        g=self.gold[ordinal];require(name==f'op_{g["op"]}','Original helper/seed/length/mask/start order')
        require([self.regs.get(r) for r in range(10,17)]==[self.s['a'],self.s['b'],self.s['out']+1,g['vl'],512,self.s['mask'],g['vstart']],
            'Actual full source arguments')
        previous=self.gold[ordinal-1] if ordinal else None
        seed_first=previous is None or previous['seed']!=g['seed']
        group_first=previous is None or any(previous[k]!=g[k] for k in ('seed','op','li','mode'))
        for name,values in (('a',g['a']),('b',g['b']),('mask',g['mask']),('out',[91]*514)):
            require([self.value(self.s[name]+i,1) for i in range(len(values))]==values,'Actual source initialized values '+name)
            if name=='out' or name=='mask' and group_first or name in ('a','b') and seed_first:
                require(self.fresh[name]==set(range(len(values))),'Deleted fresh source initialization '+name)
                self.fresh[name]=set()
        require(self.init_index==65,'Every-call exact514 initializer store ledger');self.init_index=0
        require(self.value(self.s['checks'],8)==ordinal and self.value(self.s['elements'],8)==ordinal*512 and self.value(self.s['errors'],8)==0,
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
        site=self.lookup.get(pc)
        if site:
            name,j=site
            if j==0:
                require(self.helper is None and self.body_entered and self.csr_count==5,'Helper phase/overlap')
                if name=='capacity':require(not self.calls and self.capacity==0,'Capacity repeated');self.capacity=1
                else:require(self.capacity==1,'Capacity missing');self.begin_call(name)
                self.helper=name;self.index=0
            require(self.helper==name and self.index==j,'Exact contiguous original helper window')
            if name=='capacity' and j==1:require((rd,result)==(10,512),'Actual VLMAX512')
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
                elif site[1]==8:kind='target';required=self.gold[call]['vstart']<self.gold[call]['vl']
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
                elif addr<self.s['out']+1026 and addr+size>self.s['out']:
                    require(self.body_entered and self.spec['body_start']<=pc<self.spec['body_end'] and self.init_index<65,
                        'Output write owner/extra init')
                    index=self.init_index;want=self.spec['init_stores'][index%4 if index<64 else 4]
                    require((pc,insn,size)==tuple(want) and addr==self.s['out']+index*8 and
                        wd==(0x5b5b if index==64 else 0x5b5b5b5b5b5b5b5b),'Exact514 initializer PC/order/data')
                    self.init_index+=1
                for i in range(size):self.memory[addr+i]=(wd>>(8*i))&255
                if self.body_entered and self.spec['body_start']<=pc<self.spec['body_end']:
                    for name,length in (('a',512),('b',512),('mask',128),('out',514)):
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
                if self.s['out']<=addr<self.s['out']+514:
                    require(self.active is not None and self.helper is None,'Output oracle phase')
                    offset=addr-self.s['out'];chunk=offset//8
                    require(offset%8==0 and size==(2 if offset==512 else 8) and chunk not in self.active['reads'],
                        'Full64word+exact tail2 oracle read/drop/duplicate')
                    raw=self.gold[self.active['ordinal']]['raw'];expected=int.from_bytes(raw[offset:offset+size],'little')
                    if result!=loaded_value(expected,size,desc['signed']):
                        delta=(result^expected)&((1<<(8*size))-1);byte=next((i for i in range(size) if (delta>>(8*i))&255),0)
                        position=offset+byte;g=self.gold[self.active['ordinal']]
                        category='guard' if position in (0,513) else 'tail' if position-1>=g['vl'] else 'prestart' if position-1<g['vstart'] else 'result'
                        raise ValueError(f'call={self.active["original_ordinal"]} {category} byte={position} pc={pc:08x} insn={insn:08x} '
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
        console_gate(self.console.decode('ascii'),simulator=False)
        return dict(status='FULL4095_ACTUAL_RVFI_ACCEPTED_NOT_LINUX',calls=4095,results=2096640,guards=8190,
            returned_vstart_zero=4095,helper_instructions=53235,routine_counts=self.counts,packed_output_reads=266175,
            fresh_output_bytes_each_call=514,mask_initialization='Original per-group reuse',seed_initialization='Original once per seed',
            rows=self.rows,retired=self.retired,last_cycle=self.cycle,parking=self.parking,firmware_through_ctrl=self.exit_retire,
            full_order=True,partitioned=False,fflags_oracle='Original integer source has no explicit fflags oracle',
            call_ledger=[dict(call,reads=sorted(call['reads'])) for call in self.calls])

OwnerObserver=mature.OwnerObserver

def audit(path,spec,abort):
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
    generic=observer.finish();mature.protocol_presence(generic)
    strict=state.finish();coverage=observer.owner_coverage(state.offloads,dict(rows=state.gold,masks=[state.gold[i]['mask'] for i in (0,3,6)]))
    require((strict['rows'],strict['retired'],strict['last_cycle'])==(generic['rows'],generic['retire_count'],generic['last_cycle']),
        'Generic/strict full trace counts differ')
    op24=sum(x['op']==24 and x['vstart']<x['vl'] for x in state.gold)
    require(op24==117 and coverage['compulsory_memory_owners']==20475,'All required helper and117 target memory owners')
    coverage['required_op24_memory_targets']=op24
    return dict(strict=strict,generic=generic,owner_coverage=coverage,actual_csv_sha256=sha(path),strict_csv_parses=1)

def artifacts(result,case,ledger,spec,abort):
    require(result.status=='PASS' and type(result.returncode)is int and result.returncode==0 and not abort.is_set(),'Actual numeric outcome')
    common.check_artifacts(result,dict(case,original_name=case['id']),ledger)
    for name in ('console.log','work/run.vcs.log'):console_gate((result.artifact_dir/name).read_text())
    return audit(result.artifact_dir/'commit_trace.csv',spec,abort)
