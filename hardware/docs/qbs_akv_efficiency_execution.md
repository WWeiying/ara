# QBS/AKV efficiency execution plan

## Scope

Active objective: complete the prioritized QBS/AKV improvements, not just the
first passing experiment. Preserve ordinary RVV and llama.cpp fallback,
numerical contracts, fault recovery and existing model/shape support. No
synthesis or physical implementation is part of this stage.

Main baseline: `03743c61`. Work takes place in the independent
`ara_dsa_qbs_activation_overlap` feature worktree. Main's unrelated uncommitted
files and FPGA copies are not experimental outputs. Record each accepted
mechanism in a separate commit; integrate only reviewed, tested changes.

## Milestones and acceptance

| Priority | Work | Evidence required | State |
|---|---|---|---|
| 1 | Short-block QBS conversion/scale/accumulation throughput | Current-image cycle probes; real Q8_0 and neighboring format inputs; bit/fflags checks; paired cycles and traffic; multi-profile fault regression | Investigating |
| 2 | QBS activation overlap and Prefill scheduling | Existing M1/M4 overlap plus M5..8 comparison; include activation preparation and traffic; shared runtime selection if software changes | Direct M1..4 overlap validated; remaining scope open |
| 3 | AKV fill/replay/RVV compute overlap | Lifecycle and single-port conflict analysis; real Attention tile; matched QK/PV/numerical checks; shape and fault regression | Pending |
| Parallel resource work | Shared QBS/AKV reader; unified legacy/v2 AKV storage | Ownership/drain invariants; unchanged outstanding capacity and context lifetime; matched latency/fault tests | Pending |
| Subsequent coverage work | Quantized KV | One common llama.cpp format first; explicit decode/view contract; native RTL and model numerical validation; F16 fallback preserved | Pending |

Do not represent lower traffic as lower cycles or SRAM capacity reduction as
measured area reduction. Do not replace the requested mechanisms with smaller
test-only variants. A rejected candidate needs evidence and an explicit next
design decision, not a claim that the milestone is complete.

## Stage 1 hypotheses

The historical Q8_0 slot-stall counts are not current performance evidence.
The current FP accumulator has sixteen fixed slots and one issued FP micro-op
per cycle. Its I2F, scale multiply and accumulation form a per-entry chain.

Distinguish these hypotheses with one instrumented command-level image:

1. Arithmetic issue capacity is saturated: valid eligible work and FP fire
   remain high while upstream results wait. More buffering alone cannot help.
2. Fixed result-stream slot binding stalls with other slots free: observe
   requested slot busy, occupancy below sixteen and no accumulator conflict.
3. Selection causes avoidable head-of-line blocking: selected FP unit not
   ready while another operation class could issue.
4. Dependency latency dominates with few eligible entries: no-ready-work
   intervals coincide with in-flight conversions/multiply/accumulate.

Record command-relative cycle, K block, requested slot/accumulator, occupancy,
ready/valid, selected operation/state, FP issue and completion tags, and
upstream result blockage. Bound detailed trace output. Preserve result order
within each output and all rounding/exception semantics.

## Evidence ledger

The previously completed activation-overlap work is recorded in
`qbs_activation_overlap.md`. Its paired and final replay evidence lives at:

`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/qbs-activation-overlap-20261022/`

`final_replay/status.json` is passed, with eight exact result/counter replay
groups and source hashes verified on 2026-10-22. It does not close stages 1,
3, resource sharing, quantized KV, or full-SoC/model integration.
