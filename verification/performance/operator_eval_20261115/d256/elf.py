"""ELF function/word reader including local noinline SDK schedule functions."""
import struct
from contract import require


def read(path):
    raw=path.read_bytes();require(raw[:7]==b'\x7fELF\x02\x01\x01','ELF64 little endian required')
    h=struct.unpack_from('<16sHHIQQQIHHHHHH',raw);require(h[1:4]==(2,243,1),'RISC-V executable required')
    sections=[struct.unpack_from('<IIQQQQIIQQ',raw,h[6]+i*h[11]) for i in range(h[12])]
    symbols={}
    for s in sections:
        if s[1]!=2:continue
        t=sections[s[6]];names=raw[t[4]:t[4]+t[5]]
        for offset in range(s[4],s[4]+s[5],24):
            n,info,_,index,address,size=struct.unpack_from('<IBBHQQ',raw,offset)
            if index and n and info&15==2:
                name=names[n:names.index(0,n)].decode();require(name not in symbols,'Duplicate ELF function')
                symbols[name]=dict(address=address,size=size)
    def memory(address,size):
        for s in sections:
            if s[1]!=8 and s[3]<=address and address+size<=s[3]+s[5]:
                return raw[s[4]+address-s[3]:s[4]+address-s[3]+size]
        raise ValueError('Unmapped ELF address')
    return symbols,memory
