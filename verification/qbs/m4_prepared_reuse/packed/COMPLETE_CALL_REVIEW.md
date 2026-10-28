# Independent Complete-Call Audit

Terminal verdict: **PASS for the measured full-output M4 Q/V/K slice**.
Audited 2026-10-28 UTC (2026-10-27 America/Los_Angeles), on
`ara_dsa_signoff_integration`. This is an independent replay of completed
evidence, not a new simulation, whole-model result, or deployment approval.

## Evidence and independence

- Packed run: `verification/out/m4-packed-qkv-vcs-20261027-01`.
- Prior cache-only run: `verification/out/m4-prepared-qkv-vcs-20261027-01`.
- Replayed `qkv/check.py` functions `check_output(raw_log)` and
  `check_trace(vector_trace.csv)` for both runs. Both PASS and exactly reproduce
  the saved `result.json` measured objects, including all four trial records.
- Independently invoked `ara_verify.uvm_dut.check_real_uvm_log` for both runs,
  with `require_events`, `require_backend`, `require_axi`, and
  `require_axi_write` all true, and the existing vector trace. Both PASS with
  no issues; every returned field matches the saved protocol receipt.
  Called functions in memory instead of the output-writing CLI, preserving
  existing receipts. All Python invocations used `-B`.
- Rehashed every source pin, image pin, and build-manifest entry using
  incremental SHA-256 reads, not `hashlib.file_digest`. Packed: 1880 source,
  68 image, 1876 build entries; prior: 1782 source, 68 image, 1022 build
  entries. No missing or mismatched files. Source-pin file digests match the
  run receipts; both build-manifest digests match their build receipts.
  ELF hashes match run and protocol receipts. `simulation_image(simv)`,
  including generated shared libraries, matches both protocol receipts.
- Replayed `ara_verify.vcs_source_manifest --check` on the canonical image:
  PASS, 468 files, no changes. The two run image-pin dictionaries are identical.
  Read-only `check-sim-l2.sh` also passes for the packed ELF: 4,157,544 bytes
  required, 16,777,216 provided; QBS, AKV and AKV-v2 enabled.
- Reconstructed R4 weights directly from the Q/V/K capture binaries and
  compared them with linked build assets. All match. Each activation's first
  four rows matches the 24,576-byte input; Q oracle, captured V/K oracle slices,
  and prepared-byte golden also match their source assets.

This audit does not merely accept the worker's PASS. However, it reuses the
sealed checkers and original simulation evidence; it is not a newly written
numerical checker or an independent simulation. Numerical correctness rests on
the guest's checked golden/oracle comparisons and zero-error result. Vector
trace replay establishes native work geometry/byte coverage, not numerical
values of every output or all ordinary RVV instruction semantics.

## Exact Work Scope

The input is the first four rows of the captured Qwen2.5-1.5B Q4_K_M block-0
prefill projections, not all 15 captured rows. Execution order is Q, V, K:
M=4, K=1536; N=1536/256/256; weight profiles Q4_K/Q6_K/Q4_K. Each trial
produces 8192 float outputs using 64 native M4 commands (48/8/8), with six
K-blocks, command N=32, no split-K, wide-M, or activation-context path.

Four trials in one ELF execute original recompute / packed plus reuse /
packed plus reuse / original recompute. Baseline prepares three times with
`m4_produce`. Each candidate starts with a fresh cache: one packed cold miss
and store, then two exact-input hits with prepared-byte copies. Final K
preparation clears/releases the cache inside timing. The generated packed
main differs from `qkv_projection.cpp` only by the packed producer declaration
and cold-miss call substitution. Original producer and unaffected objects
remain linked. Reusing producer tag 1 is confined to these fresh, isolated
cache instances; this does not validate mixing producers in a persistent cache.

Timing boundaries were checked against the source, not only the contract:

- `admit`: three `qbs_plan_create_segmented_r4` calls.
- `prep`: original preparations, or packed cold preparation plus cache lookup,
  allocation/store, owned input snapshot, exact-input comparisons, hit copies,
  flag handling and final `cache.clear()` release.
- `execute`: three complete `qbs_execute` calls, including SDK/native dispatch
  and all 64 commands.
- `total`: surrounds the three-part loop and includes timing fences, loop and
  local plan/status bookkeeping. It is not exactly the sum of the three phases.
- Excluded: initial device query/input integrity, buffer initialization, cache
  construction, initial CSR setup, post-loop CSR reads/statistics, numerical
  checks/canaries/printing, model loading, weight repacking, intervening graph
  operations, GGML graph scheduling/threadpool/allocator, and model execution.
  Cache allocation/release is included; GGML allocator overhead is not.

Guest checks cover all 7008 prepared bytes per projection, 64-byte guards,
all outputs against fixed oracles (Q atol=2e-4/rtol=2e-5; V/K 2e-3/2e-3),
bitwise output equality to trial 0, output guards, caller FCSR/VCSR, and
input/weight integrity. All trials report errors=0, FCSR=17, VCSR=5; candidate
hits/misses/stores=2/1/1, baseline=0/0/0.

## Measured Results

All values below are cycles summed across the two trials of each kind.

| Run and path | Admit | Prep | Execute | Residual | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Packed run baseline | 11948 | 689531 | 955981 | 2004 | 1659464 |
| Packed run candidate | 12481 | 194799 | 956795 | 1997 | 1166072 |
| Prior run baseline | 11926 | 689620 | 955880 | 2005 | 1659431 |
| Prior cache-only candidate | 11967 | 272660 | 956466 | 1995 | 1243088 |

Packed same-ELF result: **1.4231231004603488x**, **29.732009853784114% fewer
cycles** (493392 saved). Prior same-ELF cache-only result: 1.3349264090716024x,
25.089503570802285% fewer cycles.

Comparing the two candidate totals gives **1.0660473795786194x**, or
**6.195538851633997% fewer cycles** (77016 saved). This is explicitly a
**cross-run, different-ELF comparison**, not a paired same-ELF packed versus
cache-only experiment. The baseline totals differ by 33 cycles. Identical
image/data/scope improves comparability but does not remove code-layout and
run-order effects or provide statistical confidence. Candidate preparation
falls by 77861 cycles while admission/execution/residual rise by 845 combined.
Do not multiply isolated preparation and cache-reuse speedups.

## Protocol and Terminal State

Both traces contain exactly 256 native matrix commands and 131072 result
bytes, with four lanes, VLEN=1024, and 512 unique result bytes per command.
Packed protocol replay observes 82148 requests/responses; 77008 backend
allocations/completions; 33081 completed AXI reads; 38068 completed AXI writes.
UVM/contract event counts both equal 85622; backend/vector event counts both
equal 154016, with matching event digests. No aborts or pending AXI work.
Prior corresponding counts are 87810, 84112, 33643, 50360, 92028 and 168224.
Both protocol replays have no issues.

Packed `status.json` records PASS, simulator exit 0, checker exits 0, one
simulation, and completion at 2026-10-28T05:03:59.172760+00:00. The raw log
contains guest success, Core Test SUCCESS and zero UVM_ERROR/UVM_FATAL.
Recorded worker PID 3117217 and historical simulator PID 3129641 no longer
exist; a `/proc` scan found no actual `simv` for this packed run. A retained
`simulator_pid` field is historical, not evidence of a live process.

Service terminal success was supplied by the parent. No matching loaded
system/user unit was visible and journal access was denied, so this audit
does not independently certify the systemd Result or historical cgroup
ownership. Completed raw evidence supports the simulation verdict independently
of that service-status limitation.

## Disposition

The completed packed complete-call experiment passes this audit. No remaining
replay or provenance blocker was found for this measured slice. No whole-model
speedup, full-GGML acceptance, production cache safety, or live installation
approval follows from it. The parent reports promotion backup/candidate
prepared but not installed, 14 guard tests passing, commit `37c6a4f86`; those
promotion claims were not independently audited here.

Only this new review and `complete-call-audit-20261027.json` were written.
No simulations, builds, RTL/live-code/pin changes, existing-receipt changes,
parent-review edits, or commits were performed. Machine-readable identities
and replay summaries are in the adjacent audit JSON.
