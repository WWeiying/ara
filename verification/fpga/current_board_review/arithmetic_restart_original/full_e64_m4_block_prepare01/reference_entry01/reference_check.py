#!/usr/bin/env python3
"""One complete closed Spike parse. Exact e64 source bits, not host FP."""
import re
from context import artifacts,require,width
from lifecycle import Lifecycle,full_group,words
from raw_boundary import RawBoundary
LAST_CONTEXT={}

def validate_console(console):
    marker='RVV_MATRIX_PASS sew=64 vlmax=64 cases=5985 elements=383040 errors=0 seeds=3 guard_tail_mask_vstart=checked'
    require(console.splitlines()==[marker] and not re.search('FAIL|TRAP|UNSUPPORTED',console),'Raw full original console veto')
def validate_exit(value):require(type(value) is int and value==0,'Original software return nonzero')

def audit(raw):
    global LAST_CONTEXT
    symbols,code,helpers,rows=artifacts()
    lookup={i['pc']:(op,j,i['insn']) for op in range(35)
        for j,i in enumerate(helpers[f'op_{op}'])}
    regex=re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    rd_regex=re.compile(r'\bx\s*(\d+)\s+(0x[0-9a-f]+)')
    mem_regex=re.compile(r'\bmem\s+(0x[0-9a-f]+)(?:\s+(0x[0-9a-f]+))?')
    vec_regex=re.compile(r'\bv\s*(\d+)\s+0x([0-9a-f]+)')
    csr_regex=re.compile(r'\bc\d+_(vstart|vl|vtype)\s+0x([0-9a-f]+)')
    regs={0:0};memory={};vectors={};csrs={};fresh=set();reads=set()
    ordinal=0;step=0;counts=[0]*13;retired=0;boot=0;capacity=0;row=None
    capacity_counts=[0,0,0];capacity_lookup={x['pc']:i for i,x in enumerate(helpers['capacity'])}
    cap_step=0;bootstrap_fcsr=0;rounding_mode=None
    failure_pcs={v for n,v in symbols.items() if n.startswith('failure')}
    exit_entry=None;read_count=0;context=None
    a,b,out,mask=(symbols[n] for n in ('a','b','out','mask'))
    expected=None;report=None;boundary=RawBoundary()
    lifecycle=Lifecycle(symbols,code,[helpers[f'op_{i}'][0]['pc'] for i in range(35)],rows)
    def group(first):return full_group(vectors,first)
    def finish_call():
        if row is not None:require(step==0 and reads==set(range(66)),f'call{ordinal}: incomplete13/full66 oracle reads')
    with raw.open() as stream:
        for lineno,line in enumerate(stream,1):
            require('trap_' not in line,f'Unexpected reference trap line{lineno}')
            match=regex.match(line)
            if not match:
                require(not line.strip(),f'Unparsed raw line{lineno}')
                continue
            pc,insn,rest=int(match[1],16),int(match[2],16),match[3]
            LAST_CONTEXT=dict(line=lineno,firmware_before=retired,call=ordinal,pc=hex(pc),insn=hex(insn))
            state=boundary.enter(pc,insn,rest)
            if state=='boot':
                boot+=1
                require(retired+boot+boundary.park<=4000000,'Hard whole raw instruction bound')
                continue
            if state=='park':
                require(retired+boot+boundary.park<=4000000,'Hard whole raw instruction bound')
                continue
            retired+=1
            require(retired+boot<=4000000,'Hard reference instruction bound')
            require(code.get(pc)==insn,f'PC/code mismatch pc{pc:x}')
            lifecycle.enter(pc,regs)
            if pc==0x8000002a:
                require(insn==0x00305073 and bootstrap_fcsr==0,'Exact initial fcsr0 instruction')
                bootstrap_fcsr=1;rounding_mode=0
            if pc==0x8000002e:
                require(insn==0x00805073,'Exact initial vstart0 instruction');csrs['vstart']=0
            if pc in failure_pcs:raise ValueError(f'Original failure routine pc{pc:x} call{ordinal}')
            require(cap_step==0 or pc in capacity_lookup,'Interrupted capacity window')
            rd=rd_regex.search(rest);mem=mem_regex.findall(rest)
            context=dict(line=lineno,retired=retired,call=ordinal,pc=f'{pc:08x}',insn=f'{insn:08x}')
            if pc==symbols['replay_exit']:
                validate_exit(regs.get(10));exit_entry=retired-1
            if pc in capacity_lookup:
                k=capacity_lookup[pc]
                require(ordinal==0 and k==cap_step and capacity_counts[k]==0,'Capacity exact3 instruction owner/order')
                capacity_counts[k]+=1;cap_step=(cap_step+1)%3
            if pc==helpers['capacity'][1]['pc']:
                require(rd and int(rd[2],16)==64,'Capacity not64');capacity+=1
            w=width(insn,True)
            if w:
                require(len(mem)==1 and mem[0][1],'Scalar store log schema')
                address,value=int(mem[0][0],16),int(mem[0][1],16)
                lifecycle.store(pc,insn,address,w,value)
                for j in range(w):memory[address+j]=(value>>(8*j))&255
                if lifecycle.entered and out<=address<out+528:
                    require(address+w<=out+528,'Output setup writes beyond exact528')
                    fresh.update(range(address-out,address-out+w))
            h=lookup.get(pc)
            require(step==0 or h is not None,'Interrupted original helper window')
            if h is not None:
                op,j,want_insn=h
                require(j==step and insn==want_insn,'Original helper PC/order/machine code')
                if j==0:
                    finish_call();require(ordinal<5985,'Extra helper call')
                    row=rows[ordinal];ordinal+=1;reads=set()
                    require(op==row['op'] and capacity_counts==[1,1,1] and bootstrap_fcsr==1,'Original helper order/full prelude')
                    require(csrs.get('vstart')==0,'Legal bootstrap/previous helper vstart')
                    require([regs.get(n) for n in range(10,17)]==[a,b,out+8,row['vl'],64,mask,row['start']],
                        'Actual helper arguments/source context')
                    for base,want in ((a,words(row['a'])),(b,words(row['b'])),
                        (out,words([91]*66)),(mask,row['mask'])):
                        require([memory.get(base+k) for k in range(len(want))]==list(want),'Actual initialized bytes '+str(base))
                    require(all(memory.get(a+i)==memory.get(b+i)==0 for i in range(512,8192)) and all(memory.get(out+i)==0 for i in range(528,8208)),"Unused physical backing remains BSS zero")
                    require(fresh==set(range(528)),'Every call fresh exact528 setup');fresh=set()
                    expected=b''.join(w.to_bytes(8,'little') for w in row['words'])
                else:require(row and op==row['op'],'Cross-helper replay')
                if j in (0,5,10):
                    require(rd and int(rd[1])==5 and int(rd[2],16)==(row['vl'] if j==5 else 64),'vsetvl result')
                if j==8:
                    require(rounding_mode==0,'Original FP RNE setup retained, not flags oracle')
                    require((csrs.get('vl'),csrs.get('vtype'),csrs.get('vstart'))==(row['vl'],26,row['start']),
                        'Target CSR context')
                    require(group(8)==words(row['a']) and group(16)==words(row['b']) and
                        group(24)==words([91]*64),'Actual physical inputs/old vd')
                    require(0 in vectors and (vectors[0]&((1<<64)-1))==int.from_bytes(bytes(row['mask'][:8]),'little'),
                        'Actual predicate used')
                    require(regs.get(28)==7,'Original immediate scalar t3')
                if j==9:require(rd and int(rd[1])==10 and int(rd[2],16)==0,'Returned vstart')
                if j==11:require(group(24)==expected[8:520] and csrs.get('vl')==64,'Complete stored vector output')
                counts[j]+=1;step=(step+1)%13
            for n,v in vec_regex.findall(rest):vectors[int(n)]=int(v,16)
            for name,v in csr_regex.findall(rest):csrs[name]=int(v,16)
            if h and h[1]==8:
                require(group(24)==expected[8:520] and csrs.get('vstart')==0,'Target full bitwise output/reset')
            rwidth=width(insn,False)
            if rwidth:
                require(len(mem)==1 and not mem[0][1] and rd,'Scalar read log schema and actual destination value')
                address=int(mem[0][0],16)
                lifecycle.read(pc,address,rwidth,int(rd[2],16))
                if out<=address<out+528:
                    require(row is not None and step==0 and rd,'Output read outside scalar oracle')
                    offset=address-out;chunk=offset//8
                    require(offset%8==0 and rwidth==8 and chunk not in reads,
                        'Oracle exact66 full64bit words, no short tail')
                    require(int(rd[2],16)==int.from_bytes(expected[offset:offset+rwidth],'little'),
                        f'call{ordinal} full bitwise output/guard mismatch offset{offset} line{lineno}')
                    reads.add(chunk);read_count+=1
            lifecycle.effect(pc,(int(rd[1]),int(rd[2],16)) if rd else None)
            if rd:
                n=int(rd[1]);regs[n]=int(rd[2],16) if n else 0
            lifecycle.leave(pc,regs)
            if w and mem and int(mem[0][0],16)==symbols['tohost']:
                require(int(mem[0][1],16)==1 and exit_entry is not None,'Actual HTIF not success1')
                lifecycle.finish()
                require(all(symbols[n]+k in memory for n in ('checks','elements','errors') for k in range(8)),'Known full counter bytes')
                require([sum(memory[symbols[n]+k]<<(8*k) for k in range(8)) for n in ('checks','elements','errors')]==[5985,383040,0],'Original final full counters')
                require(bootstrap_fcsr==1,'Single actual fcsr0 bootstrap')
                require(read_count==395010 and capacity_counts==[1,1,1],'Full actual output reads/capacity window')
                finish_call();require(ordinal==5985 and counts==[5985]*13 and capacity==1,'Incomplete full5985/helper coverage')
                require(all(symbols['replay_log']+k in memory for k in range(8192)),'Known whole console BSS, no missing-byte substitution')
                console=bytes(memory[symbols['replay_log']+k] for k in range(8192)).split(b'\0',1)[0].decode('ascii')
                validate_console(console)
                boundary.success(pc,insn,int(mem[0][1],16))
                require(report is None,'Duplicate architectural completion')
                report=dict(status='ACCEPTED_FULL5985_SPIKE_SOURCE_ONLY_NOT_DUT',calls=ordinal,results=383040,
                    guards=11970,vstart_zero=5985,helper_instruction_counts=counts,helper_instructions=sum(counts),
                    packed_output_reads=read_count,expected_dictionary_reads=lifecycle.expected_reads,dictionary_ID_reads=lifecycle.id_reads,sticky_equal_BEQ=lifecycle.beq_count,sticky_zero_initializations=lifecycle.flag_zero_count,per_call_fresh_output_bytes=528,physical_mask_bytes=128,
                    firmware_to_exit=exit_entry,firmware_to_HTIF=retired,boot=boot,
                    capacity_instruction_counts=capacity_counts,mask_groups=lifecycle.mask_groups,
                    original_seed_scalar_writes=lifecycle.seed_cursor,FP_input_scalar_writes=lifecycle.fp_stores,FP_calls=lifecycle.fp_calls,
                    mask_clear_stores=lifecycle.mask_clear_stores,mask_bit_stores=lifecycle.mask_bit_stores,
                    physical_registers_per_group=4,observed_register_bytes=512,physical_register_bytes=128,vlm_read_bytes=8,console=console,closed_raw_parses=1,
                    final_context=context,fflags_oracle=False,bootstrap_fcsr_zero_instructions=bootstrap_fcsr)
    require(report is not None,'Reference ended without architectural full5985 exit: '+repr(context))
    boundary.finish()
    require(retired+boot+boundary.park<=4000000,'Hard whole raw instruction bound')
    report.update(post_HTIF_park_rows=boundary.park,whole_raw_rows=retired+boot+boundary.park,EOF_checked=True)
    return report
