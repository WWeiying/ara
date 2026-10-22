import tempfile
import unittest
from pathlib import Path
import re
from unittest.mock import patch

from ara_verify.vector_signature import (
    VectorSignatureError,
    _count_program_vector_scalar_reads,
    _insert_defined_scalar_sources,
    _proven_index_rotation_reads,
    _is_vector_store_instruction,
    rewrite_deterministic_vector_policies,
    rewrite_vector_signature,
)


class VectorSignatureTests(unittest.TestCase):
    @staticmethod
    def index_constructor(width=32, count=15, nf=1):
        lmul = {16: "mf4", 32: "mf2", 64: "m1"}[width]
        code = ("la x26, user_stack_end\n"
                f"main: vsetvli t0, zero, e{width}, {lmul}, tu, mu "
                "#start riscv_vector_load_store_instr_stream_0\n")
        code += "".join(f"li t0, {2*i}\nvslide1down.vx v17, v17, t0\n" for i in range(count))
        code += "vmv.x.s t0, v17\nvslide1down.vx v17, v17, t0\n" * (16 - count)
        code += (f"li t0, {count}\nvsetvli a0, t0, e16, mf4, tu, mu\n"
                 "la s5, region_0+0\nli s2, 1\ncsrrw s2, vstart, s2\n")
        segment = f"seg{nf}" if nf > 1 else ""
        code += (f"vlux{segment}ei{width}.v v8, (s5), v17, v0.t\n"
                 "vmv.x.s a1, v19\ntest_done:\necall\nuser_stack_end:\n"
                 ".section .region_0,\"aw\",@progbits;\nregion_0:\n"
                 ".word " + ",".join(["0"] * 1024) + "\n")
        return code

    def test_index_rotations_preserved_but_other_scalar_reads_defined(self):
        for width, count, nf in ((16, 10, 4), (32, 10, 1), (32, 15, 1), (64, 15, 3)):
            with self.subTest(width=width, count=count, nf=nf), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "test.S"
                source.write_text(self.index_constructor(width, count, nf))
                result = rewrite_vector_signature(source, defined_scalar_sources=True)
                self.assertEqual(result.preserved_index_rotation_reads, 16 - count)
                self.assertEqual(result.defined_scalar_source_reads, 1)
                self.assertNotIn("vl1re8.v v17", source.read_text())
                self.assertIn("vl1re8.v v19", source.read_text())

    def test_index_rotation_exemption_fails_closed(self):
        baseline = self.index_constructor() + "__ara_region_0_end:\n"
        self.assertEqual(len(_proven_index_rotation_reads(baseline.splitlines(True), 1024)), 1)
        for old, new in (("li t0, 15\nvsetvli", "li t0, 14\nvsetvli"),
                         ("e32, mf2", "e32, m1"),
                         ("vslide1down.vx v17, v17, t0", "vslide1down.vx v17, v17, a0"),
                         ("la s5, region_0+0", "la s5, region_0+4090"),
                         ("li s2, 1", "vsub.vx v17, v1, a1"),
                         ("li s2, 1", "vmv2r.v v16, v20"),
                         ("li s2, 1", "li x21, 1"),
                         ("li s2, 1", "label: li s2, 1"),
                         ("csrrw s2, vstart, s2", "csrrw s2, vtype, s2"),
                         ("vluxei32.v v8, (s5), v17", "vluxei32.v v8, (s5), v16")):
            with self.subTest(old=old, new=new):
                changed = baseline.replace(old, new, 1).splitlines(True)
                self.assertFalse(_proven_index_rotation_reads(changed, 1024))
                rewritten, count = _insert_defined_scalar_sources(changed, "x26", None)
                self.assertEqual(count, 2)
                self.assertIn("vl1re8.v v17", "".join(rewritten))

    def test_defined_sources_cover_executed_subprograms(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "la x26, user_stack_end\nvsetivli x5, 4, e8, m1, ta, ma\n"
                "main: vcpop.m a0, v1\n"
                "test_done:\n  ecall\n"
                "sub_2: vfmv.f.s fa0, v3\n"
                "  vfirst.m a1, v4\n"
                "write_tohost: vmv.x.s a2, v5\n"
                "user_stack_end:\n", encoding="utf-8")
            result = rewrite_vector_signature(source, defined_scalar_sources=True)
            rewritten = source.read_text(encoding="utf-8")
            self.assertEqual(result.defined_scalar_source_reads, 3)
            self.assertIn("sub_2:\n                  # ARA_DSA_DEFINED_SCALAR_SOURCE_001",
                          rewritten)
            self.assertEqual(rewritten.count("ARA_DSA_DEFINED_SCALAR_SOURCE_"), 3)
            self.assertNotIn("vl1re8.v v5,", rewritten)

    def test_missing_scalar_read_instrumentation_fails_before_simulation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "la x26, user_stack_end\nvsetivli x5, 4, e8, m1, ta, ma\n"
                "main: vfmv.f.s fa0, v3\n"
                "test_done:\n  ecall\nuser_stack_end:\n", encoding="utf-8")
            with patch("ara_verify.vector_signature._SCALAR_VECTOR_READ_RE",
                       re.compile(r"^never$")):
                with self.assertRaisesRegex(VectorSignatureError, "0/1"):
                    rewrite_vector_signature(source, defined_scalar_sources=True)

    def test_defined_scalar_sources_preserve_labels_and_control_state(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "la x26, user_stack_end\n"
                "vsetivli x5, 4, e8, m1, ta, ma\n"
                "vmv.x.s a0, v1\n"
                "main: vcpop.m a1, v22, v0.t # masked count\n"
                "7: vmv.x.s a2, v16\n"
                "vfmv.f.s fa0, v3\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )
            result = rewrite_vector_signature(source, defined_scalar_sources=True)
            rewritten = source.read_text(encoding="utf-8")
            self.assertEqual(result.defined_scalar_source_reads, 3)
            self.assertIn("main:\n                  # ARA_DSA_DEFINED_SCALAR_SOURCE_000", rewritten)
            self.assertIn("7:\n                  # ARA_DSA_DEFINED_SCALAR_SOURCE_001", rewritten)
            self.assertIn("vl1re8.v v22, (x5)", rewritten)
            self.assertIn("vl1re8.v v0, (x5)", rewritten)
            self.assertIn("vl1re8.v v16, (x5)", rewritten)
            self.assertIn("vl1re8.v v3, (x5)", rewritten)
            self.assertIn("sd x5, 0(x26)", rewritten)
            self.assertIn("csrr x5, vstart", rewritten)
            self.assertIn("csrw vstart, x5", rewritten)
            self.assertEqual(rewritten.count(".byte "), 16)
            self.assertEqual(rewritten.count("ARA_DSA_DEFINED_SCALAR_SOURCE_"), 3)
            self.assertEqual(rewritten.count("vmv.x.s a0, v1"), 1)

    def test_defined_scalar_sources_empty_is_noop(self):
        text = (
            "la x26, user_stack_end\nvsetivli x5, 4, e8, m1, ta, ma\n"
            "main: vadd.vv v1, v2, v3\n"
            "test_done:\n  ecall\nuser_stack_end:\n"
        )
        lines = text.splitlines(keepends=True)
        self.assertEqual(_count_program_vector_scalar_reads(lines), 0)
        rewritten, count = _insert_defined_scalar_sources(lines, "x26", None)
        self.assertEqual(count, 0)
        self.assertEqual(rewritten, lines)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "defined.S"
            baseline = Path(directory) / "baseline.S"
            source.write_text(text)
            baseline.write_text(text)
            result = rewrite_vector_signature(source, defined_scalar_sources=True)
            rewrite_vector_signature(baseline)
            self.assertEqual(result.defined_scalar_source_reads, 0)
            self.assertEqual(source.read_bytes(), baseline.read_bytes())
            self.assertNotIn("__ara_defined_scalar_source", source.read_text())

    def test_defined_scalar_sources_reject_malformed_or_unknown_operands(self):
        for instruction in ("vmv.x.s a0, v32", "vcpop.m a0, unknown",
                            "vfirst.m a0", "vfmv.f.s fa0, v3, bad_mask"):
            with self.subTest(instruction=instruction), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "test.S"
                text = ("la x26, user_stack_end\nvsetivli x5, 4, e8, m1, ta, ma\nmain: " + instruction +
                        "\ntest_done:\n  ecall\nuser_stack_end:\n")
                source.write_text(text)
                with self.assertRaisesRegex(VectorSignatureError, "0/1"):
                    rewrite_vector_signature(source, defined_scalar_sources=True)
                self.assertEqual(source.read_text(), text)

    def test_defined_scalar_sources_reject_checkpoint_combination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "la x26, user_stack_end\nvsetivli x5, 4, e8, m1, ta, ma\n"
                "main: vadd.vv v1, v2, v3\n"
                "test_done:\n  ecall\nuser_stack_end:\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VectorSignatureError, "cannot be combined"):
                rewrite_vector_signature(
                    source, defined_scalar_sources=True, vector_checkpoints=True
                )

    def test_policy_only_rewrite_does_not_add_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "vadd.vv v1, v2, v3\n",
                encoding="utf-8",
            )

            policy_rewrites, dynamic_policy_rewrites = (
                rewrite_deterministic_vector_policies(source)
            )
            rewritten = source.read_text(encoding="utf-8")

            self.assertEqual(policy_rewrites, 1)
            self.assertEqual(dynamic_policy_rewrites, 0)
            self.assertIn("e32, m1, tu, mu", rewritten)
            self.assertNotIn("ARA_DSA_VECTOR_SIGNATURE", rewritten)

    def test_rewrites_policy_and_adds_full_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                ".section .text\n"
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "vsetivli x3, 4, e8, mf2, tu, ma # policy\n"
                "la x26, user_stack_end\n"
                "test_done:\n"
                "  li gp, 1\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )

            result = rewrite_vector_signature(source)
            rewritten = source.read_text(encoding="utf-8")

            self.assertEqual(result.policy_rewrites, 2)
            self.assertEqual(result.dynamic_policy_rewrites, 0)
            self.assertEqual(result.signature_bytes, 4096)
            self.assertEqual(result.scalar_check_loads, 512)
            self.assertIn("vsetvli x1, x2, e32, m1, tu, mu", rewritten)
            self.assertIn("vsetivli x3, 4, e8, mf2, tu, mu # policy", rewritten)
            self.assertEqual(rewritten.count("vs1r.v"), 32)
            self.assertEqual(rewritten.count("csrr x7, vl"), 32)
            self.assertIn("li x6, 512", rewritten)
            self.assertIn("addi x26, x26, -32", rewritten)
            self.assertIn("sd x5, 0(x26)", rewritten)
            self.assertIn("ld x7, 16(x26)", rewritten)
            self.assertIn("addi x26, x26, 32", rewritten)
            self.assertIn(".zero 4096", rewritten)
            self.assertIn(
                "__ara_vector_signature_exit_ecall:\n  ecall", rewritten
            )
            self.assertLess(rewritten.index("ARA_DSA_VECTOR_SIGNATURE_BEGIN"), rewritten.index("li gp, 1"))

    def test_rewrites_constant_dynamic_vsetvl_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "li x3, 0xd7\n"
                "vsetvl x1, x2, x3\n"
                "la x26, user_stack_end\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )
            result = rewrite_vector_signature(source)
            rewritten = source.read_text(encoding="utf-8")
            self.assertEqual(result.dynamic_policy_rewrites, 1)
            self.assertIn(
                "li x3, 0xd7\nli x3, 0x17\nvsetvl x1, x2, x3\nli x3, 0xd7",
                rewritten,
            )

    def test_rewrites_non_adjacent_constant_dynamic_vsetvl_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "li x21, 0xd7\n"
                "add x4, x5, x6\n"
                "vadd.vv v1, v2, v3\n"
                "vsetvl x1, x2, s5\n"
                "la x26, user_stack_end\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )
            result = rewrite_vector_signature(source)
            rewritten = source.read_text(encoding="utf-8")
            self.assertEqual(result.dynamic_policy_rewrites, 1)
            self.assertIn("li s5, 0x17\nvsetvl x1, x2, s5\nli s5, 0xd7", rewritten)

    def test_vsetvl_shared_avl_vtype_uses_distinct_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "li s3, 0x41\n"
                "vsetvl t4, s3, s3 # AVL and vtype alias\n",
                encoding="utf-8",
            )
            _, dynamic = rewrite_deterministic_vector_policies(source)
            self.assertEqual(dynamic, 1)
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "li s3, 0x41\nli t4, 0x1\n"
                "vsetvl t4, s3, t4 # AVL and vtype alias\n",
            )

    def test_vsetvl_shared_avl_vtype_without_scratch_destination_spills_gpr(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "la x26, user_stack_end\nli s3, 0x41\nvsetvl zero, s3, s3\n",
                encoding="utf-8",
            )
            _, dynamic = rewrite_deterministic_vector_policies(source)
            self.assertEqual(dynamic, 1)
            self.assertIn(
                "addi x26, x26, -16\nsd t6, 0(x26)\nli t6, 0x1\n"
                "vsetvl zero, s3, t6\nld t6, 0(x26)\naddi x26, x26, 16",
                source.read_text(encoding="utf-8"),
            )

    def test_rewrites_dynamic_vsetvl_after_numeric_local_label(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "bnez x4, 223f\n"
                "223: li x3, 0xd7\n"
                "vsetvl x1, x2, x3\n"
                "la x26, user_stack_end\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )

            result = rewrite_vector_signature(source)
            rewritten = source.read_text(encoding="utf-8")

            self.assertEqual(result.dynamic_policy_rewrites, 1)
            self.assertIn(
                "223: li x3, 0xd7\nli x3, 0x17\nvsetvl x1, x2, x3\nli x3, 0xd7",
                rewritten,
            )

    def test_accepts_non_adjacent_already_deterministic_vsetvl(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "li x21, 0\n"
                "vrgather.vx v1, v2, s5\n"
                "vsetvl x1, x2, s5\n"
                "la x26, user_stack_end\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )
            result = rewrite_vector_signature(source)
            rewritten = source.read_text(encoding="utf-8")
            self.assertEqual(result.dynamic_policy_rewrites, 1)
            self.assertEqual(rewritten.count("li x21, 0"), 1)
            self.assertNotIn("li s5", rewritten)

    def test_rejects_unproven_dynamic_vsetvl(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "la x26, user_stack_end\n"
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "add x3, x4, x5\n"
                "vsetvl x1, x2, x3\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VectorSignatureError, "not a constant li"):
                rewrite_vector_signature(source)

    def test_dynamic_vsetvl_with_shared_avl_and_vtype_preserves_avl(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "li x3, 0xd7\n"
                "vsetvl x3, x3, x3\n"
                "la x26, user_stack_end\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )
            result = rewrite_vector_signature(source)
            self.assertEqual(result.dynamic_policy_rewrites, 1)
            self.assertIn(
                "li t6, 0x17\nvsetvl x3, x3, t6\nld t6, 0(x26)",
                source.read_text(encoding="utf-8"),
            )

    def test_shared_sp_vsetvl_uses_reserved_user_stack(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "la x26, user_stack_end\nli sp, 0xc2\nvsetvl zero, sp, sp\n",
                encoding="utf-8",
            )
            rewrite_deterministic_vector_policies(source)
            self.assertIn(
                "addi x26, x26, -16\nsd t6, 0(x26)\nli t6, 0x2\n"
                "vsetvl zero, sp, t6\nld t6, 0(x26)\naddi x26, x26, 16",
                source.read_text(encoding="utf-8"),
            )

    def test_shared_avl_vtype_rejects_missing_reserved_stack(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text("li sp, 0xc2\nvsetvl zero, sp, sp\n", encoding="utf-8")
            with self.assertRaisesRegex(VectorSignatureError, "distinct reserved stack"):
                rewrite_deterministic_vector_policies(source)

    def test_rejects_ambiguous_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1\n"
                "test_done:\n"
                "  ecall\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VectorSignatureError, "cannot identify"):
                rewrite_vector_signature(source)

    def test_checkpoints_every_vector_instruction_in_main(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                ".section .text\n"
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "vle32.v v1, (x10) # initialization\n"
                "la x26, user_stack_end\n"
                "main: vadd.vv v2, v0, v1\n"
                "  add x8, x8, x9\n"
                "  vsetivli x3, 4, e8, mf2, ta, ma\n"
                "  vle8.v v4, (x11)\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )

            result = rewrite_vector_signature(source, vector_checkpoints=True)
            rewritten = source.read_text(encoding="utf-8")

            self.assertEqual(result.checkpoints, 4)
            self.assertEqual(result.checkpoint_source_indices, (0, 1, 2, 3))
            self.assertEqual(
                result.checkpoint_instructions,
                (
                    "initial_state",
                    "vadd.vv v2, v0, v1",
                    "vsetivli x3, 4, e8, mf2, tu, mu",
                    "vle8.v v4, (x11)",
                ),
            )
            self.assertEqual(result.scratch_stack_register, "x26")
            self.assertEqual(rewritten.count("ARA_DSA_VECTOR_CHECKPOINT_"), 4)
            self.assertIn("__ara_vector_checkpoint_000_read_loop:", rewritten)
            self.assertIn("__ara_vector_checkpoint_001_read_loop:", rewritten)
            self.assertIn("__ara_vector_checkpoint_002_read_loop:", rewritten)
            self.assertIn("__ara_vector_checkpoint_003_read_loop:", rewritten)
            self.assertIn("__ara_vector_checkpoint_001_instruction:", rewritten)
            self.assertEqual(rewritten.count("vs1r.v"), 160)
            self.assertEqual(rewritten.count("csrr x7, vl"), 164)
            self.assertEqual(rewritten.count("csrr x7, vtype"), 4)
            self.assertEqual(rewritten.count("csrr x7, vstart"), 4)
            self.assertEqual(rewritten.count("csrr x7, vcsr"), 4)
            self.assertEqual(rewritten.count("csrr x7, fcsr"), 4)
            self.assertIn("after vsetivli x3, 4, e8, mf2, tu, mu", rewritten)
            self.assertNotIn("after initialization", rewritten)
            self.assertIn("sd x5, 0(x26)", rewritten)
            self.assertIn("ld x5, 0(x26)", rewritten)

    def test_checkpoint_preserves_kernel_stack_and_enables_fcsr(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                ".section .text\n"
                "kernel_sp:\n"
                "  la x7, kernel_stack_end\n"
                "  vsetvli x10, x11, e32, m1, ta, ma\n"
                "  la x28, user_stack_end\n"
                "main:\n"
                "  vadd.vv v2, v0, v1\n"
                "test_done:\n"
                "  ecall\n"
                "kernel_stack_end:\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )

            result = rewrite_vector_signature(source, vector_checkpoints=True)
            rewritten = source.read_text(encoding="utf-8")

            self.assertEqual(result.checkpoints, 2)
            self.assertIn("csrr x29, fcsr", rewritten)
            self.assertNotIn("csrr x7, fcsr", rewritten)
            self.assertIn("li x29, 0x6000\n                  csrs mstatus, x29", rewritten)
            self.assertEqual(rewritten.count("csrs mstatus, x29"), 1)

    def test_selects_static_vector_checkpoint_indices(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                ".section .text\n"
                "la x26, user_stack_end\n"
                "main:\n"
                "  vadd.vv v2, v0, v1\n"
                "  vsetivli x3, 4, e8, mf2, ta, ma\n"
                "  vle8.v v4, (x11)\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )

            result = rewrite_vector_signature(
                source, vector_checkpoints=True, checkpoint_indices=(2,)
            )
            rewritten = source.read_text(encoding="utf-8")

            self.assertEqual(result.checkpoints, 2)
            self.assertEqual(result.checkpoint_source_indices, (0, 2))
            self.assertEqual(
                result.checkpoint_instructions,
                ("initial_state", "vsetivli x3, 4, e8, mf2, tu, mu"),
            )
            self.assertIn("__ara_vector_checkpoint_001_instruction:", rewritten)
            self.assertNotIn("__ara_vector_checkpoint_002_instruction:", rewritten)

    def test_uses_non_destructive_mask_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                ".section .text\n"
                "la x26, user_stack_end\n"
                "main:\n"
                "  vadd.vv v2, v0, v1\n"
                "  vsetivli x3, 4, e8, mf2, ta, ma\n"
                "  vmseq.vi v20, v4, 4\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )

            result = rewrite_vector_signature(
                source,
                vector_checkpoints=True,
                checkpoint_indices=(3,),
                checkpoint_mask_register=20,
            )
            rewritten = source.read_text(encoding="utf-8")

            self.assertEqual(result.checkpoint_mask_register, 20)
            self.assertEqual(result.checkpoint_source_indices, (0, 3))
            self.assertIn("vcpop.m x7, v20", rewritten)
            self.assertNotIn("vs1r.v v0", rewritten.split("test_done:", 1)[0])
            self.assertEqual(result.checkpoint_memory_sites, ())

    def test_rejects_mask_checkpoint_without_vector_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "la x26, user_stack_end\n"
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "main: vadd.vv v2, v0, v1\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                VectorSignatureError, "mask checkpoint register requires vector checkpoints"
            ):
                rewrite_vector_signature(source, checkpoint_mask_register=20)

    def test_checkpoints_require_riscv_dv_user_stack(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "main: vadd.vv v2, v0, v1\n"
                "test_done:\n"
                "  ecall\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VectorSignatureError, "user stack register"):
                rewrite_vector_signature(source, vector_checkpoints=True)

    def test_checkpoints_vector_instructions_in_called_subroutines(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                ".section .text\n"
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "la x26, user_stack_end\n"
                "main: vadd.vv v2, v0, v1\n"
                "  call sub_1\n"
                "test_done:\n"
                "  ecall\n"
                "sub_1: vsub.vv v3, v2, v1\n"
                "  ret\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )

            result = rewrite_vector_signature(source, vector_checkpoints=True)

            self.assertEqual(result.checkpoints, 3)
            self.assertEqual(
                result.checkpoint_instructions,
                (
                    "initial_state",
                    "vadd.vv v2, v0, v1",
                    "vsub.vv v3, v2, v1",
                ),
            )

    def test_signature_avoids_a_temporary_used_as_user_stack(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "la x5, user_stack_end\n"
                "test_done:\n"
                "  ecall\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )

            result = rewrite_vector_signature(source)
            rewritten = source.read_text(encoding="utf-8")

            self.assertEqual(result.scratch_stack_register, "x5")
            self.assertIn("addi x5, x5, -32", rewritten)
            self.assertIn("sd x6, 0(x5)", rewritten)
            self.assertIn("sd x7, 8(x5)", rewritten)
            self.assertIn("sd x28, 16(x5)", rewritten)
            self.assertNotIn("sd x5, 0(x5)", rewritten)

    def test_checkpoints_read_every_generated_memory_region_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                ".section .text\n"
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "la x26, user_stack_end\n"
                "main:\n"
                "  vse32.v v1, (x10)\n"
                "test_done:\n"
                "  ecall\n"
                ".section .region_0,\"aw\",@progbits;\n"
                "region_0:\n"
                "  .byte 1, 2, 3\n"
                ".section .region_1,\"aw\",@progbits;\n"
                "region_1:\n"
                "  .byte 4, 5\n"
                ".section .user_stack,\"aw\",@progbits;\n"
                "user_stack_end:\n",
                encoding="utf-8",
            )

            result = rewrite_vector_signature(source, vector_checkpoints=True)
            rewritten = source.read_text(encoding="utf-8")

            self.assertEqual(result.checkpoint_memory_regions, ("region_0", "region_1"))
            self.assertIn("__ara_region_0_end:", rewritten)
            self.assertIn("__ara_region_1_end:", rewritten)
            self.assertEqual(result.checkpoint_memory_sites, (1,))
            self.assertEqual(rewritten.count("_region_0_read_loop:"), 1)
            self.assertEqual(rewritten.count("_region_1_read_loop:"), 1)
            self.assertIn("lbu x7, 0(x5)", rewritten)
            self.assertIn("beqz x6, __ara_vector_checkpoint_001_region_1_read_done", rewritten)

    def test_only_vector_stores_trigger_memory_signatures(self):
        stores = (
            "vse8.v v1, (x10)",
            "vsse64.v v2, (x11), x12",
            "vsuxei32.v v3, (x13), v4",
            "vsoxseg4ei16.v v8, (x14), v5",
            "vssseg8e32.v v16, (x15), x16",
            "vs8r.v v24, (x17)",
            "vsm.v v0, (x18)",
        )
        non_stores = (
            "vsadd.vv v1, v2, v3",
            "vssrl.vx v1, v2, x3",
            "vsub.vv v1, v2, v3",
            "vsetvli x1, x2, e32, m1, tu, mu",
            "vle32.v v1, (x10)",
        )

        self.assertTrue(all(_is_vector_store_instruction(item) for item in stores))
        self.assertFalse(any(_is_vector_store_instruction(item) for item in non_stores))
