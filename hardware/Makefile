SHELL = /usr/bin/env bash
ROOT_DIR := $(patsubst %/,%, $(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ARA_DIR := $(shell git rev-parse --show-toplevel 2>/dev/null || echo $$ARA_DIR)
INSTALL_DIR := $(abspath $(ROOT_DIR)/../install)
VERILATOR_INCLUDE := $(INSTALL_DIR)/verilator/share/verilator/include/vltstd

BENDER         ?= $(ROOT_DIR)/bender
BENDER_VERSION := 0.27.3

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

# Optional behavioral memory expansion for large application replay. This is
# intentionally separate from the synthesized 1 MiB L2 and SRAM-macro flow.
mc ?= 0
qbs ?= 0
akv ?= 0
akv_v2 ?= 0
qbs_perf ?= 0
sim_l2_mb ?= 1
large_l2_mb ?= 16
valid_sim_l2_mb := 1 2 4 8 16 32 64
ifeq ($(filter $(sim_l2_mb),$(valid_sim_l2_mb)),)
$(error sim_l2_mb must be one of: $(valid_sim_l2_mb))
endif
sim_l2_bytes := $(shell echo $$(( $(sim_l2_mb) * 1024 * 1024 )))
ifneq ($(sim_l2_mb),1)
  ifeq ($(mc),1)
    $(error simulation-only L2 expansion cannot be combined with mc=1)
  endif
  ifneq ($(filter dc dc_flist dc_preflight sram saif saif_all saif_ara,$(MAKECMDGOALS)),)
    $(error simulation-only L2 expansion cannot be used by synthesis, SRAM generation, or SAIF targets)
  endif
endif

# build path
ifeq ($(sim_l2_mb),1)
buildpath      ?= $(ARA_DIR)/hardware/build
else
buildpath      ?= $(ARA_DIR)/hardware/build_sim_l2_$(sim_l2_mb)m
endif
resultpath     ?= results
# questa library
library        ?= work
# dpi library
dpi_library    ?= work-dpi
# verilator library
vcs_library  ?= $(buildpath)/vcs
veril_library ?= $(buildpath)/verilator
veril_path    ?= $(abspath $(INSTALL_DIR)/verilator/bin)
veril_top     ?= ara_tb_verilator
veril_jobs    ?= 8
veril_threads ?= 4
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
ifeq ($(qbs),1)
bender_defs += --define ARA_QBS_ENABLE=1
endif
ifeq ($(akv),1)
bender_defs += --define ARA_AKV_ENABLE=1
endif
ifeq ($(akv_v2),1)
bender_defs += --define ARA_AKV_ENABLE=1 --define ARA_AKV_V2_ENABLE=1
endif
ifneq ($(sim_l2_mb),1)
bender_defs += --define SIM_L2_SIZE_BYTES=$(sim_l2_bytes)
endif

bender_defs_veril = $(bender_defs) --define COMMON_CELLS_ASSERTS_OFF
# Targets
bender_common_targs := -t rtl -t cv64a6_imafdcv_sv39 -t tech_cells_generic_include_tc_sram -t tech_cells_generic_include_tc_clk -t exclude_first_pass_decoder
bender_targs_veril    := $(bender_common_targs) -t cva6_test -t notsynthesis -t verilator
bender_targs_spyglass := $(bender_common_targs) -t spyglass

ifeq ($(mc), 1)
  bender_targs_vcs      := $(bender_common_targs) -t ara_test -t cva6_test -t notsynthesis -t sram_mc
  bender_targs_dc       := $(bender_common_targs) -t synthesis -t sram_blackbox -t sram_mc -t tech_cells_generic_exclude_tc_sram
else
bender_targs_vcs      := $(bender_common_targs) -t ara_test -t cva6_test -t notsynthesis
bender_targs_dc       := $(bender_common_targs) -t synthesis -t sram_blackbox
endif

ifeq ($(mc), 1)
  sim_dir ?= sim_mc
else ifneq ($(sim_l2_mb),1)
  sim_dir ?= sim_l2_$(sim_l2_mb)m
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
SIM_FILELIST := -f $(vcs_library)/bender_script_$(config) $(buildpath)/$(dpi_library)/elfloader.o
SIM_TIME := #+vcs+finish+10000ns
APP := +PRELOAD=$(preload) +TESTCASE=$(app)
ifeq ($(no_fsdb), 1)
APP += +NO_FSDB
endif
ifeq ($(qbs_perf), 1)
APP += +QBS_PERF
endif

.PHONY: bender compile compile_large verilate sim sim_large sim_verilator verify clean verdi lint trace dc dc_flist dc_preflight dpi sram saif sim_all saif_all saif_ara llama_spike_build llama_spike_check llama_spike_list llama_spike llama_real_list llama_real_eval_list llama_real_eval_compile llama_real_eval_parallel llama_real_eval_status llama_real_build llama_real_spike llama_real_sim llama_real_sum llama_real_metrics_sum llama_qbs_eval_list llama_qbs_eval_build llama_qbs_eval_compile llama_qbs_eval_parallel llama_qbs_eval_status llama_qbs_eval_sum llama_format_list llama_format_build llama_format_rvv_compile llama_format_qbs_compile llama_format_rvv_parallel llama_format_qbs_parallel llama_format_status llama_format_sum

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
	@$(CXX) -shared -fPIC -std=c++11 -Bsymbolic -c $< -I$(VERILATOR_INCLUDE) -I$(INSTALL_DIR)/riscv-isa-sim/include -o $@

$(buildpath)/$(dpi_library)/ara_dpi.so: $(dpi)
	@mkdir -p $(buildpath)/$(dpi_library)
	@$(CXX) -shared -m64 -o $(buildpath)/$(dpi_library)/ara_dpi.so $?

compile: bender dpi ../Bender.yml
	@mkdir -p $(vcs_library)
	@echo "ARA Configuration: NR_LANES=$(nr_lanes) VLEN=$(vlen)"
	@$(BENDER) script verilator --no-default-target -t verilator $(bender_targs_vcs) $(bender_defs_veril) --define FOR_VERIFY  > $(vcs_library)/bender_script_$(config)
	@$(call generate_sram_filelist, $(sram_techlib_path), $(vcs_library)/bender_script_$(config))
	@mkdir -p ./$(sim_dir)/incremental_db
	@cd ./$(sim_dir) && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(SIMULATOR_DEF) $(SIM_FILELIST) $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT)
	@printf 'schema_version=1\nsim_l2_mb=%s\nsim_l2_bytes=%s\n' \
		'$(sim_l2_mb)' '$(sim_l2_bytes)' > ./$(sim_dir)/simulator.conf

verilate: bender ../Bender.yml
	@rm -rf $(veril_library)
	@mkdir -p $(veril_library)
	@$(BENDER) script verilator --no-default-target \
		$(bender_targs_veril) $(bender_defs_veril) \
		> $(veril_library)/bender_script_$(config).raw
	@grep -v '/deprecated/pad_functional.sv' \
		$(veril_library)/bender_script_$(config).raw \
		> $(veril_library)/bender_script_$(config)
	@$(veril_path)/verilator \
		-f $(veril_library)/bender_script_$(config) \
		-GNrLanes=$(nr_lanes) -GVLEN=$(vlen) -GL2SizeBytes=$(sim_l2_bytes) \
		-O3 --timing --hierarchical --threads $(veril_threads) \
		-Wno-fatal -Wno-MODDUP -Wno-PINCONNECTEMPTY -Wno-PINMISSING \
		-Wno-BLKANDNBLK -Wno-CASEINCOMPLETE -Wno-CMPCONST -Wno-LATCH \
		-Wno-LITENDIAN -Wno-UNOPTFLAT -Wno-UNPACKED -Wno-UNSIGNED \
		-Wno-WIDTH -Wno-WIDTHCONCAT -Wno-ENUMVALUE -Wno-COMBDLY \
		-Wno-SELRANGE -Wno-ALWCOMBORDER -Wno-IMPLICIT \
		--Mdir $(veril_library) --compiler gcc \
		-CFLAGS "-O3 -march=native -DTOPLEVEL_NAME=$(veril_top)" \
		-CFLAGS "-DNR_LANES=$(nr_lanes) -DL2_SIZE_BYTES=$(sim_l2_bytes)" \
		-CFLAGS "-I$(ROOT_DIR)/tb/verilator/lowrisc_dv_verilator_memutil_dpi/cpp" \
		-CFLAGS "-I$(ROOT_DIR)/tb/verilator/lowrisc_dv_verilator_memutil_verilator/cpp" \
		-CFLAGS "-I$(ROOT_DIR)/tb/verilator/lowrisc_dv_verilator_simutil_verilator/cpp" \
		-LDFLAGS "-lelf" --exe \
		$(ROOT_DIR)/tb/verilator/lowrisc_dv_verilator_memutil_dpi/cpp/*.cc \
		$(ROOT_DIR)/tb/verilator/lowrisc_dv_verilator_memutil_verilator/cpp/*.cc \
		$(ROOT_DIR)/tb/verilator/lowrisc_dv_verilator_simutil_verilator/cpp/*.cc \
		$(ROOT_DIR)/tb/verilator/ara_tb.cpp \
		--cc --top-module $(veril_top)
	@$(MAKE) -C $(veril_library) -j$(veril_jobs) -f V$(veril_top).mk

sim_verilator: verilate
	@test -n "$(app)" || { echo "usage: make sim_verilator app=<app> [sim_l2_mb=16]" >&2; exit 2; }
	@$(veril_library)/V$(veril_top) \
		-l ram,$(app_path)/$(app),elf \
		$(if $(filter 1,$(qbs_perf)),+QBS_PERF,) \
		$(if $(filter 1,$(akv_v2)),+AKV_PERF,)

compile_large:
	@$(MAKE) compile sim_l2_mb=$(large_l2_mb)

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

sim_large:
	@test -n "$(app)" || { echo "usage: make sim_large app=<app> [large_l2_mb=16]" >&2; exit 2; }
	@$(MAKE) -C ../apps $(app) sim_l2_mb=$(large_l2_mb)
	@$(MAKE) sim app=$(app) sim_l2_mb=$(large_l2_mb)
verify: 
	@cd ../apps && $(MAKE) $(app) && $(MAKE) bin/$(app).ideal
	@$(MAKE) sim app=$(app) verify=1 ideal_dispatcher=1
#	@./regdump_compare.py sim/regdump.ideal sim/regdump.real --trace --trace-reg --dest-only --log-file sim/regdump_compare.log

llama_spike_build:
	@./scripts/llama_q4km_extract/build-spike.sh

llama_spike_list:
	@./scripts/llama_q4km_extract/run-case.sh

llama_spike_check: llama_spike_build
	@./scripts/llama_q4km_extract/cases.py verify-data
	@LLAMA_SPIKE_TIMEOUT=$${LLAMA_SPIKE_TIMEOUT:-300} \
		./scripts/llama_q4km_extract/run-case-spike.sh \
		micro/q4_k_x_q8_k_dot_n1536_nrc1

llama_spike:
	@test -n "$(case)" || { \
		echo "usage: make llama_spike case=<case-id>" >&2; \
		echo "list cases: ./scripts/llama_q4km_extract/run-case.sh" >&2; \
		exit 2; \
	}
	@$(MAKE) llama_spike_build
	@LLAMA_SPIKE_TIMEOUT=$${LLAMA_SPIKE_TIMEOUT:-3600} \
		./scripts/llama_q4km_extract/run-case-spike.sh "$(case)"

llama_real_list:
	@printf '%s\n' \
		decode_attn_q decode_ffn_gate decode_ffn_down \
		prefill_attn_q prefill_ffn_gate prefill_ffn_down

llama_real_eval_list:
	@printf '%s\n' \
		decode_attn_q_eval decode_ffn_gate_eval decode_ffn_down_eval \
		prefill_attn_q_eval prefill_ffn_gate_eval prefill_ffn_down_eval

llama_real_eval_compile:
	@$(MAKE) compile sim_l2_mb=$(large_l2_mb) \
		sim_dir=sim_llama_eval_$(large_l2_mb)m_template no_fsdb=1

llama_real_eval_parallel:
	@./scripts/llama_qwen25_real/run_eval_parallel.sh

llama_real_eval_status:
	@./scripts/llama_qwen25_real/eval_status.sh

llama_real_build:
	@test -f "../apps/llama_qwen25_$(case)/case.json" || { \
		echo "usage: make llama_real_build case=<case from llama_real_list>" >&2; \
		exit 2; \
	}
	@$(MAKE) -C ../apps "llama_qwen25_$(case)" sim_l2_mb=$(large_l2_mb)

llama_real_spike:
	@test -f "../apps/llama_qwen25_$(case)/case.json" || { \
		echo "usage: make llama_real_spike case=<case from llama_real_list>" >&2; \
		exit 2; \
	}
	@$(MAKE) -C ../apps "spike-run-llama_qwen25_$(case)"

llama_real_sim:
	@test -f "../apps/llama_qwen25_$(case)/case.json" || { \
		echo "usage: make llama_real_sim case=<case from llama_real_list>" >&2; \
		exit 2; \
	}
	@$(MAKE) sim_large app="llama_qwen25_$(case)" \
		large_l2_mb=$(large_l2_mb) no_fsdb=$(no_fsdb)

llama_real_sum:
	@test -n "$(run_log)" -a -n "$(perf_log)" || { \
		echo "usage: make llama_real_sum run_log=<run.vcs.log> perf_log=<perf_report.log> [output=result.csv]" >&2; \
		exit 2; \
	}
	@./scripts/llama_qwen25_real/summarize.py \
		--run-log "$(run_log)" --perf-log "$(perf_log)" \
		--output "$(or $(output),llama_real_result.csv)"

llama_real_metrics_sum:
	@test -n "$(metrics_log)" || { \
		echo "usage: make llama_real_metrics_sum metrics_log=<llm_perf_report.log> [output=metrics.csv]" >&2; \
		exit 2; \
	}
	@./scripts/llama_qwen25_real/summarize_llm_perf.py \
		--metrics-log "$(metrics_log)" \
		--output "$(or $(output),llama_real_metrics.csv)"

llama_qbs_eval_list:
	@printf '%s\n' \
		decode_attn_q_qbs decode_ffn_gate_qbs decode_ffn_down_qbs \
		prefill_attn_q_qbs prefill_ffn_gate_qbs prefill_ffn_down_qbs

llama_qbs_eval_build:
	@$(MAKE) -C ../verification/qbs generated-check
	@$(MAKE) -C ../apps \
		llama_qwen25_decode_attn_q_qbs \
		llama_qwen25_decode_ffn_gate_qbs \
		llama_qwen25_decode_ffn_down_qbs \
		llama_qwen25_prefill_attn_q_qbs \
		llama_qwen25_prefill_ffn_gate_qbs \
		llama_qwen25_prefill_ffn_down_qbs \
		sim_l2_mb=$(large_l2_mb)

llama_qbs_eval_compile:
	@$(MAKE) compile qbs=1 sim_l2_mb=$(large_l2_mb) \
		buildpath=$(ARA_DIR)/hardware/build_qbs_llama_eval_$(large_l2_mb)m \
		sim_dir=sim_qbs_llama_eval_$(large_l2_mb)m_template no_fsdb=1

llama_qbs_eval_parallel:
	@./scripts/qbs/run_eval_parallel.sh

llama_qbs_eval_status:
	@./scripts/llama_qwen25_real/eval_status.sh \
		"$(or $(run_root),$(ROOT_DIR)/qbs_eval_runs/latest)"

llama_qbs_eval_sum:
	@./scripts/qbs/summarize_qbs_suite.py \
		--run-root "$(or $(run_root),$(ROOT_DIR)/qbs_eval_runs/latest)" \
		$(if $(filter 1,$(allow_partial)),--allow-partial,)

llama_format_list:
	@printf '%s\n' \
		q3k_decode_attn_q q5k_decode_attn_q \
		q6k_decode_attn_q q8_0_decode_attn_q

llama_format_build:
	@$(MAKE) -C ../apps \
		llama_qwen25_q3k_decode_attn_q_rvv \
		llama_qwen25_q3k_decode_attn_q_qbs \
		llama_qwen25_q5k_decode_attn_q_rvv \
		llama_qwen25_q5k_decode_attn_q_qbs \
		llama_qwen25_q6k_decode_attn_q_rvv \
		llama_qwen25_q6k_decode_attn_q_qbs \
		llama_qwen25_q8_0_decode_attn_q_rvv \
		llama_qwen25_q8_0_decode_attn_q_qbs sim_l2_mb=1

llama_format_rvv_compile:
	@$(MAKE) compile qbs=0 sim_l2_mb=1 \
		buildpath=$(ARA_DIR)/hardware/build_rvv_real_formats_1m \
		sim_dir=sim_rvv_real_formats_1m_template no_fsdb=1

llama_format_qbs_compile:
	@$(MAKE) compile qbs=1 sim_l2_mb=1 \
		buildpath=$(ARA_DIR)/hardware/build_qbs_real_formats_1m \
		sim_dir=sim_qbs_real_formats_1m_template no_fsdb=1

llama_format_rvv_parallel:
	@./scripts/llama_qwen25_real/run_format_parallel.sh rvv

llama_format_qbs_parallel:
	@./scripts/llama_qwen25_real/run_format_parallel.sh qbs

llama_format_status:
	@test "$(mode)" = rvv -o "$(mode)" = qbs || { \
		echo "usage: make llama_format_status mode=<rvv|qbs> [run_root=...]" >&2; \
		exit 2; \
	}
	@./scripts/llama_qwen25_real/eval_status.sh \
		"$(or $(run_root),$(ROOT_DIR)/$(mode)_format_eval_runs/latest)"

llama_format_sum:
	@./scripts/llama_qwen25_real/summarize_format_closure.py \
		--rvv-root "$(or $(rvv_root),$(ROOT_DIR)/rvv_format_eval_runs/latest)" \
		--qbs-root "$(or $(qbs_root),$(ROOT_DIR)/qbs_format_eval_runs/latest)" \
		--output "$(or $(output),$(ROOT_DIR)/format_closure.csv)" \
		--markdown-output "$(or $(markdown_output),$(ROOT_DIR)/format_closure.md)"

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

dc_flist:
	@echo "1.Generating dc flist"
	@mkdir -p ../backend/flist
	@$(BENDER) script --no-default-target verilator $(bender_targs_dc) $(bender_defs_veril) > ../backend/flist/ara_soc.f
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

dc_preflight: dc_flist
	@python3 scripts/akv/check-synthesis-preflight.py \
		--filelist ../backend/flist/ara_soc_dc.f \
		--sdc ../backend/syn/ara_soc/v1-dc/local_scripts/ara_soc.sdc \
		--setup ../backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env \
		$(if $(filter 1,$(qbs)),--require-qbs,) \
		$(if $(filter 1,$(akv) $(akv_v2)),--require-akv,) \
		$(if $(filter 1,$(akv_v2)),--require-akv-v2,) \
		$(if $(filter 1,$(mc)),--require-macro-sram,) \
		--nr-lanes $(nr_lanes) --vlen $(vlen)

dc: dc_preflight
	@echo "2.Synthesis"
	@cd ../backend/syn/ara_soc/v1-dc/run/ && ./run.cmd
	@if [ "$(mc)" = "1" ] && [ "$(qbs)" = "1" ] && [ "$(akv_v2)" = "1" ]; then \
		python3 scripts/akv/collect-synthesis-results.py --mode integrated; \
	else \
		echo "AKV physical result collection skipped (requires mc=1 qbs=1 akv_v2=1)"; \
	fi

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
