# Bounded 64-Query-Block Prefill Reuse

## 1. Design decision

This note records the retained long-Prompt Prefill Attention schedule, the
alternative that was rejected by measurement, and the exact software/RTL
contract used to evaluate it.

The retained mechanism keeps one 64-token K/V tile in AKV-v2 while a bounded
software Query block consumes that tile. All QK, online Softmax, and PV
arithmetic still executes on the standard RVV lanes. The design does not add
an Attention MAC array and does not change ordinary RVV behavior.

The fixed bounds are:

- one GQA group with 1 through 8 Query heads;
- one 64-Query software block;
- one resident 64-token K/V tile;
- D64, D96, or D128;
- F32 Query, output, and online-Softmax state;
- F16 K, V, mask, and temporary Query rows; and
- a 137,472-byte aligned workspace independent of M, P, and KV length.

The application output remains software-visible storage and naturally scales
with the model shape. No hidden hardware state grows with the prompt.

## 2. Why Query-only context update was rejected

AKV-v2 physically separates Query rows from the resident K/V tile, so a
Query-only update initially appeared to permit a global K/V-outer schedule:

```text
for each K/V tile:
    retain K/V
    update Query rows for every visible Query token
    run QK, Softmax, and PV
```

The proposal was implemented as a distinct fill mode and tested on the real
Qwen2.5 D128, GQA6, P0/M15 capture. The discriminating measurements were:

| Schedule | Cycles | External Q | External K/V | Local replay |
|---|---:|---:|---:|---:|
| direct AKV-v2 | 507,201 | 3,072 B | 15,360 B | 176,640 B |
| Query update | 510,334 | 46,080 B | 15,360 B | 176,640 B |
| strong tiled RVV | 542,674 | n/a | n/a | n/a |

The Query-update schedule was 3,133 cycles, or about 0.62%, slower than the
direct path. It did not reduce K/V traffic at this one-tile point and added
43,008 bytes of Query traffic. Static RTL tracing also confirmed that the QK
microkernel reads the selected Query row through ordinary scalar/RVV memory
accesses; updating the hidden Query store did not remove those reads.

This result rejects Query update as the retained primitive. The command,
capability bit, counters, reference behavior, and RTL state were removed.
AKV-v2 returns to the smaller FULL/REFILL/row-load/column-load/RELEASE contract.

## 3. Retained dataflow

The retained schedule moves reuse into a fixed software block:

```text
for each KV head:
    map its GQA Query heads
    for each Query block QB of at most 64 tokens:
        convert QB from F32 to a fixed F16 workspace
        initialize F32 max, denominator, and output numerator

        block_prefix = past_tokens + QB.start + QB.count
        for each 64-token K/V tile below block_prefix:
            FULL for tile zero, otherwise REFILL

            for each Query token q in QB that can see this tile:
                load q directly from the workspace
                read resident K by token-axis columns
                compute QK on RVV lanes
                apply scale and q's causal mask
                merge stable F32 online-Softmax state
                read resident V by rows
                update the F32 output numerator on RVV lanes

        RELEASE the context
        normalize the block's outputs by their F32 denominators
```

The K/V tile is therefore fetched once per Query block and KV head, rather
than once per Query token. A later Query block may need a longer causal prefix,
so it starts a new bounded context and walks all visible tiles again. This is
not the unique-K/V traffic floor, but it is bounded, requires no new command,
and removes most serial-AKV rereads.

The existing FULL contract requires Query rows. For each block it reads the
first local Query group as context-seeding payload. QK for every local Query,
including the first, uses the software workspace directly. Those seed bytes
are included in the strict `q_external_bytes` model and are not claimed as
useful Query-cache hits.

## 4. Fixed workspace and layouts

The public Prefill problem uses contiguous batch-one tensors:

```text
Query   F32 [query_heads][query_tokens][head_dim]
Key     F16 [kv_heads][kv_capacity][head_dim]
Value   F16 [kv_heads][kv_capacity][head_dim]
Mask    F16 [query_tokens][kv_capacity]
Output  F32 [query_tokens][query_heads][head_dim]
```

The fixed workspace is:

```text
query      F16 [8][64][128]  = 131,072 B
plan                            = 192 B
score      F32 [8][64]        = 2,048 B
maximum    F32 [64][8]        = 2,048 B
sum        F32 [64][8]        = 2,048 B
old_scale  F32 [8]            = 32 B
total, including layout        = 137,472 B
```

The `query[head][token][dimension]` layout gives one contiguous vector per
Query head. The stride between two heads for a fixed local token is 16 KiB.
The QK helpers receive that stride explicitly and support GQA1 through GQA8.

The output buffer holds the current block's F32 numerator in place. It is
initialized before the first tile, rescaled after each tile, and normalized
only after the final tile. This avoids a second output-sized hidden buffer.

## 5. Stable online Softmax

For each Query head and tile, software maintains:

```text
m_new = max(m_old, max(score_tile))
a     = exp(m_old - m_new)
w_j   = exp(score_j - m_new)
l_new = a * l_old + sum_j(w_j)
o_new = a * o_old + sum_j(w_j * V_j)
```

`m`, `l`, and `o` are F32. A never-initialized state uses
`m_old=-infinity` and `a=0`. The active token count is:

```text
min(64, past_tokens + query_index + 1 - tile_start)
```

and a tile is skipped when that value is not positive. Consequently:

- no future token contributes to QK, denominator, or PV;
- a 1..64 tail has one explicit VL;
- every tile merge is numerically stable;
- state survives any number of K/V tiles; and
- final normalization occurs exactly once.

F16 numerator state is intentionally not used. On long real captures it caused
errors around 1.7e-2, while F32 state stayed near the configured 1e-5-scale
focused tolerance.

## 6. Validation and failure behavior

Selection and validation happen before output is modified. The implementation
requires:

- non-null, non-overlapping Query, K, V, mask, output, and workspace ranges;
- a finite positive scale;
- batch one and at least two Query tokens;
- integral `query_heads / kv_heads` in 1..8;
- D64, D96, or D128 advertised by the AKV-v2 capability;
- F32-aligned Query/output, F16-aligned mask, and 32-byte-aligned K/V;
- sizes and address ranges representable without integer wraparound; and
- a dense causal-prefix mask.

The first Query row determines `past_tokens = first_prefix - 1`. Every later
row must expose exactly `past_tokens + query_index + 1` finite entries,
followed by F16 negative infinity. Non-prefix, ALiBi, soft-cap, sink, unsupported
dtype/stride, and unsupported D/GQA cases use the unchanged RVV fallback.

Every `(KV head, Query block)` descriptor is preflighted before output writes.
Once native execution begins, a command fault follows the existing AKV
exception contract and invalidates the hidden context; software does not
silently recompute a partially modified output.

## 7. Hardware command contract

No Prefill-specific command remains. The schedule uses the existing AKV-v2
profile:

- `V2_FULL(descriptor, tile_start)` reads descriptor, Query seed rows, and
  one 1..64-token K/V tile;
- `V2_REFILL(tile_start)` retains shape and Query metadata while replacing
  only the K/V tile;
- `V2_COLUMN_LOAD(dimension)` returns the selected K column;
- the existing row load returns one resident V row; and
- `RELEASE` invalidates the context.

FULL and REFILL are blocking and commit atomically. Local row/column loads use
the normal VLSU lane-result path, so ordinary vector destination hazards,
backpressure, and completion rules remain in force. Standard RVV instructions
perform conversion, dot products, exponentiation, reductions, accumulation,
and final normalization.

## 8. Strict accounting

The performance log reports literal hardware events:

- `v2_full` and `v2_refill`: accepted context commands;
- `v2_column_load` and `v2_row_load`: accepted local replay commands;
- `release`: accepted releases;
- `q_external_bytes`: Query seed bytes accepted by the read engine;
- `kv_external_bytes`: K/V bytes accepted by the read engine;
- `replay_bytes`: bytes accepted by the normal lane-result path;
- `read_ranges`, `translations`, `ar`, and `r_beats`: translated
  external-read activity; and
- replay/read backpressure and outstanding occupancy counters: resource
  pressure, not additive stall partitions.

The static analyzer independently derives exact expected values from the real
capture. Strict validation fails if any command or byte count differs. Old
logs containing removed Query-update fields are not part of the current
schema.

One column command replays the entire active resident tile, not one scalar.
For a tile of T tokens it contributes `2*T` replay bytes. One V-row command
contributes `2*D` replay bytes. This distinction explains why local replay
can dominate after external K/V traffic is reduced.

## 9. Exact Qwen2.5 P0/M1024 projection

For D128, Hq=12, Hkv=2, GQA6, M=1024, P=0:

| Quantity | Exact value |
|---|---:|
| Query blocks | 16 |
| Sum of block maximum prefixes per KV head | 8,704 |
| Query-tile visits across two KV heads | 17,408 |
| `V2_FULL` | 32 |
| `V2_REFILL` | 240 |
| K-column commands | 2,228,224 |
| V-row commands | 1,049,600 |
| releases | 32 |
| command records | 3,278,128 |
| external Query seed bytes | 49,152 B |
| external K/V bytes | 8,912,896 B |
| column replay bytes | 285,212,672 B |
| row replay bytes | 268,697,600 B |
| total replay bytes | 553,910,272 B |
| fixed allocated workspace | 137,472 B |

Serial AKV projects 537,395,200 external K/V bytes for the same capture. B64
therefore reduces that traffic by 60.29x, but still reads 8.5x the unique
1,048,576-byte K/V payload floor and retains all QK/PV arithmetic and local
replay. A 60.29x traffic reduction is not a 60.29x cycle prediction.

## 10. Falsifiable performance hypothesis

The retained hypothesis is:

> At a real M>=512 Prefill point, amortizing K/V fill over a 64-Query block
> reduces full Attention-core cycles by at least 1.20x relative to the
> strongest tiled-RVV implementation.

The hypothesis is accepted only with:

1. a complete golden comparison;
2. exact command and traffic counters;
3. cycles/token and total operator cycles;
4. separately reported Query conversion, QK, Softmax/reduction, PV, and final
   normalization activity;
5. RVV functional-unit utilization and VLSU/sequencer backpressure; and
6. no unexplained regression in Decode AKV, QBS, or ordinary RVV.

If K/V bytes match the projection but speedup is below 1.20x, the mechanism has
transferred the bottleneck to column/row replay, command setup, F32 state,
reductions, or backend pressure. Any additional hardware semantic must target
that measured critical path rather than assume K/V traffic is still dominant.

## 11. Verification status

Completed:

- real-capture static work, traffic, state, and workspace accounting;
- direct versus Query-update discriminating RTL measurement;
- removal of the losing Query-update ABI and RTL state;
- B64 software implementation with preflight and strict fallback;
- host runtime/alias/range tests;
- ABI generation contract;
- generic-SRAM AKV engine regression;
- target-macro SRAM AKV engine regression; and
- synthesis-wrapper elaboration without running synthesis.

Remaining acceptance work:

- complete the short B64 RTL discriminator and strict counter check;
- run a multi-tile focused point;
- run at least one real M>=512 full Attention-core RTL point;
- compare against ordinary and strong tiled RVV;
- integrate the selector into the real GGML Prefill path;
- complete D64/D96/D128 and GQA1..8 plus seven-model fallback census; and
- document measured performance, numerical tolerance, and unsupported cases.
