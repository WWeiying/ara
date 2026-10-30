"""Host mutations and isolation tests; synthetic logs are not RTL evidence."""
import copy
from pathlib import Path
import tempfile
import unittest

import baseline as b
import preflight as p
from threeway_run_test import fixture


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.consumer = b.Consumer()

    def historical_pins(self):
        pins = {str(b.ROOT / name): sha for name, sha in b.a.CHANGED.items()}
        pins.update({name: row['sha256'] for name, row in self.consumer.history.bindings().items()})
        return pins

    def test_exact_seven_translations_and_original_map_unchanged(self):
        pins = self.historical_pins()
        header = b.ROOT / 'hardware/include/ara_pkg.sv'
        pins[str(header)] = b.s.digest(header)
        before = dict(pins)
        mapped = self.consumer.translate(pins)
        self.assertEqual(pins, before)
        self.assertTrue(set(self.historical_pins()).isdisjoint(mapped))
        self.assertEqual(mapped[str(header)], pins[str(header)])
        for name, sha in b.a.CHANGED.items():
            self.assertEqual(mapped[str(self.consumer.archive.payload / name)], sha)
        for original, binding in self.consumer.history.bindings().items():
            self.assertEqual(mapped[binding['archived']], pins[original])
        b.s.verify_pins(mapped)

    def test_every_wrong_historical_hash_rejects(self):
        for name in self.historical_pins():
            bad = self.historical_pins()
            bad[name] = '0' * 64
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.consumer.verify(bad)

    def test_archive_collision_and_unreviewed_manifest_reject(self):
        bad = self.historical_pins()
        name = next(iter(b.a.CHANGED))
        bad[str(self.consumer.archive.payload / name)] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.consumer.translate(bad)
        with self.assertRaisesRegex(ValueError, 'receipt drift'):
            b.a.Archive(b.ARCHIVE, '0' * 64)
        bad = self.historical_pins()
        target = next(iter(self.consumer.history.bindings().values()))['archived']
        bad[target] = '0' * 64
        with self.assertRaises(ValueError):
            self.consumer.translate(bad)

    def test_unlisted_drift_is_not_historical(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'unchanged.sv'
            path.write_text('original')
            pins = {str(path): b.s.digest(path)}
            self.consumer.verify(pins)
            path.write_text('changed')
            with self.assertRaises(ValueError):
                self.consumer.verify(pins)
        pins = {str(b.ROOT / 'hardware/include/ara_pkg.sv'): '0' * 64}
        with self.assertRaises(ValueError):
            self.consumer.verify(pins)

    def test_complete_clone_graph_no_module_mutations(self):
        original, context, contract = b.contract.original, b.contract.context, b.contract
        functions = (original.checked_build, original.checked_image, context.checked_prerequisite,
                     contract.consumed_evidence, contract.checked_baseline)
        snapshots = [dict(f.__globals__) for f in functions]
        cloned = self.consumer.validators()
        replacements = (cloned.build, cloned.image, cloned.prerequisite, cloned.evidence, cloned.baseline)
        for old, new, before in zip(functions, replacements, snapshots):
            self.assertIs(old.__code__, new.__code__)
            self.assertIsNot(old.__globals__, new.__globals__)
            self.assertEqual(set(old.__globals__), set(before))
            self.assertTrue(all(old.__globals__[k] is v for k, v in before.items()))
        bg = cloned.baseline.__globals__
        self.assertIs(bg['original'].checked_build, cloned.build)
        self.assertIs(bg['s'].checked_image, cloned.image)
        self.assertIs(bg['context'].checked_prerequisite, cloned.prerequisite)
        self.assertIs(bg['consumed_evidence'], cloned.evidence)
        self.assertIs(cloned.prerequisite.__globals__['prior'].checked_build, cloned.build)
        for verify in (cloned.build.__globals__['verify_pins'], cloned.image.__globals__['verify_pins'],
                       cloned.prerequisite.__globals__['s'].verify_pins,
                       cloned.evidence.__globals__['s'].verify_pins, bg['s'].verify_pins):
            self.assertEqual(verify, self.consumer.verify)

    def test_actual_after_tree_and_guard(self):
        pins = p.after_tree(self.consumer)
        self.assertGreaterEqual(len(pins), 19)
        guard = p.ReadGuard(self.consumer)
        for path in guard.forbidden:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Forbidden'):
                guard('open', (str(path), 'rb', 0))
        for event in ('os.scandir', 'os.listdir'):
            with self.assertRaisesRegex(ValueError, 'scan forbidden'):
                guard(event, (str(guard.include),))
        with self.assertRaisesRegex(ValueError, 'external process'):
            guard('subprocess.Popen', ('simv',))
        for path in self.consumer.translate(self.historical_pins()):
            guard('open', (path, 'rb', 0))
        guard('open', (str(b.ROOT / 'hardware/include/ara_pkg.sv'), 'rb', 0))
        self.assertGreater(guard.opens, 7)

    def test_other_baseline_build_rejected_before_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'Only the reviewed'):
                self.consumer.checked_baseline(Path(tmp), Path(tmp))

    def test_raw_record_missing_and_fake_pass_reject(self):
        text = fixture()
        parsed = b.contract.original.check_log(text)
        self.assertEqual(len(parsed['trials']), 6)
        rows = [line for line in text.splitlines() if line.startswith('[AKV_PERF] ')]
        self.assertEqual(len(rows), 3864)
        for bad in (b.contract.original.SUITE, text.replace(rows[0] + '\n', '', 1),
                    text.replace('vcsr=5', 'vcsr=0', 1)):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                b.contract.original.check_log(bad)

    def test_per_call_regression_and_offsetting_records_still_reject(self):
        text = fixture()
        parsed = b.contract.original.check_log(text)
        rows = [b.s.numeric_fields(line[len('[AKV_PERF] '):], b.s.PERF_FIELDS)
                for line in text.splitlines() if line.startswith('[AKV_PERF] ')]
        bad = copy.deepcopy(parsed)
        bad['trials'][0]['cycles'] += 1
        bad['trials'][1]['cycles'] -= 1
        self.assertEqual(b.contract.compare(parsed, bad, rows, rows)['state'], 'FAIL')
        changed = copy.deepcopy(rows)
        changed[0]['busy_cycles'] += 1
        changed[1]['busy_cycles'] -= 1
        with self.assertRaisesRegex(ValueError, 'Per-command'):
            b.contract.compare(parsed, parsed, rows, changed)


if __name__ == '__main__':
    unittest.main()
