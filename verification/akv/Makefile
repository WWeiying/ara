ROOT := $(abspath ../..)
BENDER := $(ROOT)/hardware/bender
BUILD := rtl_engine_build
MACRO_BUILD := rtl_engine_macro_build
SYNTH_WRAPPER_BUILD := rtl_synth_wrapper_build
FILELIST := $(abspath $(BUILD)/bender.f)
MACRO_FILELIST := $(abspath $(MACRO_BUILD)/bender.f)
TB := $(abspath akv_engine_tb.sv)
MACRO_MODEL := $(abspath ../qbs/qbs_context_sram_macro_model.sv)
SYNTH_WRAPPER := $(abspath synthesis/akv_engine_synth_wrapper.sv)
SYNTH_SDC := $(abspath synthesis/akv_engine.sdc)
SYNTH_CHECKER := $(abspath $(ROOT)/hardware/scripts/akv/check-synthesis-preflight.py)
DC_SETUP := $(abspath $(ROOT)/backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env)
DC_FILELIST := $(abspath $(ROOT)/backend/flist/ara_soc_dc.f)

BENDER_TARGETS := --no-default-target -t rtl -t cv64a6_imafdcv_sv39 \
	-t tech_cells_generic_include_tc_sram \
	-t tech_cells_generic_include_tc_clk -t exclude_first_pass_decoder
BENDER_DEFINES := --define NR_LANES=4 --define VLEN=1024 \
	--define ARIANE_ACCELERATOR_PORT=1 --define ARA_QBS_ENABLE=1 \
	--define ARA_AKV_ENABLE=1 --define ARA_AKV_V2_ENABLE=1 \
	--define COMMON_CELLS_ASSERTS_OFF

.PHONY: check contract-check rtl-compile rtl-check rtl-macro-compile \
	rtl-macro-check synth-wrapper-compile synth-preflight context-synth \
	engine-synth clean

check: contract-check rtl-check rtl-macro-check

contract-check:
	./run_contract_test.sh

$(FILELIST): $(ROOT)/Bender.yml Makefile
	mkdir -p $(BUILD)
	cd $(ROOT) && $(BENDER) script verilator $(BENDER_TARGETS) \
		$(BENDER_DEFINES) > $(FILELIST)

$(MACRO_FILELIST): $(ROOT)/Bender.yml Makefile
	mkdir -p $(MACRO_BUILD)
	cd $(ROOT) && $(BENDER) script verilator $(BENDER_TARGETS) \
		$(BENDER_DEFINES) > $(MACRO_FILELIST)

rtl-compile: $(FILELIST) $(TB)
	cd $(BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+define+ARA_AKV_ENABLE=1 +define+ARA_AKV_V2_ENABLE=1 \
		+lint=TFIPC-L -l compile.log \
		-f $(FILELIST) $(TB) -top akv_engine_tb -o simv

rtl-check: rtl-compile
	cd $(BUILD) && ./simv -l run.log
	grep -q "AKV engine PASS" $(BUILD)/run.log

rtl-macro-compile: $(MACRO_FILELIST) $(TB) $(MACRO_MODEL)
	cd $(MACRO_BUILD) && vcs -full64 -sverilog -timescale=1ns/1ps \
		+define+ARA_AKV_ENABLE=1 +define+ARA_AKV_V2_ENABLE=1 \
		+define+TARGET_SRAM_MC +lint=TFIPC-L \
		-l compile.log -f $(MACRO_FILELIST) $(MACRO_MODEL) $(TB) \
		-top akv_engine_tb -o simv

rtl-macro-check: rtl-macro-compile
	cd $(MACRO_BUILD) && ./simv -l run.log
	grep -q "AKV engine PASS" $(MACRO_BUILD)/run.log

synth-wrapper-compile: $(MACRO_FILELIST) $(MACRO_MODEL) $(SYNTH_WRAPPER)
	mkdir -p $(SYNTH_WRAPPER_BUILD)
	cd $(SYNTH_WRAPPER_BUILD) && vcs -full64 -sverilog \
		+define+ARA_AKV_ENABLE=1 +define+ARA_AKV_V2_ENABLE=1 \
		+define+TARGET_SRAM_MC +lint=TFIPC-L -l compile.log \
		-f $(MACRO_FILELIST) $(MACRO_MODEL) $(SYNTH_WRAPPER) \
		-top akv_engine_synth_wrapper -o simv

synth-preflight: synth-wrapper-compile
	$(MAKE) -C $(ROOT)/hardware dc_preflight mc=1 qbs=1 akv_v2=1
	python3 $(SYNTH_CHECKER) --filelist $(DC_FILELIST) --sdc $(SYNTH_SDC) \
		--setup $(DC_SETUP) --require-qbs --require-akv --require-akv-v2 \
		--require-macro-sram --nr-lanes 4 --vlen 1024

context-synth:
	./synthesis/run_context_dc.sh

engine-synth:
	./synthesis/run_engine_dc.sh

clean:
	rm -rf $(BUILD) $(MACRO_BUILD) $(SYNTH_WRAPPER_BUILD)
