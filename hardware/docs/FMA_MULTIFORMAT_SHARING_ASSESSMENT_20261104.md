# FMA Multiformat Sharing Assessment (2026-11-04)

## Scope and decision

- Static source assessment only; no RTL or verification-script changes, FPU simulation, or DC run.
- Only this new document is authored. Existing workers and evidence remain untouched.
- Scope: one 64-bit Ara lane, FPUSupportHalfSingleDouble, FP16/32/64 enabled, no FP8/alternate formats.
- Existing fpnew has a multiformat FMA implementation preserving FP16 x4 / FP32 x2 / FP64 x1 spatial capacity.
- It is not a validated configuration-only replacement: mask mapping is incorrect for the proposed use, and scheduling needs qualification.
- Correction to the earlier review: direct FP64-to-FP16/32 overlap is blocked by the current VMFPU latency gate. It is not a demonstrated bug.
- Partial sharing is worth evaluating, but requires an ADDMUL-specific format subset; changing UnitTypes alone does not produce the intended widths.
- No area, timing, power, or application-throughput improvement is claimed.

## Source identity and references

Repository HEAD at review: `130730b5bb25eeba375a5b04eefb67d9e8635f34`.
The worktree is not clean; SHA-256 below identifies the actual reviewed files, not just HEAD.
Line references in this document refer to these snapshots; paths are relative to repository root.
Active `operand_fifo_soc_20261104_02/source-pins.json` and inherited inventory documentation entries were inspected before writing.
The new document did not exist and was not listed in those inspected pins; no existing pinned file is edited.

| ID | Source | SHA-256 |
| --- | --- | --- |
| V | `hardware/src/lane/vmfpu.sv` | `a01ea5a29483ada2519ad2f9aa6ae9bcb4fc9bc364aa5d3846715947c7c22581` |
| A | `hardware/include/ara_pkg.sv` | `49a4fd9879cad35c2c77241bd5114fb8d02ab520e833335fd916122854830971` |
| P | `hardware/deps/fpnew/src/fpnew_pkg.sv` | `e742515e3c26e351c3b4a6bf160bcbfb29f7d6fb989bb81b0c34adf1384cf0e1` |
| B | `hardware/deps/fpnew/src/fpnew_opgroup_block.sv` | `bf38a22561603e7c2bed7e15fb1b398661d798c080706236548c6e9ecb7c8756` |
| S | `hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv` | `c6819beb6a21ae10e12a3529d4e315dba4447b40f088c9c0a70775cf089d08b8` |
| M | `hardware/deps/fpnew/src/fpnew_opgroup_multifmt_slice.sv` | `42657b27f28cd781dd76515b15985167140fdf4abe7f52972a6dab4f1958715c` |
| F | `hardware/deps/fpnew/src/fpnew_fma_multi.sv` | `73fee010682853487671fdbafda6b36553ca99fda91802bded7233ec9e51000d` |
| T | `hardware/deps/fpnew/src/fpnew_top.sv` | `405ea1c64c00beba6d87b4380914072e4eb75fc952f4f02b0461036575e41ebf` |
| D | `hardware/src/ara_dispatcher.sv` | `7bd7b46c87e2821e349d7c8938870ac79b2a77bf31eb3525fa07b904fc4eadf8` |

## Present structure and lane mapping

V:1014-1036 sets Width=64, vectors enabled, ADDMUL PARALLEL, DIVSQRT/CONV MERGED, NONCOMP PARALLEL, DOTP disabled.
S:95-125 generates a separate `fpnew_fma` for every element of each parallel format.
Thus the present ADDMUL structure is 1 FP64 + 2 FP32 + 4 FP16 = 7 FMA subunits per Ara lane.
These are FMA-capable arithmetic subunits, not seven concurrently issuable vector instructions.
P:444-468 defines element count and per-lane format membership; M:180-204 applies that membership.
M:260-292 already instantiates `fpnew_fma_multi`; F:62-78 sizes arithmetic by its largest enabled format.

| All-MERGED sublane | Supported formats | Selected operand bits for same-format arithmetic |
| --- | --- | --- |
| 0 | FP64, FP32, FP16 | FP64 [63:0], FP32 [31:0], FP16 [15:0] |
| 1 | FP32, FP16 | FP32 [63:32], FP16 [31:16] |
| 2 | FP16 | FP16 [47:32] |
| 3 | FP16 | FP16 [63:48] |

M:226-230 shifts operands by lane index times source width; this is not four fixed 16-bit arithmetic slices.
The resulting 4 subunits retain FP16 x4 / FP32 x2 / FP64 x1 capacity, not a time-multiplexed single FMA.
F:140-153 implements elastic pipeline stages; initiation interval 1 is structurally possible with ready output.
Actual timing closure, sustained transaction acceptance, and workload throughput remain unmeasured.

## Confirmed mask mismatch in the proposed MERGED ADDMUL path

V:1256-1267 samples byte enables at indices 0,2,4,6 in this FP16/32/64 configuration.
V:1942-1957 includes predicate, tail, and vstart suppression in those enables.
For FP32, mask entries in ascending index order are [m0,m0,m1,m1].
B:103-106 correctly selects entries 0 and 2 for the current PARALLEL FP32 pair.
M:278 instead passes `simd_mask_i[lane]`, selecting 0 and 1 for MERGED FP32.
M:708-715 collapses per-lane status using these masks, making the mismatch observable in exception flags.
Example: active element 0 and inactive exceptional element 1 can leak element 1's exception; reversing predicates can suppress a required exception.
This is a source-confirmed candidate-path defect, independent of format mixing; it is not a claim that current PARALLEL ADDMUL is broken.
Result byte-enable masking does not repair already-collapsed exception flags. Directed flag checks are mandatory.

## Pipeline latency and VMFPU scheduling

A:139-141 sets FP16/32/64 pipeline counts to 3/4/5; V:1025 uses these counts.
B:174 and P:583-590 select the maximum count among formats marked MERGED.
All-MERGED therefore uses 5 stages for all three formats; intended FP16+FP32 sharing uses 4, with FP64 independently 5.
These are configured pipeline counts, not a promise of end-to-end instruction latency under stalls.
V:237-253 still models latency per SEW; V:2307-2334 also uses it in reduction micro-operation scheduling.
A later implementation must reconcile both ordering and reduction scheduling with actual pipeline latency.
Keeping 3/4/5 unchanged is not a complete solution; replacing it with 5/5/5 also changes which overlaps the gate permits.

### What the current gate does prove

V:1700-1713 and 1780-1804 stall a younger instruction with lower modeled latency than the processing instruction.
V:1904-1914 applies this gate before ordinary FPU input valid; the transition term covers the registered decision's stale cycle.
Consequently, with FP64 processing, direct FP32 or FP16 issue is blocked; FP32 processing similarly blocks FP16.
V:1790-1804 also protects operation-group changes, but explicitly retains pipelining within one group.
V:1978-1989 advances issue independently of processing at V:2138-2151: ordinary instructions are not globally serialized to completion.
Reduction completion has a stronger busy/drain condition at V:2639; it must not be generalized to ordinary FMA traffic.
D:1685-1688 permits configuration acknowledgment while busy; D:1748-1755 drains for a particular LMUL decrease, not every SEW change.

### What remains a hypothesis, not a demonstrated VMFPU failure

M:217-224 sends sparse valid streams to ADDMUL sublanes; M:136 uses only lane0 input ready.
M:513-517 allows sublane consumption, while M:695-706 takes result format/tag/valid from lane0.
Different occupancy under backpressure can let a participating upper lane advance independently of lane0.
The direct wide-to-narrow example from the earlier review is insufficient because the current latency gate blocks it.
The comparator checks the processing head, not every outstanding instruction or the immediately preceding format.
For example, FP16(A), FP64(B), FP32(C) with A still processing is a discriminating sequence to investigate, not a proven reachable failing trace.
Operand availability, queue timing, issue/processing pointer movement, and downstream backpressure must be included in that investigation.
If a candidate equalizes modeled latencies, previously blocked format transitions require a new synchronization argument.
Conclusion: the gate narrows the risk substantially; neither a confirmed integrated bug nor a full safety proof has been established here.

## CONV is relevant evidence, not an FMA proof

M:220-224 explicitly fixes sparse CONV streams by sending every token to every lane, including nonparticipating bubbles.
M:94-95, 452-453, and 516-517 carry participation and suppress unused output contributions.
M:457-474 separately maps CONV masks by the larger source/destination element width.
ADDMUL has neither that mask mapping nor CONV's token-participation treatment.
CONV supports source/destination width changes and packing; ordinary same-format FMA and its VMFPU scheduling differ.
Do not infer a current FMA failure from the CONV comment, or copy its changes without checking unsupported formats, status gating, and FMA pipeline behavior.

## Three alternatives and recommendation

| Alternative | Structural intent | Main qualification |
| --- | --- | --- |
| Present PARALLEL | 7 units: 64 + 2x32 + 4x16; stages 5/4/3 | Retain as reference; no sharing change |
| All MERGED | 4 units: 64-capable + 32-capable + 2x16; stages 5/5/5 | Fix mask mapping; prove token alignment; update latency/reduction model; qualify frequency and short-vector cost |
| FP16+FP32 shared, FP64 separate | Intended 5 units: 64 + 2x32-capable + 2x16; stages 5/4/4 | Requires a correctly restricted ADDMUL merged format subset, then the same mask/alignment checks and format-arbiter ordering checks |

**Partial-sharing trap:** B:183 passes the entire `FpFmtMask` to the merged slice, not only MERGED formats.
B:178 filters incoming transactions, but that does not change M:180-204 elaborated formats or F:62-78 arithmetic dimensions.
Merely selecting FP16/32 MERGED and FP64 PARALLEL still elaborates an FP64-capable merged lane0 plus the separate FP64 unit.
Five instances therefore do not establish the intended widths or savings; possible synthesis pruning is unmeasured and must not be assumed.
A future subset must be scoped to ADDMUL; blindly filtering CONV formats can remove necessary source-format conversion support.
Review operand/boxing format arrays, mask dimensions, ready routing, and B:225-240 result arbitration alongside that subset.
Recommendation: evaluate corrected partial sharing as the lower-latency candidate, all-MERGED as the broader sharing comparison, and PARALLEL as baseline.
Neither candidate is recommended for immediate RTL adoption; do not serialize every format switch and label that unchanged mixed-format throughput.

## Area interpretation and preservation targets

7-to-4 is an instance count, not a 43% FMA area reduction and certainly not a 43% whole-machine saving.
An illustrative significand-multiplier bit-product count is `(53^2 + 2*24^2 + 4*11^2) = 4445` versus `(53^2 + 24^2 + 2*11^2) = 3627`, about 18.4% less.
This is only structural intuition, not a rigorous bound or PPA forecast: muxing, alignment, normalization, rounding, registers, and technology mapping are omitted.
Preserve FP16 x4 and FP32 x2 results per lane per cycle in ready, steady-state streams, with initiation interval 1 and no lower target clock.
Also measure dependency chains, reductions, short vectors, and mixed-format transitions; unchanged peak element count alone is insufficient.
Whole-machine significance requires matched hierarchical ADDMUL/VMFPU/SoC area and timing evidence; DIVSQRT and CONV are already MERGED.

## Minimum future validation plan (not executed or authorized by this document)

1. Freeze independent baseline/candidate inputs; verify enabled formats, sublane widths, and stage counts, especially partial-sharing lane0.
2. Check ADD/MUL/FMA results and flags against an independent arithmetic oracle, plus PARALLEL comparison; cover rounding modes, NaNs, infinities, subnormals, zeros, overflow/underflow, and fused cancellation.
3. Isolate exceptions in each FP32 element with masks 01/10, tail, and vstart; include FP16 per-element masks and active exceptional controls so checks cannot pass vacuously.
4. Scoreboard only accepted input/output handshakes, with unique transaction and sublane tags; check no loss, duplication, misalignment, unknown valid results, or timeout. Exercise stalls beyond pipeline capacity and full drain.
5. Test homogeneous streams, every ordered format pair, and the three-instruction pattern above through actual VMFPU gates. Separate unconstrained fpnew stress failures from reachable integrated failures; record issue/processing IDs, latency gates, format, sublane valid/ready/tag, and result-queue fullness.
6. Qualify reduction feedback and widening paths separately; cover reset with outstanding work. Unit-level flush is useful, but V:1318 ties integrated fpnew flush low, so do not claim SoC flush coverage from it.
7. Count accepted elements/cycle and total completion cycles at matched frequency assumptions. Only after functional qualification and separate authorization compare same-library, same-constraint block and SoC PPA, including all sharing overhead.

Current status: assessment complete; candidate implementation, failure reproduction, throughput evidence, and PPA remain pending.
