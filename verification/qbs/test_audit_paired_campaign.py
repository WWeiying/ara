import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit_paired_campaign import audit_campaign


class PairedCampaignTests(unittest.TestCase):
    def write_manifest(self, root: Path,
                       formats=tuple(sorted(("q2_K", "q3_K", "q4_K", "q4_0",
                                             "q5_K", "q5_0", "q6_K", "q8_0",
                                             "iq4_nl")))) -> Path:
        manifest = root / "pairs.json"
        spec = {
            "schema_version": 1,
            "qbs_pairs": [
                {"format": name, "qbs_run": f"{name}-run", "rvv_run": "rvv-run",
                 "qbs_app": "qbs-app", "rvv_app": "rvv-app"}
                for name in formats
            ],
            "akv_pair": {name: name for name in
                         ("rvv_run", "akv_run", "rvv_elf", "akv_elf", "rvv_asm", "akv_asm")},
        }
        manifest.write_text(json.dumps(spec))
        return manifest

    def test_same_image_and_complete_pairs_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_manifest(Path(directory))
            def qbs_result(qbs_run, *_args):
                return {"status": "PASS", "case": {"weight_type": qbs_run.name[:-4]},
                        "vcs_image_components": {"simv": "one"}}
            with patch("audit_paired_campaign.audit_qbs_pair", side_effect=qbs_result), \
                 patch("audit_paired_campaign.audit_akv_pair",
                       return_value={"status": "PASS", "vcs_image_components": {"simv": "one"}}):
                result = audit_campaign(manifest)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["missing_qbs_formats"], [])
            self.assertTrue(result["image_match"])
            self.assertEqual(result["campaign_shape_coverage"]["multi_input_formats"], [])
            self.assertEqual(result["campaign_shape_coverage"]["row_tail_formats"], [])

    def test_campaign_shape_bins_report_only_audited_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_manifest(Path(directory))
            def qbs_result(qbs_run, *_args):
                name = qbs_run.name[:-4]
                return {"status": "PASS", "case": {"weight_type": name, "k": 896,
                        "rows": 7 if name == "q4_K" else 32,
                        "inputs": 4 if name == "q4_K" else 1},
                        "vcs_image_components": {"simv": "one"}}
            with patch("audit_paired_campaign.audit_qbs_pair", side_effect=qbs_result), \
                 patch("audit_paired_campaign.audit_akv_pair",
                       return_value={"status": "PASS", "vcs_image_components": {"simv": "one"}}):
                result = audit_campaign(manifest)
            coverage = result["campaign_shape_coverage"]
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(coverage["multi_input_formats"], ["q4_K"])
            self.assertEqual(coverage["row_tail_formats"], ["q4_K"])
            self.assertNotIn("q4_K", coverage["missing_multi_input_formats"])

    def test_second_shape_of_same_format_requires_unique_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_manifest(Path(directory))
            spec = json.loads(manifest.read_text())
            extra = dict(next(row for row in spec["qbs_pairs"] if row["format"] == "q4_K"))
            extra["variant"] = "prefill_n32_m4"
            extra["qbs_run"] = "q4_K-prefill-run"
            spec["qbs_pairs"].append(extra)
            manifest.write_text(json.dumps(spec))

            def qbs_result(qbs_run, *_args):
                name = qbs_run.name.split("-", 1)[0]
                return {"status": "PASS", "case": {"weight_type": name, "k": 1536,
                        "rows": 32, "inputs": 4 if "prefill" in qbs_run.name else 1},
                        "vcs_image_components": {"simv": "one"}}

            with patch("audit_paired_campaign.audit_qbs_pair", side_effect=qbs_result), \
                 patch("audit_paired_campaign.audit_akv_pair",
                       return_value={"status": "PASS", "vcs_image_components": {"simv": "one"}}):
                result = audit_campaign(manifest)
                self.assertEqual(result["status"], "PASS")
                self.assertEqual(result["qbs_pair_count"], 10)
                self.assertIn("q4_K@prefill_n32_m4", result["pairs"])
                self.assertEqual(result["campaign_shape_coverage"]["multi_input_formats"],
                                 ["q4_K"])
                spec["qbs_pairs"][-1].pop("variant")
                manifest.write_text(json.dumps(spec))
                self.assertIn("duplicate QBS pair: q4_K",
                              audit_campaign(manifest)["issues"])

    def test_mixed_images_do_not_close_campaign(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_manifest(Path(directory))
            def qbs_result(qbs_run, *_args):
                name = qbs_run.name[:-4]
                return {"status": "PASS", "case": {"weight_type": name},
                        "vcs_image_components": {"simv": "old" if name == "q8_0" else "new"}}
            with patch("audit_paired_campaign.audit_qbs_pair", side_effect=qbs_result), \
                 patch("audit_paired_campaign.audit_akv_pair",
                       return_value={"status": "PASS", "vcs_image_components": {"simv": "old"}}):
                result = audit_campaign(manifest)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertFalse(result["image_match"])

    def test_missing_format_and_failed_pair_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_manifest(Path(directory), formats=("q3_K", "q5_K"))
            def qbs_result(qbs_run, *_args):
                return {"status": "PASS", "case": {"weight_type": qbs_run.name[:-4]},
                        "vcs_image_components": {"simv": "one"}}
            with patch("audit_paired_campaign.audit_qbs_pair", side_effect=qbs_result), \
                 patch("audit_paired_campaign.audit_akv_pair",
                       return_value={"status": "PASS", "vcs_image_components": {"simv": "one"}}):
                result = audit_campaign(manifest)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["missing_qbs_formats"],
                             sorted({"q2_K", "q4_K", "q4_0", "q5_0", "q6_K",
                                     "q8_0", "iq4_nl"}))
            with patch("audit_paired_campaign.audit_qbs_pair",
                       return_value={"status": "FAIL", "case": {},
                                     "vcs_image_components": {"simv": "one"}}), \
                 patch("audit_paired_campaign.audit_akv_pair",
                       return_value={"status": "PASS", "vcs_image_components": {"simv": "one"}}):
                result = audit_campaign(manifest)
            self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
