SHELL := /bin/bash
.DEFAULT_GOAL := plan

PYTHON ?= python3
PYTHONPATH := $(CURDIR)
VERIFY := $(PYTHON) $(CURDIR)/verify.py
OUT ?= $(CURDIR)/out

.PHONY: plan list doctor doctor-no-vcs unit static preflight \
        smoke-dry-run signoff-dry-run linux-help fpga-help uvm-smoke \
        real-ara-contract-compile real-ara-contract-smoke \
        real-ara-contract-run real-ara-contract-check real-ara-contract-app contract-selftest \
        linux-userspace-build linux-userspace-qemu qbs-read-contract fpga-source-check
.PHONY: cva6-contract cva6-load-contract linux-prereq
.PHONY: plic-prepare plic-check plic-contract mmio-prepare mmio-contract
.PHONY: fpga-soc-candidate fpga-soc-smoke
.PHONY: real-ara-uvm-smoke real-ara-uvm-compile real-ara-uvm-app real-ara-uvm-run real-ara-uvm-check
.PHONY: rtl-quick-check fast-rtl-gate fast-rtl-rvv fast-rtl-qbs fast-rtl-akv
.PHONY: host-quick-check

VCS ?= vcs
UVM_OUT ?= $(CURDIR)/out/uvm-cvxif-smoke
REAL_CONTRACT_OUT ?= $(CURDIR)/out/real-ara-contract-compile
REAL_CONTRACT_TESTCASE ?= rv64uv-ara-vfredmax_boundary
REAL_CONTRACT_APP ?= $(CURDIR)/../apps/bin/$(REAL_CONTRACT_TESTCASE)
REAL_CONTRACT_LOG ?= $(REAL_CONTRACT_OUT)/sim/$(REAL_CONTRACT_TESTCASE).log
REAL_UVM_OUT ?= $(OUT)/real-ara-uvm
REAL_UVM_TESTCASE ?= rv64uv-ara-vfredmax_boundary
REAL_UVM_APP ?= $(CURDIR)/../apps/bin/$(REAL_UVM_TESTCASE)
REAL_UVM_WORK ?= $(REAL_UVM_OUT)/tests/$(REAL_UVM_TESTCASE)/work
REAL_UVM_LOG ?= $(REAL_UVM_WORK)/run.vcs.log
REAL_UVM_INPUT ?= $(REAL_UVM_WORK)/input.elf
REAL_UVM_TIMEOUT ?= 300
REAL_UVM_TRACE_LIMIT ?= 100000
REAL_UVM_AXI_DELAY ?= 0
REAL_UVM_SIM_L2_MB ?= 1
REAL_UVM_QBS ?= 0
REAL_UVM_AKV_V2 ?= 0
FAST_GATE_SIMV ?=
FAST_GATE_OUT ?= $(OUT)/fast-rtl-gate
FAST_GATE_TIMEOUT ?= 300
FAST_GATE_AKV_ELF ?= $(CURDIR)/../apps/bin/qbs_akv_handoff_smoke
CAPTURED_QBS_MANIFEST ?= $(CURDIR)/qbs/captured_real_cases_20260923.json
CAPTURED_QBS_OUT ?= $(OUT)/qbs-captured-quick-check
CONTRACT_UNIT_OUT ?= $(CURDIR)/out/contract-selftest
LINUX_PAYLOAD_OUT ?= $(OUT)/linux-userspace/payload
LINUX_QEMU_OUT ?= $(OUT)/linux-userspace/qemu
QBS_READ_OUT ?= $(OUT)/qbs-read-contract
FPGA_SOURCE_REPORT ?= $(OUT)/fpga-source-check.json
CVA6_CONTRACT_OUT ?= $(OUT)/cva6-contract
CVA6_LOAD_OUT ?= $(OUT)/cva6-load-contract
CVA6_LOAD_PACKAGE ?= $(OUT)/fpga-soc-candidate-20260922-04/package
LINUX_PREREQ_OUT ?= $(OUT)/linux-prereq
PLIC_PYTHON ?= $(CURDIR)/tools/plic-venv/bin/python
PLIC_ROOTS ?=
PLIC_OUT ?= $(OUT)/plic-candidate
PLIC_DIR ?= $(PLIC_OUT)/rv_plic
PLIC_RUN_OUT ?= $(OUT)/plic-contract
PLIC_DTS ?= $(PLIC_OUT)/ara_vcu118.dts.in
PLIC_CHECK_REPORT ?= $(PLIC_OUT)/static-check.json
PLIC_FIX_CONTRACT ?= 0
MMIO_OUT ?= $(OUT)/mmio-candidate
MMIO_DIR ?=
MMIO_RUN_OUT ?= $(OUT)/mmio-contract
SOC_CANDIDATE_OUT ?= $(OUT)/fpga-soc-candidate
SOC_PYTHON ?= $(CURDIR)/tools/soc-venv/bin/python
SOC_SMOKE_PACKAGE ?= $(OUT)/fpga-soc-candidate-20260922-04/package
SOC_SMOKE_OUT ?= $(OUT)/fpga-soc-smoke

fpga-soc-smoke:
	PYTHONPATH=$(PYTHONPATH) $(SOC_PYTHON) -B $(CURDIR)/fpga/run_soc_smoke.py \
		--package "$(SOC_SMOKE_PACKAGE)" --output "$(SOC_SMOKE_OUT)" --vcs "$(VCS)"

# Short diagnostic gate on one already-compiled, feature-complete real-DUT image.
# Invoke with -j3; each case has its own output and a bounded wall-clock timeout.
# Passing these three cases is not a substitute for random or Linux signoff.
host-quick-check:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest -q \
		$(CURDIR)/qbs/test_capture_real_format.py \
		$(CURDIR)/qbs/test_run_captured_real_cases.py \
		$(CURDIR)/qbs/test_run_real_format_rtl.py
	$(MAKE) -C $(CURDIR)/qbs real-check
	@test ! -e "$(CAPTURED_QBS_OUT)" || { echo 'CAPTURED_QBS_OUT must be new: $(CAPTURED_QBS_OUT)' >&2; exit 2; }
	$(MAKE) -C $(CURDIR)/qbs qbs_real_test
	$(PYTHON) $(CURDIR)/qbs/run_captured_real_cases.py \
		--manifest "$(CAPTURED_QBS_MANIFEST)" \
		--binary "$(CURDIR)/qbs/qbs_real_test" \
		--output "$(CAPTURED_QBS_OUT)"

rtl-quick-check:
	@test -n "$(FAST_GATE_SIMV)" || { echo 'set FAST_GATE_SIMV to the current verified VCS simv' >&2; exit 2; }
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest -q \
		$(CURDIR)/tests/test_uvm_dut.py \
		$(CURDIR)/tests/test_runner.py \
		$(CURDIR)/tests/test_plan.py
	$(MAKE) --no-print-directory -j3 fast-rtl-gate

fast-rtl-gate: fast-rtl-rvv fast-rtl-qbs fast-rtl-akv
	@echo "fast RTL gate passed: $(FAST_GATE_OUT)"

fast-rtl-rvv:
	@test -n "$(FAST_GATE_SIMV)" || { echo 'set FAST_GATE_SIMV to the verified VCS simv' >&2; exit 2; }
	@ARA_VCS_TIMEOUT_SECONDS=$(FAST_GATE_TIMEOUT) $(CURDIR)/uvm/run_real_dut_case.sh \
		"$(FAST_GATE_SIMV)" "$(CURDIR)/../apps/bin/rv64uv-ara-vfredmax_boundary" \
		rv64uv-ara-vfredmax_boundary "$(FAST_GATE_OUT)/rvv"

fast-rtl-qbs:
	@test -n "$(FAST_GATE_SIMV)" || { echo 'set FAST_GATE_SIMV to the verified VCS simv' >&2; exit 2; }
	@ARA_VCS_TIMEOUT_SECONDS=$(FAST_GATE_TIMEOUT) $(CURDIR)/uvm/run_real_dut_case.sh \
		"$(FAST_GATE_SIMV)" "$(CURDIR)/../apps/bin/llama_qwen25_decode_attn_q_qbs_direct2" \
		decode_attn_q_qbs_direct2 "$(FAST_GATE_OUT)/qbs"

fast-rtl-akv:
	@test -n "$(FAST_GATE_SIMV)" || { echo 'set FAST_GATE_SIMV to the verified VCS simv' >&2; exit 2; }
	@ARA_VCS_TIMEOUT_SECONDS=$(FAST_GATE_TIMEOUT) $(CURDIR)/uvm/run_real_dut_case.sh \
		"$(FAST_GATE_SIMV)" "$(FAST_GATE_AKV_ELF)" \
		qbs_akv_handoff_smoke "$(FAST_GATE_OUT)/akv"

fpga-soc-candidate:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -B $(CURDIR)/fpga/prepare_soc_candidate.py \
		--output "$(SOC_CANDIDATE_OUT)"

plic-prepare:
	$(if $(PLIC_ROOTS),,$(error PLIC_ROOTS must point to the pinned FPGA roots.json))
	$(if $(filter $(PLIC_FIX_CONTRACT),0 1),,$(error PLIC_FIX_CONTRACT must be 0 or 1))
	$(PLIC_PYTHON) -B $(CURDIR)/fpga/prepare_plic.py \
		--roots "$(PLIC_ROOTS)" --output "$(PLIC_OUT)" \
		$(if $(filter 1,$(PLIC_FIX_CONTRACT)),--fix-contract,)

plic-contract:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) $(CURDIR)/run_plic_contract.py \
		--plic-dir "$(PLIC_DIR)" --vcs "$(VCS)" --output "$(PLIC_RUN_OUT)" \
		$(if $(MMIO_DIR),--mmio-dir "$(MMIO_DIR)",)

mmio-prepare:
	$(PYTHON) -B $(CURDIR)/fpga/prepare_mmio.py --output "$(MMIO_OUT)"

mmio-contract:
	$(if $(MMIO_DIR),,$(error MMIO_DIR must select the fixed overrides or the original export RTL explicitly))
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) $(CURDIR)/run_mmio_read_contract.py \
		--vcs "$(VCS)" --output "$(MMIO_RUN_OUT)" --mmio-dir "$(MMIO_DIR)"

plic-check:
	$(PLIC_PYTHON) -B $(CURDIR)/fpga/check_plic.py --plic-dir "$(PLIC_DIR)" \
		--dts "$(PLIC_DTS)" --output "$(PLIC_CHECK_REPORT)"

cva6-contract:
	$(PYTHON) $(CURDIR)/cva6/run_contract.py --output $(CVA6_CONTRACT_OUT)

cva6-load-contract:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -B $(CURDIR)/cva6/run_load_contract.py \
		--package "$(CVA6_LOAD_PACKAGE)" --output "$(CVA6_LOAD_OUT)"

linux-prereq:
	PYTHONPATH=$(PYTHONPATH) $(VERIFY) run linux-prereq --contract-monitor --commit-trace \
		--output $(LINUX_PREREQ_OUT)

fpga-source-check:
	$(PYTHON) $(CURDIR)/fpga/check_sources.py --output $(FPGA_SOURCE_REPORT)

qbs-read-contract:
	$(PYTHON) $(CURDIR)/run_qbs_read_contract.py --vcs $(VCS) --output $(QBS_READ_OUT)

linux-userspace-build:
	$(PYTHON) $(CURDIR)/linux/build_userspace.py --output $(LINUX_PAYLOAD_OUT)

linux-userspace-qemu:
	$(PYTHON) $(CURDIR)/linux/run_userspace_qemu.py \
		--payload $(LINUX_PAYLOAD_OUT) --output $(LINUX_QEMU_OUT)

plan:
	PYTHONPATH=$(PYTHONPATH) $(VERIFY) plan

list:
	PYTHONPATH=$(PYTHONPATH) $(VERIFY) list --suites

doctor:
	PYTHONPATH=$(PYTHONPATH) $(VERIFY) doctor

doctor-no-vcs:
	PYTHONPATH=$(PYTHONPATH) $(VERIFY) doctor --no-vcs

unit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest -q $(CURDIR)/tests

static: plan doctor-no-vcs unit

preflight: static
	@echo "verification preflight passed; no simulation was started"

smoke-dry-run:
	PYTHONPATH=$(PYTHONPATH) $(VERIFY) run smoke --dry-run --output $(OUT)/dry_run_smoke

signoff-dry-run:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) $(CURDIR)/run_signoff.py \
		--stage preflight --output $(OUT)/dry_run_signoff --dry-run

linux-help:
	$(PYTHON) $(CURDIR)/linux/check_boot.py --help

fpga-help:
	$(PYTHON) $(CURDIR)/fpga/check_run.py --help

uvm-smoke:
	@mkdir -p $(UVM_OUT)/csrc
	$(VCS) -full64 -sverilog -timescale=1ns/1ps -ntb_opts uvm-1.2 \
		-Mdir=$(UVM_OUT)/csrc -o $(UVM_OUT)/simv \
		$(CURDIR)/uvm/ara_cvxif_if.sv \
		$(CURDIR)/uvm/ara_cvxif_uvm_pkg.sv \
		$(CURDIR)/uvm/ara_cvxif_smoke_tb.sv \
		-l $(UVM_OUT)/compile.log
	$(UVM_OUT)/simv +UVM_TESTNAME=ara_cvxif_smoke_test \
		-l $(UVM_OUT)/run.log
	@grep -q 'UVM CVXIF contract smoke PASS' $(UVM_OUT)/run.log
	@grep -q 'observed requests=6 responses=5 aborted=1 reused=1 immediate=1' $(UVM_OUT)/run.log
	@grep -q 'allocations=3 completions=2 aborted=1 max_live=1' $(UVM_OUT)/run.log
	@grep -q 'ar=6 r_beats=7 completed=5 aborted=1 pending=0 max_pending=2' $(UVM_OUT)/run.log
	@grep -q 'aw=7 w_beats=7 w_bursts=6 matched=6 b=6 aborted=1 pending=0 max_pending=2' $(UVM_OUT)/run.log
	@grep -q 'ar=0 r=0 aw=2 w=0 b=0 hold_checks=2' $(UVM_OUT)/run.log
	@grep -q 'UVM_ERROR :    0' $(UVM_OUT)/run.log
	@grep -q 'UVM_FATAL :    0' $(UVM_OUT)/run.log
	@for channel in AR R AW W B; do \
		case "$$channel" in \
			AW) option=+AXI_INJECT_AW_HOLD ;; \
			*) option=+AXI_INJECT_$${channel}_HOLD ;; \
		esac; \
		$(UVM_OUT)/simv -no_save +UVM_TESTNAME=ara_cvxif_smoke_test "$$option" \
			-l $(UVM_OUT)/hold_$${channel}.log >/dev/null || exit 1; \
		grep -q "\[AXI/HOLD\] $$channel payload or valid changed" \
			$(UVM_OUT)/hold_$${channel}.log || exit 1; \
		grep -q 'UVM_ERROR :    1' $(UVM_OUT)/hold_$${channel}.log || exit 1; \
		grep -q 'UVM_FATAL :    0' $(UVM_OUT)/hold_$${channel}.log || exit 1; \
	done

real-ara-uvm-compile:
	@test ! -e $(REAL_UVM_OUT) || { echo "output already exists: $(REAL_UVM_OUT)" >&2; exit 2; }
	@mkdir -p $(REAL_UVM_OUT)
	$(MAKE) -C $(CURDIR)/../hardware compile \
		buildpath=$(REAL_UVM_OUT)/hardware-build \
		sim_dir=$(REAL_UVM_OUT)/sim \
		sim_l2_mb=$(REAL_UVM_SIM_L2_MB) \
		qbs=$(REAL_UVM_QBS) akv_v2=$(REAL_UVM_AKV_V2) \
		verify_uvm_cvxif=1 verify_axi_delay=$(REAL_UVM_AXI_DELAY) \
		fail_on_assert=1 no_fsdb=1 verify_source_manifest=1 \
		verify_extra_sources='$(CURDIR)/uvm/ara_cvxif_if.sv $(CURDIR)/uvm/ara_cvxif_uvm_pkg.sv $(CURDIR)/uvm/ara_acc_contract_monitor.sv $(CURDIR)/uvm/ara_cvxif_dut_bind.sv'

real-ara-uvm-app:
	$(MAKE) -C $(CURDIR)/../apps bin/$(REAL_UVM_TESTCASE)

real-ara-uvm-smoke: real-ara-uvm-compile real-ara-uvm-app
	$(MAKE) real-ara-uvm-run REAL_UVM_OUT=$(REAL_UVM_OUT) \
		REAL_UVM_TESTCASE=$(REAL_UVM_TESTCASE) REAL_UVM_APP=$(REAL_UVM_APP)

real-ara-uvm-run:
	@test -x $(REAL_UVM_OUT)/sim/simv
	@test -f $(REAL_UVM_APP)
	@test ! -e $(REAL_UVM_WORK) || { echo "case output already exists: $(REAL_UVM_WORK)" >&2; exit 2; }
	@mkdir -p $(REAL_UVM_WORK)
	@cp -p $(REAL_UVM_APP) $(REAL_UVM_INPUT)
	@cd $(REAL_UVM_WORK) && timeout --foreground $(REAL_UVM_TIMEOUT) $(REAL_UVM_OUT)/sim/simv -no_save \
		-l $(REAL_UVM_LOG) \
		+PRELOAD=$(REAL_UVM_INPUT) +TESTCASE=$(REAL_UVM_TESTCASE) +NO_FSDB \
		+ARA_CONTRACT_TRACE_LIMIT=$(REAL_UVM_TRACE_LIMIT) \
		+ARA_UVM_TRACE_LIMIT=$(REAL_UVM_TRACE_LIMIT) \
		+VECTOR_TRACE=$(REAL_UVM_WORK)/vector_trace.csv
	$(MAKE) real-ara-uvm-check REAL_UVM_OUT=$(REAL_UVM_OUT) \
		REAL_UVM_TESTCASE=$(REAL_UVM_TESTCASE) REAL_UVM_INPUT=$(REAL_UVM_INPUT)

real-ara-uvm-check:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m ara_verify.uvm_dut \
		--require-events --require-backend --require-axi \
		$(if $(filter 1,$(REAL_UVM_REQUIRE_WRITE)),--require-axi-write,) \
		--vector-trace $(REAL_UVM_WORK)/vector_trace.csv \
		--log $(REAL_UVM_LOG) --simv $(REAL_UVM_OUT)/sim/simv \
		--elf $(REAL_UVM_INPUT) --output $(REAL_UVM_OUT)/tests/$(REAL_UVM_TESTCASE)/uvm_result.json

# Compile the normal ara_tb/ara_system DUT with the real-boundary monitor.
# This is intentionally separate from the ordinary hardware compile and uses
# an isolated build/output tree, so adding the monitor cannot affect normal
# simulation or synthesis targets.
real-ara-contract-compile:
	@mkdir -p $(REAL_CONTRACT_OUT)
	$(MAKE) -C $(CURDIR)/../hardware compile \
		buildpath=$(REAL_CONTRACT_OUT)/hardware-build \
		sim_dir=$(REAL_CONTRACT_OUT)/sim \
		verify_extra_sources=$(CURDIR)/uvm/ara_acc_contract_monitor.sv

# Run one directed ELF through the real ara_system-bound monitor.  This is a
# bounded integration smoke, not a replacement for the full differential
# campaign; it proves the monitor observes non-zero traffic in the current DUT.
real-ara-contract-app:
	$(MAKE) -C $(CURDIR)/../apps bin/$(REAL_CONTRACT_TESTCASE)

real-ara-contract-smoke: real-ara-contract-compile real-ara-contract-app
	$(MAKE) real-ara-contract-run

# Reuse the already compiled DUT for additional short tests or log checking.
real-ara-contract-run:
	@test -x $(REAL_CONTRACT_OUT)/sim/simv
	@test -f $(REAL_CONTRACT_APP)
	@cd $(REAL_CONTRACT_OUT)/sim && timeout --foreground 300 ./simv -no_save \
		-l $(REAL_CONTRACT_LOG) \
		+PRELOAD=$(REAL_CONTRACT_APP) +TESTCASE=$(REAL_CONTRACT_TESTCASE) +NO_FSDB
	$(MAKE) real-ara-contract-check

real-ara-contract-check:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m ara_verify.contract \
		$(REAL_CONTRACT_LOG)
	@echo "real Ara boundary monitor smoke passed"

contract-selftest:
	@mkdir -p $(CONTRACT_UNIT_OUT)
	$(VCS) -full64 -sverilog -timescale=1ns/1ps \
		+define+ARA_ACC_CONTRACT_STANDALONE -top ara_acc_contract_selftest \
		-Mdir=$(CONTRACT_UNIT_OUT)/csrc -o $(CONTRACT_UNIT_OUT)/simv \
		$(CURDIR)/uvm/ara_acc_contract_monitor.sv \
		$(CURDIR)/uvm/ara_acc_contract_selftest.sv -l $(CONTRACT_UNIT_OUT)/compile.log
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) $(CURDIR)/run_contract_selftest.py \
		$(CONTRACT_UNIT_OUT)/simv --output $(CONTRACT_UNIT_OUT)
