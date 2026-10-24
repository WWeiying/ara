"""Bounded object mapping and exact-small-matrix check, NOT native FP validation."""
import re
import struct

QK = 'akv_experimental_qk_f16_pair_panel4'
PV = 'akv_experimental_pv_f16_pair'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def instructions(text, symbol):
    result, active = {}, False
    for line in text.splitlines():
        label = re.fullmatch(r'([0-9a-f]+) <([^>]+)>:', line.strip())
        if label:
            if active:
                break
            active = label[2] == symbol
        elif active:
            m = re.fullmatch(r'\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([.\w]+)\s*(.*?)\s*', line)
            if m:
                result[int(m[1], 16)] = (int(m[2], 16), m[3], m[4].split('#', 1)[0].strip())
    require(bool(result), 'Missing symbol '+symbol)
    return result


def query(h, d):
    return (h*3+d*2) % 5 - 2


def key(t, d):
    return (t*2+d*3) % 7 - 3


def probability(h, t):
    return (h+t) % 3 - 1


def value(t, d):
    return (t*2+d*3) % 5 - 2


def initial(h, d):
    return (h*7+d) % 5 - 2


def execute(code, dim, tokens, stride, pv=False):
    g = dict(zero=0, a0=0x20000 if pv else 0x10000,
             a1=0x30000 if pv else 0x20000, a2=0x40000 if pv else tokens,
             a3=tokens if pv else stride, a4=dim)
    fp, tags, columns = {}, {}, {}
    vrf = bytearray(b'\xcc' * 4096)
    result = bytearray(b'\xa5' * (64 + (1024 if pv else 512) + 64))
    reference = bytearray(result)
    if pv:
        for h in range(2):
            for d in range(dim):
                struct.pack_into('<e', result, 64+h*512+2*d, initial(h, d))
        reference[:] = result
    events, loads, stores, converts, scales, initializes = [], [], [], [], [], []
    pcs = sorted(code)
    successor = dict(zip(pcs, pcs[1:]))
    pc, sew, lmul, vl = pcs[0], 0, 0, 0

    def integer(s):
        if s in g:
            return g[s]
        return int(s, 0)

    def address(s):
        m = re.fullmatch(r'(-?\d*)\((\w+)\)', s)
        require(m is not None, 'Memory operand')
        return integer(m[2])+int(m[1] or '0')

    def put(reg, index, number, fmt):
        struct.pack_into('<'+fmt, vrf, reg*128+index*struct.calcsize(fmt), number)

    def get(reg, index, fmt):
        return struct.unpack_from('<'+fmt, vrf, reg*128+index*struct.calcsize(fmt))[0]

    for _step in range(10000):
        require(pc in code, 'Invalid control flow')
        word, op, args = code[pc]
        f = [x.strip() for x in args.split(',')]
        nxt = successor.get(pc)
        if word & 127 == 0x5b:
            rd, rs1, rs2, f3, f7 = ((word >> 7)&31, (word >> 15)&31,
                                    (word >> 20)&31, (word >> 12)&7, word >> 25)
            require((rd, rs1, rs2) == (8, 10, 0), 'Custom register/operand encoding')
            if not pv:
                d = g['a0']
                require((f3, f7, sew, lmul, vl) == (7, 1, 16, 1, tokens) and
                        d % 4 == 0 and 0 <= d <= dim-4, 'PANEL4 shape/encoding')
                loads.append(d)
                for offset in range(4):
                    columns[8+offset] = d+offset
                    for t in range(tokens):
                        put(8+offset, t, key(t, d+offset), 'e')
            else:
                t = g['a0'] >> 2
                require((f3, f7, sew, lmul, vl) == (3, {64: 0, 96: 2, 128: 1}[dim], 16, 2, dim)
                        and g['a0'] & 3 == 2 and 0 <= t < tokens, 'V row shape/encoding')
                loads.append(t)
                columns[8] = t
                for d in range(dim):
                    put(8, d, value(t, d), 'e')
        elif op in ('mv', 'li', 'add', 'addi', 'slli', 'ori'):
            require(re.fullmatch(r'[at][0-6]|a7', f[0]) is not None, 'Non-caller-saved GPR write')
            if op in ('mv', 'li'):
                g[f[0]] = integer(f[1])
            elif op in ('add', 'addi'):
                g[f[0]] = integer(f[1])+integer(f[2])
            elif op == 'slli':
                g[f[0]] = integer(f[1]) << integer(f[2])
            else:
                g[f[0]] = integer(f[1]) | integer(f[2])
        elif op == 'vsetvli':
            require(f[0] == 'zero' and f[4:] == ['ta', 'ma'], 'vset operands')
            sew, lmul = int(f[2][1:]), int(f[3][1:])
            want = dim if pv else tokens
            vl = min(integer(f[1]), 1024*lmul//sew)
            require(vl == want and ((sew, lmul) == (16, 2) if pv else
                    (sew, lmul) in ((32, 2), (16, 1))), 'VL truncation/geometry')
        elif op == 'vmv.v.i':
            reg = int(f[0][1:])
            require(not pv and reg in (0, 2) and f[1] == '0' and (sew, lmul) == (32, 2), 'Init')
            initializes.append(reg//2)
            for t in range(tokens):
                put(reg, t, 0, 'f')
        elif op == 'flh':
            a = address(f[1])-0x10000
            h, offset = divmod(a, stride)
            require(not pv and h in (0, 1) and offset % 2 == 0 and offset//2 < dim, 'Query stride/bounds')
            tags[f[0]], fp[f[0]] = ('q', h, offset//2), query(h, offset//2)
        elif op == 'flw':
            a = address(f[1])
            require(pv, 'Unexpected FP32 load')
            if 0x40000 <= a < 0x40008:
                require((a-0x40000) % 4 == 0, 'Scale alignment')
                h = (a-0x40000)//4
                tags[f[0]], fp[f[0]] = ('scale', h, 0), h+1
            else:
                h, offset = divmod(a-0x20000, 256)
                require(h in (0, 1) and offset % 4 == 0 and offset//4 < tokens, 'Score stride/bounds')
                tags[f[0]], fp[f[0]] = ('score', h, offset//4), probability(h, offset//4)
        elif op == 'fcvt.h.s':
            require(pv and f[0] == f[1] and (len(f) == 2 or f[2:] == ['dyn']), 'Conversion/RM')
            tag = tags[f[1]]
            require(tag[0] in ('scale', 'score'), 'Conversion source')
            converts.append(tag)
            tags[f[0]] = ('half_'+tag[0], *tag[1:])
            fp[f[0]] = struct.unpack('<e', struct.pack('<e', fp[f[1]]))[0]
        elif op == 'vle16.v':
            reg, a = int(f[0][1:]), address(f[1])-0x30000
            require(pv and reg in (0, 2) and a == reg//2*512 and (sew, lmul) == (16, 2), 'Accumulator load')
            initializes.append(reg//2)
            for d in range(dim):
                put(reg, d, struct.unpack_from('<e', result, 64+a+2*d)[0], 'e')
        elif op == 'vfmul.vf':
            reg = int(f[0][1:])
            require(pv and reg in (0, 2) and f[1] == f[0] and
                    tags[f[2]] == ('half_scale', reg//2, 0), 'Initial scale mapping')
            scales.append(reg//2)
            for d in range(dim):
                put(reg, d, get(reg, d, 'e')*fp[f[2]], 'e')
        elif op in ('vfwmacc.vf', 'vfmacc.vf'):
            reg, src = int(f[0][1:]), int(f[2][1:])
            require(reg in (0, 2), 'Accumulator mapping')
            h = reg//2
            tag = tags[f[1]]
            if pv:
                require(op == 'vfmacc.vf' and src == 8 and tag == ('half_score', h, columns[8]) and
                        (sew, lmul) == (16, 2), 'PV token/head/precision order')
                events.append((tag[2], h))
                for d in range(dim):
                    put(reg, d, get(reg, d, 'e')+fp[f[1]]*get(src, d, 'e'), 'e')
            else:
                require(op == 'vfwmacc.vf' and src in range(8, 12) and
                        tag == ('q', h, columns[src]) and (sew, lmul) == (16, 1), 'QK dimension/head order')
                events.append((tag[2], h))
                for t in range(tokens):
                    put(reg, t, get(reg, t, 'f')+fp[f[1]]*get(src, t, 'e'), 'f')
        elif op in ('vse16.v', 'vse32.v'):
            reg = int(f[0][1:])
            h = reg//2
            a = address(f[1])-(0x30000 if pv else 0x20000)
            require(reg in (0, 2) and a == h*(512 if pv else 256) and
                    op == ('vse16.v' if pv else 'vse32.v') and
                    (sew, lmul) == ((16, 2) if pv else (32, 2)), 'Store mapping/width')
            stores.append(h)
            nbytes = vl*(2 if pv else 4)
            result[64+a:64+a+nbytes] = vrf[reg*128:reg*128+nbytes]
        elif op in ('bltu', 'beq'):
            take = integer(f[0]) < integer(f[1]) if op == 'bltu' else integer(f[0]) == integer(f[1])
            if take:
                nxt = int(f[2].split()[0], 16)
        elif op == 'j':
            nxt = int(f[0].split()[0], 16)
        elif op == 'ret':
            break
        else:
            raise ValueError('Unexpected instruction '+op+' '+args)
        pc = nxt
    else:
        raise ValueError('Step bound')
    require(initializes == [0, 1] and stores == [0, 1], 'Init/store coverage')
    require(events == [(x, h) for x in range(tokens if pv else dim) for h in (0, 1)], 'Exact FMA sequence')
    require(loads == list(range(tokens)) if pv else loads == list(range(0, dim, 4)), 'Replay count/order')
    if pv:
        require(scales == [0, 1] and converts == [('scale', h, 0) for h in (0, 1)] +
                [('score', h, t) for t in range(tokens) for h in (0, 1)], 'Conversion count/order')
    for h in range(2):
        if pv:
            for d in range(dim):
                expected = initial(h, d)*(h+1)+sum(probability(h, t)*value(t, d) for t in range(tokens))
                struct.pack_into('<e', reference, 64+h*512+2*d, expected)
        else:
            for t in range(tokens):
                expected = sum(query(h, d)*key(t, d) for d in range(dim))
                struct.pack_into('<f', reference, 64+h*256+4*t, expected)
    require(result == reference, 'Independent exact matrix/gap/tail/guard mismatch')


def check(text):
    qk, pv = instructions(text, QK), instructions(text, PV)
    count = 0
    for dim in (64, 96, 128):
        for tokens in range(1, 65):
            for stride in (dim*2, dim*2+16, dim*2+64):
                execute(qk, dim, tokens, stride)
                count += 1
            execute(pv, dim, tokens, dim*2, True)
            count += 1
    mutations = []
    for original, pv_mode, op, old, new in (
        (qk, False, 'mv', 't5,a4', 't5,a3'),
        (qk, False, 'vfwmacc.vf', 'v0,', 'v2,'),
        (qk, False, 'vse32.v', 'v2,', 'v0,'),
        (pv, True, 'add', 'a4,t1,512', 'a4,t1,256'),
        (pv, True, 'flw', '256(t0)', '128(t0)'),
        (pv, True, 'fcvt.h.s', 'ft0,ft0', 'ft0,ft1'),
        (pv, True, 'vfmacc.vf', 'v2,', 'v0,')):
        for pc, (word, operation, args) in original.items():
            if operation in (op, 'addi' if op == 'add' else op) and old in args:
                bad = dict(original)
                bad[pc] = (word, operation, args.replace(old, new, 1))
                mutations.append((bad, pv_mode))
                break
        else:
            raise ValueError('Mutation target missing '+op+' '+old)
    for original, mode in ((qk, False), (pv, True)):
        for pc, (word, op, args) in original.items():
            if word & 127 == 0x5b:
                bad = dict(original)
                bad[pc] = ((word & ~(31 << 7)) | (2 << 7), op, args)
                mutations.append((bad, mode))
                break
    for bad, mode in mutations:
        try:
            execute(bad, 128, 17, 320, mode)
        except (ValueError, KeyError):
            continue
        raise ValueError('Mutation unexpectedly accepted')
    return dict(mapped_matrix_cases=count, rejected_mutations=len(mutations),
                qk_cases=576, pv_cases=192, native_numerical_acceptance=False,
                scope='Disassembly mapping and exact-small-integer oracle only; no native CSR/RTL proof')
