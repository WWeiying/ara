"""Pure functions copied from pinned corrected02 auditor; no driver imports."""
from scoped_rv64c_memory import decode as compressed
def require(ok, why):
    if not ok: raise ValueError(why)

def descriptor(ins):
    if ins&3!=3:return compressed(ins)
    op=ins&127;f=(ins>>12)&7
    if op not in (3,35):return None
    require(f in ((0,1,2,3,4,5,6) if op==3 else (0,1,2,3)),'Scalar width')
    imm=ins>>20 if op==3 else (ins>>25<<5)|((ins>>7)&31)
    if imm&2048:imm-=4096
    return dict(kind='read' if op==3 else 'write',size=1<<(f&3),base=(ins>>15)&31,
                register=(ins>>(7 if op==3 else 20))&31,offset=imm)

def next_helper_pc(pc,ins,regs):
    size=4 if ins&3==3 else 2
    if ins==0x8082:return regs[1]&~1
    if ins&3!=3:
        # The exact original helpers use compressed J, BEQZ/BNEZ, and scalar LI.
        f=ins>>13
        if f==5:
            imm=((ins>>12)&1)<<11|((ins>>11)&1)<<4|((ins>>9)&3)<<8|((ins>>8)&1)<<10|((ins>>7)&1)<<6|((ins>>6)&1)<<7|((ins>>3)&7)<<1|((ins>>2)&1)<<5
            if imm&2048:imm-=4096
            return pc+imm
        if f in (6,7):
            imm=((ins>>12)&1)<<8|((ins>>10)&3)<<3|((ins>>5)&3)<<6|((ins>>3)&3)<<1|((ins>>2)&1)<<5
            if imm&256:imm-=512
            value=regs[8+((ins>>7)&7)]
            return pc+imm if (value==0)==(f==6) else pc+2
    if ins&127==0x63:
        f=(ins>>12)&7;require(f in (0,1),'Unexpected helper branch')
        imm=((ins>>31)&1)<<12|((ins>>7)&1)<<11|((ins>>25)&63)<<5|((ins>>8)&15)<<1
        if imm&4096:imm-=8192
        equal=regs[(ins>>15)&31]==regs[(ins>>20)&31]
        return pc+imm if equal==(f==0) else pc+4
    if ins&127==0x6f:
        imm=((ins>>31)&1)<<20|((ins>>12)&255)<<12|((ins>>20)&1)<<11|((ins>>21)&1023)<<1
        if imm&(1<<20):imm-=1<<21
        return pc+imm
    return pc+size
