"""The new adapter retains original known-byte and policy rejection gates."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(ROOT / 'verification/coverage'),
               str(ROOT / 'hardware/fpga/ara_dsa_vcu118/software/vendor/pyelftools-0.32-py3-none-any.whl')]
from audit_pending_rvv_20261016 import CASES, prefix
from unittest.mock import patch
from types import SimpleNamespace


class OracleTests(unittest.TestCase):
    def test_exact_disjoint_selection(self):
        self.assertEqual(CASES, (730, 739, 743, 762, 767, 774, 775, 796, 797))

    def test_missing_reference_terminal_rejected(self):
        with patch('ara_verify.spike_trace.parse_spike_commits', return_value=[
                SimpleNamespace(pc=0x80000000, memory_accesses=())]):
            with self.assertRaisesRegex(ValueError, 'terminal'):
                prefix(Path('/unused'), 0x80001000)

    def test_entry_and_successful_terminal_required(self):
        rows = [SimpleNamespace(pc=0x1000, memory_accesses=()),
                SimpleNamespace(pc=0x80000000, memory_accesses=()),
                SimpleNamespace(pc=0x80000004, memory_accesses=((0x80001000, 1),)),
                SimpleNamespace(pc=0x80000008, memory_accesses=())]
        with patch('ara_verify.spike_trace.parse_spike_commits', return_value=rows):
            self.assertEqual(prefix(Path('/unused'), 0x80001000), rows[1:3])

    def test_unknown_business_byte_rejected(self):
        from qualify_operand_mask_data_02_defined import byte_gate
        with self.assertRaisesRegex(ValueError, 'Unknown actual defined'):
            byte_gate(3, 8, 0, None, 0, 8)

    def test_mask_tail_exception_not_applied_to_active_bits(self):
        from qualify_operand_mask_data_02_defined import byte_gate
        with self.assertRaisesRegex(ValueError, 'Unknown actual defined'):
            byte_gate(13, 1, 15, None, 0, 1)
        self.assertFalse(byte_gate(13, 1, 16, None, 0, 1))

    def test_corrupt_vector_summary_rejected(self):
        from collect_vsmul_saturation796 import generic_gate
        with self.assertRaises((ValueError, KeyError)):
            generic_gate(dict(status='FAIL'))


if __name__ == '__main__':
    unittest.main()
