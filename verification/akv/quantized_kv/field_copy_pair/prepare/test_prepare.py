import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('field_pair_test_build', HERE / 'build.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class PreparationTests(unittest.TestCase):
    def test_scope(self):
        self.assertEqual(b.WORKLOAD['trial_order'], [0, 1, 2, 2, 1, 0])
        self.assertEqual(b.WORKLOAD['total_outputs'], 4608)
        self.assertEqual(b.WORKLOAD['expected_commands'], 16)
        self.assertEqual(len(b.CHANGED), 5)
        self.assertNotIn(b.NEW, b.CHANGED)

    def test_original_main_recipe(self):
        argv, _ = b.compile_record(b.BASE / 'main.o')
        self.assertIn('-fno-builtin', argv)
        self.assertIn('-ffp-contract=fast', argv)
        deps = b.deps_command(argv)
        self.assertNotIn('-c', deps)
        self.assertNotIn('-o', deps)
        self.assertEqual(deps[-3:], ['-M', '-MT', 'object'])

    def test_invalid_compile(self):
        with self.assertRaises(ValueError):
            b.deps_command(['gcc', '-c', 'a.c', '-o', 'a.o', '-o', 'b.o'])

    def test_translation_only_exact_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / 'archive'
            changed = next(iter(b.CHANGED))
            (old / changed).parent.mkdir(parents=True)
            (old / changed).write_bytes(b'old')
            unchanged = root / 'not-a-header'
            unchanged.write_bytes(b'fixed')
            pins = {str(root / changed): b.sha(old / changed), str(unchanged): b.sha(unchanged)}
            with patch.object(b, 'ROOT', root):
                translated = b.translated(pins, old)
                self.assertEqual(set(translated), {str(old / changed), str(unchanged)})
                unchanged.write_bytes(b'drift')
                with self.assertRaisesRegex(ValueError, 'Historical pin drift'):
                    b.translated(pins, old)

    def test_translation_wrong_blob(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = next(iter(b.CHANGED))
            p = root / 'old' / changed
            p.parent.mkdir(parents=True)
            p.write_bytes(b'wrong')
            with patch.object(b, 'ROOT', root), self.assertRaises(ValueError):
                b.translated({str(root / changed): '0' * 64}, root / 'old')

    def test_live_changed_header_leak(self):
        path = b.ROOT / b.QDIR / 'q8_0_value.h'
        with self.assertRaisesRegex(ValueError, 'Live header leaked'):
            b.check_dependency(path, HERE / 'private', {str(path): b.sha(path)}, {})

    def test_unknown_external_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'header.h'
            p.write_bytes(b'x')
            with self.assertRaisesRegex(ValueError, 'Unproven original'):
                b.check_dependency(p, HERE / 'private', {}, {})

    def test_dependency_protocol(self):
        with self.assertRaises(ValueError):
            b.parse_deps('warning: object: fake')

    def test_ordinary_script(self):
        script = b.layout.script((b.BASE / 'link.ld').read_text())
        self.assertNotIn('__review_main', script)
        self.assertNotIn('. += 0x48', script)
        self.assertIn('*(.text.*)', script)
        self.assertIn('LENGTH = 0x01000000', script)

    def test_source_exact_copy_not_diagnostic(self):
        text = (b.BASE / 'attention_threeway_untimed.c').read_text()
        self.assertIn('THREEWAY_TRIALS = 6', text)
        self.assertNotIn('QUANT_DIAG_HSB_', text)
        self.assertIn('QUANT_THREEWAY_SUITE_PASS', text)

    def test_unknown_generated_assembly(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'fake.S'
            source.write_text('.incbin "fake"\n')
            with self.assertRaisesRegex(ValueError, 'Generated source identity'):
                b.generated_inputs(source, Path(tmp) / 'fake.o', {}, {})

    def test_changed_generated_assembly(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'mask.S'
            source.write_text('fake')
            with self.assertRaisesRegex(ValueError, 'Generated source identity'):
                b.generated_inputs(source, Path(tmp) / 'mask.o', {}, {})

    def test_timed_cfg_branches_and_calls(self):
        rows = [dict(pc=0, encoding='00000000', text='rdcycle a0'),
                dict(pc=4, encoding='00000000', text='beqz a0,c <end>'),
                dict(pc=8, encoding='00000000', text='jalr a5'),
                dict(pc=12, encoding='00000000', text='rdcycle a1')]
        result = b.layout.timed_cfg(rows, [rows[0], rows[-1]])
        self.assertEqual(result['unknown_edges'], [])
        self.assertEqual(len(result['calls']), 1)
        rows[2]['text'] = 'ret'
        with self.assertRaises(ValueError):
            b.layout.timed_cfg(rows, [rows[0], rows[-1]])


if __name__ == '__main__':
    unittest.main()
