ROOT := $(abspath ../..)
CC ?= gcc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror -pedantic -ffp-contract=off \
	-frounding-math
CPPFLAGS += -I$(ROOT)/apps/common
LDLIBS += -lm

TARGETS := qbs_ref_test qbs_real_test qbs_rtl_vectors qbs_command_vectors
RTL_BUILD := rtl_build
RTL_COMMAND_BUILD := rtl_command_build
RTL_DESCRIPTOR_BUILD := rtl_descriptor_build
RTL_READ_BUILD := rtl_read_build
RTL_COMMIT_BUILD := rtl_commit_build
RTL_ENGINE_BUILD := rtl_engine_build
RTL_CONTEXT_BUILD := rtl_context_build
RTL_CONTEXT_MACRO_BUILD := rtl_context_macro_build
RTL_RUN_TIMEOUT ?= 10800
RTL_VECTOR_FILE := $(abspath qbs_rtl_vectors.txt)
RTL_COMMAND_VECTOR_FILE := $(abspath qbs_command_vectors.txt)
RTL_INCLUDES := +incdir+$(ROOT)/hardware/deps/common_cells/include \
	+incdir+$(ROOT)/hardware/deps/axi/include
RTL_SOURCES := \
	$(ROOT)/hardware/deps/common_cells/src/cf_math_pkg.sv \
	$(ROOT)/hardware/deps/axi/src/axi_pkg.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_pkg.sv \
	$(ROOT)/hardware/include/qbs_pkg.sv \
	$(ROOT)/hardware/deps/common_cells/src/lzc.sv \
	$(ROOT)/hardware/deps/common_cells/src/rr_arb_tree.sv \
	$(ROOT)/hardware/deps/fpnew/src/lfsr_sr.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_classifier.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_rounding.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_cast_multi.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_fma.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_opgroup_multifmt_slice.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_opgroup_block.sv \
	$(ROOT)/hardware/deps/fpnew/src/fpnew_top.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_profile_decoder.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_dot_array.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_read_engine.sv \
	$(ROOT)/hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_activation_context.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_block_adapter.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_profile_engine_int.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_fp_accumulator.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_compute_engine.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_commit.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_engine.sv
RTL_PROFILE_SOURCES := $(RTL_SOURCES) $(abspath qbs_profile_engine_tb.sv)
RTL_COMMAND_SOURCES := $(RTL_SOURCES) $(abspath qbs_compute_engine_tb.sv)
RTL_DESCRIPTOR_SOURCES := $(RTL_SOURCES) $(abspath qbs_descriptor_decoder_tb.sv)
RTL_READ_SOURCES := $(RTL_SOURCES) $(abspath qbs_read_engine_tb.sv)
RTL_COMMIT_SOURCES := $(RTL_SOURCES) $(abspath qbs_commit_tb.sv)
RTL_ENGINE_SOURCES := $(RTL_SOURCES) $(abspath qbs_engine_tb.sv)
RTL_CONTEXT_SOURCES := \
	$(ROOT)/hardware/include/qbs_pkg.sv \
	$(ROOT)/hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_activation_context.sv \
	$(abspath qbs_activation_context_tb.sv)
RTL_CONTEXT_MACRO_SOURCES := \
	$(ROOT)/hardware/include/qbs_pkg.sv \
	$(abspath qbs_context_sram_macro_model.sv) \
	$(ROOT)/hardware/src/vlsu/qbs/qbs_activation_context.sv \
	$(abspath qbs_activation_context_tb.sv)

.PHONY: all clean check generated-check real-check activation-context-evidence-check

all: $(TARGETS)

qbs_ref_test: qbs_ref_test.o qbs_ref.o
	$(CC) $(LDFLAGS) $^ $(LDLIBS) -o $@

qbs_real_test: qbs_real_test.o qbs_ref.o
	$(CC) $(LDFLAGS) $^ $(LDLIBS) -o $@

qbs_rtl_vectors: qbs_rtl_vectors.o qbs_ref.o
	$(CC) $(LDFLAGS) $^ $(LDLIBS) -o $@

qbs_command_vectors: qbs_command_vectors.o qbs_ref.o
	$(CC) $(LDFLAGS) $^ $(LDLIBS) -o $@

qbs_rtl_vectors.txt: qbs_rtl_vectors
	./qbs_rtl_vectors $@

qbs_command_vectors.txt: qbs_command_vectors
	./qbs_command_vectors $@

generated-check:
	python3 $(ROOT)/scripts/gen_qbs_abi.py --check
	python3 test_generate_qbs_case.py
	python3 test_summarize_qbs_perf.py
	python3 test_compare_adaptive_model_logs.py

check: generated-check qbs_ref_test
	./qbs_ref_test

real-check: all
	./run_real_cases.sh

ACTIVATION_CONTEXT_EVIDENCE ?= $(ROOT)/hardware/qbs_activation_context_evidence
activation-context-evidence-check:
	python3 check_activation_context_evidence.py \
		--direct $(ACTIVATION_CONTEXT_EVIDENCE)/direct/console.log \
		--context $(ACTIVATION_CONTEXT_EVIDENCE)/context/console.log

.PHONY: qemu-contract-check rtl-adaptive-real-check
qemu-contract-check:
	./qemu/run_qbs_contract_test.sh

rtl-adaptive-real-check: qbs_command_vectors rtl-engine-compile
	./run_adaptive_real_rtl.sh

.PHONY: rtl-compile rtl-profile-check rtl-command-compile rtl-command-check \
	rtl-descriptor-compile rtl-descriptor-check rtl-read-compile \
	rtl-read-check rtl-commit-compile rtl-commit-check rtl-engine-compile \
	rtl-engine-check rtl-context-compile rtl-context-check rtl-check
rtl-compile: qbs_rtl_vectors.txt $(RTL_PROFILE_SOURCES)
	mkdir -p $(RTL_BUILD)
	cd $(RTL_BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(RTL_INCLUDES) $(RTL_PROFILE_SOURCES) \
		-top qbs_profile_engine_tb -o simv

rtl-profile-check: rtl-compile
	cd $(RTL_BUILD) && timeout --foreground $(RTL_RUN_TIMEOUT) ./simv -l run.log \
		+QBS_VECTOR_FILE=$(RTL_VECTOR_FILE)
	grep -q "QBS profile engine PASS:" $(RTL_BUILD)/run.log
	! grep -Eq "Fatal:|Error:" $(RTL_BUILD)/run.log

rtl-command-compile: qbs_command_vectors.txt $(RTL_COMMAND_SOURCES)
	mkdir -p $(RTL_COMMAND_BUILD)
	cd $(RTL_COMMAND_BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(RTL_INCLUDES) $(RTL_COMMAND_SOURCES) \
		-top qbs_compute_engine_tb -o simv

rtl-command-check: rtl-command-compile
	cd $(RTL_COMMAND_BUILD) && timeout --foreground $(RTL_RUN_TIMEOUT) ./simv -l run.log \
		+QBS_COMMAND_VECTOR_FILE=$(RTL_COMMAND_VECTOR_FILE)
	grep -q "QBS command engine PASS:" $(RTL_COMMAND_BUILD)/run.log
	! grep -Eq "Fatal:|Error:" $(RTL_COMMAND_BUILD)/run.log

rtl-descriptor-compile: $(RTL_DESCRIPTOR_SOURCES)
	mkdir -p $(RTL_DESCRIPTOR_BUILD)
	cd $(RTL_DESCRIPTOR_BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(RTL_INCLUDES) $(RTL_DESCRIPTOR_SOURCES) \
		-top qbs_descriptor_decoder_tb -o simv

rtl-descriptor-check: rtl-descriptor-compile
	cd $(RTL_DESCRIPTOR_BUILD) && timeout --foreground $(RTL_RUN_TIMEOUT) ./simv -l run.log
	grep -q "QBS descriptor decoder PASS" $(RTL_DESCRIPTOR_BUILD)/run.log
	! grep -Eq "Fatal:|Error:" $(RTL_DESCRIPTOR_BUILD)/run.log

rtl-read-compile: $(RTL_READ_SOURCES)
	mkdir -p $(RTL_READ_BUILD)
	cd $(RTL_READ_BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(RTL_INCLUDES) $(RTL_READ_SOURCES) \
		-top qbs_read_engine_tb -o simv

rtl-read-check: rtl-read-compile
	cd $(RTL_READ_BUILD) && timeout --foreground $(RTL_RUN_TIMEOUT) ./simv -l run.log
	grep -q "QBS read engine PASS" $(RTL_READ_BUILD)/run.log
	! grep -Eq "Fatal:|Error:" $(RTL_READ_BUILD)/run.log

rtl-commit-compile: $(RTL_COMMIT_SOURCES)
	mkdir -p $(RTL_COMMIT_BUILD)
	cd $(RTL_COMMIT_BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(RTL_INCLUDES) $(RTL_COMMIT_SOURCES) \
		-top qbs_commit_tb -o simv

rtl-commit-check: rtl-commit-compile
	cd $(RTL_COMMIT_BUILD) && timeout --foreground $(RTL_RUN_TIMEOUT) ./simv -l run.log
	grep -q "QBS commit PASS" $(RTL_COMMIT_BUILD)/run.log
	! grep -Eq "Fatal:|Error:" $(RTL_COMMIT_BUILD)/run.log

rtl-engine-compile: qbs_command_vectors.txt $(RTL_ENGINE_SOURCES)
	mkdir -p $(RTL_ENGINE_BUILD)
	cd $(RTL_ENGINE_BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(RTL_INCLUDES) $(RTL_ENGINE_SOURCES) \
		-top qbs_engine_tb -o simv

rtl-engine-check: rtl-engine-compile
	cd $(RTL_ENGINE_BUILD) && timeout --foreground $(RTL_RUN_TIMEOUT) ./simv -l run.log \
		+QBS_COMMAND_VECTOR_FILE=$(RTL_COMMAND_VECTOR_FILE)
	grep -q "QBS engine PASS:" $(RTL_ENGINE_BUILD)/run.log
	! grep -Eq "Fatal:|Error:" $(RTL_ENGINE_BUILD)/run.log

rtl-context-compile: $(RTL_CONTEXT_SOURCES)
	mkdir -p $(RTL_CONTEXT_BUILD)
	cd $(RTL_CONTEXT_BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+lint=TFIPC-L -l compile.log $(RTL_CONTEXT_SOURCES) \
		-top qbs_activation_context_tb -o simv

rtl-context-check: rtl-context-compile
	cd $(RTL_CONTEXT_BUILD) && timeout --foreground $(RTL_RUN_TIMEOUT) ./simv -l run.log
	grep -q "QBS activation context PASS" $(RTL_CONTEXT_BUILD)/run.log
	! grep -Eq "Fatal:|Error:" $(RTL_CONTEXT_BUILD)/run.log

.PHONY: rtl-context-macro-compile rtl-context-macro-check
rtl-context-macro-compile: $(RTL_CONTEXT_MACRO_SOURCES)
	mkdir -p $(RTL_CONTEXT_MACRO_BUILD)
	cd $(RTL_CONTEXT_MACRO_BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+define+TARGET_SRAM_MC +lint=TFIPC-L -l compile.log \
		$(RTL_CONTEXT_MACRO_SOURCES) -top qbs_activation_context_tb -o simv

rtl-context-macro-check: rtl-context-macro-compile
	cd $(RTL_CONTEXT_MACRO_BUILD) && timeout --foreground $(RTL_RUN_TIMEOUT) ./simv -l run.log
	grep -q "QBS activation context PASS" $(RTL_CONTEXT_MACRO_BUILD)/run.log
	! grep -Eq "Fatal:|Error:" $(RTL_CONTEXT_MACRO_BUILD)/run.log

rtl-check: rtl-profile-check rtl-command-check rtl-descriptor-check \
	rtl-read-check rtl-commit-check rtl-context-check rtl-context-macro-check \
	rtl-engine-check

clean:
	rm -f $(TARGETS) *.o qbs_rtl_vectors.txt
	rm -f qbs_command_vectors.txt
	rm -rf $(RTL_BUILD) $(RTL_COMMAND_BUILD) $(RTL_DESCRIPTOR_BUILD) \
		$(RTL_READ_BUILD) $(RTL_COMMIT_BUILD) $(RTL_ENGINE_BUILD) \
		$(RTL_CONTEXT_BUILD) $(RTL_CONTEXT_MACRO_BUILD)
