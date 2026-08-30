ROOT := $(abspath ../..)
BENDER := $(ROOT)/hardware/bender
BUILD := rtl_engine_build
FILELIST := $(abspath $(BUILD)/bender.f)
TB := $(abspath akv_engine_tb.sv)

BENDER_TARGETS := --no-default-target -t rtl -t cv64a6_imafdcv_sv39 \
	-t tech_cells_generic_include_tc_sram \
	-t tech_cells_generic_include_tc_clk -t exclude_first_pass_decoder
BENDER_DEFINES := --define NR_LANES=4 --define VLEN=1024 \
	--define ARIANE_ACCELERATOR_PORT=1 --define ARA_QBS_ENABLE=1 \
	--define ARA_AKV_ENABLE=1 --define COMMON_CELLS_ASSERTS_OFF

.PHONY: check contract-check rtl-compile rtl-check clean

check: contract-check rtl-check

contract-check:
	./run_contract_test.sh

$(FILELIST): $(ROOT)/Bender.yml Makefile
	mkdir -p $(BUILD)
	cd $(ROOT) && $(BENDER) script verilator $(BENDER_TARGETS) \
		$(BENDER_DEFINES) > $(FILELIST)

rtl-compile: $(FILELIST) $(TB)
	cd $(BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+define+ARA_AKV_ENABLE=1 +lint=TFIPC-L -l compile.log \
		-f $(FILELIST) $(TB) -top akv_engine_tb -o simv

rtl-check: rtl-compile
	cd $(BUILD) && ./simv -l run.log
	grep -q "AKV engine PASS" $(BUILD)/run.log

clean:
	rm -rf $(BUILD)
