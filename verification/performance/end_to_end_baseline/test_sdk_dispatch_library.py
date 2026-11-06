"""Fail-closed tests for the one-member SDK dispatch archive integration."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import build_sdk_dispatch_library as target


def member(name, data):
    header = f'{name:<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'.encode()
    return header + data + (b'\n' if len(data) % 2 else b'')


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.before = [('same.o', b'first'), (target.MEMBER, b'old'), ('same.o', b'second')]
        self.after = [('same.o', b'first'), (target.MEMBER, b'new'), ('same.o', b'second')]

    def test_only_runtime_replaced_duplicate_other_names_preserved(self):
        evidence = target.compare_member_archives(self.before, self.after, target.MEMBER, b'new')
        self.assertEqual([e['changed'] for e in evidence], [False, True, False])

    def test_generic_member_not_hardcoded_to_qbs(self):
        evidence = target.compare_member_archives([('any.o', b'x')], [('any.o', b'y')], 'any.o', b'y')
        self.assertEqual(evidence[0]['after_sha256'], target.sha(b'y'))

    def test_reject_stale_wrong_extra_removed_reordered_or_other_delta(self):
        bad = [self.before, self.after + [('extra.o', b'x')], self.after[:-1],
               list(reversed(self.after)), [('same.o', b'wrong')] + self.after[1:],
               self.after[:1] + [(target.MEMBER, b'wrong')] + self.after[2:]]
        for after in bad:
            with self.subTest(after=after), self.assertRaises(ValueError):
                target.compare_member_archives(self.before, after, target.MEMBER, b'new')

    def test_reject_missing_or_duplicate_replacement(self):
        for before, after in (([('x.o', b'x')], [('x.o', b'x')]),
                              (self.before + [(target.MEMBER, b'old')],
                               self.after + [(target.MEMBER, b'new')])):
            with self.assertRaises(ValueError):
                target.compare_member_archives(before, after, target.MEMBER, b'new')

    def test_parser_preserves_long_names_and_rejects_thin_or_truncation(self):
        raw = b'!<arch>\n' + member('//', b'qbs_runtime.c.o/\n') + member('/0', b'x')
        self.assertEqual(target.archive_members(raw), [(target.MEMBER, b'x')])
        for bad in (b'!<thin>\n', raw[:-1]):
            with self.assertRaises(ValueError):
                target.archive_members(bad)

    @unittest.skipUnless(shutil.which('ar'), 'host ar unavailable')
    def test_real_ar_replacement_with_duplicate_other_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib = root / 'lib.a'
            lib.write_bytes(b'!<arch>\n' + b''.join(member(n + '/', d) for n, d in self.before))
            obj = root / target.MEMBER
            obj.write_bytes(b'new')
            subprocess.run([shutil.which('ar'), 'rD', str(lib), str(obj)], check=True, capture_output=True)
            target.compare_member_archives(self.before, target.archive_members(lib.read_bytes()),
                                           target.MEMBER, b'new')


class RecipeTests(unittest.TestCase):
    def entry(self, extra=()):
        argv = ['/cc', '-DGGML_USE_RISCV_QBS', '-I/sealed/include', '-O3',
                '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-std=gnu11', *extra,
                '-o', 'relative/runtime.o', '-c', str(target.SOURCE)]
        return dict(file=str(target.SOURCE), arguments=argv, directory='/original/cwd')

    def test_native_flags_preserved_only_source_and_output_replaced(self):
        entry = self.entry()
        _, argv = target.command_entry([entry], target.SOURCE)
        actual = target.compile_command(argv, Path('/candidate/qbs_runtime.c'), Path('/out/object.o'))
        self.assertEqual(actual[:-4], argv[:-4])
        self.assertEqual(actual[-4:], ['-o', '/out/object.o', '-c', '/candidate/qbs_runtime.c'])
        self.assertEqual(argv, entry['arguments'])

    def test_reject_unaccepted_command_or_source(self):
        entry = self.entry()
        for entries, source in (([], target.SOURCE), ([entry, entry], target.SOURCE),
                                ([entry], Path('/other/qbs_runtime.c'))):
            with self.assertRaises(ValueError):
                target.command_entry(entries, source)

    def test_reject_hidden_inputs_shell_namespace_or_dependency_outputs(self):
        for token in ('@response', '-fplugin=bad', '-specs=bad', '--sysroot=/other',
                      '-B/other', '-include', '-isystem', '-I', '-MMD', '-MD',
                      '-Dqbs_execute=baseline_qbs_execute', '&&', '-save-temps'):
            with self.subTest(token=token), self.assertRaises(ValueError):
                target.command_entry([self.entry([token])], target.SOURCE)

    def test_preprocessing_preserves_flags_and_source_not_output(self):
        argv = self.entry()['arguments']
        actual = target.preprocess_command(argv, '-M', '-MT', 'object')
        self.assertNotIn('-c', actual)
        self.assertNotIn('-o', actual)
        self.assertNotIn('relative/runtime.o', actual)
        self.assertIn(str(target.SOURCE), actual)
        self.assertEqual(actual[-3:], ['-M', '-MT', 'object'])

    def test_export_multiset_detects_removed_duplicate_and_type_change(self):
        before = target.exports('lib[a.o]:\nfoo T 0 1\nfoo T 2 1\nbar W 0 1\n')
        self.assertEqual(before, target.exports('bar W 0 3\nfoo T 4 1\nfoo T 8 9\n'))
        self.assertNotEqual(before, target.exports('bar W 0 1\nfoo T 0 1\n'))
        self.assertNotEqual(before, target.exports('bar T 0 1\nfoo T 0 1\nfoo T 0 1\n'))

    def test_fresh_attempt_preserves_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.object(target, 'RUNS', root):
                first = target.fresh_attempt(root / 'run')
                (first / 'result.json').write_text('{"state":"FAIL"}')
                second = target.fresh_attempt(root / 'run')
                self.assertEqual(second.name, 'attempt-02')
                self.assertEqual((first / 'result.json').read_text(), '{"state":"FAIL"}')
                with self.assertRaises(ValueError):
                    target.fresh_attempt(root.parent / 'outside')

    def test_pins_reject_content_or_symlink_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            b = target.Build(root)
            a, other, link = root / 'a', root / 'other', root / 'link'
            a.write_bytes(b'a')
            other.write_bytes(b'a')
            link.symlink_to(a)
            b.pin(link)
            link.unlink()
            link.symlink_to(other)
            with self.assertRaises(ValueError):
                b.verify()


if __name__ == '__main__':
    unittest.main()
