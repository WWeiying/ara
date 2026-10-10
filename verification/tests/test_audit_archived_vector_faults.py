import tempfile
import unittest
from pathlib import Path

from audit_archived_vector_faults import assess_bytes, bounded_input


class ArchivedFaultAuditTests(unittest.TestCase):
    def test_known_identity(self):
        result = assess_bytes({(2, 1): (0x12, 1)}, {2: 0x1234}, {})
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(result["unresolved_bytes"], [])

    def test_changed_byte_is_not_identity(self):
        result = assess_bytes({(2, 1): (0x13, 1)}, {2: 0x1234}, {})
        self.assertEqual(result["mismatches"], [[2, 1, 0x13, 0x12]])

    def test_unknown_prior_never_becomes_proof(self):
        result = assess_bytes({(2, 1): (0x12, 1)}, {2: 0x1234}, {2: 0xff00})
        self.assertEqual(result["unresolved_bytes"], [[2, 1]])

    def test_unknown_actual_never_becomes_proof(self):
        result = assess_bytes({(2, 1): (None, 1)}, {2: 0x1234}, {})
        self.assertEqual(result["unresolved_bytes"], [[2, 1]])

    def test_missing_register_never_assumed_zero(self):
        result = assess_bytes({(2, 0): (0, 1)}, {}, {})
        self.assertEqual(result["unresolved_bytes"], [[2, 0]])

    def test_empty_writes_only_report_zero_evidence(self):
        self.assertEqual(assess_bytes({}, {}, {})["observed_bytes"], 0)

    def test_partial_effect_is_not_identity_but_can_match_post_state(self):
        actual = {(20, 4): (0xab, 1)}
        self.assertTrue(assess_bytes(actual, {20: 0}, {})["mismatches"])
        self.assertEqual(assess_bytes(actual, {20: 0xab << 32}, {})["mismatches"], [])

    def test_oversize_input_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "log"
            path.write_bytes(b"12345")
            with self.assertRaisesRegex(ValueError, "Refusing full parse"):
                bounded_input(path, limit=4)
            self.assertEqual(bounded_input(path, limit=5)["bytes"], 5)


if __name__ == "__main__":
    unittest.main()
