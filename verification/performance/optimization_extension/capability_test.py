"""Mutation tests for the minimal, fail-closed capability evidence gate."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('capability_gate', Path(__file__).with_name('capability_run.py'))
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def native(expected=1):
    return ('EXT_NATIVE_CAPABILITY_DONE expected=%d actual=%d decoded=%d legacy=0 errors=0\n' %
            (expected, expected, expected) +
            'EXT_NATIVE_WORDS info0=7f01f1ffff100203 info1=2002010400070003 old_words=255 hash=1234567890abcdef errors=0\n')


class CapabilityGate(unittest.TestCase):
    def test_native_both(self):
        for expected in (0, 1):
            self.assertEqual(c.native_check(native(expected), expected)['old_words'], 255)

    def test_native_mutations(self):
        mutations = [('actual=1', 'actual=0'), ('decoded=1', 'decoded=0'), ('legacy=0', 'legacy=1'),
                     ('errors=0', 'errors=1'), ('old_words=255', 'old_words=254')]
        for before, after in mutations:
            with self.subTest(before=before), self.assertRaises(ValueError):
                c.native_check(native().replace(before, after), 1)
        with self.assertRaises(ValueError):
            c.native_check(native() * 2, 1)

    def test_package_derivation(self):
        source = 'initial begin\n    $display("EXT_CAPABILITY_PASS");\nend'
        derived = c.package_bench(source)
        self.assertIn('legacy_qbs_pkg::qbs_capability_word', derived)
        self.assertIn('QbsCooperativeCapabilityIndex != 5', derived)
        self.assertIn('QbsCooperativeQ4KBit != 0', derived)
        with self.assertRaises(ValueError):
            c.package_bench('unrecognized')

    def test_identity_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input'
            path.write_text('original')
            pins = {str(path): c.sha(path)}
            c.verify(pins)
            path.write_text('changed')
            with self.assertRaises(ValueError):
                c.verify(pins)

    def test_protocol_fail_closed(self):
        image = dict(simv='simv', image_pins={'simv': 'sha', 'simv.daidir/design.so': 'library'})
        proof = dict(status='PASS', issues=[], elf_sha256='sha', simv_sha256='sha', log_sha256='sha',
            sim_image_sha256=image['image_pins'], contract_counts=dict(requests=320, responses=320,
                exceptions=0, protocol_errors=0, outstanding=0, mmu_request_cycles=0),
            backend_counts=dict(allocations=0, completions=0, aborted=0, max_live=0),
            uvm_backend_event_count=0, axi_read_counts=dict(ar=0, pending=0), axi_write_counts=dict(aw=0, pending=0))
        with patch.object(c, 'sha', return_value='sha'):
            c.protocol_check(proof, image, 'elf', 'log')
            for group, key in (('contract_counts', 'exceptions'), ('contract_counts', 'outstanding'),
                               ('contract_counts', 'mmu_request_cycles'), ('backend_counts', 'allocations'),
                               ('axi_read_counts', 'ar'), ('axi_write_counts', 'aw')):
                broken = copy.deepcopy(proof)
                broken[group][key] = 1
                with self.subTest(group=group, key=key), self.assertRaises(ValueError):
                    c.protocol_check(broken, image, 'elf', 'log')
            for key in ('elf_sha256', 'simv_sha256', 'log_sha256'):
                broken = copy.deepcopy(proof)
                broken[key] = 'wrong'
                with self.subTest(key=key), self.assertRaises(ValueError):
                    c.protocol_check(broken, image, 'elf', 'log')

    def test_output_policy(self):
        self.assertEqual(c.output(c.OUT / 'optimization_extension_capability_20261111_01').parent, c.OUT)
        with self.assertRaises(ValueError):
            c.output(c.ROOT / 'verification/out/optimization_extension_capability_20261111_01')


if __name__ == '__main__':
    unittest.main(verbosity=2)
