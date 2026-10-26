# Decode block-sum compiler review

The first candidate is functionally equivalent in the completed helper and
captured-input gates, but its vector-valued conditional introduces redundant
work in the measured ELF. This was found by inspecting the sealed
`verification/out/q8k-decode-soc-build-20261026-01/disassembly.log`, not by
assuming intrinsic count predicts executed instructions.

In `decode_candidate.constprop.0`, each 16-byte group executes:

| Address | Instruction | Role |
| --- | --- | --- |
| 0x80000248 | `vslidedown.vx v2,v8,a3` | low subregister candidate |
| 0x8000024c | `vslidedown.vx v1,v9,a2` | high subregister candidate |
| 0x80000254 | `vwredsum.vs v2,v2,v3` | low sum |
| 0x80000258 | `vwredsum.vs v1,v1,v3` | high sum |
| 0x80000266 | `vmv.x.s a7,v2` | low scalar result |
| 0x8000026a | `vmv.x.s a6,v1` | high scalar result |
| 0x8000026e | `bgeu a3,s1,...` | select which result to store |

Both alternatives execute before the scalar branch. The original has one
reduction per group; the first candidate has two. At VLEN1024 and 256 values,
the old loop issues 15 full-range slides and 16 reductions; the candidate
issues 32 short slides and 32 reductions. Shorter slides therefore do not
establish a net benefit. The VCS run is retained unchanged to measure it.

The successor `sums_split.h` processes the low and high subregisters in two
separate loops. This removes the per-group vector select. Full production-TU
compilation passed in `q8k-decode-split-compile-20261026-01`. Disassembly of
`quantize_row_q8_K` shows one slide/reduction/scalar extraction in each loop
body (0x7848/0x7852/0x785e and 0x7882/0x788c/0x789a), rather than both
alternatives per iteration. It also introduces a `vmv1r.v` at each half's
entry, so this is not claimed to be free or faster without measurement.

The original VCS inputs remain sealed. The successor has separate helper and
captured-input gates; no runtime source or RTL has been changed. After those
gates, inspect the actual bare-metal successor disassembly too, because the
Linux production object and bare-metal compilation are different contexts.

Both successor gates completed successfully on 2026-10-26:

- `verification/out/q8k-decode-split-helper-20261026-01`: 33,280 checks at
  each of VLEN128/256/512/1024, 133,120 total.
- `verification/out/q8k-decode-split-real-20261026-01`: seven real Decode
  captures, 280 comparisons per VLEN, 1,120 total; exact output bytes and
  matching FCSR/VCSR, with independent block sums and guard checks.

These results do not replace the pending latency test or establish complete
model correctness for an integrated successor. Keep this candidate private.

## Successor bare-metal measurement

The successor golden and ELF are in
`verification/out/q8k-decode-split-soc-golden-20261026-01` and
`verification/out/q8k-decode-split-soc-build-20261026-01`. The golden passed.
In the bare-metal disassembly, the low loop has one slide/reduction/extraction
at 0x80000258/0x80000262/0x8000026e; the high loop has one at
0x8000028c/0x80000296/0x800002a4. Each half still has an entry `vmv1r.v`.

The RTL motivation is specific: `hardware/src/sldu/sldu.sv` initializes
VSLIDEDOWN `issue_cnt_d` to `vl << vsew`, then decrements remaining work by
the processed byte count. With e8 and VLEN1024, the original block-sum loop
requests 15 slides of VL256; the split candidate requests 16 slides of VL16.
Those are logical output extents, not measured AXI traffic or elapsed cycles.
Setup, operand queues, register copies, reduction and scalar-result latency
can still dominate. This is why instruction inspection is not sufficient to
claim performance.

The successor VCS run is isolated in
`verification/out/q8k-decode-split-soc-vcs-20261026-01`, directly owned by
`q8k-decode-split-soc-vcs-20261026-01.service`. Its actual `simv` process was
confirmed running. The first candidate's worker and sealed inputs were not
changed. Both compare against their own original path in the same ELF; do
not substitute cross-ELF cycle ratios for those paired measurements.

## Preliminary K1536 RTL result: do not promote

Both workers emitted all four K1536 records while K8960 was still running.
The observations below are partial-run timing, not final PASS receipts:

| Candidate | Original ABBA cycle sum | Candidate ABBA cycle sum | Cycle increase |
| --- | ---: | ---: | ---: |
| Vector-select loop | 19,660 | 45,618 | 132.03% |
| Split loops | 19,669 | 28,028 | 42.50% |

The split trial records are 9909/14108/13920/9760 cycles in ABBA order.
All eight observed K1536 records across the two runs have packed digest
`30ba8689f5196189`, FCSR=1 and VCSR=3. Final canary/protocol/provenance and
K8960 checks remain pending. Neither candidate is justified for production.

Removing duplicate reductions improved the candidate but did not beat the
original. Smaller logical slide extents alone are therefore insufficient.
Use the instruction-level allocation/completion and writeback trace to
separate slide, reduction, register-copy and scalar synchronization costs
before proposing any further local variant. Do not infer the runtime or
model speedup from these partial preparation numbers.

## Cycle trace: register layout churn

The frozen snapshot in
`verification/out/q8k-decode-split-trace-analysis-20261026-01/trace-prefix.csv`
has SHA256 `4d5441043d231c4a1bd0aa144c9faa5ed3af784374f6f16482dfa963a2c4a09a`.
The first two six-block invocations of each path (K1536 ABBA) show:

| Instruction site | Architectural instructions | Backend micro-operations | Mean first-allocation to last-completion cycles |
| --- | ---: | ---: | ---: |
| Original slide | 180 | 180 | 24.00 |
| Original widening reduction | 192 | 216 | 24.56 |
| Split slide | 192 | 384 | 26.00 |
| Split widening reduction | 192 | 588 | 55.13 |

The split reductions contain 192 VL16/EEW16 micro-operations plus 396
VL64/EEW16 micro-operations. Its slides contain 192 VL16/EEW8 operations plus
192 VL128/EEW8 operations. These are backend metadata lengths, not extra
architectural instructions. Residence intervals overlap and cannot be added
as a stall-cycle breakdown. Write-byte accounting includes internal layout
operations; it is not DRAM traffic.

`ara_commit_monitor.sv` retains an architectural sequence across internal
operations and permits VID reuse after completion. Accordingly, the analysis
must match allocation occurrences and completions, not assume a sequence/VID
pair occurs only once. The initial analyzer rejected that assumption rather
than silently dropping micro-operations; tests now cover repeated pairs.

The split assembly writes e8 slide output to v1 and immediately performs
`vwredsum.vs v1,v1,v2`, whose result has e16 layout. The next slide overwrites
the same register at e8. The dispatcher's source/destination reshuffle and
legal overlapping widening-reduction repair paths explain the repeated
layout micro-operations. The original reduction uses a distinct destination
and does not alternate its layout on every group.

The next private candidate keeps the narrow input live alongside the widened
result through an empty compiler constraint. Its purpose is distinct register
allocation, not a new instruction or removal of overlap correctness logic.
Inspect generated code and repeat functional gates before any RTL timing run.
