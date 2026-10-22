"""Independent integer FP16 comparator; original unboxed-scalar semantics."""
NAME='fp_compare_unboxed_e16_mf4_prefix265'
CAP,BOUND=16,265
INPUT=[0,0x8000,0x3c00,0xbc00,0x3800,0x4000,0x4200,0x1000,1,0x3ff,0x400,0x7bff,0x7c00,0xfc00,0x7e55,0x7c55]
def require(ok,message):
    if not ok: raise ValueError(message)
def compare(op,a,b):
    an=(a&0x7c00)==0x7c00 and bool(a&1023); bn=(b&0x7c00)==0x7c00 and bool(b&1023)
    sn=(an and not a&512) or (bn and not b&512)
    eq=a==b or not a&0x7fff and not b&0x7fff
    ka=a^ (0xffff if a&0x8000 else 0x8000); kb=b^(0xffff if b&0x8000 else 0x8000)
    lt=not eq and ka<kb
    bit=(op==1) if an or bn else (eq,not eq,lt,lt or eq,not lt and not eq,not lt)[op]
    return int(bit),16*int(bool(sn if op<2 else an or bn))
def model():
    rows=[]
    for seed in range(32):
        for op in range(10):
            for vl in (0,1,2,3,8,15,16):
                for mode in range(4):
                    for sticky in range(2):
                        a=[INPUT[(i+seed+7*(seed//16))%16] for i in range(16)]
                        b=[INPUT[(i*3+seed*5+seed//16)%16 if op<4 else seed%16] for i in range(16)]
                        flags=sticky; allowed=[]
                        for i in range(16):
                            bit,nv=compare(op if op<4 else op-4,a[i],b[i] if op<4 else 0x7e00)
                            old=(91>>(i%8))&1
                            allowed.append([bit] if i<vl else [old] if vl==0 else sorted({old,1,bit}))
                            if i<vl:flags|=nv
                        rows.append(dict(ordinal=len(rows)+1,seed=seed,op=op,vl=vl,mode=mode,sticky=sticky,vstart=0,
                                         a=a,b=b,mask=[(255,170,36,0)[mode]]*128,allowed=allowed,flags=flags))
                        if len(rows)==265:
                            require((seed,op,vl,mode,sticky)==(0,4,15,0,0),'Endpoint')
                            return dict(rows=rows,calls=265,capacity=16,predecessors=264,result_bits=4240,guards=530)
