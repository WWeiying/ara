#!/usr/bin/env python3

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("summarize_activation_lifetime.py")
SPEC = importlib.util.spec_from_file_location("summarize_activation_lifetime", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ActivationLifetimeTest(unittest.TestCase):
    def test_strict_qkv_group_and_cross_epoch_rejection(self):
        records = []
        weights = ("blk.0.attn_q.weight", "blk.0.attn_k.weight", "blk.0.attn_v.weight")
        outputs = (1536, 256, 256)
        for seq, (weight, output) in enumerate(zip(weights, outputs), 1):
            records.append(
                "GGML_RISCV_QBS_LIFETIME "
                f"seq={seq} graph_epoch=7 op=op{seq} weight={weight} weight_type=q4_K weight_profile=2 "
                f"source=attn_norm activation_type=q8_K activation_profile=1 m=1 n={output} k=1536 "
                f"bytes=1584 digest=0123456789abcdef match_seq={0 if seq == 1 else seq - 1} "
                f"match_weight={'-' if seq == 1 else weights[seq - 2]} same_tensor={0 if seq == 1 else 1} "
                f"same_data={0 if seq == 1 else 1} reusable={0 if seq == 1 else 1} "
                f"quantize_time_valid=1 quantize_time_us={10 + seq} op_id=0x{seq} weight_id=0x{seq + 10:x} "
                "source_id=0x100 source_data=0x200 quantized_data=0x300"
            )
            records.append(
                "GGML_RISCV_QBS_COMMAND "
                f"seq={seq} graph_epoch=7 activation_seq={seq} linked=1 weight_type=q4_K weight_profile=2 "
                "activation_profile=1 m=1 n=32 k_blocks=6 access=0 context_id=0 "
                f"context_generation={seq} segmented=0 emulated=0"
            )
        records.append(
            "GGML_RISCV_QBS_LIFETIME seq=4 graph_epoch=8 op=op4 weight=blk.0.attn_q.weight "
            "weight_type=q4_K weight_profile=2 source=attn_norm activation_type=q8_K activation_profile=1 "
            "m=1 n=1536 k=1536 bytes=1584 digest=0123456789abcdef match_seq=0 match_weight=- "
            "same_tensor=0 same_data=0 reusable=0 quantize_time_valid=1 quantize_time_us=14 "
            "op_id=0x4 weight_id=0xe source_id=0x100 source_data=0x200 quantized_data=0x300"
        )
        records.append(
            "GGML_RISCV_QBS_COMMAND seq=4 graph_epoch=8 activation_seq=4 linked=1 weight_type=q4_K "
            "weight_profile=2 activation_profile=1 m=1 n=32 k_blocks=6 access=0 context_id=0 "
            "context_generation=4 segmented=0 emulated=0"
        )
        records.append(
            "GGML_RISCV_QBS_LIFETIME_SUMMARY quantizations=4 exact_reuse_candidates=2 "
            "quantized_bytes=6336 reusable_quantized_bytes=3168 quantizations_with_time=4 "
            "quantize_time_us=50 reusable_quantize_time_us=25 graph_epochs=2"
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qemu.log"
            path.write_text("\n".join(records) + "\n", encoding="utf-8")
            lifetimes, commands, _ = MODULE.parse_log(path)
        groups = MODULE.build_groups(lifetimes, commands)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["family"], "attention_qkv")
        self.assertEqual(groups[0]["eligible_single_context"], 1)
        self.assertEqual(groups[0]["removable_quantizations"], 2)
        self.assertEqual(groups[0]["removable_quantized_bytes"], 3168)
        summary = MODULE.summarize(lifetimes, commands, groups)
        self.assertEqual(summary["graph_epochs"], 2)
        self.assertEqual(summary["unlinked_commands"], 0)

    def test_intervening_activation_rejects_single_context(self):
        base = {
            "graph_epoch": 1,
            "source_id": "0x10",
            "source": "ffn_norm",
            "activation_type": "q8_K",
            "activation_profile": 1,
            "m": 1,
            "k": 1536,
            "bytes": 1584,
            "digest": 1,
            "quantize_time_valid": 1,
            "quantize_time_us": 3,
        }
        lifetimes = [
            {**base, "seq": 1, "role": "ffn_gate", "weight": "blk.0.ffn_gate.weight", "n": 8960, "reusable": 0},
            {**base, "seq": 2, "role": "other", "weight": "other.weight", "n": 64, "reusable": 0},
            {**base, "seq": 3, "role": "ffn_up", "weight": "blk.0.ffn_up.weight", "n": 8960, "reusable": 1},
        ]
        commands = [
            {"seq": index, "activation_seq": index, "linked": 1}
            for index in (1, 2, 3)
        ]
        groups = MODULE.build_groups(lifetimes, commands)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["eligible_single_context"], 0)
        self.assertEqual(groups[0]["reject_reason"], "intervening_activation")

    def test_prefill_m14_is_not_counted_as_current_context_reuse(self):
        base = {
            "graph_epoch": 1,
            "source_id": "0x10",
            "source": "attn_norm",
            "activation_type": "q8_K",
            "activation_profile": 1,
            "m": 14,
            "k": 1536,
            "bytes": 24528,
            "digest": 1,
            "quantize_time_valid": 1,
            "quantize_time_us": 30,
        }
        lifetimes = [
            {**base, "seq": 1, "role": "attention_q", "weight": "blk.0.attn_q.weight", "n": 1536, "reusable": 0},
            {**base, "seq": 2, "role": "attention_k", "weight": "blk.0.attn_k.weight", "n": 256, "reusable": 1},
            {**base, "seq": 3, "role": "attention_v", "weight": "blk.0.attn_v.weight", "n": 256, "reusable": 1},
        ]
        commands = [
            {"seq": index, "activation_seq": index, "linked": 1, "m": 4, "segmented": 0}
            for index in (1, 2, 3)
        ]
        groups = MODULE.build_groups(lifetimes, commands)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["context_shape_supported"], 0)
        self.assertEqual(groups[0]["eligible_single_context"], 0)
        self.assertEqual(groups[0]["reject_reason"], "hardware_context_unsupported")

    def test_cross_operator_chain_and_run_selection(self):
        lines = ["AKV_TOKEN_RUN_BEGIN=QBS_CROSS_OP"]
        lines.append(
            "GGML_RISCV_QBS_CROSS_OP graph_epoch=2 action=fill_keep source_id=0x100 "
            "activation_profile=1 m=1 k=1536 generation=7 activation_seq=0 "
            "quantization_skipped=0 activation_bytes_saved=0 next_same=1"
        )
        lines.append(
            "GGML_RISCV_QBS_LIFETIME seq=1 graph_epoch=2 op=q weight=blk.0.attn_q.weight "
            "weight_type=q4_K weight_profile=2 source=attn_norm activation_type=q8_K activation_profile=1 "
            "m=1 n=1536 k=1536 bytes=1584 digest=0123456789abcdef match_seq=0 match_weight=- "
            "same_tensor=0 same_data=0 reusable=0 quantize_time_valid=1 quantize_time_us=10 "
            "op_id=0x1 weight_id=0x2 source_id=0x100 source_data=0x200 quantized_data=0x300"
        )
        for seq, access in enumerate((1, 2, 2), 1):
            lines.append(
                "GGML_RISCV_QBS_COMMAND "
                f"seq={seq} graph_epoch=2 activation_seq=1 linked=1 weight_type=q4_K weight_profile=2 "
                f"activation_profile=1 m=1 n=32 k_blocks=6 access={access} context_id=0 "
                "context_generation=7 segmented=0 emulated=0"
            )
        lines.append(
            "GGML_RISCV_QBS_CROSS_OP graph_epoch=2 action=reuse_keep source_id=0x100 "
            "activation_profile=1 m=1 k=1536 generation=7 activation_seq=1 "
            "quantization_skipped=1 activation_bytes_saved=1584 next_same=1"
        )
        lines.append(
            "GGML_RISCV_QBS_CROSS_OP graph_epoch=2 action=reuse_release source_id=0x100 "
            "activation_profile=1 m=1 k=1536 generation=7 activation_seq=1 "
            "quantization_skipped=1 activation_bytes_saved=1584 next_same=0"
        )
        lines.append(
            "GGML_RISCV_QBS_COMMAND seq=4 graph_epoch=2 activation_seq=1 linked=1 weight_type=q4_K "
            "weight_profile=2 activation_profile=1 m=1 n=32 k_blocks=6 access=3 context_id=0 "
            "context_generation=7 segmented=0 emulated=0"
        )
        lines.append(
            "GGML_RISCV_QBS_LIFETIME_SUMMARY quantizations=1 exact_reuse_candidates=0 "
            "quantized_bytes=1584 reusable_quantized_bytes=0 quantizations_with_time=1 "
            "quantize_time_us=10 reusable_quantize_time_us=0 graph_epochs=1 "
            "cross_op_fill=1 cross_op_reuse=2 cross_op_release=1 "
            "cross_op_quantization_skips=2 cross_op_activation_bytes_saved=3168"
        )
        lines.append("AKV_TOKEN_RUN_EXIT=QBS_CROSS_OP:0")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qemu.log"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            lifetimes, commands, trace_summary = MODULE.parse_log(path, "QBS_CROSS_OP")
            cross_ops = MODULE.parse_cross_ops(path, "QBS_CROSS_OP")
        result = MODULE.validate_cross_ops(lifetimes, commands, trace_summary, cross_ops)
        self.assertEqual(result["chains"], 1)
        self.assertEqual(result["quantization_skips"], 2)
        self.assertEqual(result["activation_bytes_saved"], 3168)

    def test_reused_activation_allows_a_different_weight_profile(self):
        lifetime = (
            "GGML_RISCV_QBS_LIFETIME seq=1 graph_epoch=2 op=q weight=blk.0.attn_q.weight "
            "weight_type=q4_K weight_profile=1 source=attn_norm activation_type=q8_K activation_profile=1 "
            "m=1 n=1536 k=1536 bytes=1752 digest=0123456789abcdef match_seq=0 match_weight=- "
            "same_tensor=0 same_data=0 reusable=0 quantize_time_valid=1 quantize_time_us=10 "
            "op_id=0x1 weight_id=0x2 source_id=0x100 source_data=0x200 quantized_data=0x300"
        )
        command = (
            "GGML_RISCV_QBS_COMMAND seq=1 graph_epoch=2 activation_seq=1 linked=1 "
            "weight_type=q6_K weight_profile=2 activation_profile=1 m=1 n=32 k_blocks=6 "
            "access=2 context_id=0 context_generation=1 segmented=0 emulated=0"
        )
        summary = (
            "GGML_RISCV_QBS_LIFETIME_SUMMARY quantizations=1 exact_reuse_candidates=0 "
            "quantized_bytes=1752 reusable_quantized_bytes=0 quantizations_with_time=1 "
            "quantize_time_us=10 reusable_quantize_time_us=0 graph_epochs=1"
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qemu.log"
            path.write_text("\n".join((lifetime, command, summary)) + "\n", encoding="utf-8")
            lifetimes, commands, _ = MODULE.parse_log(path)
            self.assertEqual(len(lifetimes), 1)
            self.assertEqual(len(commands), 1)

            bad_command = command.replace("activation_profile=1", "activation_profile=2")
            path.write_text("\n".join((lifetime, bad_command, summary)) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "activation profile differs"):
                MODULE.parse_log(path)

            bad_command = command.replace("m=1 n=32", "m=2 n=32")
            path.write_text("\n".join((lifetime, bad_command, summary)) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "row tile exceeds"):
                MODULE.parse_log(path)


if __name__ == "__main__":
    unittest.main()
