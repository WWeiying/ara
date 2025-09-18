SHELL = /usr/bin/env bash
ROOT_DIR := $(patsubst %/,%, $(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ARA_DIR := $(shell git rev-parse --show-toplevel 2>/dev/null || echo $$ARA_DIR)
INSTALL_DIR := $(abspath $(ROOT_DIR)/../install)
VERILATOR_INCLUDE := $(INSTALL_DIR)/verilator/share/verilator/include/vltstd

BENDER         := $(ROOT_DIR)/../hardware/bender
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
spsram127_techlib_path := /home/wangwy/technical_library/tsmc28nm/Memory/tsn28hpcpd127spsram_20120200_180a/AN61001_20180416/tsn28hpcpd127spsram_20120200_180a/TSMCHOME/sram/Compiler/tsn28hpcpd127spsram_20120200_180a/tsn28hpcpd127spsram_20120200_180a
spsram_techlib_path := /home/wangwy/technical_library/tsmc28nm/Memory/tsn28hpcpuhdspsram_20120200_170a/AN61001_20180125/tsn28hpcpuhdspsram_20120200_170a/TSMCHOME/sram/Compiler/tsn28hpcpuhdspsram_20120200_170a/tsn28hpcpuhdspsram_20120200_170a

mc ?= 0
saif ?= 0

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

ifeq ($(ideal_dispatcher), 1)
  vtrace       = $(vtrace_path)/$(app).vtrace
  bender_defs += --define IDEAL_DISPATCHER=1 --define VTRACE="$(vtrace)" --define N_VINSN=$(shell wc -l $(vtrace) | cut -d " " -f 1)
  ideal        = "_ideal"
endif

# Bender
# Defines
bender_defs += --define NR_LANES=$(nr_lanes) --define VLEN=$(vlen) --define ARIANE_ACCELERATOR_PORT=1

bender_defs_veril = $(bender_defs) --define COMMON_CELLS_ASSERTS_OFF
ifeq ($(saif), 1)
  bender_defs += --define SAIF
endif
# Targets
bender_common_targs := -t rtl -t cv64a6_imafdcv_sv39 -t tech_cells_generic_include_tc_sram -t tech_cells_generic_include_tc_clk -t exclude_first_pass_decoder
bender_targs_simc     := $(bender_common_targs) -t ara_test -t cva6_test
bender_targs_veril    := $(bender_common_targs) -t ara_test -t cva6_test -t verilator
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
SIMULATOR_LOG := -l comp.vcs.log
SIMULATOR_POWER_OPT := 
SIMV_POWER_OPT      := +fsdb+power +fsdb+all 
SIM_DUMP := 
SIM_FILELIST := -f $(vcs_library)/bender_script_$(config) /home/wangwy/openproject/ara/hardware/build/work-dpi/elfloader.o
SIM_TIME := #+vcs+finish+10000ns
APP := +PRELOAD=$(preload) +TESTCASE=$(app)

.PHONY: bender compile sim clean verdi lint trace dc dpi sram saif 

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
	@$(BENDER) script verilator $(bender_targs_vcs) $(bender_defs_veril) > $(vcs_library)/bender_script_$(config)
	@$(call generate_sram_filelist, $(spsram127_techlib_path), $(vcs_library)/bender_script_$(config))
	@$(call generate_sram_filelist, $(spsram_techlib_path), $(vcs_library)/bender_script_$(config))
	@mkdir -p ./$(sim_dir)/incremental_db
	@cd ./$(sim_dir) && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(SIMULATOR_DEF) $(SIM_FILELIST) $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT)

sim: compile
	@export NOVAS_FSDB_QUIET=1
	@cd ./$(sim_dir) && ./simv -l run.vcs.log $(SIMV_POWER_OPT) $(APP)

clean:
	@cd ./$(sim_dir) && rm -rf *
	@rm -rf $(buildpath)

verdi:
	@cd ./$(sim_dir) && verdi $(SIMULATOR_DEF) -sv $(SIM_FILELIST) -top ara_tb -dbdir simv.daidir -ssf ara_tb.fsdb -l verdi.log &

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
	grep -v "_pkg.sv" > rtl.temp
	@cd ../backend/flist && cat ara_soc.f | grep "incdir" > incdir.temp 
	@cd ../backend/flist && echo "+define+SYNTHESIS" > defines.temp 
	@cd ../backend/flist && echo "+define+HPDCACHE_ASSERT_OFF" > defines.temp 
	@cd ../backend/flist && cat ara_soc.f | grep "+define" >> defines.temp 
	@cd ../backend/flist && cat ara_soc.f | grep "_pkg.sv" > packages.temp 
	@cd ../backend/flist && cat incdir.temp > ara_soc_dc.f
	@cd ../backend/flist && cat defines.temp >> ara_soc_dc.f
	@cd ../backend/flist && cat packages.temp >> ara_soc_dc.f
	@cd ../backend/flist && cat rtl.temp >> ara_soc_dc.f
	@echo "2.Synthesis"
	@cd ../backend/syn/ara_soc/v1-dc/run/ && ./run.cmd

sram:
	@$(call generate_sram, $(spsram127_techlib_path), $(L2_SRAM_CONFIGS))
	@$(call generate_sram, $(spsram_techlib_path), $(VECTOR_REGFILE_SRAM_CONFIGS))
	@$(call generate_sram, $(spsram_techlib_path), $(ICACHE_TAG_SRAM_CONFIGS))
	@$(call generate_sram, $(spsram_techlib_path), $(ICACHE_DATA_SRAM_CONFIGS))
	@$(call generate_sram, $(spsram_techlib_path), $(DCACHE_DATA_SRAM_CONFIGS))

saif:
	mkdir -p ./vcd ./saif
	$(MAKE) sim app=$(app) mc=1 saif=1
	vcd2saif -input ./vcd/$(app).vcd -output ./saif/$(app).saif
