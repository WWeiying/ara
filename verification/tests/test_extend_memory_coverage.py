"""Check that supplemental coverage admits only verified, unchanged PASS VDBs."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import extend_memory_coverage as module


class MemoryCoverageTests(unittest.TestCase):
    def test_preflight_failure_prevents_expansion(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "scheduler").mkdir()
            module.b.save(output / "outcomes/a.json", {"status": "FAIL"})
            with patch.object(module, "original_schedule") as schedule:
                with self.assertRaisesRegex(ValueError, "representative failed"):
                    module.schedule(output, ["a", "b", "c"], 8)
                schedule.assert_called_once_with(output, ["a", "b"], 1)

    def test_preflight_pass_expands_eight_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "scheduler").mkdir()
            for name in ("a", "b"):
                module.b.save(output / "outcomes" / (name + ".json"), {"status": "PASS"})
            with patch.object(module, "original_schedule") as schedule:
                module.schedule(output, ["a", "b", "c", "d"], 8)
                self.assertEqual(schedule.call_count, 2)
                schedule.assert_called_with(output, ["c", "d"], 8)

    def test_failed_case_is_not_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            vdb = output / "results/ok/tests/ok/work/code.vdb"
            design = str(output / "design.vdb")
            case = {"name": "ok", "elf_sha256": "e", "coverage_test": "ok", "source_name": "ok"}
            failed = {"name": "bad", "elf_sha256": "f", "coverage_test": "bad", "source_name": "bad"}
            good_record = dict(case, status="PASS", files={}, passed_only=True,
                vdb_valid=True, vdb=str(vdb), vdb_files={})
            bad_record = dict(failed, status="TIMEOUT", files={}, passed_only=False,
                              vdb=str(output / "results/bad/tests/bad/work/code.vdb"))
            for item in (good_record, bad_record):
                module.b.save(output / "outcomes" / (item["name"] + ".json"), item)
            def invoke(command, *args, **kwargs):
                report = output / "dve"
                report.mkdir()
                (report / "selected_tests.txt").write_text(str(vdb.with_suffix("") / "ok") + "\n")
                module.b.save(report / "waiver_status.json", {"status": "APPLIED"})
                (report / "summary.csv").write_text("raw")
                (report / "summary_waived.csv").write_text("waived")
                return 0
            with patch.object(module.b, "valid_vdb", return_value={}), \
                 patch.object(module.b.base, "inventory", return_value={}), \
                 patch.object(module.b, "invoke", side_effect=invoke):
                module.summarize(output, {"cases": [case, failed], "design_vdb": design,
                    "design_files": {}, "simv": "/image", "image": {}, "reused": []})
            report = module.b.read(output / "collection.json")
            self.assertEqual(report["passed"], 1)
            self.assertEqual(report["excluded"], ["bad"])
            self.assertEqual((output / "dve-inputs.txt").read_text().splitlines(), [design, str(vdb)])

    def test_changed_vdb_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            case = {"name": "ok", "elf_sha256": "e", "coverage_test": "ok", "source_name": "ok"}
            module.b.save(output / "outcomes/ok.json", dict(case, status="PASS", files={},
                passed_only=True, vdb_valid=True, vdb=str(output / "results/ok/tests/ok/work/code.vdb"), vdb_files={"old": "hash"}))
            with patch.object(module.b, "valid_vdb", return_value={}), \
                 patch.object(module.b, "invoke") as invoke:
                with self.assertRaisesRegex(ValueError, "VDB drift"):
                    module.summarize(output, {"cases": [case], "simv": "/image", "reused": []})
                invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
