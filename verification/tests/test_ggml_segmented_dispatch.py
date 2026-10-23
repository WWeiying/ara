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


if __name__ == "__main__":
    unittest.main()
