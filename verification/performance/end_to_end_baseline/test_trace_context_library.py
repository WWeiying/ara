"""Fail-closed unit tests for the isolated trace-context archive builder."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import build_trace_context_library as target


def member(name, payload):
    header = f'{name:<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(payload):<10}`\n'.encode()
    return header + payload + (b'\n' if len(payload) % 2 else b'')


class ArchiveTests(unittest.TestCase):
    def test_duplicates_long_names_and_symbol_metadata(self):
        raw = (b'!<arch>\n' + member('/', b'index') + member('//', b'long-object-name.cpp.o/\n') +
               member('same.o/', b'a') + member('/0', b'long') + member('same.o/', b'b'))
        self.assertEqual(target.archive_members(raw),
                         [('same.o', b'a'), ('long-object-name.cpp.o', b'long'), ('same.o', b'b')])

    def test_malformed_archives(self):
        valid = b'!<arch>\n' + member('qbs.cpp.o/', b'old')
        for raw in (b'!<thin>\n', valid[:-1], valid[:20], b'!<arch>\n' + member('/999', b'x'),
                    b'!<arch>\n' + member('#1/4', b'namepayload')):
            with self.subTest(raw=raw), self.assertRaises((ValueError, UnicodeError)):
                target.archive_members(raw)

    def test_exact_replacement_with_duplicate_other_members(self):
        before = [('runtime.c.o', b'a'), (target.MEMBER, b'old'), ('runtime.c.o', b'b')]
        after = [('runtime.c.o', b'a'), (target.MEMBER, b'new'), ('runtime.c.o', b'b')]
        evidence = target.compare_archives(before, after, b'new')
        self.assertEqual([e['changed'] for e in evidence], [False, True, False])

    def test_reject_stale_duplicate_reordered_or_changed_member(self):
        before = [('x.o', b'x'), (target.MEMBER, b'old')]
        bad = [before, before + [(target.MEMBER, b'new')],
               [(target.MEMBER, b'new'), ('x.o', b'x')],
               [('x.o', b'bad'), (target.MEMBER, b'new')],
               [('x.o', b'x'), (target.MEMBER, b'wrong')]]
        for after in bad:
            with self.subTest(after=after), self.assertRaises(ValueError):
                target.compare_archives(before, after, b'new')

    @unittest.skipUnless(shutil.which('ar'), 'host ar unavailable')
    def test_real_ar_replacement_preserves_duplicate_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib = root / 'lib.a'
            lib.write_bytes(b'!<arch>\n' + member('same.o/', b'first') +
                            member('qbs.cpp.o/', b'old') + member('same.o/', b'second'))
            before = target.archive_members(lib.read_bytes())
            obj = root / target.MEMBER
            obj.write_bytes(b'new')
            subprocess.run([shutil.which('ar'), 'rD', str(lib), str(obj)], check=True, capture_output=True)
            target.compare_archives(before, target.archive_members(lib.read_bytes()), b'new')


class InputTests(unittest.TestCase):
    def test_command_selection_and_flags_untouched(self):
        source = Path('/sealed/llama') / target.SOURCE
        argv = ['/compiler', '-O3', '-march=rv64gcv', '-march=rv64gcv_zfh_zvfh',
                '-o', 'relative/qbs.cpp.o', '-c', str(source)]
        entry = dict(file=str(source), directory='/unused-dirty-cwd', arguments=argv)
        _, actual = target.command_entry([entry], source)
        self.assertEqual(actual, argv)
        for entries in ([], [entry, entry]):
            with self.assertRaises(ValueError):
                target.command_entry(entries, source)
        with self.assertRaises(ValueError):
            target.command_entry([entry], Path('/dirty') / target.SOURCE)

    def test_reject_hidden_inputs_and_shell_tokens(self):
        source = Path('/sealed/llama') / target.SOURCE
        for token in ('@response', '-fplugin=bad', '--sysroot=/dirty', '-I', '-include', '-MMD', '&&'):
            entry = dict(file=str(source), arguments=['/cc', token, '-o', 'a.o', '-c', str(source)])
            with self.subTest(token=token), self.assertRaises(ValueError):
                target.command_entry([entry], source)

    def test_remap_sealed_includes_and_reject_dirty_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph = root / 'graph'
            for name in ('llama/ggml/src', 'sdk/software/qbs/include', 'dirty'):
                (graph / name).mkdir(parents=True)
            argv = ['/cc', '-I' + str(graph / 'llama/ggml/src/..'),
                    '-I' + str(graph / 'sdk/software/qbs/include'), '-O3',
                    '-o', 'qbs.cpp.o', '-c', str(graph / 'llama' / target.SOURCE)]
            mapped = target.remap_command(argv, graph, root / 'inputs', root / 'objects/qbs.cpp.o')
            self.assertEqual(mapped[1], '-I' + str(root / 'inputs/llama/ggml'))
            self.assertEqual(mapped[3], '-O3')
            argv[1] = '-I' + str(graph / 'dirty')
            with self.assertRaises(ValueError):
                target.remap_command(argv, graph, root / 'inputs', root / 'qbs.cpp.o')

    def test_dependency_rule_escaped_space_and_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'source.cpp').touch()
            (root / 'header space.h').touch()
            deps = target.dependencies('object: source.cpp ' + '\\\n' + ' header\\ space.h\n', root)
            self.assertEqual(deps, {root / 'source.cpp', root / 'header space.h'})
            with self.assertRaises(ValueError):
                target.dependencies('object: source.cpp\nsecond: source.cpp', root)

    def test_pins_fail_on_bad_hash_mutation_and_symlink_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            b = target.Build(root)
            source = root / 'source'
            source.write_bytes(b'original')
            with self.assertRaises(ValueError):
                b.pin(source, target.AFTER)
            b.pin(source)
            source.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                b.verify()
            source.write_bytes(b'original')
            link = root / 'alias'
            link.symlink_to(source)
            b.pin(link)
            other = root / 'other'
            other.write_bytes(b'original')
            link.unlink()
            link.symlink_to(other)
            with self.assertRaises(ValueError):
                b.verify()

    def test_export_order_independent_but_count_and_type_sensitive(self):
        before = target.exports('archive[a.o]:\nfoo T 10 20\nbar W 0 1\nfoo T 20 20\n')
        after = target.exports('archive[b.o]:\nbar W 0 2\nfoo T 40 30\nfoo T 50 30\n')
        self.assertEqual(before, after)
        self.assertNotEqual(before, target.exports('foo T 0 1\nbar W 0 1\n'))
        self.assertNotEqual(before, target.exports('foo W 0 1\nbar W 0 1\nfoo T 0 1\n'))


class RegisteredPatchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('patch'), 'patch unavailable')
    def test_registered_patch_preimage_postimage_and_reapply_rejection(self):
        sealed = target.GRAPH / 'llama' / target.SOURCE
        if not sealed.is_file():
            self.skipTest('sealed delivery input unavailable')
        self.assertEqual(target.digest(sealed), target.BEFORE)
        patch = target.HERE / 'trace-context.patch'
        self.assertEqual(target.digest(patch), target.PATCH)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / target.SOURCE
            source.parent.mkdir(parents=True)
            shutil.copyfile(sealed, source)
            command = [shutil.which('patch'), '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch)]
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            self.assertEqual(target.digest(source), target.AFTER)
            self.assertNotEqual(subprocess.run(command, cwd=root, capture_output=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
