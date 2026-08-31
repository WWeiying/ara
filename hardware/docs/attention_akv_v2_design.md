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

This document covers functional organization and projected performance only.
It intentionally contains no synthesis, area, or timing result.

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

## 5. Compatibility boundary

AKV-v2 must add capability discovery and commands without changing AKV-v1
encodings. An old binary must continue to observe the v1 tile-8 row contract.
A new binary selects v2 only after capability discovery confirms the token-axis
profile, tile limit, D64/D128 support, and required command set. Unsupported
shape, stride, mask, tail, or runtime state uses the existing RVV or AKV-v1
fallback before changing hidden context state.

The contract must define:

- descriptor version and size without reinterpreting v1 reserved fields;
- FULL and REFILL behavior for a 1..64-token tail;
- row load versus K-column load selectors and destination register grouping;
- whether an invalid tile, dimension, selector, or destination faults before
  modifying context or VRF state;
- release and fault behavior with reads or local replay in flight; and
- strict counters for v2 fill bytes, K-column commands, K-view bank cycles,
  row commands, replay bytes, conflict cycles, and rejected commands.

The implemented ABI keeps the v1 architecture and descriptor words byte-for-
byte unchanged. `AKVINFO(0)` and `AKVINFO(1)` therefore retain their old values.
`AKVINFO(2)` advertises token-axis profile version 2, a 64-token maximum, eight
token banks, six selector-index bits, tail support, row-view support, and an
enable bit. `AKVINFO(3)` publishes the two new instruction encodings. Hardware
without the profile returns zero for both extension words, which remains a
valid AKV-v1 device.

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
`akv_attention_plan_create()` intentionally continues to select kernel version
1 at this checkpoint; capability and reference support do not silently route a
real model through unfinished RTL.

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

The focused implementation follows the modeled organization directly. Eight
single-port 256-bit SRAM banks store row-major K and V payloads, with token
index modulo eight selecting the bank. `vakv2kcol` gathers one F16 element from
each bank per bank cycle and returns an `e16,m1` token vector through the normal
VRF result path. Existing row replay supplies V, while six standard-RVV
accumulators consume each K column once. FULL and REFILL use the existing
translated read engine; software supplies row-major model tensors and performs
no K transpose or K/V scratch packing.

The controlled runs use the real Qwen2.5-1.5B Q4_K_M D128/GQA6 capture and the
same output tolerance as the RVV, tiled-RVV, and AKV-v1 baselines. Kernel cycles
are the application's measured interval. The AKV-v2 runs use source commit
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

Compatibility checks use the AKV-v2-enabled RTL rather than a separately
compiled legacy image. The original RVV and AKV-v1 KV=16 binaries retain their
exact 121,338- and 52,318-cycle results with zero mismatches; AKV-v1 emits no
v2 command. A QBS/AKV-v2 coexistence image executes the QBS control smoke test,
including successful legal commands and the expected atomic validation fault.
The C reference, generated ABI, QBS reference/repack tests, and AKV engine tests
all pass. The engine tests run with both generic SRAM and the SRAM macro model
and cover v1 D64/D128, v2 D64/D128, a 64-token tile, one- and five-token tails,
row/column ordering, byte enables, validation atomicity, and read faults.

## 8. Integration decision

AKV-v2 remains a real-model operator experiment rather than a generic GGML
backend route at this checkpoint. The application-local helpers and RTL prove
the D128/GQA6 token-axis mechanism and retain ordinary RVV arithmetic, but a
production route still needs measured D64, additional GQA ratios, arbitrary
GGML strides, worker-local ownership, and native trap-safe capability discovery.
The current benchmark's `akv_device_init_reference()` is appropriate only for
an image built for known AKV hardware; it is not presented as runtime discovery
on an unknown processor. Until those selection contracts are implemented,
unsupported software remains on the existing RVV or AKV-v1 paths and the v2
kernel is not silently selected by `akv_attention_plan_create()`.

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

None of these stop conditions triggered: the measured long points beat the
tiled baseline and the explicit 130,000/250,000-cycle targets, all structural
counts match, and the representative compatibility regressions pass.
