"""Small offline fixtures; no EDA, sealed input mutations, or performance assertions."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark_verification_epoch as benchmark
from verification_epoch import EpochError


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.data = root / 'data'
        self.data.write_bytes(b'large-hash-only-input')
        self.json = root / 'small.json'
        self.json.write_bytes(b'{"field":[1,true]}')
        self.alias = root / 'alias'
        self.alias.symlink_to('data')
        digest = hashlib.sha256(self.data.read_bytes()).hexdigest()
        self.spec = dict(passes=2, json_paths=[str(self.json)],
            pins={str(self.data): digest, str(self.alias): digest,
                  str(self.json): hashlib.sha256(self.json.read_bytes()).hexdigest()},
            aliases={str(self.alias): dict(link_target='data', resolved=str(self.data), sha256=digest)})

    def test_exact_outcomes_and_bounded_read_reduction(self):
        old = benchmark.evaluate(self.spec, 'repeated')
        new = benchmark.evaluate(self.spec, 'capture')
        self.assertEqual(old['matched_pins'], new['matched_pins'])
        self.assertEqual(old['parsed_json_sha256'], new['parsed_json_sha256'])
        self.assertEqual((old['file_reads'], new['file_reads']), (6, 2))
        self.assertEqual((old['json_parses'], new['json_parses']), (2, 1))

    def test_wrong_sha_rejected_both_modes(self):
        self.spec['pins'][str(self.json)] = '0' * 64
        for mode in ('repeated', 'capture'):
            with self.subTest(mode=mode), self.assertRaises(EpochError):
                benchmark.evaluate(self.spec, mode)

    def test_conflicting_alias_rejected(self):
        self.spec['aliases'][str(self.alias)]['sha256'] = '0' * 64
        with self.assertRaises(EpochError):
            benchmark.evaluate(self.spec, 'capture')

    def test_wrong_literal_same_endpoint_rejected(self):
        self.alias.unlink()
        self.alias.symlink_to('./data')
        with self.assertRaises(EpochError):
            benchmark.evaluate(self.spec, 'capture')

    def test_missing_alias_permission_rejected(self):
        self.spec['aliases'] = {}
        with self.assertRaises(EpochError):
            benchmark.evaluate(self.spec, 'capture')

    def test_missing_alias_endpoint_pin_rejected(self):
        del self.spec['pins'][str(self.data)]
        with self.assertRaises(EpochError):
            benchmark.evaluate(self.spec, 'capture')

    def test_unpinned_alias_permission_rejected(self):
        del self.spec['pins'][str(self.alias)]
        with self.assertRaises(EpochError):
            benchmark.evaluate(self.spec, 'capture')

    def test_large_json_budget_rejected(self):
        with patch.object(benchmark, 'MAX_JSON', 1):
            with self.assertRaises(EpochError):
                benchmark.evaluate(self.spec, 'capture')

    def test_total_json_budget_rejected(self):
        with patch.object(benchmark, 'MAX_JSON_TOTAL', 1):
            with self.assertRaises(EpochError):
                benchmark.evaluate(self.spec, 'capture')

    def test_bad_json_rejected_in_both_modes(self):
        self.json.write_bytes(b'{"a":1,"a":2}')
        self.spec['pins'][str(self.json)] = hashlib.sha256(self.json.read_bytes()).hexdigest()
        for mode in ('repeated', 'capture'):
            with self.subTest(mode=mode), self.assertRaises(EpochError):
                benchmark.evaluate(self.spec, mode)

    def test_stream_changed_during_capture_rejected(self):
        original = benchmark.os.fstat
        calls = []

        def mutate(fd):
            calls.append(fd)
            if len(calls) == 2:
                self.data.write_bytes(b'changed-size')
            return original(fd)

        with patch.object(benchmark.os, 'fstat', side_effect=mutate):
            with self.assertRaises(EpochError):
                benchmark.evaluate(self.spec, 'capture')

    def test_fresh_evaluation_does_not_reuse_old_hash(self):
        benchmark.evaluate(self.spec, 'capture')
        self.data.write_bytes(b'changed-after-first-evaluation')
        with self.assertRaises(EpochError):
            benchmark.evaluate(self.spec, 'capture')


if __name__ == '__main__':
    unittest.main()
