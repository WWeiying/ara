"""Host geometry/source contracts only. Does not compile or execute candidate RTL."""
from collections import defaultdict
from pathlib import Path
import re
import struct
import unittest

from geometry import layout, raw_packets

HERE = Path(__file__).resolve().parent
SOURCE = (HERE/'akv_resident_pv_lane_candidate.sv').read_text()
PRODUCTION = (HERE.parents[3]/'hardware/src/lane/akv_resident_pv_lane.sv').read_text()


def qk_steps(elements, heads, dimensions):
    words = (elements+1)//2
    for dimension in range(dimensions):
        for word in range(words):
            for head in range(heads):
                mask = (1 << min(2, elements-2*word))-1
                pop = head == heads-1 and (word % 2 == 1 or word == words-1)
                yield dimension, word, head, mask, pop


def widen(bits):
    sign, exponent, mantissa = bits >> 15, (bits >> 10) & 31, bits & 1023
    if exponent == 0 and mantissa:
        leading = 10-mantissa.bit_length()
        exponent, mantissa = 112-leading, ((mantissa << (1+leading)) & 1023) << 13
    else:
        exponent = 255 if exponent == 31 else exponent+112 if exponent else 0
        mantissa <<= 13
    return sign << 31 | exponent << 23 | mantissa


class CandidateContract(unittest.TestCase):
    def test_original_named_ports_and_default_mode(self):
        def ports(text):
            header = text.split('module ', 1)[1].split(');', 1)[0]
            return {name: (direction, re.sub(r'\s+', '', width)) for direction, width, name in
                re.findall(r'\b(input|output)\s+logic\s*((?:\[[^\]]+\]\s*)*)(\w+)', header)}
        previous, candidate = ports(PRODUCTION), ports(SOURCE)
        self.assertTrue(previous)
        self.assertTrue(all(candidate.get(k) == v for k, v in previous.items()))
        self.assertIn('module akv_resident_pv_lane (', SOURCE)
        self.assertIn("input  logic cmd_qk_i = 1'b0", SOURCE)
        self.assertEqual(candidate['cmd_dimensions_i'], ('input', '[7:0]'))
        self.assertEqual(re.findall(r'\bqk_q\s*<=\s*([^;]+);', SOURCE), ["1'b0", 'cmd_qk_i'])
        self.assertIn('assign fpu_fp32_o = qk_q;', SOURCE)

    def test_only_original_arrays_and_pv_transaction_states(self):
        arrays = re.findall(r'logic\s+\[[^\]]+\]\s+(\w+)\s*\[(\d+)\]\s*;', SOURCE)
        self.assertEqual(arrays, [('accum_q', '16'), ('fifo_q', '2')])
        self.assertNotRegex(SOURCE, r'\bfpnew_(?:top|fma|multislice)\s*#')
        def states(text):
            return text.split('        Seed: if (seed_fire) begin', 1)[1].split('        FaultDrain:', 1)[0]
        self.assertEqual(states(SOURCE), states(PRODUCTION))
        self.assertIn('!expect_coeff_q && !bad_packet && !pending_q[slot]', SOURCE)
        self.assertIn('Drain: if (pending_q == 0) state_q <= Commit;', SOURCE)
        self.assertIn('accum_q[fpu_result_tag_i][16*i+:16] <= fpu_result_i[16*i+:16]', SOURCE)

    def test_dimensions_words_heads_packet_pops_and_slot_order(self):
        for n in range(1, 17):
            for heads in (1, 2):
                for dimension in (64, 96, 128):
                    steps = list(qk_steps(n, heads, dimension))
                    self.assertEqual(len(steps), ((n+1)//2)*heads*dimension)
                    self.assertEqual(sum(pop for _, _, _, _, pop in steps), ((n+3)//4)*dimension)
                    slots = defaultdict(list)
                    for d, word, head, mask, _ in steps:
                        slots[8*head+word].append(d)
                        self.assertIn(mask, (1, 3))
                    self.assertTrue(all(history == list(range(dimension)) for history in slots.values()))
                    self.assertTrue(all(slot < 16 for slot in slots))
                    self.assertEqual([(word, head) for d, word, head, _, _ in steps if d == 0],
                                     [(w, h) for w in range((n+1)//2) for h in range(heads)])
        self.assertIn('logic [7:0] tokens_q;', SOURCE)
        self.assertIn('logic [7:0] token_q;', SOURCE)
        self.assertIn('logic [7:0] rx_token_q;', SOURCE)
        self.assertIn('cmd_dimensions_i : {1\'b0, cmd_tokens_i}', SOURCE)

    def test_native_halfwords_and_partial_tail_byte_masks(self):
        for tokens in range(1, 65):
            for lane in layout(tokens, 2):
                n = lane['elements']
                if not n:
                    continue
                expected = {(w['head'], w['word']): w for w in lane['writes']}
                for _, word, head, mask, _ in qk_steps(n, 2, 1):
                    packet, subword = word//2, word % 2
                    physical = [16*packet+lane['lane']+x for x in (0, 8, 4, 12)]
                    values = (physical[subword], physical[subword+2])
                    for element in range(2):
                        if mask & 1 << element:
                            self.assertEqual(values[element], 4*(2*word+element)+lane['lane'])
                            self.assertLess(values[element], tokens)
                    self.assertEqual(expected[head, word]['element_mask'], mask)
                    self.assertEqual(expected[head, word]['byte_enable'], 0x0f if mask == 1 else 0xff)
        self.assertIn("fp32 ? 4'b0011 : 4'b1111", SOURCE)
        self.assertIn("qk_q ? {{4{commit_mask[1]}}, {4{commit_mask[0]}}}", SOURCE)
        self.assertIn('word_q[0] ? fifo_q[fifo_read_q][31:16] : fifo_q[fifo_read_q][15:0]', SOURCE)
        self.assertIn('word_q[0] ? fifo_q[fifo_read_q][63:48] : fifo_q[fifo_read_q][47:32]', SOURCE)

    def test_t17_fanout_and_single_partial_word_pop(self):
        lanes = layout(17, 2)
        self.assertEqual([l['elements'] for l in lanes], [5, 4, 4, 4])
        self.assertEqual([p['active'] for p in raw_packets(17)], [15, 1])
        self.assertEqual([sum(bool(p['active'] & (1 << l)) for p in raw_packets(17)) for l in range(4)], [2, 1, 1, 1])
        for n, heads, expected in ((1, 2, [(0, 1)]), (2, 1, [(0, 0)]),
                                   (5, 2, [(1, 1), (2, 1)])):
            self.assertEqual([(w, h) for _, w, h, _, pop in qk_steps(n, heads, 1) if pop], expected)
        self.assertIn('if (rx_word_q == raw_words_q)', SOURCE)
        self.assertIn('assign raw_word_done = !qk_q || word_q[0] || last_word;', SOURCE)
        self.assertIn('fpu_fire && last_head && raw_word_done', SOURCE)

    def test_all_finite_halfwords_widen_exactly(self):
        for bits in range(65536):
            if (bits >> 10) & 31 == 31:
                continue
            expected = struct.unpack('<I', struct.pack('<f', struct.unpack('<e', struct.pack('<H', bits))[0]))[0]
            self.assertEqual(widen(bits), expected, hex(bits))
        self.assertIn('ara_pkg::fp32_from_fp16(half_value, {1\'b0, leading_zeros})', SOURCE)
        self.assertEqual(SOURCE.count('lzc #(.WIDTH(10), .MODE(1))'), 3)

    def test_nan_payload_sign_and_class_preserved_no_manual_nv(self):
        for sign in (0, 1):
            self.assertEqual(widen(sign << 15 | 0x7c00), sign << 31 | 0x7f800000)
            for mantissa in range(1, 1024):
                bits = sign << 15 | 0x7c00 | mantissa
                wide = widen(bits)
                self.assertEqual(wide, sign << 31 | 0x7f800000 | mantissa << 13)
                self.assertEqual(bool(wide & 0x400000), bool(mantissa & 0x200))
                self.assertNotEqual(wide & 0x7fffff, 0)
        self.assertIn("single_value.m = {half_value.m, 13'b0};", SOURCE)
        self.assertIn('flags_q <= flags_q | fpu_result_flags_i;', SOURCE)
        self.assertNotIn("5'b10000", SOURCE)
        self.assertIn("accum_q[seed_slot] <= qk_q ? 64'b0 : seed_data_i", SOURCE)


if __name__ == '__main__':
    unittest.main()
