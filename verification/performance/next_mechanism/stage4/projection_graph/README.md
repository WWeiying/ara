# Stage4 Production-Helper Q/V/K Chain

Software preparation/build only. No candidate is consumed/pinned until its correctness
gate is terminal PASS and an explicit frozen OUT header/receipt pair with SHAs
is supplied. No VCS, synthesis, new kernel, worktree, or bare-GGML port is built
or launched by these helpers.

## Feasibility And Scope

Existing actual GGML graph recipes require Linux libggml, threading and dynamic
loader runtime; they execute under native QEMU using an existing kernel and
initramfs. There is no existing bare-metal graph recipe to reuse. Do not invent
thread/runtime stubs to claim otherwise. Actual GGML QEMU functional/selection
acceptance is a separate follow-up, not implemented by this SDK-chain driver.

VCS scope is the complete production-helper SDK chain: real Qwen2.5-1.5B first
four input rows, K1536, full Q/V/K widths1536/256/256, Q4_K/Q6_K/Q4_K. All three
projections have identical activation bytes. Each trial executes64 ordinary
QBEXEC commands and produces8192 outputs. Four ABBA trials produce32768 outputs
and256 commands. This is not Qwen3, a whole model, or GGML graph timing.

Both arms use accepted da56 packed parallel-sums and the same production
exact-byte value_cache. Both include one cold miss/producer/store, two hits,
allocation/copy/flag replay and final clear. Baseline producer tag3 calls
`ggml_riscv_q8_K_m4_packed::quantize<true>`. Candidate tag4 calls only
`qbs_experimental_m4_preflight::quantize` on its cold miss. Separate trial-local
cache instances prevent cross-arm reuse. No old scalar/unpacked/cache-off path
is used as the performance baseline. The explicit cache owner knows this fixed
three-consumer chain; it is not a replacement for actual GGML graph policy.

Dalton owns `software/qbs/experimental/m4_preflight/m4_preflight.h`. API:
`bool qbs_experimental_m4_preflight::quantize(const float *, void *, int64_t)`.
False means generic fallback has already completed output, never retry it.
The real representative fixture must select RVV in both arms. Unsupported
controls/fallback correctness belongs to the candidate's independent unit gate.

## Identity And Preparation

SDK/common/reference are Git archive d3d92ad72a3cabb91e8c333186160ae422f0866b.
GGML headers come only from llama da56aa750559c180d631b466de983ff2bb5d54d9.
The explicit additional source is the reviewed frozen candidate header.
Unchanged accepted generic fallback source must match an exact function body
in frozen da56 repack.cpp. No dirty SDK assembly, live llama source or private
dependency checkout is a compiler input. All target objects are fresh GNU
rv64gcv_zfh_zvfh, four lanes/VLEN1024. C++ uses no fast-math and FP contraction
fast, matching accepted production parallel-sums compilation; C oracle uses
off plus frounding-math. No numerical oracle or global checker is modified.

```sh
python3 -B verification/performance/next_mechanism/stage4/projection_graph/test_projection.py -v
python3 -B verification/performance/next_mechanism/stage4/projection_graph/build.py prepare \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage4_projection_chain_BUILD \
  --candidate-header FROZEN_OUT_HEADER --candidate-sha256 HEADER_SHA \
  --freeze-receipt TERMINAL_PASS_JSON --freeze-receipt-sha256 RECEIPT_SHA
python3 -B OUT/stage4_projection_chain_BUILD/inputs/build.py build \
  --output OUT/stage4_projection_chain_BUILD
```

Do not execute prepare while the candidate remains active. Rebuild/execute are
separate explicit operations. Preserve the first failure; no automatic retry.
After source/build review, eventual VCS must use the existing accepted SoC
image's checked receipt and pins, independent work, direct systemd ownership,
explicit environment/time limits and the unchanged strict protocol checker.
No VCS runner/launch is part of this source-only milestone.

## Checks And Measurement

Captured input/packed bytes/R4 weights/oracles retain their historical accepted
manifest identity. Original Q uses the accepted independent decoded-sum oracle;
V/K also retain captured GGML tolerances. New host code calls the unchanged
qbs_ref for every real tile to build a complete ordered raw F32 oracle. The
target compares every output bit to it, compares all arms exactly, and reports
an independently checkable complete-output hash. Every prepared byte, raw
subgroup sum, guard, original input and weight snapshot is checked. CSR is
FCSR17/VCSR5/vstart0; cache's existing raised-flags snapshot/replay is retained.

Checker requires the exact scope, tags3/4, cache queries3/hits2/misses1/stores1,
one producer,49152 requested comparison bytes,45600 copied bytes, no retained
payload after clear, full arithmetic/traffic counts, and256 alloc/write/done
groups with131072 result bytes. Hardware phase counters are exclusive classes,
not additive stall estimates. No QBACC, context reuse or cooperative M8 occurs.
Frozen ELF symbols bind `commit.csv` retire PC/instruction to the noinline
baseline/candidate producers (two entries each) and native executor (256).
Order must be each ABBA producer followed by64 native entries; cache labels
alone cannot stand in for proof of the actual chosen wrapper.

ROI includes fresh SDK plan/admission, preparation/cache handling, native
execution, result stores and final fence. Input/oracle verification and prints
are outside, as are one-time device query, cache object construction, buffer
initialization and caller CSR setup. Dynamic cache allocation/free remains
inside. These boundaries are recorded in the plan and build receipt.
Report preparation and complete-call deltas separately against
the strongest same-work baseline. No preparation-only ratio is multiplied by
old Stage2/3 gains. GGML allocation, scheduling/threadpool, model loading and
offline weight repacking are excluded. Software full-call benefit is not a
hardware or whole-model speedup.

`check.py` deliberately leaves independent protocol/image acceptance false;
the eventual runner must complete those gates before any PASS/performance claim.
