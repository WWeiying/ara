"""Independent Spike SoftFloat oracle; no arithmetic RTL equations are mirrored."""
import ctypes as C
from pathlib import Path

LIB = Path('/home/wangwy/software/toolchains/spike/lib/libsoftfloat.so')
FMT = {16: 2, 32: 0, 64: 1}
INTFMT = {8: 0, 16: 1, 32: 2, 64: 3}


class F16(C.Structure):
    _fields_ = [('v', C.c_uint16)]


class F32(C.Structure):
    _fields_ = [('v', C.c_uint32)]


class F64(C.Structure):
    _fields_ = [('v', C.c_uint64)]


TYPES = {16: F16, 32: F32, 64: F64}


class SoftFloat:
    def __init__(self, library=LIB):
        self.lib = C.CDLL(str(library))
        self.rm = C.c_uint8.in_dll(self.lib, 'softfloat_roundingMode')
        self.flags = C.c_uint8.in_dll(self.lib, 'softfloat_exceptionFlags')
        self.tiny = C.c_uint8.in_dll(self.lib, 'softfloat_detectTininess')

    def evaluate(self, op, src, dst, rm, a, b=0, c=0, unsigned=False):
        self.rm.value, self.flags.value, self.tiny.value = rm, 0, 1
        if op == 'i2f':
            name = f'{"ui" if unsigned else "i"}{src}_to_f{dst}'
            argtypes = [getattr(C, f'c_{"u" if unsigned else ""}int{src}')]
            args = [argtypes[0](a)]
            resulttype = TYPES[dst]
        elif op == 'f2i':
            name = f'f{src}_to_{"ui" if unsigned else "i"}{dst}'
            argtypes = [TYPES[src], C.c_uint8, C.c_bool]
            args = [TYPES[src](a), rm, True]
            # Spike extends SoftFloat with true saturating INT8/16 operations.
            resulttype = getattr(C, f'c_uint{dst}')
        elif op == 'cast':
            name = f'f{src}_to_f{dst}'
            argtypes, args, resulttype = [TYPES[src]], [TYPES[src](a)], TYPES[dst]
        else:
            suffix = {'fma': 'mulAdd', 'mul': 'mul', 'div': 'div', 'sqrt': 'sqrt'}[op]
            name = f'f{src}_{suffix}'
            n = 3 if op == 'fma' else (1 if op == 'sqrt' else 2)
            argtypes = [TYPES[src]] * n
            args, resulttype = [TYPES[src](v) for v in (a, b, c)[:n]], TYPES[dst]
        fn = getattr(self.lib, name)
        fn.argtypes, fn.restype = argtypes, resulttype
        result = fn(*args)
        raw = result if op == 'f2i' else result.v
        return raw & ((1 << dst) - 1), self.flags.value


def box(value, width):
    return value | (((1 << 64) - 1) ^ ((1 << width) - 1))


def cases(library=LIB):
    sf, rows = SoftFloat(library), []

    def add(group, op, src, dst, a, b=0, c=0, rm=0, unsigned=False, unit=None):
        result, flags = sf.evaluate(op, src, dst, rm, a, b, c, unsigned)
        units = [unit] if unit is not None else (
            [1, {16: 4, 32: 2, 64: 3}[dst]] if op in ('mul', 'fma') else
            [5] if op in ('div', 'sqrt') else [0])
        for u in units:
            if op == 'f2i':
                # Narrow vector conversion checks the architecturally packed bits.
                mask = (1 << dst) - 1
                expected = result
            else:
                mask = (1 << 64) - 1
                expected = box(result, dst)
            rows.append(dict(id=len(rows), group=group, unit=u, op=op,
                             src=src, dst=dst, rm=rm, unsigned=unsigned,
                             a=a if op == 'i2f' else box(a, src),
                             b=box(b, src), c=box(c, dst),
                             expected=expected, flags=flags, mask=mask))

    for rm in range(5):
        for signed in (False, True):
            for a in (65504, 65519, 65520, 65535, 65536, 131072):
                add('i2f_overflow', 'i2f', 32, 16, -a if signed else a, rm=rm)
        for dst in (16, 32, 64):
            for a in (0, 1, 16777217, -(1 << 31)):
                add('i2f_regression', 'i2f', 32, dst, a, rm=rm)
            for src in (32, 64):
                for a in (0, 1, 65536, (1 << (src-1)), (1 << src)-1):
                    add('i2f_unsigned', 'i2f', src, dst, a, rm=rm, unsigned=True)
        for a in (0x380fffffe0000000, 0x380fffffd0000002,
                  0x380fffffc0000000, 0x3810000000000000):
            for sign in (0, 1 << 63):
                add('cast_underflow', 'cast', 64, 32, a | sign, rm=rm)
        # Exhaust the small interval around the half min-normal boundary.
        for a in range(0x387fc000, 0x38800001, 0x400):
            add('cast_underflow', 'cast', 32, 16, a, rm=rm)
        for dst in (16, 32):
            for a in (0, 0x8000000000000000, 0x7ff0000000000000,
                      0xfff0000000000000, 0x7ff8000000000000, 0x7ff0000000000001):
                add('cast_special', 'cast', 64, dst, a, rm=rm)
        for width, m, e in ((16, 10, 5), (32, 23, 8), (64, 52, 11)):
            one = ((1 << (e - 1)) - 1) << m
            minimum = 1 << m
            for sign in (0, 1 << (width - 1)):
                for da in range(-2, 3):
                    for db in range(-2, 3):
                        a, b = (minimum + da) | sign, one + db
                        add('fma_underflow', 'mul', width, width, a, b, rm=rm)
                        add('fma_underflow', 'fma', width, width, a, b, 0, rm=rm)
                        add('div_underflow', 'div', width, width, a, b, rm=rm)
            inf = ((1 << e) - 1) << m
            signbit = 1 << (width - 1)
            # Nonzero addends exercise cancellation and sticky-before-add too.
            for a, b, c in ((minimum, one, signbit | 1),
                            (minimum - 1, one + 1, 1),
                            (minimum + 1, one - 1, signbit | 1),
                            (one, one, signbit | one),
                            (one + 1, one - 1, signbit | one),
                            (minimum, one - 1, 1),
                            (minimum | signbit, one - 1, signbit | 1),
                            # Exact value min-normal - 3/8 subnormal ULP:
                            # distinguishes transaction RM from poisoned live RM.
                            (3*(minimum >> 2), one - 1, minimum >> 2),
                            (inf, one, signbit | inf)):
                add('fma_addend', 'fma', width, width, a, b, c, rm=rm)
            for a, b in ((one, one), (one, one + (1 << m)), (0, 0),
                         (one, 0), (inf, one), (inf, inf), (inf + 1, one)):
                add('div_regression', 'div', width, width, a, b, rm=rm)
                add('fma_regression', 'mul', width, width, a, b, rm=rm)
            for a in (one, one + (1 << m), one + (2 << m), 0, inf):
                add('sqrt_regression', 'sqrt', width, width, a, rm=rm)
        for a in (0xd800, 0xd802, 0xd804, 0xd806, 0xdbfc, 0x8000, 0xfc00):
            for unsigned in (False, True):
                add('f2i_preserve', 'f2i', 16, 8, a, rm=rm, unsigned=unsigned)
        for a in (0xc3e0000000000000, 0xc3dfffffffffffff, 0xc3e0000000000001):
            add('f2i_preserve', 'f2i', 64, 64, a, rm=rm)
    return rows
