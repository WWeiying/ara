"""Independent offline audit of sealed raw files. Never executes guest code."""
import collections
import hashlib
import json
from pathlib import Path
import re
import struct
import time

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent/'original_remaining9_prepare01'
STATIC=OUT.parent/'original_remaining9_static_review01/prepared_inspection01.json'
SHAPES=['e16_mf2','e16_m1','e16_m2','e16_m4','e16_m8','e32_mf2','e32_m2','e32_m4','e32_m8']
ISA='rv64gcv_zfh_zvfh_zvl1024b'
LIMITS={'steps':3000000,'raw_bytes':268435456,'seconds':120}
LINE=re.compile(r'^core\s+0: 3 (0x[0-9a-f]+) \((0x[0-9a-f]+)\)(.*)\n$')
REG=re.compile(r'\bx(\d+)\s+(0x[0-9a-f]+)')
CSR=re.compile(r'\bc\d+_(\w+)\s+(0x[0-9a-f]+)')
VEC=re.compile(r'\bv(\d+)\s+(0x[0-9a-f]+)')
MEM=re.compile(r'\bmem\s+(0x[0-9a-f]+)(?:\s+(0x[0-9a-f]+))?')
BOOT=[(0x1000,0x297,{5:0x1000},[]),(0x1004,0x02028593,{11:0x1020},[]),
      (0x1008,0xf1402573,{10:0},[]),(0x100c,0x0182b283,{5:0x80000000},[[0x1018,None]]),
      (0x1010,0x28067,{},[])]


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def save(p,value):
    with Path(p).open('x') as f:
        json.dump(value,f,indent=2);f.write('\n')


def scalar_fp(i):
    if i&3!=3:return i&3 in (0,2) and i>>13 in (1,5)
    return i&127 in (0x43,0x47,0x4b,0x4f,0x53) or (i&127 in (7,0x27) and (i>>12)&7 in (1,2,3,4))


def elf_reader(p):
    b=Path(p).read_bytes();assert b[:6]==b'\x7fELF\x02\x01'
    ph=struct.unpack_from('<Q',b,32)[0];size,n=struct.unpack_from('<HH',b,54)
    seg=[]
    for i in range(n):
        t,flags,off,va,pa,fs,ms,al=struct.unpack_from('<IIQQQQQQ',b,ph+i*size)
        if t==1:seg.append((va,va+fs,off))
    def get(a,n):
        for lo,hi,off in seg:
            if lo<=a and a+n<=hi:return b[off+a-lo:off+a-lo+n]
        raise AssertionError(('unmapped ELF',hex(a)))
    return get


def input_indices(s,i):
    if s==0:return i%2,False
    if s==1:return 14,False
    if s==2:return (2 if i%2 else 15),False
    if s==3:return (13 if i%2 else 12),False
    if s==4:return [2,7,3,7,11,11][i%6],i%6 in (3,5)
    if s==5:return [8,9,10,8,9,10][i%6],i%6>=3
    if s==6:return (15 if i%2 else 2),False
    return (7 if i%2 else 2),False


def audit_case(shape):
    start=time.monotonic();d=ROOT/shape;r=d/'reference01'
    proof=read(d/'sourceproof.json');c=proof['config'];sy=read(d/'spike/symbols.json')
    w,sew,cap=c['word_bytes'],c['sew'],c['cap'];assert w==sew//8 and c['vl']==cap//2
    old=elf_reader(d/'prepared/scenario.elf');get=elf_reader(d/'spike/program.elf')
    op=proof['helper_windows']['spike']['op_0']['new'];hpc={x[0]:i for i,x in enumerate(op)}
    for window in proof['helper_windows']['spike'].values():
        assert len(window['original'])==len(window['new'])==21
        for a,b in zip(window['original'],window['new']):
            assert a[1]==b[1] and old(a[0],len(a[1])//2)==get(b[0],len(b[1])//2)==bytes.fromhex(a[1])[::-1]
    ins=[(int(a,16),int(b,16),b,t) for a,b,t in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)',(d/'spike/program.dis').read_text(),re.M)]
    code={a:b for a,b,_,_ in ins}
    for pc,i,b,t in ins:
        assert get(pc,len(b)//2)==bytes.fromhex(b)[::-1] and not scalar_fp(i)
    caprows=[x for x in ins if sy['capacity']<=x[0]<sy['op_0']];cappc={x[0] for x in caprows}
    csrpcs=[pc for pc,i,_,_ in ins if i&127==0x73 and (i>>12)&7 and pc<sy['capacity'] and not sy['trap_entry']<=pc<sy['replay_exit']]
    unused={x[0] for n in ('op_1','op_2') for x in proof['helper_windows']['spike'][n]['new']}
    fixtures=[(int(a,16),int(b)) for a,b in re.findall(r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}',(d/'prepared/fixtures.h').read_text())]
    bits=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)',(d/'prepared/input_bits.h').read_text())]
    assert len(bits)==16 and len(fixtures)==6720 and fixtures[4905]==(c['nan'],16)
    ranges=[(n,sy[n],sy[n]+z) for n,z in [('input',512*w),('seed',64*w),('mask',64),('output',144),('replay_log',8192)]]
    regs=[0]*32;csrs={};memory={};pcs=collections.Counter();counts=collections.Counter()
    helper=[];capacity=[];prelude=[];reads=[];selected=[]
    setup=None;terminal=None;main=False;total=firmware=park=0
    def buf(n,z):return bytes(memory[sy[n]+j] for j in range(z))
    for line in (r/'commits.log').open():
        m=LINE.fullmatch(line);assert m,line[:160]
        pc,i,tail=int(m[1],16),int(m[2],16),m[3]
        total+=1;firmware+=pc>=0x80000000;pcs[pc]+=1
        wr={int(k):int(v,16) for k,v in REG.findall(tail)}
        cw={k:int(v,16) for k,v in CSR.findall(tail)}
        vw={k:int(v,16).to_bytes(128,'little').hex() for k,v in VEC.findall(tail)}
        mem=[[int(a,16),int(v,16) if v else None] for a,v in MEM.findall(tail)]
        assert not scalar_fp(i)
        if total<=5:
            assert (pc,i,wr,mem)==BOOT[total-1] and not(cw or vw)
            for k,v in wr.items():regs[k]=v
            continue
        assert pc>=0x80000000 and code.get(pc)==i and pc not in unused and pc!=sy['trap_entry']
        if terminal:
            assert pc==sy['_start']+0x7e and i==0xa001 and not(wr or cw or vw or mem)
            park+=1
        if pc==sy[c['identity']+'_main']:
            assert not main;main=True
        if pc in csrpcs:
            assert not capacity and pc==csrpcs[len(prelude)]
            if len(prelude)>=5:assert list(wr.values())==[128]
            prelude.append(pc)
        elif i&127==0x73 and (i>>12)&7:assert pc in hpc
        if pc in cappc:
            j=len(capacity);assert j<3 and pc==caprows[j][0] and len(prelude)==7
            if j:assert total==capacity[-1]['ordinal']+1
            if j==1:assert regs[5]==(1<<64)-1 and wr=={10:cap}
            capacity.append(dict(ordinal=total,pc=pc,csrs=cw,regs={str(k):v for k,v in wr.items()}))
        if pc==op[0][0]:
            assert setup is None and len(capacity)==3
            setup=dict(ordinal=total,args=regs[10:18],input=list(buf('input',cap*w)),seed=list(buf('seed',64*w)),mask=list(buf('mask',64)),output=list(buf('output',144)))
        if pc in hpc:
            j=len(helper);assert j<21 and pc==op[j][0] and total==setup['ordinal']+j
            helper.append(dict(ordinal=total,pc=pc,insn=f'{i:0{len(op[j][1])}x}',regs={str(k):v for k,v in wr.items()},csrs=cw,vectors=vw,memory=mem,before_regs=regs.copy()))
        if i&127==0x57 or (i&127 in (7,0x27) and (i>>12)&7 in (0,5,6,7)):
            assert pc in hpc or pc==caprows[1][0];counts['rvv']+=1
        for addr,value in mem:
            if value is None:
                if sy['fixtures']<=addr<sy['fixtures']+6720*16:
                    j=counts['fixture_fields'];row=3360+j//2;field=(j%2)*8
                    assert j<6720 and addr==sy['fixtures']+row*16+field and len(wr)==1
                    assert list(wr.values())==[fixtures[row][field//8]]
                    if row==4905:selected.append([addr,next(iter(wr.values()))])
                    counts['fixture_fields']+=1
                if len(helper)==21 and sy['output']<=addr<sy['output']+144:
                    assert i&~0xf80==0x00064003 and len(wr)==1 and ((i>>7)&31) in wr
                    reads.append([addr-sy['output'],wr[(i>>7)&31]])
                continue
            if addr==sy['tohost']:
                assert terminal is None and pc==sy['_start']+0x7a and i==0x00a2b023
                terminal=dict(ordinal=total,firmware_retired=firmware,value=value,pc=pc)
            owner=next((n for n,lo,hi in ranges if lo<=addr<hi),None)
            if owner is None:continue
            if pc==op[19][0]:size=w
            elif i&127==0x23:size=1<<((i>>12)&7)
            else:
                assert i&3 in (0,2) and i>>13 in (6,7);size=4 if i>>13==6 else 8
            assert size<=8
            for j,b in enumerate(value.to_bytes(size,'little')):memory[addr+j]=b
            if main and pc not in hpc:
                if owner=='input':
                    s,j=divmod(counts['input_elements'],cap);assert s<8
                    index,sign=input_indices(s,j)
                    assert addr==sy[owner]+j*w and size==w and value==bits[index]^((1<<(sew-1)) if sign else 0)
                    counts['input_elements']+=1
                elif owner=='seed':
                    s,j=divmod(counts['seed_elements'],64)
                    assert s<8 and addr==sy[owner]+j*w and size==w and value==bits[[1,14,2,12,2,8,1,12][s]]
                    counts['seed_elements']+=1
                elif owner=='mask':
                    fill,j=divmod(counts['mask_bytes'],64)
                    assert fill<3360 and addr==sy[owner]+j and size==1 and value==[255,0,85,36][(fill//15)%4]
                    counts['mask_bytes']+=1
                elif owner=='output':
                    j=counts['output_init'];assert setup is None and j<144 and addr==sy[owner]+j and size==1 and value==91
                    counts['output_init']+=1
        for k,v in wr.items():regs[k]=v
        regs[0]=0;csrs.update(cw)
    assert counts==dict(rvv=11,input_elements=8*cap,seed_elements=512,fixture_fields=6720,mask_bytes=215040,output_init=144)
    assert len(helper)==21 and len(reads)==144 and len(capacity)==3 and len(prelude)==7
    assert setup['args']==[sy['input'],sy['seed'],sy['output']+8,cap//2,cap,sy['mask'],0,0]
    inp=b''.join((c['inf']|((1<<(sew-1)) if j%2 else 0)).to_bytes(w,'little') for j in range(cap))
    assert setup['input']==list(inp) and setup['seed']==list(c['inf'].to_bytes(w,'little')*64)
    assert setup['mask']==[36]*64 and setup['output']==[91]*144
    assert selected==[[sy['fixtures']+4905*16,c['nan']],[sy['fixtures']+4905*16+8,16]]
    lm={'mf2':7,'m1':0,'m2':1,'m4':2,'m8':3}[c['lmul']];base=8 if sew==16 else 16
    capcsr=capacity[1]['csrs'];assert capcsr['vtype']==base|lm and capcsr['vl']==cap and capcsr['vstart']==0
    vt=capcsr['vtype'];h=helper
    for j,vl,typ in [(0,128//w,base),(3,cap,base|lm),(6,cap//2,base|lm),(18,128//w,base)]:
        vt=h[j]['csrs'].get('vtype',vt)
        assert vt==typ and h[j]['regs']=={'5':vl} and h[j]['csrs']['vl']==vl and h[j]['csrs']['vstart']==0
    for j,reg,payload,addresses in [(1,16,c['inf'].to_bytes(w,'little')*(128//w),range(sy['seed'],sy['seed']+128,w)),(2,24,b'\x5b'*128,range(sy['output']+8,sy['output']+136,w)),(4,8,inp,range(sy['input'],sy['input']+cap*w,w)),(5,0,b'\x24'*((cap+7)//8),range(sy['mask'],sy['mask']+(cap+7)//8))]:
        n=(len(payload)+127)//128
        assert set(h[j]['vectors'])=={str(reg+k) for k in range(n)}
        assert b''.join(bytes.fromhex(h[j]['vectors'][str(reg+k)]) for k in range(n))[:len(payload)]==payload
        assert h[j]['memory']==[[a,None] for a in addresses]
    result=c['nan'].to_bytes(w,'little')+b'\x5b'*(128-w)
    assert h[7]['regs']=={'29':0} and h[8]['regs']=={'30':0}
    assert h[9]['csrs']['frm']==h[10]['csrs']['fflags']==0
    assert h[11]['vectors']=={'24':result.hex()} and h[11]['csrs']['fflags']==16 and h[11]['csrs']['vstart']==0
    assert h[12]['regs']=={'10':0} and h[13]['regs']=={'6':16} and h[14]['regs']=={'6':16<<32} and h[15]['regs']=={'10':16<<32}
    assert h[16]['csrs']['frm']==h[17]['csrs']['fflags']==0 and h[16]['before_regs'][29]==h[17]['before_regs'][30]==0
    assert csrs['frm']==csrs['fflags']==csrs['vstart']==0
    assert h[19]['memory']==[[sy['output']+8+j,int.from_bytes(result[j:j+w],'little')] for j in range(0,128,w)]
    assert reads==[[j,b] for j,b in enumerate(b'\x5b'*8+result+b'\x5b'*8)]
    console=buf('replay_log',8192).split(b'\0')[0].decode('ascii')
    assert console==f"BOARD_CASE_BEGIN {c['identity']}\nRVV_FP_REDSPECIAL_PASS sew={sew} cases=1 flags_seen=16 errors=0\nBOARD_CASE_PASS {c['identity']}\nBOARD_REPLAY_PASS\n"
    assert terminal['value']==1 and terminal['firmware_retired']+5+park==total
    ledger=read(r/'ledger.json')
    actual=dict(setup=setup,helper=helper,output_reads=reads,selected_fixture=selected,counts=dict(counts),capacity=capacity,prelude=prelude,console=console,terminal=terminal,retired_total=total,parking_retired=park,pc_counts={hex(k):v for k,v in pcs.items()})
    assert actual==ledger,'complete independent ledger differs'
    a,e=read(r/'admission.json'),read(r/'execution.json');resultrow=read(r/'result.json')
    assert a['limits']==LIMITS and a['profile']==e['profile']==ISA
    assert a['command']==[str(Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')),'-d','--debug-cmd='+str(r/'spike.cmd'),'--isa='+ISA,'-m2','--log-commits','--log='+str(r/'commits.log'),str(d/'spike/program.elf')]
    assert (r/'spike.cmd').read_text()==f"rs 3000000\nstr {sy['replay_log']:x}\nquit\n"
    assert sha(r/'admission.json')==read(r/'admission.pin.json')['sha256']==e['admission_sha256']==read(r/'ATTEMPT_STARTED.json')['admission_sha256']
    assert e['returncode']==0 and e['error'] is None and 0<e['elapsed_s']<120
    assert terminal['firmware_retired']<a['static_upper']<3000000 and total<=3000000
    for name,row in e['raw'].items():
        assert (r/name).stat().st_size==row['bytes']<=268435456 and sha(r/name)==row['sha256']
    assert resultrow['firmware_retired']==terminal['firmware_retired'] and resultrow['retired_total']==total and resultrow['parking_retired']==park
    assert resultrow['result']==hex(c['nan']) and resultrow['flags']==16 and resultrow['vstart']==0
    host=read(r/'checker_host.json');assert host['status']=='PASS_20_HOST_ONLY' and host['positive'] and len(host['negatives'])==19
    assert all(x['rejected'] for x in host['negatives'])
    return dict(shape=shape,status='INDEPENDENT_SINGLE_REFERENCE_ACCEPTED',firmware=terminal['firmware_retired'],total=total,boot=5,park=park,target_pc=hex(h[11]['pc']),target_ordinal=h[11]['ordinal'],result=hex(c['nan']),flags=16,vstart=0,full_oracle_bytes=144,helper_instructions=21,fixture_fields=6720,input_elements=8*cap,seed_elements=512,mask_bytes=215040,static_upper=a['static_upper'],reference_seconds=e['elapsed_s'],raw_bytes=(r/'commits.log').stat().st_size,raw_sha256=sha(r/'commits.log'),ledger_sha256=sha(r/'ledger.json'),spike_sha256=sha(d/'spike/program.elf'),soc_sha256=sha(d/'soc/program.elf'),independent_ledger_equal=True,no_scalar_FP=True,profile=ISA,offline_seconds=time.monotonic()-start)


def main():
    start=time.monotonic()
    assert sha(ROOT/'READY.json')=='ad59b118f7b223b7deea74a04e43a63ff616705571748e01f0d18e1ce98d937c'
    assert sha(ROOT/'TERMINAL_CHECK.json')=='996e2ad07ecfcf3daadd52018791c590c129fa6e8610a999fa9310249ddba491'
    root=read(ROOT/'READY.json');terminal=read(ROOT/'TERMINAL_CHECK.json');static=read(STATIC)
    assert root['shapes']==SHAPES and terminal['shapes']==SHAPES
    pins={}
    def merge(items):
        for p,h in items.items():
            assert p not in pins or pins[p]==h,p
            pins[p]=h
    merge(terminal['evidence_pins']);merge(static['pins']);merge(root['case_ready_pins'])
    merge({str(ROOT/'TERMINAL_CHECK.json'):sha(ROOT/'TERMINAL_CHECK.json'),str(STATIC):sha(STATIC)})
    for shape in SHAPES:merge(read(ROOT/shape/'READY.json')['pins'])
    for p,h in pins.items():assert sha(p)==h,p
    assert len(list(ROOT.glob('*/reference01/ATTEMPT_STARTED.json')))==9
    assert not (ROOT/'STOPPED.json').exists()
    print(f'PRECHECK {len(pins)} pins match; nine sealed raws only',flush=True)
    rows=[]
    for shape in SHAPES:
        row=audit_case(shape);save(OUT/(shape+'.json'),row);rows.append(row)
        print(shape,'RAW_AUDIT_PASS',row['firmware'],round(row['offline_seconds'],2),flush=True)
    for p,h in pins.items():assert sha(p)==h,p
    for a,b in zip(rows,root['results']):assert a['shape']==b['shape'] and a['firmware']==b['firmware_retired']
    save(OUT/'result.json',dict(status='INDEPENDENT_REFERENCE_ALL9_ACCEPTED_NOT_DUT',shapes=SHAPES,rows=rows,pins=pins,pins_unchanged=True,profile=ISA,script_sha256=sha(__file__),raw_commits=sum(x['total'] for x in rows),firmware_commits=sum(x['firmware'] for x in rows),oracle_bytes=9*144,fixture_fields=9*6720,helper_instructions=9*21,offline_seconds=time.monotonic()-start,DUT_accepted=False,Linux_accepted=False,full6720_accepted=False))
    print('COMPLETE INDEPENDENT_REFERENCE_ALL9_ACCEPTED_NOT_DUT',flush=True)


if __name__=='__main__':
    main()
