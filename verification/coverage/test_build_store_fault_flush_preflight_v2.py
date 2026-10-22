import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import build_store_fault_flush_preflight_v2 as p


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.runtime = {str(p.life.IMAGE): p.IMAGE_SHA}
        self.runtime.update({f'/fixed/library{i}': 'a' * 64 for i in range(65)})
        self.plan = {'simv': str(p.life.IMAGE), 'image': self.runtime}
        self.book = {'pins': {str(p.COMPILE): p.COMPILE_SHA}}
        self.review = {'pins': {'/fixed/app': 'd' * 64}}
        self.hashes = {str(p.life.IMAGE): p.IMAGE_SHA, str(p.COMPILE): p.COMPILE_SHA,
                       str(Path(p.frozen.__file__).resolve()): p.FROZEN_SHA}

    def run_guard(self):
        def read(path, seal):
            if path == p.BOOK:
                self.assertEqual(seal, p.BOOK_SHA)
                return copy.deepcopy(self.book)
            if path == p.REVIEW:
                self.assertEqual(seal, p.REVIEW_SHA)
                return copy.deepcopy(self.review)
            self.assertEqual((path, seal), (p.PLAN, p.PLAN_SHA))
            return copy.deepcopy(self.plan)
        with patch.object(p.life, 'read_bound', side_effect=read), \
             patch.object(p.life, 'digest', side_effect=lambda path: self.hashes.get(str(path), 'b' * 64)), \
             patch.object(p.life, 'check') as check:
            result = p.fixed_inputs()
            check.assert_called_once_with(result)
            return result

    def test_sealed_expected_bytes_not_fresh_whitelist(self):
        result = self.run_guard()
        self.assertEqual(result[str(p.life.IMAGE)], p.IMAGE_SHA)
        self.assertEqual(result[str(p.COMPILE)], p.COMPILE_SHA)
        self.assertTrue(all(result[k] == v for k, v in self.runtime.items()))
        self.assertEqual(result['/fixed/app'], 'd' * 64)

    def test_foreign_image_rejected(self):
        self.hashes[str(p.life.IMAGE)] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'simv bytes'): self.run_guard()

    def test_changed_compile_bytes_rejected(self):
        self.hashes[str(p.COMPILE)] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'compile-command bytes'): self.run_guard()

    def test_foreign_history_cannot_bless_image(self):
        self.plan['image'][str(p.life.IMAGE)] = 'c' * 64
        self.hashes[str(p.life.IMAGE)] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'runtime66 identity'): self.run_guard()

    def test_history_cannot_bless_compile(self):
        self.book['pins'][str(p.COMPILE)] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'compile identity'): self.run_guard()

    def test_missing_runtime_file_rejected(self):
        self.plan['image'].pop('/fixed/library0')
        with self.assertRaisesRegex(ValueError, 'runtime66 identity'): self.run_guard()

    def test_predecessor_drift_rejected(self):
        self.hashes[str(Path(p.frozen.__file__).resolve())] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'predecessor drift'): self.run_guard()

    def test_guard_runs_before_original_static(self):
        previous = p.frozen.static
        with patch.object(p, 'fixed_inputs', side_effect=ValueError('foreign image')), \
             patch.object(p, 'ORIGINAL_STATIC') as original, patch.object(p.frozen.subprocess, 'run') as tool:
            with self.assertRaises(ValueError): p.build(p.life.OUT / 'not-created')
            original.assert_not_called(); tool.assert_not_called()
            self.assertIs(p.frozen.static, previous)

    def test_guard_pins_survive_receipt_serialization(self):
        import json
        pins = {str(p.life.IMAGE): p.IMAGE_SHA, str(p.COMPILE): p.COMPILE_SHA}
        receipt = {'pins': dict(pins), 'baseline': 731, 'primary_target': {'raw_index': 54}}
        with patch.object(p, 'fixed_inputs', return_value=pins), \
             patch.object(p, 'ORIGINAL_STATIC', return_value=receipt), patch.object(p.life, 'check'):
            result = json.loads(json.dumps(p.static()))
        self.assertEqual(result['pins'], pins)
        self.assertEqual(result['fixed_image_contract']['runtime_files_checked'], 66)

    def test_conflicting_fresh_pin_rejected(self):
        pins = {str(p.life.IMAGE): p.IMAGE_SHA, str(p.COMPILE): p.COMPILE_SHA}
        receipt = {'pins': {str(p.life.IMAGE): 'c' * 64}}
        with patch.object(p, 'fixed_inputs', return_value=pins), \
             patch.object(p, 'ORIGINAL_STATIC', return_value=receipt):
            with self.assertRaisesRegex(ValueError, 'Conflicting'): p.static()


if __name__ == '__main__':
    unittest.main()
