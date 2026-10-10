"""Independent native unpack + exact rational, separately rounded K2 QBS oracle."""
from fractions import Fraction
import struct
from build_gap38_i8_f16_lane3 import require

def half_to_single(bits):
    sign, exponent, fraction = (bits & 0x8000) << 16, (bits >> 10) & 31, bits & 1023
    if exponent == 31:
        return sign | 0x7f800000 | ((fraction << 13) | 0x400000 if fraction else 0)
    if exponent:
        return sign | ((exponent + 112) << 23) | (fraction << 13)
    if not fraction:
        return sign
    top = fraction.bit_length() - 1
    return sign | ((top + 103) << 23) | ((fraction - (1 << top)) << (23 - top))


def integer_single(value):
    if not value:
        return 0
    magnitude = abs(value); top = magnitude.bit_length() - 1
    require(top <= 23, 'Bounded exact integer conversion exceeded')
    return (0x80000000 if value < 0 else 0) | ((top + 127) << 23) | ((magnitude - (1 << top)) << (23 - top))


def binary_power(exponent):
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def finite_value(bits):
    require(type(bits) is int and 0 <= bits <= 0xffffffff, 'Malformed FP32 bits')
    exponent, mantissa = (bits >> 23) & 255, bits & 0x7fffff
    require(exponent != 255, 'Nonfinite value outside GAP109 oracle')
    significand = mantissa | (0x800000 if exponent else 0)
    value = significand * binary_power(exponent - 150 if exponent else -149)
    return -value if bits & 0x80000000 else value


def round_single(value):
    """Exact rational RNE with tininess after rounding; no host float."""
    require(isinstance(value, Fraction) and value.denominator & (value.denominator - 1) == 0,
            'Only exact binary rational arithmetic')
    sign = 0x80000000 if value < 0 else 0
    value = abs(value)
    if not value:
        return 0, 0
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if value < binary_power(exponent):
        exponent -= 1
    units = value / binary_power(max(-149, exponent - 23))
    floor = units.numerator // units.denominator
    remainder = units - floor
    rounded = floor + int(remainder > Fraction(1,2) or
                          (remainder == Fraction(1,2) and floor & 1))
    flags = int(bool(remainder))
    if exponent < -126:
        if rounded < 0x800000:
            return sign | rounded, flags | (2 if flags else 0)
        exponent = -126
    if rounded >= 0x1000000:
        rounded >>= 1
        exponent += 1
    if exponent > 127:
        return sign | 0x7f800000, 5
    return sign | ((exponent + 127) << 23) | (rounded & 0x7fffff), flags


def finite_fma(a, b, c):
    va, vb, vc = map(finite_value, (a,b,c))
    value = va * vb + vc
    if not value and (not va or not vb) and not vc:
        return (a ^ b) & c & 0x80000000, 0
    return round_single(value)


def fixtures(phase):
    require(type(phase) is int and phase in (0,1), 'Only two reviewed phases')
    block = (struct.pack('<HH',0x3c00,0)+bytes([1]*4+[0]*4+[1]*4)+
             bytes(32)+bytes([0x11]*128))
    scales = (0 if phase == 0 else 0x21800000, 0x3f800000)
    activation = b''.join(struct.pack('<I',scale)+bytes([1]*256)+
                          struct.pack('<16h',*([16]*16)) for scale in scales)
    return block*2, activation


def evaluate(w, a, phase):
    require(type(phase) is int and phase in (0,1), 'Only two reviewed phases')
    require(len(w)==352 and len(a)==584, 'Exactly two Q5_K/Q8_K blocks')
    acc, flags, bits, stages_flags = 0, 0, [], []
    for block in (0,1):
        wb, ab = w[block*176:(block+1)*176], a[block*292:(block+1)*292]
        dot, correction = 0, 0
        for group in range(8):
            meta = wb[4:16]
            scale = meta[group]&63 if group<4 else (meta[group+4]&15)|((meta[group-4]>>6)<<4)
            minimum = meta[group+4]&63 if group<4 else (meta[group+4]>>4)|((meta[group]>>6)<<4)
            qs = [((wb[48+group//2*32+i]>>(4*(group%2)))&15)|
                  (((wb[16+i]>>group)&1)<<4) for i in range(32)]
            av = list(struct.unpack('<32b',ab[4+group*32:4+(group+1)*32]))
            require([sum(av[:16]),sum(av[16:])]==list(struct.unpack('<2h',ab[260+group*4:264+group*4])),
                    'Individual Q8_K bsums differ')
            dot += scale*sum(q*v for q,v in zip(qs,av))
            correction += minimum*sum(av)
        require(dot==256 and correction==0, 'Bounded independent integer MAC differs')
        d,dmin = map(half_to_single,struct.unpack('<HH',wb[:4]))
        ad = struct.unpack('<I',ab[:4])[0]
        block_bits = [integer_single(dot),integer_single(correction)]
        block_flags = [0,0]
        for operands in ((d,ad,0x80000000),(dmin,ad,0x80000000)):
            value, f = finite_fma(*operands);block_bits.append(value);block_flags.append(f)
        value,f = finite_fma(block_bits[2],block_bits[0],acc)
        block_bits.append(value);block_flags.append(f)
        acc,f = finite_fma(block_bits[3]^0x80000000,block_bits[1],value)
        block_bits.append(acc);block_flags.append(f)
        bits.extend(block_bits);stages_flags.extend(block_flags)
        for f in block_flags:flags |= f
    return dict(phase=phase,scope='bounded-native-IEEE-host-only',dot=256,correction=0,
                bits=acc,flags=flags,csr_flags=8|flags,stage_bits=bits,stage_flags=stages_flags)


def oracle_expected(phase):
    return evaluate(*fixtures(phase),phase)


def oracle_check(row, phase):
    require(row==oracle_expected(phase), 'Independent per-stage integer/RNE oracle differs')
    flags = 0
    for f in row['stage_flags']:flags |= f
    require(flags==row['flags'] and 8|flags==row['csr_flags'], 'Flags must accumulate by OR')

