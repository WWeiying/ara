"""Twelve unchanged strict cases and two exact compile-option adapter tests."""
import unittest
import test_store_fifo_burst_preflight as frozen
import build_store_fifo_burst_preflight_v2 as successor


class StoreBurstV2Tests(frozen.StoreBurstTests):
    def test_exact_adapter_only_two_replacements(self):
        raw = successor.PREDECESSOR.read_bytes()
        adapted = successor.adapted_source(raw)
        for old, new in reversed(successor.REPLACEMENTS):
            self.assertEqual(adapted.count(new), 1)
            adapted = adapted.replace(new, old, 1)
        self.assertEqual(adapted.encode('ascii'), raw)
        self.assertEqual(successor.library.APP, frozen.p.APP)
        self.assertEqual(successor.library.LENGTHS, frozen.p.LENGTHS)
        self.assertEqual(successor.library.CHECKS, 2360)

    def test_predecessor_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'predecessor changed'):
            successor.adapted_source(successor.PREDECESSOR.read_bytes() + b'\n')


if __name__ == '__main__':
    unittest.main()
