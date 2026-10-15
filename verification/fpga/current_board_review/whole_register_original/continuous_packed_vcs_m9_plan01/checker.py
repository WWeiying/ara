"""Full continuous1134 SoC RVFI: fresh scalar setup, all bytes, original helpers/owners."""
import importlib.util
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
G=HERE.parents[1]
REF=HERE.parent/'continuous_packed_prepare01/corrected02'
sys.path.insert(0,str(G/'gather_repair05'))
import regression as common
read,require=common.read,common.require
def sha(p):return common.sha(Path(p))
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s)
    sys.modules[name]=m;s.loader.exec_module(m);return m
sys.path.insert(0,str(G.parents[1]/'coverage'))
from scoped_rv64c_memory import decode as compressed_memory
coverage=load('whole_frozen_coverage',REF/'coverage_gate.py')
cache=load('whole_frozen_completion',REF/'completion_cache.py')
# Byte-identical pure functions; no reference driver or generic module-name imports.
reference=load('whole_pure_semantics',HERE/'helper_semantics.py')
MASK64=(1<<64)-1
READY_SHA='a6423a31855de08ad5010d3209e7b7dacf07a1e0c7752c9265c123971e79ff68'
BOUND_SHA='d8f8d364c77680bcc5d6b2573df6347bbd769a2064487359eb19f0b6d1b67000'
ELF_SHA='514142ed332ef213be7a2ffff88069a86ddd758ce7d6019ff11228393e1e75ca'
SHAPE='whole_all';SHAPES=(SHAPE,)
EXPECTED_TEXT='RVV_WHOLE_PASS cases=1134 skips=366 errors=0\nBOARD_CASE_PASS whole_all\nBOARD_REPLAY_PASS\n'
VETO=re.compile(common.BAD.pattern+r'|RVV_WHOLE_(?:BYTE|DETAIL|FAIL|CAPACITY_FAIL)|\b(?:FAIL|FAILED|TRAP|MISMATCH|UNSUPPORTED|ABORTED)\b',re.I)
is_vector=lambda ins: ins&127==0x57 or ins&127 in (7,39) and (ins>>12)&7 in (0,5,6,7)
is_csr=lambda ins:ins&127==0x73 and (ins>>12)&7!=0
def memory_op(ins):
    d=reference.descriptor(ins)
    return dict(d,signed=d['kind']=='read' and (d['size']==4 if ins&3!=3 else (ins>>12)&7<4)) if d else None
def specification(shape=SHAPE):
    require(shape==SHAPE and sha(REF/'RESULT.json')==READY_SHA,'Frozen reference identity')
    proof=read(REF/'sourceproof.json');s=proof['backends']['soc'];symbols=s['symbols'];code={int(k):v for k,v in s['code'].items()}
    require(s['sha256']==ELF_SHA and sha(s['elf'])==ELF_SHA,'Actual SoC ELF')
    helper_pcs={x['pc'] for w in s['helpers'].values() for x in w}
    csr=[pc for pc,i in code.items() if is_csr(i) and pc not in helper_pcs and
         (pc<symbols['trap_entry'] or symbols['whole_original_main']<=pc<symbols['op_0'] or
          symbols['main']<=pc<symbols['replay_text'])]
    startup=[pc for pc in csr if pc<symbols['trap_entry']]
    require([code[pc] for pc in startup]==[0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073],'Original startup CSRs')
    capacities=[pc for pc in csr if code[pc]>>20==0xc22]
    require(len(csr)==7 and len(capacities)==2,'Exact original vlenb/main CSR scope')
    exit_store,=[pc for pc,i in code.items() if symbols['replay_exit']<=pc<symbols['main'] and i==0x00a2b023]
    bss_store,=[pc for pc,i in code.items() if pc<symbols['trap_entry'] and i==0x0002b023]
    require(code[exit_store+4]==0xa001 and 'tohost' not in symbols,'Actual CTRL/park not Spike')
    targets={int(op):next(w[i-1]['pc'] for i,x in enumerate(w) if x['insn']==0x00802573) for op,w in s['helpers'].items()}
    return dict(backend=s,csr_prelude=startup,capacity_pcs=capacities,exit_store=exit_store,park=exit_store+4,
                bss_store=bss_store,ctrl=0xd0000000,uart=0xc0000000,targets=targets,
                config=dict(id=SHAPE,calls=1134,skips=366))
def validate_reset(spec):
    p=read(HERE/'reset_profile.json')
    authority=G/'arithmetic_restart_original/full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json'
    require(sha(authority)==p['authority_sha256'],'Reviewed M9 profile identity')
    old=read(authority)
    require(p['rtl_pins']==old['rtl_pins'] and p['FpgaEn']==old['FpgaEn']==0 and
            p['initial_gpr_values']==old['initial_gpr_values']==[0]*32,'Exact FF reset/encoder profile')
    require(p['allowed_shape']==SHAPE and p['original_soc_elf_sha256']==spec['backend']['sha256']==ELF_SHA
            and p['reference_bound_sha256']==BOUND_SHA,'Whole-only profile scope')
    for path,digest in p['rtl_pins'].items():require(sha(path)==digest,'Actual compiled reset RTL')
    image=read(p['image'])
    for key in ('snapshot_sha256','configuration_sha256'):
        require(image[key]==p[key]==old[key],'Actual compiled config/snapshot')
    require(image['manifest_sha256']==p['compiled_manifest_sha256']==old['compiled_manifest_sha256']
            and sha(p['image'])==p['image_sha256']==old['image_sha256'],'M9 actual image')
    return dict(enumerate(p['initial_gpr_values']))

class Owners:
    def __init__(self,spec,gold):
        s=spec['backend'];self.expected=[]
        for ordinal,c in enumerate(gold):
            window=s['helpers'][str(c['op'])];target=spec['targets'][c['op']]
            payload=[x for x in window if x['insn']&127 in (7,39) or x['pc']==target]
            require(len(payload)==4,'Original whole payload windows')
            for i,x in enumerate(payload):
                self.expected.append(dict(pc=x['pc'],insn=x['insn'],call=ordinal,target=i==2,
                    required=i!=2 or c['start']<c['evl'],effective_vl=c['evl'] if i==2 else c['registers']*128 if i==3 else 1024))
        require(len(self.expected)==4536 and sum(x['required'] for x in self.expected)==4266,'Original whole required owners')
        self.instructions={x['insn'] for x in self.expected};self.arch={};self.live={}
        self.payload_arch=[];self.payload_cvx=[];self.retired=[];self.allocs=self.dones=0
    def consume(self,row):
        event=row['event'];ins=int(row['insn'],16)
        if event=='cvx_req' and ins in self.instructions:
            self.payload_cvx.append((ins,int(row['trans_id'])))
        elif event=='arch_start':
            seq=int(row['order']);require(seq not in self.arch,'Repeated architecture owner')
            self.arch[seq]=dict(insn=ins,trans=int(row['trans_id']),allocs=0,dones=0)
            if ins in self.instructions:self.payload_arch.append(seq)
        elif event=='uop_alloc':
            seq,vid=int(row['order']),int(row['port'])
            require(seq in self.arch and vid not in self.live,'Unowned/reused backend allocation')
            a=self.arch[seq];require((a['insn'],a['trans'])==(ins,int(row['trans_id'])),'Backend owner metadata')
            self.live[vid]=(seq,ins,int(row['trans_id']));a['allocs']+=1;self.allocs+=1
        elif event=='uop_done':
            seq,vid=int(row['order']),int(row['port'])
            require(self.live.get(vid)==(seq,ins,int(row['trans_id'])),'Backend completion owner identity')
            del self.live[vid];self.arch[seq]['dones']+=1;self.dones+=1
        elif event=='retire' and ins in self.instructions:
            require(len(self.retired)<len(self.expected),'Extra payload retirement')
            e=self.expected[len(self.retired)]
            require((int(row['pc'],16),ins)==(e['pc'],e['insn']),'Whole payload PC/order')
            self.retired.append(e)
    def finish(self):
        require(not self.live and self.allocs==self.dones and self.allocs>0,'Full paired owner completion')
        require(len(self.retired)==len(self.payload_arch)==len(self.payload_cvx)==4536,'Full payload CVX/architecture/retirement')
        for e,seq,request in zip(self.retired,self.payload_arch,self.payload_cvx):
            a=self.arch[seq];require(a['insn']==e['insn'] and a['allocs']==a['dones'],'Owner sequence mismatch')
            require((a['insn'],a['trans'])==request,'Architectural owner/CVX transaction identity')
            require(not e['required'] or a['allocs']>0,'Missing required owner call='+str(e['call'])+' pc='+hex(e['pc']))
        return dict(payload_requests=4536,required_staging_readback=3402,required_nonempty_targets=864,
                    allowed_empty_targets=270,required_owners=4266,all_uop_allocs=self.allocs,
                    all_uop_dones=self.dones,live_at_end=0)

class Strict:
    def __init__(self,spec,gold=None):
        self.spec=spec;self.gold=read(REF/'tuples.json')['cases'] if gold is None else gold
        self.s=spec['backend']['symbols'];self.code={int(k):v for k,v in spec['backend']['code'].items()}
        self.lookup={x['pc']:int(op) for op,w in spec['backend']['helpers'].items() for x in w}
        self.entries={self.s['op_'+str(op)]:op for op in range(20)}
        self.regs=validate_reset(spec);self.memory={};self.calls=[];self.active=None;self.helper=None;self.nextpc=None
        self.completion=cache.CompletionCache();self.setup=coverage.SetupLedger(self.s['input'],self.s['output'])
        self.owners=Owners(spec,self.gold)
        self.rows=self.retired=self.capacity=self.csr_count=self.parking=self.helper_instructions=0
        self.cycle=-1;self.bss_next=self.s['__bss_start'];self.main_entered=self.armed=self.exited=False
        self.console=bytearray();self.numbers=[];self.exit_retire=None
    def value(self,address,size):
        require(all(address+j in self.memory for j in range(size)),'Missing actual initialized byte')
        return sum(self.memory[address+j]<<(8*j) for j in range(size))
    def finish_call(self):self.completion.finish(self.active)
    def consume(self,row):
        self.rows+=1
        try:self._consume(row)
        except Exception as e:
            raise ValueError('first row='+str(self.rows)+' cycle='+row.get('cycle','')+' event='+row.get('event','')+
                ' pc='+row.get('pc','')+' call='+str(len(self.calls)-1)+': '+str(e)) from e
    def _consume(self,row):
        self.owners.consume(row)
        cycle=int(row['cycle']);require(cycle>=self.cycle and int(row['trap'])==0,'Cycle reversal/trap');self.cycle=cycle
        if row['event']!='retire':return
        require(int(row['order'])==self.retired,'Retirement order');self.retired+=1
        pc,ins=int(row['pc'],16),int(row['insn'],16);rd,value=int(row['rd']),int(row['rd_wdata'],16)
        addr,rm,wm,data=(int(row[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        require(self.code.get(pc)==ins,'Actual SoC PC/code')
        require(self.retired!=1 or pc==self.s['_start'],'Original start/reset ABI')
        if self.exited:
            require(pc==self.spec['park'] and ins==0xa001 and rd==rm==wm==0,'Actual original park')
            self.parking+=1;return
        require(pc not in (self.s['trap_entry'],self.s['replay_trap']),'Trap/failure entry')
        if pc==self.s['main']:
            require(not self.main_entered and self.bss_next==self.s['__bss_end'],'BSS/main identity')
            self.main_entered=True
        if pc==self.s['whole_original_main']:
            require(self.main_entered and not self.armed,'Original main identity');self.armed=True
        if pc in self.entries:
            self.finish_call();require(self.helper is None and len(self.calls)<1134 and self.capacity==2
                and self.csr_count==5 and self.armed,'Helper order/ABI phase')
            self.setup.enter();c=self.gold[len(self.calls)];require(self.entries[pc]==c['op'],'Original full ordering')
            require([self.regs.get(r) for r in range(10,14)]==
                    [self.s['input'],self.s['output']+32,c['start'],c['mode']],'Original whole arguments')
            require([self.value(self.s['input']+i,1) for i in range(1024)]==
                    [(i*37+c['seed']*71+3)&255 for i in range(1024)],'All actual input bytes')
            require(all(self.value(self.s['output']+i,1)==91 for i in range(1088)),'All sentinel bytes')
            self.active=dict(ordinal=len(self.calls),tuple=c,reads=set(),returned=False,csrs=[],preloads=0,stores=0,entry_step=self.retired)
            self.calls.append(self.active);self.helper=c['op'];self.nextpc=pc
        if self.helper is not None:
            require(pc==self.nextpc and self.lookup.get(pc)==self.helper,'Actual helper branch/window')
            self.nextpc=reference.next_helper_pc(pc,ins,self.regs);self.helper_instructions+=1;c=self.active['tuple']
            if pc in (self.s['op_'+str(self.helper)]+4,self.s['op_'+str(self.helper)]+8):self.active['preloads']+=1
            if pc==self.spec['targets'][self.helper]:
                require(self.active['preloads']==2 and self.active['csrs']==[c['start']],'Target before original setup')
                self.active.update(target_pc=pc,target_step=self.retired)
            if is_csr(ins) and ins>>20==8 and (ins>>12)&7==2:
                expected=c['start'] if not self.active['csrs'] else 0
                require(rd in (28,10) and value==expected and len(self.active['csrs'])<2,'Actual vstart')
                self.active['csrs'].append(value)
            if ins&127==39:
                require(self.active['csrs']==[c['start'],0] and self.regs.get((ins>>15)&31)==self.s['output']+32,'Whole output store')
                self.active['stores']+=1
            if ins==0x8082:
                require(self.regs.get(10)==c['start']<<32 and self.active['stores']==1,'Returned whole status')
                self.active['returned']=True;self.helper=None
        else:require(pc not in self.lookup,'Interior helper entry')
        if is_vector(ins):require(pc in self.lookup,'Extra RVV')
        if is_csr(ins) and pc not in self.lookup:
            if pc in self.spec['capacity_pcs']:
                require(not self.calls and self.main_entered and rd==(ins>>7)&31 and value==128,'Actual vlenb128')
                self.capacity+=1;require(self.capacity<=2,'Duplicate capacity')
            else:
                require(self.csr_count<5 and pc==self.spec['csr_prelude'][self.csr_count] and not self.main_entered,'Exact startup CSR')
                self.csr_count+=1
        if pc==self.s['num']:self.numbers.append(self.regs.get(10))
        if pc==self.s['replay_exit']:require(self.regs.get(10)==0,'Raw firmware exit0')
        d=memory_op(ins)
        if d:
            size=d['size'];require(d['base'] in self.regs and addr==(self.regs[d['base']]+d['offset'])&MASK64,'Actual scalar address/base')
            enable=((1<<size)-1)<<(addr%8);require(addr%size==0 and enable<=255,'Scalar alignment/mask width')
            if d['kind']=='write':
                require(wm==enable and rm==0 and d['register'] in self.regs and
                        (data&((1<<(8*size))-1))==(self.regs[d['register']]&((1<<(8*size))-1)),'Scalar store enables/value/register')
                if pc==self.spec['bss_store']:
                    require(size==8 and data==0 and not self.main_entered and addr==self.bss_next
                            and addr+8<=self.s['__bss_end'] and self.regs.get(6)==self.s['__bss_end'],'Ordered reset BSS')
                    self.bss_next+=8
                if self.armed and (self.s['input']<=addr<self.s['input']+1024 or self.s['output']<=addr<self.s['output']+1088):
                    require(self.helper is None and len(self.calls)<1134,'Fresh initialization phase')
                    self.finish_call();self.setup.store(addr,size,data,self.gold[len(self.calls)])
                for j in range(size):self.memory[addr+j]=(data>>(8*j))&255
                if addr==self.spec['uart']:
                    require(self.main_entered and size==1 and len(self.console)<8192,'Actual UART byte stream')
                    self.console.append(data&255)
                if addr==self.spec['ctrl']:
                    require(pc==self.spec['exit_store'] and size==8 and data==0 and self.regs.get(10)==0,'CTRL raw0 not HTIF1')
                    self.finish_call();self.setup.finish();require(len(self.calls)==1134,'Early exit')
                    self.exited=True;self.exit_retire=self.retired
            else:
                require(rm==enable and wm==0 and rd==d['register'],'Scalar load enables/destination')
                if self.s['output']<=addr<self.s['output']+1088:
                    require(self.active is not None and self.helper is None and self.active['returned'],'Original oracle phase')
                    coverage.word_read(self.active,addr-self.s['output'],size,value)
        elif not is_vector(ins):require(rm==wm==0,'Unclassified scalar memory')
        if rd and ins&127 not in (7,0x53,0x43,0x47,0x4b,0x4f):self.regs[rd]=value
        self.regs[0]=0
    def finish(self):
        owners=self.owners.finish();self.finish_call();self.setup.finish()
        require(self.exited and len(self.calls)==1134 and self.capacity==2 and self.csr_count==5,'Incomplete original program')
        require(self.numbers==[1134,366,0],'Original final numeric counters')
        text=self.console.decode('ascii');require(text==EXPECTED_TEXT,'Exact original UART/failure veto')
        return dict(status='FULL_ORIGINAL_RVFI_ACCEPTED',calls=1134,exclusions=366,output_byte_checks=1233792,
            fresh_input_stores=self.setup.input_stores,fresh_output_stores=self.setup.output_stores,output_word_reads=154224,
            vstart_reads=2268,helper_instructions=self.helper_instructions,owners=owners,retired=self.retired,rows=self.rows,
            last_cycle=self.cycle,firmware_through_ctrl=self.exit_retire,post_ctrl_parking=self.parking,
            full_order=True,partitioned=False,console=text,raw_exit=0,call_ledger=[{k:v for k,v in c.items() if k!='reads'} for c in self.calls])

def console_gate(text,simulator=True):
    require(not VETO.search(text),'Raw failure/detail veto')
    for line in EXPECTED_TEXT.splitlines():require(text.splitlines().count(line)==1,'Original complete console')
    require(not any(x.startswith(('RVV_WHOLE_','BOARD_CASE_PASS','BOARD_REPLAY_PASS')) and x not in EXPECTED_TEXT.splitlines()
                    for x in text.splitlines()),'Ambiguous oracle line')
    if simulator:require(text.count(common.SUCCESS)==1 and '$finish' in text,'Simulator actual exit')

def reference_pins():
    require(sha(REF/'RESULT.json')==READY_SHA and sha(REF/'reference_bound01.json')==BOUND_SHA,'Accepted reference identity')
    result=read(REF/'RESULT.json'); report=read(REF/'reference01/reference.json')
    require(result['status']==report['status']=='FULL1134_PACKED_REFERENCE_PASS_NOT_DUT' and result['retries']==0,'Actual complete reference')
    for key,limit in [('actual_spike',120),('actual_audit',600)]:
        x=result[key];require(type(x['returncode']) is int and x['returncode']==0 and not x['timeout'] and x['elapsed_s']<=limit and x['attempts']==1,'Reference numeric exit')
    require(sha(REF/'reference01/reference.json')==result['reference_sha256'] and
            [report[k] for k in ('calls','exclusions','fresh_input_stores','fresh_output_stores','output_word_reads','output_byte_checks','vstart_reads','raw_exit')]
            ==[1134,366,145152,154224,154224,1233792,2268,0] and not report['partitioned'],'Complete original reference scope')
    pins=dict(read(REF/'reference_bound01.json')['pins'])
    for n in ('RESULT.json','reference_bound01.json','reference01/reference.json','OUTCOME.json'):
        pins[str(REF/n)]=sha(REF/n)
    common.base.verify_pins(pins)
    return pins

def save(path,value):
    import json,os
    with Path(path).open('x') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())

def stream_validate(path,abort):
    import time
    from stream import one_pass
    path=Path(path);root=path.parent;began=time.monotonic()
    outcome=read(root/'child_outcome.unvalidated.json')
    require(type(outcome['returncode']) is int and outcome['returncode']==0 and
            not any(outcome[k] for k in ('timed_out','failure_seen','cancelled')),'Numeric wait before CSV')
    generic=load('whole_private_generic',Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/verification/ara_verify/trace.py'))
    strict=Strict(specification())
    def checkpoint():require(not abort.is_set() and time.monotonic()-began<900,'Bounded single-pass abort/deadline')
    try:
        general,specific,digest,identity=one_pass(path,strict,generic,checkpoint)
        specific.update(generic=general,raw_sha256=digest,raw_identity=identity,full_csv_passes=1,
                        elapsed_s=time.monotonic()-began,actual_numeric_outcome_sha256=sha(root/'child_outcome.unvalidated.json'))
        save(root/'strict_original.json',specific)
        return general
    except BaseException as error:
        save(root/'strict_first_error.json',dict(status='NOT_PASS',error=str(error),rows=strict.rows,
             calls=len(strict.calls),elapsed_s=time.monotonic()-began))
        abort.set();raise

def artifacts(result,case,ledger,spec,abort):
    common.check_artifacts(result,dict(case,original_name=case['id']),ledger)
    root=result.artifact_dir;console_gate((root/'console.log').read_text())
    require(not VETO.search((root/'work/run.vcs.log').read_text()),'Raw VCS failure')
    report=read(root/'strict_original.json')
    from stream import identity
    require(not abort.is_set() and report['status']=='FULL_ORIGINAL_RVFI_ACCEPTED' and
            report['full_csv_passes']==1 and report['raw_identity']==identity(root/'commit_trace.csv') and
            report['actual_numeric_outcome_sha256']==sha(root/'child_outcome.unvalidated.json'),'Single complete combined CSV audit')
    return report

