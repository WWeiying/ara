TESTMODULE = brook
CURRENT_DIR := $(shell pwd)
AVL = 1024

COMPILER = llvm
PLATFORM = spike

GCC_PATH = /home/wangwy/brook/toolchains/Xuantie-900-gcc-elf-newlib-x86_64-V3.0.1/bin/
LLVM_PATH = /home/wangwy/brook/toolchains/Xuantie-900-llvm-elf-newlib-x86_64-V2.0.1/bin
SPIKE = /home/wangwy/brook/toolchains/spike1.0/bin/spike
SPIKE_FLAGS = --isa=rv64gcv_zvl2048b -d
SPIKE_C910 = /home/wangwy/brook/toolchains/spike_openc910/bin/spike
SPIKE_C910_FLAGS = --isa=rv64gc -d

ifeq ($(COMPILER), gcc)
  CC      = $(GCC_PATH)/riscv64-unknown-elf-gcc
  AS      = $(GCC_PATH)/riscv64-unknown-elf-as
  LINK    = $(GCC_PATH)/riscv64-unknown-elf-ld
  OBJDUMP = $(GCC_PATH)/riscv64-unknown-elf-objdump
  OBJCOPY = $(GCC_PATH)/riscv64-unknown-elf-objcopy
  LLVM_OPTION ?=
else
  CC      = $(LLVM_PATH)/clang
  AS      = $(LLVM_PATH)/llvm-as
  LINK    = $(LLVM_PATH)/lld
  OBJDUMP = $(LLVM_PATH)/llvm-objdump
  OBJCOPY = $(GCC_PATH)/riscv64-unknown-elf-objcopy
  LLVM_OPTION ?= --target=riscv64-unknown-elf
endif

RISCV_ARCH = rv64gcv_zvl256b
RISCV_ABI  = lp64d

ifeq ($(PLATFORM),spike)
  CCFLAGS = -v --target=riscv64-unknown-elf -march=$(RISCV_ARCH) -mabi=$(RISCV_ABI) -O3 -menable-experimental-extensions -mcmodel=medany -DPREALLOCATE=1 -DSPIKE=1 -Wall -fno-builtin -fno-builtin-memset -fno-common

  LDFLAGS = -fuse-ld=$(GCC_PATH)/riscv64-unknown-elf-ld -Wl,-Map=run/compfiles/main_map -Trun/scripts/test.ld -nostartfiles -nostdlib
  OBJFLAGS = --mattr=+v
else
endif

SPIKE_C_SRCS = $(wildcard run/apps/*.c)
CODE_ELFS = $(patsubst run/apps/%.c, run/bin/%.elf, $(SPIKE_C_SRCS))
SPIKE_LOGS = $(patsubst run/apps/%.c, run/log/%_spike_run.log, $(SPIKE_C_SRCS))

$(CODE_ELFS): run/bin/%.elf: run/apps/%.c run/apps/common/crt.S run/apps/data.S
	$(CC) $(CCFLAGS) $^ -o $@ $(LDFLAGS) -D TOTAL_ELEMENTS=$(AVL) 2>&1 | tee run/log/$*_compile.log
	$(OBJDUMP) $(OBJFLAGS) -d $@ >run/compfiles/$*.asm | tee -a run/log/$*_compile.log
	$(OBJDUMP) -s -j .vec_data $@ >> run/compfiles/$*.asm | tee -a run/log/$*_compile.log
	$(OBJCOPY) -O binary -j .vec_data $@ run/bin/vector_data.bin | tee -a run/log/$*_compile.log
	hexdump -v -e '64/1 "%02x" "\n"' run/bin/vector_data.bin >hardware/include/vector_data.hex | tee -a run/log/$*_compile.log
	cd hardware/include/ && split -d -l 256 vector_data.hex vector_data_bank_
	 
$(SPIKE_LOGS): run/log/%_spike_run.log: run/bin/%.elf
	echo "run" | $(SPIKE) $(SPIKE_FLAGS) $< 2>$@ 1>/dev/null
	./run/scripts/vinst_env_extract.py

.PHONY: gen_data code_compile spike_run clean dirs disasm 
gen_data:
	./run/scripts/gen_data.py --src1-size $(AVL) --src2-size $(AVL) --dest-size $(AVL) -o ./run/apps/data.S
code_compile: clean dirs gen_data $(CODE_ELFS)
spike_run: dirs $(SPIKE_LOGS) 
disasm: $(ELF_FILE)
	$(OBJDUMP) $(OBJFLAGS) -d $(ELF_FILE) >$(dir $(ELF_FILE))$(basename $(notdir $(ELF_FILE))).asm

dirs:
	mkdir -p run/{apps,bin,obj,compfiles,log}

clean:
	rm -rf run/{bin,obj,compfiles,log}

RISCV_ARCH_C910 = rv64gc
RISCV_ABI_C910  = lp64d

CCFLAGS_C910 = --target=riscv64-unknown-elf -march=$(RISCV_ARCH_C910) -mabi=$(RISCV_ABI_C910) -O3 -menable-experimental-extensions -mcmodel=medany -DPREALLOCATE=1 -DSPIKE=1 -Wall
LDFLAGS_C910 = -nostdlib -Trun/apps/common/test.ld
OBJFLAGS_C910 = 

SPIKE_C910_C_SRCS = $(wildcard run/c910/apps/*.c)
SPIKE_C910_ELF_OBJS = $(patsubst run/c910/apps/%.c, run/c910/bin/%.elf, $(SPIKE_C910_C_SRCS))
SPIKE_C910_LOGS = $(patsubst run/c910/apps/%.c, run/c910/log/%_log, $(SPIKE_C910_C_SRCS))

$(SPIKE_C910_ELF_OBJS): run/c910/bin/%.elf: run/c910/apps/%.c run/c910/apps/common/crt.S | dirs_c910
	$(CC) $(CCFLAGS_C910) $^ -o $@ $(LDFLAGS_C910) -DSPIKE
	$(OBJDUMP) $(OBJFLAGS_C910) -d $@ >run/c910/compfiles/$*.asm 
	 
$(SPIKE_C910_LOGS): run/c910/log/%_log: run/c910/bin/%.elf | dirs_c910
	 echo "run" | $(SPIKE_C910) $(SPIKE_C910_FLAGS) $< 2>$@ 1>/dev/null

.PHONY: spike_compile_c910 spike_run_c910 clean_c910 dirs_c910
spike_compile_c910: $(SPIKE_C910_ELF_OBJS) 
spike_run_c910: clean_c910 $(SPIKE_C910_LOGS) 

dirs_c910:
	mkdir -p run/c910/{apps,bin,obj,compfiles,log}

clean_c910:
	rm -rf run/c910/{bin,obj,compfiles,log}

.PHONY: compile sim verdi cleansim lint trace
TIMESCALE := -timescale=1ns/100fs
SIMULATOR_OPT := -full64 -sverilog -Mupdate -j64 -lca -kdb -debug_access +nospecify +notimingchecks +lint=TFIPC-L  +vpi +lint=PCWM +error+30
SIMULATOR_DEF := +define+SIMULATION +define+no_warning +define+TSMC_NO_WARNING
SIMULATOR_LOG := -l comp.vcs.log
SIMULATOR_POWER_OPT := 
SIMV_POWER_OPT      := +fsdb+power +fsdb+all +PRELOAD=/home/wangwy/openproject/ara/apps/bin/gemv
SIM_DUMP :=
SIM_FILELIST := -f /home/wangwy/openproject/ara/hardware/ara.f /home/wangwy/openproject/ara/hardware/build/work-dpi/elfloader.o
SIM_TIME := #+vcs+finish+10000ns

compile:
	@mkdir -p ./sim
	@cd ./sim && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(SIMULATOR_DEF) $(SIM_FILELIST) $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT)

sim: compile
	@cd ./sim && ./simv -l run.vcs.log $(SIMV_POWER_OPT)

cleansim:
	@cd ./sim && rm -rf *

verdi:
	@cd ./sim && verdi $(SIMULATOR_DEF) -sv $(SIM_FILELIST) -ssy -ssv -top ara_tb -ssf ara_tb.fsdb &

lint:
	cd ./hardware/lint && rm -rf brook_* *.log reports spyglass-1 brook
	cd ./hardware/lint && ./run.sh

trace:
	@./run/scripts/compare_traces.py -g ./run/log/ref_trace.log -d ./run/log/dut_trace.log -o ./run/log/diff_report
	@head -n 20 ./run/log/diff_report

