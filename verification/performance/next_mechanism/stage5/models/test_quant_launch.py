import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('quant_launch.py')
spec = importlib.util.spec_from_file_location('quant_launch_under_test', SOURCE)
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class QuantLauncherTests(unittest.TestCase):
    def run_launcher(self, drift=None, action='run'):
        original_checker = SOURCE.with_name('prefill_check.py')
        source_hash, checker_hash = '1' * 64, '2' * 64
        pins = {str(original_checker): 'original-checker-pin'}
        loaded = []

        def require(ok, message):
            if not ok:
                raise ValueError(message)

        def merge(target, extra):
            for key, value in extra.items():
                require(key not in target or target[key] == value, 'Conflicting pin')
                target[key] = value

        def base_load(path, name):
            loaded.append((path, name))
            return name

        base = types.SimpleNamespace(load=base_load, merge=merge)
        hashes = {launch.LAUNCH: launch.LAUNCH_SHA, launch.HERE: source_hash,
                  launch.CHECK: checker_hash}
        if drift is not None:
            hashes[drift] = '0' * 64
        fake = types.SimpleNamespace(require=require, sha=lambda p: hashes[p],
            checked=lambda *args: (base, pins), CHECK=original_checker)

        def main():
            checked_base, checked_pins = fake.checked('inputs')
            checked_base.load(original_checker, 'corrected')
            checked_base.load(Path('/other/helper.py'), 'unchanged')
            self.assertEqual(sys.argv, [str(launch.LAUNCH), 'run', '--output', '/out'])
            self.assertEqual(checked_pins[str(original_checker)], 'original-checker-pin')
            self.assertEqual(checked_pins[str(launch.HERE)], source_hash)
            self.assertEqual(checked_pins[str(launch.CHECK)], checker_hash)
            return 0

        fake.main = main
        args = [str(SOURCE), action, '--output', '/out',
                '--quant-launch-sha256', source_hash,
                '--quant-checker-sha256', checker_hash]
        with patch.object(launch, 'load', return_value=fake), patch.object(sys, 'argv', args):
            result = launch.main()
        return result, loaded

    def test_only_checker_is_substituted_and_both_sources_pinned(self):
        rc, loaded = self.run_launcher()
        self.assertEqual(rc, 0)
        self.assertEqual(loaded, [(launch.CHECK, 'corrected'),
                                  (Path('/other/helper.py'), 'unchanged')])

    def test_original_launcher_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Original launcher drift'):
            self.run_launcher(drift=launch.LAUNCH)

    def test_extension_source_drift_rejected(self):
        for path in (launch.HERE, launch.CHECK):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Unreviewed'):
                self.run_launcher(drift=path)

    def test_other_actions_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Execution extension only'):
            self.run_launcher(action='build')


if __name__ == '__main__':
    unittest.main()
