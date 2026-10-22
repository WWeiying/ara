import copy
import json
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

import run_gap111_simulation as r


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((r.PRE / 'preflight-manifest.json').read_bytes())

    def test_exact_software_preflight(self):
        self.assertGreater(len(r.validate(self.pre)), 15)

    def test_false_overlap_claim(self):
        self.pre['runtime_overlap_proven'] = True
        with self.assertRaises(ValueError): r.validate(self.pre)

    def test_wrong_ELF_rejected(self):
        self.pre['output_pins'][str(r.PRE / 'input.elf')] = '0' * 64
        with self.assertRaises(ValueError): r.validate(self.pre)

    def test_wrong_population_rejected(self):
        self.pre['baseline_tests'] = 741
        with self.assertRaises(ValueError): r.validate(self.pre)

    def test_software_boundary_rejected(self):
        self.pre['validation']['scalar_counts']['instructions'] -= 1
        with self.assertRaises(ValueError): r.validate(self.pre)

    def test_command_no_FSDB_fixed_image(self):
        out = r.life.OUT / 'gap111-test-never-run'
        command = r.command(out)
        self.assertEqual(command[0], str(r.life.IMAGE))
        self.assertIn('+NO_FSDB', command)
        self.assertIn('+PRELOAD=' + str(r.PRE / 'input.elf'), command)
        self.assertIn('-cm', command)
        self.assertEqual(r.BUDGET, 180)

    def test_prepared_drift_never_runs(self):
        with patch.object(r, 'manifest', return_value={'expected': True}):
            with self.assertRaises(ValueError): r.invoke_run(r.life.OUT / 'not-created', {})

    def test_private_lifecycle_binding_without_run(self):
        original = r.frozen.run.__globals__['BUDGET']
        self.assertEqual(original, 600)
        self.assertNotEqual(original, r.BUDGET)

    def test_actual_ELF_fits_frozen_L2(self):
        result = r.elf_fit((r.PRE / 'input.elf').read_bytes())
        self.assertEqual(result['L2_bytes'], 2 << 20)
        self.assertEqual(result['entry'], 0x80000000)

    def test_ELF_wrong_entry_rejected(self):
        raw = bytearray((r.PRE / 'input.elf').read_bytes())
        struct.pack_into('<Q', raw, 24, 0x80000004)
        with self.assertRaises(ValueError): r.elf_fit(raw)

    def test_ELF_out_of_memory_rejected(self):
        raw = bytearray((r.PRE / 'input.elf').read_bytes())
        offset = struct.unpack_from('<Q', raw, 32)[0]
        count = struct.unpack_from('<H', raw, 56)[0]
        for i in range(count):
            at = offset + 56 * i
            if struct.unpack_from('<I', raw, at)[0] == 1:
                struct.pack_into('<Q', raw, at + 40, 3 << 20)
                break
        with self.assertRaises(ValueError): r.elf_fit(raw)


if __name__ == '__main__':
    unittest.main()
