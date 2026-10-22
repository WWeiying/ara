import json
import unittest
from unittest.mock import Mock, patch

import audit_uvm_no_traffic_719_snapshot as subject
from audit_historical_nonpass_717 import Audit


class SnapshotTests(unittest.TestCase):
    def test_exact_snapshot_and_build_mapping(self):
        proof = subject.bind_snapshot(Audit())
        self.assertTrue(proof["exact_compiled_source_match"])
        self.assertFalse(proof["current_hardware_source_read"])
        self.assertEqual(len(proof["evidence"]), 5)

    def test_original_inputs_never_read_current_rtl(self):
        a = Mock()
        subject.original_inputs(a, dict(inputs={str(subject.HARDWARE_PATH): "old", "/safe": "digest"}, outputs={}))
        a.pin.assert_called_once_with("/safe", "digest")

    def test_wrong_snapshot_or_build_hash_rejected(self):
        with patch.object(subject, "SNAPSHOT_SHA", "0" * 64):
            with self.assertRaisesRegex(ValueError, "Hardware build mapping"):
                subject.bind_snapshot(Audit())
        a = Mock()
        a.pin.side_effect = ValueError("snapshot drift")
        with self.assertRaises(ValueError):
            subject.bind_snapshot(a)

    def test_original_policies_not_promoted(self):
        cases = json.loads((subject.ORIGINAL / "diagnosis.json").read_text())["cases"]
        result = subject.policy_summary(cases)
        self.assertEqual(result["require_contract_false"], 26)
        self.assertFalse(result["full_isa_differential_pass_claimed"])
        cases[0]["original_oracle"]["policy"]["require_contract"] = True
        with self.assertRaises(ValueError):
            subject.policy_summary(cases)

    def test_backend_emission_in_config_rejected(self):
        text = subject.SNAPSHOT.read_text().replace("OPCFG: begin: opcfg", "OPCFG: begin: opcfg\nara_req_valid = 1'b1;", 1)
        with self.assertRaisesRegex(ValueError, "backend validity"):
            subject.blocks(text)


if __name__ == "__main__":
    unittest.main()
