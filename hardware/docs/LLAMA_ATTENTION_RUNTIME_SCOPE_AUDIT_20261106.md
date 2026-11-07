# Whole-runtime Attention scope audit, 2026-11-06

## Decision

Keep the running quantized-KV phase experiment, but do not let it choose the
next whole-runtime optimization by itself. The four original complete Qwen3
board cases use **F16 K and V, native AKV v2, GQA2/D128** in both peers.
Output-Tile and a possible four-head quantized-PV successor do not execute on
those calls. F16 Attention's share of their runtime remains unmeasured; default
F16 storage does not establish that Attention dominates model latency.

This audit reads existing sources, receipts and raw logs only. It launches no
EDA, model, board or synthesis job and changes no existing sealed input.

## Frozen sources and routing

`G` below is the immutable build input directory:
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_output_graph_20261106_01`.
The inspected files match its `source-pins.json`. Its F16 `akv.cpp`, native C
and RVV assembly also match the corresponding board-build inputs under
`/home/wangwy/fpga_runs/qwen3_hw_sw_ab_20261104_01/inputs/{llama,ara}`.
No inference is drawn from the dirty live AKV assembly.

| Input relative to G | SHA256 |
| --- | --- |
| `llama/ggml/src/ggml-cpu/arch/riscv/akv.cpp` | `a2382b3a19a9c035428181c22a131ca18aaa466c153d9dc8006d7b43a75f97fb` |
| `llama/ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp` | `eaa86c14d300f20c9fb8c546d72e2aca3ac1ca1d56c98a60901b7d1a72b6e7a5` |
| `llama/ggml/src/ggml-cpu/ops.cpp` | `7e8dea5f434230002de9bc5817422ebcebda59207f7b691b385af961414a6b14` |
| `llama/ggml/src/ggml-cpu/common.h` | `db7c19747a28c819d18922aa43b91b224df3730e424e6d8a4cf4fd16bfb1db14` |
| `llama/src/llama-context.cpp` | `9f97b439415acffd07e6fd83343811e36a6beb90a9957a03b70d14003c8bf0ee` |
| `llama/src/models/qwen3.cpp` | `06f400665980d30fd357886a5d14b541adda06d159a5b7f0ce929ca36788778c` |
| `sdk/software/akv/src/akv_v2_native_riscv.c` | `aff613518b3495df363209beacf0940ef6d8b6c734f4851f63a7aa820d4f692c` |
| `sdk/software/akv/src/akv_v2_attention_rvv.S` | `0e90dccf193c43bcda367fa18813bedb1077e9790795635f9efa993871a20061` |

`ops.cpp:9074` first attempts `ggml_riscv_akv_flash_attn`. Quantized KV is
attempted inside `akv.cpp:687` **before** F16 runtime admission. Thus setting
`GGML_RISCV_AKV=0` alone does not disable quantized Attention. Both backends
require compilation and runtime admission; F16 cache defaults do not enable
AKV automatically. `llama-context.cpp:3534` defaults both cache types to F16.

| Actual input and phase | Admitted implementation | Otherwise |
| --- | --- | --- |
| F16 K/V, Decode M1 | AKV v2 when token-axis capabilities are available; auto can choose legacy v1, which requires D128/GQA6. Current Qwen3 GQA2 needs v2. | Ordinary GGML RVV; unsupported feature/layout/mask/capability is not silently admitted. |
| F16 K/V, Prefill M>=64 | AKV v2 causal-prefix schedule, 64-query blocks; no forced-v1 policy, sinks, bias or softcap. | Ordinary GGML. M2..63 specifically cannot take this F16 native Prefill route. |
| K Q4_0 or Q8_0, V Q8_0, Decode M1 | QBS DIRECT QK plus software/RVV Softmax/PV. Choose Output-Tile, Register-PV, Grouped-PV, or generic strided runtime; experimental choices are mutually exclusive. | Ordinary GGML quantized-KV path. |
| Same quantized types, Prefill M>1 | Separate `quant_prefill_ggml_execute` grouped causal-prefix runtime when compiled/enabled. **Not Output-Tile**, irrespective of its Decode flag. | Ordinary GGML quantized-KV path. |

Common quantized admission additionally requires one worker, NORMAL_MEMORY,
native QBS, VLEN1024/RNE/vstart0 and supported tensor/finite/mask/alias contracts.
QBS emulation is not native admission. AKV context locking precedes the QBS
DIRECT lock. Admitted failures are terminal, not invitations to retry fallback.

When the AKV attempt rejects, `ops.cpp:9124` selects ordinary F16/F32 Decode
split-KV at capacity >=512; Prefill can use tiled RVV at M>=64, otherwise the
one-chunk loop. Ordinary quantized KV cannot enter these F16/F32-only tiled
conditions. With Flash Attention disabled, the model's unfused graph also
bypasses this hook. An old simple per-token RVV fixture is not automatically
the strongest current GGML baseline.

## What remains in each complete Attention call

| Route | Remaining software, vector and serialization work; not measured fractions |
| --- | --- |
| F16 Decode | GGML feature/layout/prefix scan, mutex, F32-to-F16 Q conversion, workspace initialization and planning; serial FULL/REFILL; resident K column commands plus RVV widening QK; tile Softmax; V row commands plus half-precision output recurrence; RELEASE and F16-to-F32 normalization/store. |
| F16 Prefill | Full causal-mask validation and bounded-block preflight/planning; query preparation; KV fills shared across queries in each block; QK, tile Softmax, F32 PV accumulation, release/normalization. Qwen3 GQA2/D128 can use capability-selected F32 query PANEL4 QK. It is not the D128/GQA6 specialized two-query branch. |
| Quantized Decode | GGML mapping/finite/overlap checks and locking; Q8_0 query quantization; strided K panel gather/reuse; descriptor setup and synchronous QBS dispatch/completion; ordered coefficients; V decoding/PV and normalization. Output-Tile keeps two output heads resident and decodes V again for later head pairs. |
| Quantized Prefill | Per-call heap workspace allocation/free in the GGML adapter; admission, query quantization, bounded K panel packing, grouped QBS commands, shared V decode and causal per-row recurrence; scratch-to-output copies. Decode Output-Tile probes do not measure this allocation or schedule. |

The F16 implementation already has `vector_expf` (`native C:140`): a fixed RVV
polynomial/exponent construction with a small-term clamp, applied over a KV
tile. `apply_scale_mask_and_softmax` and its Prefill counterpart also use a
scalar `expf` for cross-tile old-maximum scaling and a widening F64 reduction.
This is **not** Output-Tile's scalar `expf` per head/token. Preserve that existing
F16 numerical definition, including Decode F16 versus Prefill F32 accumulator
behavior; do not substitute a new approximate exponential or transplant the
quantized recurrence under a bit-exact label.

FULL/REFILL move resident data; AKV's QK/PV arithmetic still uses ordinary RVV
resources. The new 256-bit QBS weight ingress does not turn the logical
128-bit AKV reader into a 32B/cycle F16 fill path. Handoff smoke is correctness,
not an F16 Attention bandwidth/performance measurement.

## Actual whole-model observations

`B=/home/wangwy/fpga_runs/optimization_board_proof_20261105_01`.
`B/final_e2e_observer_01/collection_000087` contains the four original candidate
and baseline UART/report pairs. Both use F16 K/V, Qwen3-1.7B Q4_K_M,
16 Q heads, 8 KV heads, D128 and one worker. Aggregate native coverage agrees
between peers, with no F16 fallbacks or v1 executions:

| Board case | Prompt / Decode runs | Native Prefill / Decode ops | First Decode visible KV |
| --- | ---: | ---: | ---: |
| Chinese facts | 135 / 41 | 28 / 1148 | 136 |
| Log diagnosis | 212 / 70 | 28 / 1960 | 213 |
| Long document | 676 / 33 | 56 / 924 | 677 |
| Longer answer | 174 / 94 | 28 / 2632 | 175 |

The long prompt runs Prefill M512/P0 then M164/P512. These are aggregate route
counters, not per-phase cycle attribution or a complete timestamped timeline.

Four-case board totals: prompt evaluation 4558.76303 -> 3310.94867 s; Decode
evaluation 2647.16506 -> 2141.96137 s; reported inference 7246.14 -> 5522.84 s.
They compare baseline `9ce1bce9...` against trace-hoisted candidate `d0a1bbfd...`
with the M4 preparation bundle explicitly enabled, on bitstream `86930e50...`.
**Both already use native QBS and native F16 AKV v2.** The 1.312031x inference
ratio is not an AKV-versus-RVV ratio or isolated hardware gain. Model load,
host elapsed, inference and prompt/Decode metrics have different boundaries;
do not force their sums to agree. Only the first case has original baseline
full-logits equality; all four check answers/work/native counts.

The separate board quantized full-answer comparison keeps Q4_0/Q8_0 KV fixed
and native QK in both peers: Register-PV/grouped-Prefill gives 1.169150x prompt
and 1.064938x Decode. It generates 55 tokens, not the original F16 case's 41;
it cannot be used for cross-format latency or quality equivalence.

## Timing ledger and limits

| Evidence | Available | Missing / non-transferable |
| --- | --- | --- |
| Original F16 board model | Complete prompt/Decode/inference times and native route/work counts above. | Attention share; admission/packing, KV fill, QK, Softmax, PV, normalization and command-front waits separately. |
| F16 canonical Decode, `verification/akv/results/canonical-decode-runtime-20261024.json` | Four derived-real shapes including D128/GQA2/L64; correctness, CSR and commands. | No new complete-call timing. Shared-storage replay explicitly records timing unavailable. |
| F16 canonical Prefill, adjacent `canonical-prefill-runtime-20261024.json` | 202315/190069/190352/201779 cycles; paired-F32-PV increment 1.062228x. | SmolLM2 D64, four queries; not Qwen3 or full M>=64 GGML admission, nor ordinary-RVV comparison. |
| Older F16 PANEL4 / paired-head experiments | Complete-call incremental measurements and retained negative refill-overlap result. | Mostly Qwen2.5/derived head groups, not current Qwen3 F16 stage attribution; ordinary RVV fixture is not strong tiled RVV. |
| Quantized Output-Tile native | GQA6/D128/T128 Register-PV -> Output-Tile 410489 -> 344633.5 cycles; QBS busy about 9300/call. | Residual is not expf/PV time. Captured model is Qwen2.5, not Qwen3 F16. |
| Running Attention phase experiment | Frozen same-ELF original/probed ABBA, 8 QBS commands and 768 output words/call; overhead control. | Await terminal numerical/CSR/protocol gates. Coefficients includes expf+recurrence; PV includes decode+accumulation. No F16 or quantized-Prefill attribution. |
| Output-Tile complete Qwen3 model | QEMU 911616 logits, 56 Prefill and 112 Decode calls per mode; actual quantized types and switches pinned. | Functional only. Both modes share grouped Prefill; F16 AKV is disabled. No model hardware throughput. |

The source Qwen3 graph also contains embeddings, attention RMSNorm, Q/K/V
projections and Q/K head norms, RoPE, KV cache writes/conversion, output projection,
residual additions, FFN norm/gate/up/SwiGLU/down, final norm, vocabulary and
sampling. A layer has seven projections including attention output; the recent
seven-part Decode slice instead includes vocabulary and omits attention-output
projection. Neither that slice nor Attention timers cover the entire graph.

### Additional 112 MUL_MAT groups: existing Hadamard FWHT

The historical `graph-schedule-model-20261029-01/qemu.log` has 309 MUL_MAT
execution groups per graph: 197 quantized projections plus 112 Hadamard
rotations, four per layer. These are not LoRA or 112 additional dense GEMMs.
The pinned `ggml.h` hash is
`5dd0551fcd1a3992c1acd31870315b9e7222ed4e71e8b439b60d60d91c7671ac`.

`llama-graph.cpp:2760` rotates Q and K with the K basis, V with the V basis,
and the Attention output back with the V basis at line 2797. The first M40
graph's nodes 9/14/22/37 are respectively Q `[128,640]`, V `[64,640]`,
K `[128,320]`, and output `[64,1280]`; each shape occurs 28 times.
Decode shapes become `[128,16]`, `[64,16]`, `[128,8]`, `[64,32]`.

`llama-impl.h:57` sets `GGML_HINT_SRC0_IS_HADAMARD`. The actual instrumented
`ggml-cpu.c:1272` dispatches non-reference calls to
`ggml_compute_forward_fwht`, not the generic dense dot loop. The linked ELF
contains the tail jump at `0x251d86` to FWHT at `0x28fd06`. The F32 kernel in
`ops.cpp:11840` first scales/copies each row and then executes iterative
butterflies. It already has SIMD macros: `simd-mappings.h:1285` fixes RVV EPR=4,
and the ELF's later stages use `vsetivli zero,4,e32,m1` plus vector ADD/FMA.
Early passes also contain compiler-generated vector/scalar alternatives.
Thus the candidate is improving an existing FWHT vector implementation, not
introducing FWHT or assuming D-squared work. Preserve pre-butterfly scaling
and the existing FP operation/rounding sequence.

Quantized historical logs report both rotations enabled; the original board
F16 logs report both disabled. These transforms and their CONT/copy traffic
are outside the standalone post-cache Attention ROI. Add them to the ledger
before ranking further quantized-only changes. Do not disable rotations as a
same-semantics optimization: this changes quantization inputs and numerics.
The six graphs all contain 113 RMSNorm, 56 RoPE, 56 SET_ROWS, 28 FLASH_ATTN,
56 ADD, 28 GLU and 3 GET_ROWS groups in addition to the 309 MUL_MAT groups.
This is an operation census, never a QEMU cycle-share claim.

A usable ledger keys every row by actual model/phase/layer/shape/type/context,
backend, binary/image and timing boundary. Start with exact existing route and
call counts; keep unmeasured times null. Keep GGML admission/lock/cleanup and
KV-cache writes outside the native-kernel interval explicitly. QBS busy is
nested in complete calls, not a second additive cost. Context length and causal
prefixes preclude multiplying one small slice by token count. No MAC/count
fraction is a runtime fraction, and no ratios from these cohorts multiply.

## Prioritized next step

1. Finish and interpret the already-running GQA6 quantized phase control only
   within its cohort. A four-head residency candidate may be prepared without a
   long run: for six heads it changes three decode passes to two, not all PV
   work by one third. Qwen3 GQA2 already has one pair; this alone supplies no
   benefit for its default F16 route or its two-head quantized group.
2. Make the next authorized attribution target **Qwen3 F16**, not another
   GQA6 quantized sweep: the first board-case Decode at visible136/GQA2/D128
   and the first native Prefill block of the M135/P0 call. Reuse the pinned
   original F16 runtime and numerical kernels. Observe outer admission/Q
   preparation, KV FULL/REFILL, QK, tile Softmax, PV and release/normalization;
   keep an uninstrumented same-ELF ABBA control and exact output/CSR/work gates.
   A one-KV-head block replay must be labelled a slice, not the full GGML node.
3. First locate/pin genuine F16 post-cache bytes for those boundaries. Existing
   quantized captures cannot be dequantized and relabelled F16 captures. The
   existing Qwen3 F16 M33 capture is below the GGML M64 native Prefill threshold;
   padding it does not prove the M135 route. If exact data were not retained,
   request a bounded capture using the existing model, not a new model or long
   full-RTL execution. No capture/build/measurement is authorized by this doc.

Choose an optimization only after F16 phase times and its share of a compatible
runtime ledger are known. SFU, additional PV registers or another integer dot
array are not justified by the current missing attribution.

## Evidence identities checked in this audit

- F16 board receipt `B/final_e2e_observer_01/result.json`:
  `de42f70355e9fe406e0393f0b5fa7d665fd8dce3751d644e8b1e1b99e047437b`.
- Quantized board receipt `B/native_answer_observer_06/result.json`:
  `a8ea54a347ec21a081b5d011af56e88af2c6c7f47949416cae72b2a8406ef9b7`.
- Quantized board grid `B/native_followup_observer_04/result.json`:
  `f43a2eb3ee98735e18257e0a1eaed016cad655d9ad9d6411ad87166798a42a40`.
- Rechecked these three collections' local pins/artifacts: 55/54, 180/28 and
  205/36 respectively, plus collection metadata expected/actual identities.
  Read the actual F16 baseline/candidate UART routing and timing records; this
  audit does not rerun inference or re-establish every historical model build.
- Local compact records: `verification/performance/evidence/output_model_20261106_01/result.json`,
  `output_gqa6_20261106_01/result.json`, `output_native_20261106_01/result.json`
  and `end_to_end_baseline_20261105_01/result.json`.

This is a new scope audit, not a relabelling of any old receipt, a new numerical
acceptance, or evidence that a performance phase campaign has completed.
