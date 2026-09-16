"""Check that area collection rejects incomparable or unfinished reports."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("compact_area", HERE / "collect_qbs_compact_area_results.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class AreaCollectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.before, self.after = [Path(self.temp.name) / s for s in ("before", "after")]
        settings = dict(top="qbs_adapter_pipeline_timing", period_ns=1,
                        setup_uncertainty_ns=.15, cores=2, clock_gating=True,
                        element_width=2, elaborate_only=False, compact_read=False,
                        quick_reports=True, flow_sha256={"library_env.tcl": "same"})
        for path, area in ((self.before, 200), (self.after, 150)):
            path.mkdir()
            (path / "manifest.json").write_text(json.dumps(settings))
            (path / "payload_dc.tcl").write_text("compile_ultra\n")
            (path / "status.json").write_text('{"state":"PASS"}')
            (path / "dc.log").write_text("PAYLOAD_DC_COMPLETE\n")
            (path / "area.rpt").write_text(f"Total cell area: {area}.0\n")

    def test_mapped_pair(self):
        result = MOD.area_pair(self.before, self.after)
        self.assertEqual(result["reduction_percent"], 25)
        self.assertEqual(result["scope"], "local_wrapper_not_chip")

    def test_running_report_is_not_a_result(self):
        (self.after / "status.json").write_text('{"state":"RUNNING"}')
        self.assertNotIn("after_um2", MOD.area_pair(self.before, self.after))

    def test_changed_constraint_rejected(self):
        path = self.after / "manifest.json"
        settings = json.loads(path.read_text())
        settings["setup_uncertainty_ns"] = .1
        path.write_text(json.dumps(settings))
        with self.assertRaisesRegex(ValueError, "settings differ"):
            MOD.area_pair(self.before, self.after)

    def test_changed_compile_rejected(self):
        (self.after / "payload_dc.tcl").write_text("compile\n")
        with self.assertRaisesRegex(ValueError, "script differs"):
            MOD.area_pair(self.before, self.after)

    def test_missing_completion_rejected(self):
        (self.after / "dc.log").write_text("Error: mapping failed\n")
        with self.assertRaisesRegex(ValueError, "not a passing"):
            MOD.area_pair(self.before, self.after)


if __name__ == "__main__":
    unittest.main()
