import copy
import json
import unittest

import capture_operand_debug_branch_v5 as m


class ActualGenerateAnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((m.FAILED / "config.json").read_bytes())
        cls.raw = (m.FAILED / "first.el").read_bytes()

    def test_actual_full_first_exact1832(self):
        rows = m.bind_native(self.raw, self.config)
        self.assertEqual(len(rows), 1832)
        self.assertEqual(sum("vcs_gen_start:" in r["native_annotation"] for r in rows), 1800)

    def test_wrong_generate_annotation_rejected(self):
        with self.assertRaisesRegex(ValueError, "compiled generate_info"):
            m.bind_native(self.raw.replace(b"requester_index=8:vcs_gen_end:", b"requester_index=7:vcs_gen_end:", 1), self.config)

    def test_missing_generate_annotation_rejected(self):
        with self.assertRaisesRegex(ValueError, "compiled generate_info"):
            m.bind_native(self.raw.replace(b"vcs_gen_start:requester_index=8:vcs_gen_end:", b"", 1), self.config)

    def test_extra_directive_rejected(self):
        with self.assertRaises(ValueError):
            m.bind_native(self.raw + b'Toggle 1 "0" "x"\n', self.config)

    def test_duplicate_record_rejected(self):
        with self.assertRaises(ValueError):
            m.bind_native(self.raw + self.raw, self.config)

    def test_source_checksum_mutation_rejected(self):
        with self.assertRaises(ValueError):
            m.bind_native(self.raw.replace(b'Branch 148 "1012054768"', b'Branch 148 "1012054769"', 1), self.config)

    def test_generate_info_mutation_rejected(self):
        config = copy.deepcopy(self.config)
        for metrics in config["plan"]["scopes"].values():
            for row in metrics["branch"]:
                if row["target"] and row["point"]["attributes"].get("generate_info") == "requester_index=8":
                    row["point"]["attributes"]["generate_info"] = "requester_index=7"
                    with self.assertRaises(ValueError):
                        m.bind_native(self.raw, config)
                    return
        self.fail("No real generate fixture")


if __name__ == "__main__":
    unittest.main()
