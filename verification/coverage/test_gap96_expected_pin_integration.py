"""Exercise the inherited admission loop, not just its pin helper."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import admit_gap96_offline_v2 as tool


class InheritedPinLoopTests(unittest.TestCase):
    def test_inherited_rehash_loop_rejects_changed_pinned_console(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "verification/out"
            run = out / "probe-old-image-20261006-01"
            base = out / "baseline-20261006-01"
            run.mkdir(parents=True)
            base.mkdir()

            def save(path, value):
                path.write_text(json.dumps(value))

            console = run / "console.log"
            console.write_text("original")
            expected = tool.original_sha(console)
            save(run / "manifest.json", dict(pins={str(console): expected}))
            save(run / "simulation-status.json", dict(status="SIMULATION_EXITED_NOT_ADMITTED"))
            save(base / "status.json", dict(status="PASS_RAW_UNION_HISTORICAL_ONLY", aggregate_passed=1))
            save(base / "combined-bits.json", dict(tests=["old.vdb"]))
            save(base / "evidence-pins.json", {})
            design = out / "repaired-aligned-build-20260930-01/sim/simv.vdb"
            (base / "combined-inputs.txt").write_text(str(design) + "\nold.vdb\n")
            console.write_text("changed after sealing")
            spec = dict(stem="probe", base="baseline", count=1)
            with patch.object(tool.admission, "ROOT", root), \
                 patch.object(tool.admission, "SPECS", {"probe": spec}), \
                 patch.object(tool.admission, "sha", tool.checked_sha), \
                 patch.dict(tool.expected_pins, {str(console): expected}, clear=True), \
                 patch("sys.argv", ["admission", "probe", "--output", str(out / "result")]), \
                 patch.object(tool.admission, "compare_commit_prefix") as comparison:
                with self.assertRaisesRegex(ValueError, "Pinned evidence drift"):
                    tool.admission.main()
                comparison.assert_not_called()
            self.assertFalse((out / "result").exists())
            self.assertEqual(json.loads((run / "manifest.json").read_text())["pins"][str(console)], expected)


if __name__ == "__main__":
    unittest.main()
