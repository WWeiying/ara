import copy
import json
from unittest.mock import patch
import unittest
import apply_qbs_rooted_699 as report


class ReportGateTests(unittest.TestCase):
    def config(self):
        config = json.loads((report.PILOT / "config.json").read_bytes())
        config.update(mode="report", inputs=(report.base.BASE / "combined-inputs.txt").read_text().splitlines(),
                      selected_tests=(report.base.RAW / "selected_tests.txt").read_text().splitlines(),
                      rooted_report_pilot=dict(output=str(report.PILOT), config_sha256=report.PILOT_SEAL,
                                              result_sha256=report.PILOT_RESULT_SEAL))
        return config

    def test_fixed699(self):
        report.population_gate(self.config())

    def test_reject701(self):
        config = self.config()
        config["selected_tests"] += ["future700", "future701"]
        with self.assertRaises(ValueError):
            report.population_gate(config)

    def test_reject_duplicate(self):
        config = self.config()
        config["selected_tests"][1] = config["selected_tests"][0]
        with self.assertRaises(ValueError):
            report.population_gate(config)

    def test_reject_order_substitution(self):
        config = self.config()
        config["inputs"][1], config["inputs"][2] = config["inputs"][2], config["inputs"][1]
        with self.assertRaises(ValueError):
            report.population_gate(config)

    def test_reject_root_alias(self):
        config = self.config()
        config["root_refresh_scopes"][-1] = "i_payload_buffer"
        with self.assertRaises(ValueError):
            report.population_gate(config)

    def test_pilot_negative_evidence(self):
        saved = json.loads((report.PILOT / "capture-result.json").read_bytes())
        actual = {k: v for k, v in saved.items() if k not in ("capture_only", "config_sha256")}
        report.compare_saved(saved, actual)
        for key, bad in (("records", 447), ("protected", 3789), ("final_reset", False)):
            broken = copy.deepcopy(saved)
            broken[key] = bad
            with self.assertRaises(ValueError):
                report.compare_saved(broken, actual)

    def test_pilot_artifact_mismatch(self):
        saved = json.loads((report.PILOT / "capture-result.json").read_bytes())
        actual = {k: v for k, v in saved.items() if k not in ("capture_only", "config_sha256")}
        actual["files"] = dict(actual["files"], unexpected="0" * 64)
        with self.assertRaises(ValueError):
            report.compare_saved(saved, actual)

    def test_framework_config_selection_superset(self):
        saved = json.loads((report.PILOT / "capture-result.json").read_bytes())
        actual = {k: v for k, v in saved.items() if k not in ("capture_only", "config_sha256")}
        actual["files"] = {p: h for p, h in saved["files"].items()
                           if not p.endswith(("/config.json", "/selection.tcl"))}
        report.compare_saved(saved, actual)
        missing = copy.deepcopy(saved)
        missing["files"].pop(next(iter(actual["files"])))
        with self.assertRaises(ValueError):
            report.compare_saved(missing, actual)

    def test_no_contract_promotion_or_wrong_seal(self):
        with self.assertRaises(ValueError):
            report.prepare(report.base.OUT / "unused", "contract", None)
        with self.assertRaises(ValueError):
            report.prepare(report.base.OUT / "unused", "report", None, report.PILOT, "0" * 64,
                           report.PILOT_RESULT_SEAL)

    def test_existing_pilot_dispatch(self):
        with patch.object(report.pilot, "verify_artifacts", return_value={"sentinel": True}) as verify:
            self.assertEqual(report.verify_artifacts(report.PILOT, {}), {"sentinel": True})
            verify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
