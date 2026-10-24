"""Narrow machine-word mapper plus exact RNE integer arithmetic, not an ISA simulator."""
import ctypes
import struct

SYMBOL = 'akv_experimental_pv_f32_pair'
SIGN, INF, NAN = 0x80000000, 0x7f800000, 0x7fc00000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def words_from_elf(path):
    data = path.read_bytes()
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    require(data[:6] == b'\x7fELF\x02\x01' and header[2] == 243, 'Not LE ELF64 RISC-V')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, header[6]+i*header[11]) for i in range(header[12])]
    found = []
    for section in sections:
        if section[1] != 2:
            continue
        strings = sections[section[6]]
        names = data[strings[4]:strings[4]+strings[5]]
        for offset in range(section[4], section[4]+section[5], section[9]):
            name, info, _other, index, address, size = struct.unpack_from('<IBBHQQ', data, offset)
            if names[name:].split(b'\0', 1)[0].decode() != SYMBOL:
                continue
            require(info & 15 == 2 and size > 0 and size % 4 == 0, 'Function symbol/extent')
            text = sections[index]
            begin = text[4]+address-text[3]
            require(begin >= text[4] and begin+size <= text[4]+text[5], 'Function outside section')
            found.append(list(struct.unpack_from('<'+'I'*(size//4), data, begin)))
    require(len(found) == 1, 'Missing/duplicate candidate function')
    require(all(w & 3 == 3 for w in found[0]), 'Unexpected compressed instruction')
    return found[0]


def finite_parts(bits):
    exponent, fraction = (bits >> 23) & 255, bits & 0x7fffff
    return ((-1 if bits & SIGN else 1) * ((1 << 23) | fraction) if exponent else
            (-fraction if bits & SIGN else fraction)), exponent-150 if exponent else -149


def rounded(integer, exponent, zero_sign=0):
    if integer == 0:
        return zero_sign, 0
    sign, magnitude = (SIGN if integer < 0 else 0), abs(integer)
    unit = max(magnitude.bit_length()-1+exponent-23, -149)
    shift = unit-exponent
    if shift > 0:
        quotient, remainder = divmod(magnitude, 1 << shift)
        quotient += int(remainder > (1 << (shift-1)) or
                        (remainder == (1 << (shift-1)) and quotient & 1))
    else:
        quotient, remainder = magnitude << -shift, 0
    if quotient >= 1 << 24:
        quotient >>= 1
        unit += 1
    if quotient >= 1 << 23:
        exp_field = unit+150
        if exp_field >= 255:
            return sign | INF, 5  # OF | NX
        return sign | (exp_field << 23) | (quotient & 0x7fffff), int(bool(remainder))
    return sign | quotient, 3 if remainder else 0  # tininess after rounding


def arithmetic(a, b, c=None):
    operands = [a, b] + ([] if c is None else [c])
    nan = any(x & 0x7fffffff > INF for x in operands)
    signaling = any(x & 0x7fffffff > INF and not x & 0x400000 for x in operands)
    product_sign = (a ^ b) & SIGN
    invalid_product = ((a & 0x7fffffff == INF and b & 0x7fffffff == 0) or
                       (b & 0x7fffffff == INF and a & 0x7fffffff == 0))
    if nan or invalid_product:
        return NAN, 16 if signaling or invalid_product else 0
    if a & 0x7fffffff == INF or b & 0x7fffffff == INF:
        if c is not None and c & 0x7fffffff == INF and c & SIGN != product_sign:
            return NAN, 16
        return product_sign | INF, 0
    if c is not None and c & 0x7fffffff == INF:
        return c, 0
    ma, ea = finite_parts(a)
    mb, eb = finite_parts(b)
    product, exponent = ma*mb, ea+eb
    if c is None:
        return rounded(product, exponent, product_sign)
    mc, ec = finite_parts(c)
    unit = min(exponent, ec)
    exact = (product << (exponent-unit)) + (mc << (ec-unit))
    zero_sign = product_sign if product == mc == 0 and product_sign == c & SIGN else 0
    return rounded(exact, unit, zero_sign)


def half_to_single(bits):
    exponent, fraction = (bits >> 10) & 31, bits & 1023
    require(exponent != 31, 'Fixture V must be finite F16')
    value = ((1024+fraction) if exponent else fraction) * (-1 if bits & 0x8000 else 1)
    result, flags = rounded(value, exponent-25 if exponent else -24, SIGN if bits & 0x8000 else 0)
    require(flags == 0, 'Finite half extension not exact')
    return result


def fixture(dim, tokens, profile):
    # Asymmetric heads/dimensions expose swapped rows, wrong D stride and rounding.
    values = [0x3c00, 0xbc00, 0x3555, 0xb801, 0x0001, 0x8000, 0x7bff, 0x0401]
    scores = [0x3eaaaaab, 0xbe800001, 0x3f000001, 0x33800000, 0xbf123456, 0x00800001]
    initials = [0x3f800001, 0xbf800002, 0x00800001, 0x00000001, 0x80000000, 0x4b000001]
    scales = [0x3f000001, 0x3f7fffff]
    if profile == 'exact':
        scores = [0x3f800000, 0xbf800000, 0x40000000]
        initials = [0x3f800000, 0xc0000000, 0]
        values = [0x3c00, 0xbc00, 0x4000, 0]
        scales = [0x40000000, 0x3f800000]
    elif profile == 'range':
        initials = [0x7f7fffff, 0xff7fffff, 1, 0x80000001, 0x00800001, 0x80000000]
        scales = [0x40000000, 0x3f000000]
        scores = [0, 0x80000000, 1, 0x80000001]
    elif profile == 'invalid':
        initials = [INF, SIGN | INF, 0, SIGN, NAN, 0x7f800001]
        scales = [0, 0x3f800000]
        scores = [INF, SIGN | INF, 0x3f800000]
        values = [0, 0x3c00, 0xbc00]
    score = [scores[(h*3+t*5) % len(scores)] for h in range(2) for t in range(64)]
    initial = [initials[(h*7+d*5) % len(initials)] for h in range(2) for d in range(dim)]
    value = [values[(t*3+d*5) % len(values)] for t in range(tokens) for d in range(dim)]
    return score, initial, scales, value


def scalar_oracle(library, inputs, dim, tokens):
    score, initial, scales, value = inputs
    arrays = [(ctypes.c_uint32*len(a))(*a) for a in (score, initial, scales)]
    values = (ctypes.c_uint16*len(value))(*value)
    output = (ctypes.c_uint32*(2*dim))()
    flags = library.f32_pv_oracle(*arrays, values, dim, tokens, output)
    require(0 <= flags <= 31, 'Host oracle environment/shape failure')
    return list(output), flags


def sext(value, bits):
    return value-(1 << bits) if value & (1 << (bits-1)) else value


def execute(code, dim, tokens, inputs, initial_flags=0):
    score, initial, scales, value = inputs
    g = [0]*32
    g[10:15] = [0x10000, 0x20000, 0x30000, tokens, dim]
    fp, tags = {}, {}
    vrf = bytearray(b'\xcc'*4096)
    output = bytearray(b'\xa5'*64 + struct.pack('<'+'I'*len(initial), *initial) + b'\xa5'*64)
    events, loads, converts, stores, scaled, initialized, fp_reads = [], [], [], [], [], [], []
    pc, sew, lmul, vl, flags = 0, 0, 0, 0, initial_flags
    v_token = converted_token = None

    def put(reg, d, number, fmt='I'):
        struct.pack_into('<'+fmt, vrf, reg*128+d*struct.calcsize(fmt), number)

    def get(reg, d, fmt='I'):
        return struct.unpack_from('<'+fmt, vrf, reg*128+d*struct.calcsize(fmt))[0]

    def write(reg, number):
        require(reg in (5, 6, 7, *range(10, 18), 28, 29, 30, 31), 'Callee-saved/zero/ra write')
        g[reg] = number

    for _step in range(3000):
        require(pc % 4 == 0 and 0 <= pc//4 < len(code), 'Control flow outside function')
        w = code[pc//4]
        op, rd, f3, rs1, rs2 = w & 127, (w >> 7) & 31, (w >> 12) & 7, (w >> 15) & 31, (w >> 20) & 31
        nxt = pc+4
        if op == 0x13:
            imm = sext(w >> 20, 12)
            if f3 == 0:
                write(rd, g[rs1]+imm)
            elif f3 == 1 and w >> 26 == 0:
                write(rd, g[rs1] << ((w >> 20) & 63))
            elif f3 == 6:
                write(rd, g[rs1] | imm)
            else:
                raise ValueError('Unsupported integer immediate')
        elif op == 0x33 and f3 == 0 and w >> 25 == 0:
            write(rd, g[rs1]+g[rs2])
        elif op == 0x63 and f3 in (0, 6):
            offset = sext(((w >> 31) << 12) | (((w >> 7) & 1) << 11) |
                (((w >> 25) & 63) << 5) | (((w >> 8) & 15) << 1), 13)
            take = g[rs1] == g[rs2] if f3 == 0 else g[rs1] < g[rs2]
            if take:
                nxt = pc+offset
        elif op == 0x6f and rd == 0:
            offset = sext(((w >> 31) << 20) | (((w >> 12) & 255) << 12) |
                (((w >> 20) & 1) << 11) | (((w >> 21) & 1023) << 1), 21)
            nxt = pc+offset
        elif w == 0x00008067:
            require(pc == 4*(len(code)-1), 'Early return')
            break
        elif op == 0x07 and f3 == 2:
            address = g[rs1]+sext(w >> 20, 12)
            require(rd in (0, 1), 'Unexpected scalar FP destination')
            if 0x30000 <= address < 0x30008 and address % 4 == 0:
                h = (address-0x30000)//4
                fp[rd], tags[rd] = scales[h], ('scale', h)
            else:
                h, offset = divmod(address-0x10000, 256)
                require(h in (0, 1) and offset % 4 == 0 and 0 <= offset//4 < tokens, 'Score stride/active extent')
                fp[rd], tags[rd] = score[h*64+offset//4], ('score', h, offset//4)
            fp_reads.append(tags[rd])
        elif op in (0x07, 0x27) and f3 == 6:
            require(w >> 20 == 0x20 and (sew, lmul, vl) == (32, 4, dim), 'Vector memory mode/width')
            require(rd in (0, 4) and g[rs1]-0x20000 == rd//4*dim*4, 'Output stride4*D/register mapping')
            h = rd//4
            if op == 0x07:
                initialized.append(h)
                for d in range(dim):
                    put(rd, d, initial[h*dim+d])
            else:
                stores.append(h)
                output[64+h*dim*4:64+(h+1)*dim*4] = vrf[rd*128:rd*128+dim*4]
        elif op == 0x5b:
            require(scaled == [0, 1], 'Replay before both initial scales')
            require((rd, rs1, rs2, f3, w >> 25) == (8, 10, 0, 3, {64: 0, 96: 2, 128: 1}[dim]), 'AKV encoding/D/group')
            require((sew, lmul, vl) == (16, 2, dim) and g[10] & 3 == 2, 'V selector/VL')
            v_token = g[10] >> 2
            require(0 <= v_token < tokens, 'Replay token extent')
            loads.append(v_token)
            for d in range(dim):
                put(8, d, value[v_token*dim+d], 'H')
        elif op == 0x57 and f3 == 7:
            require(rd == 0 and w >> 31 == 0 and (w >> 20) in (0xd2, 0xc9), 'Unsupported vtype/policy')
            sew, lmul = (32, 4) if w >> 20 == 0xd2 else (16, 2)
            vl = min(g[rs1], 1024*lmul//sew)
            require(vl == dim, 'VL truncation/D mismatch')
        elif op == 0x57 and f3 == 1 and w >> 26 == 0x12:
            require((rd, rs1, rs2, (w >> 25) & 1) == (12, 12, 8, 1) and
                    (sew, lmul, vl) == (16, 2, dim) and v_token is not None, 'F16->F32 widening geometry')
            converted_token = v_token
            converts.append(v_token)
            for d in range(dim):
                put(12, d, half_to_single(get(8, d, 'H')))
        elif op == 0x57 and f3 == 5 and w >> 26 in (0x24, 0x2c):
            require(rd in (0, 4) and (w >> 25) & 1 and (sew, lmul, vl) == (32, 4, dim), 'FP32 accumulator geometry')
            h = rd//4
            if w >> 26 == 0x24:
                require(rs2 == rd and tags[rs1] == ('scale', h), 'Scale head/order')
                scaled.append(h)
                for d in range(dim):
                    bits, raised = arithmetic(get(rs2, d), fp[rs1])
                    put(rd, d, bits)
                    flags |= raised
            else:
                require(scaled == [0, 1], 'FMA before both initial scales')
                require(rs2 == 12 and tags[rs1] == ('score', h, converted_token), 'FMA head/token mapping')
                events.append((converted_token, h))
                for d in range(dim):
                    bits, raised = arithmetic(fp[rs1], get(12, d), get(rd, d))
                    put(rd, d, bits)
                    flags |= raised
        else:
            raise ValueError(f'Unsupported machine word {w:08x} at {pc:x}')
        pc = nxt
    else:
        raise ValueError('Instruction step bound')
    require(initialized == scaled == stores == [0, 1], 'Exact two real heads load/scale/store')
    require(events == [(t, h) for t in range(tokens) for h in (0, 1)], 'Exact token FMA order/count')
    require(loads == converts == list(range(tokens)), 'Exactly one V replay/widen per token')
    require(fp_reads == [('scale', h) for h in (0, 1)] +
            [('score', h, t) for t in range(tokens) for h in (0, 1)], 'Scalar input load order/count')
    require(output[:64] == output[-64:] == b'\xa5'*64, 'Output guard corruption')
    return list(struct.unpack_from('<'+'I'*(2*dim), output, 64)), flags


def check(elf, oracle_path):
    code = words_from_elf(elf)
    library = ctypes.CDLL(str(oracle_path))
    p32, p16 = ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint16)
    library.f32_pv_oracle.argtypes = [p32, p32, p32, p16, ctypes.c_uint, ctypes.c_uint, p32]
    library.f32_pv_oracle.restype = ctypes.c_int
    # Directed independent expected values: fused cancellation, gradual underflow,
    # after-rounding tininess, overflow, invalid and signed zero.
    for args, expected in [((0x3f800001, 0x3f7ffffe, 0xbf800000), (0xa8800000, 0)),
        ((1, 0x3f000000), (0, 3)), ((0x00800000, 0x3f7fffff), (0x00800000, 1)),
        ((0x7f7fffff, 0x40000000), (INF, 5)), ((INF, 0), (NAN, 16)),
        ((SIGN, 0x3f800000, SIGN), (SIGN, 0))]:
        require(arithmetic(*args) == expected, 'Exact arithmetic directed check')
    count, sticky_count, flag_union = 0, 0, 0
    for dim in (64, 96, 128):
        for tokens in range(1, 65):
            profiles = ['rounding'] + (['exact', 'range', 'invalid'] if tokens in (1, 2, 17, 64) else [])
            for profile in profiles:
                data = fixture(dim, tokens, profile)
                expected, expected_flags = scalar_oracle(library, data, dim, tokens)
                actual, flags = execute(code, dim, tokens, data)
                require(actual == expected and flags == expected_flags,
                        f'Independent scalar IEEE oracle mismatch D{dim} T{tokens} {profile}: flags {flags}/{expected_flags}')
                if tokens == 17 and profile == 'rounding':
                    for initial_flags in (1, 8, 16, 31):
                        sticky_result, sticky_flags = execute(code, dim, tokens, data, initial_flags)
                        require(sticky_result == expected and sticky_flags == (expected_flags | initial_flags),
                                'Sticky flags/input state mismatch')
                        sticky_count += 1
                flag_union |= expected_flags
                count += 1
    require(flag_union == 23, 'Fixtures did not cover NV/OF/UF/NX')
    mutations = []
    def mutate(name, predicate, change, dim=128):
        indices = [i for i, w in enumerate(code) if predicate(w)]
        require(bool(indices), 'Missing mutation target '+name)
        bad = list(code)
        bad[indices[0]] = change(bad[indices[0]])
        mutations.append((name, bad, dim))
    mutate('D saved from wrong arg', lambda w: w == 0x00070f13, lambda w: w ^ (1 << 15))
    mutate('fixed512 output stride', lambda w: (w & 0xfffff) == 0xf1713,
           lambda w: (512 << 20) | (14 << 7) | 0x13, 64)
    mutate('score stride128', lambda w: w & 0x7f == 7 and w >> 20 == 256,
           lambda w: (w & 0xfffff) | (128 << 20))
    mutate('wrong scale head', lambda w: w & 0x7f == 7 and (w >> 12) & 7 == 2 and w >> 20 == 4,
           lambda w: w & 0xfffff)
    mutate('FMA head alias', lambda w: w >> 26 == 0x2c and (w >> 7) & 31 == 4,
           lambda w: w & ~(31 << 7))
    mutate('FMA source alias', lambda w: w >> 26 == 0x2c, lambda w: (w & ~(31 << 20)) | (8 << 20))
    mutate('narrowing instead of widening', lambda w: w >> 26 == 0x12,
           lambda w: (w & ~(31 << 15)) | (20 << 15))
    mutate('V accumulator overlap', lambda w: w & 127 == 0x5b, lambda w: w & ~(31 << 7))
    mutate('wrong D selector', lambda w: w == 0x0205345b, lambda w: w ^ (1 << 25))
    mutate('output head0 overwrite', lambda w: w & 127 == 0x27 and (w >> 7) & 31 == 4,
           lambda w: w & ~(31 << 7))
    mutate('skip tokens', lambda w: w == 0x001e8e93, lambda w: w ^ (3 << 20))
    mutate('VL m2 accumulator', lambda w: w & 127 == 0x57 and w >> 20 == 0xd2,
           lambda w: w ^ (3 << 20))
    # Swap the actual FMA words: same aggregate arithmetic, wrong pair order.
    bad = list(code)
    fmas = [i for i, w in enumerate(code) if w >> 26 == 0x2c]
    require(len(fmas) == 2, 'FMA instruction extent')
    bad[fmas[0]], bad[fmas[1]] = bad[fmas[1]], bad[fmas[0]]
    mutations.append(('reversed FMA pair order', bad, 128))
    for name, bad, dim in mutations:
        try:
            execute(bad, dim, 17, fixture(dim, 17, 'rounding'))
        except (ValueError, KeyError):
            continue
        raise ValueError('Mutation accepted: '+name)
    return dict(state='HOST_OBJECT_MAPPING_PASS', mapped_cases=count, sticky_cases=sticky_count, exhaustive_shapes=192,
        profiles=['rounding', 'exact', 'range', 'invalid'], rejected_mutations=[m[0] for m in mutations],
        scalar_oracle='Independent host C head-major fmaf/fenv; exact integer RNE mapper',
        covered_fflags=flag_union, machine_words=len(code), vlen_bits=1024,
        native_execution=False, rtl_acceptance=False,
        limits='Finite F16 V; RNE; NaN outputs canonicalized for host comparison. No actual CSR, trap, timing or odd-caller proof.')
