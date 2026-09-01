# Prefill Attention Stage-1 Evidence and Decision Gate

## 1. Scope

This stage determines whether Prefill Attention warrants a new AKV hardware
operation before changing RTL. It uses data captured from a real
llama.cpp Qwen2.5 execution and compares the ordinary RVV kernel with a
functionally equivalent schedule built from the existing AKV-v2 commands.

This stage deliberately does not:

- add an instruction or change RTL;
- claim performance from a traffic projection alone;
- extrapolate a short-prompt result to long-context Prefill; or
- run synthesis or physical design.

The decision is based on three evidence classes: source-level command-path
inspection, exact traffic/state accounting, and a focused cycle-accurate RTL
measurement.

## 2. Representative Real-Model Case

The numerical case is captured from
`Qwen2.5-1.5B-Instruct-Q4_K_M` at the llama.cpp `attention_core` boundary.
The tensor topology is:

| Tensor | Type | GGML shape | Interpretation |
|---|---:|---:|---|
| Query | F32 | `[128, 15, 12, 1]` | head dimension 128, 15 prompt tokens, 12 Query heads |
| Key | F16 | `[128, 256, 2, 1]` | physical KV capacity 256, 2 KV heads |
| Value | F16 | `[128, 256, 2, 1]` | same topology as Key |
| Mask | F16 | `[256, 15, 1, 1]` | one causal row per Query token |
| Output | F32 | `[1536, 15, 1, 1]` | 12 output heads per token |

The GQA ratio is six Query heads per KV head. The mask is validated as an
exact visible-prefix/blocked-tail causal mask. Its active prefixes are
`1, 2, ..., 15`; the analysis rejects a hole in any prefix or a non-causal
progression.

The seven-model graph census provides shape and chunking diversity rather than
additional tensor-level numerical goldens. It revalidates 28 immutable real
llama.cpp Host traces at target effective-KV lengths 16, 128, 512, and 1024.
The corresponding prompt lengths are 15, 127, 511, and 1023 tokens. llama.cpp
executes the 1023-token prompts as two Prefill chunks, `(M=512,P=0)` followed
by `(M=511,P=512)`, so the census contains 35 observed Prefill chunks:

| Model | D | Hq | Hkv | GQA | Observed M | Observed P | Target disposition |
|---|---:|---:|---:|---:|---:|---:|---|
| Qwen2.5-1.5B | 128 | 12 | 2 | 6 | 15/127/511/512 | 0/512 | candidate |
| TinyLlama-1.1B | 64 | 32 | 4 | 8 | 15/127/511/512 | 0/512 | candidate |
| SmolLM2-135M | 64 | 9 | 3 | 3 | 15/127/511/512 | 0/512 | candidate |
| Llama-3.2-1B | 64 | 32 | 8 | 4 | 15/127/511/512 | 0/512 | candidate |
| Gemma-3-1B | 256 | 4 | 1 | 4 | 15/127/511/512 | 0/512 | D256 gate/fallback |
| Phi-3.5-Mini | 96 | 32 | 32 | 1 | 15/127/511/512 | 0/512 | candidate |
| OLMoE-1B-7B | 128 | 16 | 16 | 1 | 15/127/511/512 | 0/512 | candidate |

All 35 graph records directly show F32 Query/output and F16 Key/Value/mask,
with GGML shapes `Q=[D,M,Hq,1]`, `K/V=[D,K,Hkv,1]`,
`mask=[K,M,1,1]`, and `output=[D,Hq,M,1]`. The graph trace does not record byte
strides or mask payload, so those fields are not promoted to measured facts.
The exact Qwen M15 capture separately validates contiguous byte strides and
causal prefixes 1 through 15. The target fast contract accepts D64/D96/D128
and GQA1..8; D256 remains a fallback until it passes the long-Prefill
performance gate. Only the Qwen case currently has raw tensors and a golden
output attached to RTL runs.

## 3. Exact Work and Traffic

For causal prefixes `1..15`, the sum of visible KV tokens per Query head is
120. The case therefore performs:

- 1,440 visible Query-head/KV-token pairs;
- 184,320 score MACs;
- 184,320 value MACs; and
- 368,640 total attention MACs.

The following values count K and V payload only. They are not cycle estimates.

| Schedule | K/V bytes | Reduction vs RVV | Additional state requirement |
|---|---:|---:|---|
| Query-head-serial RVV | 737,280 | 1.00x | one Query row |
| Existing-command GQA-serial AKV | 122,880 | 6.00x | six GQA rows |
| Two-Query tile | 72,704 | 10.14x | 12 concurrent rows, exceeds current limit |
| Four-Query tile | 39,936 | 18.46x | 24 concurrent rows, exceeds current limit |
| One resident K/V tile, Query-only update | 15,360 | 48.00x | six rows; new command semantics |

The Query-only schedule reaches the unique-visible-K/V floor for this case:
each KV head's 15 K/V rows is fetched once, while successive Query groups and
causal masks are applied to the resident tile. It does not require multiple
Query tokens to keep concurrent accumulators.

## 4. Why Existing AKV-v2 Cannot Express the Resident Schedule

Static inspection of `akv_attention_execute_v2_native()` and
`akv_engine.sv` shows the following command semantics:

- `V2_FULL` reads a descriptor and fills Query plus the first K/V tile;
- `V2_REFILL` replaces the resident K/V tile for a later sequence range;
- row/column loads replay resident data into the standard vector path; and
- `RELEASE` invalidates the context.

There is no operation that atomically replaces all Query rows while retaining
the current K/V tile. The benchmark compatibility path must consequently run
one complete AKV-v2 context for every `(token, KV-head)` pair. This schedule is
functionally useful as a measured lower-risk baseline, but it refetches the
same causal K/V prefixes and pays repeated descriptor/FULL/RELEASE overhead.

## 5. Falsifiable Hypothesis

The stage-2 candidate is a **Query-only context update** for an already valid
AKV-v2 context. The hypothesis is:

> For short Prefill in which the maximum visible prefix fits one 64-token AKV
> tile, repeated K/V fill traffic and context setup materially constrain the
> existing-command schedule. Retaining K/V while replacing Query rows will
> reduce both external K/V bytes and total cycles without adding concurrent
> accumulator rows.

Signals and counters that distinguish this from alternatives are:

- `v2_full` and `release` command counts;
- `q_external_bytes` and `kv_external_bytes`;
- command busy cycles and read backpressure cycles;
- score/value compute phase cycles; and
- total operator cycles with an unchanged golden-output comparison.

If K/V and setup are not on the critical path, traffic falls but cycles do not.
That result rejects the performance hypothesis and prevents an unjustified RTL
extension.

## 6. Focused Experiment

Both RTL runs use the same capture, L2 configuration, simulator family, and
golden comparison:

1. `rvv_qhead_serial`: ordinary RVV attention;
2. `akv_gqa_serial`: token-serial compatibility schedule using only existing
   AKV-v2 FULL/REFILL/LOAD/RELEASE semantics.

The benchmark extension supports `tokens > 1` by following the captured GGML
layouts exactly: Query is indexed as `[D, M, H]`, output as `[D*H, M]`, and
each token uses its own `[KV, M]` mask row. Decode (`M=1`) retains the same
address expressions as before.

The generated artifacts are kept outside prior result directories under
`hardware/prefill_attention_stage1_runs/` and
`hardware/prefill_attention_stage1_20260901/`. The analyzer records SHA-256
values for the case, all five tensor payloads, and attached RTL logs.

An initial full-M15 AKV attempt is invalid evidence: the application ELF
requires 1,505,432 bytes above `0x80000000`, while the reused simulator was
compiled with the default 1 MiB L2. That older testbench did not terminate on
the out-of-range load, allowing data aliasing and producing 10,247 output
mismatches. It is excluded from both correctness and performance results.

To discriminate a datapath error from the capacity mismatch, the first six
real Query tokens were replayed with the same K/V tensors and causal prefixes
1 through 6 on a simulator compiled with a 16 MiB L2. This M6 case passed the
complete golden-output comparison in 180,786 operator cycles. A focused
token-5 probe checked all 256 K dimensions across the two KV-head contexts;
every gathered value matched the context-fill value. This rejects the earlier
token-5 bank/gather hypothesis. The complete M15 matched-L2 run subsequently
passed, closing the capacity-controlled correctness test.

## 7. Decision Gate

Proceed to a Query-only hardware command only if all of the following hold:

- ordinary RVV and existing-command AKV both match the captured golden output;
- the existing-command AKV schedule improves operator cycles by at least 1.20x
  over ordinary RVV, or measured counters show a dominant and removable setup
  or K/V-read component hidden by current total cycles;
- a model-level profile gives Prefill Attention at least 10% of the target
  phase cycles for the prompt/context regime being claimed; and
- Decode and ordinary RVV fallback regressions remain unchanged.

For maximum visible prefixes above 64, Query-only update alone is insufficient:
`REFILL` overwrites the resident K/V tile. Long-context Prefill requires either
multiple concurrent Query states streamed across K/V tiles, a larger resident
store, or a separate tiled schedule. That is a distinct design decision and is
not implied by this short-Prefill experiment.

## 8. Reproduction

Static analysis and its unit tests:

```bash
python3 -m unittest hardware/scripts/akv/test_analyze_prefill_attention.py

python3 hardware/scripts/akv/analyze_prefill_attention.py \
  /home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/replay/cases/operator/prefill/attention_core/case.json \
  --query-tiles 2,4 \
  --measurement \
    rvv_qhead_serial=hardware/prefill_attention_stage1_runs/decode_attention_core_rvv_kv256_20260901_062809/ara.log \
  --measurement \
    akv_gqa_serial=hardware/prefill_attention_stage1_20260901/m15_rtl_16m_runs/decode_attention_core_akv_v2_kv256_20260901_080838/ara.log \
  --output-dir hardware/prefill_attention_stage1_20260901

python3 hardware/scripts/akv/census_prefill_shapes.py \
  --output hardware/akv_prefill_shape_census_20260901
```

The RTL commands set `LLAMA_ATTN_CASE_ID` to
`operator/prefill/attention_core`, set `Q4KM_CAPTURE_ROOT` to the Qwen capture,
and invoke `run-ara-attention-core.sh` with `rvv` and `akv_v2`, respectively.
The exact command, source commit, dirty-state flag, ELF hash, simulator hash,
capture manifest hash, simulator L2 capacity, and ELF L2 requirement are
retained in each run's `run.conf`. The runner refuses to start when the ELF
load span exceeds the simulator's compiled L2 capacity.

## 9. Measured Result

The matched 16 MiB ordinary-RVV and existing-command AKV-v2 M15 runs both pass
the complete captured golden-output comparison with zero mismatches. RVV takes
1,131,610 operator cycles; AKV-v2 takes 475,640 cycles, a measured 2.379x
speedup. The AKV-v2 run records 30 FULL commands, 30 RELEASE commands, 240 row
loads, and 3,840 column loads. Its strict traffic counters report 46,080 Query
bytes, 122,880 external K/V bytes, and 122,880 replay bytes, exactly matching
the GQA-serial schedule. No command reports a validation or read fault.

The M6 diagnostic remains supporting cycle-level evidence: it passes in
180,786 operator cycles, and its focused K/token-5 probe checks all 256 K
dimensions across two KV-head contexts with zero mismatches. The old 1 MiB M15
result is invalid and excluded. The matched-L2 result passes the Stage-1
correctness and 1.20x kernel-speedup gates. The model-share gate and the strong
tiled-RVV comparison remain pending and are evaluated with the long-Prompt
matrix rather than inferred from this short M15 point.
