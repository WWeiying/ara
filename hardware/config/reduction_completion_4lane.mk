# SPDX-License-Identifier: SHL-0.51
# Explicit experimental profile; default hardware/Makefile behavior is unchanged.
# Load BEFORE Makefile so its conditional feature definitions see these values:
# make -C hardware -f config/reduction_completion_4lane.mk -f Makefile compile
# Command-line assignments can disable individual features for ablation.
nr_lanes ?= 4
vlen ?= 1024

reduction_output_bypass ?= 1
reduction_route_bypass ?= 1
reduction_mask_fastpath ?= 1
reduction_mask_skip ?= 1
reduction_dense_input_bypass ?= 1
reduction_tree_input_bypass ?= 1
reduction_terminal_fusion ?= 1
reduction_context_flow ?= 1
reduction_context_stream ?= 1
reduction_slack_schedule ?= 1
reduction_heterogeneous_stream ?= 1
reduction_masked_stream ?= 1
reduction_tree_stage_pipeline ?= 1
reduction_ordered_interleave ?= 1
reduction_source_fusion ?= 1
reduction_ordered_fast ?= 1
reduction_exact_sum ?= 1
reduction_exact_segmented ?= 1
reduction_exact_global ?= 1
reduction_exact_fp16 ?= 1
reduction_exact_stream ?= 1
reduction_chain_bypass ?= 1
reduction_exact_no_round_bubble ?= 1
reduction_rce_int ?= 1
reduction_rce_compact_word ?= 1
reduction_rce_operand_isolation ?= 1
reduction_rce_fp_minmax ?= 1
reduction_rce_fp64_sum ?= 1
reduction_rce_mixed ?= 1
reduction_rce_exact_direct ?= 1
reduction_rce_exact ?= 1
reduction_rce_int_late_seed ?= 1
reduction_rce_queue_lookahead ?= 1
reduction_rce_word_turnaround ?= 1
reduction_rce_exact_egress_release ?= 1
reduction_rce_empty_bypass ?= 1
reduction_rce_word_sparse ?= 1
reduction_rce_split_credit ?= 1
reduction_rce_sldu_buffer ?= 1
reduction_rce_mfpu_restart ?= 1
reduction_rce_fp64_feedback ?= 1
# Sparse FP64: paired module/SoC checks and combined 106-program regression passed.
reduction_rce_fp64_sparse ?= 1
reduction_rce_exact_decouple ?= 1
reduction_rce_fp_late_seed ?= 1
reduction_rce_ordinary_seed ?= 1
reduction_rce_seed_lookahead ?= 1
# Seed admission/capture: paired checks and combined 106-program regression passed.
reduction_rce_seed_group ?= 1
reduction_rce_external_seed ?= 1

reduction_rce_alu_result_depth ?= 4
# Four slots remove the measured ordinary-result backpressure behind FP64 RCE.
# Override to 2 for the same-ELF queue-capacity ablation.
reduction_rce_fp_result_depth ?= 4
# This experimental same-VFU path regressed the measured FP seed workload.
reduction_rce_ordinary_seed_same_vfu ?= 0
