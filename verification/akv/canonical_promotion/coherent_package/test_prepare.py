"""Temporary-fixture composition only; no EDA or canonical writes."""
import copy
from pathlib import Path
import tempfile
import unittest

import prepare as p


class CoherentTests(unittest.TestCase):
    def test_accepted_serial_and_aggregate_roundtrip(self):
        inputs, before, modes, expected, sources, steps = p.collect()
        patch, stages = p.exercise(before, modes, expected, steps)
        self.assertEqual(len(expected), 19)
        self.assertEqual(sum(data is None for data in before.values()), 7)
        self.assertEqual(len(stages), 5)
        self.assertEqual(set(sources), set(expected))
        self.assertIn(b'--- /dev/null\n', patch)
        self.assertIn(b'+++ b/Bender.yml\n', patch)
        inputs.verify()

    def test_binding_drift_and_conflicting_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input'
            path.write_bytes(b'first')
            pins = p.Inputs()
            with self.assertRaises(ValueError):
                pins.bind(path, '0' * 64)
            pins.bind(path)
            path.write_bytes(b'second')
            with self.assertRaises(ValueError):
                pins.bind(path)
            with self.assertRaises(ValueError):
                pins.verify()

    def fixture(self):
        before = {'old.txt': b'first\r\nsecond\n', 'added.txt': None}
        after = {'old.txt': b'first\r\nchanged\n', 'added.txt': b'new\n'}
        modes = {name: 0o644 for name in before}
        expected = {name: p.sha(data) for name, data in after.items()}
        step = dict(name='synthetic', input='synthetic', patch=p.make_patch(before, after), after=expected)
        return before, modes, expected, [step]

    def test_mixed_line_endings_and_additions_exact(self):
        before, modes, expected, steps = self.fixture()
        patch, _ = p.exercise(before, modes, expected, steps)
        self.assertIn(b' first\r\n', patch)

    def test_extra_target_cannot_hide_in_patch(self):
        before, modes, expected, steps = self.fixture()
        steps[0]['patch'] += p.make_patch({'unexpected.txt': None}, {'unexpected.txt': b'no\n'})
        with self.assertRaisesRegex(ValueError, 'target set/bytes differ'):
            p.exercise(before, modes, expected, steps)

    def test_wrong_final_or_stage_bytes_rejected(self):
        for which in ('final', 'stage'):
            before, modes, expected, steps = self.fixture()
            if which == 'final':
                expected = {**expected, 'old.txt': '0' * 64}
            else:
                steps = copy.deepcopy(steps)
                steps[0]['after']['old.txt'] = '0' * 64
            with self.subTest(which=which), self.assertRaises(ValueError):
                p.exercise(before, modes, expected, steps)

    def test_unsafe_paths_and_empty_changes_rejected(self):
        for name in ('/absolute', '../escape', 'a/../b', './relative', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                p.target(name)
        with self.assertRaises(ValueError):
            p.make_patch({'same': b'x\n'}, {'same': b'x\n'})

    def test_apply_canonical_or_children_forbidden(self):
        for directory in (p.ROOT, p.ROOT / 'verification'):
            with self.assertRaisesRegex(ValueError, 'independent temporary'):
                p.apply_temp(directory, b'not executed')

    def test_output_scope_and_existing_output_rejected(self):
        for directory in (p.ROOT, p.HERE, p.HERE / 'test_prepare.py'):
            with self.assertRaisesRegex(ValueError, 'fresh output'):
                p.prepare(directory)

    def test_symlink_fixture_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'link').symlink_to('/nonexistent')
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                p.tree(directory)


if __name__ == '__main__':
    unittest.main()
