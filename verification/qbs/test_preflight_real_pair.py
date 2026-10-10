"""Tests for the no-simulation RVV/QBS input gate."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from preflight_real_pair import audit, check_r4, digest, expected_activation_profile


class PairedPreflightTests(unittest.TestCase):
    def test_activation_profile_follows_weight_abi(self):
        for weight in ("q4_0", "q5_0", "iq4_nl", "q8_0"):
            self.assertEqual(expected_activation_profile(weight), "Q8_0")
        for weight in ("q2_K", "q3_K", "q4_K", "q5_K", "q6_K"):
            self.assertEqual(expected_activation_profile(weight), "Q8_K")

    def test_r4_repack_order_is_checked(self):
        self.assertTrue(check_r4(b"abcdefgh", b"acegbdfh", 4, 1, 2))
        self.assertFalse(check_r4(b"abcdefgh", b"abcdefgh", 4, 1, 2))

    def test_pair_rejects_changed_golden_after_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "capture"
            capture.mkdir()
            (capture / "model.json").write_text("{}\n", encoding="utf-8")
            case = {
                "capture_root": str(capture), "phase": "decode",
                "operator": "weight", "weight_type": "q6_K", "k": 4,
                "rows": 4, "inputs": 1, "capture_rows": 4,
                "capture_inputs": 1,
            }
            apps = []
            elfs = []
            for name in ("rvv", "qbs"):
                app = root / name
                generated = app / "generated"
                generated.mkdir(parents=True)
                (app / "case.json").write_text(json.dumps(case), encoding="utf-8")
                blobs = {
                    "source_weight.bin": b"abcdefgh",
                    "embedded_weight.bin": b"acegbdfh" if name == "qbs" else b"abcdefgh",
                    "activation_f32.bin": b"activation",
                    "golden_f32.bin": b"golden",
                }
                for filename, content in blobs.items():
                    (generated / filename).write_bytes(content)
                provenance = {
                    **case, "model_metadata_sha256": digest(capture / "model.json"),
                    "tensors": {filename: {"sha256": digest(generated / filename)}
                                for filename in blobs},
                }
                if name == "qbs":
                    provenance["qbs"] = {
                        "descriptor_version": 2, "weight_profile": "Q6_K",
                        "weight_layout": "W_R4_BLOCK_MAJOR",
                        "activation_profile": "Q8_K", "activation_layout": "A_ROW_MAJOR",
                        "block_elements": 2, "k_blocks": 2,
                    }
                (generated / "provenance.json").write_text(json.dumps(provenance),
                                                           encoding="utf-8")
                elf = root / f"{name}.elf"
                elf.write_bytes(b"start" + blobs["embedded_weight.bin"] +
                                blobs["activation_f32.bin"] + blobs["golden_f32.bin"])
                apps.append(app)
                elfs.append(elf)
            simv = root / "simv"
            simv.write_bytes(b"simulator")
            (root / "simv.daidir").mkdir()
            (root / "simulator.conf").write_text(
                "vlen=1024\nnr_lanes=4\nsim_l2_mb=4\nqbs_enabled=1\n",
                encoding="utf-8")
            with patch("preflight_real_pair.elf_identity", return_value={"sha256": "mock"}):
                self.assertEqual(audit(*apps, *elfs, simv)["status"], "READY_NOT_RUN")
                (apps[1] / "generated/golden_f32.bin").write_bytes(b"changed")
                result = audit(*apps, *elfs, simv)
            self.assertEqual(result["status"], "NOT_READY")
            self.assertIn("RVV/QBS golden_f32.bin differs", result["issues"])
            (apps[1] / "generated/golden_f32.bin").write_bytes(b"golden")
            for app in apps:
                saved = json.loads((app / "case.json").read_text())
                saved.pop("capture_root")
                (app / "case.json").write_text(json.dumps(saved))
            with patch("preflight_real_pair.elf_identity", return_value={"sha256": "mock"}):
                self.assertEqual(audit(*apps, *elfs, simv)["status"], "READY_NOT_RUN")
                corrupted = json.loads((apps[1] / "generated/provenance.json").read_text())
                corrupted["capture_root"] = str(root / "other-capture")
                (apps[1] / "generated/provenance.json").write_text(json.dumps(corrupted))
                result = audit(*apps, *elfs, simv)
            self.assertEqual(result["status"], "NOT_READY")
            self.assertIn("case capture_root differs", result["issues"])


if __name__ == "__main__":
    unittest.main()
