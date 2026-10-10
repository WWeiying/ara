"""Host-only fixtures for same-image, same-denominator coverage increments."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import report_batch_increment as inc


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


class BatchIncrementTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.image = self.root / "image"
        self.image.write_bytes(b"same coverage image")
        self.plan_path = self.root / "plan.json"
        self.exploration = self.root / "exploration/collection.json"
        self.passed = self.root / "passed-only/collection.json"
        self.cases, self.samples = [], []
        data = [([1, 0, 0, 0, 0, 0], "FAIL", "RTL_STALL"),
                ([1, 0, 0, 1, 0, 0], "PASS", "PASS"),
                ([0, 1, 0, 1, 0, 1], "PASS", "RTL_FAIL"),
                ([0, 0, 1, 0, 1, 0], "PASS", "PASS")]
        for index, (counts, status, source_status) in enumerate(data):
            name = f"case{index}"
            directory = self.root / name
            directory.mkdir()
            elf = directory / "input.elf"
            elf.write_bytes(name.encode())
            (directory / "sim.log").write_text("self-check evidence")
            points = [self.point(point, count) for point, count in enumerate(counts)]
            (directory / "coverage.dat").write_text("".join(points))
            result = {"status": status, "self_check_pass": status == "PASS",
                      "sim_returncode": 0, "report_returncode": 0 if status == "PASS" else None,
                      "simv": str(self.image), "simv_sha256": inc.sha256(self.image),
                      "elf": str(elf), "elf_sha256": inc.sha256(elf),
                      "coverage_sha256": inc.sha256(directory / "coverage.dat"),
                      "sim_log_sha256": inc.sha256(directory / "sim.log")}
            result_path = directory / "result.json"
            save(result_path, result)
            audit = directory / "audit.json"
            save(audit, {"status": "PASS", "errors": [], "case_count": 1,
                         "passed_cases": 1, "failed_cases": 0,
                         "policy": {k: True for k in ("require_complete", "require_trace",
                                                       "require_vector", "require_full_match")},
                         "cases": [{"name": name, "status": "PASS", "errors": [],
                                    "artifact_dir": str(directory)}]})
            case = {"name": name, "kind": "random", "source_name": name,
                    "artifact_dir": str(directory), "source_status": source_status,
                    "source_elf": str(elf), "elf_sha256": inc.sha256(elf),
                    "source_audit": str(audit) if source_status == "PASS" else None,
                    "source_files": {str(elf): inc.sha256(elf)}}
            passed = status == source_status == "PASS"
            sample = {**case, "status": status, "raw_valid": True, "passed_only": passed,
                      "result": str(result_path), "result_sha256": inc.sha256(result_path),
                      "source_reaudit": str(audit) if passed else None,
                      "source_reaudit_sha256": inc.sha256(audit) if passed else None,
                      "sample": inc.validate_sample(result_path)}
            self.cases.append(case)
            self.samples.append(sample)
        self.write_manifests()

    def point(self, index, count):
        kind = "line" if index < 3 else "expr" if index < 5 else "branch"
        # Same source/line, distinct hierarchy and expression labels must not collapse.
        return (f"C '\x01f\x02/hardware/src/dut.sv\x01l\x0210\x01t\x02{kind}"
                f"\x01h\x02TOP.tb.dut.lane{index % 3}\x01o\x02point{index}' {count}\n")

    def write_manifests(self):
        save(self.plan_path, {"image": str(self.image), "image_sha256": inc.sha256(self.image),
                              "coverage": inc.SCOPES, "cases": self.cases})
        for path, kind, samples in ((self.exploration, "exploration", self.samples),
                                    (self.passed, "passed-only", [s for s in self.samples if s["passed_only"]])):
            save(path, {"status": "COLLECTED", "purpose": inc.PURPOSES[kind],
                        "coverage": inc.SCOPES, "source_plan": str(self.plan_path),
                        "source_plan_sha256": inc.sha256(self.plan_path), "samples": samples})

    def refresh(self, index):
        sample = self.samples[index]
        path = Path(sample["result"])
        result = inc.read(path)
        result["coverage_sha256"] = inc.sha256(path.parent / "coverage.dat")
        save(path, result)
        sample["result_sha256"] = inc.sha256(path)
        sample["sample"] = inc.validate_sample(path)
        self.write_manifests()

    def report(self, n=1):
        return inc.report(self.exploration, self.passed, n, "tb.dut", ["/hardware/src/"])

    def test_separate_fixed_prefix_increment_and_point_denominators(self):
        result = self.report()
        self.assertEqual(result["denominator_check"]["samples_checked"], 4)
        self.assertEqual(result["denominator_check"]["points"], 6)
        explore = result["collections"]["exploration"]
        passed = result["collections"]["passed-only"]
        self.assertEqual(explore["baseline_names"], ["case0"])
        self.assertEqual(passed["baseline_names"], ["case1"])
        for kind, expected in (("line", (3, 1, 3, 2)), ("expr", (2, 0, 2, 2)),
                               ("branch", (1, 0, 1, 1))):
            counts = explore["by_type"][kind]
            self.assertEqual(tuple(counts[k] for k in ("full_denominator", "baseline_hit", "full_hit", "new_hit")),
                             expected)
            self.assertTrue(counts["denominator_equal"])
            self.assertEqual(counts["denominator_sha256"], passed["by_type"][kind]["denominator_sha256"])
        self.assertEqual(passed["by_type"]["line"]["new_hit"], 1)
        self.assertEqual(passed["by_type"]["expr"]["new_hit"], 1)
        self.assertEqual(passed["by_type"]["branch"]["new_hit"], 0)
        self.assertFalse(result["coverage"]["toggle"])
        self.assertFalse(result["coverage"]["fsm"])
        self.assertFalse(result["coverage"]["assertion"])

    def test_same_count_different_point_identity_rejected(self):
        raw = Path(self.samples[3]["sample"]["coverage"])
        raw.write_text(raw.read_text().replace("point4", "other_expression_term"))
        self.refresh(3)
        with self.assertRaisesRegex(ValueError, "denominator mismatch.*missing=1, extra=1"):
            self.report()

    def test_duplicate_raw_keys_do_not_inflate_denominator(self):
        raw = Path(self.samples[0]["sample"]["coverage"])
        raw.write_text(raw.read_text() + self.point(0, 9))
        self.refresh(0)
        result = self.report()
        self.assertEqual(result["denominator_check"]["points"], 6)
        self.assertEqual(result["collections"]["exploration"]["by_type"]["line"]["baseline_hit"], 1)

    def test_different_image_rejected_even_with_equal_points(self):
        image = self.root / "old-image"
        image.write_bytes(b"old RTL")
        result_path = Path(self.samples[0]["result"])
        result = inc.read(result_path)
        result.update(simv=str(image), simv_sha256=inc.sha256(image))
        save(result_path, result)
        self.refresh(0)
        with self.assertRaisesRegex(ValueError, "identity differs"):
            self.report()

    def test_changed_raw_or_source_elf_rejected(self):
        raw = Path(self.samples[0]["sample"]["coverage"])
        saved = raw.read_text()
        raw.write_text(saved + self.point(0, 4))
        with self.assertRaisesRegex(ValueError, "coverage.dat"):
            self.report()
        raw.write_text(saved)
        Path(self.cases[0]["source_elf"]).write_bytes(b"changed source ELF")
        with self.assertRaisesRegex(ValueError, "elf"):
            self.report()

    def test_reordering_or_duplicate_selection_rejected(self):
        document = inc.read(self.exploration)
        for samples in (list(reversed(document["samples"])), [document["samples"][0]] * 2):
            save(self.exploration, {**document, "samples": samples})
            with self.assertRaisesRegex(ValueError, "duplicated, reordered"):
                self.report()

    def test_passed_subset_must_be_complete_and_have_pass_audit(self):
        document = inc.read(self.passed)
        save(self.passed, {**document, "samples": document["samples"][:1]})
        with self.assertRaisesRegex(ValueError, "exact independently passing subset"):
            self.report()
        save(self.passed, document)
        sample = self.samples[1]
        audit_path = Path(sample["source_reaudit"])
        audit = inc.read(audit_path)
        audit["policy"]["require_full_match"] = False
        save(audit_path, audit)
        sample["source_reaudit_sha256"] = inc.sha256(audit_path)
        self.write_manifests()
        with self.assertRaisesRegex(ValueError, "matching complete PASS"):
            self.report()

    def test_failed_source_cannot_be_promoted_to_passed_only(self):
        self.samples[2]["passed_only"] = True
        self.write_manifests()
        with self.assertRaisesRegex(ValueError, "failed sample"):
            self.report()

    def test_baseline_not_silently_shortened_and_empty_not_reported_zero(self):
        with self.assertRaisesRegex(ValueError, "baseline not shortened"):
            self.report(3)
        with self.assertRaisesRegex(ValueError, "positive"):
            self.report(0)
        document = inc.read(self.passed)
        save(self.passed, {**document, "status": "EMPTY", "samples": []})
        with self.assertRaisesRegex(ValueError, "not a collected"):
            self.report()

    def test_scope_empty_and_unsupported_toggle_rejected(self):
        with self.assertRaisesRegex(ValueError, "no points"):
            inc.report(self.exploration, self.passed, 1, "tb.other", ["/hardware/src/"])
        raw = Path(self.samples[0]["sample"]["coverage"])
        raw.write_text(raw.read_text().replace("\x02expr", "\x02toggle"))
        self.refresh(0)
        with self.assertRaisesRegex(ValueError, "unsupported raw point type"):
            self.report()

    def test_drift_during_raw_read_is_rejected(self):
        original = inc.point_sets
        def changed(path, *args):
            result = original(path, *args)
            path.write_text(path.read_text() + self.point(0, 2))
            return result
        with patch.object(inc, "point_sets", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed input"):
                self.report()

    def test_cli_writes_only_new_report_no_external_commands(self):
        output = self.root / "increment.json"
        argv = ["increment", "--exploration", str(self.exploration), "--passed-only", str(self.passed),
                "--baseline-samples", "1", "--hierarchy-prefix", "tb.dut", "--output", str(output)]
        with patch.object(sys, "argv", argv), patch("subprocess.run", side_effect=AssertionError("external command")):
            self.assertEqual(inc.main(), 0)
            with self.assertRaises(SystemExit):
                inc.main()
        self.assertEqual(inc.read(output)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
