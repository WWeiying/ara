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
                        for n in ((4,) * 9 + (1,) if segment == 0 and threads == 1 else (32, 5)):
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

    def test_tail_only_old_tiles(self):
        text = natural_fixture()
        marker = "QBS_GRAPH_RUN_BEGIN segment=256 wide=0"
        head, tail = text.split(marker, 1)
        line = "GGML_RISCV_QBS_COMMAND seq=1 weight_type=q4_K weight_profile=1 activation_profile=1 m=1 n=32 k_blocks=24 access=0 context_id=0 emulated=1\n"
        tail = tail.replace(line, line.replace("n=32", "n=4") * 8, 1)
        with self.assertRaises(RuntimeError):
            MODULE.check_natural_dispatch(head + marker + tail)


def context_fixture():
    output = []
    for segment, enabled in ((0, 1), (3, 1), (256, 1), (256, 0)):
        output.append(f"QBS_GRAPH_RUN_BEGIN segment={segment} wide=0\nQBS_CONTEXT_POLICY enabled={enabled}\n")
        graph_epoch = 0
        for blocks, m, shared, threads in ((2, 1, 1, 1), (7, 1, 1, 1), (7, 1, 0, 1), (7, 1, 1, 3), (7, 3, 1, 1), (7, 4, 1, 1)):
            split = segment == 3 and blocks > 3
            eligible = enabled and shared and m == 1 and threads == 1 and not split
            for epoch in (0, 1):
                graph_epoch += 1
                output.append(f"QBS_CONTEXT_BEGIN blocks={blocks} m={m} n=37 shared={shared} threads={threads} epoch={epoch} segment={segment}\n")
                for projection in (0, 1):
                    if eligible:
                        action = "reuse_release" if projection else "fill_keep"
                        output.append(f"GGML_RISCV_QBS_CROSS_OP graph_epoch={graph_epoch} action={action} source_id=0x123 activation_profile=1 m=1 k={blocks*256} generation=1 activation_seq=1 quantization_skipped={projection} next_same=0\n")
                    output.append(f"GGML_RISCV_QBS_CALL type=q4_K mode=gemm k={blocks*256} input_rows={m} output_rows=37 split_k={int(split)}\n")
                    for depth in ((3, 3, 1) if split else (blocks,)):
                        for n in (32, 5):
                            access = (1 if projection == 0 and n == 32 else 3 if projection == 1 and n == 5 else 2) if eligible else 0
                            if not eligible and not split and m == 1 and threads == 1:
                                access = 1 if n == 32 else 3
                            output.append(f"GGML_RISCV_QBS_COMMAND seq=1 weight_type=q4_K weight_profile=1 activation_profile=1 m={m} n={n} k_blocks={depth} access={access} context_id=0 emulated=0\n")
                output.append(f"QBS_CONTEXT_PASS outputs={3*m*37}\n")
        output.append(f"QBS_GRAPH_RUN_END segment={segment} wide=0 exit=0\n")
    return "".join(output)


class ContextDispatchEvidence(unittest.TestCase):
    def test_valid(self):
        MODULE.check_context_dispatch(context_fixture())

    def test_no_native_execution(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("emulated=0", "emulated=1"))

    def test_no_reuse(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("reuse_release", "fill_keep"))

    def test_no_quantization_skip(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("quantization_skipped=1", "quantization_skipped=0"))

    def test_wrong_work(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("n=5 k_blocks", "n=4 k_blocks"))

    def test_no_release(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("access=3", "access=2"))

    def test_stale_epoch(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("graph_epoch=2 ", "graph_epoch=1 "))

    def test_split_uses_context(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("k_blocks=3 access=0", "k_blocks=3 access=1"))

    def test_policy_disabled(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("QBS_CONTEXT_POLICY enabled=1", "QBS_CONTEXT_POLICY enabled=0"))


    def test_multirow_uses_context(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("m=3 n=32 k_blocks=7 access=0", "m=3 n=32 k_blocks=7 access=1"))

    def test_operation_local_context_missing(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("k_blocks=7 access=3", "k_blocks=7 access=0"))

    def test_split_depths_preserve_total_but_wrong_partitions(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_context_dispatch(context_fixture().replace("k_blocks=3", "k_blocks=2").replace("k_blocks=1", "k_blocks=3"))


def barrier_fixture():
    output = []
    for segment, enabled in ((0, 1), (3, 1), (256, 1), (256, 0)):
        output.append(f"QBS_GRAPH_RUN_BEGIN segment={segment} wide=0\nQBS_CONTEXT_POLICY enabled={enabled}\n")
        for epoch in (0, 1):
            output.append(f"QBS_CONTEXT_BEGIN blocks=2 m=1 n=37 shared=1 threads=1 epoch={epoch} segment={segment}\n")
            output.append("QBS_CONTEXT_MOE_BARRIER expert=1 rows=36\n")
            for n in (37, 36, 37):
                output.append(f"GGML_RISCV_QBS_CALL type=q4_K mode=gemv k=512 input_rows=1 output_rows={n} split_k=0\n")
                for cols, access in ((32, 1), (n - 32, 3)):
                    output.append(f"GGML_RISCV_QBS_COMMAND seq=1 weight_type=q4_K weight_profile=1 activation_profile=1 m=1 n={cols} k_blocks=2 access={access} context_id=0 emulated=0\n")
            output.append("QBS_CONTEXT_PASS outputs=111\nQBS_CONTEXT_MOE_PASS outputs=36\n")
        output.append(f"QBS_GRAPH_RUN_END segment={segment} wide=0 exit=0\n")
    return "".join(output)


class BarrierDispatchEvidence(unittest.TestCase):
    def test_valid(self):
        MODULE.check_barrier_dispatch(barrier_fixture())

    def test_missing_expert(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_barrier_dispatch(barrier_fixture().replace("QBS_CONTEXT_MOE_PASS", "MISSING"))

    def test_missing_release(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_barrier_dispatch(barrier_fixture().replace("access=3", "access=2"))

    def test_reservation(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_barrier_dispatch(barrier_fixture().replace("QBS_CONTEXT_MOE_BARRIER", "GGML_RISCV_QBS_CROSS_OP\nQBS_CONTEXT_MOE_BARRIER"))

    def test_wait(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_barrier_dispatch(barrier_fixture().replace("QBS_CONTEXT_MOE_BARRIER", "GGML_RISCV_QBS_CONTEXT_WAIT\nQBS_CONTEXT_MOE_BARRIER"))

    def test_wrong_expert_work(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_barrier_dispatch(barrier_fixture().replace("n=4 k_blocks", "n=3 k_blocks"))

    def test_emulated(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_barrier_dispatch(barrier_fixture().replace("emulated=0", "emulated=1"))


def alias_fixture():
    output = []
    for segment, enabled in ((0, 1), (3, 1), (256, 1), (256, 0)):
        output.append(f"QBS_GRAPH_RUN_BEGIN segment={segment} wide=0\nQBS_CONTEXT_POLICY enabled={enabled}\n")
        for kind in range(1, 5):
            for epoch in (0, 1):
                reuse = enabled and kind >= 3
                output.append(f"QBS_CONTEXT_BEGIN blocks=2 m=1 n=37 shared=1 threads=1 epoch={epoch} segment={segment}\n")
                output.append(f"QBS_CONTEXT_MUTATION kind={kind} writes_source={int(kind <= 2)}\n")
                if enabled and kind <= 2:
                    output.append("GGML_RISCV_QBS_CONTEXT_BARRIER graph_epoch=1 op=SCALE reason=may_modify_activation\n")
                for projection in (0, 1):
                    if reuse:
                        action = "reuse_release" if projection else "fill_keep"
                        output.append(f"GGML_RISCV_QBS_CROSS_OP graph_epoch=1 action={action} source_id=0x123 activation_profile=1 m=1 k=512 generation=1 activation_seq=1 quantization_skipped={projection} next_same=0\n")
                    output.append("GGML_RISCV_QBS_CALL type=q4_K mode=gemv k=512 input_rows=1 output_rows=37 split_k=0\n")
                    for n in (32, 5):
                        access = (1 if projection == 0 and n == 32 else 3 if projection == 1 and n == 5 else 2) if reuse else (1 if n == 32 else 3)
                        output.append(f"GGML_RISCV_QBS_COMMAND seq=1 weight_type=q4_K weight_profile=1 activation_profile=1 m=1 n={n} k_blocks=2 access={access} context_id=0 emulated=0\n")
                output.append("QBS_CONTEXT_MUTATION_INPUT_PASS words=512\nQBS_CONTEXT_PASS outputs=111\n")
        output.append(f"QBS_GRAPH_RUN_END segment={segment} wide=0 exit=0\n")
    return "".join(output)


class AliasDispatchEvidence(unittest.TestCase):
    def test_valid(self):
        MODULE.check_alias_dispatch(alias_fixture())

    def test_missing_input_check(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_alias_dispatch(alias_fixture().replace("MUTATION_INPUT_PASS", "MISSING"))

    def test_missing_write_barrier(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_alias_dispatch(alias_fixture().replace("reason=may_modify_activation", "reason=unknown"))

    def test_wrong_mutation(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_alias_dispatch(alias_fixture().replace("kind=2 writes_source=1", "kind=2 writes_source=0"))

    def test_lost_reuse(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_alias_dispatch(alias_fixture().replace("quantization_skipped=1", "quantization_skipped=0"))

    def test_wrong_context_identity(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_alias_dispatch(alias_fixture().replace("action=reuse_release source_id=0x123", "action=reuse_release source_id=0x456"))

    def test_not_native(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_alias_dispatch(alias_fixture().replace("emulated=0", "emulated=1"))

    def test_wrong_work(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_alias_dispatch(alias_fixture().replace("n=5 k_blocks", "n=4 k_blocks"))

    def test_duplicate_scenario(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_alias_dispatch(alias_fixture().replace("kind=4", "kind=3"))


if __name__ == "__main__":
    unittest.main()
