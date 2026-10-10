import json
import tempfile
import unittest
from pathlib import Path

from qbs.capture_real_format import PROMPT, audit_capture, audit_existing, sha256


class RealFormatCaptureTests(unittest.TestCase):
    @staticmethod
    def fixture(root: Path) -> Path:
        directory = root / "decode/operators/blk_0_attn_q_weight"
        directory.mkdir(parents=True)
        (root / "model.json").write_text(json.dumps({
            "capture_layer": 0, "llama_commit": "test-commit",
        }))
        (directory / "operator.json").write_text(json.dumps({
            "op": "GGML_OP_MUL_MAT", "phase": "decode",
            "weight": "blk.0.attn_q.weight", "weight_type": "q4_0",
            "result_type": "F32", "activation_quantization": "Q8_K",
        }))
        for role, kind, shape, strides, size in (
            ("weight_q4_0", "q4_0", [32, 2, 1, 1], [18, 18, 36, 36], 36),
            ("activation_f32", "f32", [32, 1, 1, 1], [4, 128, 128, 128], 128),
            ("output_f32", "f32", [2, 1, 1, 1], [4, 8, 8, 8], 8),
        ):
            (directory / f"{role}.json").write_text(json.dumps({
                "role": role, "type": kind, "shape": shape,
                "strides": strides, "nbytes": size,
            }))
            (directory / f"{role}.bin").write_bytes(bytes(size))
        return directory

    def test_accepts_complete_real_format_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            result = audit_capture(root, "blk_0_attn_q_weight", "q4_0")
            self.assertEqual(result["status"], "PASS")
            self.assertEqual((result["k"], result["n"], result["m"]), (32, 2, 1))
            self.assertEqual(result["tensors"]["golden"]["bytes"], 8)

    def test_rejects_truncated_tensor_and_wrong_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.fixture(root)
            (directory / "output_f32.bin").write_bytes(bytes(4))
            with self.assertRaisesRegex(ValueError, "output_f32"):
                audit_capture(root, "blk_0_attn_q_weight", "q4_0")
            with self.assertRaisesRegex(ValueError, "metadata"):
                audit_capture(root, "blk_0_attn_q_weight", "q5_0")

    def test_saved_audit_detects_golden_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            directory = self.fixture(output / "capture")
            model = output / "model.gguf"
            binary = output / "llama-completion"
            model.write_bytes(b"model")
            binary.write_bytes(b"binary")
            (output / "console.log").write_text("capture completed\n")
            inputs = {
                "model": str(model), "model_sha256": sha256(model),
                "binary": str(binary), "binary_sha256": sha256(binary),
                "format": "q4_0", "operator": "blk_0_attn_q_weight",
                "prompt": PROMPT,
            }
            inputs_path = output / "inputs.json"
            inputs_path.write_text(json.dumps(inputs))
            result = audit_capture(output / "capture", inputs["operator"], inputs["format"])
            result.update({
                "command": [str(binary), "-m", str(model), "-p", PROMPT,
                            "-n", "2", "-t", "4", "-c", "256", "-no-cnv", "-nr"],
                "returncode": 0, "inputs_sha256": sha256(inputs_path),
                "model_sha256": sha256(model), "binary_sha256": sha256(binary),
                "console_sha256": sha256(output / "console.log"),
            })
            (output / "result.json").write_text(json.dumps(result))
            self.assertEqual(audit_existing(output)["status"], "PASS")
            (directory / "output_f32.bin").write_bytes(bytes([1, *([0] * 7)]))
            self.assertEqual(audit_existing(output)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
