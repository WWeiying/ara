"""Host/exact-rational checks only; no simulation or target execution."""
import ctypes as C
from fractions import Fraction
import json
import os
from pathlib import Path
import random
import struct
import unittest

import software_div as s


def magnitude(bits):
    exponent, significand = (bits >> 23) & 255, bits & 0x7fffff
    if exponent:
        significand |= 1 << 23
    shift = exponent - 150 if exponent else -149
    return Fraction(significand) * Fraction(2) ** shift


def exact_div(a, b):
    """Independent test oracle: rational quotient and binary32 neighbor search."""
    sign = (a ^ b) & 0x80000000
    aa, bb = a & 0x7fffffff, b & 0x7fffffff
    if aa > 0x7f800000 or bb > 0x7f800000:
        signaling = any(x > 0x7f800000 and not x & 0x400000 for x in (aa, bb))
        return 0x7fc00000, 16 if signaling else 0
    if (aa == bb == 0) or (aa == bb == 0x7f800000):
        return 0x7fc00000, 16
    if aa == 0x7f800000:
        return sign | 0x7f800000, 0
    if not bb:
        return sign | 0x7f800000, 8
    if not aa or bb == 0x7f800000:
        return sign, 0
    q = magnitude(aa) / magnitude(bb)
    if q >= Fraction(2) ** 128 - Fraction(2) ** 103:
        return sign | 0x7f800000, 5
    lo, hi = 0, 0x7f7fffff
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if magnitude(mid) <= q:
            lo = mid
        else:
            hi = mid - 1
    candidates = [lo] + ([lo + 1] if lo < 0x7f7fffff else [])
    rounded = min(candidates, key=lambda x: (abs(magnitude(x) - q), x & 1))
    inexact = magnitude(rounded) != q
    flags = int(inexact) | (2 if inexact and rounded < 0x800000 else 0)
    return sign | rounded, flags


def canonical(bits):
    return 0x7fc00000 if bits & 0x7fffffff > 0x7f800000 else bits


class PatchTest(unittest.TestCase):
    def test_only_two_replacements_and_fail_closed(self):
        rows = json.loads((s.PARENT / 'commands.json').read_text())
        argv = next(x['argv'] for x in rows if x['label'] == 'compile-firmware_quant.o')
        original = Path(argv[argv.index('-c') + 1]).read_text()
        patched = s.patch_quantizer(original)
        self.assertEqual(patched.count('power_softdiv_f32_rne('), 2)
        restored = patched.removeprefix('#include "power_softdiv.h"\n')
        for old, new in s.REPLACEMENTS:
            restored = restored.replace(new, old)
        self.assertEqual(original, restored)
        for drift in (original + '\n', original.replace('1.0f / iscale', '2.0f / iscale')):
            with self.assertRaises(ValueError):
                s.patch_quantizer(drift)

    def test_frozen_m4_parents_compatible(self):
        for mode in ('native', 'x32'):
            p = s.OUT / ('operator_qbs_prepare_20261115_q4_m4_%s_01' % mode)
            m = json.loads((p / 'build.json').read_text())
            self.assertEqual(m['sdk_commit'], s.SDK)
            pins = json.loads(Path(m['source_pins']).read_text())
            sources = [(p, h) for p, h in pins.items() if p.endswith('/arch/riscv/quants.c')]
            self.assertEqual(len(sources), 1)
            source, digest = sources[0]
            self.assertEqual(s.sha(source), digest)
            self.assertEqual(digest, s.QUANT_SHA)
            commands = json.loads((s.PARENT / 'commands.json').read_text())
            argv = next(x['argv'] for x in commands if x['label'] == 'compile-firmware_quant.o')
            shared = Path(argv[argv.index('-c') + 1]).read_text()
            self.assertEqual(s.patch_quantizer(Path(source).read_text()), s.patch_quantizer(shared))


class PreparedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get('POWER_SOFTDIV_BUILD', s.DEFAULT))
        if not (cls.output / 'host-softdiv.so').exists():
            raise unittest.SkipTest('Run software_div.py to build host/cross artifacts first')
        cls.lib = C.CDLL(str(cls.output / 'host-softdiv.so'))
        for name in ('power_softdiv_f32_bits', 'power_host_div'):
            f = getattr(cls.lib, name)
            f.argtypes, f.restype = [C.c_uint32, C.c_uint32], C.c_uint32
        cls.flags = C.c_uint32.in_dll(cls.lib, 'power_softdiv_host_fflags')
        cls.host_flags = C.c_uint32.in_dll(cls.lib, 'power_host_flags')

    def check_div(self, a, b, seed=0):
        expected, flags = exact_div(a, b)
        self.flags.value = seed
        got = self.lib.power_softdiv_f32_bits(a, b)
        self.assertEqual((got, self.flags.value), (expected, flags | seed),
                         '%08x / %08x seed=%x' % (a, b, seed))
        host = self.lib.power_host_div(a, b)
        self.assertEqual((canonical(host), self.host_flags.value), (expected, flags),
                         'native host %08x / %08x' % (a, b))
        return got

    def test_fault_and_flags(self):
        for seed in (0, 8, 16, 31):
            self.assertEqual(self.check_div(0xc2fe0000, 0x3fdcf5c9, seed), 0xc29323c3)
            self.assertEqual(self.check_div(0x3f800000, 0xc29323c3, seed), 0xbc5eb32f)
            self.assertEqual(self.check_div(0x3f800000, 0xc29323c2, seed), 0xbc5eb330)
            self.assertEqual(self.check_div(0x3f800000, 0x40000000, seed), 0x3f000000)
        # Test the float-argument bitcast entry as well as the bits entry.
        wrapper = self.lib.power_softdiv_f32_rne
        wrapper.argtypes, wrapper.restype = [C.c_float, C.c_float], C.c_float
        f = lambda u: struct.unpack('<f', struct.pack('<I', u))[0]
        u = lambda f: struct.unpack('<I', struct.pack('<f', f))[0]
        self.flags.value = 8
        self.assertEqual(u(wrapper(f(0xc2fe0000), f(0x3fdcf5c9))), 0xc29323c3)
        self.assertEqual(self.flags.value, 9)

    def test_exact_rational_host_edges_random(self):
        edges = [0, 0x80000000, 1, 0x80000001, 0x7fffff, 0x800000,
                 0x800001, 0x3f7fffff, 0x3f800000, 0x3f800001, 0x40000000,
                 0x7f7fffff, 0x7f800000, 0xff800000, 0x7fc00000, 0x7f800001]
        for a in edges:
            for b in edges:
                self.check_div(a, b)
        rng = random.Random(0x5346444956)
        for _ in range(2000):
            self.check_div(rng.getrandbits(32), rng.getrandbits(32))

    def test_captured_all_eight_points_and_compact_m4(self):
        cases = sorted((s.PARENT / 'cases').iterdir())
        self.assertEqual(len(cases), 8)
        fixtures = [p for p in cases if p.is_dir()]
        fixtures += [s.OUT / ('operator_qbs_prepare_20261115_q4_m4_%s_01' % mode) / 'data'
                     for mode in ('native', 'x32')]
        blocks = 0
        for p in fixtures:
            raw = (p / 'input_f32.bin').read_bytes()
            golden = (p / 'expected_q8.bin').read_bytes()
            values = struct.unpack('<%df' % (len(raw) // 4), raw)
            bits = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
            f32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]
            self.assertEqual(len(golden), len(values) // 256 * 292)
            for offset in range(0, len(values), 256):
                a = values[offset:offset + 256]
                extremum = max(a, key=abs)
                if extremum == 0:
                    packed = bytes(292)
                else:
                    scale = self.check_div(0xc2fe0000, bits(extremum))
                    d = self.check_div(0x3f800000, scale)
                    sf = struct.unpack('<f', struct.pack('<I', scale))[0]
                    # Product of two binary32 numbers is exact in binary64 before packing.
                    qs = [min(127, round(f32(x * sf))) for x in a]
                    packed = struct.pack('<I256b16h', d, *qs,
                        *[sum(qs[i:i + 16]) for i in range(0, 256, 16)])
                start = offset // 256 * 292
                self.assertEqual(packed, golden[start:start + 292], str(p) + ' block ' + str(offset // 256))
                blocks += 1
        self.assertEqual(blocks, 336)

    def test_cross_disassembly(self):
        helper = (self.output / 'helper-disassembly.log').read_text()
        quant = (self.output / 'quant-q8k-disassembly.log').read_text()
        self.assertNotRegex(helper, r'\bf(?:div|sqrt|mul|add|sub|cvt)\.')
        self.assertIn('divu', helper)
        self.assertRegex(helper, r'\bcsrs\s+fflags,')
        self.assertNotRegex(quant, r'\bfdiv\.')
        self.assertEqual(quant.count('R_RISCV_CALL_PLT\tpower_softdiv_f32_rne'), 2)
        self.assertEqual((self.output / 'helper-undefined.log').read_text().strip(), '')


if __name__ == '__main__':
    unittest.main()
