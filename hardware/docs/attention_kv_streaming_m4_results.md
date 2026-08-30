# Attention/KV Streaming Milestone 4 Results

## 1. Scope and evidence boundary

Milestone 4 hardens the AKV v1 mechanism from milestone 3. It maps the hidden
payload to SRAM, verifies the complete read-fault and validation matrix, checks
coexistence with ordinary RVV and QBS, and measures scaling on real
Qwen2.5-1.5B Q4_K_M Decode Attention captures at effective KV lengths 16, 128,
and 256.

The performance numbers in this document are RTL simulation results. The area
and timing numbers are a standalone pre-layout Design Compiler check of only
`akv_context` at the TSMC 28 nm TT corner. They are useful implementation
evidence, but they are not full-chip PPA or post-route signoff results.

## 2. SRAM-backed resident context

The architectural capacity remains 6,144 bytes:

```text
8 Q rows x 128 F16 elements = 2,048 B
8 K rows x 128 F16 elements = 2,048 B
8 V rows x 128 F16 elements = 2,048 B
                                  -------
                                    6,144 B
```

`akv_context` presents this state as 192 logical rows of 256 bits. Consecutive
logical rows alternate between two single-port banks, so a compact 128-bit AXI
payload beat that crosses one 32-byte row boundary writes at most one row in
each bank. This avoids requiring a two-write-port memory.

Each logical bank contains 96 rows. Under `TARGET_SRAM_MC`, one bank maps to two
`TS1N28HPCPUHDSVTB64X256M1SWBSO` macros, for four macros total. The logical
payload is 49,152 bits and the four physical macros provide 65,536 bits. The
unused capacity is a consequence of the available 64-row macro depth, not
architectural state.

The write path is a two-stage pipeline:

1. stage 0 captures one compact payload beat, its byte strobes, slot, and
   logical offset;
2. combinational routing aligns the beat to one or two 256-bit rows; and
3. stage 1 registers bank request, address, data, and byte enables before they
   drive the SRAM macro interface.

AKV v1 accepts only F16 payloads and validates every base and stride as
halfword aligned. The alignment network therefore shifts in 16-bit rather than
unreachable byte-granular steps. It sustains one compact 128-bit beat per cycle.
`payload_complete` waits for the write pipeline to drain, so a successful full
or refill cannot expose a context before its final SRAM write commits.

Replay uses the SRAM synchronous read latency. One `REPLAY_READ` cycle selects
the logical row, and the following `REPLAY_WRITE` state sends the 256-bit word
through the existing LDU lane-result ports. No private VRF write path was
introduced. The existing sequencer allocation, destination hazard, byte-enable,
and completion rules therefore remain authoritative.

## 3. Fault and state semantics

The independent testbench checks all descriptor and payload sources through
the same `qbs_read_engine` used by the integrated design. It covers:

- D=64 and D=128 full, refill, and replay;
- aligned and base+2 F16-aligned source streams;
- replay backpressure and lane-by-lane completion;
- reserved descriptor fields, invalid dimensions, selector bounds, destination
  alignment, and empty-context access;
- descriptor, Q, K, and V MMU faults;
- descriptor, Q, K, and V PMA faults;
- descriptor, Q, K, and V AXI response faults; and
- recovery after every terminal fault without a partial destination write.

A failed full or refill invalidates the hidden context. A descriptor or payload
read fault also invalidates it because the replacement state was not committed.
An illegal local-load selector or destination is different: validation occurs
before any LDU write, the command reports an exception, and the previously
committed context remains valid. `akvrelease` succeeds for both ready and empty
contexts.

Fault injection exposed one issue in the shared read engine rather than in AKV
storage. If a younger planned range hit a PMA/MMU fault while older AXI
responses were still in flight, the engine froze burst metadata as it drained
those older responses. A legal older `RLAST` could then be compared with stale
`beats_left` and be misreported as an AXI protocol fault, replacing the real
planner fault. The corrected behavior advances metadata for older clean
responses during planner-fault drain, suppresses only repeated response checks
after a real response fault, and preserves first-fault ordering. A dedicated
QBS regression reproduces the older-clean-response plus younger-PMA-fault case.

## 4. Verification results

The following checks pass on the final SRAM-backed source:

| Check | Configuration | Result |
|---|---|---|
| generated AKV ABI contract | software/SV definitions | PASS |
| independent AKV engine | generic `tc_sram` | PASS |
| independent AKV engine | four physical SRAM macro models | PASS |
| shared QBS read engine | response/planner fault ordering | PASS |
| QBS profile matrix | 432 profile cases | PASS |
| QBS command/fault matrix | 22 functional cases plus faults | PASS |
| integrated AKV smoke | `qbs=1 akv=1`, 16 MiB simulation L2 | PASS |
| integrated QBS smoke | `qbs=1 akv=1` | PASS |
| ordinary RVV `vvaddint32` | `qbs=1 akv=1` | PASS |
| disabled AKV probe | `qbs=1 akv=0` | expected SKIP/PASS |
| QBS smoke with AKV disabled | `qbs=1 akv=0` | PASS |

The generic and physical-macro AKV tests both finish with the same message:

```text
AKV engine PASS: D64/D128 aligned/unaligned fill, refill/replay,
validation matrix, descriptor/Q/K/V MMU, PMA, and AXI faults
```

In the integrated smoke test, SRAM pipelining adds only the fixed write-pipeline
drain to fill operations. D128 full and refill take 339 and 152 busy cycles;
D128 and D64 local replay remain 25 and 13 cycles. The replay path itself did
not regress.

## 5. Real-model scaling

All points use the same Qwen2.5-1.5B Q4_K_M layer-0 Decode Attention captures,
`D=128`, 12 Q heads, two KV heads, and GQA group size six. The reference is the
ordinary one-dot-at-a-time RVV implementation on the same RTL environment.

| Effective KV | RVV operator cycles | AKV operator cycles | Speedup | Cycle reduction | Mismatches |
|---:|---:|---:|---:|---:|---:|
| 16 | 137,961 | 50,881 | 2.7114x | 63.12% | 0 |
| 128 | 796,177 | 382,001 | 2.0842x | 52.02% | 0 |
| 256 | 1,551,299 | 760,366 | 2.0402x | 50.99% | 0 |

The command and traffic counters are exact sums of per-command RTL records:

| Effective KV | full/refill/load/release | Q external bytes | K/V external bytes | local replay bytes | replay backpressure cycles |
|---:|---:|---:|---:|---:|---:|
| 16 | 2 / 2 / 256 / 2 | 3,072 | 16,384 | 65,536 | 2,048 |
| 128 | 2 / 30 / 2,048 / 2 | 3,072 | 131,072 | 524,288 | 16,384 |
| 256 | 2 / 62 / 4,096 / 2 | 3,072 | 262,144 | 1,048,576 | 32,768 |

Thus external Q+K/V traffic is 19,456, 134,144, and 265,216 bytes. All three
values exactly match the resident/reuse lower bound derived before RTL
implementation. Compared with the generic loop's targeted logical traffic,
the reductions are 12.63x, 14.66x, and 14.83x. Local replay is deliberately
reported separately and is not counted as external-memory savings.

The speedup decreases from the short KV16 result reported at milestone 3 to
about 2.0x at long contexts even though traffic elimination improves. This is
expected: the remaining ordinary RVV exponentials, output updates, instruction
dispatch, and 25-cycle local loads scale with every token. AKV removes repeated
external data movement and scalar score feedback; it does not add an Attention
arithmetic array.

## 6. Standalone implementation evidence

The retained halfword-alignment implementation was checked at 1.0 ns with
0.15 ns clock uncertainty, 0.10 ns input/output delay, the TSMC 28 nm TT
standard-cell library, and the 64x256 context SRAM library. The exact-source
standalone result before the synthesis pause was:

| Item | Result |
|---|---:|
| SRAM macros | 4 |
| logical / physical capacity | 49,152 / 65,536 bits |
| combinational area | 2,820.720 um^2 |
| sequential area | 1,898.064 um^2 |
| SRAM macro area | 28,332.289 um^2 |
| total cell area | 33,051.073 um^2 |
| worst setup slack | 0.00 ns, met |

The critical path runs from the registered halfword offset through the
alignment mux into the registered SRAM write data. A measured one-hot offset
experiment kept the same 0.00 ns reported slack while increasing total area to
33,789.265 um^2; it was therefore rejected. No additional pipeline stage was
added because the retained source already meets the standalone constraint and
an extra stage would add fixed fill latency without measured system benefit.

These figures exclude clock-tree insertion, placement, routing, full-chip
congestion, and hold repair. The apparent zero-slack result is not timing
margin and must not be presented as post-layout closure. Full-chip DC and P&R
remain separate work; no synthesis was rerun after the explicit pause request.

## 7. Reproduction

Focused contract and RTL checks:

```bash
make -C verification/akv contract-check
make -C verification/akv rtl-check
make -C verification/akv rtl-macro-check
```

Representative integrated checks use an image built with `qbs=1 akv=1`:

```bash
hardware/sim_akv_m4_final/simv +NO_FSDB +AKV_PERF \
  +PRELOAD=$PWD/apps/bin/akv_context_smoke +TESTCASE=akv_context_smoke

hardware/sim_akv_m4_final/simv +NO_FSDB +QBS_PERF \
  +PRELOAD=$PWD/apps/bin/qbs_control_smoke +TESTCASE=qbs_control_smoke

hardware/sim_akv_m4_final/simv +NO_FSDB \
  +PRELOAD=$PWD/apps/bin/vvaddint32 +TESTCASE=vvaddint32
```

Real-model points use independent output directories:

```bash
LLAMA_ATTN_SIM_DIR=$PWD/hardware/sim_akv_m4_final \
LLAMA_ATTN_RUN_ROOT=$PWD/hardware/llama_attention_runs_akv_m4 \
hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh \
  akv 128 --ara-only
```

KV256 changes only the second argument. Runs expected to exceed ten minutes
must be launched in independent background directories and inspected only
after completion.

## 8. Remaining boundary

Milestone 4 establishes functional, fault, scaling, and block-level physical
evidence for AKV v1. Milestone 5 subsequently integrates strict
shape/type/capability selection into the GGML RISC-V backend, retains ordinary
RVV fallback, and reports model-level operator coverage. A portable multi-row
tiled-RVV software baseline remains necessary for finer performance
attribution; see `attention_kv_streaming_m5_results.md`.
