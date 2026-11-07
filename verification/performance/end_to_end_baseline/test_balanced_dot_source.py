"""Host-only transform and signed arithmetic tests, not an RTL simulation."""
import itertools
from pathlib import Path
import random
import re
import unittest

from balanced_dot_source import DECODER_SHA, DOT_SHA, decoder, dot, sha


ROOT = Path('/home/wangwy/openproject/ara_dsa')
RTL = ROOT / 'hardware/src/vlsu/qbs'
MASK = (1 << 19) - 1


def signed(value, width):
    value &= (1 << width) - 1
    return value - (1 << width) if value & (1 << (width - 1)) else value


def compress3(a, b, c):
    return (a ^ b ^ c) & MASK, (((a & b) | (a & c) | (b & c)) << 1) & MASK


def quad_csa(products):
    a, b, c, d = [value & MASK for value in products]
    low, carry = compress3(a, b, c)
    return compress3(low, carry, d)


def octet_csa(products):
    a, b = quad_csa(products[:4])
    c, d = quad_csa(products[4:])
    low, carry = compress3(a, b, c)
    low, carry = compress3(low, carry, d)
    return signed(low + carry, 19)


def source_mapping(text):
    match = re.search(r'if \(BalancedMatrixDot && quant_matrix_wide_q\) begin\n'
                      r'          ctx = slot >> (\d+);\n          lane = slot & (\d+);', text)
    if match is None:
        raise ValueError('Missing exact balanced slot mapping')
    return tuple(map(int, match.groups()))


def array_model(text, weights, acts, m, rows, wide, balanced, matrix):
    """Exercise the emitted slot mapping and reduction widths in Python."""
    if balanced and not wide:
        raise ValueError('Balanced requires wide')
    matrix = wide and matrix
    products_per_row = 32 if balanced else 16 if wide else 8
    balanced_shift, balanced_mask = source_mapping(text)
    outputs = [0] * 16
    for row in range(4):
        products = [0] * products_per_row
        for slot in range(products_per_row):
            if slot >= 8 and not matrix:
                continue
            if balanced and matrix:
                ctx, lane = slot >> balanced_shift, slot & balanced_mask
            elif matrix or m == 2:
                ctx, lane = slot >> 2, slot & 3
            elif m >= 3:
                ctx, lane = slot >> 1, slot & 1
            else:
                ctx, lane = 0, slot
            products[slot] = signed(weights[row][lane] * acts[ctx][lane], 16)
        if row >= rows:
            continue
        for ctx in range(m):
            if m == 1:
                value = octet_csa(products[:8])
            elif m == 2:
                a, b = quad_csa(products[4 * ctx:4 * ctx + 4])
                value = signed(a + b, 18)
            elif balanced and matrix:
                value = octet_csa(products[8 * ctx:8 * ctx + 8])
            elif matrix:
                a, b = quad_csa(products[4 * ctx:4 * ctx + 4])
                value = signed(a + b, 18)
            else:
                value = signed(sum(products[2 * ctx:2 * ctx + 2]), 17)
            outputs[4 * row + ctx] = value
    return outputs


def oracle(weights, acts, m, rows, width):
    return [sum(weights[row][lane] * acts[ctx][lane] for lane in range(width))
            if row < rows and ctx < m else 0 for row in range(4) for ctx in range(4)]


class BalancedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dot_original = (RTL / 'qbs_dot_array.sv').read_text()
        cls.decoder_original = (RTL / 'qbs_profile_decoder.sv').read_text()
        cls.dot_text, cls.dot_report = dot(cls.dot_original)
        cls.decoder_text, cls.decoder_report = decoder(cls.decoder_original)

    def test_exact_input_and_generated_hashes(self):
        for original, text, report, expected in (
                (self.dot_original, self.dot_text, self.dot_report, DOT_SHA),
                (self.decoder_original, self.decoder_text, self.decoder_report, DECODER_SHA)):
            self.assertEqual(sha(original), expected)
            self.assertEqual(report['original_sha256'], expected)
            self.assertEqual(report['generated_sha256'], sha(text))

    def test_all_edits_reverse_including_names(self):
        for original, text, report in ((self.dot_original, self.dot_text, self.dot_report),
                                       (self.decoder_original, self.decoder_text, self.decoder_report)):
            for edit in reversed(report['edits']):
                self.assertEqual(text.count(edit['after']), 1)
                text = text.replace(edit['after'], edit['before'], 1)
            self.assertEqual(text, original)
            self.assertTrue(report['source_reversible'])

    def test_drift_wrong_source_and_already_cloned_rejected(self):
        for function, original, clone in ((dot, self.dot_original, self.dot_text),
                                          (decoder, self.decoder_original, self.decoder_text)):
            for invalid in (None, b'', '', original + '\n', original + original, clone,
                            original.replace("WideMatrixDot = 1'b0", "WideMatrixDot = 1'b1", 1)):
                with self.subTest(function=function.__name__, value=type(invalid)), self.assertRaises(ValueError):
                    function(invalid)
        with self.assertRaises(ValueError):
            dot(self.decoder_original)

    def test_default_off_and_parameter_contracts(self):
        for text, name in ((self.dot_text, 'qbs_dot_array_balanced'),
                            (self.decoder_text, 'qbs_profile_decoder_balanced')):
            self.assertIn("parameter bit BalancedMatrixDot = 1'b0", text)
            self.assertIn('assert (!BalancedMatrixDot || WideMatrixDot)', text)
            self.assertIn('module ' + name, text)
            self.assertIn('endmodule : ' + name, text)
        with self.assertRaises(ValueError):
            array_model(self.dot_text, [[0] * 8] * 4, [[0] * 8] * 4, 4, 4, False, True, True)

    def test_original_register_blocks_and_interfaces_unchanged(self):
        old_ff = self.dot_original.split('  always_ff @', 1)[1].split('`ifndef SYNTHESIS', 1)[0]
        new_ff = self.dot_text.split('  always_ff @', 1)[1].split('`ifndef SYNTHESIS', 1)[0]
        self.assertEqual(new_ff, old_ff)
        self.assertEqual(new_ff.count('valid_o <= product_valid_q;'), 1)
        self.assertIn('quant_valid_q <= valid_i;', new_ff)
        self.assertIn('product_valid_q <= quant_valid_q;', new_ff)
        for old, new in ((self.dot_original, self.dot_text), (self.decoder_original, self.decoder_text)):
            ports = lambda text: text.split(') (\n', 1)[1].split('\n);', 1)[0]
            self.assertEqual(ports(old), ports(new))

    def test_original_narrow_paths_and_decoder_payload_math_unchanged(self):
        for anchor, end in (('          3\'d1:', '          default:'),
                            ('      for (int pair =', '      for (int quad =')):
            self.assertEqual(self.dot_original.split(anchor, 1)[1].split(end, 1)[0],
                             self.dot_text.split(anchor, 1)[1].split(end, 1)[0])
        for anchor, end in (('  logic [7:0] compact_low', '    k_per_context_o ='),
                            ("    group_index_o = '0;", '\nendmodule')):
            original = self.decoder_original.split(anchor, 1)[1].split(end, 1)[0]
            changed = self.decoder_text.split(anchor, 1)[1].split(end, 1)[0]
            if anchor.startswith('    group_index'):
                changed = changed.split('`ifndef SYNTHESIS', 1)[0]
                original, changed = original.rstrip(), changed.rstrip()
            self.assertEqual(original, changed)

    def test_tree_uses_constant_octets_and_full_signed_width(self):
        self.assertEqual(source_mapping(self.dot_text), (3, 7))
        self.assertIn('logic signed [18:0] balanced_oct_sum [4][4]', self.dot_text)
        self.assertIn('quad_sum_bits[row][2*ctx]', self.dot_text)
        self.assertIn('quad_carry_bits[row][2*ctx+1]', self.dot_text)
        self.assertIn('balanced_oct_sum[row][ctx] = second[18:0] + second[37:19]', self.dot_text)
        self.assertIn('BalancedMatrixDot ? 32 : (WideMatrixDot ? 16 : 8)', self.dot_text)
        self.assertEqual(octet_csa([(-128) * (-128)] * 8), 131072)
        self.assertNotEqual(signed(131072, 18), 131072)

    def test_octet_csa_corners_and_random_signed_products(self):
        for products in itertools.product((-32768, 32767), repeat=8):
            self.assertEqual(octet_csa(products), sum(products))
        rng = random.Random(0x128ba1)
        for _ in range(10000):
            products = [rng.randrange(-32768, 32768) for _ in range(8)]
            self.assertEqual(octet_csa(products), sum(products))

    def test_all_modes_directed_extremes_rows_and_contexts(self):
        directed = (-128, -127, -1, 0, 1, 126, 127)
        for a, b in itertools.product(directed, repeat=2):
            weights, acts = [[a] * 8 for _ in range(4)], [[b] * 8 for _ in range(4)]
            self.check_modes(weights, acts)

    def test_all_modes_random_math_and_disabled_equivalence(self):
        rng = random.Random(0x644128)
        for _ in range(400):
            weights = [[rng.randrange(-128, 128) for _ in range(8)] for _ in range(4)]
            acts = [[rng.randrange(-128, 128) for _ in range(8)] for _ in range(4)]
            self.check_modes(weights, acts)

    def check_modes(self, weights, acts):
        for wide, balanced in ((False, False), (True, False), (True, True)):
            for m, rows in itertools.product(range(1, 5), repeat=2):
                for block in (32, 256):
                    matrix = m >= 3 and block == 256
                    width = 8 if m == 1 else 4 if m == 2 else (
                        8 if balanced and wide and matrix else 4 if wide and matrix else 2)
                    actual = array_model(self.dot_text, weights, acts, m, rows, wide, balanced, matrix)
                    self.assertEqual(actual, oracle(weights, acts, m, rows, width))

    def test_decoder_steps_and_subgroup_boundaries_all_profiles(self):
        self.assertIn('BalancedMatrixDot && WideMatrixDot && m_i >= 3 &&', self.decoder_text)
        self.assertIn("k_per_context_o = 4'd8;", self.decoder_text)
        # Select the emitted conditions, then independently count every K
        # element and group boundary, including M1/M2 and compact formats.
        profiles = {1: (256, 32), 2: (256, 16), 3: (32, 32),
                    4: (256, 32), 5: (256, 16), 6: (32, 32),
                    7: (256, 16), 8: (32, 32), 9: (32, 32)}
        checked = 0
        for wide, balanced in ((False, False), (True, False), (True, True)):
            for m in range(1, 5):
                for profile, (block, subgroup) in profiles.items():
                    self.assertIn(profile, range(1, 10))
                    old = 8 if m == 1 else 4 if m == 2 else 4 if wide and block == 256 else 2
                    step = 8 if balanced and wide and block == 256 and m >= 3 else old
                    self.assertTrue(step in (2, 4, 8))
                    cursor = list(range(0, block, step))
                    consumed = [k + lane for k in cursor for lane in range(step)]
                    self.assertEqual(consumed, list(range(block)))
                    boundaries = [k + step for k in cursor if k % subgroup + step == subgroup]
                    self.assertEqual(boundaries, list(range(subgroup, block + 1, subgroup)))
                    if not balanced or m <= 2 or block == 32:
                        self.assertEqual(step, old)
                    checked += 1
        self.assertEqual(checked, 108)


if __name__ == '__main__':
    unittest.main(verbosity=2)
