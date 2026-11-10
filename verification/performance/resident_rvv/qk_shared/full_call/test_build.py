#!/usr/bin/env python3
"""Build and equal-work contract checks; no simulator launch."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('resident_attention_build', HERE/'build.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BuildTests(unittest.TestCase):
    def test_two_wrappers_and_all_old_objects_retained(self):
        commands = b.recipes(Path('/tmp/stage3_attention'), 'abba')
        link = next(c['argv'] for c in commands if c['label']=='link')
        self.assertIn('-Wl,--wrap='+b.QK_SYMBOL, link)
        self.assertIn('-Wl,--wrap='+b.PV_SYMBOL, link)
        self.assertNotIn(str(b.BASE/'00_main.o'), link)
        for index, name in enumerate(('data','crt0','printf','string','serial','util',
                'print_trap_cause','akv_runtime','akv_decode','akv_features',
                'akv_prefill_reference','akv_native_riscv','akv_v2_native_riscv',
                'akv_v2_attention_rvv','akv_attention_rvv'), 1):
            self.assertIn(str(b.BASE/f'{index:02d}_{name}.o'), link)
        for c in commands[:6]:
            self.assertIn('-ffp-contract=off', c['argv'])
            self.assertIn('-fno-fast-math', c['argv'])
            self.assertIn('-DAKV_REFILL_OVERLAP=0', c['argv'])

    def test_smoke_changes_only_main_source_and_paths(self):
        abba, smoke = (b.recipes(Path('/tmp/stage3_attention'), k) for k in ('abba','smoke'))
        self.assertEqual(abba[1:], smoke[1:])
        aa, ss = abba[0]['argv'], smoke[0]['argv']
        self.assertEqual([i for i,(a,s) in enumerate(zip(aa,ss)) if a!=s], [aa.index('-c')+1])

    def test_qk_wrapper_preserves_original_and_calls_shared_leaf(self):
        text = (HERE/'qk_wrap.S').read_text()
        self.assertIn('tail    __real_'+b.QK_SYMBOL, text)
        self.assertIn('tail    akv_experimental_resident_qk', text)
        self.assertIn('resident_pv_rotation_selected', text)
        self.assertNotIn('.word', text)
        self.assertNotIn('vfm', text)

    def test_refuse_reusing_output_before_any_write(self):
        with tempfile.TemporaryDirectory(prefix='stage3_attention_build_') as tmp:
            output = Path(tmp)
            sentinel = output/'build.json'
            sentinel.write_text('original evidence')
            with patch.object(b, 'OUT', output.parent), patch.object(b, 'baseline') as baseline:
                with self.assertRaisesRegex(ValueError, 'Fresh'):
                    b.build(output, 'smoke')
                baseline.assert_not_called()
            self.assertEqual(sentinel.read_text(), 'original evidence')

    def test_dependency_path_normalization_and_missing_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            source = output/'source.c'
            source.write_text('int x;')
            (output/'nested').mkdir()
            for name in b.OBJECTS:
                (output/(name+'.d')).write_text('x.o: '+str(output/'nested/../source.c')+'\n')
            b.dependencies(output, {str(source):b.sha(source)})
            with self.assertRaisesRegex(ValueError, 'Unpinned'):
                b.dependencies(output, {})


if __name__ == '__main__':
    unittest.main()
