from functools import lru_cache
from scope import *
source=load('full6720_source_events',REF/'checker.py')
isa=source.base
def csr(c):return c&127==0x73 and ((c>>12)&7)!=0
def vector(c):return c&127==0x57 or c&127 in (7,39) and (c>>12)&7 in (0,5,6,7)
def offload(c):return vector(c) or csr(c) and c>>20 in (8,9,10,15,0xc20,0xc21,0xc22)
@lru_cache(maxsize=1)
def specification():
    require(sha(ELF)==ELF_SHA,'Exact SoC ELF')
    parser=load('full6720_linked_reader',G/'fp_compare_unboxed_full17920_prepare01/compile01/inspect_linked.py');parser.RUN=PREP/'execution01'
    d,code,func,sy,sizes=parser.parse('soc');ref=source.config()
    require(d==SOFTWARE and 'tohost' not in sy and 'replay_log' not in sy,'Actual SoC not Spike')
    image=isa.elf_image(ELF)
    require(all(isa.word(image,p,len(r['insn'])//2)==int(r['insn'],16) for p,r in code.items()),'All linked code bytes')
    helpers=[func['op_'+str(i)] for i in range(3)]
    require([[r['insn'] for r in h] for h in helpers]==[[r['insn'] for r in ref['func']['op_'+str(i)]] for i in range(3)],'All original63 helper encodings')
    body=func[NAME+'_main'];refbody=ref['func'][NAME+'_main']
    require(len(body)==len(refbody) and all(x['pc']==y['pc']-14 and x['op']==y['op'] and len(x['insn'])==len(y['insn']) for x,y in zip(body,refbody)),'Actual source event relocation, not borrowed PCs')
    def one(fn,op=None,args=None,insn=None):
        rs=[r for r in func[fn] if (op is None or r['op']==op) and (args is None or r['args']==args) and (insn is None or int(r['insn'],16)==insn)]
        require(len(rs)==1,'Unique actual linked site '+repr((fn,op,args,insn)));return rs[0]['pc']
    lower=read(PREP/'linked01/soc.json')
    pre=[r['pc'] for fn in ('_start',NAME+'_main') for r in func[fn] if csr(int(r['insn'],16))]
    require([int(code[p]['insn'],16) for p in pre]==[0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073,0xc2202473],'Six actual bootstrap CSR sites')
    opaque=[]
    for fn in ('main',NAME+'_main'):
        for r in func[fn]:
            if r['op']=='jal':break
            if r['op']=='sd' and '(sp)' in r['args'] and r['args'].split(',')[0] not in ('ra','zero'):opaque.append(r['pc'])
    failure=[int(p,16) for p,label in lower['zero_success_PCs'].items() if label!='VLEN512']
    failure.extend(r['pc'] for fn in ('trap_entry','replay_trap','hex') for r in func[fn])
    failure.extend(p for p in code if 0x80000768<=p<0x80000770 or 0x80000812<=p<0x8000082a)
    sites=dict(bss_store=one('_start',insn=0x0002b023),main_call=one('_start','jal',hex(sy['main'])[2:]+' <main>'),
               exit_store=one('replay_exit',insn=0x00a2b023),switch=one(NAME+'_main','jr','a5'))
    sites['park']=sites['exit_store']+4
    return dict(elf=str(ELF),symbols=sy,sizes=sizes,code={str(p):r for p,r in code.items()},func=func,
                helpers=helpers,capacity=func['capacity'],prelude=pre,opaque=opaque,failure_pcs=sorted(set(failure)),
                uart_stores=[one(fn,'sb','a4,0(a5)') for fn in ('replay_text','replay_write')],
                bits=ref['bits'],fixtures=[list(v) for v in ref['fixtures']],**sites)
@lru_cache(maxsize=1)
def model():
    s=source.config();return [source.original_call(s,n) for n in range(6720)]
def helper_owner(spec,op,i,g):
    c=int(spec['helpers'][op][i]['insn'],16)
    if not offload(c):return None
    if c&127 in (7,39):
        require(i in (1,2,4,5,19),'Original reduction memory instruction');return 'memory',True
    if c&127==0x57 and ((c>>12)&7)!=7:
        require(i==11,'Original reduction target');return 'target',g['vl']>0
    return 'configuration',False
def owner_contract():
    s=specification();counts=dict(memory=0,target_required=0,target_elidable=0)
    for g in model():
        for i in range(21):
            q=helper_owner(s,g['op'],i,g)
            if q and q[0]=='memory':counts['memory']+=1
            if q and q[0]=='target':counts['target_required' if q[1] else 'target_elidable']+=1
    require(counts==dict(memory=33600,target_required=5760,target_elidable=960),'Full original owner scope')
    return counts
