# Bounded Query Update for Long-Prompt Prefill Attention

## 1. Design question

This note records the falsifiable design contract and implementation status of
the mechanism selected after the Stage-2 baselines were frozen. It is organized
around externally testable behavior rather than an RTL change log.

The question is whether the existing AKV-v2 resident 64-token K/V tile can be
reused across multiple Prefill Query groups while all arithmetic continues to
execute on the standard RVV lanes. The mechanism must:

- preserve ordinary RVV behavior and fallback;
- keep hidden hardware state fixed with respect to prompt length;
- support causal prefixes that cross any number of 64-token tiles;
- preserve F32 online-softmax state across tiles;
- make a failed update invalidate the context atomically; and
- expose strict counters that distinguish external K/V savings from local
  replay, state, reduction, and backpressure costs.

It does not add an Attention MAC array. K-column dot products, exponentiation,
reductions, and weighted V accumulation remain standard RVV work.

## 2. Frozen pre-update path and its limitation

Before the Query-update node, AKV-v2 had two physically distinct payload
stores:

- `akv_context` stores the Query rows used by a context;
- `akv_v2_context` stores one 64-token K/V tile in eight token banks and
  provides row and token-axis column views.

The visible commands were:

- `V2_FULL(descriptor,tile_start)`: fetch descriptor, Query rows, and K/V;
- `V2_REFILL(tile_start)`: retain descriptor and Query metadata, replace K/V;
- row/column loads: replay resident payload through the normal VLSU result
  path into architectural vector registers; and
- `RELEASE`: invalidate the context.

There was no inverse of REFILL: software could not replace Query rows while
retaining K/V. The frozen Prefill compatibility loop therefore created one
complete context for each `(Query token, KV head)` pair. GQA rows share a fill,
but the same K/V prefixes are fetched again for the next Query token.

The physical separation of Query and K/V means this limitation is an ABI and
control-path limitation, not a storage-layout limitation. A Query-only update
can reuse the current memories without copying or rebuilding the resident K/V
tile.

## 3. Root-cause hypothesis

For long Prefill, the current serial-AKV schedule performs the required QK and
PV arithmetic but rereads K/V at Query-token granularity. The proposed change
places the K/V-tile loop outside the Query loop:

```text
for each KV head:
    initialize F32 state for its Query heads
    for each 64-token K/V tile:
        FULL or REFILL the tile once
        for each Query token that can see this tile:
            QUERY_UPDATE its GQA Query rows
            compute QK scores from resident K columns
            apply this token's causal mask
            resume stable online softmax
            update F32 output numerator from resident V rows
    normalize and store outputs
    RELEASE
```

The hypothesis is that removing repeated external K/V fills and descriptor
setup gives at least 1.20x over the strongest tiled-RVV baseline at a real
`M>=512` point. The hypothesis is rejected if external K/V bytes collapse as
predicted but cycles remain limited by local row/column replay, F32 state
traffic, reductions, or backend backpressure.

## 4. Query-update command contract

The implemented command reuses the AKV-v2 fill instruction class with a
distinct reserved fill mode. It does not consume another custom opcode.

The concrete extension keeps token-axis profile version 2 and adds capability
bit 40. `V2_FILL` uses `funct7=0` for FULL, `funct7=1` for REFILL, and
`funct7=2` for QUERY_UPDATE. Keeping the profile version avoids rejecting an
otherwise compatible v2 device; software tests the independent bit before it
uses mode 2.

For a Query update:

- `rs1` is the new F16 Query-group base;
- `rs2` and `rd` are zero;
- resident `q_rows`, Query stride, head dimension, K/V bases, K/V stride,
  logical KV length, current tile start, and tile count are unchanged;
- the new Query base must satisfy the existing V2 alignment and range rules;
- only the resident Query rows are fetched; descriptor and K/V are not read;
- the context is unavailable from command acceptance until terminal success;
- the new Query base becomes visible only on complete success; and
- any validation, translation, range, or read fault leaves the context
  invalid, so partially replaced Query rows can never be replayed.

The initial profile retains `q_rows<=8`. This covers one GQA group for the
target D64/D96/D128 and GQA1..8 contract. Increasing the physical Query-row
capacity to batch several Query tokens is a separate optimization and is not
justified until Query-update or column-command overhead is measured as the
new critical path.

Capability discovery must advertise Query update independently. Old hardware
continues to decode the capability as absent, and software then uses tiled RVV
or ordinary RVV without issuing the new mode.

## 5. State-resume contract

The captured tensors use F32 Query/output and F16 K/V/mask. Query rows may be
narrowed to F16 before AKV fill, but stable online-softmax state consists of:

```text
maximum:          F32 scalar per Query head
denominator:      F32 scalar per Query head
output numerator: F32[D] per Query head
```

F16 numerator state is not admissible for long Prefill. On the real
Qwen2.5 P0/M1024 capture, its error is reproduced at approximately 0.017,
whereas F32 state reduces the same focused cases to approximately `1e-5`.

The first mechanism stores resumable state in ordinary software-visible
memory, using the output-sized numerator buffer plus maximum and denominator
arrays. Standard RVV loads and stores restore it around each resident K/V
tile. This memory grows with the model output, but hidden hardware state does
not: AKV still contains one bounded Query group and one bounded 64-token K/V
tile. A dedicated state SRAM is not part of the first implementation.

The tile merge for one Query head is:

```text
m_new = max(m_old, max(score_tile))
a     = exp(m_old - m_new)
w     = exp(score_tile - m_new)
l_new = a * l_old + sum(w)
o_new = a * o_old + sum(w_j * V_j)
```

Masked lanes contribute neither to the maximum nor to either sum. A tail tile
contains exactly `min(64, active_prefix - tile_start)` visible tokens. The
state is committed only after all QK, softmax, and PV work for that tile has
completed.

## 6. Exact Qwen P0/M1024 expectations

For D128, Hq=12, Hkv=2, GQA=6, M=1024, P=0, and one Query token per update:

```text
K/V tiles per KV head                 = 16
visible (Query, tile) groups per head = sum(1024 - 64*t), t=0..15
                                      = 8,704
visible groups across both KV heads   = 17,408
V2_FULL                               = 2
V2_REFILL                             = 30
QUERY_UPDATE                          = 17,406
F16 Query bytes                       = 17,408 * 6 * 128 * 2
                                      = 26,738,688
external K/V bytes                    = 1024 * 2 * 128 * 2 * 2
                                      = 1,048,576
K-column load commands                = 17,408 * 128
                                      = 2,228,224
V-row load commands                   = 2 * sum(i+1), i=0..1023
                                      = 1,049,600
```

The external K/V value is the unique captured-payload floor and is 512.5x
smaller than the existing serial-AKV projection of 537,395,200 bytes. This
does not imply a 512.5x cycle speedup: K-column/V-row replay and all arithmetic
remain. The large exact replay counts are why local replay activity must be
reported alongside external bytes.

## 7. Strict counters

The retained implementation must add or preserve counters with literal
semantics:

- engine outputs `v2_full_count_o`, `v2_refill_count_o`,
  `v2_query_update_count_o`, and `release_count_o` count accepted commands by
  type; their log fields are `v2_full`, `v2_refill`, `v2_query_update`, and
  `release`;
- `q_external_bytes` counts accepted Query payload bytes only;
- `kv_external_bytes` counts accepted K/V payload bytes only;
- `v2_column_load_count` and `v2_row_load_count` count accepted local replay
  commands;
- `replay_bytes` counts bytes accepted by the lane result path;
- engine output `v2_query_update_fault_count_o`, logged as
  `v2_query_update_fault`, counts terminal Query-update faults;
- `read_*` counters retain their existing translated read-engine meaning;
- software phase counters separately record state load/store, QK, softmax,
  PV, and final-normalization cycles and bytes; and
- total operator cycles are valid only with a complete golden comparison.

`resident_tile_reuse` may be reported as a derived value equal to successful
Query updates since the most recent FULL/REFILL. It must not be presented as
an independent data-cache hit counter.

## 8. Cycle-level discriminators

Before changing a second mechanism, one focused trace must include:

- command valid/ready/type and terminal success/fault;
- context-ready, current tile start/count, pending and committed Query base;
- read-range role/address/bytes and read completion/fault;
- Query-context write slot/offset and absence of K/V writes during update;
- K/V bank column start/busy/valid and lane replay grant/final grant;
- sequencer/VLSU ready and backpressure; and
- software phase markers around state restore, QK, softmax/reduction, PV, and
  state spill.

The distinguishing observations are:

1. K/V context contents and tile metadata remain unchanged across a successful
   Query update.
2. No replay is accepted while context-ready is false.
3. A fault cannot expose a mixture of old and new Query rows.
4. Exact command and byte counts match the causal-prefix formulas.
5. If cycles do not improve after the external-byte reduction, the phase and
   replay counters identify the transferred bottleneck.

## 9. Fallback and unsupported cases

The Prefill selector must require all of the following before using Query
update:

- advertised V2 token-axis and Query-update capabilities;
- F32 Query/output and F16 K/V/mask;
- D64, D96, or D128;
- GQA ratio 1..8 with integral head mapping;
- dense causal visible-prefix masks;
- supported contiguous/aligned strides and nonaliasing ranges; and
- a size threshold that amortizes command setup.

ALiBi, logit soft-cap, non-prefix masks, unsupported dtypes/strides, D256 below
its performance gate, command faults, and absent capability use the unchanged
RVV path. Selection happens before hidden state is changed; a fault after a
command starts invalidates AKV and returns through the existing exception
contract rather than silently recomputing partial output.

## 10. Implementation status and order

1. Completed: freeze strict Stage-2 numerical and strongest-RVV baselines.
2. Completed: add ABI/reference-model Query-update semantics and negative tests.
3. Completed: add the engine command with atomic context invalidation and
   strict counters.
4. Completed: prove command behavior with generic SRAM, target macro SRAM,
   synthesis-wrapper, and complete `ara_tb` elaboration checks.
5. Next: convert the shared AKV workspace and RVV helpers to F32 numerator
   state.
6. Next: implement the K/V-outer software schedule with real captured tensors.
7. Then measure one short discriminating point and P0/M512 RTL if the hypothesis
   survives.
8. Finally regress Decode AKV, nine QBS profiles, ordinary RVV, tails, faults,
   and all supported D/GQA shapes before GGML selector integration.
