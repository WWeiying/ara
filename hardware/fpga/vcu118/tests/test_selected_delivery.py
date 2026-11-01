"""Audit the selected delivery, independently of later live-main changes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
PACKAGE = HERE.parent / "ara_dsa_vcu118"
REVISION = "1e48e205df5cec34183222c36d22eb4858466810"
sys.path.insert(0, str(HERE))
from export import patch_akv_byte_counts, patch_qbs_fault_decode
from dispatcher_fpga import patch_dispatcher_layout
from dispatcher_control_fpga import patch_dispatcher_control, patch_segment_geometry
from export import patch_dispatcher_vlen_casts


def git_bytes(root, revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=root)


class SelectedDeliveryTests(unittest.TestCase):
    def test_all_exported_ara_inputs_match_fixed_delivery(self):
        manifest = json.loads((PACKAGE / "manifest.json").read_text())
        transforms = {
            "hardware/src/ara_dispatcher.sv": lambda t: patch_dispatcher_control(
                patch_dispatcher_layout(patch_dispatcher_vlen_casts(t))),
            "hardware/src/segment_sequencer.sv": patch_segment_geometry,
            "hardware/src/vlsu/qbs/qbs_engine.sv": patch_qbs_fault_decode,
            "hardware/src/vlsu/akv/akv_engine.sv": patch_akv_byte_counts,
        }
        checked = 0
        for row in manifest["source_hashes_before_integration"]:
            rel = row["file"]
            if not rel.startswith("rtl/ara/hardware/"):
                continue
            source = rel.removeprefix("rtl/ara/")
            raw = git_bytes(ROOT, REVISION, source)
            with self.subTest(source=source):
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row["source_sha256"])
                expected = transforms.get(source, lambda t: t)(raw.decode()).encode()
                self.assertEqual((PACKAGE / rel).read_bytes(), expected)
            checked += 1
        self.assertEqual(checked, 68)

    def test_mvp_matches_declared_clean_dependency_not_local_edits(self):
        manifest = json.loads((PACKAGE / "manifest.json").read_text())
        rows = [row for row in manifest["source_hashes_before_integration"]
                if row["file"].startswith("rtl/fpu_div_sqrt_mvp/")]
        self.assertEqual(len(rows), 8)
        revision = "86e1f558b3c95e91577c41b2fc452c86b04e85ac"
        for row in rows:
            source = row["file"].removeprefix("rtl/fpu_div_sqrt_mvp/")
            raw = git_bytes(ROOT / "hardware/deps/fpu_div_sqrt_mvp", revision, source)
            with self.subTest(source=source):
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row["source_sha256"])
                self.assertEqual(raw, (PACKAGE / row["file"]).read_bytes())


if __name__ == "__main__":
    unittest.main()
