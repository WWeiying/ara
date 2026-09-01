# AKV llama.cpp integration checks

This directory contains the reproducible software-side validation for the
Attention/KV streaming (AKV) mechanism. It does not run synthesis.

The AKV-v2 token-axis design-space model is independent of simulation and also
does not invoke synthesis, area, or timing tools:

```bash
hardware/scripts/akv/akv_v2_design_model.py
```

Its exact structural counts and the interpretation boundary for projected
cycles are documented in `hardware/docs/attention_akv_v2_design.md`.

## AKV-v2 RTL operator check

The token-axis implementation is measured with real Qwen Attention captures;
it does not use synthetic K/V values or software K packing. Build one reusable
simulation image and run each context length in its own result directory:

```bash
make -C hardware compile akv_v2=1 no_fsdb=1 \
  buildpath="$PWD/hardware/build_akv_v2_compile" \
  sim_dir=sim_akv_v2_compile

LLAMA_ATTN_RUN_ROOT="$PWD/hardware/llama_attention_runs_akv_v2" \
LLAMA_ATTN_SIM_DIR="$PWD/hardware/sim_akv_v2_compile" \
  hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh \
  akv_v2 16 --ara-only
```

Use the same command with `128` or `256` for the long points. Launch any run
expected to exceed ten minutes in the background and do not poll it. Aggregate
only completed runs with:

```bash
hardware/scripts/llama_q4km_extract/summarize-ara-attention-core.py \
  --run-root hardware/llama_attention_runs_akv_v2 \
  --output hardware/llama_attention_runs_akv_v2/attention_core_summary.csv
```

The summary reads `[AKV_PERF]` records directly from `ara.log`. It therefore
preserves FULL/REFILL, K-column and V-row command counts, K-view bank cycles,
conflicts, rejected commands, external Q/K/V bytes, and local replay bytes in
addition to the whole-operator LLM counters. `run.conf` records source, capture,
ELF, and simulator provenance.

## Build

Build a static RV64GCV `llama-simple` with ordinary RVV, QBS, and AKV compiled
into the same CPU backend:

```bash
hardware/scripts/akv/build-llama.sh
```

AKV requires `Zfh` and `Zvfh` because its strict profile consumes F16 Q/K/V
data and performs F16/F32 conversion. QBS remains independently selected by
its own runtime capability and shape checks.

## Isolated AKV model check

The QEMU check runs the same Qwen2.5-1.5B Q4_K_M model and prompt twice. The
first execution leaves AKV disabled and follows the standard RVV path. The
second sets `GGML_RISCV_AKV_EMULATE=1`. QBS is disabled in both executions so
the comparison isolates Attention dispatch. The check requires a nonzero AKV
execution count, identical generated text, complete logits records, and equal
top-1 logits at every decode step. It also requires the maximum absolute
logits difference to be at most 0.001 by default and reports both maximum
absolute and relative differences:

```bash
hardware/scripts/akv/run-qemu-model-check.sh
```

Each invocation writes its binary disk, initramfs, command log, and result to a
new directory under `hardware/akv_jobs/qemu_model_*`. A run expected to exceed
ten minutes should be launched with `nohup` in the background and not polled.
A completed serial log can be validated without rerunning QEMU:

```bash
hardware/scripts/akv/run-qemu-model-check.sh --check-log path/to/qemu.log
```

The optional `AKV_LOGITS_MAX_ABS_TOLERANCE` environment variable changes the
threshold only for experiments with a separately justified numerical contract.
For a new run, the script compiles the selected threshold into the guest checker
and applies the same value again during host log validation, so
`LLAMA_GUEST_EXIT=0` and the final host verdict have the same numerical meaning.

The emulation path validates GGML graph selection, shape/layout checks, shared
runtime planning, and model-level numerical behavior. Its query-key dot,
F16 accumulator scaling, and F16 value accumulation deliberately reuse the
same GGML RVV helpers as the standard path. It is still neither a
cycle-accurate model nor an instruction-order numerical model of the native
assembly because the native kernel uses its own vector exponential
approximation. Native numerical error and performance are measured with the
shared assembly kernel on the real-model RTL operator benchmark.

## Combined QBS + AKV-v2 model closure

The combined check executes one model and one explicitly recorded prompt in three modes
inside the same QEMU guest:

1. ordinary RVV;
2. native QBS with ordinary RVV Attention; and
3. the same native QBS path with AKV-v2 Decode Attention.

Run it with:

```bash
hardware/scripts/akv/run-qemu-combined-model-check.sh
```

Override `AKV_MODEL_DISK`, `AKV_MODEL_GUEST_PATH`, and `AKV_MODEL_PROMPT` to
run another GGUF image. The manifest records the exact prompt, token count,
model image, llama binary, QEMU binary, revisions, and hashes. Host validation
rejects a run when the three child executions tokenize the prompt differently.

`QBS_ONLY` and `QBS_AKV_V2` start from the same generated context. Their text,
top-1 token, and logits must match exactly, which isolates AKV-v2 from the
known numerical-order difference between QBS and the ordinary RVV baseline.
Graph tracing associates every QBS and AKV call with its owning GGML node. The
closure checker rejects a run unless every supported `MUL_MAT` node has a QBS
call, every Decode `FLASH_ATTN_EXT` node has exactly one AKV-v2 call, QBS has no
fallback, and every non-executed AKV candidate is explained by an explicit
fallback counter. Prefill Attention remains a deliberate shape fallback.

After the guest run, combine exact dynamic work with representative real-model
RTL leaf measurements:

```bash
run=hardware/akv_jobs/qemu_model_combined_latest
hardware/scripts/akv/summarize-model-closure.py "$run/qemu.log" \
  --qbs-calibration \
    hardware/qbs_akv_goal_final_calibration_20260831/results.csv \
  --akv-calibration "$run/akv_v2_rtl_calibration_final.csv" \
  --rvv-calibration-dir \
    hardware/model_closure_rvv_calibration_compute_only_full_v2/operator_ara_latest \
  --output-dir "$run/model_closure_final"
```

The generated `dynamic_summary.json` and call/node CSVs contain exact model
execution counts. `cycle_projection_{detail,summary}.csv` is a calibrated
projection: QBS uses unique activation and dot work, AKV-v2 uses active-KV
interpolation, and remaining Decode nodes use compute-only RVV leaves. It is
not QEMU wall time or a claim of full-model RTL simulation. Decode completeness
is enforced by default; uncalibrated Prefill nodes remain explicitly listed.
The output snapshot records hashes for the attribution tool, dynamic log, run
manifest, model and QEMU binaries, source revisions, and every RTL calibration
log, together with an explicit projection-method version.

Do not copy a percentage from an older run. Use the generated
`model_closure.md` and `calibration_snapshot.json`: the projection changes with
the prompt's Prefill length, active KV length, lifetime accounting, and selected
RTL calibrations. These percentages are never QEMU time samples. Prefill nodes
without matching RTL leaves remain outside complete-phase share tables.

The final goal-level audit consumes all model, shape-matrix, QBS regression,
ordinary-RVV, and representative AKV RTL artifacts through one manifest:

```bash
python3 hardware/scripts/akv/check-goal-closure.py
```

It writes `hardware/qbs_akv_model_closure_20260831/`. The checker verifies the
exact shape Cartesian product, model execution/fallback partition, QBS command
work, activation-lifetime byte accounting, the 1% representative regression
gate, and AKV command/traffic formulas. `artifacts.csv` hashes every consumed
raw artifact. This audit contains no synthesis, PPA, place-and-route, or
full-model RTL timing claim.

## Multi-model generality closure

`model-generality-manifest.json` defines a set with the same published
`Q4_K_M` GGUF quantization label spanning Qwen2, Llama-family, Gemma3, Phi3,
and OLMoE graphs. This controls the primary format class, not the publisher's
quantizer version, importance matrix, or calibration data. The OLMoE point
exercises real `MUL_MAT_ID`; unsupported Attention dimensions or GQA ratios
must fall back explicitly instead of being forced through AKV.
This is the model-architecture/topology axis of validation, not a seven-model
by nine-profile Cartesian product; the separate profile closure supplies the
format axis.

Capture one-token Decode graphs at four effective KV lengths and rank the real
QBS shapes with the checked RTL calibration:

```bash
host=hardware/qbs_akv_model_generality_host_stage1_20260831
hardware/scripts/akv/run-context-sweep.py \
  --manifest hardware/scripts/akv/model-generality-manifest.json \
  --output "$host" --models all --kv all --threads 16 --timeout 900
hardware/scripts/akv/select_qbs_representatives.py --input "$host"
```

When the hardware support rule changes, do not edit or reinterpret the old
capture directory. Re-evaluate its immutable real-model logs into a new output
directory with the current analyzer:

```bash
hardware/scripts/akv/revalidate-context-sweep.py \
  --source-root "$host" \
  --output hardware/akv_context_census_generalized_YYYYMMDD
```

The revalidator writes all 28 per-model/KV summaries, `dynamic_counts.csv`, a
model-level `support_matrix.csv`, and hashes of the source logs, prompts,
manifest, analyzer, and tool. Its provenance also freezes the exact admitted
head-dimension and GQA sets, so a later contract extension cannot silently
change the meaning of an older result.

The host census keeps workload and offload accounting separate. Fields named
`attention_candidate_*` include every Decode Attention node, including shapes
that must remain on RVV. Fields named `akv_shape_eligible_*` include only work
admitted by the current AKV contract. For `MUL_MAT_ID`, routed matrix rows,
resident all-expert weight capacity, and source-activation quantization rows
are also separate quantities; they must not be substituted for one another.
Legacy guest traces that omit the source tensor shape are marked
`unavailable_legacy_source_shape`; their routed matrix and command-dot work
remain usable, but activation quantization is taken only from the newer Host
graph trace.

Run each full model in QEMU with ordinary RVV, native QBS, and native QBS plus
the AKV functional-emulation backend. This is a long functional run; launch it
independently and do not poll it:

```bash
qemu=hardware/akv_jobs/model_generality_all_YYYYMMDD
nohup hardware/scripts/akv/run-model-generality-qemu.py \
  --models all --output "$qemu" >"$qemu.launch.log" 2>&1 &
```

The final summarizer requires one dynamic QEMU summary per manifest model. It
cross-checks the exact Host/QEMU operator counts, profile set, operator versus
native-command dot work, AKV Prefill/Decode partition, source/model-disk
hashes, complete Host matrix, representative-shape provenance, and the
existing timing-RTL closure. Each dynamic summary must also record the
SHA-256 of the current `summarize-model-closure.py`; summaries produced with
older accounting semantics are rejected instead of being mixed into a new
aggregate:

```bash
hardware/scripts/akv/summarize-model-generality.py \
  --host-root "$host" \
  --qbs-representatives "$host/qbs_representative_selection" \
  --qemu-summary qwen25_1p5b_q4km=path/to/dynamic_summary.json \
  --qemu-summary tinyllama_1p1b_q4km=path/to/dynamic_summary.json \
  --qemu-summary smollm2_135m_q4km=path/to/dynamic_summary.json \
  --qemu-summary llama32_1b_q4km=path/to/dynamic_summary.json \
  --qemu-summary gemma3_1b_q4km=path/to/dynamic_summary.json \
  --qemu-summary phi35_mini_q4km=path/to/dynamic_summary.json \
  --qemu-summary olmoe_1b7b_q4km=path/to/dynamic_summary.json \
  --output hardware/qbs_akv_model_generality_YYYYMMDD
```

The final directory archives the manifest, Host aggregate/provenance, all
model/KV Decode summaries, every QEMU dynamic summary, the checked QBS cycle
calibration, the representative selection, the final verification tools, and
the timing-RTL closure. Raw
QEMU logs, model disks, and build products remain external and are referenced
by hashes instead of copied into the compact result.

The frozen full-model result is `hardware/qbs_akv_model_generality_20260831/`:
7/7 QEMU models and 28/28 Host model/KV cases pass; 908,688 native QBS
commands and zero emulated QBS commands are observed. That artifact used the
older D64/D128 and GQA1/4/6/8 selector, so four model shapes execute AKV and
three use explicit shape fallback. It remains valid evidence for that frozen
contract and must not be relabeled as the generalized result.

The current host-side generalized census is
`hardware/akv_context_census_generalized_20260901_r4/`. All 28/28 model/KV
cases pass under the production D64/D96/D128 and GQA1..8 rule. Qwen2.5,
TinyLlama, SmolLM2, Llama-3.2, Phi-3.5, and OLMoE are shape eligible; Gemma-3
D256 remains an explicit shape fallback. This artifact proves real-graph shape
coverage only. Full-model QEMU numerics and native RTL cycles remain separate
evidence layers and are not inferred from the census.

The output includes `summary.json`, `dynamic_counts.csv`, `support_matrix.csv`,
and `provenance.json`. The summary records the seven-model/four-KV matrix,
execute-versus-fallback partition, aggregate candidate accounting, and hashes of
the three detailed artifacts. The `complete` marker is written only after all
four files have been generated successfully.

This layered result has a strict interpretation. Host graphs establish exact
workload coverage; QEMU establishes ISA/runtime functionality and numerical
behavior; directed RTL establishes datapath and protocol behavior. None of
these alone is a cycle-accurate full-model RTL measurement.

## Area-controlled generalization closure audit

The current generalization evidence is audited independently of the older goal
closure with:

```bash
python3 hardware/scripts/akv/check-generalization-closure.py --allow-pending
```

The manifest is
`hardware/scripts/akv/generalization-closure-manifest.json`; the generated
status is `hardware/akv_generalization_closure_20260901/summary.json`. Every
requirement is reported as `PASS`, `PENDING`, or `FAIL`. `--allow-pending` only
allows the audit file to be emitted while background or explicitly deferred
work remains; it does not turn `PENDING` into closure. Without that option the
tool exits with status 2 whenever any requirement is pending.

The host-census check is identity- and provenance-strict: it verifies the exact
seven model IDs, names, D/GQA shapes and execute/fallback dispositions; the
complete 7-model x 4-KV case matrix and candidate accounting; the hashes of the
support matrix, dynamic counts and provenance files; and the hashes of all 28
immutable source Host logs. Matching only the aggregate model/case counts is
not sufficient to pass.

Model-level evidence is layered rather than inferred. The audit first verifies
the frozen 7/7-model QEMU closure (908,688 native QBS commands, zero emulated
commands, and the historical four-execute/three-shape-fallback AKV partition),
then requires current generalized QEMU runs for SmolLM2 GQA3 and Phi-3.5 D96.
The latter two runs prove that the newly admitted shapes execute rather than
silently retaining their former fallback disposition.

The current non-physical audit reports 34 passing requirements, zero failures,
and one pending requirement. The sole pending item is the explicitly deferred
TSMC28 1 GHz physical closure; it is not treated as a functional pass. All six
integrated QBS representatives, including the long Prefill FFN-gate point, have
terminal passing results in the current simulator image.

After other long simulations release the VCS resources, rerun the four frozen
D64/D128, GQA1/4/6/8 non-regression points in one background worker with:

```bash
make -C hardware compile akv_v2=1 sim_l2_mb=16 \
  buildpath="$PWD/hardware/build_akv_d256_compile" \
  sim_dir=sim_akv_d256_compile no_fsdb=1

mkdir -p hardware/akv_generalization_regress_20260901
nohup hardware/scripts/akv/run-generalization-regression.sh \
  > hardware/akv_generalization_regress_20260901/launcher.log 2>&1 &
```

The worker uses the immutable derived-real Qwen capture and writes a terminal
`status`. The closure audit compares every current cycle count with its frozen
baseline and enforces the 1% maximum-regression gate. Before any point starts,
the worker also checks the VCS filelist and refuses a `simv` that predates an
RTL/build input. Each accepted result must record the same simulator path and
SHA-256 as the current binary, so an old executable cannot satisfy the gate.

## QBS cross-operator activation lifetime

The lifetime check runs the same real Qwen prompt twice with native QBS. The
baseline retains per-operation activation quantization; the second run reuses
one byte-identical Q8_K activation across eligible Q/K/V and gate/up matrix
operations. Run or recheck it with:

```bash
AKV_MODEL_MODE=qbs-lifetime hardware/scripts/akv/run-qemu-model-check.sh
AKV_MODEL_MODE=qbs-lifetime hardware/scripts/akv/run-qemu-model-check.sh \
  --check-log path/to/qemu.log
```

`compare_activation_lifetime_runs.py` rejects the pair unless the semantic QBS
command stream is unchanged, every baseline reuse group has one balanced
fill/release chain, and the reductions in quantization count and activation
bytes exactly equal the recorded reuse counters. It records both the removed
F32 quantization-input bytes and the removed Q8_K output bytes; these are
different traffic quantities. The generated
`qbs_cross_operator_summary.json` labels QEMU host quantization time as a
diagnostic only; it is not an RTL cycle measurement.

To incorporate lifetime data into model-level cycle attribution, pass the
paired summary explicitly:

```bash
hardware/scripts/akv/summarize-model-closure.py combined/qemu.log \
  --qbs-lifetime-summary lifetime/qbs_cross_operator_summary.json \
  --output-dir combined/model_closure_lifetime
```

The summarizer accepts the pair only when model path, model image, prompt,
token count, llama binary, QEMU binary, and source revision match. It then
matches each eliminated quantization to a concrete `op/type/M/N/K` node;
unmatched records are an error rather than a global proportional estimate.

## Runtime selection

- no AKV environment variable: standard RVV fallback;
- `GGML_RISCV_AKV_EMULATE=1`: software functional emulation;
- `GGML_RISCV_AKV=1`: native capability query and AKV instruction execution;
- `GGML_RISCV_AKV_TRACE=1`: candidate, execution, group, and fallback counts.

The current AKV-v2 production profile is deliberately strict: Decode only, F32
Query, F16 K/V/mask, F32 output, one batch, `D=64/96/128`, and `q_rows` (the
GQA ratio) from 1 through 8. Positive KV lengths are processed in 64-token
tiles, including one-token and non-multiple-of-64 tails. D96 uses the D-axis
tail capability in the existing D128 physical slot and does not increase
context capacity. The specialized assembly path is D128/six rows; other
admitted combinations use generic RVV arithmetic over the same AKV-v2
token-axis context and commands. Attention sinks, ALiBi bias, softcap,
incompatible layouts, malformed masks, or any unsupported state fall back
before hidden context state changes.

The original derived-real matrix still provides 112/112 passing scalar/RVV
cases over D64/D128, GQA1/4/6/8, and KV
16/63/64/65/128/256/1024. Generalization is additionally checked by the AKV
engine's generic- and macro-SRAM suites, a real SmolLM2 D64/GQA3 RTL leaf
(30,853 cycles, zero mismatches), and a real Phi-3.5 D96/GQA1 RTL leaf
(10,073 cycles, zero mismatches). These results prove correctness and
selection breadth, not uniform speedup for every admitted shape.

The runtime and directed tests implement D256 as two D128 score/value phases
using `d_offset`/`d_count`, partial-score accumulation, and K/V replay without
doubling context SRAM. The real Gemma D256 leaf passes with zero mismatches but
takes 47,191 cycles versus 36,043 for the strong tiled-RVV baseline (0.764x).
It fails the required 1.2x admission gate, so the production GGML selector and
host support matrix intentionally retain D256 as `fallback_shape`.
