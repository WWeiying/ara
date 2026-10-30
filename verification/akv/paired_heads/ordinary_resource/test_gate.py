"""Host-only semantic/mutation tests; no simulator or live service inspection."""
import copy
import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import contract as c
import historical_sources as historical
from threeway_run_test import fixture

spec = importlib.util.spec_from_file_location('ordinary_resource_worker', c.HERE / 'run.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = fixture()
        cls.parsed = c.original.check_log(cls.text)
        cls.rows = [c.s.numeric_fields(line[len('[AKV_PERF] '):], c.s.PERF_FIELDS)
                    for line in cls.text.splitlines() if line.startswith('[AKV_PERF] ')]

    def test_exact_or_improved_all_calls(self):
        for change in (0, -1):
            after = copy.deepcopy(self.parsed)
            for trial in after['trials']:
                trial['cycles'] += change
            result = c.compare(self.parsed, after, self.rows, self.rows)
            self.assertEqual(result['state'], 'PASS')
            self.assertEqual(result['hardware_records_equal'], 3864)
            self.assertEqual(len(result['calls']), 6)
            self.assertFalse(result['model_execution'])

    def test_single_call_regression_not_hidden_by_sum(self):
        for index in range(6):
            after = copy.deepcopy(self.parsed)
            after['trials'][index]['cycles'] += 1
            after['trials'][(index + 1) % 6]['cycles'] -= 100
            result = c.compare(self.parsed, after, self.rows, self.rows)
            self.assertEqual(result['state'], 'FAIL')
            self.assertTrue(result['functional_same_work_pass'])
            self.assertEqual(result['calls'][index]['delta_cycles'], 1)

    def test_corresponding_identity_not_cross_variant(self):
        self.assertNotEqual(self.parsed['trials'][0]['checksum'], self.parsed['trials'][1]['checksum'])
        for field, value in (('checksum', '0'*16), ('fcsr', 9), ('vcsr', 0), ('native', 1)):
            after = copy.deepcopy(self.parsed)
            after['trials'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'output/CSR/work'):
                c.compare(self.parsed, after, self.rows, self.rows)

    def test_full_records_not_only_totals(self):
        after = copy.deepcopy(self.rows)
        after[0]['busy_cycles'] += 1
        after[1]['busy_cycles'] -= 1
        with self.assertRaisesRegex(ValueError, 'Per-command'):
            c.compare(self.parsed, self.parsed, self.rows, after)
        with self.assertRaises(ValueError):
            c.compare(self.parsed, self.parsed, self.rows, self.rows[:-1])

    def test_no_missing_or_reordered_trials(self):
        for trials in (self.parsed['trials'][:-1], list(reversed(self.parsed['trials']))):
            after = dict(self.parsed, trials=trials)
            with self.assertRaises(ValueError):
                c.compare(self.parsed, after, self.rows, self.rows)

    def test_raw_missing_records_fake_pass_and_csr(self):
        first = next(line for line in self.text.splitlines() if line.startswith('[AKV_PERF] '))
        for bad in (self.text.replace(first + '\n', '', 1), c.original.SUITE,
                    self.text.replace('vcsr=5', 'vcsr=0', 1),
                    self.text.replace('variant=rvv', 'variant=paired', 1)):
            with self.assertRaises(ValueError):
                c.original.check_log(bad)

    def test_consumed_evidence_each_required_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'work').mkdir()
            files = [root / 'work' / n for n in c.EVIDENCE_NAMES] + [root / 'source-pins.json']
            for path in files:
                path.write_text('host fixture, not RTL evidence\n')
            pins = c.s.hashes(files)
            c.consumed_evidence(root, dict(evidence_sha256=pins))
            for path in files:
                bad = dict(pins)
                del bad[str(path)]
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'consumed evidence'):
                    c.consumed_evidence(root, dict(evidence_sha256=bad))
            files[0].write_text('drift')
            with self.assertRaises(ValueError):
                c.consumed_evidence(root, dict(evidence_sha256=pins))

    def test_unified_storage_typing(self):
        for variant in (None, 'shared_reader_only', c.STORAGE):
            with patch.object(c, 'checked_soc', return_value=({}, dict(storage_variant=variant), {}, {})):
                if variant == c.STORAGE:
                    self.assertEqual(c.unified_image(Path('/unused')), ({}, {}, {}))
                else:
                    with self.assertRaises(ValueError):
                        c.unified_image(Path('/unused'))

    def test_full_original_simulation_flags_and_timeout(self):
        argv = list(map(str, worker.simulation_command(Path('/simv'), Path('/same.elf'), Path('/work'))))
        for required in ('+PRELOAD=/same.elf', '+AKV_PERF', '+AKV_SUMMARY', '+NO_FSDB',
                         '+COMMIT_TRACE=/work/commit_trace.csv', '+VECTOR_TRACE=/work/vector_trace.csv',
                         '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'):
            self.assertEqual(argv.count(required), 1)
        for timeout in (1, 9000, 10800):
            worker.validate_timeout(timeout)
        for timeout in (0, 10801, True, 3.5):
            with self.assertRaises(ValueError):
                worker.validate_timeout(timeout)


class HistoricalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = b'exact historical fixture, not production source\n'
        self.sha = hashlib.sha256(self.data).hexdigest()
        names = {'software/old.c': self.sha}
        patcher = patch.dict(historical.SOURCES, names, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.archive = historical.HistoricalSources(self.root, self.root / 'archive', c.s)

    def materialize(self):
        with patch.object(historical.subprocess, 'check_output', return_value=self.data):
            self.archive.materialize()

    def test_exact_historical_mapping_no_current_source_edit(self):
        self.materialize()
        source = self.root / 'software/old.c'
        source.parent.mkdir()
        source.write_bytes(b'new canonical code must be untouched')
        pins = {str(source): self.sha}
        self.archive.verify(pins)
        translated = self.archive.translate(pins)
        self.assertNotIn(str(source), translated)
        self.assertEqual(translated[str(self.root / 'archive/old.c')], self.sha)
        self.assertEqual(source.read_bytes(), b'new canonical code must be untouched')

    def test_wrong_git_bytes_or_version_rejected(self):
        with patch.object(historical.subprocess, 'check_output', return_value=b'wrong'):
            with self.assertRaisesRegex(ValueError, 'git object'):
                self.archive.materialize()
        self.assertFalse(self.archive.directory.exists())
        self.materialize()
        with self.assertRaisesRegex(ValueError, 'source version'):
            self.archive.verify({str(self.root / 'software/old.c'): '0'*64})

    def test_archive_and_unlisted_pin_drift_rejected(self):
        self.materialize()
        unlisted = self.root / 'unlisted.c'
        unlisted.write_bytes(self.data)
        pins = {str(unlisted): self.sha}
        self.archive.verify(pins)
        unlisted.write_bytes(b'drift')
        with self.assertRaises(ValueError):
            self.archive.verify(pins)
        (self.archive.directory / 'old.c').write_bytes(b'drift')
        with self.assertRaises(ValueError):
            self.archive.checked_pins()

    def test_private_validator_code_identical_no_global_patching(self):
        old_verify = c.original.checked_build.__globals__['verify_pins']
        build, prior = self.archive.validators(c.original, c.context)
        self.assertIs(build.__code__, c.original.checked_build.__code__)
        self.assertIs(prior.__code__, c.context.checked_prerequisite.__code__)
        self.assertIs(c.original.checked_build.__globals__['verify_pins'], old_verify)
        self.assertIs(prior.__globals__['prior'].checked_build, build)


if __name__ == '__main__':
    unittest.main()
