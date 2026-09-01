# AKV-v2 Token-Axis Attention Design

## 1. Evidence boundary

AKV-v1 removes repeated external Q/K/V reads, but it does not change the
arithmetic schedule. Its 6 KiB context contains eight Q rows, eight K rows, and
eight V rows in 256-byte D128 slots. A local load replays one complete slot into
the VRF. The native D128/GQA6 kernel therefore processes one token at a time:
it loads K, reloads six Q rows, performs six horizontal reductions, loads V,
and updates six outputs.

The controlled real-Qwen measurements expose the resulting boundary. At
KV=128, AKV-v1 reads only 140,416 AXI bytes, but executes 1,536 FP reductions,
2,048 local loads, and 512 KiB of local replay in 383,502 cycles. A standard-RVV
64-token implementation reads more data and pays 60,429 cycles to transpose K
in L2, yet needs only 48 reductions and finishes in 157,434 cycles. At KV=256,
the same comparison is 761,933 versus 309,574 cycles. The next mechanism must
therefore change the token-axis schedule, not merely increase row-replay
bandwidth.

This document covers functional organization, cycle-accurate RTL evidence,
full-model functional selection, and the statically elaborated SRAM-macro
organization. It intentionally contains no synthesized area or timing result.

## 2. Executable model

`hardware/scripts/akv/akv_v2_design_model.py` enumerates tile sizes 8, 16, 32,
and 64; Query groups 2, 4, and 6; and five context organizations. It reports
exact structural counts for context bytes, reductions, local commands, replay
bytes, K-view reads, model bytes, and a conservative VRF liveness lower bound.
It also reports a cycle interval anchored to the measured tiled-RVV no-pack
path and AKV-v1 fill/load costs. That interval is a hypothesis for selecting a
focused RTL experiment, not a substitute for simulation.

Run the model with:

```bash
hardware/scripts/akv/akv_v2_design_model.py
```

The alternatives have distinct, testable costs:

- `legacy_row` preserves the current word-banked slot layout. All K tokens for
  one dimension map to the same bank, so one token is gathered per cycle. It
  is functionally possible but structurally serial.
- `transpose_k` writes K dimension-major and reads up to 16 F16 tokens per
  256-bit word. It minimizes K-view reads, but every arriving row-major K
  element must be placed into a different destination row. The model exposes
  those element placements and does not hide their implementation latency.
- `dual_k` adds a row view to the transposed view. It preserves both access
  modes but duplicates K storage and retains the fill-transpose problem.
- `token_banked8` keeps K and V row-major while mapping token slots across
  eight banks. One read from each bank gathers eight K elements for the chosen
  dimension; a D128 V row remains a sequence of eight ordinary 256-bit reads.
  It needs no software or fill-time transpose.
- `token_banked8_phased` reuses storage between K and V. Scores must survive
  the phase boundary, so this alternative adds two fill phases and explicit
  score spill traffic.

## 3. Selected and implemented candidate

The implemented RTL candidate is `token_banked8`, `tile=64`, and a six-Query
score group. This is the only modeled point that simultaneously provides all
of the following without an unmodeled transform:

1. 24, 48, and 96 reductions at KV=16, 128, and 256;
2. one row-major model read of each K and V element;
3. no L2 K transpose and no phase-boundary score spill;
4. one K-column load reused by all six GQA Query rows;
5. a D-axis V row compatible with the existing output-update loop; and
6. a VRF liveness lower bound of 18 registers, leaving 14 architectural
   registers before compiler or assembly temporaries.

The context holds eight D128 Q-capacity rows plus 64 K and 64 V rows, or 34,816
bytes. This number is a functional capacity, not an area estimate. For a full
tile, each K column takes eight bank-read cycles and four 32-byte replay words.
Across KV=256, two K/V heads require 1,536 local commands and 256 KiB of local
replay, compared with AKV-v1's 4,096 commands and 1 MiB replay. Model input
traffic is 265,216 bytes, close to the 271,488 AXI bytes measured for AKV-v1.

The projected interval is deliberately broad. At KV=128 it is 105,465 to
126,713 cycles; at KV=256 it is 205,493 to 247,989 cycles. The lower edge assumes
local supply replaces ordinary packed-K/V loads, while the upper edge adds all
local-load busy cycles serially and therefore double-counts work already
present in the no-pack tiled path. The requested 130,000/250,000-cycle targets
lie inside those intervals. RTL implementation is justified as a
discriminating experiment, but the targets are not claimed until measured.

## 4. Required dataflow

One AKV-v2 tile executes in four phases:

1. Fill six F16 Query rows and up to 64 row-major F16 K/V tokens through the
   existing translated read engine. Tail tiles carry an explicit valid-token
   count.
2. For each dimension, gather one token-axis K column. Use that column once for
   six `vfwmacc.vf` score accumulators rather than loading it in separate 4+2
   Query passes.
3. Apply scale and mask, then perform one maximum and one sum reduction per
   Query row and tile. Scores may use ordinary measured L2 scratch initially;
   no model K/V packing is permitted.
4. Replay each V row once and update six D128 output accumulators. V never needs
   a token-axis physical layout.

Arithmetic remains ordinary RVV. AKV-v2 supplies a layout and reuse contract;
it does not add a private Attention arithmetic pipeline. Existing sequencer,
VRF writeback, exception, and completion rules remain authoritative.

The implemented generalization preserves that physical organization. The
Query-group count is runtime `q_rows=1..8`, rather than a fixed six-row
constant. D64 and D128 use complete physical rows, while D96 uses only the
first 96 elements of the D128 slot and suppresses the remaining D-axis tail.
No additional context bank or row is allocated for either change.

D256 was evaluated as a composed schedule rather than a larger context. The
software plan carries `d_offset` and `d_count`, presents two D128 descriptors,
accumulates the two partial QK scores before softmax, and replays the low and
high V halves into one D256 output accumulator. Hardware continues to see only
the existing D128 physical rows. This is a functional segmented contract; its
admission to the production backend is decided separately by measured
performance.

## 5. Compatibility boundary

AKV-v2 must add capability discovery and commands without changing AKV-v1
encodings. An old binary must continue to observe the v1 tile-8 row contract.
A new binary selects v2 only after capability discovery confirms the token-axis
profile, tile limit, D64/D96/D128 support, the requested Query-row count, and
the required command set. Unsupported shape, stride, mask, tail, or runtime
state uses the existing RVV or AKV-v1
fallback before changing hidden context state.

The contract must define:

- descriptor version and size without reinterpreting v1 reserved fields;
- FULL and REFILL behavior for a 1..64-token tail;
- row load versus column-view load selectors and destination register grouping;
- whether an invalid tile, dimension, selector, or destination faults before
  modifying context or VRF state;
- release and fault behavior with reads or local replay in flight; and
- strict counters for v2 fill bytes, column commands, column-view bank cycles,
  row commands, replay bytes, conflict cycles, and rejected commands.

The emitted performance log retains the historical field name
`v2_k_view_bank_cycles`. Its strict hardware meaning is now the number of bank
read cycles used by a v2 column-view command: selector bit 7 chooses the
physical K or V stream, while bits 6:0 select the local dimension. Production
D64/D96/D128 score code uses the K view; the segmented D256 experiment also
uses the V view for the high D128 score segment.

The implemented ABI keeps the v1 architecture and descriptor words byte-for-
byte unchanged. `AKVINFO(0)` and `AKVINFO(1)` therefore retain their old values.
`AKVINFO(2)` advertises token-axis profile version 2, a 64-token maximum, eight
token banks, six selector-index bits, tail support, row-view support, and an
enable bit. It also advertises D-axis-tail and segmented-D256 composition
capabilities. `AKVINFO(3)` publishes the two new instruction encodings and the
128-element physical row bound. Hardware without the profile returns zero for
both extension words, which remains a valid AKV-v1 device.

The two extension instructions use the remaining custom-2 function classes:

- `vakv2fill` uses `funct3=6`. Its FULL and REFILL forms retain the v1 operand
  convention: FULL takes the unchanged 64-byte descriptor in `rs1` and
  `tile_start` in `rs2`; REFILL reserves `rs1=x0` and takes `tile_start` in
  `rs2`. A successful command installs 1..64 active tokens.
- `vakv2kcol` uses `funct3=7`, writes one `e16,m1` destination, and takes the
  dimension index in `rs1`. Only the first `tile_count` elements are valid.
  Existing `vakvload` remains the row-load command; under a v2 context its row
  selector uses six index bits so V0..V63 and K0..K63 are addressable.

The descriptor still describes row-major Q, K, and V model tensors. The v2
profile changes only hidden-context organization and local views; software does
not pretranspose K and no reserved descriptor field is reinterpreted. Mask data
is deliberately not copied into hidden context. Software loads the active
1..64-element mask through ordinary RVV and uses exactly `tile_count` as VL, so
tail validity has one source of truth and masked values retain standard RVV
semantics.

The v1 descriptor permits any F16-aligned base and stride. The v2 token-bank
profile additionally requires Q, K, and V bases and row/token strides to be
32-byte aligned. This keeps each 128-bit fill beat within one 256-bit bank row
and makes the single-port bank-write contract explicit. The separate
`akv_v2_descriptor_is_valid()` check enforces this extension constraint without
weakening or silently changing the v1 layout contract.

`software/akv/src/akv_v2_reference.c` implements these visible semantics. It
copies row-major Q/K/V, exposes row and K-column views, checks a one-token tail,
and guarantees that selector, dimension, capacity, or tile-range validation
fails before changing the destination or the previously valid reference
context. A payload memory fault is a different class in RTL: partially written
hidden storage is never made ready, and the failed context is invalidated.
The generic `akv_attention_plan_create()` remains the version-1 compatibility
entry point. Version 2 is selected explicitly through
`akv_attention_plan_create_v2()` and `akv_attention_execute_v2_native()` only
after a backend has checked the token-axis capability and the complete software
shape contract; capability discovery alone does not reroute a model call.
The production llama.cpp selector admits only D64/D96/D128. Although the shared
runtime can construct the two-descriptor D256 plan, this does not make D256 a
selected model path.

## 6. Falsifiable implementation checks

Before changing RTL, the implementation hypothesis is:

> If eight token-indexed banks provide one K-column group every cycle and the
> six Query accumulators reuse each completed column, then KV=16 will show one
> 24-reduction tile per K/V head, no software pack interval, no K-view bank
> conflict, and exactly one model read of each active K/V element.

The focused waveform must distinguish this from four alternatives:

- K columns are accidentally reloaded for separate Query groups;
- tail lanes contain stale token data or escape mask gating;
- V row replay conflicts with an unfinished K gather;
- command completion occurs before all VRF words are accepted; or
- fill accounting omits a row, duplicates a range, or reads inactive tail
  tokens.

Required cycle-level signals are command valid/ready/type, context mode and
tile count, K dimension and bank-group counters, per-bank request/address/data,
gather-buffer valid mask, replay word and lane grants, range issue/completion,
fault state, and final vector-instruction completion. Only after these signals
agreed with the strict counters were KV=128 and KV=256 launched in independent
background directories.

## 7. Measured RTL closure

### 7.1 Design-stage mechanism characterization

The focused implementation follows the modeled organization directly. Eight
single-port 256-bit SRAM banks store row-major K and V payloads, with token
index modulo eight selecting the bank. `vakv2kcol` gathers one F16 element from
each bank per bank cycle and returns an `e16,m1` token vector through the normal
VRF result path. Existing row replay supplies V, while six standard-RVV
accumulators consume each K column once. FULL and REFILL use the existing
translated read engine; software supplies row-major model tensors and performs
no K transpose or K/V scratch packing.

The controlled design-stage runs use the real Qwen2.5-1.5B Q4_K_M D128/GQA6
capture and the same output tolerance as the RVV, tiled-RVV, and AKV-v1
baselines. Kernel cycles are the application's measured interval. These
three-point AKV-v2 measurements use source commit
`b57f11b0d40a58a76c8fa7423047dfdc1106d00f` and simulator SHA-256
`e5e340f3d616d4343420744971596850d19d5cb47808d2b1e6abf7f6efdc958a`.

| Effective KV | RVV cycles | AKV-v1 cycles | Tiled-RVV cycles | AKV-v2 cycles | RVV / v2 | AKV-v1 / v2 | Tiled / v2 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 16 | 121,338 | 52,318 | 41,293 | 33,799 | 3.59x | 1.55x | 1.22x |
| 128 | 725,838 | 383,502 | 157,400 | 100,530 | 7.22x | 3.81x | 1.57x |
| 256 | 1,413,791 | 761,933 | 309,540 | 193,369 | 7.31x | 3.94x | 1.60x |

All three points report `PASS` with zero output mismatches. Across the three
lengths, AKV-v2 is 5.74x faster than original RVV, 2.85x faster than AKV-v1,
and 1.45x faster than the strong tiled-RVV baseline by geometric mean. The
following strict counter equalities establish that the speedup comes from the
intended view and reuse behavior rather than an omitted computation:

| Effective KV | FULL | REFILL | K columns | V rows | K bank cycles | FP reductions | Q bytes | K/V bytes | Replay bytes | Conflict / rejected |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 16 | 2 | 0 | 256 | 32 | 512 | 24 | 3,072 | 16,384 | 16,384 | 0 / 0 |
| 128 | 2 | 2 | 512 | 256 | 4,096 | 48 | 3,072 | 131,072 | 131,072 | 0 / 0 |
| 256 | 2 | 6 | 1,024 | 512 | 8,192 | 96 | 3,072 | 262,144 | 262,144 | 0 / 0 |

For KV=16, 256 K-column commands are exactly two KV heads times 128
dimensions, rather than six commands per Query row. The 32 V-row commands are
exactly two heads times 16 tokens. KV=128 and KV=256 preserve the same
invariants over two and four tiles per head. External K/V bytes equal one read
of every active row-major K and V element, and the 24/48/96 reduction counts
equal two reductions per Query row and tile. These independent counts exclude
skipped Query work, duplicated model reads, hidden software packing, and stale
tail lanes as explanations for the cycle result.

### 7.2 Frozen pre-generalization integration regression

The pre-generalization coexistence image is identified by simulator SHA-256
`f21553f480d15f89b138c729cad17a8e359bc77691b12b032ae573e958f86cad`.
The held-request fix described below was therefore exercised together with
QBS, AKV-v2, the ordinary VLSU, and the 16 MiB simulation-only L2 configuration,
rather than inferred from the earlier mechanism image. The current real-model
AKV-v2 points are:

| Effective KV | Kernel cycles | FULL | REFILL | K columns | V rows | K bank cycles | Q bytes | K/V bytes | Replay bytes | Conflict / rejected |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 16 | 35,636 | 2 | 0 | 256 | 32 | 512 | 3,072 | 16,384 | 16,384 | 0 / 0 |
| 128 | 103,055 | 2 | 2 | 512 | 256 | 4,096 | 3,072 | 131,072 | 131,072 | 0 / 0 |

Both points report `PASS`, zero output mismatches, `Core Test *** SUCCESS`, and
the exact command/traffic identities shown above. Their run manifests bind the
capture manifest, Spike ELF, RTL ELF, and simulator hashes. The aggregation
tool accepts a point only after the runner has emitted a completion marker and
the implementation, effective-KV, result, mismatch count, terminal marker, and
performance-log checks all agree; an interrupted or mislabeled run cannot be
selected silently.

Compatibility checks use the AKV-v2-enabled RTL rather than a separately
compiled legacy image. The original RVV and AKV-v1 KV=16 binaries retain their
exact 121,338- and 52,318-cycle results with zero mismatches; AKV-v1 emits no
v2 command. A QBS/AKV-v2 coexistence image executes the QBS control smoke test,
including successful legal commands and the expected atomic validation fault.
On the same final image, a direct-activation diagnostic executes the real Qwen
Q4_K Decode-Attention leaf in 125,278 cycles. That number is not the Full-QBS
regression point because it omits the production activation context. Rebuilding
the formal representative app with the required `FILL/REUSE/RELEASE` sequence
completes all 48 native commands in 119,894 cycles with zero faults and zero
numerical mismatches. This differs by only 11 cycles (`+0.009%`) from the
119,883-cycle context baseline. The matching current Q6_K Decode leaf
completes in 208,863 cycles with zero mismatches; it deliberately uses DIRECT
activation reads and is therefore conservative for model calls whose software
K segmentation can reuse one context per segment.

This regression must use an ELF built against QBS descriptor version 2. An
older descriptor-version-1 ELF was initially observed to stall on the current
image, while that exact ELF completed on its matching older image. Rebuilding
the unchanged model case against the current generated ABI removed the stall
without an RTL change. The QBS suite launcher now rejects an ELF older than
the generated ABI, shared ABI headers, or benchmark command source before
starting simulation and records hashes of those ABI inputs in the run
manifest.

The C reference, generated ABI, QBS reference/repack tests, and AKV engine tests
all pass. The engine tests run with both generic SRAM and the SRAM macro model
and cover v1 D64/D128; v2 D64/D96/D128; segmented D256 row/column views; a
64-token tile; one- and five-token tails; runtime Query groups; row/column
ordering; byte enables; validation atomicity; and read faults.

The target-macro configuration now maps both context versions explicitly. The
v1 store has two logical banks of depth 96; each bank uses two 64x256 macros,
for four macros total. The v2 store has eight token banks of depth 128; each
bank uses two 64x256 macros, for 16 macros total. The current elaborated AKV
organization is therefore 20 macros with 40 KiB of physical macro capacity for
38 KiB of logical context (6 KiB v1 plus 32 KiB v2). This is an RTL organization
and macro-model regression result, not a synthesized area result. In
particular, the v2 `TARGET_SRAM_MC` branch is exercised by the macro suite; it
no longer silently falls back to generic `tc_sram` storage.

### 7.3 Area-controlled generalization

The generalized implementation adds no K/V context capacity. D96 reuses a D128
slot with a D-axis tail, arbitrary `q_rows=1..8` reuses the existing maximum
eight Query slots, and D256 reuses the D128 K/V regions in two phases. Focused
real-model RTL leaves use the current integrated QBS+AKV simulator with SHA-256
`dd6fbd3f696d8ce558fa46278fb22b0b0a09ef83c79e562b95dc2abdf46d052b`
and provide the following evidence:

| Model shape | Path | Cycles | Result | Interpretation |
|---|---|---:|---|---|
| SmolLM2 D64/GQA3/KV5 | AKV-v2 | 30,853 | PASS, 0 mismatches | Newly admitted runtime Query count |
| Phi-3.5 D96/GQA1/KV18 | AKV-v2 | 10,073 | PASS, 0 mismatches | D-axis tail without SRAM growth |
| Gemma D256/GQA4/KV17 | segmented AKV-v2 | 47,191 | PASS, 0 mismatches | Functional two-D128 composition |
| Gemma D256/GQA4/KV17 | tiled RVV | 36,043 | PASS, 0 mismatches | Matched admission baseline |

The D256 ratio is only 0.764x relative to tiled RVV, below the required 1.2x
gate. Every tile requires a score FULL that maps K0/K1 into the two physical
streams and a value FULL that remaps V0/V1 into those streams. Descriptor
fetches, Query payload reads, and K/V payload reads are therefore repeated
between the score and value phases; the 256 column gathers also serialize two
D128 segments. These measured costs outweigh context reuse at the
representative shape. The hardware/runtime contract remains testable, but the
GGML selector keeps Gemma D256 on ordinary RVV. This negative result prevents
context SRAM from being doubled for an unprofitable path.

Static inspection also considered sharing the v1 and v2 storage because only
one context version is architecturally ready at a time. Reusing the first v2
K/V rows for v1 K/V is possible in capacity terms, but v1 intentionally accepts
any F16-aligned address and can write a 128-bit beat across a 32-byte row. Its
two-bank staged writer can commit the two row fragments without serializing the
translated read stream. The v2 store instead relies on 32-byte-aligned rows and
one write to one token bank per cycle. Preserving the v1 contract in shared
banks would therefore require split-write buffering and explicit read-data
backpressure. A separate v1-compatible Query store would still require two
64x256 macros to preserve cross-row write throughput, so this change would
reduce the static organization only from 20 to 18 macros while adding control
and timing risk. Storage sharing is consequently an evaluated follow-up, not
part of the current implementation; it must be reconsidered only with measured
area, timing, and performance evidence.

The machine-readable generalization audit is generated by
`hardware/scripts/akv/check-generalization-closure.py`. It intentionally keeps
functional, full-model QEMU, cycle non-regression, and physical closure as
separate checks. A `PENDING` physical check therefore cannot be hidden by a
passing Host census or directed RTL suite.

The corrected model-level integration executes ordinary RVV, QBS-only, and
QBS plus AKV-v2 in one Qwen2.5-1.5B Q4_K_M QEMU guest. Its manifest records the
literal prompt, and all three executions report the same ten prompt tokens.
QBS-only and QBS+AKV-v2 produce identical text, top-1 tokens, and both recorded
logits tensors. Across one Prefill and one Decode graph, 394 high-level
quantized `MUL_MAT` nodes execute through QBS with 14,507,311,104 exact dot
elements and no QBS fallback. All 28 Decode `FLASH_ATTN_EXT` nodes execute
AKV-v2 at `D128/GQA6/active-KV=11`, covering 946,176 attention MACs; the other
28 candidates are Prefill nodes and are explicitly reported as shape fallback.
No runtime, capability, threading, feature, layout, or mask fallback is hidden.

The same trace closes one complete Decode graph, not only the accelerated
nodes. Exact node/type/shape matching maps every remaining Decode operation to
a compute-only real-model RVV RTL leaf. Combining that dynamic work with the
representative RTL calibration gives the following model-level Decode-token
projection:

| Component | Dynamic instances | Projected cycles | Share of calibrated Decode cycles |
|---|---:|---:|---:|
| QBS quantized `MUL_MAT` | 197 | 97,055,000 | 95.51% |
| AKV-v2 `FLASH_ATTN_EXT` | 28 | 862,958 | 0.85% |
| Remaining ordinary RVV | 340 | 3,700,824 | 3.64% |
| Total | 565 | 101,618,782 | 100.00% |

This is the final cross-operator-adjusted projection. The paired lifetime trace
matches each of the 85 eliminated quantizations to its concrete high-level
node; matrix work remains unchanged. Relative to the per-operation
quantization projection of 102,585,188 cycles, activation lifetime reuse removes
966,406 projected Decode cycles (`0.94%`). QBS projection otherwise uses per-node activation work plus exact
dot-element work with the current-image Q4_K context and Q6_K direct rates
above. AKV-v2 uses active-KV interpolation between measured RTL points, and the remaining
categories use exact Decode node multiplicities with type/shape-matched RTL
leaves. This is a reproducible RTL-calibrated cycle attribution, not QEMU wall
time and not a claim that the whole model was simulated in RTL. In particular,
the Q6_K rate is a conservative representative rate rather than a cycle-exact
model of every segmented context reuse.
The single Prefill graph is retained in the dynamic record: its 197 QBS nodes
project to 186,458,166 cycles for this prompt, but its non-QBS operators are deliberately not
included in the share table because no complete Prefill leaf calibration was
performed. The provenance snapshot records the dynamic log, run manifest,
source revisions, binaries, calibration logs, hashes, and projection-method
version.

The machine-checkable closure is defined by
`hardware/scripts/akv/goal-closure-manifest.json` and executed by
`hardware/scripts/akv/check-goal-closure.py`. It rejects incomplete shape
matrices, hidden model fallbacks, QBS command-work mismatches, unbalanced
activation-lifetime accounting, representative regressions above 1%, failed
RTL leaves, and AKV command or byte totals that violate the D/GQA/KV formulas.

Integration exposed one interface bug not visible in the isolated engine: the
sequencer can hold a blocking PE request through the engine's terminal cycle,
so VLSU ownership becoming idle could accept that same level-valid request a
second time. VLSU now records that the held request has fired and suppresses a
second command until the upstream request is withdrawn. A simulation-only
assertion requires every field of the held request to remain stable during this
interval. This follows the sequencer's registered `WAIT` contract and still
permits the next AKV instruction after the mandatory valid-low withdrawal
cycle.

## 8. Integration decision

AKV-v2 is now a real llama.cpp/GGML RISC-V backend route rather than an
application-local operator experiment. The route remains deliberately bounded:
Decode, F32 Query, F16 K/V and mask, F32 output, one batch, `D64/D96/D128`,
GQA ratios `1..8`, the supported stride/layout contract, and no sinks, ALiBi, or
softcap. KV is tiled in groups of at most 64 tokens, including arbitrary final
tails. It selects the shared version-2 planner and native kernel only when
capability discovery and every condition agree. Any unsupported shape or
feature returns before hidden context state changes and executes the existing
GGML RVV implementation.

The QEMU emulation route validates graph dispatch, planning, fallback, and
model-level numerical behavior; it is not a cycle model. Native performance is
established separately with real-model RTL leaves and strict AKV counters. The
frozen derived-real matrix passes `112/112` scalar-reference/RVV executions over
`D64/D128`, GQA `1/4/6/8`, and KV `16/63/64/65/128/256/1024`. Representative
RTL leaves pass with zero mismatches at `D64/GQA8/KV64` (43,357 cycles),
`D128/GQA6/KV128` (52,995), `D128/GQA4/KV63` (37,069), and
`D64/GQA1/KV65` (12,828). Relative to the frozen pre-generalization points,
the changes are `+0.009%`, `+0.021%`, `-0.162%`, and `+0.675%`, all within the
1% gate. The `D128/GQA6` arithmetic path is specialized
assembly; other admitted shapes use generic RVV arithmetic over the same v2
context, so the matrix proves correctness and selection breadth rather than
uniform speedup. The generalized Host census passes 28/28 real model/KV cases
with D64/D96/D128 and GQA1..8, and the SmolLM2/Phi directed leaves above prove
the two newly required shape classes in RTL. Arbitrary GGML strides and
trap-safe capability probing on an unknown processor remain outside the current
profile. Gemma D256 is the only one of the seven representative model shapes
that deliberately remains `fallback_shape`.

## 9. Stop conditions

The implementation stops rather than growing a dedicated Attention engine if
any of the following is measured:

- reductions remain above 24/48/96;
- software still transposes or rereads model K/V data;
- the six-Query group cannot be scheduled without architectural spills that
  erase K reuse;
- KV=128 or KV=256 does not beat 157,434/309,574 cycles after one root-cause
  iteration; or
- ordinary RVV, QBS, AKV-v1, descriptor, fault, or replay regressions fail.

Such a result would reject the current banked-view hypothesis and must be
documented before considering a physical transpose, local score store, or
dedicated arithmetic extension.

None of these original token-axis stop conditions triggered: the measured long points beat the
tiled baseline and the explicit 130,000/250,000-cycle targets, all structural
counts match, and the representative compatibility regressions pass.
The later D256-extension gate did trigger: segmented D256 is functionally
correct but fails the separate 1.2x-over-tiled-RVV requirement, so physical
capacity is not expanded and production selection remains disabled.
