"""Strict RV64 integer C memory decoding; no global checker patching."""


def decode(instruction):
    if type(instruction) is not int or not 0 <= instruction <= 0xffffffff:
        raise ValueError('Invalid instruction word')
    if instruction & 3 == 3:
        return None
    if instruction > 0xffff:
        raise ValueError('Nonzero upper compressed instruction bits')
    q, f = instruction & 3, instruction >> 13
    if q not in (0,2) or f not in (2,3,6,7):
        return None
    write, size = f >= 6, 4 if f in (2,6) else 8
    if q == 0:
        base = 8+((instruction>>7)&7)
        register = 8+((instruction>>2)&7)
        # Frozen CVA6 C0Lw/Sw and RV64 C0Ld/Sd immediate wiring.
        offset = (((instruction>>10)&7)<<3)
        if size == 4:
            offset |= ((instruction>>5)&1)<<6 | ((instruction>>6)&1)<<2
        else:
            offset |= ((instruction>>5)&3)<<6
    else:
        base = 2
        register = ((instruction>>2)&31) if write else ((instruction>>7)&31)
        if not write and register == 0:
            raise ValueError('Reserved C.LWSP/C.LDSP rd=x0')
        if write:
            offset = (((instruction>>9)&15)<<2 | ((instruction>>7)&3)<<6) if size == 4 else \
                     (((instruction>>10)&7)<<3 | ((instruction>>7)&7)<<6)
        else:
            offset = ((instruction>>12)&1)<<5
            offset |= (((instruction>>4)&7)<<2 | ((instruction>>2)&3)<<6) if size == 4 else \
                      (((instruction>>5)&3)<<3 | ((instruction>>2)&7)<<6)
    funct3 = 2 if size == 4 else 3
    if write:
        expanded = ((offset>>5)<<25)|(register<<20)|(base<<15)|(funct3<<12)|((offset&31)<<7)|0x23
    else:
        expanded = (offset<<20)|(base<<15)|(funct3<<12)|(register<<7)|0x03
    return dict(kind='write' if write else 'read',size=size,base=base,register=register,
                offset=offset,expanded=expanded,
                mnemonic='C.'+('S' if write else 'L')+('W' if size == 4 else 'D')+('SP' if q == 2 else ''))
