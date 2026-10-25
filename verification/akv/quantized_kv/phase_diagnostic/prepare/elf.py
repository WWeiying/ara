"""Bounded little-endian RV64 ELF section/symbol inspection, no ISA simulation."""
import struct


class Elf:
    def __init__(self, path):
        self.data = path.read_bytes()
        if self.data[:6] != b'\x7fELF\x02\x01':
            raise ValueError('Need ELF64 little endian')
        h = struct.unpack_from('<16sHHIQQQIHHHHHH', self.data)
        if h[2] != 243 or h[11] != 64 or not h[12]:
            raise ValueError('Need ordinary RV64 section table')
        self.sections = [struct.unpack_from('<IIQQQQIIQQ', self.data, h[6] + i*h[11])
                         for i in range(h[12])]
        names = self.section_bytes(h[13])
        self.names = [self.string(names, s[0]) for s in self.sections]
        self.symbols = {}
        for s in self.sections:
            if s[1] != 2:
                continue
            if s[9] != 24 or s[5] % 24:
                raise ValueError('Invalid symbol table')
            strings = self.section_bytes(s[6])
            for offset in range(s[4], s[4]+s[5], 24):
                name, info, other, index, address, size = struct.unpack_from('<IBBHQQ', self.data, offset)
                name = self.string(strings, name)
                if name and index and not name.startswith('$') and (info & 15) != 4:
                    row = dict(address=address, size=size, section=index, type=info & 15)
                    if name in self.symbols and self.symbols[name] != row:
                        raise ValueError('Ambiguous symbol: '+name)
                    self.symbols[name] = row

    @staticmethod
    def string(data, offset):
        return data[offset:data.index(b'\0', offset)].decode()

    def section_bytes(self, index):
        s = self.sections[index]
        if s[1] == 8:
            raise ValueError('NOBITS has no file payload')
        result = self.data[s[4]:s[4]+s[5]]
        if len(result) != s[5]:
            raise ValueError('Truncated section')
        return result

    def payload(self, name, size=None):
        row = self.symbols[name]
        s = self.sections[row['section']]
        if s[1] == 8:
            raise ValueError('NOBITS has no initialized payload')
        size = row['size'] if size is None else size
        offset = row['address']-s[3]
        if offset < 0 or size < 0 or offset+size > s[5]:
            raise ValueError('Symbol extent outside section')
        return self.section_bytes(row['section'])[offset:offset+size]

    def allocated(self):
        return [dict(name=n, address=s[3], bytes=s[5], nobits=s[1] == 8)
                for n,s in zip(self.names,self.sections) if s[2] & 2 and s[5]]
