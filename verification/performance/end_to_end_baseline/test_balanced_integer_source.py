"""Host policy proofs and exact-source checks, not RTL simulation coverage."""

import hashlib
from pathlib import Path
import random
import unittest
from unittest.mock import patch

import balanced_integer_source as b


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv'


def prefix_two(pending):
    """Mirror the emitted three-level saturating prefix network."""
    any_prefix, two_prefix = pending, 0
    for shift in (1, 2, 4):
        two_prefix = (two_prefix | (two_prefix << shift) |
                      (any_prefix & (any_prefix << shift))) & 255
        any_prefix = (any_prefix | (any_prefix << shift)) & 255
    first = second = 0
    for index in range(1, 8):
        if pending & (1 << index):
            if not any_prefix & (1 << (index - 1)):
                first |= index
            if (any_prefix & (1 << (index - 1)) and
                    not two_prefix & (1 << (index - 1))):
                second |= index
    return (bool(any_prefix & 128), first, bool(two_prefix & 128), second)


def select_row(pending, rr, balanced_contexts):
    upper = prefix_two(pending & (255 ^ ((1 << rr) - 1)))
    lower = prefix_two(pending & ((1 << rr) - 1))
    first_found = upper[0] or lower[0]
    first = upper[1] if upper[0] else lower[1]
    second_found = upper[2] or (upper[0] and lower[0]) or lower[2]
    second = upper[3] if upper[2] else lower[1] if upper[0] else lower[3]
    grants = [first] if first_found else []
    if second_found and balanced_contexts[second >> 2]:
        grants.append(second)
    return grants, ((grants[-1] + 1) & 7) if grants else rr


def reference_row(pending, rr, balanced_contexts):
    ordered = [(rr + i) & 7 for i in range(8) if pending & (1 << ((rr + i) & 7))]
    count = 2 if len(ordered) > 1 and balanced_contexts[ordered[1] // 4] else 1
    grants = ordered[:count]
    return grants, ((grants[-1] + 1) % 8) if grants else rr


def k_step(m, block, wide, balanced):
    return 8 if m == 1 else 4 if m == 2 else (8 if balanced else 4) if wide and block == 256 else 2


class BalancedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = SOURCE.read_text()
        cls.text, cls.report = b.integer(cls.original)

    def test_exact_sha_and_reversible_including_module_names(self):
        self.assertEqual(hashlib.sha256(self.original.encode()).hexdigest(), b.INT_SHA)
        restored = self.text
        for edit in reversed(self.report['edits']):
            self.assertEqual(restored.count(edit['after']), 1)
            restored = restored.replace(edit['after'], edit['before'], 1)
        self.assertEqual(restored, self.original)
        self.assertEqual(hashlib.sha256(self.text.encode()).hexdigest(),
                         self.report['generated_sha256'])
        self.assertIn('module qbs_profile_engine_int_balanced import', self.text)
        self.assertIn('endmodule : qbs_profile_engine_int_balanced', self.text)
        self.assertIn("parameter bit BalancedMatrixDot = 1'b0", self.text)
        self.assertIn('assert (!BalancedMatrixDot || WideMatrixDot)', self.text)

    def test_identity_and_anchor_fail_closed(self):
        for bad in ('', self.original + '\n', self.original * 2,
                    self.original.replace('DotLatency = 3', 'DotLatency = 4', 1),
                    self.original.replace('\n', '\r\n')):
            with self.assertRaises(ValueError):
                b.integer(bad)
        bad = self.original.replace('  parameter bit WideMatrixDot', '  parameter bit OtherWide', 1)
        with patch.object(b, 'INT_SHA', hashlib.sha256(bad.encode()).hexdigest()):
            with self.assertRaises(ValueError):
                b.integer(bad)

    def test_children_and_physical_capacity_contract(self):
        self.assertEqual(self.text.count('qbs_profile_decoder_balanced #('), 1)
        self.assertEqual(self.text.count('qbs_dot_array_balanced #('), 1)
        self.assertEqual(self.text.count('.BalancedMatrixDot(BalancedMatrixDot)'), 2)
        self.assertIn('ProductsPerRow = BalancedMatrixDot ? 32 : (WideMatrixDot ? 16 : 8)', self.text)
        self.assertIn('CorrectionLanes = BalancedMatrixDot ? 8 : (WideMatrixDot ? 4 : 2)', self.text)
        self.assertIn('pair_capacity_o + row_count_q * ProductsPerRow', self.text)
        self.assertIn('DotLatency = 3;', self.text)
        self.assertIn('WideMatrixDot && block_elements_q == 256 ? (BalancedMatrixDot ? 8 : 4) : 2', self.text)
        for m in range(1, 5):
            for block in (32, 256):
                if m < 3 or block == 32:
                    self.assertEqual(k_step(m, block, True, True), k_step(m, block, True, False))
                else:
                    self.assertEqual((k_step(m, block, True, False), k_step(m, block, True, True)), (4, 8))

    def test_captured_epoch_not_current_profile_or_m(self):
        self.assertIn("context_balanced_q[context_index] <= 1'b0;", self.text)
        self.assertIn('''context_balanced_q[start_context] <= BalancedMatrixDot && start_m_i >= 3 &&
            qbs_weight_block_elements(start_profile_i) == 256;''', self.text)
        self.assertIn('selected_valid[row][1] = context_balanced_q[selected[row][1][2]]', self.text)
        self.assertEqual(self.text.count('context_balanced_q[start_context] <='), 1)
        self.assertNotIn('profile_q', b.BALANCED_CORRECTIONS)
        self.assertNotIn('m_q', b.BALANCED_CORRECTIONS)

    def test_legacy_branches_commit_drain_and_single_result_unchanged(self):
        def section(text, begin, end):
            return text.split(begin, 1)[1].split(end, 1)[0]
        for begin, end in (
            ('begin : gen_two_corrections', '  // Read the subtotal at commit'),
            ('  // Read the subtotal at commit', '  logic [FlatEntries-1:0] result_upper'),
            ('  logic [FlatEntries-1:0] result_upper', '  always_ff @(posedge clk_i or negedge rst_ni)'),
            ('      if (!WideMatrixDot && correction_consume_any)', '      if (dot_valid) begin'),
            ('      if (dot_valid) begin', '`ifndef SYNTHESIS\n      if (start_fire) begin'),
            ('  assign tail_wave_requires_correction_drain =', '  qbs_profile_decoder')):
            self.assertEqual(section(self.original, begin, end), section(self.text, begin, end))
        self.assertIn("2'(BalancedMatrixDot ? (lane >> 1) : lane)", self.text)
        for reason in ('QBS correction lanes committed the same stream twice',
                       'QBS correction slot overflow:',
                       'QBS shared subgroup metadata overwritten before consumption',
                       'QBS correction committed to a released/completed stream',
                       'QBS dot subtotal overflow:', 'QBS aux subtotal overflow:',
                       'QBS early integer completion left dot work pending'):
            self.assertEqual(self.text.count(reason), self.original.count(reason))

    def test_emitted_prefix_and_row_mapping_match_host_model(self):
        for token in ('level < 3', 'bit_index < 8', 'any_prefix[3][7]', 'two_prefix[3][7]',
                      'first_index |=', 'second_index |=', 'entry / 4][4*row + entry % 4]',
                      'correction_valid[2*row+port] = selected_valid[row][port]',
                      'correction_context[2*row+port] = selected[row][port][2]',
                      "correction_stream[2*row+port] = {2'(row), selected[row][port][1:0]}",
                      "if (selected_valid[row][1]) rr_q[row] <= selected[row][1] + 1'b1",
                      "if (selected_valid[row][0]) rr_q[row] <= selected[row][0] + 1'b1",
                      'Balanced correction duplicate or legacy second grant'):
            self.assertIn(token, b.BALANCED_CORRECTIONS)


class RowPolicyTests(unittest.TestCase):
    def test_prefix_all_masks(self):
        for mask in range(256):
            selected = [i for i in range(8) if mask & (1 << i)]
            got = prefix_two(mask)
            self.assertEqual(got[0], bool(selected))
            self.assertEqual(got[2], len(selected) > 1)
            if selected:
                self.assertEqual(got[1], selected[0])
            if len(selected) > 1:
                self.assertEqual(got[3], selected[1])

    def test_exhaustive_masks_rr_epoch_flags_and_row_ownership(self):
        for mask in range(256):
            for rr in range(8):
                for flags in ((False, False), (False, True), (True, False), (True, True)):
                    grants, next_rr = select_row(mask, rr, flags)
                    self.assertEqual((grants, next_rr), reference_row(mask, rr, flags))
                    self.assertEqual(len(grants), len(set(grants)))
                    if len(grants) == 2:
                        self.assertTrue(flags[grants[1] // 4])
                    for row in range(4):
                        keys = [(g // 4, 4 * row + g % 4) for g in grants]
                        self.assertEqual(len(keys), len(set(keys)))
                        for port, (context, stream) in enumerate(keys):
                            self.assertEqual(stream >> 2, (2 * row + port) >> 1)
                            self.assertTrue(mask & (1 << (4 * context + stream % 4)))

    def test_no_skip_counterexample_and_legacy_sequence(self):
        # Jumping from legacy 0 to balanced 4 would strand legacy 1..3 under refill.
        self.assertEqual(select_row(255, 0, (False, True)), ([0], 1))
        self.assertEqual(select_row(255, 3, (False, True)), ([3, 4], 5))
        self.assertEqual(select_row(129, 7, (True, False)), ([7, 0], 1))
        self.assertEqual(select_row(129, 7, (False, True)), ([7], 0))
        rng = random.Random(0x6113)
        rr = 0
        for _ in range(2000):
            mask = rng.randrange(256)
            grants, nxt = select_row(mask, rr, (False, False))
            old = next(((rr + i) & 7 for i in range(8) if mask & (1 << ((rr + i) & 7))), None)
            self.assertEqual(grants, [] if old is None else [old])
            self.assertEqual(nxt, rr if old is None else (old + 1) & 7)
            rr = nxt

    def test_persistent_and_random_refill_fairness(self):
        for flags in ((False, False), (False, True), (True, False), (True, True)):
            for start in range(8):
                rr = start
                seen = set()
                for _ in range(8):
                    grants, rr = select_row(255, rr, flags)
                    seen.update(grants)
                self.assertEqual(seen, set(range(8)))
        rng = random.Random(0x832)
        pending = rr = 0
        age = [0] * 8
        for _ in range(10000):
            pending |= rng.randrange(256)
            flags = (bool(rng.getrandbits(1)), bool(rng.getrandbits(1)))
            grants, rr = select_row(pending, rr, flags)
            for i in range(8):
                age[i] = age[i] + 1 if pending & (1 << i) else 0
                self.assertLessEqual(age[i], 8)
            for i in grants:
                pending &= ~(1 << i)
                age[i] = 0

    def test_two_stage_commit_shared_metadata_and_result_drain(self):
        rng = random.Random(0x828)
        for m in (1, 2, 3, 4):
            for subgroup in (16, 32):
                for block in (32, 256):
                    for rows in range(1, 5):
                        balanced = m >= 3 and block == 256
                        flags = (balanced, False)
                        periods = (subgroup // k_step(m, block, True, True), 4)
                        deposits = {}
                        expected = {}
                        for context in range(2):
                            start = 0 if context == 0 else 3 * periods[0] + 4 + periods[1]
                            for group in range(4):
                                jobs = {}
                                for row in range(rows):
                                    scale, minimum = rng.randrange(-64, 64), rng.randrange(64)
                                    for activation in range(m):
                                        key = context, 4 * row + activation
                                        dot, aux = rng.randrange(-65536, 65537), rng.randrange(-32768, 32768)
                                        jobs[key] = (group, dot * scale, aux * minimum, group == 3)
                                        a, bsum = expected.get(key, (0, 0))
                                        expected[key] = a + dot * scale, bsum + aux * minimum
                                deposits[start + group * periods[context]] = jobs
                        slots = {}
                        rr = [0] * 4
                        pipeline = [[], []]
                        subtotal, pending_result, actual = {}, {}, {}
                        live = [True, True]
                        emitted = [0, 0]
                        same_edge_replace = 0
                        for cycle in range(300):
                            # The real output also sees only pre-edge pending bits.
                            if pending_result:
                                key = min(pending_result)
                                actual[key] = pending_result.pop(key)
                                emitted[key[0]] += 1
                                if emitted[key[0]] == rows * m:
                                    live[key[0]] = False
                            commits = pipeline.pop(0)
                            self.assertEqual(len(commits), len({k for k, _ in commits}))
                            for key, (_, dot, aux, last) in commits:
                                self.assertTrue(live[key[0]])
                                a, bsum = subtotal.get(key, (0, 0))
                                subtotal[key] = a + dot, bsum + aux
                                if last:
                                    self.assertNotIn(key, pending_result)
                                    pending_result[key] = subtotal[key]
                            issued = []
                            for row in range(4):
                                mask = sum(1 << (4 * c + a) for c in range(2) for a in range(4)
                                           if (c, 4 * row + a) in slots)
                                grants, rr[row] = select_row(mask, rr[row], flags)
                                for g in grants:
                                    key = g // 4, 4 * row + g % 4
                                    issued.append((key, slots.pop(key)))
                            self.assertEqual(len(issued), len({k for k, _ in issued}))
                            if cycle in deposits:
                                jobs = deposits[cycle]
                                context = next(iter(jobs))[0]
                                self.assertTrue(live[context])
                                self.assertFalse(any(k[0] == context for k in slots),
                                                 'Shared subgroup metadata overwritten before consumption')
                                same_edge_replace += len(set(jobs) & {k for k, _ in issued})
                                slots.update(jobs)
                            pipeline.append(issued)
                            if not slots and not any(pipeline) and not pending_result and not any(live):
                                break
                        self.assertEqual(actual, expected)
                        self.assertFalse(any(live))
                        if m == 4 and block == 256 and subgroup == 16:
                            self.assertGreater(same_edge_replace, 0)

    def test_per_step_group_and_correction_numeric_widths(self):
        for step in (2, 4, 8):
            for a in (-128, 127):
                for w in (-128, 127):
                    dot = step * a * w
                    self.assertTrue(-(1 << 18) <= dot < (1 << 18))
                    for group in (16, 32):
                        self.assertTrue(-(1 << 20) <= group * a * w < (1 << 20))
        for dot in (-(1 << 20), (1 << 20) - 1):
            for scale in (-128, 127):
                self.assertTrue(-(1 << 28) <= dot * scale < (1 << 28))
        for aux in (-32768, 32767):
            for minimum in (0, 63):
                self.assertTrue(-(1 << 22) <= aux * minimum < (1 << 22))


if __name__ == '__main__':
    unittest.main()
