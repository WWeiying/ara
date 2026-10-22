"""RV64C memory instruction metadata only, not an ISA execution model."""


def decode(word):
    if not isinstance(word,int) or not 0<=word<65536:
        raise ValueError('Expected one zero-extended compressed instruction')
    quadrant,funct3 = word&3,word>>13
    if quadrant not in (0,2) or funct3 not in (1,2,3,5,6,7): return None
    load = funct3<4
    size = 4 if funct3 in (2,6) else 8
    floating = funct3 in (1,5)
    if quadrant==0:
        register = 8+((word>>2)&7)
        base = 8+((word>>7)&7)
        offset = (((word>>10)&7)<<3)+(((word>>5)&3)<<6) if size==8 else (
            (((word>>6)&1)<<2)+(((word>>10)&7)<<3)+(((word>>5)&1)<<6))
    elif load:
        register = (word>>7)&31; base = 2
        if not floating and register==0: return None  # Reserved C.LWSP/C.LDSP.
        offset = (((word>>5)&3)<<3)+(((word>>12)&1)<<5)+(((word>>2)&7)<<6) if size==8 else (
            (((word>>4)&7)<<2)+(((word>>12)&1)<<5)+(((word>>2)&3)<<6))
    else:
        register = (word>>2)&31; base = 2
        offset = (((word>>10)&7)<<3)+(((word>>7)&7)<<6) if size==8 else (
            (((word>>9)&15)<<2)+(((word>>7)&3)<<6))
    mnemonic = {1:'FLD',2:'LW',3:'LD',5:'FSD',6:'SW',7:'SD'}[funct3]
    return dict(kind='read' if load else 'write',size=size,floating=floating,
                register=register,base_register=base,offset=offset,
                mnemonic='C.'+mnemonic+('SP' if quadrant==2 else ''))
