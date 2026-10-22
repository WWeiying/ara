import json
import unittest

import capture_qbs_pending_metadata_v2 as m


class ActualOlderSignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = m.base.OUT / "qbs-pending-native-pilot2-20261006-01"
        cls.config = json.loads((cls.out / "config.json").read_bytes())
        cls.raw = (cls.out / "first.el").read_bytes()

    def test_actual_pilot_exact_signature_and_roundtrip(self):
        rows = m.bind_native(self.raw, self.config)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows, m.bind_native((self.out / "second.el").read_bytes(), self.config))

    def test_false_path_signature_rejected(self):
        for replacement in (b" 1,1\"", b" 0,-\"", b" anything\""):
            with self.assertRaisesRegex(ValueError, "older signature"):
                m.bind_native(self.raw.replace(b' 1,0"', replacement, 1), self.config)

    def test_signature_expression_mutation_rejected(self):
        raw = self.raw.replace(b'.enable 1,0"', b'.use_newer 1,0"', 1)
        with self.assertRaisesRegex(ValueError, "older signature"):
            m.bind_native(raw, self.config)

    def test_actual_pilot_full_offline_verify(self):
        result = m.base.verify_artifacts(self.out, self.config)
        self.assertEqual(result["status"], "QBS_PILOT_EXACT_ROUNDTRIP_NOT_APPLICATION_APPROVAL")
        self.assertEqual(result["records"], 2)
        self.assertFalse(result["exclusions_applied_to_aggregate"])


if __name__ == "__main__":
    unittest.main()
