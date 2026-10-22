"""Integer FP16 vmfeq and original alias old-bit/tail policy, no Spike gold."""
from newscope import NAME
CAP,BOUND=512,50
INPUT=[0,0x8000,0x3c00,0xbc00,0x3800,0x4000,0x4200,0x1000,1,0x3ff,0x400,0x7bff,0x7c00,0xfc00,0x7e55,0x7c55]


def require(ok,why):
    if not ok: raise ValueError(why)


def compare(op,a,b):
    require(op==0,'Only original first50 op0')
    an=(a&0x7c00)==0x7c00 and bool(a&1023)
    bn=(b&0x7c00)==0x7c00 and bool(b&1023)
    sn=(an and not a&512) or (bn and not b&512)
    eq=a==b or not(a&0x7fff) and not(b&0x7fff)
    return int(not(an or bn) and eq),16*int(bool(sn))


def model():
    rows=[]
    for vl in (0,1,2,3,256,511,512):
        for mode in range(4):
            for sticky in range(2):
                a=[INPUT[i%16] for i in range(CAP)]
                b=[INPUT[(3*i)%16] for i in range(CAP)]
                flags=sticky;allowed=[]
                for i in range(CAP):
                    bit,nv=compare(0,a[i],b[i])
                    old=(a[i//16]>>(i%16))&1
                    allowed.append([bit] if i<vl else [old] if vl==0 else sorted({old,1,bit}))
                    if i<vl:flags|=nv
                rows.append(dict(ordinal=len(rows)+1,seed=0,op=0,vl=vl,mode=mode,sticky=sticky,vstart=0,
                    a=a,b=b,mask=[(255,170,36,0)[mode]]*128,allowed=allowed,flags=flags))
                if len(rows)==BOUND:
                    require((vl,mode,sticky,flags)==(512,0,1,17),'Original historical call50 endpoint')
                    return dict(rows=rows,calls=BOUND,capacity=CAP,predecessors=49,result_bits=25600,guards=100)
