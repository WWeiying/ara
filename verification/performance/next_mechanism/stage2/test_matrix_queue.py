#!/usr/bin/env python3
"""Queue host contracts; evidence-only cases skip under general discovery."""
import argparse
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
import run_matrix_queue as q

PREPARED = None


def fixture(depth=16):
    enq = 8 if depth else 0
    return (f'STAGE2_QUEUE_COMMAND seq=1 depth={depth} enabled={int(depth > 0)} m=8 n=1 profile=1 kb=1 success=1 fault=0 '
            f'enq={enq} deq={enq} fp_accept=8 max_occ={enq} full=0 decoupled={int(depth > 0)} '
            f'start_overlap={int(depth > 0)} final_drain={int(depth > 0)} fault_drain=0 '
            'start_blocked=3 ctx0=0 ctx1=0 ctx2=0 ctx3=3 pending=3 fp_full=3 queue_full=0\n'
            f'STAGE2_QUEUE_DONE commands=1 enq={enq} deq={enq} resets=0 reset_flushed=0 depth={depth}\n')


class QueueContractTest(unittest.TestCase):
    def test_both_depths(self):
        for depth in (0, 16):
            self.assertEqual(q.check_queue_log(fixture(depth), depth)['totals']['depth'], depth)

    def test_duplicate_missing_unknown(self):
        for before, after in (('seq=1', 'seq=1 seq=1'), ('fp_accept=8 ', ''), ('full=0 ', 'full=0 alien=1 ')):
            with self.assertRaises(ValueError):
                q.check_queue_log(fixture().replace(before, after, 1), 16)

    def test_terminal_drain_and_work(self):
        for before, after in (('deq=8', 'deq=7'), ('fp_accept=8', 'fp_accept=7'),
                              ('max_occ=8', 'max_occ=17'), ('enabled=1', 'enabled=0'),
                              ('ctx3=3', 'ctx3=2'), ('commands=1', 'commands=2')):
            with self.assertRaises(ValueError):
                q.check_queue_log(fixture().replace(before, after, 1), 16)

    def test_disabled_queue_cannot_appear_active(self):
        with self.assertRaises(ValueError):
            q.check_queue_log(fixture(0).replace('start_overlap=0', 'start_overlap=1'), 0)

    def test_lender_not_replaced(self):
        self.assertNotIn('simd_mul', q.PROBE)
        self.assertIn('stage2_matrix_queue_probe', q.PROBE)
        self.assertIn('integer_result_data', q.PROBE)
        self.assertIn('fp_request_data', q.PROBE)

class PreparedQueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PREPARED is None:
            raise unittest.SkipTest('Pass --prepared DIRECTORY for frozen evidence checks')
        cls.old = q.checker.legacy()
        cls.config = json.loads((PREPARED / 'selection.json').read_text())

    def test_typed_entry_and_no_profile_change(self):
        source = (PREPARED / 'inputs' / q.COMPUTE).read_text()
        for token in ('IntegerResultQueueDepth = CooperativeWaves ? 16 : 0',
                      'fifo_v3 #', '.dtype(integer_result_t)', '.FALL_THROUGH(1\'b0)',
                      '!integer_busy && !integer_queue_busy && !fp_busy',
                      'QBS integer result queue cleared or released before drain',
                      '$stable(fp_request_data)', '$bits(integer_result_t) == 140'):
            self.assertIn(token, source)
        rel = Path('hardware/src/vlsu/qbs/qbs_profile_engine_int.sv')
        self.assertEqual(q.checker.sha(PREPARED / 'inputs' / rel),
                         q.checker.sha(q.checker.ORIGINAL / 'inputs' / rel))

    def test_minimal_shape_and_golden_unchanged(self):
        original = (PREPARED / 'minimal_original.txt').read_text()
        updated, changes = self.old.candidate_vector(original)
        self.assertEqual((PREPARED / 'minimal.txt').read_text(), updated)
        case, = self.old.vectors(updated)
        self.assertEqual((case['m'], case['n'], case['kb']), (8, 4, 2))
        self.assertEqual(len(changes), 1)

    def test_qwen3_vectors_copied_without_numeric_change(self):
        previous = json.loads((q.HISTORICAL / 'selection.json').read_text())
        for view, slices in previous['vectors'].items():
            for name, info in slices.items():
                self.assertEqual(Path(self.config['vectors'][f'{view}_{name}']).read_bytes(),
                                 Path(info['candidate']).read_bytes())

    def test_original_fallback_and_fault_vectors_unchanged(self):
        for name in ('synthetic', 'context'):
            self.assertEqual(Path(self.config['vectors'][name]).read_bytes(),
                             (q.checker.ORIGINAL / f'{name}_candidate.txt').read_bytes())

    def test_baseline_label_and_archived_images(self):
        historical = json.loads((PREPARED / 'historical-baseline.json').read_text())
        self.assertIn('historical matched engine baseline', historical['label'])
        self.assertFalse(historical['old_live_root_audit_reused'])
        self.old.verify(historical['archived_source_pins'])
        for arm, images in historical['images'].items():
            for name, digest in images.items():
                target = PREPARED / 'historical_images' / arm / Path(name).relative_to(q.checker.ORIGINAL / arm)
                self.assertEqual(q.checker.sha(target), digest)

    def test_only_two_fixed_depths(self):
        self.assertEqual(self.config['configurations'], [0, 16])
        self.assertEqual(self.config['queue_entry_bits'], 140)

    def test_shadow_checker_measures_real_effect_and_drain(self):
        local = Path(self.config['local'])
        source = (local / 'matrix_queue_probe.sv').read_text()
        for text in ('shadow.pop_front()', 'data_o === expected', 'shadow.push_back(data_i)',
                     'occupancy_i == shadow.size()', 'fp_valid_i && fp_ready_i',
                     'start_valid_i && !start_ready_i', 'final_drain_i && occupancy_i != 0',
                     'fault_drain_i && occupancy_i != 0'):
            self.assertIn(text, source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared', type=Path)
    args, rest = parser.parse_known_args()
    PREPARED = args.prepared
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
