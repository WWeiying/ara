SHELL = /usr/bin/env bash
ROOT_DIR := $(patsubst %/,%, $(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ARA_DIR := $(shell git rev-parse --show-toplevel 2>/dev/null || echo $$ARA_DIR)
INSTALL_DIR := $(abspath $(ROOT_DIR)/../install)
VERILATOR_INCLUDE := $(INSTALL_DIR)/verilator/share/verilator/include/vltstd

BENDER_FALLBACK := /home/wangwy/openproject/ara/hardware/bender
BENDER         ?= $(shell \
	if [ -x "$(ROOT_DIR)/bender" ]; then \
	  echo "$(ROOT_DIR)/bender"; \
	elif command -v bender >/dev/null 2>&1; then \
	  command -v bender; \
	elif [ -x "$(BENDER_FALLBACK)" ]; then \
	  echo "$(BENDER_FALLBACK)"; \
	else \
	  echo "$(ROOT_DIR)/bender"; \
	fi)
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

# Per-app HDV kernel arguments (a0-a3).  The TB's default HdvInitial* values are
# vsaxpy's; every other HDV kernel needs its own pointer arguments because main()'s
# C argument setup never runs under HDV (the TB jumps straight to the kernel entry).
# Values are plain decimal addresses (the TB zero-extends them to 64 bits).
ifeq ($(app),vsspmv_hdv)
  hdv_initial_a0 ?= $(shell printf '%d' 0x80001100)  # a0 = src1   (val)
  hdv_initial_a1 ?= $(shell printf '%d' 0x80021200)  # a1 = col_idx (gather indices)
  hdv_initial_a2 ?= $(shell printf '%d' 0x80011180)  # a2 = src2   (x, gather base)
  hdv_initial_a3 ?= $(shell printf '%d' 0x80011280)  # a3 = src2+64 (y, output)
endif
ifeq ($(app),vsdot_hdv)
  hdv_initial_a0 ?= $(shell printf '%d' 0x80001070)  # a0 = src1 (a)
  hdv_initial_a1 ?= $(shell printf '%d' 0x80005080)  # a1 = src2 (b)
  hdv_initial_a2 ?= 1024                             # a2 = avl  (TOTAL_ELEMENTS)
endif
ifeq ($(app),vsscal_hdv)
  hdv_initial_a0 ?= 1024                             # a0 = n (TOTAL_ELEMENTS)
  hdv_initial_a1 ?= $(shell printf '%d' 0x80001040)  # a1 = src
  hdv_initial_a2 ?= $(shell printf '%d' 0x80005050)  # a2 = dst (fa0=6.66=vsaxpy default)
endif
ifeq ($(app),fdotp_hdv)
  hdv_initial_a0 ?= $(shell printf '%d' 0x80001090)  # a0 = v64a
  hdv_initial_a1 ?= $(shell printf '%d' 0x80002090)  # a1 = v64b
  hdv_initial_a2 ?= 1024                             # a2 = avl (DOTP_AVL)
endif
ifeq ($(app),vmc_hdv)
  hdv_initial_a0 ?= 1024                             # a0 = n (TOTAL_ELEMENTS)
  hdv_initial_a1 ?= $(shell printf '%d' 0x800010d0)  # a1 = src1
  hdv_initial_a2 ?= $(shell printf '%d' 0x800020e0)  # a2 = dest
  hdv_initial_a3 ?= 3                                # a3 = shift
endif
ifeq ($(app),jacobi2d_hdv)
  hdv_initial_a0 ?= 130                              # a0 = R
  hdv_initial_a1 ?= 130                              # a1 = C
  hdv_initial_a2 ?= $(shell printf '%d' 0x800011d0)  # a2 = A_v
  hdv_initial_a3 ?= $(shell printf '%d' 0x800264f0)  # a3 = B_v
endif
ifeq ($(app),dropout_hdv)
  hdv_initial_a0 ?= 1024                             # a0 = n (N)
  hdv_initial_a1 ?= $(shell printf '%d' 0x80001090)  # a1 = in (I)
  hdv_initial_a2 ?= $(shell printf '%d' 0x80002090)  # a2 = sel (SEL); scale->fa0
  hdv_initial_a3 ?= $(shell printf '%d' 0x80002490)  # a3 = o
endif
ifeq ($(app),lavamd_hdv)
  hdv_initial_a0 ?= $(shell printf '%d' 0x800082c0)  # a0 = bx (px)
  hdv_initial_a1 ?= $(shell printf '%d' 0x800086c0)  # a1 = by (py)
  hdv_initial_a2 ?= $(shell printf '%d' 0x80008ac0)  # a2 = bz (pz)
  hdv_initial_a3 ?= $(shell printf '%d' 0x80008ec0)  # a3 = bv (pv)
  hdv_initial_a4 ?= $(shell printf '%d' 0x800092c0)  # a4 = bq (pq)
  hdv_initial_a5 ?= $(shell printf '%d' 0x800096c0)  # a5 = aparams (ap)
  hdv_initial_a6 ?= $(shell printf '%d' 0x800096d8)  # a6 = fout_v (output)
  hdv_initial_a7 ?= 256                              # a7 = NPAR (count)
endif
ifeq ($(app),softmax_hdv)
  hdv_initial_a0 ?= $(shell printf '%d' 0x800082d0)  # a0 = i  (input)
  hdv_initial_a1 ?= $(shell printf '%d' 0x8000a6d0)  # a1 = o_v (output)
  hdv_initial_a2 ?= 3                                # a2 = channels
  hdv_initial_a3 ?= 256                              # a3 = innerSize
endif
ifeq ($(app),fconv2d_hdv)
  hdv_initial_a0 ?= $(shell printf '%d' 0x8001c710)  # a0 = o  (output)
  hdv_initial_a1 ?= $(shell printf '%d' 0x80001260)  # a1 = i  (input)
  hdv_initial_a2 ?= $(shell printf '%d' 0x8001c580)  # a2 = f  (filter)
  hdv_initial_a3 ?= 112                              # a3 = M (rows)
  hdv_initial_a4 ?= 112                              # a4 = N (cols)
  hdv_initial_a5 ?= 7                                # a5 = F (filter dim, 7x7)
endif

ifdef hdv_task_entry
  bender_defs += --define HDV_TASK_ENTRY=$(hdv_task_entry)
endif
ifdef hdv_vsaxpy_elements
  bender_defs += --define HDV_VSAXPY_ELEMENTS=$(hdv_vsaxpy_elements)
endif
ifdef hdv_expected_ep
  bender_defs += --define HDV_EXPECTED_EP=$(hdv_expected_ep)
endif
ifdef hdv_initial_a0
  bender_defs += --define HDV_INITIAL_A0=$(hdv_initial_a0)
endif
ifdef hdv_initial_a1
  bender_defs += --define HDV_INITIAL_A1=$(hdv_initial_a1)
endif
ifdef hdv_initial_a2
  bender_defs += --define HDV_INITIAL_A2=$(hdv_initial_a2)
endif
ifdef hdv_initial_a3
  bender_defs += --define HDV_INITIAL_A3=$(hdv_initial_a3)
endif
ifdef hdv_initial_a4
  bender_defs += --define HDV_INITIAL_A4=$(hdv_initial_a4)
endif
ifdef hdv_initial_a5
  bender_defs += --define HDV_INITIAL_A5=$(hdv_initial_a5)
endif
ifdef hdv_initial_a6
  bender_defs += --define HDV_INITIAL_A6=$(hdv_initial_a6)
endif
ifdef hdv_initial_a7
  bender_defs += --define HDV_INITIAL_A7=$(hdv_initial_a7)
endif
ifdef hdv_initial_fa0
  bender_defs += --define HDV_INITIAL_FA0=$(hdv_initial_fa0)
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
SIMULATOR_LOG := -l comp.vcs.log
SIMULATOR_POWER_OPT := 
SIMV_POWER_OPT      := +fsdb+power +fsdb+all 
SIM_DUMP := 
dump_vcd ?= 0
FSDB2VCD ?= fsdb2vcd
FSDB2VCD_OUT ?= ara_tb.vcd
SIM_FILELIST := -f $(vcs_library)/bender_script_$(config) $(buildpath)/$(dpi_library)/elfloader.o
SIM_TIME := #+vcs+finish+10000ns
APP := +PRELOAD=$(preload) +TESTCASE=$(app)

.PHONY: bender compile sim verify clean verdi lint trace dc dpi sram saif sim_all saif_all saif_ara

# Bender
bender: $(BENDER)
$(BENDER):
	@[ -x $(BENDER) ] && echo "Bender already exists." || \
	(cd $(ROOT_DIR) && curl --proto '=https' --tlsv1.2 https://pulp-platform.github.io/bender/init -sSf | sh -s -- $(BENDER_VERSION))
	@echo "$$($(BENDER) --version) available."

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
	@$(BENDER) script verilator $(bender_targs_vcs) $(bender_defs_veril) --define FOR_VERIFY  > $(vcs_library)/bender_script_$(config)
	@$(call generate_sram_filelist, $(sram_techlib_path), $(vcs_library)/bender_script_$(config))
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
	@if [ "$(dump_vcd)" = "1" ] && [ -f ./$(sim_dir)/ara_tb.fsdb ]; then \
	  if command -v $(FSDB2VCD) >/dev/null 2>&1; then \
	    echo "Converting ./$(sim_dir)/ara_tb.fsdb -> ./$(sim_dir)/$(FSDB2VCD_OUT)"; \
	    cd ./$(sim_dir) && $(FSDB2VCD) ara_tb.fsdb -o $(FSDB2VCD_OUT); \
	  else \
	    echo "Skipping FSDB to VCD conversion: $(FSDB2VCD) not found"; \
	  fi; \
	fi
	@if [ -f ./$(sim_dir)/$(sim_log) ]; then \
	  cp ./$(sim_dir)/$(sim_log) ./$(sim_dir)/perf.log; \
	else \
	  : > ./$(sim_dir)/perf.log; \
	fi
verify: 
	@cd ../apps && $(MAKE) $(app) && $(MAKE) bin/$(app).ideal
	@$(MAKE) sim app=$(app) verify=1 ideal_dispatcher=1
#	@./regdump_compare.py sim/regdump.ideal sim/regdump.real --trace --trace-reg --dest-only --log-file sim/regdump_compare.log

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
	@echo "0.Preparing dc output dirs"
	@mkdir -p ../backend/flist ../backend/syn/ara_soc/v1-dc/outputs ../backend/syn/ara_soc/v1-dc/reports
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
	@$(call generate_sram, $(spsram_techlib_path), $(HDV_IPU_SRAM_CONFIGS))

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
	@cd ./build/saif && echo "$(ARA_DIR)/backend/syn/ara_soc/v1-dc/outputs/ara_soc_dc.v" >> rtl.temp
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
	@cd ./sim_saif && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(SIMULATOR_DEF) -f ../build/saif/ara_tb_saif.f $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT) -v /home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140_170a_vlg/TSMCHOME/digital/Front_End/verilog/tcbn28hpcplusbwp12t40p140_170a/tcbn28hpcplusbwp12t40p140.v $(buildpath)/$(dpi_library)/elfloader.o
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
	cd $(vcs_library) && echo "$(ARA_DIR)/backend/syn/ara_soc/v1-dc/outputs/ara_dc.v" >> bender_script_$(config)
	mkdir -p ./$(sim_dir)/incremental_db
	cd ./$(sim_dir) && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(SIMULATOR_DEF) $(SIM_FILELIST) $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT) -v /home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140_170a_vlg/TSMCHOME/digital/Front_End/verilog/tcbn28hpcplusbwp12t40p140_170a/tcbn28hpcplusbwp12t40p140.v #/home/wangwy/openproject/ara/hardware/build/work-dpi/elfloader.o
	cd ./$(sim_dir) && ./simv -l run.vcs.log $(SIMV_POWER_OPT) $(APP)
	vcd2saif -input ./vcd/$(app).vcd -output ./saif_ara/$(app).saif
