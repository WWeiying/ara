"""Full original e8/mf4 cap32 model; original integer-only25 operation order."""
import hashlib
import math
import struct

CAP=32
FP=[0xc1000000,0xc0000000,0x80000000,0,0x3f000000,0x3f800000,0x40000000,0x41000000]
KINDS=[0]*19+[1,1,1,2,3,0]+[0]*10
def require(ok,why):
    if not ok:raise ValueError(why)
def selected(mode,i):return mode==0 or (mode==1 and i%2==1) or (mode==2 and i%7==2)
def signed(x,sew):return x-(1<<sew) if x>>(sew-1) else x
def fp(op,x,y):
    a,b=(struct.unpack('<f',struct.pack('<I',z))[0] for z in (x,y))
    if op==31:return (x&0x7fffffff)|(y&0x80000000)
    if op==32:return (x&0x7fffffff)|((~y)&0x80000000)
    if op==33:return x^(y&0x80000000)
    if op in (29,30):
        if a==b==0:return (x|y) if op==29 else (x&y)
        return x if (a<b if op==29 else a>b) else y
    if op==25:v=a+b
    elif op==26:v=a-b
    elif op==27:v=a*b
    elif op==28:
        if b==0:return 0x7fc00000 if a==0 else 0x7f800000|((x^y)&0x80000000)
        v=a/b
    elif op==34:
        if a<0:return 0x7fc00000
        v=math.sqrt(a)
    else:raise ValueError('Unknown FP op')
    if math.isnan(v):return 0x7fc00000
    return struct.unpack('<I',struct.pack('<f',v))[0]
def integer(op,x,y,sew):
    mod=(1<<sew)-1;sx,sy=signed(x,sew),signed(y,sew)
    if op==0:v=x+y
    elif op==1:v=x-y
    elif op==2:v=x&y
    elif op==3:v=x|y
    elif op==4:v=x^y
    elif op==5:v=x<<(y&(sew-1))
    elif op==6:v=x>>(y&(sew-1))
    elif op==7:v=sx>>(y&(sew-1))
    elif op==8:v=min(x,y)
    elif op==9:v=max(x,y)
    elif op==10:v=x if sx<sy else y
    elif op==11:v=x if sx>sy else y
    elif op==12:v=x*y
    elif op==13:v=x//y if y else mod
    elif op==14:v=x%y if y else x
    elif op in (15,16):
        if sy==0:return mod if op==15 else x
        quotient=(abs(sx)//abs(sy))*(-1 if (sx<0)!=(sy<0) else 1)
        v=quotient if op==15 else sx-quotient*sy
    elif op==17:v=x+7
    elif op==18:v=x+3
    else:raise ValueError('Unknown integer op')
    return v&mod
def fnv(data):
    h=14695981039346656037
    for b in data:h=((h^b)*1099511628211)&((1<<64)-1)
    return h
def words(values,sew):return b''.join(v.to_bytes(sew//8,'little') for v in values)
def rows(sew):
    require(sew == 8,'Only authorized full e8 mf4')
    rows=[];mod=(1<<sew)-1
    for seed in range(3):
        random=0x937ad68de41c725f^seed;a=[];b=[]
        for i in range(CAP):
            random^=(random<<13)&((1<<64)-1);random^=random>>7;random^=(random<<17)&((1<<64)-1)
            x,y=random&mod,(random>>19)&mod
            if i%8==0:x=y=0
            elif i%8==1:x,y=mod,1
            elif i%8==2:x,y=1<<(sew-1),mod
            elif i%8==3:y=sew
            a.append(x);b.append(y)
        for op in range(25 if sew<32 else 35):
            for li,vl in enumerate((0,1,2,3,CAP//2,CAP-1,CAP)):
                for mode in range(3):
                    mask=[0]*128
                    for i in range(CAP):
                        if selected(mode,i):mask[i//8]|=1<<(i%8)
                    for si in range(3 if KINDS[op]==0 else 1):
                        start=(0,vl//2,vl if vl<CAP else CAP-1)[si]
                        if op>=25:a=[FP[(i+seed)%8] for i in range(CAP)];b=[FP[(i*3+seed)%8] for i in range(CAP)]
                        out=[91]*CAP
                        if op==22:
                            if vl:out[0]=(b[0]+sum(a[i] for i in range(vl) if selected(mode,i)))&mod
                        elif op==23:
                            packed=[a[i] for i in range(vl) if selected(mode,i)];out[:len(packed)]=packed
                        else:
                            for i in range(start,vl):
                                if not selected(mode,i):continue
                                if op<19:out[i]=integer(op,a[i],b[i],sew)
                                elif op==19:
                                    if i>=2:out[i]=a[i-2]
                                elif op==20:out[i]=a[i+2] if i+2<CAP else 0
                                elif op==21:out[i]=a[b[i]] if b[i]<CAP else 0
                                elif op==24:out[i]=a[i]
                                else:out[i]=fp(op,a[i],b[i])
                        data=words(a+b,sew)+bytes(mask)+words([91]*(CAP+2),sew)
                        rows.append(dict(ordinal=len(rows),seed=seed,op=op,li=li,vl=vl,mode=mode,si=si,vstart=start,
                            a=list(a),b=list(b),mask=mask,expected=out,input_fnv64=fnv(data)))
    require(len(rows)==(4095 if sew<32 else 5985),'Exact full sequence count')
    return rows
