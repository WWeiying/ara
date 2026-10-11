SHELL = /usr/bin/env bash
ROOT_DIR := $(patsubst %/,%, $(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ARA_DIR := $(shell git rev-parse --show-toplevel 2>/dev/null || echo $$ARA_DIR)
INSTALL_DIR := $(abspath $(ROOT_DIR)/../install)
VERILATOR_INCLUDE := $(INSTALL_DIR)/verilator/share/verilator/include/vltstd
# VCS supplies svdpi.h as well; a VCS-only checkout need not install Verilator.
DPI_INCLUDE ?= $(if $(VCS_HOME),$(VCS_HOME)/include,$(VERILATOR_INCLUDE))

BENDER         ?= $(ROOT_DIR)/bender
BENDER_VERSION := 0.28.2

# Choose Ara's configuration
ifndef config
        ifdef ARA_CONFIGURATION
                config := $(ARA_CONFIGURATION)
        else
                config := default
        endif
endif

# Include configuration
include $(ARA_DIR)/config/$(config).mk
include $(ARA_DIR)/config/sram.mk

# build path
buildpath      ?= $(ARA_DIR)/hardware/build
resultpath     ?= results
# questa library
library        ?= work
# dpi library
dpi_library    ?= work-dpi
# verilator library
vcs_library  ?= $(buildpath)/vcs
# Path to the binaries
app_path       ?= $(abspath $(ROOT_DIR)/../apps/bin)
# Path to ideal dispatcher vtraces
vtrace_path    ?= $(abspath $(ROOT_DIR)/../apps/ideal_dispatcher/vtrace)
# DPI source files
dpi   := $(patsubst tb/dpi/%.cc,$(buildpath)/$(dpi_library)/%.o,$(wildcard tb/dpi/*.cc))

#techlib path
sram_techlib_path := /home/wangwy/ara/backend/library/mem
spsram127_techlib_path := /home/wangwy/technical_library/tsmc28nm/Memory/tsn28hpcpd127spsram_20120200_180a/AN61001_20180416/tsn28hpcpd127spsram_20120200_180a/TSMCHOME/sram/Compiler/tsn28hpcpd127spsram_20120200_180a/tsn28hpcpd127spsram_20120200_180a
spsram_techlib_path := /home/wangwy/technical_library/tsmc28nm/Memory/tsn28hpcpuhdspsram_20120200_170a/AN61001_20180125/tsn28hpcpuhdspsram_20120200_170a/TSMCHOME/sram/Compiler/tsn28hpcpuhdspsram_20120200_170a/tsn28hpcpuhdspsram_20120200_170a

mc ?= 0

define generate_sram
  > $(1)/config.txt

  for config in $(2); do \
    depth=$$(echo "$$config" | cut -d'x' -f1); \
    width=$$(echo "$$config" | cut -d'x' -f2); \
    mux_type=$$(echo "$$config" | cut -d'x' -f3); \
    echo "$${depth}x$${width}m$${mux_type}s" >> $(1)/config.txt; \
  done

  cd $(1) && ./run.sh

  >convert_script.tcl

  for dir in $(1)/*/; do \
    if [ -d "$$dir" ]; then \
      ./scripts/generate_db.sh $$dir/NLDM $$dir/DB; \
    fi; \
  done

  echo "exit" >> convert_script.tcl
  lc_shell -f convert_script.tcl
  rm convert_script.tcl

endef

ifeq ($(mc), 1)
  define generate_sram_filelist
    for dir in $(1)/*; do \
      if [ -d "$$dir" ]; then \
        find "$$dir/VERILOG" -name "*tt0p9v25c.v" -print >> $(2); \
      fi; \
    done
  endef
else
  define generate_sram_filelist
    echo "" >> $(2)
  endef
endif

# Bender Defines
ideal          ?=
ifeq ($(ideal_dispatcher), 1)
  vtrace       = $(vtrace_path)/$(app).vtrace
  bender_defs += --define IDEAL_DISPATCHER=1 --define VTRACE="$(vtrace)" --define N_VINSN=$(shell wc -l $(vtrace) | cut -d " " -f 1)
  ideal        = "_ideal"
endif

bender_defs += --define NR_LANES=$(nr_lanes) --define VLEN=$(vlen) --define ARIANE_ACCELERATOR_PORT=1

# Reduction-acceleration ablation switches.  Keep the baseline behavior unless
# explicitly enabled so each mechanism can be measured independently.  The
# context stream switch covers both VMFPU and VALU reduction pipelines.
# Independently controlled completion-throughput experiments.
reduction_rce_seed_lookahead ?= 0
ifeq ($(reduction_rce_seed_lookahead),1)
  bender_defs += --define ARA_RED_RCE_SEED_LOOKAHEAD=1
endif
reduction_rce_queue_lookahead ?= 0
reduction_rce_word_turnaround ?= 0
reduction_rce_ordinary_seed_same_vfu ?= 0
ifeq ($(reduction_rce_ordinary_seed_same_vfu),1)
  ifneq ($(reduction_rce_ordinary_seed),1)
    $(error reduction_rce_ordinary_seed_same_vfu requires reduction_rce_ordinary_seed=1)
  endif
  bender_defs += --define ARA_RED_RCE_ORDINARY_SEED_SAME_VFU=1
endif
reduction_rce_ordinary_seed ?= 0
ifeq ($(reduction_rce_ordinary_seed),1)
  bender_defs += --define ARA_RED_RCE_ORDINARY_SEED=1
endif
reduction_rce_fp_late_seed ?= 0
ifeq ($(reduction_rce_fp_late_seed),1)
  bender_defs += --define ARA_RED_RCE_FP_LATE_SEED=1
endif
reduction_rce_exact_external_seed ?= 0
ifeq ($(reduction_rce_exact_external_seed),1)
  bender_defs += --define ARA_RED_RCE_EXACT_EXTERNAL_SEED=1
endif
reduction_rce_exact_seed_receive ?= 0
ifeq ($(reduction_rce_exact_seed_receive),1)
  bender_defs += --define ARA_RED_RCE_EXACT_SEED_RECEIVE=1
endif
reduction_rce_exact_decouple ?= 0
ifeq ($(reduction_rce_exact_decouple),1)
  bender_defs += --define ARA_RED_RCE_EXACT_DECOUPLE=1
endif
reduction_rce_sldu_buffer ?= 0
ifeq ($(reduction_rce_sldu_buffer),1)
  bender_defs += --define ARA_RED_RCE_SLDU_BUFFER=1
endif
reduction_rce_split_credit ?= 0
ifeq ($(reduction_rce_split_credit),1)
  bender_defs += --define ARA_RED_RCE_SPLIT_CREDIT=1
endif
reduction_rce_word_sparse ?= 0
ifeq ($(reduction_rce_word_sparse),1)
  bender_defs += --define ARA_RED_RCE_WORD_SPARSE=1
endif
reduction_rce_external_seed ?= 0
ifeq ($(reduction_rce_external_seed),1)
  bender_defs += --define ARA_RED_RCE_EXTERNAL_SEED=1
endif
reduction_rce_seed_group ?= 0
ifeq ($(reduction_rce_seed_group),1)
  bender_defs += --define ARA_RED_RCE_SEED_GROUP=1
endif
reduction_rce_fp64_sparse ?= 0
ifeq ($(reduction_rce_fp64_sparse),1)
  bender_defs += --define ARA_RED_RCE_FP64_SPARSE=1
endif
reduction_rce_fp64_seed_feedback ?= 0
ifeq ($(reduction_rce_fp64_seed_feedback),1)
  bender_defs += --define ARA_RED_RCE_FP64_SEED_FEEDBACK=1
endif
reduction_rce_fp64_feedback ?= 0
ifeq ($(reduction_rce_fp64_feedback),1)
  bender_defs += --define ARA_RED_RCE_FP64_FEEDBACK=1
endif
reduction_rce_mfpu_restart ?= 0
ifeq ($(reduction_rce_mfpu_restart),1)
  bender_defs += --define ARA_RED_RCE_MFPU_RESTART=1
endif
reduction_rce_empty_bypass ?= 0
ifeq ($(reduction_rce_empty_bypass),1)
  bender_defs += --define ARA_RED_RCE_EMPTY_BYPASS=1
endif
reduction_rce_exact_egress_release ?= 0
reduction_rce_result_depth ?= 2
ifeq ($(reduction_rce_queue_lookahead),1)
  bender_defs += --define ARA_RED_RCE_QUEUE_LOOKAHEAD=1
endif
ifeq ($(reduction_rce_word_turnaround),1)
  bender_defs += --define ARA_RED_RCE_WORD_TURNAROUND=1
endif
ifeq ($(reduction_rce_exact_egress_release),1)
  bender_defs += --define ARA_RED_RCE_EXACT_EGRESS_RELEASE=1
endif
ifneq ($(filter $(reduction_rce_result_depth),2 4),$(reduction_rce_result_depth))
  $(error reduction_rce_result_depth must be 2 or 4)
endif
bender_defs += --define ARA_RED_RCE_RESULT_DEPTH=$(reduction_rce_result_depth)
reduction_rce_alu_result_depth ?= $(reduction_rce_result_depth)
reduction_rce_fp_result_depth ?= $(reduction_rce_result_depth)
ifneq ($(filter $(reduction_rce_alu_result_depth),2 4),$(reduction_rce_alu_result_depth))
  $(error reduction_rce_alu_result_depth must be 2 or 4)
endif
ifneq ($(filter $(reduction_rce_fp_result_depth),2 4),$(reduction_rce_fp_result_depth))
  $(error reduction_rce_fp_result_depth must be 2 or 4)
endif
bender_defs += --define ARA_RED_RCE_ALU_RESULT_DEPTH=$(reduction_rce_alu_result_depth)
bender_defs += --define ARA_RED_RCE_FP_RESULT_DEPTH=$(reduction_rce_fp_result_depth)


reduction_rce_int ?= 0
reduction_rce_int_late_seed ?= 0
reduction_rce_compact_word ?= 0
reduction_rce_operand_isolation ?= 0
reduction_rce_mixed ?= 0
reduction_rce_fp_minmax ?= 0
reduction_rce_fp64_sum ?= 0
reduction_rce_exact ?= 0
reduction_rce_exact_direct ?= 0
reduction_exact_no_round_bubble ?= 0
ifeq ($(reduction_exact_no_round_bubble),1)
  bender_defs += --define ARA_RED_EXACT_NO_ROUND_BUBBLE=1
endif
ifeq ($(reduction_rce_int),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_rce_int currently requires nr_lanes=4)
  endif
  bender_defs += --define ARA_RED_RCE_INT=1
endif
ifeq ($(reduction_rce_compact_word),1)
  bender_defs += --define ARA_RED_RCE_COMPACT_WORD=1
endif
ifeq ($(reduction_rce_operand_isolation),1)
  bender_defs += --define ARA_RED_RCE_OPERAND_ISOLATION=1
endif
ifeq ($(reduction_rce_fp_minmax),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_rce_fp_minmax currently requires nr_lanes=4)
  endif
  bender_defs += --define ARA_RED_RCE_FP_MINMAX=1
endif
ifeq ($(reduction_rce_fp64_sum),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_rce_fp64_sum currently requires nr_lanes=4)
  endif
  bender_defs += --define ARA_RED_RCE_FP64_SUM=1
endif
ifeq ($(reduction_rce_mixed),1)
  ifeq ($(filter 1,$(reduction_rce_int) $(reduction_rce_fp_minmax) $(reduction_rce_exact) $(reduction_rce_fp64_sum)),)
    $(error reduction_rce_mixed requires an enabled RCE backend)
  endif
  bender_defs += --define ARA_RED_RCE_MIXED=1
endif
reduction_output_bypass ?= 0
reduction_route_bypass  ?= 0
reduction_mask_fastpath ?= 0
reduction_mask_skip     ?= 0
reduction_dense_input_bypass ?= 0
reduction_tree_input_bypass  ?= 0
reduction_terminal_fusion    ?= 0
reduction_context_flow       ?= 0
reduction_context_stream     ?= 0
reduction_slack_schedule     ?= 0
reduction_heterogeneous_stream ?= 0
reduction_masked_stream       ?= 0
reduction_tree_stage_pipeline ?= 0
reduction_ordered_interleave  ?= 0
reduction_source_fusion       ?= 0
reduction_ordered_fast        ?= 0
reduction_exact_sum           ?= 0
reduction_exact_segmented     ?= 0
reduction_exact_global        ?= 0
reduction_exact_fixed_window  ?= 0
reduction_exact_fp16          ?= 0
reduction_exact_stream        ?= 0
reduction_chain_bypass        ?= 0
reduction_complete_4lane      ?= 0
reduction_complete_4lane_chain_bypass ?= 1

# Reproducible final 4-lane candidate.  Individual switches remain available
# for ablation builds, while this profile prevents a paper/kernel run from
# silently omitting an already-validated mechanism.  The fixed-window exact
# protocol is intentionally excluded because it is the dense ablation control;
# the final candidate uses the sparse active-window protocol.
ifeq ($(reduction_complete_4lane),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_complete_4lane requires nr_lanes=4)
  endif
  override reduction_output_bypass       := 1
  override reduction_route_bypass        := 1
  override reduction_mask_fastpath       := 1
  override reduction_mask_skip           := 1
  override reduction_dense_input_bypass  := 1
  override reduction_tree_input_bypass   := 1
  override reduction_terminal_fusion     := 1
  override reduction_context_flow        := 1
  override reduction_context_stream      := 1
  override reduction_slack_schedule      := 1
  override reduction_heterogeneous_stream := 1
  override reduction_masked_stream       := 1
  override reduction_tree_stage_pipeline := 1
  override reduction_ordered_interleave  := 1
  override reduction_source_fusion       := 1
  override reduction_ordered_fast        := 1
  override reduction_exact_sum           := 1
  override reduction_exact_segmented     := 1
  override reduction_exact_global        := 1
  override reduction_exact_fp16          := 1
  override reduction_exact_stream        := 1
  # Set only the following knob to 0 for a same-profile chain-bypass
  # ablation; every other final mechanism remains enabled.
  override reduction_chain_bypass        := $(reduction_complete_4lane_chain_bypass)
endif

# Masked-off token relay uses the direct VMFPU output protocol and the
# mask-decoupled return credit.  Make those prerequisites explicit so a skip
# experiment cannot accidentally be built with an incompatible handshake.
ifeq ($(reduction_mask_skip),1)
  reduction_output_bypass := 1
  reduction_mask_fastpath := 1
endif

ifeq ($(reduction_output_bypass),1)
  bender_defs += --define ARA_RED_OUTPUT_BYPASS=1
endif
ifeq ($(reduction_route_bypass),1)
  bender_defs += --define ARA_RED_ROUTE_BYPASS=1
endif
ifeq ($(reduction_mask_fastpath),1)
  bender_defs += --define ARA_RED_MASK_FASTPATH=1
endif
ifeq ($(reduction_mask_skip),1)
  bender_defs += --define ARA_RED_MASK_SKIP=1
endif
ifeq ($(reduction_dense_input_bypass),1)
  bender_defs += --define ARA_RED_DENSE_INPUT_BYPASS=1
endif
ifeq ($(reduction_tree_input_bypass),1)
  bender_defs += --define ARA_RED_TREE_INPUT_BYPASS=1
endif
ifeq ($(reduction_terminal_fusion),1)
  bender_defs += --define ARA_RED_VMFPU_TERMINAL_FUSION=1
endif
ifeq ($(reduction_context_flow),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_context_flow currently requires nr_lanes=4)
  endif
  bender_defs += --define ARA_RED_CONTEXT_FLOW_4LANE=1
endif
ifeq ($(reduction_context_stream),1)
  ifneq ($(reduction_context_flow),1)
    $(error reduction_context_stream requires reduction_context_flow=1)
  endif
  ifneq ($(nr_lanes),4)
    $(error reduction_context_stream currently requires nr_lanes=4)
  endif
  bender_defs += --define ARA_RED_CONTEXT_STREAM_4LANE=1
endif
ifeq ($(reduction_slack_schedule),1)
  ifneq ($(reduction_context_stream),1)
    $(error reduction_slack_schedule requires reduction_context_stream=1)
  endif
  bender_defs += --define ARA_RED_SLACK_SCHED_4LANE=1
endif
ifeq ($(reduction_heterogeneous_stream),1)
  ifneq ($(reduction_context_stream),1)
    $(error reduction_heterogeneous_stream requires reduction_context_stream=1)
  endif
  bender_defs += --define ARA_RED_HETERO_STREAM_4LANE=1
endif
ifeq ($(reduction_masked_stream),1)
  ifneq ($(reduction_context_stream),1)
    $(error reduction_masked_stream requires reduction_context_stream=1)
  endif
  bender_defs += --define ARA_RED_MASKED_STREAM_4LANE=1
endif
ifeq ($(reduction_tree_stage_pipeline),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_tree_stage_pipeline currently requires nr_lanes=4)
  endif
  bender_defs += --define ARA_RED_TREE_STAGE_PIPE_4LANE=1
endif
ifeq ($(reduction_ordered_interleave),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_ordered_interleave currently requires nr_lanes=4)
  endif
  bender_defs += --define ARA_RED_ORDERED_INTERLEAVE_4LANE=1
endif
ifeq ($(reduction_source_fusion),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_source_fusion currently requires nr_lanes=4)
  endif
  ifneq ($(reduction_ordered_interleave),1)
    $(error reduction_source_fusion requires reduction_ordered_interleave=1)
  endif
  bender_defs += --define ARA_RED_SOURCE_FUSION_4LANE=1
endif
ifeq ($(reduction_ordered_fast),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_ordered_fast currently requires nr_lanes=4)
  endif
  ifneq ($(reduction_output_bypass),1)
    $(error reduction_ordered_fast requires reduction_output_bypass=1)
  endif
  bender_defs += --define ARA_RED_ORDERED_FAST_4LANE=1
endif
ifeq ($(reduction_exact_sum),1)
  ifneq ($(nr_lanes),4)
    $(error reduction_exact_sum currently requires nr_lanes=4)
  endif
  ifeq ($(shell test $(vlen) -le 8192 && echo yes),)
    $(error reduction_exact_sum requires VLEN<=8192 for the 288-bit lane accumulator)
  endif
  bender_defs += --define ARA_RED_EXACT_SUM_4LANE=1
endif
ifeq ($(reduction_exact_segmented),1)
  ifneq ($(reduction_exact_sum),1)
    $(error reduction_exact_segmented requires reduction_exact_sum=1)
  endif
  ifeq ($(shell test $(vlen) -le 4096 && echo yes),)
    $(error reduction_exact_segmented requires VLEN<=4096 for 49-bit exponent bins)
  endif
  bender_defs += --define ARA_RED_EXACT_SEGMENTED_4LANE=1
endif
ifeq ($(reduction_exact_global),1)
  ifneq ($(reduction_exact_sum),1)
    $(error reduction_exact_global requires reduction_exact_sum=1)
  endif
  ifneq ($(reduction_exact_segmented),1)
    $(error reduction_exact_global requires reduction_exact_segmented=1)
  endif
  ifneq ($(nr_lanes),4)
    $(error reduction_exact_global currently requires nr_lanes=4)
  endif
  # At LMUL=8, VLEN/4 binary32 elements plus the scalar seed can contribute.
  # A 288-bit signed 2^-149 accumulator holds at most 1024 maximum finite
  # binary32 values. VLEN=4096 would require 1025 (including the seed).
  ifeq ($(shell test $(vlen) -le 2048 && echo yes),)
    $(error reduction_exact_global requires VLEN<=2048 for the 288-bit global sum)
  endif
  bender_defs += --define ARA_RED_EXACT_GLOBAL_4LANE=1
endif
ifeq ($(reduction_rce_exact_direct),1)
  ifneq ($(reduction_rce_exact),1)
    $(error reduction_rce_exact_direct requires reduction_rce_exact=1)
  endif
  bender_defs += --define ARA_RED_RCE_EXACT_DIRECT=1
endif
ifeq ($(reduction_rce_exact),1)
  ifneq ($(reduction_exact_global),1)
    $(error reduction_rce_exact requires reduction_exact_global=1)
  endif
  bender_defs += --define ARA_RED_RCE_EXACT=1
endif
ifeq ($(reduction_exact_fixed_window),1)
  ifneq ($(reduction_exact_global),1)
    $(error reduction_exact_fixed_window requires reduction_exact_global=1)
  endif
  bender_defs += --define ARA_RED_EXACT_FIXED_WINDOW_4LANE=1
endif
ifeq ($(reduction_exact_fp16),1)
  ifneq ($(reduction_exact_global),1)
    $(error reduction_exact_fp16 requires reduction_exact_global=1)
  endif
  bender_defs += --define ARA_RED_EXACT_FP16_4LANE=1
endif
ifeq ($(reduction_exact_stream),1)
  ifneq ($(reduction_exact_global),1)
    $(error reduction_exact_stream requires reduction_exact_global=1)
  endif
  bender_defs += --define ARA_RED_EXACT_STREAM_4LANE=1
endif
ifeq ($(reduction_chain_bypass),1)
  ifneq ($(reduction_exact_global),1)
    $(error reduction_chain_bypass requires reduction_exact_global=1)
  endif
  ifneq ($(nr_lanes),4)
    $(error reduction_chain_bypass currently requires nr_lanes=4)
  endif
  bender_defs += --define ARA_RED_CHAIN_BYPASS_4LANE=1
endif
ifeq ($(reduction_rce_int_late_seed),1)
  ifneq ($(reduction_rce_int),1)
    $(error reduction_rce_int_late_seed requires reduction_rce_int=1)
  endif
  bender_defs += --define ARA_RED_RCE_INT_LATE_SEED=1
endif
ifneq ($(filter 1,$(reduction_chain_bypass) $(reduction_rce_int_late_seed) $(reduction_rce_fp_late_seed) $(reduction_rce_ordinary_seed)),)
  bender_defs += --define ARA_RED_REGISTER_VERSIONS=1
endif
ifneq ($(filter 1,$(reduction_dense_input_bypass) $(reduction_tree_input_bypass)),)
  bender_defs += --define ARA_RED_INPUT_BYPASS=1
endif

# Legacy report code names lane 2/3 hierarchically.  The parameterized
# execution monitor remains the authoritative all-lane, ROI-scoped report.
ifneq ($(nr_lanes),2)
  bender_defs += --define ARA_HAS_LANE_2_3=1
endif

bender_defs_veril = $(bender_defs) --define COMMON_CELLS_ASSERTS_OFF
# Targets
bender_common_targs := -t rtl -t cv64a6_imafdcv_sv39 -t tech_cells_generic_include_tc_sram -t tech_cells_generic_include_tc_clk -t exclude_first_pass_decoder
bender_targs_veril    := $(bender_common_targs) -t ara_test -t cva6_test
bender_targs_spyglass := $(bender_common_targs) -t spyglass

ifeq ($(mc), 1)
  bender_targs_vcs      := $(bender_common_targs) -t ara_test -t cva6_test -t notsynthesis -t sram_mc
  bender_targs_dc       := $(bender_common_targs) -t sram_blackbox -t sram_mc
else
bender_targs_vcs      := $(bender_common_targs) -t ara_test -t cva6_test -t notsynthesis
bender_targs_dc       := $(bender_common_targs) -t sram_blackbox
endif

ifeq ($(mc), 1)
  sim_dir ?= sim_mc
else
  sim_dir ?= sim
endif

ifdef app
  ifeq ($(ideal_dispatcher), 1)
  	preload ?= "$(app_path)/$(app).ideal"
  else
  	preload ?= "$(app_path)/$(app)"
  endif
endif

TIMESCALE := -timescale=1ns/100fs
SIMULATOR_OPT := -full64 -sverilog +v2k -Mlib=./incremental_db -Mupdate -j64 -lca -kdb -debug_access+all +nospecify +notimingchecks +lint=TFIPC-L  +vpi +lint=PCWM +error+30
SIMULATOR_DEF := +define+SIMULATION +define+no_warning +define+TSMC_NO_WARNING
ifeq ($(fail_on_assert), 1)
SIMULATOR_DEF += +define+ARA_FAIL_FAST_ASSERTS
endif
SIMULATOR_LOG := -l comp.vcs.log
SIMULATOR_POWER_OPT := 
SIMV_POWER_OPT      := +fsdb+power +fsdb+all 
SIM_DUMP := 
SIM_FILELIST := -f $(vcs_library)/bender_script_$(config) $(dpi)
SIM_TIME := #+vcs+finish+10000ns
APP := +PRELOAD=$(preload) +TESTCASE=$(app)
ifeq ($(no_fsdb), 1)
APP += +NO_FSDB
endif

.PHONY: bender compile sim verify clean verdi lint trace dc dpi sram saif sim_all saif_all saif_ara analyze_perf analyze_perf_suite compare_perf

# Bender
bender: $(BENDER)
$(BENDER):
	@[ -x $(BENDER) ] && echo "Bender already exists." || \
	curl --proto '=https' --tlsv1.2 https://pulp-platform.github.io/bender/init -sSf | sh	-s -- $(BENDER_VERSION)
	@echo "$$(./bender --version) available."

# DPIs
dpi: $(buildpath)/$(dpi_library)/ara_dpi.so

$(buildpath)/$(dpi_library)/%.o: tb/dpi/%.cc
	@mkdir -p $(buildpath)/$(dpi_library)
	@$(CXX) -shared -fPIC -std=c++11 -Bsymbolic -c $< -I$(DPI_INCLUDE) -I$(INSTALL_DIR)/riscv-isa-sim/include -o $@

$(buildpath)/$(dpi_library)/ara_dpi.so: $(dpi)
	@mkdir -p $(buildpath)/$(dpi_library)
	@$(CXX) -shared -m64 -o $(buildpath)/$(dpi_library)/ara_dpi.so $?

compile: bender dpi ../Bender.yml
	@mkdir -p $(vcs_library)
	@echo "ARA Configuration: NR_LANES=$(nr_lanes) VLEN=$(vlen)"
	@$(BENDER) script verilator $(bender_targs_vcs) $(bender_defs_veril) --define FOR_VERIFY  > $(vcs_library)/bender_script_$(config)
	@$(call generate_sram_filelist, $(sram_techlib_path), $(vcs_library)/bender_script_$(config))
	@python3 scripts/prepare_reduction_dependency_overlay.py $(vcs_library)/bender_script_$(config)
	@mkdir -p ./$(sim_dir)/incremental_db
	@cd ./$(sim_dir) && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(SIMULATOR_DEF) $(SIM_FILELIST) $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT)

ifeq ($(ideal_dispatcher), 1)
sim_log = "perf_report_$(app)_ideal.log"
else
sim_log = "perf_report_$(app).log"
endif

sim: compile
	@touch ./$(sim_dir)/perf*.log
	@rm ./$(sim_dir)/perf*.log
	@cd ./$(sim_dir) && ./simv -l run.vcs.log $(SIMV_POWER_OPT) $(APP)
	@cp ./$(sim_dir)/$(sim_log) ./$(sim_dir)/perf.log
verify: 
	@cd ../apps && $(MAKE) $(app) && $(MAKE) bin/$(app).ideal
	@$(MAKE) sim app=$(app) verify=1 ideal_dispatcher=1
#	@./regdump_compare.py sim/regdump.ideal sim/regdump.real --trace --trace-reg --dest-only --log-file sim/regdump_compare.log

analyze_perf:
	@$(if $(strip $(log)),,$(error Usage: make analyze_perf log=<path_to_perf_log> [md=1] [json_out=<path>] [require_ready=1]))
	@python3 scripts/analyze_perf_bottleneck.py $(log) \
		$(if $(strip $(top_n)),--top-n $(top_n),) \
		$(if $(strip $(json_out)),--json-out $(json_out),) \
		$(if $(strip $(require_ready)),--require-ready,) \
		$(if $(strip $(md)),--md,)

analyze_perf_suite:
	@$(if $(strip $(logs)),,$(error Usage: make analyze_perf_suite logs="<perf1.log> <perf2.log> ..." [require_complete=1] [json_out=<path>]))
	@python3 scripts/analyze_perf_suite.py $(logs) \
		$(if $(strip $(json_out)),--json-out $(json_out),) \
		$(if $(strip $(require_complete)),--require-complete,)

compare_perf:
	@$(if $(strip $(baseline)),,$(error Usage: make compare_perf baseline=<before.log> candidate=<after.log> [require_ready=1] [require_equivalent=1] [fail_regression_pct=1.0]))
	@$(if $(strip $(candidate)),,$(error candidate=<after.log> is required))
	@python3 scripts/compare_perf_reports.py $(baseline) $(candidate) \
		$(if $(strip $(top_n)),--top-n $(top_n),) \
		$(if $(strip $(json_out)),--json-out $(json_out),) \
		$(if $(strip $(require_ready)),--require-ready,) \
		$(if $(strip $(require_equivalent)),--require-equivalent,) \
		$(if $(strip $(fail_regression_pct)),--fail-regression-pct $(fail_regression_pct),)

clean:
	@cd ./$(sim_dir) && rm -rf *
	@rm -rf $(buildpath)

verdi:
	@cd ./$(sim_dir) && verdi $(SIMULATOR_DEF) -sv $(SIM_FILELIST) -top ara_tb -dbdir simv.daidir -ssf ara_tb.fsdb -sswr ../debug/signal_ideal.rc -l verdi.log &

lint:
	cd ./hardware/lint && rm -rf brook_* *.log reports spyglass-1 brook
	cd ./hardware/lint && ./run.sh

trace:
	@./run/scripts/compare_traces.py -g ./run/log/ref_trace.log -d ./run/log/dut_trace.log -o ./run/log/diff_report
	@head -n 20 ./run/log/diff_report

dc:
	@echo "1.Generating dc flist"
	@$(BENDER) script verilator $(bender_targs_dc) $(bender_defs_veril) > ../backend/flist/ara_soc.f
	@cd ../backend/flist && cat ara_soc.f | \
	grep -v "incdir" | \
	grep -v "+define"| \
	grep -v "ara_tb_verilator.sv"| \
	grep -v "_pkg.sv" > rtl.temp
	@cd ../backend/flist && cat ara_soc.f | grep "incdir"      >  incdir.temp 
	@cd ../backend/flist && echo "+define+SYNTHESIS"           >  defines.temp 
	@cd ../backend/flist && echo "+define+HPDCACHE_ASSERT_OFF" >> defines.temp 
	@cd ../backend/flist && cat ara_soc.f | grep "+define"     >> defines.temp 
	@cd ../backend/flist && cat ara_soc.f | grep "_pkg.sv"     >  packages.temp 
	@cd ../backend/flist && cat incdir.temp   >  ara_soc_dc.f
	@cd ../backend/flist && cat defines.temp  >> ara_soc_dc.f
	@cd ../backend/flist && cat packages.temp >> ara_soc_dc.f
	@cd ../backend/flist && cat rtl.temp      >> ara_soc_dc.f
	@echo "2.Synthesis"
	@cd ../backend/syn/ara_soc/v1-dc/run/ && ./run.cmd

sram:
	@$(call generate_sram, $(spsram127_techlib_path), $(L2_SRAM_CONFIGS))
	@$(call generate_sram, $(spsram_techlib_path), $(VECTOR_REGFILE_SRAM_CONFIGS))
	@$(call generate_sram, $(spsram_techlib_path), $(ICACHE_TAG_SRAM_CONFIGS))
	@$(call generate_sram, $(spsram_techlib_path), $(ICACHE_DATA_SRAM_CONFIGS))
	@$(call generate_sram, $(spsram_techlib_path), $(DCACHE_DATA_SRAM_CONFIGS))

start_time?=
stop_time?=

saif:
	@mkdir -p ./vcd ./saif ./build/saif
	@echo "1.Generating saif flist"
	@$(BENDER) script verilator $(bender_targs_vcs) $(bender_defs_veril) --define SAIF > ./build/saif/ara_tb.f
	@cd ./build/saif && cat ara_tb.f | grep "incdir"       >  incdir.temp 
	@cd ./build/saif && cat ara_tb.f | grep "_pkg.sv"      >  packages.temp 
	@cd ./build/saif && echo "+define+SYNTHESIS"           >  defines.temp 
	@cd ./build/saif && echo "+define+HPDCACHE_ASSERT_OFF" >> defines.temp 
	@cd ./build/saif && cat ara_tb.f | grep "+define"      >> defines.temp 
	@cd ./build/saif && cat ara_tb.f | grep "ara_tb.sv"          >  rtl.temp 
	@cd ./build/saif && cat ara_tb.f | grep "ara_testharness.sv" >> rtl.temp 
	@cd ./build/saif && echo "/home/wangwy/openproject/ara/backend/syn/ara_soc/v1-dc/outputs/ara_soc_dc.v" >> rtl.temp 
	@cd ./build/saif && cat ara_tb.f | grep "mock_uart.sv"       >> rtl.temp 
	@cd ./build/saif && cat incdir.temp   >  ara_tb_saif.f
	@cd ./build/saif && cat packages.temp >> ara_tb_saif.f
	@cd ./build/saif && cat defines.temp  >> ara_tb_saif.f
	@cd ./build/saif && cat rtl.temp      >> ara_tb_saif.f
	@$(call generate_sram_filelist, $(spsram127_techlib_path), ./build/saif/ara_tb_saif.f)
	@$(call generate_sram_filelist, $(spsram_techlib_path),    ./build/saif/ara_tb_saif.f)
	@echo "2.VCS simulate"
	@rm sim_saif -rf
	@mkdir -p ./sim_saif/incremental_db
	@cd ./sim_saif && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(SIMULATOR_DEF) -f ../build/saif/ara_tb_saif.f $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT) -v /home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140_170a_vlg/TSMCHOME/digital/Front_End/verilog/tcbn28hpcplusbwp12t40p140_170a/tcbn28hpcplusbwp12t40p140.v /home/wangwy/openproject/ara/hardware/build/work-dpi/elfloader.o
	@cd ./sim_saif && ./simv -l run.vcs.log $(SIMV_POWER_OPT) $(APP)
	@echo "3.vcd2saif"
	@vcd2saif -input ./vcd/$(app).vcd -output ./saif/$(app).saif -time $(start_time) $(stop_time)

sim_apps ?= fft imatmul
sim_all:
	for sim_app in $(sim_apps);do \
		$(MAKE) sim app=$$(sim_app); \
	done

saif_apps ?= fft imatmul
saif_all:
	for saif_app in $(saif_apps);do \
		$(MAKE) sim app=$$(saif_app) mc=1; \
	done

saif_ara:
	mkdir -p $(vcs_library) ./saif_ara
	echo "ARA Configuration: NR_LANES=$(nr_lanes) VLEN=$(vlen)"
	$(BENDER) script verilator $(bender_targs_vcs) $(bender_defs_veril) --define SAIF > $(vcs_library)/bender_script_$(config)
	$(call generate_sram_filelist, $(spsram127_techlib_path), $(vcs_library)/bender_script_$(config))
	$(call generate_sram_filelist, $(spsram_techlib_path), $(vcs_library)/bender_script_$(config))
	cd $(vcs_library) && cat bender_script_$(config) | grep -v "ara.sv" > rtl.temp
	cd $(vcs_library) && mv rtl.temp bender_script_$(config)
	cd $(vcs_library) && echo "/home/wangwy/openproject/ara/backend/syn/ara_soc/v1-dc/outputs/ara_dc.v" >> bender_script_$(config) 
	mkdir -p ./$(sim_dir)/incremental_db
	cd ./$(sim_dir) && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(SIMULATOR_DEF) $(SIM_FILELIST) $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT) -v /home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140_170a_vlg/TSMCHOME/digital/Front_End/verilog/tcbn28hpcplusbwp12t40p140_170a/tcbn28hpcplusbwp12t40p140.v #/home/wangwy/openproject/ara/hardware/build/work-dpi/elfloader.o
	cd ./$(sim_dir) && ./simv -l run.vcs.log $(SIMV_POWER_OPT) $(APP)
	vcd2saif -input ./vcd/$(app).vcd -output ./saif_ara/$(app).saif
