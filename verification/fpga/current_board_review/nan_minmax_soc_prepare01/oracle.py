"""Independent FP32 bitwise maximum oracle; no fixture/Spike result input."""

def classify(bits):
    exponent = (bits >> 23) & 255
    fraction = bits & 0x7fffff
    return exponent == 255 and fraction != 0, exponent == 255 and fraction != 0 and not (fraction & 0x400000)


def maximum(a, b):
    an, asn = classify(a)
    bn, bsn = classify(b)
    flags = 16 if asn or bsn else 0
    if an and bn:
        return 0x7fc00000, flags
    if an:
        return b, flags
    if bn:
        return a, flags
    if (a & 0x7fffffff) == 0 and (b & 0x7fffffff) == 0:
        return (a & b), flags
    # IEEE magnitude order, with reversed magnitude for negative operands.
    key = lambda x: (~x & 0xffffffff) if x & 0x80000000 else x | 0x80000000
    return (a if key(a) >= key(b) else b), flags


def bitwise_oracle(seed, values, mask_byte):
    accumulator, flags = seed, 0
    for index, value in enumerate(values):
        if mask_byte & (1 << (index % 8)):
            accumulator, new_flags = maximum(accumulator, value)
            flags |= new_flags
    return accumulator, flags
