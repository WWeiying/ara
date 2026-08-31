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

The combined check executes one Qwen2.5-1.5B Q4_K_M prompt in three modes
inside the same QEMU guest:

1. ordinary RVV;
2. native QBS with ordinary RVV Attention; and
3. the same native QBS path with AKV-v2 Decode Attention.

Run it with:

```bash
hardware/scripts/akv/run-qemu-combined-model-check.sh
```

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

For the closed Qwen run, the calibrated Decode-token projection is 81,978,147
QBS cycles (94.54%), 1,031,518 AKV-v2 cycles (1.19%), and 3,700,824 remaining
ordinary-RVV cycles (4.27%). The QBS table uses a current-image Q4_K
FILL/REUSE/RELEASE point and a conservative current-image Q6_K DIRECT point.
These percentages are not QEMU time samples. The
single Prefill graph remains in the dynamic trace, but its non-QBS nodes are
outside the current complete calibration and therefore outside this share.

## Runtime selection

- no AKV environment variable: standard RVV fallback;
- `GGML_RISCV_AKV_EMULATE=1`: software functional emulation;
- `GGML_RISCV_AKV=1`: native capability query and AKV instruction execution;
- `GGML_RISCV_AKV_TRACE=1`: candidate, execution, group, and fallback counts.

The current native profile is deliberately strict: Decode only, F32 query,
F16 K/V/mask, F32 output, D=128, GQA ratio 6, one batch, no attention sinks,
no ALiBi bias, no softcap, and a finite active mask prefix followed only by
exact F16 negative infinity. GGML may use multiple CPU workers, but AKV v1 has
one hidden context: all workers select the same path, worker zero executes the
AKV groups, and the others wait at GGML's normal node barrier. Any unsupported
feature, shape, layout, capability, or invalid worker state remains on the
standard RVV path.
