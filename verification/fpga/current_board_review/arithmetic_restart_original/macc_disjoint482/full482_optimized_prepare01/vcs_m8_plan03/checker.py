"""Actual RVFI memory, original13 and complete natural482; no inferred stores."""
from collections import Counter
import csv
import importlib.util
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REF=HERE.parent/'work05'
G=HERE.parents[3]
sys.path.insert(0,str(G/'gather_repair05'))
import regression as common


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value)
    return value


LEGACY=G/'arithmetic_restart_original/full_small2_vcs_m6_plan01/checker.py'
legacy=module('macc482_memory_contract',LEGACY)
GENERIC=G/'fp_comparison_original/fp_alias50_terminal_eventcheck01/observer.py'
transport=module('macc482_protocol_transport',GENERIC)
PROFILE_SOURCE=G/'arithmetic_restart_original/full_small2_reset_gpr_recovery01/reset_profile.json'
PROFILE_SOURCE_SHA='308784d27eaf81e2a608cd7cd37a9ac61a22a58ce9eda994715cec58dcd682a4'
PROFILE_REVIEW=G/'arithmetic_restart_original/full_small2_reset_gpr_entry_review01/REVIEW.md'
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/campaign/image')
ID='macc_disjoint_e8_m4_prefix482_scalar64'
SOURCE='rvv_integer_macc_accumulators_restart_e8_m4'
READY_SHA='06197d69f8e3767e358b0dacdb6020147f8b1dcf7c9961fd20f5929436a0941a'
ELF_SHA='8c95b2d84da424c3456248871f8cb8c02f99862dadeaf39327dc31e6172cddda'
read,require=common.read,common.require
def sha(path):return common.sha(Path(path))
memory_op,loaded_value,is_vector,is_csr=legacy.memory_op,legacy.loaded_value,legacy.is_vector,legacy.is_csr
MASK64=(1<<64)-1
VETO=re.compile(common.BAD.pattern+r'|RVV_MATRIX_FAIL|MACC_OPT_(?:SCOPE|RNG)_FAIL|\b(?:ERROR|FATAL|FAIL|FAILED|ABORT|ABORTED|TRAP|MISMATCH|UNSUPPORTED)\b',re.I)
SUMMARY='RVV_MATRIX_PASS sew=8 vlmax=512 cases=482 elements=246784 errors=0 seeds=5 guard_tail_mask_vstart=checked'


def instructions(dis,name):
    body=dis.split('<'+name+'>:\n')[1].split('\n\n')[0]
    return [dict(pc=int(m[1],16),insn=int(m[2],16),text=m[3]) for m in
            re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)$',body,re.M)]


def specification():
    require(sha(REF/'READY.json')==READY_SHA,'Actual complete reference READY')
    program=read(REF/'soc/program.json')
    require(program['runtime_id']==ID and program['sha256']==ELF_SHA and sha(program['path'])==ELF_SHA,'Actual optimized ELF identity')
    dis=(REF/'soc/program.dis').read_text()
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+',dis,re.M)}
    symbols={name:value['address'] for name,value in program['symbols'].items()}
    routine=instructions(dis,'op_0');capacity=instructions(dis,'capacity')
    require(len(routine)==13 and routine[8]['insn']==0xb5042c57 and
            [r['insn'] for r in routine]==[int(r['insn'],16) for r in program['original13_routine']], 'Original13 helper')
    require(len(capacity)==3 and capacity[1]['insn']==0x0022f557,'Original e8/m4 capacity')
    startup=instructions(dis,'_start');main=instructions(dis,'main');body=instructions(dis,'macc_main')
    prefix=[r['pc'] for r in startup if is_csr(r['insn'])]
    require([code[pc] for pc in prefix]==[0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073], 'Exact startup CSR sequence')
    main_csr=[r['pc'] for r in main if is_csr(r['insn'])]
    body_csr=[r['pc'] for r in body if is_csr(r['insn'])]
    require(len(main_csr)==len(body_csr)==1 and all(code[pc]&~0xf80==0xc2202073 for pc in main_csr+body_csr),'Actual two vlenb sites')
    bss,=[r['pc'] for r in startup if r['insn']==0x0002b023]
    exit_rows=instructions(dis,'replay_exit')
    store,=[r for r in exit_rows if r['insn']==0x00a2b023]
    require(code[store['pc']+4]==0xa001 and 'tohost' not in symbols,'Original CTRL0 and park')
    failure=[value for name,value in symbols.items() if name=='failure' or name.startswith('failure.')]
    require(failure,'Missing original failure entry')
    return dict(elf=program['path'],sha256=ELF_SHA,code=code,symbols=symbols,routine=routine,capacity=capacity,
        startup=startup,main=main,main_pcs=[r['pc'] for r in body],startup_csrs=prefix,
        main_vlenb=main_csr[0],body_vlenb=body_csr[0],bss_store=bss,exit_store=store['pc'],park=store['pc']+4,
        failure_pcs=failure,forbidden_pcs=[r['pc'] for n in range(1,8) for r in instructions(dis,'op_'+str(n))],
        ctrl=0xd0000000,uart=0xc0000000)


def make_profile(ledger):
    require(sha(PROFILE_SOURCE)==PROFILE_SOURCE_SHA,'Reviewed reset fact source')
    old=read(PROFILE_SOURCE)
    require(old['FpgaEn']==0 and old['regfile']=='ariane_regfile_ff.sv' and old['initial_gpr_values']==[0]*32,
            'Only hardware-proven FF reset values')
    pins={str(PROFILE_SOURCE):PROFILE_SOURCE_SHA,str(PROFILE_REVIEW):sha(PROFILE_REVIEW)}
    rtl={}
    for name,digest in old['rtl_pins'].items():
        new=Path(name.replace('candidate06','candidate08'))
        require(sha(new)==digest,'M8 reset/memory/monitor implementation differs: '+str(new))
        rtl[str(new)]=digest
    return dict(schema='EXACT_M8_FROM_RESET_GPR_PROFILE_NOT_ISA_DEFAULT',image=str(IMAGE/'image.json'),
        image_sha256=sha(IMAGE/'image.json'),snapshot_sha256=ledger['snapshot_sha256'],
        compiled_manifest_sha256=ledger['manifest_sha256'],configuration_sha256=ledger['configuration_sha256'],
        FpgaEn=0,regfile=old['regfile'],initial_gpr_values=list(old['initial_gpr_values']),
        trace_origin='Complete original _start order0 after fresh frozen testbench reset',
        rtl_pins=rtl,source_profile_sha256=PROFILE_SOURCE_SHA,proof_pins=pins,
        allowed_runtime_id=ID,soc_elf_sha256=ELF_SHA)


def validate_profile(profile):
    require(profile['schema']=='EXACT_M8_FROM_RESET_GPR_PROFILE_NOT_ISA_DEFAULT' and
            profile['FpgaEn']==0 and profile['initial_gpr_values']==[0]*32 and
            profile['allowed_runtime_id']==ID and profile['soc_elf_sha256']==ELF_SHA,'Exact reset-known profile')
    require(sha(profile['image'])==profile['image_sha256'],'M8 reset image binding')
    ledger=read(profile['image'])
    require((ledger['snapshot_sha256'],ledger['manifest_sha256'],ledger['configuration_sha256'])==
            (profile['snapshot_sha256'],profile['compiled_manifest_sha256'],profile['configuration_sha256']), 'M8 profile ledger')
    common.base.verify_pins(profile['rtl_pins']);common.base.verify_pins(profile['proof_pins'])


def console_gate(text,simulator=True):
    require(not VETO.search(text),'Raw failure/abort/unsupported veto')
    for prefix,exact in [('BOARD_CASE_BEGIN','BOARD_CASE_BEGIN '+ID),('RVV_MATRIX_PASS',SUMMARY),
            ('MACC_PREFIX_PASS','MACC_PREFIX_PASS '+ID+' trials=482'),('BOARD_CASE_PASS','BOARD_CASE_PASS '+ID),
            ('BOARD_REPLAY_PASS','BOARD_REPLAY_PASS')]:
        require([s for s in text.splitlines() if s.startswith(prefix)]==[exact],'Missing/ambiguous original oracle marker '+prefix)
    if simulator:
        require(text.splitlines().count(common.SUCCESS)==1 and '$finish' in text,'Actual simulator completion missing')


class Strict:
    def __init__(self,spec,gold,profile):
        validate_profile(profile)
        require(len(gold['rows'])==482 and gold['capacity']==512,'Complete full482 model')
        self.spec,self.gold=spec,gold
        self.code={int(k):v for k,v in spec['code'].items()};self.s=spec['symbols']
        self.regs=dict(enumerate(profile['initial_gpr_values']));self.memory={}
        self.rows=self.retired=self.capacity_calls=self.csr_count=self.main_vlenb=self.body_vlenb=self.parking=0
        self.cycle=-1;self.calls=[];self.current=None;self.helper=None;self.index=0
        self.lookup={r['pc']:(name,i) for name,rows in (('capacity',spec['capacity']),('op_0',spec['routine']))
                     for i,r in enumerate(rows)}
        self.main_pcs=set(spec['main_pcs']);self.in_main=False;self.exited=False;self.ctrl=None
        self.bss_next=self.s['__bss_start'];self.console=bytearray()
        self.ranges={n:(self.s[n],512 if n in ('a','b') else 128 if n=='mask' else 514) for n in ('a','b','mask','out')}
        self.fresh={n:set() for n in self.ranges};self.fresh64={n:set() for n in self.ranges}
        self.counts=[0]*13
        self.offloads=[]

    def value(self,address,width):
        require(all(address+i in self.memory for i in range(width)),'Missing actual initialized bytes')
        return sum(self.memory[address+i]<<(8*i) for i in range(width))

    def finish_call(self):
        if self.current is not None:
            require(self.helper is None and self.current['reads']==set(range(65)) and
                    self.current['returned_vstart']==0,'Incomplete65 reads/full13/vstart')

    def begin_call(self):
        self.finish_call()
        number=len(self.calls);require(number<482,'Extra original call')
        row=self.gold['rows'][number]
        require([self.regs.get(r) for r in range(10,18)]==[self.s['a'],self.s['b'],self.s['out']+1,
            row['vl'],512,self.s['mask'],row['vstart'],0],'Actual helper arguments/order/start/rm')
        for name,values in (('a',self.gold['a']),('b',self.gold['b']),('mask',self.gold['masks'][row['mode']]),
                            ('out',[91]+row['old']+[91])):
            require(self.fresh[name]==set(range(len(values))), 'Missing fresh per-call setup '+name)
            chunks=16 if name=='mask' else 64
            require(self.fresh64[name]==set(range(0,chunks*8,8)),'Missing fresh packed setup '+name)
            require([self.value(self.s[name]+i,1) for i in range(len(values))]==values,'Actual setup payload '+name)
        require(self.value(self.s['checks'],8)==number and self.value(self.s['elements'],8)==number*512 and
                self.value(self.s['errors'],8)==0,'Actual ordinal/counter ledger')
        self.current=dict(trial=number,original_ordinal=number+1,vl=row['vl'],vstart=row['vstart'],
            accumulator=row['accumulator'],mode=row['mode'],entry_retire=self.retired,entry_cycle=self.cycle,
            fresh_setup_bytes=1666,reads=set(),returned_vstart=None)
        self.calls.append(self.current)
        self.fresh={n:set() for n in self.ranges};self.fresh64={n:set() for n in self.ranges}

    def consume(self,row):
        self.rows+=1;cycle=int(row['cycle'])
        require(cycle>=self.cycle and row['event'] in ('retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done') and
                int(row['trap'])==0,'Cycle reversal/unknown event/trap')
        self.cycle=cycle
        if row['event']!='retire':return
        require(int(row['order'])==self.retired,'Actual retire order')
        self.retired+=1;require(self.retired<=4000000,'Unexpected firmware retirement budget')
        pc,code=int(row['pc'],16),int(row['insn'],16)
        rd,result=int(row['rd']),int(row['rd_wdata'],16)
        addr,rm,wm,wd=(int(row[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        require(self.code.get(pc)==code and (self.retired!=1 or pc==self.s['_start']),'Actual ELF/startup instruction')
        require(pc not in self.spec['forbidden_pcs'],'Retired unused original helper instruction')
        if self.exited:
            require(pc==self.spec['park'] and code==0xa001 and rd==rm==wm==0,'Post-CTRL non-original parking')
            self.parking+=1;return
        require(pc!=self.s['trap_entry'] and pc not in self.spec['failure_pcs'],'Actual oracle/trap failure entry')
        if pc==self.s['main']:
            require(not self.in_main and self.bss_next==self.s['__bss_end'] and self.csr_count==5,'Incomplete BSS/startup/reentered main')
            self.in_main=True
        if pc in self.lookup:
            name,i=self.lookup[pc]
            if i==0:
                require(self.helper is None and self.in_main and self.csr_count==5 and self.main_vlenb==1,'Helper before initialized source')
                if name=='capacity':
                    require(self.capacity_calls==0 and not self.calls and self.body_vlenb==0,'Repeated/late capacity')
                    self.capacity_calls=1
                else:
                    require(self.capacity_calls==self.body_vlenb==1,'Call before capacity/RNG source vlenb')
                    self.begin_call()
                self.helper=name;self.index=0
            require(self.helper==name and self.index==i,'Original helper13 continuity')
            if name=='capacity' and i==1:
                require((rd,result)==(10,512),'Actual capacity512')
            elif name=='op_0':
                gold=self.gold['rows'][self.current['trial']]
                if i in (0,5,10):require((rd,result)==(5,gold['vl'] if i==5 else 512),'Actual vset VL')
                if i==6:require((rd,result)==(28,0),'Actual ordinary b[0]/scalar0 load')
                if i==7:require(self.regs.get(16)==gold['vstart'] and rd==0,'Actual vstart CSR operand')
                if i==8:
                    require(self.regs.get(28)==0 and self.regs.get(16)==gold['vstart'] and self.regs.get(17)==0 and rd==0,'Original target scalar/start/rm')
                    self.current.update(target_pc=pc,target_retire=self.retired,target_cycle=cycle,target_opcode=code)
                if i==9:
                    require((rd,result)==(10,0),'Actual full returned-vstart/status0')
                    self.current['returned_vstart']=0
                if i in (1,2,3,4,11,12):require(rd==0,'Unexpected integer write in vector/return helper')
                self.counts[i]+=1
            self.index+=1
            if self.index==len(self.spec['capacity'] if name=='capacity' else self.spec['routine']):
                self.helper=None;self.index=0
        else:
            require(self.helper is None,'Retirement escaped original helper window')
        if transport.transport.vector(code):
            site=self.lookup.get(pc)
            kind='configuration'
            required=False
            call=None
            if site and site[0]=='op_0':
                call=self.current['trial']
                if site[1] in (1,2,3,4,11):kind='memory';required=True
                elif site[1]==8:
                    kind='target';required=self.gold['rows'][call]['vstart']<self.gold['rows'][call]['vl']
            self.offloads.append(dict(insn=code,pc=pc,retire_order=self.retired-1,call=call,
                helper_index=site[1] if site else None,kind=kind,required=required))
        if is_vector(code):require(pc in self.lookup,'New/unselected RVV instruction')
        if is_csr(code) and pc not in self.lookup:
            if pc in self.spec['startup_csrs']:
                require(not self.in_main and pc==self.spec['startup_csrs'][self.csr_count],'Startup CSR order')
                self.csr_count+=1
            elif pc==self.spec['main_vlenb']:
                require(self.in_main and self.main_vlenb==0 and self.capacity_calls==0,'Main vlenb phase')
                require(rd==(code>>7)&31 and result==128,'Actual main vlenb128');self.main_vlenb=1
            elif pc==self.spec['body_vlenb']:
                require(self.capacity_calls==1 and self.body_vlenb==0 and not self.calls,'Original body vlenb phase')
                require(rd==(code>>7)&31 and result==128,'Actual body vlenb128');self.body_vlenb=1
            else:raise ValueError('CSR outside exact original startup/helper/source phase')
        desc=memory_op(code)
        if desc:
            size=desc['size'];require(desc['base'] in self.regs,'Unknown base GPR fail-closed')
            require(addr==(self.regs[desc['base']]+desc['offset'])&MASK64,'RVFI actual address vs decoded base')
            enable=((1<<size)-1)<<(addr%8)
            require(addr%size==0 and enable<=255,'Actual scalar alignment/enable')
            if desc['kind']=='write':
                require(desc['register'] in self.regs,'Unknown source GPR fail-closed')
                mask=(1<<(8*size))-1
                require(wm==enable and rm==0 and wd&mask==self.regs[desc['register']]&mask,'RVFI store BE/data/register')
                if pc==self.spec['bss_store']:
                    require(not self.in_main and size==8 and wd==0 and addr==self.bss_next and
                            addr+8<=self.s['__bss_end'] and self.regs.get(6)==self.s['__bss_end'],'Actual ordered BSS zero')
                    self.bss_next+=8
                for byte in range(size):self.memory[addr+byte]=(wd>>(8*byte))&255
                if pc in self.main_pcs:
                    for name,(base,length) in self.ranges.items():
                        if base<=addr<base+length:
                            require(addr+size<=base+length,'Actual initialized-range overrun')
                            self.fresh[name].update(range(addr-base,addr-base+size))
                            if size==8:self.fresh64[name].add(addr-base)
                if addr==self.spec['uart']:
                    require(self.in_main and size==1 and len(self.console)<8192,'Actual UART byte protocol')
                    self.console.append(wd&255)
                if addr==self.spec['ctrl']:
                    require(pc==self.spec['exit_store'] and size==8 and wm==255 and wd==0 and self.regs.get(10)==0,
                            'Actual original CTRL raw exit0')
                    self.finish_call();self.exited=True
                    self.ctrl=dict(pc=pc,order=self.retired-1,cycle=cycle,address=addr,data=wd)
            else:
                require(rm==enable and wm==0 and rd==desc['register'],'RVFI load BE/destination')
                if self.s['out']<=addr<self.s['out']+520:
                    require(self.current is not None and self.helper is None and size==8 and
                            (addr-self.s['out'])%8==0,'Actual complete packed oracle window')
                    chunk=(addr-self.s['out'])//8;require(chunk not in self.current['reads'],'Duplicate packed oracle read')
                    gold=self.gold['rows'][self.current['trial']]
                    data=bytes([91]+gold['output']+[91]);want=int.from_bytes(data[chunk*8:chunk*8+8],'little')
                    mask=0xffff if chunk==64 else MASK64
                    require(result&mask==want,'Actual full result/guard payload mismatch')
                    self.current['reads'].add(chunk)
                if self.helper=='op_0' and self.index==7:
                    require(addr==self.s['b'] and size==1 and result==0,'Original helper scalar b0 source')
        elif not is_vector(code):require(rm==wm==0,'Unclassified scalar memory effect')
        if rd and code&127 not in (7,39,0x53,0x43,0x47,0x4b,0x4f):self.regs[rd]=result
        self.regs[0]=0

    def finish(self):
        self.finish_call()
        require(self.exited and len(self.calls)==482 and self.counts==[482]*13 and
                self.capacity_calls==self.main_vlenb==self.body_vlenb==1 and self.csr_count==5,'Full482 control ledger missing')
        require(self.value(self.s['checks'],8)==482 and self.value(self.s['elements'],8)==246784 and
                self.value(self.s['errors'],8)==0,'Actual final counters')
        text=self.console.decode('ascii');console_gate(text,False)
        prints=re.findall(r'RVV_TRIAL seed=(\d+) vl=(\d+) mask=(\d+) vstart=(\d+) completed=(\d+)',text)
        want=[('0',str(r['vl']),'0',str(r['vstart']),str(r['trial'])) for r in self.gold['rows'] if r['mode']==r['accumulator']==0]
        require(prints==want and len(prints)==26,'Actual26 original boundary prints/order')
        return dict(status='FULL482_ACTUAL_RVFI_ACCEPTED_NOT_LINUX',calls=482,predecessors=481,
            results=246784,guards=964,packed_output_reads=31330,returned_vstart_zero=482,
            helper_instructions=6266,routine_counts=self.counts,capacity=512,vlenb=128,
            fresh_setup_bytes_each_call=1666,physical_mask_bytes=128,ignored_final_load_high_bytes=6,
            actual_ctrl=self.ctrl,rows=self.rows,retired=self.retired,last_cycle=self.cycle,parking=self.parking,
            call_ledger=[dict(c,reads=sorted(c['reads'])) for c in self.calls],console=text,
            full22400_accepted=False,original_Linux_history_closed=False)


def protocol_presence(summary):
    for key in ('cvx_request_count','cvx_response_count','architecture_request_count','backend_uop_alloc_count','backend_uop_done_count'):
        require(type(summary[key]) is int and summary[key]>0,'Expected event family absent: '+key)


class OwnerObserver(transport.Observer):
    def __init__(self,protocol):
        super().__init__(protocol)
        self.owner_alloc=Counter();self.owner_done=Counter()

    def observe(self,row):
        super().observe(row)
        if row['event']=='uop_alloc':self.owner_alloc[int(row['order'])]+=1
        elif row['event']=='uop_done':self.owner_done[int(row['order'])]+=1

    def owner_coverage(self,ledger,gold):
        require([r['insn'] for r in ledger]==self.retvec,'Actual retired offload ledger differs')
        index=0;owners=[];replays=[]
        for order,insn in enumerate(self.arch):
            if index<len(ledger) and insn==ledger[index]['insn']:
                item=dict(ledger[index],arch_order=order,
                    alloc=self.owner_alloc[order],done=self.owner_done[order])
                require(item['alloc']==item['done'],'Owner alloc/done mismatch')
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
        expected_targets=sum(r['vstart']<r['vl'] for r in gold['rows'])
        require(len(memories)==len(gold['rows'])*5 and len(targets)==len(gold['rows']) and
                sum(r['required'] for r in targets)==expected_targets,'Natural helper owner scope differs')
        for call in range(len(gold['rows'])):
            require([r['helper_index'] for r in memories if r['call']==call]==[1,2,3,4,11],
                'Missing/duplicate per-call compulsory memory owner')
        return dict(status='EVERY_NECESSARY_RETIRED_OWNER_COMPLETED',
            compulsory_memory_owners=len(memories),required_target_owners=expected_targets,
            required_alloff_target_owners=sum(r['vstart']<r['vl'] and not any(gold['masks'][r['mode']])
                for r in gold['rows']),
            elidable_target_owners=len(targets)-expected_targets,
            minimum_required_owners=len(memories)+expected_targets,
            harmless_configuration_replay_arch_orders=replays,owner_ledger=owners)


def audit(path,spec,profile,protocol,abort):
    state=Strict(spec,read(REF/'model.json'),profile)
    observer=OwnerObserver(protocol)
    with Path(path).open(newline='') as stream:
        for row in observer.rows(csv.DictReader(stream)):
            if state.rows%4096==0:require(not abort.is_set(),'Cancelled full482 postcheck')
            state.consume(row)
    generic=observer.finish();protocol_presence(generic)
    strict=state.finish()
    coverage=observer.owner_coverage(state.offloads,state.gold)
    require((strict['rows'],strict['retired'],strict['last_cycle'])==
            (generic['rows'],generic['retire_count'],generic['last_cycle']),'Combined observer counts differ')
    return dict(strict=strict,generic=generic,owner_coverage=coverage,actual_csv_sha256=sha(path),strict_csv_parses=1)


def artifacts(result,case,ledger,spec,profile,protocol,abort):
    require(result.status=='PASS' and type(result.returncode) is int and result.returncode==0 and not abort.is_set(),'Actual case outcome not accepted')
    common.check_artifacts(result,dict(case,original_name=ID),ledger)
    for name in ('console.log','work/run.vcs.log'):console_gate((result.artifact_dir/name).read_text())
    return audit(result.artifact_dir/'commit_trace.csv',spec,profile,protocol,abort)
