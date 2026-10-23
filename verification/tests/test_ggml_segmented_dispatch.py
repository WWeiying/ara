"""Fail-closed tests for GGML segmented-layout dispatch evidence."""
import importlib.util
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "qbs/run_ggml_segmented.py"
SPEC = importlib.util.spec_from_file_location("ggml_segmented", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    output = []
    for segment, wide in ((0, 0), (3, 0), (256, 1), (3, 1)):
        output.append(f"QBS_GRAPH_RUN_BEGIN segment={segment} wide={wide}\n")
        for threads in (1, 3):
            output.append("repack: repack tensor qbs_moe_weights with q2_K_4x1\n")
            for _ in range(6):
                output.append(f"GGML_RISCV_QBS_CALL type=q2_K mode=gemv k=1792 input_rows=1 output_rows=8 split_k={int(segment == 3)}\n")
                output.append("GGML_RISCV_QBS_COMMAND seq=1 m=1 n=8 k_blocks=3 access=0\n")
            output.append(f"QBS MUL_MAT_ID Q2_K 3-expert graph: PASS (threads {threads}, max abs error 0)\n")
        for _ in range(126):
            output.append(f"QBS_MATRIX_BEGIN type=q4_K m=8 n=37 k=1792 threads=1 segment={segment}\n")
            output.append(f"GGML_RISCV_QBS_CALL type=q4_K mode=gemm k=1792 input_rows=8 output_rows=37 split_k={int(segment == 3)}\n")
            output.append(f"GGML_RISCV_QBS_COMMAND seq=1 m={8 if segment == 256 else 4} n=16\n")
            output.append("QBS MUL_MAT graph: PASS\n")
        output.append(f"QBS_GRAPH_RUN_END segment={segment} wide={wide} exit=0\n")
    return "".join(output)


class DispatchEvidence(unittest.TestCase):
    def test_valid(self):
        MODULE.check_graph_dispatch(fixture())

    def test_wrong_policy(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_graph_dispatch(fixture().replace("threads=1 segment=3", "threads=1 segment=0"))

    def test_no_split(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_graph_dispatch(fixture().replace("split_k=1", "split_k=0"))

    def test_no_wide(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_graph_dispatch(fixture().replace("seq=1 m=8", "seq=1 m=4"))

    def test_missing_work(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_graph_dispatch(fixture().replace("output_rows=37", "output_rows=36"))

    def test_wrong_depth(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_graph_dispatch(fixture().replace("mode=gemm k=1792", "mode=gemm k=768"))

    def test_expert_wrong_depth(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_graph_dispatch(fixture().replace("mode=gemv k=1792", "mode=gemv k=768"))

    def test_expert_original_stride(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_graph_dispatch(fixture().replace("m=1 n=8 k_blocks=3", "m=1 n=4 k_blocks=3"))


def natural_fixture():
    output = []
    for segment, wide in ((0, 0), (256, 0), (256, 1)):
        output.append(f"QBS_GRAPH_RUN_BEGIN segment={segment} wide={wide}\n")
        for kind, k in (("q4_K", 71680), ("q8_0", 8960)):
            for m in (1, 3, 4):
                for threads in (1, 3):
                    output.append(f"QBS_MATRIX_BEGIN type={kind} m={m} n=37 k={k} threads={threads} segment={segment}\n")
                    output.append(f"GGML_RISCV_QBS_CALL type={kind} mode=gemm k={k} input_rows={m} output_rows=37 split_k=1\n")
                    for blocks in (256, 24):
                        for n in (32, 5):
                            output.append(f"GGML_RISCV_QBS_COMMAND seq=1 weight_type={kind} weight_profile=1 activation_profile=1 m={m} n={n} k_blocks={blocks} access=0 context_id=0 emulated=1\n")
                    output.append("QBS_NATURAL_DIGEST value=0123456789abcdef\n")
                    output.append("QBS MUL_MAT graph: PASS\n")
        output.append(f"QBS_GRAPH_RUN_END segment={segment} wide={wide} exit=0\n")
    return "".join(output)


class NaturalDispatchEvidence(unittest.TestCase):
    def test_valid(self):
        MODULE.check_natural_dispatch(natural_fixture())

    def test_no_split(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("split_k=1", "split_k=0"))

    def test_wrong_tail(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("k_blocks=24", "k_blocks=23"))

    def test_wrong_work(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("n=5 k_blocks=24", "n=4 k_blocks=24"))

    def test_missing_commands(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("GGML_RISCV_QBS_COMMAND", "MISSING"))

    def test_duplicate_shape(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("threads=3 segment=", "threads=1 segment="))

    def test_wrong_policy(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("segment=256\n", "segment=0\n"))

    def test_invalid_context(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("access=0", "access=1"))

    def test_not_software_reference(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("emulated=1", "emulated=0"))

    def test_changed_outputs(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("value=0123456789abcdef", "value=1123456789abcdef", 1))

    def test_missing_outputs(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(natural_fixture().replace("QBS_NATURAL_DIGEST", "MISSING"))


if __name__ == "__main__":
    unittest.main()
