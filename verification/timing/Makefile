ROOT := $(abspath ../..)
BUILD ?= $(CURDIR)/build
override BUILD := $(abspath $(BUILD))
REFERENCE ?= b07e194d
VCS ?= vcs
RUN_TIMEOUT ?= 300
SIM_ARGS ?=
ADAPTER_REFERENCE ?= 7b7c3de0
SRAM_REFERENCE ?= be1487b5
SRAM_DEFINES ?=
SRAM_EXTRA_SOURCES ?=

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
check: bounds-check qbs-check alu-check sram-check

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

qbs-check: references
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
sram-references:
	$(MAKE) adapter-references BUILD=$(BUILD) ADAPTER_REFERENCE=$(SRAM_REFERENCE)

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
		RTL_EXTRA_SOURCES="$(BUILD)/qbs_block_adapter_reference.sv $(CURDIR)/qbs_sram_adapter_checker.sv $(CURDIR)/qbs_sram_ingress_checker.sv"
