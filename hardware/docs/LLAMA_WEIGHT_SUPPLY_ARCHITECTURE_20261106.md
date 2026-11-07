# llama.cpp Weight Supply Architecture, 2026-11-06

## 1. Decision And Scope

Status: ARCHITECTURE PROPOSAL WITH TESTED SUBCOMPONENTS; THE WIDE SOC IS NOT
ENABLED OR PERFORMANCE VALIDATED. Section 9 records the implemented parts and
their acceptance boundaries. No synthesis, physical or FPGA work is included.

The primary next performance experiment is **physical 256-bit SoC supply plus
32-byte/cycle QBS weight admission and sufficiently wide SRAM writes**. Preserve
the default 128-bit configuration, four lanes, VLEN=1024, native weight bytes,
software shapes, and each output's integer/FP accumulation order. Do not combine
this experiment with new dot/correction/FP arithmetic or a weight-residency ISA.
Borrowing lane multipliers to replace WideMatrixDot's extra 32 product slots is
a separate same-throughput PPA candidate, not this performance workstream.

The `weight_supply_codec_20261106_01` receipt records independent verification
of 197 tensors / 6.72 million blocks: all selected raw fallback, with zero net
saving. That codec is excluded; this document does not extend its census.
Dynamic evidence below is
restricted to Q4_K/Q6_K. Interfaces must remain correct for all nine profiles.
32 B/cycle is a supply/admission target, not a promise of compute saturation for
every profile. In particular Q8_0 uses 34 bytes per 32 weights and can be limited
by FP/result service; Q4_K/Q6_K evidence does not validate its performance.

### Accepted Evidence, Not Predictions

- `verification/performance/evidence/decode_native_20261106_01/result.json` and
  `verification/out/e2e_decode_native_diagnosis_20261106_01/result.json` in the
  signoff worktree identify the real Qwen3 M1/N128/full-K down prefix:
  busy=49,703, R beats=42,532, dot issue=24,576. These scope the existing case;
  they are NOT a forecast of the widened design, full-N decode, or whole-model
  speedup. R beats include the shared reader's traffic, not only weights.
- `verification/performance/evidence/full_qwen3_qkv_20261106_01/result.json`
  accepts M4/full-N QKV region speedup 1.603028x for WideMatrixDot. Its causal
  audit bounds removal of that pair's additional weight wait at approximately
  1.05224x region speedup. This is not the bound for every wider-supply change,
  but rules out assuming that all remaining QKV time is removable supply wait.
- The SDK single-input fastloop receipt is already accepted. Keep its sealed
  source/library selection identical across the width comparison; do not count
  its software benefit again as a hardware-width gain.

Source references below are relative to the repository root. Current SoC/QBS
path inspection is distinct from acceptance of a future implementation. Active
RMS and SDK-dispatch-model worker inventories, including inherited source-pins,
were inspected before this document was created; none pins this new path. Their
reports and inputs remain untouched. Inventories were read, not recursively
rehash-audited across unrelated QEMU/model input trees.

## 2. Checked Boundaries And Required Changes

| Boundary | Current source and limitation | Proposed change / invariant |
| --- | --- | --- |
| SoC memory | `hardware/src/ara_soc.sv`: `AxiDataWidth=64*NrLanes/2`, hence 128 at four lanes; `axi_to_mem NumBanks=1`; one-cycle SRAM; ASIC wrapper names an 8192x128 macro | Add an explicitly selected 256-bit configuration independent of lane count. Return two physical 128-bit halves in parallel or one genuine 256-bit word, not in alternating cycles. |
| Capacity | `hardware/tb/ara_testharness.sv` passes `L2NumWords=L2SizeBytes/(AxiDataWidth/8)`; direct SoC instantiations can instead leave a fixed word count | Fix L2 bytes, address map, initialization and dataset residency in all comparisons. Halve word count when doubling word width; audit every instantiation. |
| Interconnect | `ara_system.sv`: CVA6 64-bit width converter, Ara/system types, AXI mux/cuts and SoC xbar | All Ara-to-memory R data paths must really be 256 bits. Keep scalar upconversion and normal RVV load/store byte lanes correct. No hidden QBS 256-to-128 converter on this path. |
| VLSU | `hardware/src/vlsu/vlsu.sv`: normal/QBS/AKV ownership mux, translated physical-range checks, prepared-load path and shared-reader include | Propagate bus width through all types/cuts. Keep four-lane result interfaces unchanged. Validate normal loads/stores, masks, tails and prepared loads at both widths. |
| Response typedef | `hardware/include/shared_reader_types.svh` macro `QBS_AKV_SHARED_READER_TYPEDEF_RSP_T` takes data width; `vlsu_shared_reader.svh` instantiates it with `AxiDataWidth` | The checked current shared response is already parameterized. Ensure the instantiated wide response is 256 data / 32 strobe; no fixed-128 alias or narrowing assignment. Use a distinct narrow response type only on compatibility branches. |
| qbs_pkg | `hardware/include/qbs_pkg.sv`: generated ABI, `QbsMaxResults=128`, native block geometry and payload-location functions; no fixed-128 reader-response typedef was found in this checked source | Do not mistake 128 result elements for bus bits. Keep ABI/profile geometry unchanged. If another pinned source revision embeds a fixed-128 response here, explicitly migrate that typedef too and audit the selected revision. Generated package changes must come from its generator, not manual edits. |
| Shared reader | `qbs_akv_shared_reader.sv`: one owner, one `qbs_read_engine`, `ReadOutstanding=2`; asserts response width matches bus | Preserve one-hot owner, shared gate and two-outstanding ordering. Add explicit per-range transfer-size information if narrow transfers share a 256-bit physical bus. |
| Read engine | `qbs/qbs_read_engine.sv`: bus-wide `BeatBytes`, compacted first beat, page/burst splitting, same AXI ID, two burst records, fault drain | Retain full 256-bit payload and 32-bit strobe for weight responses. Separate physical bus width from selected transfer size for compatible narrow accesses. Extend lane/beat metadata, never merely change ARSIZE. |
| QBS engine | `qbs_engine.sv` asserts `AxiDataWidth==128`; weight data connects directly to a 128-bit compute input; descriptor is 16 bytes; activation/context paths remain 128-bit | Permit only deliberately supported 128/256 configurations. Keep weight response full width through compute/adapter. Adapt descriptor/activation/context explicitly, with correct offsets, completion and faults; never silently truncate upper bytes. |
| Compute ingress | `qbs_compute_engine.sv`: `weight_write_data_i[127:0]`, `strb[15:0]`, two four-row weight banks, response-carried bank/row-count metadata | Parameterize WEIGHT ingress only where necessary. Retain active-bank protection, K/N scheduler and existing arithmetic/results. The bank tag is not inferred from the live scheduler. |
| Adapter | `qbs_block_adapter.sv`: 16 input-byte targets, 128-bit beats, two-entry ingress plus pending beat, 16-byte rotation/phases and write grants | Build a genuine 32-byte weight mapper and bounded write combiner. Widen target arrays/counts/phase logic consistently. A two-entry 256-bit FIFO feeding the old 16-byte writer fails the throughput requirement. |
| Payload SRAM | `qbs_payload_buffer.sv`: weight planes each write one 128-bit word/row/cycle; activation plane is 256-bit; single-port read/write exclusion | Provide one 256-bit weight-word write/row/plane/cycle plus bounded unaligned carry, or a separately proven equivalent multi-bank write implementation. Preserve compute's existing 128-bit window semantics through a registered half-select. |
| AKV | `akv/akv_engine.sv` asserts 128-bit AXI; legacy/v2 context sinks accept 128-bit writes; replay and early acknowledgments have existing contracts | Keep AKV's logical interface at 128 bits via an owner-specific compatibility port. Do not feed 32 bytes into a 16-byte context sink. Its adapter state participates in busy/terminal/fault drain. |

Important correction to the shorthand "fixed qbs_pkg response 128": the current
checked typedef lives in `shared_reader_types.svh` and is parameterized. The
actual hard fixed-width obstacles are the engine assertion, compute/adapter
weight ports and native activation/AKV paths. All must be enumerated in the
implementation review, rather than claiming the entire path is generic.

## 3. Physical Supply And Storage Fairness

Required weight data path:

```text
parallel SRAM halves / true 256-bit SRAM
  -> axi_to_mem(256) -> xbar/mux/cut(256) -> VLSU ownership mux(256)
  -> shared reader(256) -> QBS weight response(256, 32 strb)
  -> 32-byte adapter -> wide write combiner -> 256-bit payload-word writes
```

For the common 16 MiB simulation memory, 128 bits require 1,048,576 words;
256 bits require 524,288 words. Addressable bytes and preloaded bytes are equal.
In the ASIC-macro branch, pair two 8192x128 macros at the same word index, use
separate low/high byte strobes, and concatenate their simultaneous read data.
The row address drops five byte-offset bits instead of four. Reduce the number
of depth groups so aggregate bytes do not double. The current high-address
depth-bank selection is not already a two-word parallel read implementation.

Keep one physical word request/cycle and its declared response latency; both
halves must meet it. `axi_to_mem.NumBanks=2` by itself divides `DataWidth`, not
independent requests or a missing bandwidth source. If memory latency changes,
size `BufDepth` against the actual return latency and prove credit/response
buffering. The present one-cycle/one-bank/fall-through path is not automatically
a half-rate service just because BufDepth is one. CPU writes share the memory
port; 32 B/cycle is the uncontended read service ceiling, not read+write each at
full rate. Scalar narrow reads/writes and masked stores require correct lane
placement and write strobes at 256 bits.

Keep `PrepareBytes` fixed (128 bytes at VLEN1024); the prepared-load path's beat
count changes from eight to four. Check its alignment, page and pending-store
overlap tests together with VLD/VST address generation. Changing NrLanes or VLEN
to obtain width would confound both resources and software behavior.

This is a SoC-local SRAM supply experiment. FPGA wider buses, DDR controllers,
CDC and board timing are later targets; do not edit or rebuild them here. A
32-byte on-chip path does not double unchanged external streaming bandwidth.
Any later board claim must measure the memory service actually reaching Ara.

### Local Payload Resource Inventory

The following excludes L2, the separate activation context, AKV storage and all
accumulator/control registers. These are byte counts, not measured cell area.
There are two adapters, four rows each.

| Payload storage | Current logical bytes | Proposed logical bytes |
| --- | ---: | ---: |
| Weight plane 0: eight rows x 8x128 -> eight x 4x256 | 1,024 | 1,024 |
| Weight plane 1: eight rows x 4x128 -> eight x 2x256 | 512 | 512 |
| Activation plane: eight rows x 8x256, unchanged | 2,048 | 2,048 |
| Total payload SRAM | 3,584 | 3,584 |
| Weight side registers: eight x 20 bytes | 160 | 160 |
| Activation side registers: eight x 36 bytes | 288 | 288 |

Current `qbs_payload_sram.sv` hard macro instances have depth eight even when
logical depth is four. With those exact available macros, current payload
physical allocation is 2 KiB weight + 2 KiB activation = 4 KiB. Reusing only the
existing 8x256 macro for every widened weight plane allocates 4 KiB weight +
2 KiB activation = 6 KiB, despite unchanged logical bytes. Record that 2 KiB
physical overhead honestly; smaller-depth macro availability is not assumed.
The generic SRAM instance must also honor its requested logical depth.

Primary write implementation: one 32-byte line assembler per weight bank/row/
plane, sixteen assemblers in total, with byte masks, destination word, epoch
and tail state. A budget of one pending 32-byte line plus an emit register per
assembler is up to 1,024 data bytes of temporary registers, plus metadata.
Combine partial incoming bytes into the pending word, emit at most one complete
256-bit word per destination SRAM/cycle, and retain the next word fragment.
If a plane ends, flush its masked tail without dropping the complete-word emit;
completion waits for both. A two-entry 256-bit ingress FIFO adds 64 data bytes
per adapter (128 total), plus its tags/masks. Existing 128-bit ingress/pending
storage must be replaced or separately counted, not hidden in the comparison.

Each row/plane still has ONE memory operation/cycle. Current active-bank reads
and inactive-bank prefetch writes remain separated. At bank turnover, outstanding
assembler/emit state must be empty before clear/reuse. The old 128-bit compute
window can select a half from a synchronous 256-bit read with aligned metadata;
do not change decoder element order or add an unaccounted arithmetic bubble.

The assembler bounds are a design budget requiring proof, not a proof of
32-byte throughput. Boundary fragments can require a finite flush. If this
budget cannot absorb the worst legal nine-profile sequence with bounded
occupancy, change the architecture or report the shortfall before performance
promotion. Do not hide sustained 16-byte draining behind a deeper FIFO.

## 4. Native Mapping And Nonalignment

Keep the native R4 layout, original base alignment, row-count tails and raw
bytes. Do not pad 210-byte Q6_K blocks or substitute a pre-repacked wider format
for only one side of the experiment.

- A Q6_K four-row R4 tile is 840 bytes; its successive packed K-tile starts
  advance by eight modulo 32. For a 32-aligned start it needs 27 physical beats,
  not 26.25 realizable beats. With the existing two-byte base alignment some
  phases need 28. Head/tail masks, overfetch and page splits remain explicit.
- A 32-byte logical slice at offsets 192..223 crosses the row boundary at 210:
  18 bytes belong to one row's side metadata and 14 to the next row's low plane.
  Internal plane boundaries at native offsets 128 and 192 also matter. Compute
  all 32 byte targets from the range offset, profile and response row/bank tag.
- A 32-byte slice starting at a non-16-aligned payload offset can touch THREE
  old 128-bit words. Merely providing two 128-bit writes does not cover it.
  The proposed aligned-word assembler retains the partial word across beats;
  it is not a 256-to-128 serial data path.
- Some short-block profiles can touch three rows in one beat. Use profile
  geometry for every byte, not a Q6-only assumption of one crossed boundary.
  All nine profiles retain row-major/R4 semantics and exact side metadata.
- First-beat compaction in the reader uses physical byte-lane position; the
  adapter uses logical range offset. They are different coordinates. After a
  partial first response, offsets advance by valid byte count, not always 32.
- Single-beat popcount must represent 0..32; combined pending/commit counts must
  represent their full possible sum. Expand 16-target loops, duplicate masks,
  consumed masks and 4-bit phase/rotation logic rather than only data vectors.

Track received bytes separately from SRAM-committed bytes. Only committed
bytes with no pending/emit state make a row complete. Assertions must check
each expected native byte exactly once, untouched guard bytes and no writes
to an active or incorrectly tagged bank. Independent row/plane/side writes may
occur together; same-word writes require a defined byte merge.

## 5. Narrow Compatibility, Permissions And Drain

Keep the default 128 build on its original constant-selected path. On a 256
physical bus, make transfer size explicit per range: QBS weights may use 32
bytes; descriptors, activation/context and AKV may retain 16-byte transfers.
An internal range maximum-transfer-size field is not a public SDK ABI change.
Use a distinct 128-bit client response for AKV, not an implicit assignment from
the wide shared response. A compacting/splitting bridge on this narrow branch
is permitted; putting that bridge in the QBS weight path is forbidden.

Narrow AXI bursts on a wide bus need correct ARSIZE, burst beat count and
address-dependent R lanes. A 16-byte INCR burst on a 32-byte bus alternates
halves as addresses advance. The current reader unconditionally plans with
bus BeatBytes and clears first_lane after the first beat, so it needs per-burst
transfer-size/lane-cursor metadata to support this. Merely setting ARSIZE=4 is
incorrect. Keep logical offsets/tags, RLAST and final range completion aligned.

If a compatibility implementation instead accepts a full wide response and
splits it, retain the upper valid fragment, increment logical offset by bytes
actually emitted, and delay completion until every fragment has been consumed.
On faults, invalidate unconsumed compatibility/assembler state and drain all
already offered/accepted AXI work before terminal release. Preserve AKV's
existing early acknowledgment versus terminal completion distinction.

### MMU, PMP And Physical Ranges

Retain `QBS_PLAN_WAIT_STORE -> TRANSLATE -> AR`, cached/idempotent admission,
4 KiB splitting, AXI burst limits and original fault cause/address semantics.
The maximum burst is 256 beats, but page splitting still limits a full-width
256-bit burst within one 4 KiB page. Do not enlarge the 13-bit physical-length
field without checking its actual page-bounded maximum.

The VLSU `qbs_range_is_cacheable_idempotent()` checks configured cached and
non-idempotent regions; it is NOT proof that every byte of a wider access has
passed PMP. The accelerator MMU request visible in `ara.sv` /
`cva6/core/load_store_unit.sv` supplies a cursor address and load/store kind, not
an explicit whole-burst byte interval. Therefore a permission proof is an
implementation prerequisite, not inherited automatically from a parameter.

The inspected `ara_soc.gen_usr_cva6_config()` explicitly sets `NrPMPEntries=0`;
this is also true in both frozen experimental images. Their first smoke uses
translation-off, file-backed/allocated physical RAM. It is not a PMP-enabled
test. For this selected zero-PMP target, the remaining translated-path proof
is page permissions plus complete physical RAM/PMA footprint and fault/drain
behavior. A nonzero-PMP implementation is a separate configuration extension,
not a reason to add unneeded PMP hardware to the current width experiment.
If PMP is later enabled, address-only admission is insufficient: require the
whole span within an effective readable region, respecting higher-priority
interior restrictions. Checking only endpoints can miss a denied interior.

Before a 32-byte access, prove permission for its complete physical footprint,
including aligned head/tail overfetch. Cover in-page permission boundaries as
well as page boundaries. If only an old-width access is permitted, use a
legitimate checked narrow transfer with correct wide-bus lanes; do not silently
cross the boundary or manufacture a fault for otherwise legal legacy work.
Do not suppress a genuine MMU/PMP fault by retrying as narrow. If the existing
permission interface cannot prove the footprint, extend/check it explicitly or
restrict wide admission to a proven uniform-permission mapping and retain the
legacy path elsewhere. No blanket NORMAL_MEMORY eligibility is assumed.

### Two Outstanding And One Owner

Keep the two-entry burst FIFO and the same AXI ID: R responses are ordered by
the recorded burst, not live K/N cursors. Preserve role, bank, row count, K
block, offset and fault sequence in metadata. No increased outstanding depth
or relaxed ownership is required to obtain the width experiment.

An offered AR stalled on READY remains stable and reserved even after a fault.
Stop new work, drain responses using the stored beats/size/lane metadata, and
do not reinterpret a late R as belonging to the next command. Owner and shared
clock remain live until reader busy, stalled AR, fault drain, compatibility
fragments and adapter/assembler state are all settled. Success requires the
original compute/FP drain and atomic VRF commit; a fault must not commit VRF
bytes. A completed logical range does not authorize bank reuse while its
accepted data still waits in an assembler.

## 6. Service Limits Before Implementation

For one full four-output-row, 256-element K tile:

| Profile | Native weight bytes | Ideal 128-bit transfer floor | Ideal 256-bit transfer floor |
| --- | ---: | ---: | ---: |
| Q4_K | 576 | 36 cycles | 18 cycles |
| Q6_K | 840 | 52.5 cycles | 26.25 cycles |

These are byte-rate floors, excluding head/tail rounding, range setup,
translation, contention, assembler flush and finite command boundaries. The
Q6 aligned physical-burst example above already rounds the latter floor up.
Do not halve measured R beats or busy cycles to predict new measurements.

M1 uses 32 dot-issue cycles per such tile, with additional control/pipeline
time. M4 WideMatrixDot uses 64 issue cycles with the same 64-product hardware
as its accepted baseline. Supply widening does not change either arithmetic
count or the correction/FP service rates. Remaining activation/context,
preparation, SDK dispatch, commit and FP costs remain in elapsed time.
Occupancy and overlapping phase counters are not independent additive savings.

Resource audit must precede simulation: record L2 logical/physical bytes and
ports; bus widths/cuts; outstanding depth; payload SRAM instances/depth/width;
side registers; assembler/FIFO data and metadata; unchanged activation/AKV
storage; and unchanged dot/correction/FP configuration. This is not a measured
area or frequency result. Same-frequency cycle results are not a timing-closure
or board throughput claim.

## 7. Fair Three-Point Comparison

Three platform points require FOUR timed software/platform combinations:

| Point | Required runs | What the comparison isolates |
| --- | --- | --- |
| A: current 128 | RVV128 and current QBS128 | Existing accelerator gain on the original memory service |
| B: ordinary RVV on 256 | RVV256 | Benefit of the wider platform available without QBS |
| C: complete QBS on 256 | QBS256, with genuine 32-byte weight admission | Increment over QBS128 and advantage over RVV256 on the same platform |

Report `RVV128/QBS128`, `RVV128/RVV256`, `QBS128/QBS256`, and
`RVV256/QBS256`. A QBS256-versus-RVV128 result alone is not acceptable. B and C
use the same wide SoC, with QBS hardware present in both and only software
selection changed; A has the same byte capacity and lane/VLEN configuration.
Use the current accepted WideMatrixDot M4 setting on both QBS sides, not a
narrow-dot 128 baseline against wide-dot 256. Preserve the M1 setting too.

Use identical captured model tensors, profiles, shapes, raw weight bytes,
packing and output region. ISA/architectural work may differ naturally between
RVV and QBS; physical overfetch may differ with bus width and must be counted,
not artificially forced equal or mislabeled as codec savings. Pin source,
compiler, software selection, memory latency, clock, L2 bytes and initial state.
Include preparation/admission/dispatch and drain in region/SDK comparisons;
report cold repack explicitly and consistently. No warm-resident-only replay
or duplicated activation presented as a second real model input.

## 8. Minimum Implementation Nodes And Stop Gates

The following defines integration acceptance; independent subcomponents may be
implemented and checked before their enclosing node is complete. Execution
belongs in the sole verification campaign with fresh owned
outputs, reviewed pins and preserved first failures. No Verilator or URG.

1. **N0: source/resource contract.** Freeze actual source revisions and the
   matrix above; establish default128/optional256 selection, all type widths,
   fixed bytes and permission strategy. Stop if the physical memory supplies
   only 16 B/cycle or any weight-path bridge serializes into 128 bits.
2. **N1: physical SoC and ordinary RVV.** Implement paired physical memory,
   address/strobe conversion and width propagation without QBS arithmetic
   changes. Prove correct memory bytes for scalar and RVV traffic before using
   it as a new accelerator platform. Neither capacity doubling nor ideal
   untimed data injection substitutes for this node.
3. **N2: reader and narrow clients.** Implement wide weight response plus
   explicit narrow transfer/client handling, two-outstanding ownership,
   permissions and fault drain. Default128 and normal RVV/AKV must remain
   architecturally correct; no new command may inherit stale R/data fragments.
4. **N3: complete weight ingress.** Implement 32-byte target mapping, write
   assemblers and wide payload writes with correct bank-clear/completion.
   Keep original compute window, integer/FP sequence and atomic commit.
5. **N4: reviewed focused VCS.** Use one representative real
   Q4_K and Q6_K point for performance discrimination, plus bounded directed
   width/fault/profile contract tests. Preserve default128 evidence and check
   all nine profiles numerically, not merely the two performance points.
6. **N5: actual SDK, then GGML.** Run the fair comparison on real Decode M1
   and Prefill M4, full K and a matched full-N projection/triplet. Use the same
   accepted fastloop and matrix settings. Only passing SDK candidates advance
   to complete llama.cpp/GGML model execution and intended-mode latency tests.

### Required Focused Signals And Structural Acceptance

- At memory: `l2_req/l2_we/l2_addr/l2_be/l2_rvalid`, simultaneous low/high
  physical returns, AXI AR address/size/length and R valid/ready/last. Prove one
  32-byte physical return per service cycle under uncontended full-width reads.
- At reader: owner, plan state, range/burst counts, recorded transfer size,
  response-head role/tag, logical offset, strobe, stalled AR and drain state.
  Distinguish shared-reader transfers from weight-only transfers.
- At adapter: accepted beat/bytes, committed SRAM bytes, ingress occupancy,
  assembler masks/word addresses/emit state, pending tails and bank identity.
  A finite FIFO-fill burst is not sustained throughput. Target at least 95% of
  32 B/cycle over declared non-boundary saturated weight-stream windows, with
  no positive backlog trend; report all head/tail/flush cycles separately and
  include them in complete-tile/command latency. If the geometry admits no
  such window, report exact finite-tile service instead of selecting one.
- At compute: `QBS_LOAD_TILE/COMPUTE_TILE/WAIT_WEIGHT/START_WEIGHT`, complete
  flags, active bank, integer start/done, dot issue, correction pending,
  FP main/cast handshakes, result backpressure and architectural commit.
  Preserve useful products, per-output update order, result bits and CSR state.

Directed cases must cover every legal base phase modulo 32, Q6 row/plane and
840-byte tile boundaries, short-profile multi-row beats, row-count tails,
4 KiB crossings, mapped/unmapped next page, narrow permission boundaries,
two outstanding bursts, stalled AR at fault, R errors/RLAST faults, backpressure
with an upper compatibility fragment pending, and owner handover after drain.
No checker tolerance or fault semantics may be relaxed to accept width changes.

### Performance Promotion Gates

- Default128 retains its accepted behavior; ordinary RVV and AKV pass their
  representative regression contracts at both supported widths. Any default
  performance change must be explained, not hidden in measurement noise.
- All comparisons use independently checked passing outputs and provenance.
  Failed or timeout cases do not qualify as performance evidence.
- Proposed investment threshold: at least 10% lower complete actual-SDK region
  cycles on the predeclared real Q4_K/Q6_K workload mix, including preparation,
  admission and dispatch, relative to current QBS128. Report each mode/profile
  separately; investigate any matched case slower by more than 2%. This is a
  go/no-go target, not a claim that the bandwidth floors achieve it.
- To call the work a meaningful end-to-end optimization, subsequently require
  at least 10% lower complete GGML/model elapsed time in the intended deployment
  mode, with identical outputs/tokens and preserved fallback/admission. Report
  RVV256 alongside it and keep Decode and Prefill claims separate. A positive
  Q6 prefix or B/cycle number alone is insufficient. If this gate fails,
  deprioritize the design rather than extending its scope indefinitely.
- Area/frequency/FPGA acceptance remains a separate later decision. No area
  saving, realizable frequency, FPGA acceptance, NORMAL_MEMORY admission, or
  external-DDR bandwidth improvement is claimed by this document.

## 9. Implementation Checkpoint

This section distinguishes tested subcomponents from the complete architecture
proposed above. None of N1/N2/N3 is accepted as a complete wide SoC merely because
one of its independently testable parts passes.

### Runtime Baseline

The isolated SDK-dispatch GGML library has completed the same full Qwen3
functional pair: 607744 logits, token/CSR, 788 projection calls and both
Attention/KV selections match. Actual guest cpio contents were independently
parsed, and baseline/candidate ELF bytes are distinct and correctly linked.
`verification/performance/evidence/sdk_dispatch_model_20261106_01/result.json`
binds both audits to one payload. This is not model timing. Non-M1 RTL performance
and production-library promotion are still separate gates.

### Per-Bank Write Assembly

`hardware/src/vlsu/qbs/qbs_weight_line_assembler.sv` is an uninstantiated 32-byte
word assembler. It accepts ordered compacted prefixes, retains one partial word
and one emit word, handles full-word-plus-tail closure, and clears validity on
abort. Its output requires a single word port with a ready/valid contract.
Holding invalid data unreset is intentional; valid and byte-mask qualification
is mandatory. The existing full arithmetic/activation path is unchanged.

The first component audit covers 16387 normal cases, four aborts and four
specific internal-contract rejections, with 1057025 bytes written and 78 accepted
bytes intentionally discarded by aborts. The initial worker remains FAIL because
it expected a nonzero VCS exit for an expected fatal; an independent successor
replays the raw results without changing that report or the RTL. The actual
negative logs each contain only their intended fatal. Supplementary checks now
cover byte-address widths 6/7/8/16, simultaneous emit-plus-tail abort, immediate
same-address reuse and fragment sizes 1/3/7/16/31: 68 cases, 60 streams and eight
aborts pass. The successor also requires exactly one global fatal for each
negative run and rechecks the original four negative logs without relabeling
their worker. The 20 input pins, 90 artifacts and raw results were independently
replayed.

### Native Weight Mapping And Private SRAM Bank

`qbs_weight_wide_mapper.sv` decodes each compacted source byte independently
into its row, low/high payload plane or side-metadata byte. It registers one
shared 256-bit data packet, plus segment start/count/offset/last and side-byte
selection controls. Balanced reductions replace serial mutable count and
priority chains; only packet validity resets. The package map is checked
against an independent explicit native-region oracle, not against itself.

All nine profiles, row counts 1--4, row-major/grouped ranges and all 32 physical
base phases pass two traffic schedules: 4608 cases and 36 aborts account for
1044480 decoded bytes and 1076 deliberately discarded bytes. Eight exact
contract rejections pass. The current 43 pins, 25 artifacts and raw logs were
independently replayed. The compact receipt for both component campaigns is
`verification/performance/evidence/weight_wide_components_20261106_01/result.json`.

`qbs_weight_wide_bank.sv` now has bank-local functional acceptance.
It connects this mapper to eight line assemblers and the actual payload SRAM
wrapper, with 4x256 low-plane and 2x256 high-plane logical storage per row.
All target segments of one packet advance atomically; side bytes commit at
that handshake, while payload bytes count only at actual SRAM writes. A row
cannot complete while its payload is buffered. Reads wait for the complete
private epoch, register the half-select with the synchronous SRAM request,
and preserve the original 128-bit compute window through idle cycles. Clear
invalidates partial writes, side validity and read-window validity, not payload
data. Profile/row-count ownership must remain fixed until clear.

One VCS compile and one functional simulation cover 4608 normal cases, 72
immediate reuse cases, 72 clear/reset cases and 72 cancelled-read cases. Actual
SRAM-interface writes and 45832 synchronous reads check byte identity against
the independent native-layout/address oracle. The run exercises 1526 packets
with mixed targeted-bank readiness, including 803 carrying side metadata;
none partially advances. X-safe control/count checks and exact per-epoch read
counts prevent unknown states from silently bypassing the checks. Unthrottled
input stalls are zero, and final-input drain takes at most two edges. These
are local service/functional results, not SDK or model acceleration.

The original worker remains FAIL solely because four shared `initial +=`
resource tallies each print one quarter of the static bank total. The precise
simulator scheduling mechanism is not proven. A host-only successor accepts
only that exact known record, derives the bill from pinned RTL declarations
and each SRAM instance's geometry checks, and replays the unchanged functional
checker with a resource-only input projection. It retains the original trace
and FAIL; all functional/error/terminal gates remain. Its 38 pins, 11 artifacts
and raw functional checks were independently replayed. Receipt:
`verification/performance/evidence/weight_wide_bank_20261106_01/result.json`.

The bank is now wired into a default-disabled compute-engine configuration,
as described below. It does not widen physical memory, and has no SDK
performance or area acceptance. With existing
depth-eight hard macros its 768 logical payload bytes allocate 2048 physical
bytes per bank; the two-bank macro overhead in Section 3 still applies. Macro
allocation is static accounting; this run used the actual generic SRAM branch,
not a TSMC macro model.

### Mixed Physical/Logical Transfer Widths

`qbs_read_engine.sv` now has `PerRangeTransferSize=0` by default and a
`range_size_i` input. The default shared production reader continues to request
full bus-width transfers. The optional path records transfer size in the range FIFO,
planner/AR registers and each outstanding burst. Alignment, burst length, checked
physical footprint and response lane advancement use the recorded size.
No public ISA or descriptor field changes are required for this internal hook.

`run_mixed_reader_checked.py` validates both original128 MMU response modes,
including nonidentity pages, page-fault recovery and six held-AR fault cases
per mode. A synthetic 256-bit target passes 258 mixed transfer/phase cases and
four local fault cases; 745 complete physical footprints are checked. The new
size field remains aligned when a narrow older burst and wide younger burst
are in flight. Unsupported size rejects before AR; permission rejection and
stalled-AR fault drain are checked separately.

The preserved first mixed fixture injected its error before the wide AR was
sampled as stalled. A successor retains all original checks and inserts one
sampling edge; probes show `ar_stalled_q` changing from 0 to 1 before injection.
The same RTL passes. This is a stimulus correction, not suppression of a DUT
failure. Receipt: `verification/performance/evidence/mixed_reader_20261106_01/`.

The wide target and permission signal are synthetic. Neither these tests nor
the assembler prove real CVA6 PMP coverage, the 256-bit physical SoC path or
SDK/model speedup. Native-format-to-SRAM integration is separately checked
below; no synthesis or FPGA work has been started.

### Optional Compute And Client Integration

`qbs_compute_engine.WideWeightIngress=0` retains the original adapter and
arithmetic by default. Enabling it selects two native wide SRAM banks and
removes the legacy weight SRAM instances; the legacy adapters still supply
the unchanged 128-bit activation path. Compute consumes the original 128-bit
weight windows and side bytes. The wide bank byte counter reports SRAM-committed
bytes, not merely admitted input bytes, preserving command-counter semantics.

The first response's row count is visible before READY on an unowned bank.
After admission it remains fixed until clear. A future one-row tail held on
VALID cannot reconfigure a still-owned four-row bank. Child VALID is qualified
by the parent's state/admission conditions, not the child's READY, avoiding a
combinational READY/VALID loop. Completion waits for all line-assembler writes.

The frozen compute-only pair passes 66 normal commands, five recoveries and
five injected fault scenarios per image, covering all nine profiles, row-major
and R4 layouts, M1--M8 and N tails. Both images select the same WideMatrixDot
arithmetic. All 17736 floating-point events have identical operands and
per-accumulator order; all final result bits, fflags and work counters match
the independent C reference. A held future tail is blocked for 51 edges while
2944 current-bank window bytes are checked. The two real-input cases are
Qwen2.5 Prefill-row slices, not actual Decode or Qwen3 timing. The source pins,
artifacts and raw checker were independently replayed. This is compute
integration evidence, not a reader/SoC/SDK performance claim.

The complete default128 QBS controller, shared reader and commit path also
retain every direct/context cycle in the accepted original 36-case reference.
The original context lifecycle, fault/retry and reset checks remain in place.
This regression uses original arithmetic with WideMatrixDot disabled and a
synthetic AXI/MMU/PMA fixture; it is distinct from the compute-only pair.

Internal reader requests now carry a per-range size. Optional wide QBS uses
32-byte weight transfers and 16-byte descriptor/activation transfers. The AKV
compatibility view explicitly copies every metadata, counter and fault field,
retaining only the low 128 data bits after compaction; it rejects nonzero upper
strobes instead of silently losing bytes. VLSU selection is default-OFF under
`ARA_QBS_WIDE_WEIGHT_INGRESS`, and it requires a real 256-bit physical bus.
With the feature disabled, the AKV response width stays exactly equal to the
original physical width. No ISA/SDK descriptor changes are involved.

The complete128/256 controller pair passes 36 commands per width at response
gaps zero and three. It uses physical-width AXI returns, recorded ARSIZE stepping
and actual upper-half narrow lanes. The synthetic direct-command totals are
30179/29445 cycles at gap zero and 48907/43674 at gap three; total reader beats
are 9287/7213 at either gap. Logical payload and arithmetic remain equal. These
heterogeneous directed-case totals are not a model speedup or a throughput
forecast. Original first-beat-only AXI fault injection is retained; this test
does not add later-beat fault coverage. The default128 timing independently
matches the accepted original. All three exact worker identities, 332 input
pins and raw checkers were replayed by `collect_wide_ingress.py`; receipt:
`verification/performance/evidence/wide_ingress_20261106_01/result.json`.

The first shared-client worker failed before simulation on a testbench typedef
syntax error. Its checked successor completes 128 normal cases, 12 faults and
128 direct metadata copies. The negative test emits the intended unique
upper-strobe fatal, but its checker expects the `else $fatal` line whereas VCS
attributes the SVA failure to the `assert property` line. Both original FAIL
reports remain unchanged. A host-only scoped audit binds the exact property,
mask consequent, instance, time, source hash and unique fatal, then projects
only that header's source line to replay every other original negative gate.
Its 66 pins, nine artifacts and both raw checkers have been independently
replayed; all 128 normal cases, 12 faults and 128 metadata copies pass, as does
the exact upper-strobe guard. The wide run exercises 193 AKV upper-half narrow
returns and 809 full-width returns. Receipt:
`verification/performance/evidence/wide_clients_20261106_01/result.json`.
Neither a failed report nor a source-location correction proves a
physical wide SoC. Ordinary RVV/AKV SoC regressions, actual physical memory
width, applicable translation/permission checks and actual-SDK/model latency
remain required. The selected SoC has zero PMP entries; nonzero-PMP support
is a separate configuration extension, not a prerequisite for this flat-RAM test.

### Physical Generic-SRAM SoC: Built, Runtime Gate In Progress

The full processor now has two compiled experimental VCS images, not merely a
synthetic AXI endpoint. Both derive from the accepted scalar/RVV/dependency
inventory with an explicit reviewed QBS overlay. Unrelated main-tree area
experiments are excluded. The original DPI object and native compiler recipe
are reused; source copies and tool inputs are frozen in build artifacts, not a
new development worktree. The only non-QBS functional configuration change is
the testbench's physical bus-width selection. The SoC adds an observation-only
geometry/one-cycle-response probe. Both images preserve every one of the 131
original compile diagnostics, rather than claiming a warning-free baseline.
The independent source/image/compiler replay receipt is
`verification/performance/evidence/physical_wide_soc_builds_20261106_01/result.json`.

The 128-bit image physically instantiates 1048576 words; the 256-bit image has
524288 words. Both hold 16 MiB with four lanes and VLEN1024. The initial runtime
records confirm the actual generic memory array word width and depth. This is
on-chip behavioral SRAM service, not an external-DDR bandwidth or macro/PPA
result. Both images retain the same WideMatrixDot setting; no arithmetic gain
is folded into the bus-width comparison.

An identical ordinary-RVV/scalar ELF is running on both images. Its independent
host oracle covers 180 scalar and 240 vector scenarios, all natural alignment
phases, masks/tails, each supported element width and physical page crossings.
The runtime gate checks final bytes/digest, physical memory activity and the
independent CVXIF/VID/AXI UVM result. Only after both sides pass does an event-driven
worker run the same committed QBS/AKV/RVV ownership-handoff program in parallel.
These runs are pending, not accepted performance measurements. They use flat
physical RAM, not virtual-memory fault or real PMP coverage.

The DPI loader enumerates nonempty, file-backed PT_LOAD segments using p_paddr
and p_memsz; it does not enumerate individual ELF sections. At either width,
the run admission independently checks segment alignment, rounded loaded-range
nonoverlap, physical/virtual address identity and the fixed RAM bounds. This
prevents an invalid preload from being misdiagnosed as a wider VLSU bug.

After these gates, actual-SDK Q4_K/Q6_K Decode and matched Prefill measurements
remain the performance decision. Same-platform ordinary RVV is still required
to separate generic memory-platform benefit from QBS benefit. Linux production
use still needs actual translated-path permission/fault tests for the selected
zero-PMP configuration. Nonzero-PMP configurations require the separate
full-span admission proof described in Section 5. This experiment does not
bypass either boundary or alter a checker to claim success.

### Same-ELF SDK Supply Comparison

The successor scripts `run_supply_sdk.py` and `continue_supply_sdk.py` prepare
the actual SDK experiment without recompiling either workload. Both physical
widths retain WideMatrixDot=1, four lanes, VLEN1024 and 16 MiB of generic SRAM.
The Decode ELF is `6f321585e2f25e9037269733a2fc0e3217c19c7d5345ed7cb6d45ab9b9a1256b`;
the full-QKV ELF is `4422e0562c951eebaec3593848d06c3e18fcd9bbf0b4c571a15fb69e814b5bea`.
All four real input/image/preload preflights pass; this is not runtime acceptance.

| SDK workload | Work checked on each image | Timing scope |
| --- | --- | --- |
| Real first Decode input | Seven N128 projection prefixes, full K2048/6144, 28 commands, 896 outputs | Four preparations plus admission and execution; existing context reuse retained |
| Real Prefill QKV | M4, K2048, N2048/1024/1024, 128 commands, 16384 outputs | Four captured prompt tokens, full output width; preparation included |

The new Decode checker preserves the original numerical, CSR, context,
workload and phase checks. It replaces only the invalid fixed-16-byte reader
lower bound: weights use 16/32-byte transfers, but descriptors and activations
remain 16-byte transfers. It additionally requires exact per-command beat
counts from the pinned SDK alignment and R4 layout: a Q4 R4 range uses 36/18
beats, a Q6 R4 range 53/27, an M1 activation block 19 and an M4 block 73.
Page/burst splitting does not add beats at these aligned split boundaries.
Together with the pinned role-size mux, this rejects an all-narrow weight
stream on the wide image. It is not independently observed per-role ARSIZE.
The Prefill successor reuses the original numerical
checker with matrix-dot enabled at both widths and adds explicit reader,
phase and zero-context accounting. Both successors replay the accepted original
128-bit raw logs. `supply_footprint.py` independently models page/burst splitting
and lane compaction. The aggregate byte lower bound remains a sanity check,
not a substitute for this exact range-based accounting.

The continuation watches the existing memory/handoff campaign's terminal file
events, revalidates its original raw evidence and only dispatches after all four
smokes pass. It runs two widths concurrently, Decode first and Prefill second;
each simulation is bounded to two hours. A failed prerequisite, input drift,
numerical error or protocol error prevents subsequent dispatch. A valid but
slower result is retained, not relabelled as a failed numerical test. At least
10% fewer complete-region cycles is the initial performance continuation
criterion; a regression above 2% needs explanation. This comparison changes
both the physical memory platform and optional weight ingress. It cannot by
itself isolate QBS-only benefit or predict an unchanged external DDR system.

### Standard RVV Counterpart Preparation

The same real first-Decode inputs now have a separately linked RVV-only
counterpart: Q4_K uses the actual GGML `ggml_gemv_q4_K_32x1_q8_K` selected by
its VLEN1024/N-multiple-of-32 runtime policy, and Q6_K uses the actual
VLEN-dispatched `ggml_vec_dot_q6_K_q8_K`. It is not a deliberately weak
single-output Q4 loop. All seven N128 prefixes retain full K2048/6144 and the
same four quantization boundaries. Q4 weights are reversibly repacked to the
production R32 format; Q6 bytes remain native row-major. The existing archived
quantizer object is reused. No QBS/AKV executor or custom opcode is linked.

The independent build receipt is
`verification/performance/evidence/decode_rvv_build_20261106_01/result.json`.
It binds 286 inputs and 42 producer artifacts, verifies actual runtime archives,
and admits the same 1.8 MB preload at either physical width. The first compile
attempt applied the fixture's global warning-as-error policy to unrelated
upstream kernels. The successor preserves the pinned upstream warning policy,
including scoped C errors, without changing optimization, ISA or FP options.
The last producer remains FAIL because GCC names its internal Q6 implementation
`.isra.0`; a scoped host audit verifies that exact clone and the VLEN1024
dispatcher target, then rechecks every other post-build gate without compiling
again. Original failures are not rewritten.

The exact ELF now also passes the independent Spike ISA model: all 896 output
words, four quantized payloads, guards and eleven preparation/part CSR records
are retained. A host MMIO plugin only implements the existing UART, memory-map
queries and exit register; it does not replace any guest arithmetic. Spike uses
the unchanged instruction budget with explicitly enabled Zicntr. Without that
extension, the first `rdcycle` at 0x8000056a is illegal; a bounded first-fault
probe established that cause before changing the model configuration. The failed
attempt is preserved, not mistaken for a slow matrix computation or repaired by
increasing the budget. No ELF, Spike binary or RTL was changed for this fix.

Q4 outputs match the embedded QBS C-reference bits. Q6 parts have 69/78/51
different words, with maximum absolute errors 2.98023224e-8, 5.96046448e-8 and
1.90734863e-6, respectively; none fails the existing absolute/relative tolerance.
These are different software arithmetic paths, not an RTL result. Subsequent RVV
RTL acceptance must match the independent ISA outputs and state records exactly,
not just pass the embedded tolerance. Spike cycle values are not performance.
The receipt is `verification/performance/evidence/decode_rvv_isa_20261106_01/result.json`.

Both actual ELF disassemblies seed FCSR=8, VCSR=5 and VSTART=0; the earlier
statement that the SDK starts at VCSR=3 was incorrect. VCSR=3 is its post-quantizer
state. The RVV driver does make extra timed CSR observations. Align or bound
that instrumentation before accepting a clean complete-call speedup. The new
`run_decode_rvv_rtl.py` reuses the accepted physical images, requires the actual
memory/handoff gate, replays the exact-ELF ISA evidence, and checks all output
words/state plus independent protocol after VCS. It cannot declare an SDK ratio.
No RVV job is silently added to the existing SDK queue; full-QKV RVV remains
pending.

### First Physical Decode Supply Result

The actual 128/256-bit Decode pair passes the numerical, payload, context,
CSR and independent protocol checks, followed by raw-log replay. It uses one
unchanged ELF, 28 commands and 896 outputs with full K and N128 prefixes; both
images retain the same matrix-dot arithmetic and 16 MiB physical memory capacity.

| Measured SDK interval/activity | 128-bit | 256-bit | Time ratio |
| --- | ---: | ---: | ---: |
| Preparation | 68377 | 65243 | 1.04804x |
| Admission | 11610 | 11610 | 1.00000x |
| Execution | 145475 | 115410 | 1.26051x |
| Complete measured region | 227810 | 194611 | 1.17059x |
| QBS busy cycles | 130052 | 100071 | -- |
| Shared-reader R beats | 107012 | 55300 | -- |

The measured region falls by 14.5731%, exceeding the initial 10% cycle-reduction
screen. The preparation change is also consistent with the fact that physical
bus width affects ordinary RVV/scalar traffic, not only QBS. This pair therefore
measures the combined physical-supply/native-ingress change, not an isolated
assembler or wider arithmetic benefit. It does not establish an unchanged-DDR
speedup or a whole-model gain. Same-platform RVV, Prefill, translated access
and resource-budget checks remain necessary before production promotion. The
Decode receipt is `verification/performance/evidence/physical_supply_decode_20261106_01/result.json`;
the still-running Prefill pair is not included in that acceptance.
