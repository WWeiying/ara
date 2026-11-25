"""Small ELF64 reader for exact retired-entry and instruction binding."""
import struct
from contract import require


def read(path):
    raw=path.read_bytes();require(raw[:7]==b'\x7fELF\x02\x01\x01','Expected ELF64 little endian')
    h=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
    require(h[1:4]==(2,243,1) and h[11]==64,'ELF target/section header')
    sections=[struct.unpack_from('<IIQQQQIIQQ',raw,h[6]+i*h[11]) for i in range(h[12])]
    symbols={}
    for s in sections:
        if s[1]!=2: continue
        strings=sections[s[6]];names=raw[strings[4]:strings[4]+strings[5]]
        for offset in range(s[4],s[4]+s[5],24):
            n,info,_,index,address,size=struct.unpack_from('<IBBHQQ',raw,offset)
            if not index or not n or info>>4!=1: continue
            name=names[n:names.index(0,n)].decode()
            symbols[name]=dict(address=address,size=size,type=info&15)
    def word(address):
        for s in sections:
            if s[1]!=8 and s[3]<=address and address+4<=s[3]+s[5]:
                return struct.unpack_from('<I',raw,s[4]+address-s[3])[0]
        raise ValueError('Unmapped ELF instruction')
    return symbols,word
