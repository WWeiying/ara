"""Frozen source, VL and FIFO invariants; host-only, not native/EDA evidence."""
import json
import unittest
from unittest.mock import patch

import prove_alub_lane0_reduction_zero_731 as p


class StaticProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = {key: (p.life.ROOT / paths[1]).read_text() for key, paths in p.SOURCES.items()}

    def test_full_encoded_vl_distribution(self):
        # Eleven VL bits plus the capacity endpoint; conservation checks all lanes.
        for vl in range(2049):
            local = [p.lane_vl(vl, lane) for lane in range(4)]
            self.assertEqual(sum(local), vl)
            self.assertEqual(local[0], (vl + 3) // 4)
            self.assertEqual(local[0] == 0, vl == 0)

    def test_small_vl_lane_counterexample_protected(self):
        for vl in (1, 2, 3):
            self.assertFalse(p.command_selector(vl, 0, True)['selector'] == 8)
            for lane in range(vl, 4):
                actual = p.command_selector(vl, lane, True)
                self.assertEqual(actual['selector'], 8)
                self.assertTrue(actual['command_valid'])

    def test_global_zero_reduction_not_dispatched(self):
        for lane in range(4):
            for ignore in (False, True):
                value = p.command_selector(0, lane, True, ignore_zero=ignore)
                self.assertEqual(value['selector'], 8)
                self.assertEqual(value['request_vl'], 1)
                self.assertFalse(value['command_valid'])

    def test_nonreduction_zero_muted_even_ignore_zero(self):
        for lane in range(4):
            for vl in range(4):
                value = p.command_selector(vl, lane, False, ignore_zero=True)
                if value['selector'] == 8:
                    self.assertFalse(value['command_valid'])

    def test_no_accepted_lane0_reduction_selector(self):
        for vl in range(2049):
            for reduction in (False, True):
                for incoming in (0, 1, 2, 3, 4, 5, 6, 7, 9):
                    value = p.command_selector(vl, 0, reduction, incoming, True)
                    self.assertFalse(value['command_valid'] and value['selector'] == 8)

    def test_direct_conversion_is_real_counterexample(self):
        value = p.command_selector(4, 0, False, incoming=8)
        self.assertTrue(value['command_valid'])
        self.assertEqual(value['selector'], 8)

    def test_reset_zero_and_flush_retains_memory(self):
        memory, pointer = p.fifo_selector_step([9, 9, 9, 9], 3, reset=True)
        self.assertEqual((memory, pointer), ([0] * 4, 0))
        for value in (1, 2, 3, 4, 5, 6, 7, 9):
            memory, pointer = p.fifo_selector_step(memory, pointer, push=value)
            saved = list(memory)
            memory, pointer = p.fifo_selector_step(memory, pointer, flush=True)
            self.assertEqual(memory, saved)
            self.assertEqual(pointer, 0)
            self.assertNotIn(8, memory)

    def test_flush_does_not_repair_illegal_previous_selector(self):
        memory, pointer = p.fifo_selector_step([0, 8, 0, 0], 3, flush=True)
        self.assertIn(8, memory)
        self.assertEqual(pointer, 0)

    def test_frozen_source_ledger(self):
        ledger = p.source_contract(self.texts)
        self.assertFalse(ledger['fifo_flush_clears_memory'])
        self.assertTrue(ledger['no_alternate_lane_broadcast_producer'])

    def test_source_negative_mutations(self):
        mutations = [
            ('dispatcher', 'ara_req.conversion_vs2 = OpQueueConversionZExt2;', 'ara_req.conversion_vs2 = OpQueueReductionZExt;'),
            ('dispatcher', 'ara_req.conversion_vs2 = OpQueueConversionZExt2;', 'ara_req.conversion_vs2 = indirect_selector;'),
            ('lane', "conv       : (vfu_operation_d.vl == '0) ? OpQueueReductionZExt : pe_req.conversion_vs2,", 'conv : OpQueueReductionZExt,'),
            ('fifo', "FALL_THROUGH = 1'b0", "FALL_THROUGH = 1'b1"),
            ('requester', "operand_request_i[requester_index].vl == '0", "operand_request_i[requester_index].vl == 1"),
            ('sequencer', 'vfu = VFU_LoadUnit;', 'vfu = VFU_Alu;'),
            ('ara', '.pe_req_o              (pe_req                   )', '.pe_req_o (other)'),
        ]
        for role, old, new in mutations:
            with self.subTest(role=role):
                self.assertIn(old, self.texts[role])
                texts = dict(self.texts); texts[role] = texts[role].replace(old, new)
                with self.assertRaises(ValueError): p.source_contract(texts)

    def test_actual_inventory_exact14_and_protected(self):
        bits = json.loads((p.BASE / 'combined-bits.json').read_bytes())
        scopes, definitions = p.inventory(bits)
        selected = [(s, m, r) for s, tab in scopes.items() for m, rs in tab.items() for r in rs if r['target']]
        self.assertEqual(len(selected), 14)
        self.assertEqual(sum(m == 'line' for _, m, _ in selected), 9)
        self.assertTrue(all(s == p.scope(0, 'b') and not r['hit731'] for s, _, r in selected))
        self.assertEqual(len(definitions), 2)
        for lane in range(4):
            self.assertTrue(all(not r['target'] for rs in scopes[p.scope(lane, 'a')].values() for r in rs))
        for lane in (1, 2, 3):
            self.assertTrue(all(not r['target'] for rs in scopes[p.scope(lane, 'b')].values() for r in rs))

    def test_candidate_hit_rejected(self):
        bits = json.loads((p.BASE / 'combined-bits.json').read_bytes())
        row = bits['metrics']['line'][p.scope(0, 'b')]
        row['bits'] = hex(int(row['bits'], 16) | (1 << (row['width'] - 1 - 99)))
        with self.assertRaises(ValueError): p.inventory(bits)


if __name__ == '__main__': unittest.main()
