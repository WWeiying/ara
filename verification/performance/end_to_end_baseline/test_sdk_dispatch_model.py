from pathlib import Path
import unittest

from sdk_dispatch_model import guest_listing, recipe, relink


class ModelDispatchGates(unittest.TestCase):
    def setUp(self):
        self.obj = Path('/prior/model.o')
        self.old = Path('/old/libggml-cpu.a')
        self.new = Path('/new/libggml-cpu.a')
        self.output = Path('/prior/candidate')
        self.target = Path('/new/candidate')
        self.command = ['/compiler', '-static', str(self.obj), '/shared/libllama.a', str(self.old),
                        '/shared/libggml-base.a', '-ldl', '-lm', '-pthread', '-o', str(self.output)]

    def test_relink_changes_only_archive_and_output(self):
        new = relink(self.command, self.obj, self.old, self.new, self.output, self.target)
        changes = [(a, b) for a, b in zip(self.command, new) if a != b]
        self.assertEqual(changes, [(str(self.old), str(self.new)), (str(self.output), str(self.target))])

    def test_duplicate_or_missing_inputs_rejected(self):
        for token in (str(self.obj), str(self.old), str(self.output), '-o'):
            for command in (self.command + [token], [v for v in self.command if v != token]):
                with self.subTest(token=token, command=command), self.assertRaises(ValueError):
                    relink(command, self.obj, self.old, self.new, self.output, self.target)

    def test_output_must_be_real_output_operand(self):
        wrong = list(self.command)
        wrong[-1], wrong[-2] = wrong[-2], wrong[-1]
        with self.assertRaises(ValueError):
            relink(wrong, self.obj, self.old, self.new, self.output, self.target)

    def test_fixed_guest_driver_and_both_variants(self):
        listing = guest_listing(Path('/init'), Path('/prior/candidate'), Path('/new/candidate'), Path('/prior/test'))
        self.assertEqual(listing.splitlines()[4:], [
            'file /init /init 755 0 0', 'file /base /prior/candidate 755 0 0',
            'file /candidate /new/candidate 755 0 0', 'file /test /prior/test 755 0 0'])

    def test_listing_path_injection_rejected(self):
        for path in (Path('relative'), Path('/foo bar'), Path('/foo\nfile')):
            with self.subTest(path=path), self.assertRaises(ValueError):
                guest_listing(path, self.output, self.target, self.obj)

    def test_command_missing_or_duplicate_rejected(self):
        item = dict(label='link', argv=['compiler', '-static'])
        self.assertEqual(recipe([item], 'link'), item['argv'])
        for records in ([], [item, item]):
            with self.assertRaises(ValueError):
                recipe(records, 'link')


if __name__ == '__main__':
    unittest.main()
