"""Actual masked SoC code, not relocated Spike effects or copied FP32 PCs."""
from functools import lru_cache
from scope import *
source=load('masked17920_reference_methods',REF/'checker.py')
linked=load('masked17920_immutable_linked_parser',G/'fp_compare_unboxed_full17920_prepare01/compile01/inspect_linked.py')
linked.RUN=PREP/'build01'
def csr(c):return c&127==0x73 and (c>>12)&7!=0
def vector(c):return c&127==0x57 or c&127 in (7,39) and (c>>12)&7 in (0,5,6,7)
def offload(c):return vector(c) or csr(c) and c>>20 in (8,9,10,15,0xc20,0xc21,0xc22)


@lru_cache(maxsize=1)
def specification():
    require(sha(ELF)==ELF_SHA,'Actual new SoC ELF')
    directory,code,funcs,sy,sizes=linked.parse('soc')
    require(directory==SOFTWARE and 'tohost' not in sy and 'replay_log' not in sy,'SoC not Spike')
    image=source.base.elf_image(ELF)
    for pc,r in code.items():require(source.word(image,pc,len(r['insn'])//2)==int(r['insn'],16),'Actual ELF bytes')
    lower=read(PREP/'linked01/soc.json')
    require(lower['elf_sha256']==ELF_SHA and lower['no_extra_RVV_FP'] is True,'Actual compiled lowering')
    helpers=[funcs['op_'+str(i)] for i in range(10)]
    require([[r['insn'] for r in h] for h in helpers]==[[r['insn'] for r in h] for h in read(REF/'spec.json')['helpers']],
        'Original masked185 helper identity')
    def one(fn,op=None,args=None,insn=None):
        rows=[r for r in funcs[fn] if (op is None or r['op']==op) and
            (args is None or r['args'].split(' #')[0]==args) and (insn is None or int(r['insn'],16)==insn)]
        require(len(rows)==1,'Unique actual site '+repr((fn,op,args,insn)));return rows[0]['pc']
    prelude=[r['pc'] for n in ('_start','main') for r in funcs[n] if csr(int(r['insn'],16))]
    require([int(code[p]['insn'],16) for p in prelude]==[0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073,0xc2202773],
        'Bootstrap CSR six')
    opaque=[]
    for fn in (NAME+'_main','main'):
        for r in funcs[fn]:
            if r['op']=='jal':break
            if r['op']=='sd' and '(sp)' in r['args'] and r['args'].split(',')[0] not in ('ra','zero'):opaque.append(r['pc'])
    failure=set(map(int,lower['failure_PCs']))
    main=funcs['main']
    for i,r in enumerate(main):
        if r['op']=='beq' and r['args'].startswith('a4,a5,'):
            end=next(x['pc'] for x in main[i+1:] if x['text']=='li s0,90')
            failure.update(x['pc'] for x in main[i+1:] if x['pc']<=end)
        if r['op']=='beqz' and r['args'].startswith('a0,'):
            target=int(r['args'].split(',')[-1].split()[0],16)
            failure.update(x['pc'] for x in main[i+1:] if x['pc']<target)
    failure.update(r['pc'] for n in ('trap_entry','replay_trap','hex') for r in funcs[n])
    sites=dict(record_load=one(NAME+'_main','ld','s6,0(a5)'),output_read=one(NAME+'_main','lwu','s0,0(s0)'),
        caller_record=one(NAME+'_main','srli','a4,s6,0x20'),caller_flags=one(NAME+'_main','or','a4,a4,t0'),
        bss_store=one('_start',insn=0x0002b023),main_call=one('_start','jal',hex(sy['main'])[2:]+' <main>'),
        exit_store=one('replay_exit',insn=0x00a2b023))
    sites['park']=sites['exit_store']+4
    require(int(code[sites['park']]['insn'],16)==0xa001,'Actual CTRL park')
    return dict(elf=str(ELF),elf_sha256=ELF_SHA,symbols=sy,sizes=sizes,code={str(p):r for p,r in code.items()},
        helpers=helpers,capacity=funcs['capacity'],stores=lower['fresh_store_sites'],input_loads=lower['input_LD_sites'],
        prelude=prelude,opaque_initial_spills=opaque,failure_pcs=sorted(failure),
        uart_stores=[one(n,'sb','a4,0(a5)') for n in ('replay_text','replay_write')],
        BSS_bytes=sy['__bss_end']-sy['__bss_start'],**sites)


@lru_cache(maxsize=1)
def model():
    rows=read(PREP/'model.json')['rows'];require(len(rows)==17920,'Full original masked parent');return rows


def helper_owner(spec,op,i,g):
    c=int(spec['helpers'][op][i]['insn'],16)
    if not offload(c):return None
    if c&127 in (7,39):
        require(i in (2,3,4,5,15+(2 if op>=4 else 0)),'Memory helper index');return ('memory',True)
    if c&127==0x57 and (c>>12)&7!=7:
        require(i==8+(2 if op>=4 else 0),'Target helper index');return ('target',g['vl']>0)
    return ('configuration',False)


@lru_cache(maxsize=1)
def owner_contract():
    spec=specification();counts=dict(memory=0,target_required=0,target_elidable=0)
    for g in model():
        for i in range(len(spec['helpers'][g['op']])):
            item=helper_owner(spec,g['op'],i,g)
            if item and item[0]=='memory':counts['memory']+=1
            if item and item[0]=='target':counts['target_required' if item[1] else 'target_elidable']+=1
    require(counts==dict(memory=89600,target_required=15360,target_elidable=2560),'Necessary104960 owners, alloff not waived')
    return counts
