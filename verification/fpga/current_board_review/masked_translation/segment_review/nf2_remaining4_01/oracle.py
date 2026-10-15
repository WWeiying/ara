"""Independent halfword/byte oracle; no expected values derived from DUT."""
import sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]))
import sv39_adapter as base
from scope import CASES,require
NAMES=tuple(c['id'] for c in CASES)
OFF=tuple(c['base'] for c in CASES)
SITE=tuple('mx_segment_store' if c['store'] else 'mx_segment_load' for c in CASES)
VA,G,DONE=0x40000000,0xe370697ce370697c,0x7365677376333904
COUNTS=(756,758,474,474)
def phases(c):return (1,2) if CASES[c]['fault'] else (3,2)
def record_count(c,p):return 1+int(CASES[c]['fault'] and p==2)
def active(c,i):return bool(CASES[c]['mask']&(1<<i))
def seed(c,r,i):
    return 0x6c00+256*r+i if r in (0,3) else (101+13*i+29*(r-1) if CASES[c]['store'] else 0x5b)
def orig(h):return (37*h+11)&65535
def partial_vector(c,p,r,i):
    return p==1 and CASES[c]['fault'] and not CASES[c]['store'] and r in (1,2) and i==CASES[c]['start']
def partial_mem(c,p,h):
    return p==1 and CASES[c]['store'] and CASES[c]['fault'] and OFF[c]+4*CASES[c]['start']<4096 and h==(OFF[c]+4*CASES[c]['start'])//2
def vg(c,p,r,i):
    if not CASES[c]['store'] and r in (1,2) and i<8 and active(c,i) and (p!=1 or i<CASES[c]['start']):
        return orig((OFF[c]+4*i+2*(r-1))//2)
    return seed(c,r,i)
def memory_gold(c,p):
    data=[orig(h) for h in range(4096)]
    for i in range(8):
        if not active(c,i):continue
        for f in (0,1):
            h=(OFF[c]+4*i+2*f)//2
            if CASES[c]['store'] and (p!=1 or i<CASES[c]['start']):data[h]=seed(c,f+1,i)
            if p==2 and CASES[c]['fault'] and i<CASES[c]['start']:
                data[h]=(seed(c,f+1,i) if CASES[c]['store'] else orig(h))^0x5b
    return data
def check_host(text):
    rows=[]
    for c in range(4):
        for p in sorted(phases(c)):
            rows += ['V %d %d %d %d %d %04x'%(c,p,r,i,partial_vector(c,p,r,i),vg(c,p,r,i))
                     for r in range(4) for i in range(64)]
            rows += ['D %d %d %d %d %04x'%(c,p,h,partial_mem(c,p,h),v)
                     for h,v in enumerate(memory_gold(c,p))]
    require(text.splitlines()==rows,'Independent Python / host C oracle differs')
    return len(rows)

def expected(s,c,p):
    want, choices = {}, []
    def put(a,v,n):
        for i,b in enumerate(v.to_bytes(n,'little')):
            base.require(a+i not in want,'Overlapping oracle regions')
            want[a+i]=b
    pages=s['mx_pages']
    pte=lambda a,f:(a>>12<<10)|f
    for h,v in enumerate(memory_gold(c,p)):
        if partial_mem(c,p,h):
            choices.append((pages+2*h,2,(orig(h),seed(c,1,CASES[c]['start']))))
        else: put(pages+2*h,v,2)
    for page in range(2,5):
        for w in range(512):
            v=0
            if page==2: v=pte(pages+12288,1) if w==1 else 0x200000cf if w==2 else 0
            if page==3 and w==0: v=pte(pages+16384,1)
            if page==4 and (w==0 or w==1 and p==2): v=pte(pages+w*4096,0xc7)
            put(pages+page*4096+w*8,v,8)
    for name in ('mx_guard_lo','mx_guard_hi'):
        for w in range(8): put(s[name]+w*8,G,8)
    for name in ('mx_seed','mx_fault','mx_result'):
        a=s[name]+640*c
        for off in (0,576):
            for w in range(8): put(a+off+w*8,G,8)
        for r in range(4):
            for i in range(64):
                if name=='mx_fault' and CASES[c]['fault'] and partial_vector(c,1,r,i): continue
                value=seed(c,r,i) if name=='mx_seed' else (
                    vg(c,1 if name=='mx_fault' else 2,r,i)
                    if (name=='mx_fault' and CASES[c]['fault']) or (name=='mx_result' and p!=1)
                    else (G>>((i%4)*16))&65535)
                put(a+64+128*r+2*i,value,2)
    for i in range(130):
        v=vg(c,2,1+(i-1)//64,(i-1)%64) if p!=1 and 1<=i<=128 else 0x5b
        put(s['mx_out']+260*c+2*i,v,2)
    for j,v in enumerate((8,8,0,117,5) if p!=1 else ((1<<64)-1,)*5):
        put(s['mx_post']+40*c+8*j,v,8)
    for i in range(16): put(s['mx_mask']+16*c+i,CASES[c]['mask'],1)
    for n in range(2):
        used=n<record_count(c,p)
        fault=CASES[c]['fault'] and n==0
        vals=([15 if CASES[c]['store'] else 13,s[SITE[c]],VA+OFF[c]+4*CASES[c]['start'],None,
               (8<<60)|((pages+8192)>>12),8,8,CASES[c]['start'],117,5,0,0] if fault else
              [9,s['mx_ecall'],0,None,(8<<60)|((pages+8192)>>12),8,8,0,117,5,1,
               pte(pages+4096,0xc7) if CASES[c]['fault'] else 0])
        if not used: vals=[(1<<64)-1]*12
        for j,v in enumerate(vals):
            a=s['mx_records']+192*c+96*n+8*j
            if used and fault and j==2:
                choices.append((a,8,(VA+OFF[c]+4*CASES[c]['start'],VA+OFF[c]+4*CASES[c]['start']+2)))
            elif v is not None: put(a,v,8)
    for name,v in (('mx_count',record_count(c,p)),('mx_marker',int(p!=1))):
        put(s[name]+8*c,v,8)
    return want,choices


def readint(memory,a,n=8):
    return int.from_bytes(bytes(memory.get(a+i,255) for i in range(n)),'little')


def compare(memory,s,c,p):
    want,choices=expected(s,c,p)
    bad=[(hex(a),v,memory.get(a)) for a,v in want.items() if memory.get(a)!=v]
    base.require(not bad,f'{NAMES[c]} phase{p}: {bad[:8]}')
    for a,n,values in choices:
        base.require(readint(memory,a,n) in values, f'Invalid partial/field-address value at {a:x}')
    for n in range(record_count(c,p)):
        base.require(readint(memory,s['mx_records']+192*c+96*n+24)&0x8000031888==0x800,
                     'Trap mstatus not S-mode')
    return len(want)
