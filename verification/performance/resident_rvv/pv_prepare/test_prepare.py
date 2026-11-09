#!/usr/bin/env python3
"""Host source/layout checks only; optional parent-supplied GNU disassembly audit."""
from collections import Counter
from pathlib import Path
import re
import struct
import sys
import unittest

SOURCE = Path(__file__).with_name('prepare.S')
SYMBOL = 'resident_pv_prepare'
REGISTERS = dict(zero='x0', ra='x1', sp='x2', t0='x5', t1='x6', t2='x7',
                 t3='x28', t4='x29', t5='x30', t6='x31', ft0='f0', ft1='f1',
                 **{f'a{i}': f'x{10+i}' for i in range(8)})


def program(text):
    code, labels = [], {}
    for raw in text.splitlines():
        line = raw.split('//', 1)[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            name = line[:-1]
            if name in labels:
                raise ValueError('Duplicate assembly label')
            labels[name] = len(code)
        elif not line.startswith('.'):
            op, _, args = line.partition(' ')
            code.append((op, tuple(x.strip() for x in args.strip().split(','))))
    if labels.get(SYMBOL) != 0:
        raise ValueError('Missing leaf entry')
    return code, labels


def trace(tokens, dimensions, heads, code=None, labels=None):
    """Walk source control flow and record active operation geometry, not FP math."""
    if tokens not in range(1, 65) or dimensions not in (64, 96, 128) or heads not in (1, 2):
        raise ValueError('Outside caller-admitted geometry')
    if code is None:
        code, labels = program(SOURCE.read_text())
    regs = dict(zero=0, a0=0x100000, a1=0x200000, a2=0x300000,
                a3=tokens, a4=dimensions, a5=heads)
    pc, vl, sew, lmul = 0, 0, 0, 0
    events = []
    for _ in range(128):
        op, args = code[pc]
        pc += 1
        if op == 'li':
            regs[args[0]] = int(args[1], 0)
        elif op == 'addi':
            regs[args[0]] = regs[args[1]]+int(args[2], 0)
        elif op == 'beq':
            if regs[args[0]] == regs[args[1]]:
                pc = labels[args[2]]
        elif op == 'j':
            pc = labels[args[0]]
        elif op == 'ret':
            return events, regs
        elif op == 'vsetvli':
            vl, sew, lmul = regs[args[1]], int(args[2][1:]), int(args[3][1:])
            if not 0 < vl <= 1024*lmul//sew:
                raise ValueError('Requested VL exceeds exact VLEN1024 capacity')
            events.append(dict(op=op, args=args, vl=vl, sew=sew, lmul=lmul))
        elif op in ('flw', 'vle16.v', 'vle32.v', 'fcvt.h.s', 'vfmul.vf',
                    'vfncvt.f.f.w', 'vwaddu.vx', 'vsll.vi', 'vor.vv', 'vmv.v.i'):
            event = dict(op=op, args=args, vl=vl, sew=sew, lmul=lmul)
            if op in ('flw', 'vle16.v', 'vle32.v'):
                match = re.fullmatch(r'(-?\d+)?\((\w+)\)', args[1])
                if not match:
                    raise ValueError('Unsupported address expression')
                address = regs[match[2]]+int(match[1] or 0)
                width = 2 if op == 'vle16.v' else 4
                event['reads'] = tuple(address+width*i for i in range(1 if op == 'flw' else vl))
            events.append(event)
        else:
            raise ValueError('Unreviewed helper instruction: '+op)
    raise ValueError('Unexpected loop or missing return')


def pack_raw(row0, row1, tokens, heads):
    """Bit-level zero-extension/shift/OR model; inputs are already converted halves."""
    if not 1 <= tokens <= 64 or heads not in (1, 2):
        raise ValueError('Unsupported layout')
    result = [None]*128
    for t in range(tokens):
        lo = row0[t] & 0xffff
        hi = (row1[t] & 0xffff) if heads == 2 else 0
        word = (lo + 0) | ((hi + 0) << 16)
        result[2*t:2*t+2] = struct.unpack('<HH', struct.pack('<I', word))
    return result


def check_disassembly(text, source=None):
    """Audit a linked helper disassembled with GNU -d -M no-aliases,numeric."""
    code, labels = program(SOURCE.read_text() if source is None else source)
    match = re.search(r'(?m)^\s*[0-9a-f]+ <'+SYMBOL+r'>:\s*$', text)
    if not match:
        raise ValueError('Public helper symbol missing from disassembly')
    body = text[match.end():]
    end = re.search(r'(?m)^\s*[0-9a-f]+ <[^>]+>:', body)
    if end:
        body = body[:end.start()]
    rows = []
    for raw in body.splitlines():
        found = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*?)\s*$', raw)
        if found:
            rows.append((int(found[1], 16), int(found[2], 16), found[3], found[4].split('#', 1)[0].strip()))
        elif re.match(r'^\s*[0-9a-f]+:\s+', raw):
            raise ValueError('Compressed/data/unknown instruction in leaf')
    if len(rows) != len(code):
        raise ValueError('Disassembly/source instruction count mismatch')
    base = rows[0][0]

    def numeric(arg):
        return re.sub(r'\b(?:'+ '|'.join(REGISTERS)+r')\b', lambda m: REGISTERS[m[0]], arg)

    for index, ((op, args), (addr, word, actual_op, actual_args)) in enumerate(zip(code, rows)):
        if addr != base+4*index:
            raise ValueError('Noncontiguous helper encoding')
        wanted = list(map(numeric, args))
        if op == 'li':
            op, wanted = 'addi', [wanted[0], 'x0', wanted[1]]
        elif op == 'j':
            op, wanted = 'jal', ['x0', hex(base+4*labels[args[0]])[2:]]
        elif op == 'ret':
            op, wanted = 'jalr', ['x0', '0(x1)']
        elif op == 'beq':
            wanted[2] = hex(base+4*labels[args[2]])[2:]
        actual = [x.strip() for x in re.sub(r'\s*<[^>]+>', '', actual_args).split(',')]
        if op == 'fcvt.h.s':
            if (word & 0x7f) != 0x53 or ((word >> 12) & 7) != 7:
                raise ValueError('Scalar conversion no longer uses dynamic rounding')
            if actual[-1] != 'dyn':
                actual.append('dyn')
        if (actual_op, actual) != (op, wanted):
            raise ValueError(f'Instruction mismatch at {addr:x}: {(actual_op, actual)} != {(op, wanted)}')
    return dict(symbol=SYMBOL, instructions=len(rows), leaf=True, numerical_execution=False)


class PrepareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text()
        cls.code, cls.labels = program(cls.text)

    def test_leaf_write_set(self):
        for op, args in self.code:
            if op in ('li', 'addi'):
                self.assertIn(args[0], ('t0', 't1'))
            elif op == 'vsetvli':
                self.assertEqual(args[0], 'zero')
            elif op in ('flw', 'fcvt.h.s'):
                self.assertIn(args[0], ('ft0', 'ft1'))
            elif op.startswith('v'):
                self.assertIn(args[0], ('v8', 'v10', 'v12', 'v14', 'v16', 'v18', 'v20', 'v21'))
            else:
                self.assertIn(op, ('beq', 'j', 'ret'))
        self.assertEqual(sum(op == 'ret' for op, _ in self.code), 1)
        self.assertFalse(any(op.startswith(('csr', 'fs', 'fr', 'vsseg', 'vse')) and op != 'vsetvli'
                             for op, _ in self.code))

    def test_all_384_shapes_active_load_bounds(self):
        seen = 0
        for d in (64, 96, 128):
            for h in (1, 2):
                for t in range(1, 65):
                    events, regs = trace(t, d, h)
                    reads = [a for e in events for a in e.get('reads', ())]
                    want = [0x200000+512*head+2*i for head in range(h) for i in range(d)]
                    want += [0x300000+4*head for head in range(h)]
                    want += [0x100000+256*head+4*i for head in range(h) for i in range(t)]
                    self.assertEqual(reads, want)
                    self.assertEqual(tuple(regs[f'a{i}'] for i in range(6)),
                                     (0x100000, 0x200000, 0x300000, t, d, h))
                    seen += 1
        self.assertEqual(seen, 384)

    def test_fp_order_and_inactive_suppression(self):
        for d in (64, 96, 128):
            for h in (1, 2):
                for t in (1, 8, 9, 31, 32, 33, 63, 64):
                    events, _ = trace(t, d, h)
                    fp = [e for e in events if e['op'] in ('fcvt.h.s', 'vfmul.vf', 'vfncvt.f.f.w')]
                    want = [('fcvt.h.s', 'ft0'), ('vfmul.vf', 'v8')]
                    if h == 2:
                        want += [('fcvt.h.s', 'ft1'), ('vfmul.vf', 'v10')]
                    want += [('vfncvt.f.f.w', 'v20')]
                    if h == 2:
                        want += [('vfncvt.f.f.w', 'v21')]
                    self.assertEqual([(e['op'], e['args'][0]) for e in fp], want)
                    for e in fp:
                        if e['op'] == 'fcvt.h.s':
                            self.assertEqual(e['args'][2], 'dyn')
                        else:
                            self.assertEqual(e['vl'], d if e['op'] == 'vfmul.vf' else t)
                            self.assertEqual(e['sew'], 16)

    def test_head1_h1_has_no_memory_or_fp(self):
        events, _ = trace(64, 128, 1)
        fp_operands = [e['args'] for e in events if e['op'] in ('flw', 'fcvt.h.s', 'vfmul.vf', 'vfncvt.f.f.w')]
        self.assertFalse(any('ft1' in args or args[0] in ('v10', 'v21') for args in fp_operands))
        self.assertIn(('vmv.v.i', ('v21', '0')), [(e['op'], e['args']) for e in events])

    def test_seed_full_initialization_before_active_fp(self):
        for h in (1, 2):
            events, _ = trace(9, 96, h)
            initial = events[:3]
            self.assertEqual([(e['op'], e['vl'], e['sew'], e['lmul']) for e in initial],
                             [('vsetvli', 128, 16, 2), ('vmv.v.i', 128, 16, 2), ('vmv.v.i', 128, 16, 2)])
            self.assertEqual([initial[i]['args'][0] for i in (1, 2)], ['v8', 'v10'])
            self.assertEqual(events[3]['args'][4], 'tu')

    def test_widebits_modes_and_final_full_normalization(self):
        for h in (1, 2):
            for t in (1, 8, 9, 32, 33, 63, 64):
                events, _ = trace(t, 64, h)
                widen = [e for e in events if e['op'] == 'vwaddu.vx']
                self.assertEqual([(e['args'], e['vl'], e['sew'], e['lmul']) for e in widen],
                    [(('v12', 'v20', 'zero'), t, 16, 1), (('v14', 'v21', 'zero'), t, 16, 1)])
                shift = next(e for e in events if e['op'] == 'vsll.vi')
                self.assertEqual((shift['args'], shift['vl'], shift['sew'], shift['lmul']),
                                 (('v14', 'v14', '16'), t, 32, 2))
                last = events[-1]
                self.assertEqual((last['op'], last['args'], last['vl'], last['sew'], last['lmul']),
                                 ('vor.vv', ('v12', 'v12', 'v12'), 128, 16, 2))
        self.assertEqual(self.code[-4:], [('li', ('t0', '128')),
            ('vsetvli', ('zero', 't0', 'e16', 'm2', 'ta', 'ma')),
            ('vor.vv', ('v12', 'v12', 'v12')), ('ret', ('',))])

    def test_raw_bits_not_signed_or_numeric_conversion(self):
        row0 = [0x0000, 0x8000, 0x7c00, 0xfc00, 0x7c01, 0xffff, 0x0001, 0x7bff]*8
        row1 = list(reversed(row0))
        for t in range(1, 65):
            for h in (1, 2):
                actual = pack_raw(row0, row1, t, h)
                expected = [v for i in range(t) for v in (row0[i], row1[i] if h == 2 else 0)]
                self.assertEqual(actual[:2*t], expected)
                self.assertEqual(actual[2*t:], [None]*(128-2*t))

    def test_fixed_source_head_and_lane_word_boundaries(self):
        offsets = (0, 8, 4, 12)
        for d in (64, 96, 128):
            for h in (1, 2):
                seed0 = [0x1000+i if i < d else 0 for i in range(128)]
                seed1 = [0x2000+i if h == 2 and i < d else 0 for i in range(128)]
                coeff = pack_raw(list(range(64)), list(range(100, 164)), 64, h)
                natural = seed0+seed1+coeff
                physical = [[[natural[16*w+l+offset] for offset in offsets]
                             for w in range(24)] for l in range(4)]
                self.assertEqual(len(natural), 384)
                for l in range(4):
                    self.assertEqual(physical[l][8][0], 0x2000+l if h == 2 else 0)
                    for head in range(2):
                        for w in range(8):
                            active = head < h and w < d//16
                            self.assertEqual(any(physical[l][8*head+w]), active)
                    self.assertEqual(physical[l][16][0], coeff[l])

    def test_no_complex_interleave_or_extra_call(self):
        ops = Counter(op for op, _ in self.code)
        self.assertEqual(ops['vwaddu.vx'], 2)
        self.assertEqual(ops['vsll.vi'], 1)
        self.assertEqual(ops['vor.vv'], 2)
        self.assertFalse(any('gather' in op or 'slide' in op or op in ('call', 'jal', 'jalr') for op in ops))
        self.assertNotIn('.word', self.text)

    def test_caller_boundary_model_rejects_invalid_geometry(self):
        for t, d, h in ((0, 64, 1), (65, 64, 1), (1, 63, 1), (1, 129, 2), (1, 96, 0), (9, 128, 3)):
            with self.assertRaises(ValueError):
                trace(t, d, h)

    def test_disassembly_fail_closed_missing_symbol(self):
        with self.assertRaisesRegex(ValueError, 'symbol missing'):
            check_disassembly('00010000 <wrong_helper>:\n')
        with self.assertRaisesRegex(ValueError, 'instruction count'):
            check_disassembly('00010000 <resident_pv_prepare>:\n')


if __name__ == '__main__':
    if '--disassembly' in sys.argv:
        index = sys.argv.index('--disassembly')
        if index+1 >= len(sys.argv):
            raise SystemExit('--disassembly requires the parent-produced GNU objdump file')
        print(check_disassembly(Path(sys.argv[index+1]).read_text()))
        del sys.argv[index:index+2]
    unittest.main()
