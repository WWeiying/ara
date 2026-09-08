ROOT := $(abspath ../..)
BUILD ?= $(CURDIR)/build
override BUILD := $(abspath $(BUILD))
REFERENCE ?= b07e194d
VCS ?= vcs
RUN_TIMEOUT ?= 300
SIM_ARGS ?=

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

.PHONY: check qbs-check alu-check bounds-check references
check: bounds-check qbs-check alu-check

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
