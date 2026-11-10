"""Bounded ELF64 symbol/section reader for exact architectural trace binding."""
import struct


def contract(raw):
    def need(ok, text):
        if not ok:
            raise ValueError(text)
    need(len(raw) >= 64 and raw[:7] == b'\x7fELF\x02\x01\x01', 'Expected little-endian ELF64')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    need(h[1:4] == (2, 243, 1) and h[11] == 64 and h[6] + h[11] * h[12] <= len(raw), 'ELF bounds/type')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, h[6] + i * h[11]) for i in range(h[12])]
    symbols, words = {}, {}
    for sec in sections:
        if sec[2] & 4:
            need(sec[4] + sec[5] <= len(raw), 'Code section bounds')
            for offset in range(0, sec[5] - 3, 2):
                words[sec[3] + offset] = struct.unpack_from('<I', raw, sec[4] + offset)[0]
        if sec[1] != 2:
            continue
        need(sec[9] == 24 and sec[5] % 24 == 0 and sec[4] + sec[5] <= len(raw) and
             sec[6] < len(sections), 'Symbol table bounds')
        string = sections[sec[6]]
        need(string[1] == 3 and string[4] + string[5] <= len(raw), 'String table bounds')
        names = raw[string[4]:string[4] + string[5]]
        for offset in range(sec[4], sec[4] + sec[5], 24):
            n, info, _, index, value, size = struct.unpack_from('<IBBHQQ', raw, offset)
            end = names.find(b'\0', n)
            need(n < len(names) and end >= n, 'Symbol name bounds')
            name = names[n:end].decode('ascii')
            if info >> 4 != 1 or not name or index == 0:
                continue
            need(name not in symbols, 'Duplicate global symbol')
            symbols[name] = dict(address=value, size=size, type=info & 15)
    return dict(symbols=symbols, words=words)


def pc(c, name):
    return c['symbols'][name]['address']


def extent(c, name):
    s = c['symbols'][name]
    if s['type'] != 2 or s['size'] <= 0:
        raise ValueError('Missing function extent: ' + name)
    return s['address'], s['address'] + s['size']
