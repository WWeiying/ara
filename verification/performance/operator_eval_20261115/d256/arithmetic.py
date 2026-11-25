"""Independent SoftFloat rounding at D256's actual FP32/F16 boundaries."""
import struct
from contract import require


def bits(x):return struct.unpack('<I',struct.pack('<f',x))[0]
def value(x):return struct.unpack('<f',struct.pack('<I',x))[0]


class Arithmetic:
    def __init__(self,sf):self.sf=sf;self.flags=0;self.exp_samples=[]
    def op(self,op,width,a,b=0,c=0,dst=None):
        out,flags=self.sf.evaluate(op,width,dst or width,0,a,b,c);self.flags|=flags;return out
    def add(self,a,b):return self.op('fma',32,0x3f800000,a,b)
    def sub(self,a,b):return self.add(a,b^0x80000000)
    def cast(self,src,dst,x):return self.op('cast',src,x,dst=dst)
    def expf(self,x):
        # Installed newlib ef_exp.c FMA-contracted instruction schedule. Its
        # FP instructions/constants are bound to the linked libm by expf_audit.
        if x==0xff800000:
            self.exp_samples.append(dict(input=x,output=0));return 0
        hx=x&0x7fffffff;sign=x>>31;k=0;hi=lo=0
        require(hx<0x42b00000 and (sign or hx==0),'Scalar expf outside proven nonpositive |x|<88 domain')
        if hx>0x3eb17218:
            if hx<0x3f851592:
                hi=self.sub(x,0x3f317180^(sign<<31));lo=0x3717f7d1^(sign<<31);k=1-2*sign
            else:
                z=self.op('fma',32,x,0x3fb8aa3b,0x3f000000^(sign<<31))
                integer,f=self.sf.evaluate('f2i',32,32,1,z);self.flags|=f
                k=integer if integer<0x80000000 else integer-(1<<32)
                fk=self.op('i2f',32,k)
                hi=self.op('fma',32,fk^0x80000000,0x3f317180,x);lo=self.op('mul',32,fk,0x3717f7d1)
            reduced=self.sub(hi,lo)
        elif hx<0x31800000:
            self.add(bits(1e30),x);y=self.add(0x3f800000,x)
            self.exp_samples.append(dict(input=x,output=y));return y
        else:reduced=x
        t=self.op('mul',32,reduced,reduced);p=0x3331bb4c
        for coefficient in (0xb5ddea0e,0x388ab355,0xbb360b61,0x3e2aaaab):p=self.op('fma',32,t,p,coefficient)
        c=self.op('fma',32,p^0x80000000,t,reduced);xc=self.op('mul',32,reduced,c)
        if not k:y=self.sub(0x3f800000,self.sub(self.op('div',32,xc,self.sub(c,0x40000000)),reduced))
        else:
            y=self.sub(0x3f800000,self.sub(self.sub(lo,self.op('div',32,xc,self.sub(0x40000000,c))),hi))
            require(k>=-125,'Scalar expf subnormal exponent unsupported');y=(y+(k<<23))&0xffffffff
        self.exp_samples.append(dict(input=x,output=y));return y

    def vector_exp(self,x):
        c=lambda text:bits(float.fromhex(text))
        minimum=c('-0x1.5d58ap+6');underflow=value(x)<value(minimum)
        if underflow:x=minimum
        z=self.op('fma',32,c('0x1.715476p+0'),x,c('0x1.8p23'))
        n=self.sub(z,c('0x1.8p23'))
        b=self.op('fma',32,c('-0x1.62e4p-1'),n,x)
        b=self.op('fma',32,c('-0x1.7f7d1cp-20'),n,b)
        k=((z<<23)+0x3f800000)&0xffffffff;u=self.op('mul',32,b,b)
        j=self.op('fma',32,
            self.op('fma',32,c('0x1.0e4020p-7'),b,c('0x1.573e2ep-5')),u,
            self.op('fma',32,c('0x1.555e66p-3'),b,c('0x1.fffdb6p-2')))
        j=self.op('fma',32,j,u,self.op('mul',32,b,c('0x1.ffffecp-1')))
        result=self.op('fma',32,j,k,k)
        return 0 if underflow else result
