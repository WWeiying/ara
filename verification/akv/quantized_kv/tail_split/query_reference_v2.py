"""Exact rational RNE reference, restricted to finite normal captured Q8_0 rows.

Not a general quantizer, exception-flag oracle, or alternative production kernel.
"""
from fractions import Fraction
import hashlib
import math
import struct


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def nearest(value):
    sign = -1 if value < 0 else 1
    value = abs(value)
    whole, remainder = divmod(value.numerator, value.denominator)
    twice = 2 * remainder
    return sign * (whole + int(twice > value.denominator or
                               (twice == value.denominator and whole % 2)))


def power2(exponent):
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def normal_rne(value, precision=24, minimum=-126, maximum=127):
    if not value:
        return Fraction(0)
    magnitude = abs(value)
    exponent = magnitude.numerator.bit_length() - magnitude.denominator.bit_length()
    if magnitude < power2(exponent):
        exponent -= 1
    require(minimum <= exponent <= maximum, 'Outside finite-normal reference domain')
    units = nearest(magnitude / power2(exponent - precision + 1))
    if units == 1 << precision:
        units >>= 1
        exponent += 1
    require(exponent <= maximum, 'Reference rounding overflow')
    return (-1 if value < 0 else 1) * units * power2(exponent - precision + 1)


def reconstruct(capture):
    require(len(capture) == 6144, 'Expected complete 12-head F32 Query capture')
    values = struct.unpack('<1536f', capture)
    require(all(math.isfinite(x) and (x == 0 or abs(x) >= 2.0**-126) for x in values),
            'Nonfinite/subnormal captured input outside reference scope')
    result = bytearray()
    for offset in range(0, 768, 32):
        block = [Fraction(x) for x in values[offset:offset + 32]]
        scale = normal_rne(max(map(abs, block)) / 127)
        require(scale > 0, 'All-zero block outside current fixture scope')
        inverse = normal_rne(1 / scale)
        half = normal_rne(scale, 11, -14, 15)
        integers = [nearest(normal_rne(x * inverse)) for x in block]
        require(all(-127 <= x <= 127 for x in integers), 'Unexpected integer narrowing')
        result.extend(struct.pack('<e', float(half)))
        result.extend(struct.pack('<32b', *integers))
    require(len(result) == 816, 'Wrong six-head quantized extent')
    return bytes(result)


def elf_query(data):
    """Read one exact-size symbol from a checked ELF64 little-endian RISC-V file."""
    def unpack(fmt, offset):
        require(offset >= 0 and offset + struct.calcsize(fmt) <= len(data), 'Truncated ELF')
        return struct.unpack_from(fmt, data, offset)

    header = unpack('<16sHHIQQQIHHHHHH', 0)
    require(header[0][:6] == b'\x7fELF\x02\x01' and header[2] == 243 and
            header[11] == 64 and 0 < header[12] < 65535, 'Unsupported ELF header')
    sections = [unpack('<IIQQQQIIQQ', header[6] + i * header[11]) for i in range(header[12])]

    def payload(section):
        require(section[4] + section[5] <= len(data), 'Truncated ELF section')
        return data[section[4]:section[4] + section[5]]

    matches = []
    for table in sections:
        if table[1] != 2:
            continue
        require(table[9] == 24 and table[5] % 24 == 0 and table[6] < len(sections),
                'Malformed symbol table')
        payload(table)
        names = payload(sections[table[6]])
        for offset in range(table[4], table[4] + table[5], 24):
            name, _info, _other, index, address, size = unpack('<IBBHQQ', offset)
            require(name < len(names), 'Symbol name outside string table')
            if names[name:].split(b'\0', 1)[0] != b'attention_query':
                continue
            require(0 < index < len(sections) and size in (0, 6144), 'Unexpected Query symbol')
            section = sections[index]
            position = address - section[3]
            require(section[1] == 1 and section[2] & 2 and not section[2] & 1 and
                    position >= 0 and position + 6144 <= section[5], 'Query outside read-only PROGBITS')
            matches.append(payload(section)[position:position + 6144])
    require(len(matches) == 1, 'Missing/duplicate Query symbol')
    return matches[0]
