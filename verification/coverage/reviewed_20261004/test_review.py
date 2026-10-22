"""Offline mapping and policy rejection tests; no frozen imports or tool launches."""
import copy
import unittest
import xml.etree.ElementTree as ET

import audit_readonly as review


class MappingTests(unittest.TestCase):
    def test_reverse_is_per_spec_not_whole_instance(self):
        definition = ET.fromstring('<branch_def><branch_spec id="2">'
            '<branch_vector id="0" vector="01"/><branch_vector id="1" vector="10"/>'
            '</branch_spec><branch_spec id="7"><branch_vector id="0" vector="01"/>'
            '<branch_vector id="1" vector="10"/><branch_vector id="2" vector="11"/>'
            '</branch_spec></branch_def>')
        self.assertEqual(review.branch_index(definition, "2", "0")[:3], (1, 0, 2))
        self.assertEqual(review.branch_index(definition, "7", "0")[:3], (4, 2, 3))
        self.assertEqual(review.branch_index(definition, "7", "2")[:3], (2, 2, 3))

    def test_missing_branch_rejected(self):
        with self.assertRaises(ValueError):
            review.branch_index(ET.fromstring('<branch_def/>'), "2", "0")

    def test_native_saved_signature_not_shape_statement_checksum(self):
        entries = review.native_entries('CHECKSUM: "1532764271 3998926456"\n'
            'INSTANCE: dut\nBlock 172 "3393845244" "if (flush_i)"\n')
        self.assertEqual(entries[0]["nativepointchecksum"], "3393845244")
        self.assertEqual(entries[0]["point"], "Block 172")

    def test_unknown_native_syntax_and_duplicate_rejected(self):
        header = 'CHECKSUM: "1 2"\nINSTANCE: dut\n'
        for text in (header + 'Condition 1', header + 'Toggle flush_i',
                     header + 'Branch 2 (0)', header.replace('dut', 'dut.*'),
                     header + 'Toggle flush_i "logic flush_i"\n' * 2):
            with self.subTest(text=text), self.assertRaises(ValueError):
                review.native_entries(text)

    def test_toggle_prefix_not_whole_vector_guess(self):
        definition = ET.fromstring('<tgldef><tglshape><node name="clk_i"/>'
            '<node name="rst_ni"/><node name="flush_i" portnode="2" excluded="0"/>'
            '<arrays name="unreviewed"/></tglshape></tgldef>')
        self.assertEqual(review.scalar_toggle_offset(definition, "flush_i")[0], 4)
        with self.assertRaises(ValueError):
            review.scalar_toggle_offset(definition, "missing")

    def test_exact_scope_count_and_forbidden_neighbors(self):
        points = review.expected_points()
        self.assertEqual(len(points), 94)
        self.assertEqual(sum(p.startswith("Block") for _, p in points), 48)
        self.assertEqual(sum(p.startswith("Branch") for _, p in points), 16)
        self.assertEqual(sum(p.startswith("Toggle") for _, p in points), 30)
        self.assertFalse(any("lsu" in s or "requester" in s or p.endswith("(1)") for s, p in points))

    def test_shared_metric_checksum_requires_definition_identity(self):
        design = review.Design.__new__(review.Design)
        design.hierarchy = {"dut": ET.fromstring('<srcdef id="-207" name="vrf_perf_monitor"/>')}
        design.info = {"branch": {"dut": "1223333544"}}
        design.shapes = {"branch": ET.fromstring('<branch>'
            '<branch_def id="-99" chksum="1223333544"/>'
            '<branch_def id="-207" chksum="1223333544"/>'
            '</branch>')}
        self.assertEqual(design.definition("dut", "branch").get("id"), "-207")
        design.shapes["branch"].remove(design.shapes["branch"][1])
        with self.assertRaises(ValueError):
            design.definition("dut", "branch")

    def test_non_input_toggle_is_rejected(self):
        for attrs in ('portnode="3" excluded="0"', 'portnode="2" excluded="1"'):
            definition = ET.fromstring('<tgldef><tglshape><node name="flush_i" '
                                       + attrs + '/></tglshape></tgldef>')
            with self.subTest(attrs=attrs), self.assertRaises(ValueError):
                review.scalar_toggle_offset(definition, "flush_i")


class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = review.jread(review.HERE / "audit.json")
        cls.policy = review.jread(review.HERE / "policy.json")

    def test_policy_and_audit_binding(self):
        review.validate_policy(self.policy, self.audit)
        self.assertEqual(review.sha(review.HERE / "audit.json"), self.policy["audit_sha256"])

    def test_mutated_policy_rejected(self):
        for change in ("missing", "extra", "scope", "native", "checksum", "applied", "percentage", "observer"):
            p = copy.deepcopy(self.policy)
            if change == "missing":
                p["allowed_points"].pop()
            elif change == "extra":
                p["allowed_points"].append(copy.deepcopy(p["allowed_points"][0]))
            elif change == "scope":
                p["allowed_points"][0]["scope"] += ".i_fifo"
            elif change == "native":
                p["allowed_points"][0]["native_directive"] = 'Branch 2 (1)'
            elif change == "checksum":
                p["allowed_points"][0]["checksum"][0] = "0"
            elif change == "applied":
                p["application"]["applied"] = True
            elif change == "percentage":
                p["application"]["adjusted_percentages"] = 100
            else:
                p["allowed_observers"].append(dict(scope=review.CORE, recursive=1))
            with self.subTest(change=change), self.assertRaises(ValueError):
                review.validate_policy(p, self.audit)

    def test_all_94_have_explicit_source_signature_state(self):
        for p in self.audit["points"]:
            with self.subTest(scope=p["scope"], point=p["point"]):
                self.assertEqual(p["old"], p["current"])
                self.assertEqual(p["raw_625_state"]["samples"], 625)
                self.assertEqual(set(p["raw_625_state"]["value"]), {"0"})
                self.assertEqual(p["decision"], "REUSABLE_OFFLINE_NOT_APPLIED")
                self.assertEqual(len(p["source_sha256"]), 64)
                if p["point"] == "Block 172":
                    self.assertEqual(p["current"]["raw_indices"], [176])
                if p["point"].startswith("Branch"):
                    self.assertEqual(p["raw_625_state"]["spec_slice"], "10")

    def test_current_report_unmodified_and_unwaived(self):
        raw = self.audit["raw_report"]
        self.assertEqual(review.sha(raw["path"]), raw["sha256"])
        self.assertIsNone(raw["adjusted_percentages"])
        self.assertEqual(raw["top"]["Line"], "76.90%")
        self.assertEqual(raw["top"]["Condition"], "78.96%")
        self.assertEqual(raw["top"]["Branch"], "77.24%")
        self.assertEqual(raw["top"]["FSM"], "50.54%")
        self.assertEqual(raw["top"]["Toggle"], "59.63%")

    def test_observer_scope_cannot_swallow_product_descendants(self):
        self.assertEqual(len(self.audit["observers"]), 10)
        for observer in self.audit["observers"]:
            self.assertEqual(observer["descendants"], [])
            self.assertEqual(observer["current"], observer["old"])

    def test_frozen_files_still_match(self):
        for item in self.audit["evidence"]["files"]:
            with self.subTest(path=item["path"]):
                self.assertEqual(review.sha(item["path"]), item["sha256"])

    def test_image_manifest_and_all_raw_data_still_match(self):
        for group in ("image_and_design", "compile_sources", "raw_testdata"):
            for item in self.audit["evidence"][group]:
                with self.subTest(group=group, path=item["path"]):
                    self.assertEqual(review.sha(item["path"]), item["sha256"])


if __name__ == "__main__":
    unittest.main()
