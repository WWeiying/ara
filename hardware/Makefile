SHELL = /usr/bin/env bash
ROOT_DIR := $(patsubst %/,%, $(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ARA_DIR := $(shell git rev-parse --show-toplevel 2>/dev/null || echo $$ARA_DIR)
INSTALL_DIR := $(abspath $(ROOT_DIR)/../install)

BENDER         := $(ROOT_DIR)/../hardware/bender

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

# build path
buildpath      ?= $(ARA_DIR)/hardware/build
resultpath     ?= results
# questa library
library        ?= work
# dpi library
dpi_library    ?= work-dpi
# verilator library
vcs_library  ?= $(buildpath)/vcs

# Bender
# Defines
bender_defs += --define NR_LANES=$(nr_lanes) --define VLEN=$(vlen) --define ARIANE_ACCELERATOR_PORT=1
bender_defs_veril := $(bender_defs) --define COMMON_CELLS_ASSERTS_OFF
# Targets
bender_common_targs := -t rtl -t cv64a6_imafdcv_sv39 -t tech_cells_generic_include_tc_sram -t tech_cells_generic_include_tc_clk -t exclude_first_pass_decoder
bender_targs_simc     := $(bender_common_targs) -t ara_test -t cva6_test
bender_targs_veril    := $(bender_common_targs) -t ara_test -t cva6_test -t verilator
bender_targs_spyglass := $(bender_common_targs) -t spyglass
bender_targs_vcs      := $(bender_common_targs) -t ara_test -t cva6_test -t notsynthesis

TIMESCALE := -timescale=1ns/100fs
SIMULATOR_OPT := -full64 -sverilog +v2k -Mupdate -j64 -lca -kdb -debug_access+all +nospecify +notimingchecks +lint=TFIPC-L  +vpi +lint=PCWM +error+30
CONFIG := +define+NR_LANES=$(nr_lanes) +define+VLEN=$(vlen)
SIMULATOR_DEF := +define+SIMULATION +define+no_warning +define+TSMC_NO_WARNING
SIMULATOR_LOG := -l comp.vcs.log
SIMULATOR_POWER_OPT := 
SIMV_POWER_OPT      := +fsdb+power +fsdb+all 
SIM_DUMP :=
SIM_FILELIST := -f $(vcs_library)/bender_script_$(config) /home/wangwy/openproject/ara/hardware/build/work-dpi/elfloader.o
SIM_TIME := #+vcs+finish+10000ns
APP := +PRELOAD=/home/wangwy/openproject/ara/apps/bin/$(app)


compile: clean ../Bender.yml
	@echo "ARA NR_LANES=$(nr_lanes) VLEN=$(vlen)"
	@$(BENDER) script verilator $(bender_targs_vcs) $(bender_defs_veril) > $(vcs_library)/bender_script_$(config)
	@mkdir -p ./sim
	@cd ./sim && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(CONFIG) $(SIMULATOR_DEF) $(SIM_FILELIST) $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT)

sim: compile
	@export NOVAS_FSDB_QUIET=1
	@cd ./sim && ./simv -l run.vcs.log $(SIMV_POWER_OPT) $(APP)

clean:
	@cd ./sim && rm -rf *

verdi:
	@cd ./sim && verdi $(SIMULATOR_DEF) -sv $(SIM_FILELIST) -top ara_tb -dbdir simv.daidir -ssf ara_tb.fsdb -l verdi.log &

lint:
	cd ./hardware/lint && rm -rf brook_* *.log reports spyglass-1 brook
	cd ./hardware/lint && ./run.sh

trace:
	@./run/scripts/compare_traces.py -g ./run/log/ref_trace.log -d ./run/log/dut_trace.log -o ./run/log/diff_report
	@head -n 20 ./run/log/diff_report
