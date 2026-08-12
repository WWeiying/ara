import tempfile
import unittest
from pathlib import Path

from ara_verify.vector_signature import (
    VectorSignatureError,
    _is_vector_store_instruction,
    rewrite_deterministic_vector_policies,
    rewrite_vector_signature,
)


class VectorSignatureTests(unittest.TestCase):
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
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "add x3, x4, x5\n"
                "vsetvl x1, x2, x3\n"
                "test_done:\n"
                "  ecall\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VectorSignatureError, "not a constant li"):
                rewrite_vector_signature(source)

    def test_rejects_dynamic_vsetvl_with_shared_avl_and_vtype(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.S"
            source.write_text(
                "vsetvli x1, x2, e32, m1, ta, ma\n"
                "li x3, 0xd7\n"
                "vsetvl x1, x3, x3\n"
                "test_done:\n"
                "  ecall\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VectorSignatureError, "both AVL and vtype"):
                rewrite_vector_signature(source)

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
