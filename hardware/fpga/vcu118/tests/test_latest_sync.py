"""Latest-main migration checks; historical delivery checks remain unchanged."""
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from dispatcher_fpga import patch_dispatcher_layout
from dispatcher_control_fpga import patch_dispatcher_control
from export import optimization_defines, patch_dispatcher_vlen_casts
from prepare import dependency_roots


class LatestSyncTests(unittest.TestCase):
    def test_generic_preserves_previous_selectors(self):
        self.assertEqual(optimization_defines("generic"), {})

    def test_candidate_all_uses_defined_on_selectors(self):
        self.assertEqual(optimization_defines("candidate_all"), {
            "ARA_SHARED_SIMD_MUL": 1, "ARA_SHARED_FMA": 1,
            "ARA_QBS_LANE_MUL_ENABLE": 1,
            "ARA_AKV_RESIDENT_PV_ENABLE": 1, "ARA_AKV_RESIDENT_QK_ENABLE": 1,
        })

    def test_unknown_profile_fails(self):
        with self.assertRaises(RuntimeError):
            optimization_defines("everything")

    def test_latest_dispatcher_and_explicit_rejection(self):
        current = (ROOT / "hardware/src/ara_dispatcher.sv").read_text()
        committed = subprocess.check_output(
            ["git", "show", "870cadb9:hardware/src/ara_dispatcher.sv"],
            cwd=ROOT, text=True)
        self.assertEqual(hashlib.sha256(current.encode()).hexdigest(),
                         "fdc9f259641efc8c1ec1d2ce450ea78927ac8b5ec8321e5777ca63b2195c048e")
        for source in (current, committed):
            for transform in (patch_dispatcher_layout, patch_dispatcher_control,
                              patch_dispatcher_vlen_casts):
                self.assertEqual(transform(source), source)
            for transform in (patch_dispatcher_layout, patch_dispatcher_control):
                with self.assertRaises(RuntimeError):
                    transform(source + "\n")

    def test_dependency_validation_cannot_be_bypassed(self):
        sys.path.insert(0, str(ROOT / "verification"))
        from ara_verify.dependency_patches import PatchError
        with patch("ara_verify.dependency_patches.patch_state",
                   side_effect=PatchError("unregistered dependency delta")):
            with self.assertRaisesRegex(PatchError, "unregistered"):
                dependency_roots(ROOT / "hardware/deps")

    def test_sync_exposes_explicit_selection(self):
        result = subprocess.run([sys.executable, str(HERE / "sync.py"), "--help"],
                                text=True, capture_output=True, check=True)
        self.assertIn("--optimization-profile", result.stdout)
        self.assertIn("--dependency-root", result.stdout)

    def test_clean_but_unpatched_dependency_is_rejected(self):
        sys.path.insert(0, str(ROOT / "verification"))
        from ara_verify.dependency_patches import PatchError
        with patch("ara_verify.dependency_patches.patch_state", return_value="missing"):
            with self.assertRaisesRegex(PatchError, "required registered patch"):
                dependency_roots(ROOT / "hardware/deps")


if __name__ == "__main__":
    unittest.main()
