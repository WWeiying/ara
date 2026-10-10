import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import eight_policy_epoch_732_report_v3 as v3
from verification_epoch import EpochError


class SpoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.a, self.b = self.root / 'a.json', self.root / 'b.json'
        for path in (self.a, self.b):
            path.write_bytes(b'{"a":[1,true]}')
        self.pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.a, self.b)}

    def phase(self, budget=100):
        phase = v3.SpoolingCapture(self.pins, list(self.pins), list(self.pins), {}, max_bytes=budget)
        self.addCleanup(phase.close)
        return phase

    def test_hash_only_snapshot_uses_zero_raw_ram(self):
        phase = self.phase(1)
        phase.check_pins(self.pins)
        self.assertEqual(phase.retained, 0)
        self.assertEqual(phase.finish()['hashes'], 2)
        with self.assertRaises(EpochError):
            phase.bytes(self.a)

    def test_original_source_opened_once_and_json_shared_by_exact_hash(self):
        phase = self.phase()
        with patch.object(v3.os, 'open', wraps=v3.os.open) as opened:
            phase.check_pins(self.pins)
            first = phase.load_sealed(self.a, self.pins[str(self.a)])
            second = phase.load_sealed(self.b, self.pins[str(self.b)])
            phase.finish()
        self.assertIs(first, second)
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(phase.parses, 1)
        self.assertEqual(phase.retained, self.a.stat().st_size)

    def test_spool_tamper_rejected(self):
        phase = self.phase()
        phase.sha(self.a)
        phase.spool.seek(0)
        phase.spool.write(b'X')
        with self.assertRaises(EpochError):
            phase.bytes(self.a)
        self.assertTrue(phase.failed)

    def test_disk_budget_and_unknown_pin_rejected(self):
        phase = self.phase()
        phase.disk_limit = 1
        with self.assertRaises(EpochError):
            phase.sha(self.a)
        with self.assertRaises(EpochError):
            self.phase().sha(self.root / 'unknown')

    def test_source_change_after_capture_rejected(self):
        phase = self.phase()
        phase.sha(self.a)
        self.a.write_bytes(b'changed')
        with self.assertRaises(EpochError):
            phase.bytes(self.a)

    def test_original_family_and_earlier_plans_unchanged(self):
        self.assertIs(v3.check.__code__, v3.prior.check.__code__)
        self.assertIs(v3.run_reviewed.__code__, v3.prior.run_reviewed.__code__)
        self.assertEqual(v3.prior.PLAN, 'epoch-readiness-plan.json')
        self.assertEqual(v3.PrivateWiring.enter.__code__, v3.prior.wiring.Wiring.enter.__code__)


if __name__ == '__main__':
    unittest.main()
