# Ara Verification Environment

The 2026-09-26 integration into `ara_dsa`, its preserved local changes and
fresh-image checks are recorded in
[`MAIN_INTEGRATION_20260926.md`](MAIN_INTEGRATION_20260926.md).

The sole active verification branch is `ara_dsa_signoff_integration`.
See [consolidation and branch ownership](CONSOLIDATION.md) for imported tests,
local environment inputs, historical evidence, and the stop-on-failure policy.
Temporary repair branches must return their fixes and tests to this branch.

## System coverage extension: Gap30

Eight self-checking actual-SoC tests in
`apps/riscv-tests/isa/rv64uv/system_gap30_*.c` share
`system_gap30_common.h`. They run privileged checks through `rvtest_init`
before the runtime enters user mode. They cover Sv39 read/write permissions,
SUM/MXR, missing A/D bits, invalid PTEs, aligned/misaligned 2 MB and 1 GB
superpages, noncanonical addresses, fenced TLB remapping, scratch/tval CSR
read/write/set/clear, FS/VS/SUM and SD state, cache traffic ordered by fences,
and actual execution of patched instructions after `FENCE.I`.

The oracle checks expected data, trap count/cause/PC/tval, rejected-store
nonmodification and restoration of the surrounding machine state. The
existing runner independently audits completion and retirement traces; these
tests are not claimed to be full Spike instruction-by-instruction comparisons.
MMU data tests use MPRV with effective S privilege, not a complete Linux boot
or S/U instruction-fetch permission test. External IRQ/debug wiring and PMP
are not changed to obtain coverage.

`verification/coverage/run_system_gap30_20260929.py` extends the completed
600-PASS campaign on the same VCS image, using eight workers and separate
artifacts. Only independently accepted PASS VDBs enter the correctness
coverage report; failures remain visible. Existing 600-case evidence is
reused, not rerun or overwritten. Shared test headers are explicitly pinned.
Outputs are under `verification/out/system-gap30-20260929-01/`; compare
the new PASS-only report against the original 600-case report before claiming
coverage gains. A build or newly started simulation is not a PASS result.

For an isolated worktree, initialize the external build inputs explicitly:

```bash
bash verification/setup_worktree.sh
```

The script links only the external toolchain/application tree, installs the
locked Bender version, and clones the locked riscv-dv and RTL dependencies into
clean detached checkouts. It does not copy simulation output or source changes
from another worktree. The resulting `verification/worktree_inputs.json` records
the source and target revisions.

The requirement-driven plan is in `verification/VERIFICATION_PLAN.md` and
`verification/verification_plan.json`:

```bash
PYTHONPATH=verification python3 verification/verify.py plan
```

The current no-FPGA RTL/UVM/code-coverage/Linux signoff plan, including
bounded Linux diagnostics and explicit evidence gaps, is in
[`VCS_SIGNOFF_PLAN.md`](VCS_SIGNOFF_PLAN.md).

For fast feedback after an RTL change, compile the real-DUT UVM image once.
Run focused host checks first, then three bounded directed cases concurrently on
that same image:

```bash
make -C verification rtl-quick-check \
  FAST_GATE_SIMV=/absolute/path/to/verified/sim/simv \
  FAST_GATE_OUT=/absolute/path/to/new/fast-gate-run
```

The cases cover ordinary RVV reduction, QBS, and QBS/AKV handoff. Each has a
300-second default limit (`FAST_GATE_TIMEOUT`), separate logs and input hashes;
the output directory must be new. Use an image compiled from the RTL revision
being checked. This is an early regression filter, not random coverage or Linux
signoff. Run the long tests only after the relevant short gate passes, and keep
Linux boot to a frozen SoC candidate rather than every small RTL edit.
The quick gate does not rebuild RTL: use a simulator compiled from the current
RTL and a fresh output directory for each run. A failing focused host check
prevents the VCS runs from starting; run `make -C verification unit` for the
full framework suite before freezing a candidate. For a focused Linux boot
diagnostic, reuse the verified compiled SoC image and set an explicit cycle
milestone or minimum
cycle target; reaching a milestone is diagnostic evidence, never Linux PASS.

Short subsystem and deployment-source checks have separate evidence scopes:

```bash
make -C verification qbs-read-contract QBS_READ_OUT=/absolute/path/to/new-reader-run
make -C verification fpga-source-check FPGA_SOURCE_REPORT=/absolute/path/to/new-report.json
```

The reader check runs actual VCS RTL with delayed and same-cycle behavioral MMU
responses, including nonidentity page mappings and fault drain/reuse. See
`qbs/READ_ENGINE_VERIFICATION.md` for the hypotheses and cycle probes. The FPGA
check distinguishes package integrity from correspondence to live source;
matching package hashes alone cannot establish that a bug fix is deployed.
Neither check establishes Linux/board or full-model correctness.

Actual-SoC prerequisites are registered as `linux-prereq` (CSR/vector/FP state),
`sv39-prereq` (S-mode nonidentity translation, vector page-fault repair and
restart), and `trap-prereq` (24 exception/delegation cases, 448 checks).
`linux-vector-context` extracts the Linux 6.19.6 standard-RVV save/restore
sequence and executes it in S mode, with six context transitions and 6415
planned exact comparisons. Source provenance, image mismatch, probe hypotheses,
and scope are recorded in
[`cva6/linux_vector_context.md`](cva6/linux_vector_context.md).
`linux-mmu-relocate` extracts Linux `relocate_enable_mmu` and adds a directed
TLB remap. It requires both the VCS result and the independent host audit in
[`cva6/linux_mmu_relocate.md`](cva6/linux_mmu_relocate.md); the audit checks frozen
ELF bytes, high-VA retirement, actual SATP writes, delegated fault and physical
data observations rather than accepting a printed PASS alone.
Their measured scope and fixes are in
[`cva6/sv39_state_prereq.md`](cva6/sv39_state_prereq.md),
[`cva6/trap_probe_plan.md`](cva6/trap_probe_plan.md), and verification report
sections 104-106. Reviewed cross-module probes distinguish the first incorrect
payload from downstream propagation. None of these suites is an OS boot or
board signoff. The scalar-only trap test intentionally has no ACC traffic;
do not use the nonzero-traffic `--contract-monitor` gate for that test.

UVM is a reusable transaction-level methodology, not a replacement for the
ISA reference model or system-level boot tests. This repository currently uses
the same functional roles through VCS/SystemVerilog monitors, Spike differential
comparison, deterministic riscv-dv generation, and Python artifact control. A
full UVM agent layer can be added around the CVXIF/AXI interfaces without
changing the plan or evidence format; it must not be used to waive the
architectural and Linux gates.

This directory contains the staged functional verification environment for the
CVA6 plus Ara system. Functional correctness and performance regression are
kept separate: a functional test passes only when its self-checking software and
simulation checks pass.

## Stage 1: Reproducible regression

The current stage provides:

- automatic discovery of Ara applications and the existing `rv64uv` tests;
- manifest-defined suites in `suites.json`;
- one VCS compile per hardware configuration;
- isolated output directories for every test;
- deterministic run metadata and exact commands for replay;
- lock-file validation for RTL dependencies, the RVV 1.0 riscv-dv generator,
  and deterministic VCS seeds;
- timeout handling and JSON, CSV, and JUnit reports;
- environment and configuration checks, including every locked dependency and
  the required Bender version.

Run the environment check and inspect the suites:

```bash
python3 verification/verify.py deps
python3 verification/verify.py doctor
python3 verification/verify.py list --suites
python3 verification/verify.py list --suite smoke
```

Run the verification framework's own unit tests from the repository root with
the package directory on `PYTHONPATH`:

```bash
make -C verification unit
```

The target uses pytest with the required `PYTHONPATH`, collecting both unittest
classes and pytest functions. `unittest discover` alone omits function-style
tests and is not the complete preflight gate.

To inspect raw VCS VDB test records without URG, pass the compile VDB and a
test VDB to the read-only extractor:

```bash
PYTHONPATH=verification python3 -m ara_verify.vdb_raw \
  --compile-vdb /path/to/simv.vdb --test-vdb /path/to/code.vdb \
  --instance-prefix ara_tb.dut --summary-only
PYTHONPATH=verification python3 -m ara_verify.vdb_raw \
  --compile-vdb /path/to/simv.vdb --test-vdb /path/to/code.vdb \
  --instance-prefix ara_tb.dut > /tmp/ara-vdb-raw.jsonl
```

The JSONL export preserves each `instance_data` bitmap and
`instance_intervaldata` value; the last line summarizes record counts and raw
bitmap characters. The extractor checks the declared VCS release, but does not
apply shape definitions, exclusions, or URG aggregation rules. Its raw counts
are not coverage percentages or signoff evidence. Matching versions do not
prove that the two VDBs came from the same build. If extraction fails, discard
the partial JSONL; a complete export ends with a `summary` record.

`deps` reads exact Git revisions from `Bender.lock` and
`toolchain.lock.json`. The riscv-dv checkout is fixed to the RVV 1.0 update at
`a9e723ba921aee0cd2aea7999d92859f2a2f088e` and is stored below the ignored
`verification/tools/` directory. The command refuses to modify dirty checkouts
and can be previewed with `--dry-run`.

Run a smoke regression:

```bash
python3 verification/verify.py run smoke
```

Record scalar retirement plus CVXIF request/response events for later tandem
comparison:

```bash
python3 verification/verify.py run --test app:vsaxpy --commit-trace
```

Run selected points or all directed RVV tests:

```bash
python3 verification/verify.py run --test app:vsaxpy --test rvv:vadd
python3 verification/verify.py run rvv-directed --jobs 4
```

Tests use the manifest timeout by default. For an intentionally large directed
binary, override it for only the current invocation, for example
`python3 verification/verify.py run --test rvv:vlsseg --timeout 900`.

Generate a deterministic RVV 1.0 random assembly smoke program with the
locked riscv-dv implementation:

```bash
python3 verification/verify.py generate-rvv --test ara_dsa_rvv1_smoke --seed 1
```

The local test list also defines a ten-seed strict-checkpoint profile and
ten-seed arithmetic, load/store, integer, FP32, FP64, vector-configuration
churn, slide-index memory, and mixed-control profiles, plus a 50-seed nightly
profile. Omitting `--iterations` uses the profile's YAML iteration count and
`--seed` becomes the first seed; passing `--iterations` explicitly overrides
that count. Every generation writes
`stimulus_coverage.json`, which reports the instruction families, exact
mnemonics, SEW/LMUL/policies, masks, and memory modes actually present in the
generated assembly. Generation is only a stimulus-construction step; it
does not count as an Ara correctness pass until the resulting program has been
compiled, executed on Spike, executed on RTL, and compared architecturally.

Run that complete pipeline with an existing VCS executable:

```bash
python3 verification/verify.py run-rvv \
  --test ara_dsa_rvv1_smoke --seed 1 \
  --simv verification/out/stage2-repro-build/_build/vcs/simv
```

Use the short strict-state diagnostic before longer random regressions:

```bash
python3 verification/verify.py run-rvv \
  --test ara_dsa_rvv1_signature_smoke --seed 1 --vector-signature \
  --simv verification/out/stage2-repro-build/_build/vcs/simv
```

To localize the first vector-state divergence, replace `--vector-signature`
with `--vector-checkpoints`. This inserts a full 32-register snapshot at the
entry to the generated `main` stream, after every generated vector instruction
(including `vset*`), and at exit. The short signature profile initializes the VRF with deterministic
scalar-immediate/slide sequences so an initialization-load failure cannot be
misattributed to the first random instruction. A vector-CSR read after each
whole-register store uses Ara's existing wait-for-idle path to establish
completion without relying on overlapping diagnostic stores. The insertion
preserves its temporary GPRs on riscv-dv's generated user stack, but the extra
whole-register stores, completion barriers, fence, and scalar reads serialize
the stream.
After each vector store, the rewriter also performs byte-exact scalar reads of
every riscv-dv `.region_N` data section. Other vector checkpoints do not add
these memory reads. This makes store targets observable immediately after the
responsible instruction, rather than only through a later load or final
signature. Checkpoint mode is therefore a functional
diagnostic only; it must not be used to assess performance, overlap,
backpressure, or concurrency.

Run the formal ten-seed strict-checkpoint regression with:

```bash
python3 verification/verify.py run-rvv \
  --test ara_dsa_rvv1_checkpoint_regression --seed 1 \
  --vector-checkpoints \
  --spike /home/wangwy/openproject/riscv-isa-sim/build/spike \
  --simv verification/out/stage2-repro-build/_build/vcs/simv
```

The command preserves the generated assembly and ELF, Spike commit log, Ara
commit trace, exact replay commands, trace validation, prefix comparison, and a
machine-readable result for every seed. `COMMIT_WATCHDOG` terminates an RTL
test that continues clocking without architectural or backend-uop progress. A
stalled result identifies the remaining `vid`, architectural request tag, and
instruction encoding. The runner also resolves the ELF's `tohost` symbol and
passes it as `COMMIT_TOHOST`, so riscv-dv programs terminate when their pass or
fail value is architecturally stored instead of spinning forever.
Strict vector-signature programs intentionally finish through a trapped `ecall`
after reading the complete signature. The rewriter labels that exact instruction
and the runner passes its address as `COMMIT_EXIT_PC`; the monitor accepts only a
trapped `ecall` at that configured PC. Existing rewritten ELF files without the
new label are supported by locating the first nearby `ecall` with the repository's
LLVM objdump. Default tests continue to use only the `tohost` contract.

The current tandem comparison is strict for instruction PC/encoding, the exact
scalar GPR write set and value of every instruction, and the reconstructed
scalar-register state of the matched prefix. This includes scalar results
produced by vector instructions. Spike's vector destination values are parsed
and retained. Add `--vector-signature` to force deterministic `tu,mu` policy,
store all 32 vector registers at test exit, and compare all 4096 vector-state
bytes through 512 exact scalar load results on both Spike and Ara. For
register-form `vsetvl`, strict mode scans the preceding straight-line block for
the reaching `li` definition of the `vtype` operand and rejects an intervening
write or control transfer. If policy bits must change, it substitutes the
deterministic value only around `vsetvl` and restores the original scalar
constant afterward. Ambiguous runtime dataflow remains an error.
Default random tests remain unmodified and report `vector_state_compared:
false`.

If RTL has already printed `Core Test *** SUCCESS ***` and produced the commit
traces, but the runner was interrupted during comparison, rebuild the strict
results without rerunning VCS:

```bash
python3 verification/verify.py postprocess-rvv \
  --output verification/out/<existing-run>
```

The command recovers the ELF and seed from `rtl.command.json`, validates the
existing architecture trace, reruns scalar prefix and accepted-VRF comparisons,
and regenerates each missing `result.json` plus the run-level `summary.json`.
It does not invoke Spike or `simv`. Use `--case <artifact-name>` to restrict the
operation and `--force` only when an existing result must be recomputed.
An architectural `PREFIX` means the comparison stopped before a verified
terminal point; random runs, replay and postprocessing label it
`INCOMPLETE_PREFIX` rather than PASS. For a completed frozen replay, independently
recompute the terminal and vector checks without rerunning RTL:

```bash
PYTHONPATH=verification python3 -m ara_verify.terminal_reaudit \
  --case verification/out/<replay>/tests/<case> \
  --output verification/out/<replay>/terminal_reaudit.json \
  --require-frozen-inputs
```

This audit verifies the private ELF, Spike executable and full VCS image hashes,
the ELF-derived exit PC or tohost address, the architectural terminal match,
and all accepted vector destination requests. A diagnostic run made before
`inputs.json` was recorded cannot pass the frozen-input gate.

Focused architectural matrices can be built and run as one suite:

```bash
python3 verification/verify.py run rvv-corners --jobs 4
```

`vaverage_matrix` covers all four averaging operations, all four `vxrm`
values, and SEW 8/16/32/64. `vmask_logical_matrix` covers all eight mask
logical operations under varied VL, LMUL, nonzero `vstart`, and policy
encodings. `vmask_compare_edges` checks integer and floating comparison masks
plus mask-scan results with an unaligned mask destination and byte-exact guard
registers. `vfp_vstart_edges` checks masked FP32/FP64 arithmetic at unaligned
nonzero `vstart` values, including preservation of prestart and masked-off
destination elements. `vdiv_vstart_edges` checks masked and unmasked integer
divide/remainder restart across SEW 8/16/32/64, including request-bound write
byte-enables. `vrepair_edges` targets widening, narrowing saturation/rounding,
EEW reshuffling, and reduction register-group boundaries.
`vwiden_overlap_edges` exercises the legal case where a narrow widening source
overlaps the high-numbered half of the wider destination register group,
including a zero-VL widening accumulator that must make forward progress
without modifying the aliased group. It also covers a `.wv` operation whose
destination is its complete wide source while the narrow source aliases the
wide group's high half, requiring both source layouts to remain readable.
`vslide_mask_edges` covers masked slide-up offsets both within and beyond one
mask transport word; `vrgather_edges` covers scalar indices beyond VLMAX and
an overlapping `vrgatherei16` data/index pair that needs simultaneous e64 and
e16 views of one raw register group.
`vnclip_edges` covers narrowing overlap, masked `vd==vs1==vs2`, nonzero
`vstart`, lane-word byte shuffling, masked/prestart old-destination
preservation, and the rule that only actually executed elements may set
`vxsat`.
`vstore_signature` scalar-checks unit-stride, strided, indexed, and segmented
store targets immediately after each vector store.

Reuse an already compiled simulator while still rebuilding test binaries:

```bash
python3 verification/verify.py run smoke --simv hardware/sim/simv
```

Use `--skip-build` only when both the simulator and selected ELF files already
exist. Each run is written below `verification/out/`; the directory contains
`run.json`, build logs, per-test artifacts, `summary.json`, `summary.csv`, and
`junit.xml`. `run.json` is `RUNNING` until all selected tests have produced
reports, then becomes `COMPLETE`; a dry run is marked `DRY_RUN`. Starting a
new invocation in the same output directory invalidates stale summary/CSV/JUnit
reports but preserves case logs, so an old dry-run summary cannot be mistaken
for live results.

Run the complete directed, application, and 12-profile random campaign with an
explicit Ara-compatible Spike executable:

```bash
python3 verification/run_full_campaign.py \
  --simv verification/out/<final-build>/_build/vcs/simv \
  --spike /path/to/ara-compatible-spike \
  --output verification/out/<full-campaign> \
  --jobs 8 --random-jobs 4 --timeout 900
```

`--spike` is mandatory for the complete campaign and direct `run-rvv` or
`replay-failed-rvv` runs; there is no implicit host Spike fallback. Profiles
that enable
nonzero `vstart` require a Spike build configured
to execute restartable vector ALU instructions from nonzero `vstart`.  The
reference model must still trap for the RVV operations that architecturally
require `vstart=0`, including reductions, mask scans, `vcpop`, `vfirst`,
`viota`, and `vcompress`.  Pass that executable explicitly with `--spike` so a
campaign does not silently depend on a host-local default Spike configuration.
Before any RTL test, the runner compiles and executes a small `vwadd.vv` probe
at nonzero `vstart`; its ELF, commands, tool hashes and verdict remain under
`spike_probe/`. An incompatible Spike fails before the long campaign begins.

The validated reference build uses riscv-isa-sim commit `488e07d7` plus
`verification/patches/riscv-isa-sim-ara.patch`:

```bash
git -C /path/to/riscv-isa-sim checkout 488e07d7
git -C /path/to/riscv-isa-sim apply \
  "$PWD/verification/patches/riscv-isa-sim-ara.patch"
mkdir -p /path/to/riscv-isa-sim/build
cd /path/to/riscv-isa-sim/build
../configure --prefix="$PWD/install"
make -j8 spike
```

The current inventory is 207 directed RVV tests, 50 applications, and 142
generated random programs. In addition to the minimum count gates, the campaign
requires all 32 `rvv-corners` tests by name and requires all 12 random profiles
at their configured minimum seed counts. After generation it merges the 12
`stimulus_coverage.json` files and checks that every expected source exists and
that all required instruction families, memory modes, SEW/LMUL values,
tail/mask policies, and masked instructions actually occur. Coverage is
collected from generated `main/sub_*` code before diagnostic rewriting; missing
semantic coverage makes the campaign fail. Random profiles retain a complete exit
signature and also enable non-intrusive per-vector-instruction commit
comparison; checkpoint profiles additionally compare full vector state after
each generated RVV instruction. `campaign_summary.json` reports collection
completeness as `status` and functional success as `verdict`. The command exits
successfully only when every expected, uniquely identified result is present,
all component commands return zero, every result status is `PASS`, and the
managed RTL, application, and verification source snapshot is unchanged from
campaign start to completion.

The default `smoke` suite remains a deliberately small integration gate;
architectural coverage belongs to `rvv-directed` and `rvv-corners`.
`rvv:vsetivli` now explicitly checks the `e32,mf2,AVL=20,VLMAX=16` boundary,
including agreement between its destination GPR and the `vl` CSR. It therefore
detects an implementation that copies the immediate AVL without applying the
RVV VLMAX constraint.

## Stage 2: Commit event trace

Builds produced by this runner include a verification-only CVA6 RVFI adapter
and Ara monitor. `--commit-trace` writes `commit_trace.csv` beside each test
log. `retire` rows are scalar architectural retirement events; `arch_start`,
`cvx_req`, and `cvx_resp` describe the accelerator interface; `uop_alloc` and
`uop_done` describe the sequencer lifecycle. Reshuffle and segment-memory uops
retain the architectural request tag that created them. A CVXIF response is
not treated as generic vector architectural completion.

## Stage 3: Non-intrusive vector commit comparison

`--vector-commit-compare` records each ALU, MFPU, MASKU, SLDU, and VLDU result
only after it wins VRF arbitration. The monitor retains the backend `vid` to
architectural-request mapping across reshuffle and segment uops. The offline
comparator groups all writes by architectural request, reverses Ara's lane
shuffle using the destination EEW, maps the request to its RVFI PC and Spike
commit, and compares every known byte accepted by the VRF. No instruction or
memory access is inserted into the test program.

Use `--vector-commit-index` to check one one-based dynamic vector-destination
request while bringing up the path:

```bash
python3 verification/verify.py run-rvv \
  --test ara_dsa_rvv1_signature_smoke --iterations 1 --seed 1 \
  --vector-commit-compare --vector-commit-index 513 \
  --spike /home/wangwy/openproject/riscv-isa-sim/build/spike \
  --simv verification/out/vector-commit-build_20260808/_build/vcs/simv
```

The case directory contains `ara_vector_trace.csv` and
`vector_commit_comparison.json`. A mismatch identifies the dynamic request,
PC, instruction, vector register byte, lane, writeback source, `vid`, VRF
address, and EEW. Unknown simulation bytes are never converted into values;
they are counted separately and make a selected request unobservable if no
known byte remains. The current path strictly checks accepted write values and
detects a wholly missing destination write. Complete active-byte coverage and
vector-store memory effects remain separate checks.

The comparator also propagates architecturally agnostic vector bits. If
`vmv.x.s`, `vfmv.f.s`, `vcpop.m`, or `vfirst.m` has an unknown relevant source
bit that can change its scalar result, that result is not bit-exact across
implementations and may change later control flow. In that case scalar
retirement and vector writebacks remain strictly checked through the first such
result, then both comparisons end with an explicit `PREFIX` status. A case
accepts this boundary only when both sides agree on the prefix, the RTL program
exits successfully, and the complete RTL request/uop trace is valid; a scalar
`MATCH` never accepts a vector `PREFIX`.
This is a diagnostic PASS, not a full-program architectural signoff: later RTL
retirements after an unobservable result have not been compared. Use
`--require-full-match` for signoff; it permits a `PREFIX` only when every RTL
commit was matched and Spike merely continues past the RTL exit boundary.

The complete gate sequence, including UVM's role and the VCU118/Linux end
point, is documented in [`SIGNOFF_ROADMAP.md`](SIGNOFF_ROADMAP.md). Use the
requirement map and audit gate before accepting a result:

```bash
PYTHONPATH=verification python3 verification/verify.py plan
PYTHONPATH=verification python3 verification/verify.py audit \
  --run verification/out/<run-id> \
  --require-trace --require-vector --require-coverage --require-full-match
```

An audit failure is an incomplete result, not a functional pass. Long VCS or
FPGA runs should use an independent output directory and be inspected only
after completion; the saved `run.json` and replay command are the source of
truth for reproducibility.

## FPGA-accelerated system verification

VCU118 is included as a long-run execution target. It is appropriate for Linux
boot and userspace, repeated context switches, DDR/cache stress, long RVV
regressions, QBS/AKV fallback, and llama.cpp-derived model slices. The same ELF,
input, seed, expected signature, and software revision must be used in Spike,
VCS, and the board run. A board result is accepted only with the current RTL
commit, bitstream/software hashes, DDR and reset status, console markers, and
named test results in a board manifest.

The board is not a waveform replacement. It increases time and system coverage,
but it cannot normally locate a cycle-accurate first failure. A mismatching board
signature must be reproduced with the same input in Spike and VCS, where the
commit trace, vector checkpoints, protocol assertions, and waveforms locate the
first divergence. This preserves precise diagnosis while moving multi-hour
Linux/model workloads onto hardware.

Use the unified gate entry point for an auditable run:

```bash
PYTHONPATH=verification python3 verification/run_signoff.py \
  --stage preflight --output verification/out/preflight-<timestamp>

# Full strict signoff requires all external evidence, a clean source worktree,
# stage_result evidence for Linux, and a strict FPGA manifest. Missing inputs
# become NOT_CONFIGURED and cannot be interpreted as PASS.
PYTHONPATH=verification python3 verification/run_signoff.py \
  --stage all --strict --output verification/out/signoff-<timestamp> \
  --simv /path/to/simv --spike /path/to/spike \
  --uvm-audit /path/to/uvm_result.json \
  --qbs-pair-manifest verification/qbs/paired_campaign_20260923_with_prefill.json \
  --linux-stage-result /path/to/stage_result.json \
  --linux-stage board \
  --linux-userspace-marker 'QBS/AKV userspace smoke PASS' \
  --fpga-manifest /path/to/fpga_run_manifest.json
```

本阶段不做板卡验证时，分别运行所需的 RTL 门禁，不使用包含 FPGA 的
`--stage all`。例如 QBS/RVV 与 AKV/RVV 的真实 DUT 配对门禁会从清单
重新审计原始日志、向量 trace、ELF 和镜像哈希，而不是复用旧汇总中的 PASS：

```bash
PYTHONPATH=verification python3 verification/run_signoff.py \
  --stage qbs-pairs --output verification/out/qbs-pairs-signoff-<run-id> \
  --qbs-pair-manifest verification/qbs/paired_campaign_20260923_with_prefill.json
```

The checked-in VCU118 reports are historical planning evidence: they explicitly
record that no accepted bitstream was generated. A new Vivado run and board
execution must produce the manifest consumed by the FPGA gate.

### Linux stage evidence

QEMU、RTL 和 VCU118 的 Linux 运行统一由 `verification/linux/run_stage.py` 记录。
它产生 `stage_result.json` 及其 SHA-256 旁证，签核入口通过
`--linux-stage-result` 重新验证退出状态、启动/用户态 marker 和 payload hash：

```bash
PYTHONPATH=verification python3 verification/run_signoff.py \
  --stage linux --output verification/out/signoff-<stage> \
  --linux-stage-result verification/out/<run-id>/linux-<stage>/stage_result.json \
  --linux-stage <qemu|rtl|board> \
  --linux-userspace-marker 'RVV fallback userspace PASS'
```

同一套结果格式只统一证据，不混淆执行环境；QEMU、RTL 和板卡必须分别运行、分别
保存目录和 stage。阶段结果缺失、过期、被修改或 marker 不完整时，签核保持
`FAIL`/`INCOMPLETE`。

若 RTL Linux 使用 `run_soc_smoke.py --mode linux` 的冻结 SoC 目录，而不是
`run_stage.py` 包装运行，则使用独立审计入口：

```bash
PYTHONPATH=verification python3 verification/run_signoff.py \
  --stage linux --output verification/out/linux-soc-signoff-<run-id> \
  --linux-soc-run verification/out/<completed-soc-linux-run>
```

它重新核对冻结的 Image/DTB/initramfs/OpenSBI、VCS 镜像、运行命令、
有序 UART 用户态标志和 RTL 活动。不能与 `--linux-stage-result` 或其
`--linux-stage` 选项混用；仅到达周期或 UART 诊断里程碑的运行必须失败。
# 统一验证入口

验证工作区提供一个不依赖具体 simulator 的入口层，避免每个人手工拼接命令导致
配置、seed 和结果目录漂移：

```bash
cd /home/wangwy/openproject/ara_dsa_verification
make -C verification plan
make -C verification list
make -C verification doctor-no-vcs
make -C verification unit
make -C verification preflight
```

`preflight` 只做计划、环境和 Python 合约检查，不启动长时间 VCS。仿真必须通过
`verify.py run`、`run_full_campaign.py` 或 `run_signoff.py` 启动，并将每个 case 写入
独立的 `verification/out/<run-id>/`，保存命令、seed、RTL/工具版本、日志和状态。

## 依赖修复的可复现输入

当前 CVA6/FPnew 修复以 `verification/patches/dependencies.json` 固定基准提交和
补丁 SHA-256。`setup_worktree.sh` 从锁定提交建立独立 checkout，只应用注册表中的
补丁，并写入 `worktree_inputs.json`。重新执行接受已经完整应用的相同补丁；部分
应用、额外修改、缺失必要补丁、错误版本均不能被 doctor 当作就绪。

比较包含 staged/unstaged 修改，必需子模块逐项检查 gitlink、HEAD 和工作区。
未来依赖提交若已包含修复，须重新审核并更新注册表，不能靠 reverse-check 自动豁免。
默认 THMULTI 与备用 PULP 的覆盖分开记录；原 PULP sticky 补丁暂存 quarantine，
未应用。详见 [依赖基线说明](patches/README.md)。

## 检查器自测与诊断前置

排查 bug 前按 `AGENTS.md` 建立假设/信号/期望观察的对照表。先从已有的架构 trace
找到首错，再围绕该事务一次性补齐 request、queue、issue、completion、flush 和 ID
复用的关联证据；不能每跑一遍才追加一个必要信号。减少的是盲目诊断次数，不是
修复后的必要回归。

接口监视器也必须经过故意注入错误的自测：

```bash
make -C verification contract-selftest
make -C verification real-ara-contract-smoke
```

前者检查 monitor 是否既不漏报也不误报；后者在独立构建目录中运行真实 DUT 短测试。
字段语义、覆盖限制、复用编译产物和有界 trace 方法见
[`uvm/README.md`](uvm/README.md)。这两种结果均不能替代架构差分或板卡系统验证。

### 在普通回归中强制检查真实接口

```bash
python3 verification/verify.py run linux-prereq --contract-monitor --commit-trace \
  --output verification/out/linux-prereq-new-run
```

`--contract-monitor` 显式加入真实 Ara 请求/响应监视器，并将严格日志检查作为每点
PASS 的必要条件。复用 `--simv` 时，该产物必须已经编入监视器；缺摘要、零流量、
未排空的接口请求、断言诊断或 console/VCS 摘要不一致均失败。它不等同于执行单元
全部排空或 Spike 架构差分，监视器对这两类问题不作证明。

每次 `run` 必须使用新目录或空目录，旧结果不会被覆盖。每点复制实际执行的 ELF，
记录其哈希以及 `simv` 和 `simv.daidir` 中生成的 RTL 共享库哈希；运行后若文件丢失
或改变，则该点不能 PASS。工具安装目录中的系统/VCS 库不在这份设计镜像哈希内。
`--simv` 复用不会被写成“本次从当前源代码重新构建”，源代码归属仍须依赖原构建记录。

跨用例统计 RVV 退休活动时，`ara_verify.coverage_matrix` 现在按完整 VCS
镜像分组：`simv`、`simv.daidir/*.so` 及 `simulator.conf` 的内容都参与
指纹。`--require-same-image` 会拒绝混合镜像或缺少配置文件的报告；不加该
选项时仍允许做跨镜像激励分析，但须查看 `image_groups`，不能将汇总计数
写作单一 RTL 版本的覆盖闭合。定向运行会核对其保存的镜像输入清单；旧随机
运行只有启动命令中的镜像路径可供事后重新哈希，证据强度较弱。该报告
统计的是已退休指令活动，不是功能、异常或 RTL 代码覆盖签收。
`ara_verify.vstart_activity` 可对一条已通过的定向或严格随机 case 重算
显式 `vstart` CSR 写到下一条已退休非配置 RVV 指令的对应关系；只有提交
轨迹能还原为确定非零值的写入才计入 `linked_known_nonzero`。其输入、
镜像指纹和结果分别记录在 JSON 中；该活动计数仍需结合程序自检或
独立架构比较，不能单独证明异常重启正确。

每点的 `contract_summary.json` 保存两份原始日志的哈希和摘要，`verify.py audit`
会重新检查日志与输入文件，不能只凭一个旧 JSON 中的 PASS 签收。`--commit-trace`
的结构检查现在明确记录 `status=VALID`；VALID 不是与 Spike 比较的 MATCH。

仿真阶段收到 SIGINT/SIGTERM 后，运行器通知并行 worker 终止自己创建的进程组，
未启动测试记作 CANCELLED，保留已完成结果，运行状态记为 INTERRUPTED。终止阶段
仍会保留不完整日志，不能当作通过记录。这不是对任意外部工具进程的清理命令。
