.PHONY: compile sim verdi clean lint trace
TIMESCALE := -timescale=1ns/100fs
SIMULATOR_OPT := -full64 -sverilog -Mupdate -j64 -lca -kdb -debug_access +nospecify +notimingchecks +lint=TFIPC-L  +vpi +lint=PCWM +error+30
SIMULATOR_DEF := +define+SIMULATION +define+no_warning +define+TSMC_NO_WARNING
SIMULATOR_LOG := -l comp.vcs.log
SIMULATOR_POWER_OPT := 
SIMV_POWER_OPT      := +fsdb+power +fsdb+all 
SIM_DUMP :=
SIM_FILELIST := -f /home/wangwy/openproject/ara/hardware/ara.f /home/wangwy/openproject/ara/hardware/build/work-dpi/elfloader.o
SIM_TIME := #+vcs+finish+10000ns
KERNEL := +PRELOAD=/home/wangwy/openproject/ara/apps/bin/$(kernel)

compile:
	@mkdir -p ./sim
	@cd ./sim && vcs $(SIMULATOR_OPT) -top ara_tb $(TIMESCALE) $(SIM_TIME) $(SIMULATOR_DEF) $(SIM_FILELIST) $(SIM_DUMP) $(SIMULATOR_LOG) $(SIMULATOR_POWER_OPT)

sim: compile
	@export NOVAS_FSDB_QUIET=1
	@cd ./sim && ./simv -l run.vcs.log $(SIMV_POWER_OPT) $(KERNEL)

clean:
	@cd ./sim && rm -rf *

verdi:
	@cd ./sim && verdi $(SIMULATOR_DEF) -sv $(SIM_FILELIST) -ssy -ssv -top ara_tb -ssf ara_tb.fsdb &

lint:
	cd ./hardware/lint && rm -rf brook_* *.log reports spyglass-1 brook
	cd ./hardware/lint && ./run.sh

trace:
	@./run/scripts/compare_traces.py -g ./run/log/ref_trace.log -d ./run/log/dut_trace.log -o ./run/log/diff_report
	@head -n 20 ./run/log/diff_report
