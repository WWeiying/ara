ROOT := $(abspath ../..)
BUILD ?= $(CURDIR)/build
override BUILD := $(abspath $(BUILD))
REFERENCE ?= 1b0aec5f
VCS ?= vcs
RUN_TIMEOUT ?= 300
SIM_ARGS ?=
ADAPTER_REFERENCE ?= 7b7c3de0
SRAM_REFERENCE ?= be1487b5
SRAM_DEFINES ?=
SRAM_EXTRA_SOURCES ?=
HELPER_REFERENCE ?= 1b0aec5f
DATAPATH_REFERENCE ?= HEAD
AREA_REFERENCE ?= 630e16b3
AREA_DEFINES ?=
BEFORE_DIR ?=
VFDSU_DIR := $(ROOT)/hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl
GATED_CLOCK := $(ROOT)/hardware/deps/fpnew/vendor/opene906/E906_RTL_FACTORY/gen_rtl/clk/rtl/gated_clk_cell.v
DISPATCHER_BEFORE ?=
DISPATCHER_FEATURES ?= +define+ARA_QBS_ENABLE+ARA_AKV_ENABLE+ARA_AKV_V2_ENABLE
DISPATCHER_CHECK_ARGS ?=

.PHONY: qbs-pipeline-check
.PHONY: decoder-check
.PHONY: area-engine-check
area-engine-check:
	mkdir -p $(BUILD)/area_reference
	git -C $(ROOT) show $(AREA_REFERENCE):hardware/src/vlsu/qbs/qbs_block_adapter.sv > $(BUILD)/area_reference/original.sv
	sed -e 's/\bqbs_block_adapter\b/qbs_block_adapter_area_reference/g' \
		-e 's/logic \[255:0\] weight_window_o \[4\]\[2\], activation_window_o \[4\]/logic [127:0] weight_window_o [4][2], output logic [255:0] activation_window_o [4]/' \
		$(BUILD)/area_reference/original.sv > $(BUILD)/area_reference/adapter.sv
	$(MAKE) -C $(ROOT)/verification/qbs rtl-engine-check \
		RTL_ENGINE_BUILD=$(BUILD)/engine RTL_RUN_TIMEOUT=$(RUN_TIMEOUT) \
		RTL_ENGINE_DEFINES="$(AREA_DEFINES)" \
		RTL_EXTRA_SOURCES="$(BUILD)/area_reference/adapter.sv $(CURDIR)/qbs_adapter_area_checker.sv $(CURDIR)/qbs_unique_commit_checker.sv"

decoder-check:
	mkdir -p $(BUILD)/decoder
	git -C $(ROOT) show $(AREA_REFERENCE):hardware/src/vlsu/qbs/qbs_profile_decoder.sv > $(BUILD)/decoder/original.sv
	sed 's/\bqbs_profile_decoder\b/qbs_profile_decoder_reference/g' $(BUILD)/decoder/original.sv > $(BUILD)/decoder/reference.sv
	cd $(BUILD)/decoder && $(VCS) -full64 -sverilog -timescale=1ns/1ps -l compile.log \
		$(ROOT)/hardware/include/qbs_pkg.sv $(ROOT)/hardware/src/vlsu/qbs/qbs_profile_decoder.sv \
		reference.sv $(CURDIR)/qbs_decoder_equivalence_tb.sv -top qbs_decoder_equivalence_tb -o simv
	cd $(BUILD)/decoder && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log
	grep -q 'QBS decoder equivalence PASS' $(BUILD)/decoder/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/decoder/run.log

qbs-pipeline-check:
	mkdir -p $(BUILD)/dot_pipeline
	cd $(BUILD)/dot_pipeline && $(VCS) -full64 -sverilog -timescale=1ns/1ps -l compile.log \
		$(ROOT)/hardware/src/vlsu/qbs/qbs_dot_array.sv $(CURDIR)/qbs_dot_pipeline_tb.sv \
		-top qbs_dot_pipeline_tb -o simv
	cd $(BUILD)/dot_pipeline && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log
	grep -q 'QBS dot pipeline PASS' $(BUILD)/dot_pipeline/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/dot_pipeline/run.log

.PHONY: feedback-check
feedback-check:
	@test -n "$(BEFORE_DIR)"
	python3 generate_feedback_checks.py --before $(BEFORE_DIR) --output $(BUILD)/feedback
	cd $(BUILD)/feedback && $(VCS) -full64 -sverilog -timescale=1ns/1ps -l compile.log \
		+incdir+$(ROOT)/hardware/deps/common_cells/include \
		$(ROOT)/hardware/deps/common_cells/src/cf_math_pkg.sv \
		$(ROOT)/hardware/deps/common_cells/src/lzc.sv \
		after/qbs_correction_select_timing.sv qbs_correction_select_timing_reference.sv \
		after/qbs_address_timing.sv qbs_address_timing_reference.sv \
		$(CURDIR)/feedback_cones_tb.sv -top feedback_cones_tb -o simv
	cd $(BUILD)/feedback && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log
	grep -q 'Feedback cones PASS' $(BUILD)/feedback/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/feedback/run.log

.PHONY: dispatcher-check
dispatcher-check:
	@test -n "$(DISPATCHER_BEFORE)"
	python3 generate_dispatcher_check.py --before $(DISPATCHER_BEFORE) --output $(BUILD)/dispatcher $(DISPATCHER_CHECK_ARGS)
	cd $(BUILD)/dispatcher && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+define+FOR_VERIFY $(DISPATCHER_FEATURES) \
		+incdir+$(ROOT)/hardware/deps/common_cells/include+$(ROOT)/hardware/include+$(BUILD)/dispatcher \
		-l compile.log $(PACKAGES) $(ROOT)/hardware/deps/cva6/core/include/build_config_pkg.sv \
		$(ROOT)/hardware/include/qbs_pkg.sv \
		$(ROOT)/hardware/include/akv_pkg.sv dispatcher_check_pkg.sv \
		$(ROOT)/hardware/deps/common_cells/src/popcount.sv \
		$(ROOT)/hardware/deps/common_cells/src/delta_counter.sv \
		$(ROOT)/hardware/deps/common_cells/src/counter.sv \
		$(ROOT)/hardware/src/segment_sequencer.sv \
		segment_sequencer_reference.sv \
		ara_dispatcher_reference.sv $(ROOT)/hardware/src/ara_dispatcher.sv \
		$(CURDIR)/ara_dispatcher_timing.sv \
		dispatcher_equivalence_tb.sv -top dispatcher_equivalence_tb -o simv
	cd $(BUILD)/dispatcher && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log
	grep -q 'Dispatcher equivalence PASS' $(BUILD)/dispatcher/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/dispatcher/run.log

.PHONY: dispatcher-layout-check
dispatcher-layout-check:
	$(MAKE) dispatcher-check DISPATCHER_CHECK_ARGS=--layout
	cd $(BUILD)/dispatcher && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+incdir+$(ROOT)/hardware/deps/common_cells/include -l layout_compile.log \
		$(PACKAGES) layout.sv -top layout_tb -o layout_simv
	cd $(BUILD)/dispatcher && timeout --foreground $(RUN_TIMEOUT) ./layout_simv -l layout_run.log
	grep -q 'Dispatcher layout equivalence PASS' $(BUILD)/dispatcher/layout_run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/dispatcher/layout_run.log

.PHONY: closure-cones address-check round-check akv-count-check
.PHONY: vstu-check
vstu-check:
	@test -n "$(BEFORE_DIR)"
	python3 generate_vstu_check.py --before $(BEFORE_DIR)/vstu.sv --output $(BUILD)/vstu
	cd $(BUILD)/vstu && $(VCS) -full64 -sverilog -timescale=1ns/1ps -l compile.log \
		+incdir+$(ROOT)/hardware/deps/common_cells/include+$(ROOT)/hardware/include+$(BUILD)/vstu \
		$(PACKAGES) $(ROOT)/hardware/deps/common_cells/src/spill_register_flushable.sv \
		$(ROOT)/hardware/deps/common_cells/src/fifo_v3.sv \
		$(ROOT)/hardware/deps/common_cells/src/fall_through_register.sv \
		$(ROOT)/hardware/src/vlsu/vstu.sv vstu_reference.sv $(CURDIR)/vstu_equivalence_tb.sv \
		-top vstu_equivalence_tb -o simv
	cd $(BUILD)/vstu && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log
	grep -q 'VSTU equivalence PASS' $(BUILD)/vstu/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/vstu/run.log

closure-cones:
	@test -n "$(BEFORE_DIR)"
	python3 generate_closure_checks.py --before-dir $(BEFORE_DIR) --output $(BUILD)/cones

address-check:
	@test -n "$(BEFORE_DIR)"
	python3 generate_closure_checks.py --before-dir $(BEFORE_DIR) --output $(BUILD)/cones --address-only
	cd $(BUILD)/cones && $(VCS) -full64 -sverilog -timescale=1ns/1ps -l address_compile.log \
		$(PACKAGES) addrgen_cones.sv $(CURDIR)/addrgen_end_equivalence_tb.sv \
		-top addrgen_end_equivalence_tb -o address_simv
	cd $(BUILD)/cones && timeout --foreground $(RUN_TIMEOUT) ./address_simv -l address_run.log
	grep -q 'AddrGen equivalence PASS' $(BUILD)/cones/address_run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/cones/address_run.log

round-check: closure-cones
	cd $(BUILD)/cones && $(VCS) -full64 -sverilog -timescale=1ns/1ps -l round_compile.log \
		$(GATED_CLOCK) $(VFDSU_DIR)/ct_vfdsu_round.v round_reference.v round_tb.sv \
		-top vfdsu_round_equivalence_tb -o round_simv
	cd $(BUILD)/cones && timeout --foreground $(RUN_TIMEOUT) ./round_simv -l round_run.log
	grep -q 'VFDSU round equivalence PASS' $(BUILD)/cones/round_run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/cones/round_run.log

akv-count-check: closure-cones
	cd $(BUILD)/cones && $(VCS) -full64 -sverilog -timescale=1ns/1ps -l akv_count_compile.log \
		$(PACKAGES) $(ROOT)/hardware/include/akv_pkg.sv akv_count_cone.sv \
		$(CURDIR)/akv_count_equivalence_tb.sv -top akv_count_equivalence_tb -o akv_count_simv
	cd $(BUILD)/cones && timeout --foreground $(RUN_TIMEOUT) ./akv_count_simv -l akv_count_run.log
	grep -q 'AKV count equivalence PASS' $(BUILD)/cones/akv_count_run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/cones/akv_count_run.log

.PHONY: datapath-check
datapath-check:
	mkdir -p $(BUILD)/datapath
	git -C $(ROOT) show $(DATAPATH_REFERENCE):hardware/src/lane/simd_alu.sv > $(BUILD)/datapath/alu.original.sv
	sed 's/\bsimd_alu\b/simd_alu_reference/g' $(BUILD)/datapath/alu.original.sv > $(BUILD)/datapath/alu.reference.sv
	git -C $(ROOT) show $(DATAPATH_REFERENCE):hardware/src/vlsu/qbs/qbs_dot_array.sv > $(BUILD)/datapath/dot.original.sv
	sed 's/\bqbs_dot_array\b/qbs_dot_array_reference/g' $(BUILD)/datapath/dot.original.sv > $(BUILD)/datapath/dot.reference.sv
	cd $(BUILD)/datapath && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(PACKAGES) \
		$(ROOT)/hardware/src/lane/fixed_p_rounding.sv $(ROOT)/hardware/src/lane/simd_alu.sv \
		$(ROOT)/hardware/src/vlsu/qbs/qbs_dot_array.sv alu.reference.sv dot.reference.sv \
		$(CURDIR)/datapath_equivalence_tb.sv -top datapath_equivalence_tb -o simv
	cd $(BUILD)/datapath && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log
	grep -q 'Timing datapath equivalence PASS' $(BUILD)/datapath/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/datapath/run.log

QBS_MODULES := qbs_fp_accumulator qbs_profile_engine_int
QBS_REFERENCES := $(addprefix $(BUILD)/,$(addsuffix _reference.sv,$(QBS_MODULES)))
PACKAGES := $(ROOT)/hardware/deps/common_cells/src/cf_math_pkg.sv \
	$(ROOT)/hardware/deps/axi/src/axi_pkg.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_pkg.sv \
	$(ROOT)/hardware/deps/cva6/core/include/config_pkg.sv \
	$(ROOT)/hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv \
	$(ROOT)/hardware/deps/cva6/core/include/riscv_pkg.sv \
	$(ROOT)/hardware/include/rvv_pkg.sv \
	$(ROOT)/hardware/include/ara_pkg.sv

.PHONY: check qbs-check alu-check bounds-check references adapter-references adapter-check adapter-engine-check adapter-baseline-engine-check
check: bounds-check helpers-check descriptor-alignment-check qbs-check alu-check sram-check

.PHONY: helpers-check
.PHONY: mul-check
mul-check:
	mkdir -p $(BUILD)/mul
	git -C $(ROOT) show $(REFERENCE):hardware/src/lane/simd_mul.sv > $(BUILD)/mul/original.sv
	sed 's/\bsimd_mul\b/simd_mul_reference/g' $(BUILD)/mul/original.sv > $(BUILD)/mul/reference.sv
	cd $(BUILD)/mul && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+incdir+$(ROOT)/hardware/deps/common_cells/include +lint=TFIPC-L -l compile.log \
		$(PACKAGES) $(ROOT)/hardware/src/lane/simd_mul.sv \
		reference.sv $(CURDIR)/simd_mul_equivalence_tb.sv -top simd_mul_equivalence_tb -o simv
	cd $(BUILD)/mul && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log
	grep -q 'SIMD MUL equivalence PASS' $(BUILD)/mul/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/mul/run.log

.PHONY: descriptor-alignment-check
descriptor-alignment-check:
	mkdir -p $(BUILD)/descriptor
	python3 extract_descriptor_alignment.py $(BUILD)/descriptor/alignment_dut.sv
	cd $(BUILD)/descriptor && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log alignment_dut.sv \
		$(CURDIR)/descriptor_alignment_checker.sv $(CURDIR)/descriptor_alignment_tb.sv \
		-top descriptor_alignment_tb -o simv
	cd $(BUILD)/descriptor && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log
	grep -q 'Descriptor alignment PASS' $(BUILD)/descriptor/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/descriptor/run.log

helpers-check:
	mkdir -p $(BUILD)/helpers
	git -C $(ROOT) show $(HELPER_REFERENCE):hardware/include/ara_pkg.sv > $(BUILD)/helpers/ara_pkg.original.sv
	sed 's/\bara_pkg\b/ara_pkg_reference/g' $(BUILD)/helpers/ara_pkg.original.sv > $(BUILD)/helpers/ara_pkg_reference.sv
	cd $(BUILD)/helpers && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(PACKAGES) ara_pkg_reference.sv \
		$(CURDIR)/synthesis_helpers_tb.sv -top synthesis_helpers_tb -o simv
	cd $(BUILD)/helpers && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log
	grep -q 'Synthesis helpers PASS' $(BUILD)/helpers/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/helpers/run.log

bounds-check:
	python3 test_qbs_bounds.py

# Generated reference copies stay in the build directory, not in RTL sources.
references:
	mkdir -p $(BUILD)
	git -C $(ROOT) rev-parse $(REFERENCE) > $(BUILD)/reference.commit
	git -C $(ROOT) show $(REFERENCE):hardware/src/lane/simd_alu.sv > $(BUILD)/simd_alu.original.sv
	sed 's/\bsimd_alu\b/simd_alu_reference/g' $(BUILD)/simd_alu.original.sv > $(BUILD)/simd_alu_reference.sv
	git -C $(ROOT) show $(REFERENCE):hardware/src/vlsu/qbs/qbs_fp_accumulator.sv > $(BUILD)/qbs_fp_accumulator.original.sv
	sed 's/\bqbs_fp_accumulator\b/qbs_fp_accumulator_reference/g' $(BUILD)/qbs_fp_accumulator.original.sv > $(BUILD)/qbs_fp_accumulator_reference.sv
	git -C $(ROOT) show $(REFERENCE):hardware/src/vlsu/qbs/qbs_profile_engine_int.sv > $(BUILD)/qbs_profile_engine_int.original.sv
	sed 's/\bqbs_profile_engine_int\b/qbs_profile_engine_int_reference/g' $(BUILD)/qbs_profile_engine_int.original.sv > $(BUILD)/qbs_profile_engine_int_reference.sv

# The integer pipeline is retimed. Its primary oracle is the independent C
# model (groups, integer subtotals, FP results and flags), not cycle equality.
qbs-check: qbs-pipeline-check
	$(MAKE) -C $(ROOT)/verification/qbs rtl-profile-check rtl-engine-check \
		RTL_BUILD=$(BUILD)/profile RTL_ENGINE_BUILD=$(BUILD)/qbs RTL_RUN_TIMEOUT=$(RUN_TIMEOUT)

# Historical zero-latency-change experiments only; not the pipelined design.
.PHONY: qbs-cycle-check
qbs-cycle-check: references
	$(MAKE) -C $(ROOT)/verification/qbs rtl-profile-check rtl-engine-check \
		RTL_BUILD=$(BUILD)/profile \
		RTL_ENGINE_BUILD=$(BUILD)/qbs RTL_RUN_TIMEOUT=$(RUN_TIMEOUT) \
		RTL_EXTRA_SOURCES="$(QBS_REFERENCES) $(CURDIR)/qbs_equivalence.sv"

alu-check: references
	mkdir -p $(BUILD)/alu
	cd $(BUILD)/alu && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(PACKAGES) \
		$(ROOT)/hardware/src/lane/fixed_p_rounding.sv \
		$(ROOT)/hardware/src/lane/simd_alu.sv \
		$(BUILD)/simd_alu_reference.sv $(CURDIR)/simd_alu_equivalence_tb.sv \
		-top simd_alu_equivalence_tb -o simv
	cd $(BUILD)/alu && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log $(SIM_ARGS)
	grep -q 'SIMD ALU equivalence PASS' $(BUILD)/alu/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/alu/run.log

adapter-references:
	mkdir -p $(BUILD)
	git -C $(ROOT) rev-parse $(ADAPTER_REFERENCE) > $(BUILD)/adapter_reference.commit
	git -C $(ROOT) show $(ADAPTER_REFERENCE):hardware/src/vlsu/qbs/qbs_block_adapter.sv > $(BUILD)/qbs_block_adapter.original.sv
	sed 's/\bqbs_block_adapter\b/qbs_block_adapter_reference/g' $(BUILD)/qbs_block_adapter.original.sv > $(BUILD)/qbs_block_adapter_reference.sv

# The storage interface changed. Keep familiar target names, but use the
# handshake/window-aware checker rather than the old full-array cycle miter.
adapter-check: sram-check

adapter-engine-check: sram-engine-check

BASELINE_ROOT ?=
adapter-baseline-engine-check:
	@test -n "$(BASELINE_ROOT)" || (echo "Set BASELINE_ROOT to a clean $(SRAM_REFERENCE) worktree"; exit 2)
	@test "$$(git -C $(BASELINE_ROOT) rev-parse HEAD)" = "$$(git -C $(ROOT) rev-parse $(SRAM_REFERENCE))"
	git -C $(BASELINE_ROOT) diff --quiet HEAD -- hardware/src hardware/include
	$(MAKE) -C $(BASELINE_ROOT)/verification/qbs rtl-engine-check \
		RTL_ENGINE_BUILD=$(BUILD)/baseline_engine RTL_RUN_TIMEOUT=$(RUN_TIMEOUT)

.PHONY: sram-references sram-check sram-engine-check
.PHONY: payload-check
payload-check:
	mkdir -p $(BUILD)/payload
	cd $(BUILD)/payload && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(ROOT)/hardware/include/qbs_pkg.sv \
		$(ROOT)/hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv \
		$(ROOT)/hardware/src/vlsu/qbs/qbs_payload_sram.sv \
		$(ROOT)/hardware/src/vlsu/qbs/qbs_payload_buffer.sv \
		$(CURDIR)/qbs_payload_reference.sv $(CURDIR)/qbs_payload_equivalence_tb.sv \
		-top qbs_payload_equivalence_tb -o simv
	cd $(BUILD)/payload && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log $(SIM_ARGS)
	grep -q 'QBS payload equivalence PASS' $(BUILD)/payload/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/payload/run.log

sram-references:
	$(MAKE) adapter-references BUILD=$(BUILD) ADAPTER_REFERENCE=$(SRAM_REFERENCE)

.PHONY: stream-check
.PHONY: unique-adapter-check
unique-adapter-check:
	$(MAKE) sram-check BUILD=$(BUILD) \
		SRAM_DEFINES="$(SRAM_DEFINES) +define+QBS_STREAM_EQUIV+QBS_UNIQUE_INPUT_BYTES" \
		SRAM_EXTRA_SOURCES="$(SRAM_EXTRA_SOURCES) $(CURDIR)/qbs_unique_commit_checker.sv" \
		SIM_ARGS="$(SIM_ARGS) +QBS_STROBE_STRIDE=257"

stream-check:
	$(MAKE) sram-check BUILD=$(BUILD) \
		SRAM_DEFINES="$(SRAM_DEFINES) +define+QBS_STREAM_EQUIV" \
		SRAM_EXTRA_SOURCES="$(SRAM_EXTRA_SOURCES) $(CURDIR)/qbs_stream_contract_checker.sv" \
		SIM_ARGS="$(SIM_ARGS) +QBS_STROBE_STRIDE=257"

sram-check: sram-references
	mkdir -p $(BUILD)/sram
	cd $(BUILD)/sram && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L $(SRAM_DEFINES) -l compile.log \
		$(ROOT)/hardware/include/qbs_pkg.sv \
		$(ROOT)/hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv \
		$(ROOT)/hardware/src/vlsu/qbs/qbs_payload_sram.sv \
		$(ROOT)/hardware/src/vlsu/qbs/qbs_payload_buffer.sv \
		$(ROOT)/hardware/src/vlsu/qbs/qbs_block_adapter.sv \
		$(ROOT)/hardware/src/vlsu/qbs/qbs_profile_decoder.sv \
		$(BUILD)/qbs_block_adapter_reference.sv $(SRAM_EXTRA_SOURCES) \
		$(CURDIR)/qbs_sram_adapter_checker.sv $(CURDIR)/qbs_sram_adapter_tb.sv \
		-top qbs_sram_adapter_tb -o simv
	cd $(BUILD)/sram && timeout --foreground $(RUN_TIMEOUT) ./simv -l run.log $(SIM_ARGS)
	grep -q 'QBS SRAM adapter PASS' $(BUILD)/sram/run.log
	! grep -Eq 'Fatal:|Error:' $(BUILD)/sram/run.log

sram-engine-check: sram-references
	$(MAKE) -C $(ROOT)/verification/qbs rtl-engine-check \
		RTL_ENGINE_BUILD=$(BUILD)/engine RTL_RUN_TIMEOUT=$(RUN_TIMEOUT) \
		RTL_EXTRA_SOURCES="$(BUILD)/qbs_block_adapter_reference.sv $(CURDIR)/qbs_sram_adapter_checker.sv $(CURDIR)/qbs_sram_ingress_checker.sv $(SRAM_EXTRA_SOURCES)"
