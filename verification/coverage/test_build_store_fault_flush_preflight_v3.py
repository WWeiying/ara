import ast
from pathlib import Path
import unittest
from unittest.mock import patch

import build_store_fault_flush_preflight_v3 as p


class MemoryAdapterTests(unittest.TestCase):
    def test_real_source_only_single_memory_option_changes(self):
        source = Path(p.guarded.frozen.__file__).read_text()
        result = p.adapted_source(source)
        self.assertEqual(result.replace(p.NEW, p.OLD), source)
        tree = ast.parse(result)
        command = next(n for n in ast.walk(tree) if isinstance(n, ast.Dict) and
                       any(isinstance(k, ast.Constant) and k.value == 'spike' for k in n.keys))
        spike = command.values[next(i for i,k in enumerate(command.keys)
                                    if isinstance(k, ast.Constant) and k.value == 'spike')]
        flags = [n.value for n in spike.elts if isinstance(n, ast.Constant)]
        self.assertEqual(flags, ['--isa=rv64gcv_zvl1024b', '--priv=msu', '--pmpregions=0',
                                 p.RAM, '-l', '--log-commits'])

    def test_missing_and_ambiguous_anchor_rejected(self):
        for source in ('none', p.OLD + p.OLD, p.NEW):
            with self.assertRaisesRegex(ValueError, 'single Spike'): p.adapted_source(source)

    def test_foreign_predecessor_rejected_before_execution(self):
        with patch.object(p.life, 'digest', return_value='foreign'):
            with self.assertRaisesRegex(ValueError, 'predecessor drift'): p.load_adapter()

    def test_existing_failed_output_not_reused(self):
        with self.assertRaisesRegex(ValueError, 'Fresh independent'): p.build(p.FAILED)

    def test_exact_strict_oracle_preserved(self):
        adapter = p.load_adapter()
        original = p.guarded.frozen.validate
        self.assertEqual(adapter['validate'].__code__.co_code, original.__code__.co_code)
        self.assertEqual(adapter['validate'].__code__.co_consts, original.__code__.co_consts)
        self.assertEqual(adapter['CHECKS'], 134)
        self.assertEqual(adapter['BAD'], 0xe0000000)
        self.assertEqual(adapter['OFFSETS'], p.guarded.frozen.OFFSETS)

    def test_ram_excludes_fault_and_includes_stack(self):
        base, size = [int(x, 16) for x in p.RAM[2:].split(':')]
        self.assertTrue(base <= 0x801fff90 < base + size)
        self.assertFalse(base <= p.guarded.frozen.BAD < base + size)
        self.assertTrue(0x80000000 <= p.guarded.frozen.BAD < 0x80000000 + 2048*1024*1024)

    def test_frozen_v2_drift_rejects_before_static(self):
        with patch.object(p.life, 'digest', return_value='foreign'), \
             patch.object(p.guarded, 'static') as static:
            with self.assertRaisesRegex(ValueError, 'v2 drift'): p.static()
            static.assert_not_called()


if __name__ == '__main__':
    unittest.main()
