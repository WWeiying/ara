# Copyright 2019 ETH Zurich and University of Bologna.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Author: Matheus Cavalcante, ETH Zurich
#         Samuel Riedel, ETH Zurich

SHELL = /usr/bin/env bash
ROOT_DIR := $(patsubst %/,%, $(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
APPS_DIR := $(ROOT_DIR)
COMMON_DIR := $(ROOT_DIR)/common
TESTS_DIR := $(ROOT_DIR)/riscv-tests/isa

# This will overwrite the ROOT_DIR variable from the included makefile
include $(COMMON_DIR)/runtime.mk
include $(COMMON_DIR)/riscv_tests.mk
include $(COMMON_DIR)/default_args.mk

APPS := $(patsubst $(APPS_DIR)/%/main.c,%,$(shell find $(APPS_DIR) -name "main.c"))
APPS += $(patsubst $(APPS_DIR)/%/main.cpp,%,$(shell find $(APPS_DIR) -name "main.cpp"))
# Don't automatically compile the benchmark app, which is only a wrapper around the other apps
BINARIES := $(filter-out bin/benchmarks bin/rivec-bmarks% bin/_%, $(addprefix bin/,$(APPS)))

CVA6_EXTENSIONS := rv64ui rv64uc rv64um rv64uf rv64ud rv64si
# Atomics are messy, since there is currently no memory region capable of handling them
# CVA6_EXTENSIONS := rv64ua
CVA6_BINARIES := $(addprefix bin/, $(cva6_tests))
ARA_EXTENSIONS := rv64uv
ARA_BINARIES := $(addprefix bin/, $(ara_tests))

# Suffix for binaries
ifeq ($(LINUX),1)
BIN_SUFFIX := -linux
else
BIN_SUFFIX :=
endif

# FFT requires special treatment because of its header files
ifeq ($(ENV_DEFINES),)
bin/fft:  ENV_DEFINES += -DFFT_SAMPLES=$(subst ",,$(firstword $(def_args_fft)))
bin/fft%: ENV_DEFINES += -DFFT_SAMPLES=$(subst ",,$(firstword $(def_args_fft)))
endif

all: $(BINARIES)

# Pre-process the linker-script to correclty align the sections
.PHONY: linker_script
linker_script: $(COMMON_DIR)/script/align_sections.sh $(ROOT_DIR)/../../config/$(config).mk
	chmod +x $(COMMON_DIR)/script/align_sections.sh
	rm -f $(COMMON_DIR)/link.ld && cp $(COMMON_DIR)/arch.link.ld $(COMMON_DIR)/link.ld
	$(COMMON_DIR)/script/align_sections.sh $(nr_lanes) $(COMMON_DIR)/link.ld

# Make all applications
$(APPS): % : bin/% $(APPS_DIR)/Makefile $(shell find common -type f)
.PHONY: $(BINARIES)

# Patch spike crt0 to enable vector extension before execution
.PHONY: patch-spike-crt0
patch-spike-crt0: $(spike_env_dir)/benchmarks/common/crt.S
	sed -i s/"li t0, MSTATUS_FS | MSTATUS_XS$$"/"li t0, MSTATUS_FS | MSTATUS_XS | MSTATUS_VS"/ $<
	git update-index --assume-unchanged $<

# Only some applications need to generate and then compile the data file
# Generate a dummy data file for applications that do not need it
ifeq ($(old_data),1)
else
define app_gen_data_template
.PHONY: $1/data.S
$1/data.S:
	cd $1 && if [ -d script ]; then ${PYTHON} script/gen_data.py $(subst ",,$(def_args_$1)) > data.S ; else touch data.S; fi
endef
$(foreach app,$(APPS),$(eval $(call app_gen_data_template,$(app))))
endif

define vector_trace_template
ideal_dispatcher/vtrace/$1.vtrace: bin/$1.spike $(VTRACE_SCRIPTS)
	mkdir -p ideal_dispatcher/vtrace ideal_dispatcher/log ideal_dispatcher/temp
	echo "run" | $(RISCV_SIM_MOD) $(RISCV_SIM_MOD_OPT) $$< 2> ideal_dispatcher/temp/$1.temp 1> ideal_dispatcher/log/$1.log
	cd ideal_dispatcher && scripts/vtrace.sh temp/$1.temp vtrace/$1.vtrace
endef
$(foreach app,$(APPS),$(eval $(call vector_trace_template,$(app))))
#	echo "run" | $(SPIKE_VREG) $(SPIKE_VREG_FLAGS) $$< 2>./$1/vreg_dump 1>/dev/null

define app_compile_template_ideal
bin/$1.ideal: bin/$1.spike ideal_dispatcher/vtrace/$1.vtrace
	mkdir -p bin/
	cp bin/$1.spike bin/$1.ideal
endef
$(foreach app,$(APPS),$(eval $(call app_compile_template_ideal,$(app))))

define app_compile_template_spike
bin/$1.spike: $1/data.S.o.spike $(addsuffix .o.spike, $(shell find $(1) -name "*.c" -o -name "*.cpp" -o -name "*.S")) $(RUNTIME_SPIKE) $(COMMON_SPIKE) patch-spike-crt0
	mkdir -p bin/
	$$(RISCV_CC) -Iinclude $$(RISCV_CCFLAGS_SPIKE) -o $$@ $$(addsuffix .o.spike, $$(shell find $(1) -name "*.c" -o -name "*.cpp" -o -name "*.S")) $(RUNTIME_SPIKE) $$(RISCV_LDFLAGS_SPIKE) -DSPIKE
	$$(RISCV_OBJDUMP) $$(RISCV_OBJDUMP_FLAGS) -D $$@ > $$@.dump
endef
$(foreach app,$(APPS),$(eval $(call app_compile_template_spike,$(app))))

define app_compile_template
bin/$1$(BIN_SUFFIX): $1/data.S.o $(addsuffix .o, $(shell find -L $(1) -name "*.c" -o -name "*.cpp" -o -name "*.S")) $(RUNTIME_LLVM) linker_script
	mkdir -p bin/
	$$(RISCV_CC) -Iinclude $(RISCV_CCFLAGS) -o $$@ $$(addsuffix .o, $$(shell find -L $(1) -name "*.c" -o -name "*.cpp" -o -name "*.S")) $(RUNTIME_LLVM) $$(RISCV_LDFLAGS)
	$$(RISCV_OBJDUMP) $$(RISCV_OBJDUMP_FLAGS) -D $$@ > $(1)/$(1)$(BIN_SUFFIX).dump
	$$(RISCV_NM) -n $$@ >> $(1)/$(1)$(BIN_SUFFIX).dump
	$$(RISCV_STRIP) $$@ -S --strip-unneeded
	$$(RISCV_CC) $(RISCV_CCFLAGS) -dM -E - < /dev/null > compiler_macros.h
endef
$(foreach app,$(APPS),$(eval $(call app_compile_template,$(app))))

# Make the RISC-V tests
riscv_tests: $(CVA6_BINARIES) $(ARA_BINARIES)

define rvtest_compile_template
TESTS_$(1) := $(addprefix bin/, $($(addsuffix _ara_tests, $1)))

bin/$(1)-ara-%: $(TESTS_DIR)/$(1)/%.$(2) $(RUNTIME_GCC) linker_script
	mkdir -p bin/
	$$(RISCV_CC_GCC) -Iinclude -I$$(TESTS_DIR)/macros/scalar -I$$(TESTS_DIR)/macros/vector $$(RISCV_CCFLAGS_GCC) $$(RISCV_LDFLAGS_GCC) -o $$@ $$< $(RUNTIME_GCC)
	$$(RISCV_OBJDUMP) $$(RISCV_OBJDUMP_FLAGS) -D $$@ > $$@.dump
	$$(RISCV_STRIP) $$@ -S --strip-unneeded
endef

define rvtest_compile_template_c
TESTS_$(1) := $(addprefix bin/, $($(addsuffix _ara_tests, $1)))

bin/$(1)-ara-%: $(TESTS_DIR)/$(1)/%.$(2) $(RUNTIME_LLVM) linker_script
	mkdir -p bin/
	$$(RISCV_CC) -Iinclude -I$$(TESTS_DIR)/macros/scalar -I$$(TESTS_DIR)/macros/vector $$(RISCV_CCFLAGS) $$(RISCV_LDFLAGS) -o $$@ $$< $(RUNTIME_LLVM)
	$$(RISCV_OBJDUMP) $$(RISCV_OBJDUMP_FLAGS) -D $$@ > $$@.dump
	$$(RISCV_STRIP) $$@ -S --strip-unneeded
endef
# CVA6 tests are written in assembly
$(foreach extension, $(CVA6_EXTENSIONS), $(eval $(call rvtest_compile_template,$(extension),S)))
# Ara tests are written in C
$(foreach extension, $(ARA_EXTENSIONS), $(eval $(call rvtest_compile_template_c,$(extension),c)))

# Run Spike tests
.PHONY: riscv_tests_spike
riscv_tests_spike: patch-spike-crt0
	# Compile the tests
	PATH=$(GCC_INSTALL_DIR)/bin:$(LLVM_INSTALL_DIR)/bin:${PATH} ARA_DEFINES="$(DEFINES)" make -j4 -C riscv-tests/isa
	# Run the tests
	PATH=$(ISA_SIM_INSTALL_DIR)/bin:${PATH} make -C riscv-tests/isa run

# Format the sourcecode
.PHONY: format
format:
	$(LLVM_INSTALL_DIR)/bin/clang-format -style=file -i $$(find . | grep -E "\.[h,c,cpp]$$" | grep -v riscv-tests)
	$(LLVM_INSTALL_DIR)/bin/clang-format -style=file -i $$(find riscv-tests/isa/rv64uv | grep -E "\.[h,c,cpp]$$")

# Run benchmarks on Spike
define run_benchmark_spike
spike-run-$1: bin/$1.spike
	mkdir -p spike_runs
	@echo
	@echo "Simulating $1 with SPIKE:"
	@echo
	$(RISCV_SIM) $(RISCV_SIM_OPT) $$< | tee spike_runs/$$@
endef
$(foreach app,$(APPS),$(eval $(call run_benchmark_spike,$(app))))

# Clean Spike simulation
.PHONY: riscv_tests_spike_clean
riscv_tests_spike_clean:
	make -C riscv-tests/isa clean

.PHONY: benchmarks_clean
benchmarks_clean:
	cd $(APPS_DIR)/benchmarks && \
	rm -vf *.S.* *.c.*        && \
	rm -vf data/*.S.*         && \
	rm -vf kernel/*.c.*

.PHONY: clean
clean: riscv_tests_spike_clean benchmarks_clean
	rm -vf $(BINARIES)
	rm -vf $(CVA6_BINARIES)
	rm -vf $(ARA_BINARIES)
	rm -vf $(addsuffix .dump,$(BINARIES))
	rm -vf $(addsuffix .dump,$(CVA6_BINARIES))
	rm -vf $(addsuffix .dump,$(ARA_BINARIES))
	rm -vf $(addsuffix /main.c.o,$(APPS))
	rm -vf $(RUNTIME_GCC)
	rm -vf $(RUNTIME_LLVM)
	rm -vf $(RUNTIME_SPIKE)
	for app in $(APPS); do cd $(APPS_DIR)/$${app} && rm -f $$(find . -name "*.c.o*" -o -name "*.S.o*") && cd ..; done

.INTERMEDIATE: $(addsuffix /main.c.o,$(APPS))


################################################################################
# NMSIS
################################################################################

NMSIS_ROOT_DIR := $(APPS_DIR)/third-party/NMSIS/NMSIS
NMSIS_APPS_DIR := $(NMSIS_ROOT_DIR)/DSP/Examples/RISCV
NMSIS_DSP_SRCS_DIR := $(shell \
    if [ -d "$(NMSIS_ROOT_DIR)/DSP/Source" ]; then \
        find "$(NMSIS_ROOT_DIR)/DSP/Source" -maxdepth 1 -type d ! -name "." ! -name ".*" \
        | while read dir; do \
            if [ -d "$$dir" ] && [ -n "$$(find "$$dir" -name "*.c" -print -quit 2>/dev/null)" ]; then \
                echo "$$dir"; \
            fi; \
        done; \
    fi)
NMSIS_DSP_SRCS := $(foreach dir, $(NMSIS_DSP_SRCS_DIR), $(wildcard $(dir)/*.c)) 
NMSIS_DSP_SRCS_BINARIES := $(addsuffix .o.nmsis, $(NMSIS_DSP_SRCS))
NMSIS_INCLUDE           := -Iinclude -I$(NMSIS_ROOT_DIR)/DSP/Include -I$(NMSIS_ROOT_DIR)/DSP/PrivateInclude -I$(NMSIS_ROOT_DIR)/Core/Include
NMSIS_APPS              := $(patsubst $(NMSIS_APPS_DIR)/%/,%,$(wildcard $(NMSIS_APPS_DIR)/*/))


.PHONY: flags nmsis_all nmsis_asm gen_dsp_lib clean_dsp_lib gen_ccflags

disp:
	echo $(NMSIS_DSP_SRCS_BINARIES) 

gen_ccflags: 
	echo $(RISCV_CCFLAGS) > $(APPS_DIR)/riscv_ccflags 

gen_dsp_lib: $(NMSIS_DSP_SRCS_BINARIES) 
	cd $(NMSIS_ROOT_DIR)/DSP; find ./ -name "*.o.nmsis" | xargs $(RISCV_AR) rcs $(APPS_DIR)/library/libnmsis_dsp.a
	$(RISCV_STRIP) -g $(APPS_DIR)/library/libnmsis_dsp.a

clean_dsp_lib:
	cd $(NMSIS_ROOT_DIR)/DSP; find ./ -name "*.o.nmsis" | xargs rm 
	rm $(APPS_DIR)/library/libnmsis_dsp.a

%.S.o.nmsis: %.S
	$(RISCV_CC) $(NMSIS_INCLUDE) $(RISCV_CCFLAGS) -c $< -o $@

%.c.o.nmsis: %.c
	-$(RISCV_CC) $(NMSIS_INCLUDE) $(RISCV_CCFLAGS) -c $< -o $@

%.o.nmsis.dump: %.o.nmsis
	$(RISCV_OBJDUMP) $(RISCV_OBJDUMP_FLAGS) -D $< > $@

nmsis_asm: $(addsuffix .o.nmsis.dump, $(shell find -L $(NMSIS_APPS_DIR)/$(1) -name "*.c" -o -name "*.cpp" -o -name "*.S")) $(addsuffix .dump, $(NMSIS_DSP_SRCS_BINARIES)) 

define dsp_app_compile_template
bin/nmsis-$1: $(addsuffix .o.nmsis, $(shell find -L $(NMSIS_APPS_DIR)/$(1)/ -name "*.c" -o -name "*.cpp" -o -name "*.S")) $(RUNTIME_LLVM) linker_script nmsis_asm gen_dsp_lib
	mkdir -p bin/
	$$(RISCV_CC) $(NMSIS_INCLUDE) $(RISCV_CCFLAGS) -o $$@ $$(addsuffix .o.nmsis, $$(shell find -L $(NMSIS_APPS_DIR)/$(1) -name "*.c" -o -name "*.cpp" -o -name "*.S")) $$(RUNTIME_LLVM) -L$$(APPS_DIR)/library/ -lnmsis_dsp $$(RISCV_LDFLAGS) 
	$$(RISCV_OBJDUMP) $$(RISCV_OBJDUMP_FLAGS) -D $$@ > bin/nmsis-$(1).dump
	$$(RISCV_NM) -n $$@ >> bin/nmsis-$(1).dump
	$$(RISCV_STRIP) $$@ -S --strip-unneeded
	$$(RISCV_CC) $(RISCV_CCFLAGS) -dM -E - < /dev/null > compiler_macros.h
endef
$(foreach app,$(NMSIS_APPS),$(eval $(call dsp_app_compile_template,$(app))))

$(NMSIS_APPS): % : bin/nmsis-% $(APPS_DIR)/Makefile $(shell find common -type f)

NMSIS_BINARIES := $(filter-out bin/benchmarks bin/rivec-bmarks% bin/_%, $(addprefix bin/nmsis-,$(NMSIS_APPS)))
nmsis_all: $(NMSIS_BINARIES) 
