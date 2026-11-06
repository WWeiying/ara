# End-to-end optimization experiments and evidence

Latest matrix integration: `collect_matrix_soc.py` audits the two completed
SoC builds without rewriting their original failed worker reports. It admits
only the proven single appended blank line, not different sources or macros.
The compact receipt is `evidence/matrix_soc_20261106_01/result.json`.

For actual Qwen3 projection inputs, use `run_projection_capture_v3.py` with a
fresh verification output directory. Earlier capture entries preserve two
pre-boot inventory failures. The accepted capture retains four distinct real
token rows and full K=2048; the GGUF host file and guest disk file are hashed
against one another. This is a capture, not a complete model inference.
`build_projection_native.py --capture <accepted-capture> --output <fresh-dir>`
builds the same SDK workload for both hardware images. Its independent host
reference compares row-major/R4 output bytes; no reference executor is linked
into the measured ELF. `run_projection_native.py --wide 0|1 --build <build-dir>
--output <fresh-dir> --execute-reviewed` is a directly owned bounded worker;
omitting the last flag performs preflight only. Each side uses two identical
Q/K/V workload trials, with preparation included and checks/printing excluded.
This is a cropped-N QKV SDK region, not whole-model timing or cold repack time.

`collect_projection_native.py --base <run> --wide <run> --output <fresh-dir>`
replays actual stage timings, captured-oracle checksums, independent protocol
results, source/image inventories and exclusive QBS phase counters.
`watch_projection_pair.py` takes the same arguments and waits on inotify file
events before calling that collector once, avoiding timed status polling.
The accepted Qwen3 pair has SDK-region ratio 1.33418x and execution-only ratio
1.62669x. `diagnose_projection_pair.py --pair <pair/result.json> --output
<fresh-json>` verifies that 98304 saved dot issues minus 7744 extra strict
weight-wait cycles exactly equals 90560 saved SDK-region cycles. This identity
is scoped to this measured pair, not a general additive-stall model.

## Full-output Qwen3 successor

`build_full_projection.py --output <fresh-dir>` expands the same activation
capture to the complete Q/K/V weight matrices, N=2048/1024/1024 and K=2048.
It verifies all extracted weights against the original GGUF and the existing
prefix, checks independent row-major/R4 golden results, and reuses nine checked
common objects while rebuilding only the caller and data. Four genuine token
rows execute one reset-start trial, 128 native commands and 16384 output floats.
This is full N, not all prompt tokens or a complete GGML/model benchmark.

`run_full_projection.py --wide 0|1 --build <build-dir> --output <fresh-dir>
--execute-reviewed` uses the existing audited SoC images and independent
protocol checker. The numerical checks cover every output and all unused tail
guards. `collect_full_projection.py --base <run> --wide <run> --output
<fresh-dir>` audits the actual logs, image and input identities before comparing
regions. Use `watch_projection_pair.py --full` with those arguments to wait
for both results without timed polling. Its parent-directory watches also
handle workers that have not created their output directories yet.

The first build attempt remains FAIL because its helper changed while being
consumed; the frozen successor is a different build. The first full-pair watcher
also remains FAIL due to a startup-order race. The successor watcher fixes that
race without restarting either simulator or changing their acceptance checks.

## Actual-model activation preparation census

`run_preparation_census.py --model <audited-model-run> --audit <model-audit>
--output <fresh-dir>` reuses the accepted complete llama.cpp static libraries.
Only the caller is rebuilt: the exact accepted fixture has its two existing
M4-preparation/lifetime trace flags enabled. All prompt, KV, Attention choices,
model steps, logits comparisons and numerical checks remain unchanged.

`preparation_census.py` links each actual cache/direct group event to the next
prepared-buffer record, checking producer, K, epoch, group number and phase.
It distinguishes actual byte-cache hits from direct recomputation, and checks
that both Attention choices produce identical preparation-route counts.
Equal prepared buffers are only duplicate packed outputs, not proof of equal
original FP32 input bytes. Counts are not hardware cycles, and this M4 cache
must not be confused with M1 hardware activation-context reuse. No QEMU elapsed
time is used as an RTL performance result.

## Real FFN projection successor

`run_ffn_capture.py --output <fresh-dir>` uses the same accepted model libraries
and actual native QBS/grouped-Prefill paths to capture first-layer `attn_norm-0`,
`ffn_norm-0`, and `ffn_swiglu-0`. It verifies the prior QKV boundary and the six
logical calls/5760 native commands before stopping before down. Both trace gates
are required for command records; the first incomplete observation remains FAIL.
The accepted capture is `e2e_ffn_capture_20261106_02` in the verification tree.

`build_ffn_native.py --capture <accepted-dir> --output <fresh-dir>` prepares a
matched SDK triplet, M4/N128 and K=2048/2048/6144, with gate/up input preparation
shared. Nine checked common objects are reused, only caller/data rebuilt.
`run_ffn_native.py --wide 0|1 --build <build-dir> --output <fresh-dir>` performs
preflight; add `--execute-reviewed` to run bounded VCS plus protocol checks.
`watch_ffn_pair.py --base <run> --wide <run> --output <fresh-dir>` waits on file
events and calls `collect_ffn_native.py` once. Every output, quantized payload,
CSR state and guard is checked. This is full K but cropped N, not full FFN:
down uses the real captured input, and the cropped gate/up outputs do not feed
it. See `hardware/docs/LLAMA_FFN_THROUGHPUT_EXPERIMENT_20261106.md`.

`projection_work_ledger.py --run <historical-register-model> --output
<fresh-dir>` replays the historical model's original numerical/route checker and
conserves logical MAC work against native commands for each of the six model
steps. It records actual command/call shapes, M1/M4 boundaries and ideal weight
R-beat/dot-issue service budgets. Runtime artifacts are rehashed against their
original pins; old symlink-name pins and canonical-name pins both retain exact
content checks. It does not claim a full old-source re-audit or current RTL
performance. The accepted compact receipt is
`evidence/projection_work_ledger_20261106_01/result.json`; the implications and
non-timing scope are in `hardware/docs/LLAMA_MODEL_WORK_LEDGER_20261106.md`.

`build_output_gqa6.py --output <fresh-dir>` prepares a genuine Qwen2.5 Decode
GQA6/D128/visible128 full-call ABBA, reusing fifteen checked common objects and
rebuilding only caller/data. Raw captured KV is converted to token-major with
an inverse-layout check; input values and the original numerical tolerance are
unchanged. `run_output_gqa6.py --build <build-dir> --output <fresh-dir>
--execute-reviewed` uses the audited wide SoC. This measures software schedule
choices on one image, not old versus new hardware. Its logical `value_decodes`
does not count the output-tile schedule's repeated physical V decoding.

The completed GQA6 ABBA gives 410489 versus 344633.5 mean cycles, ratio
1.1910885x, with bit-identical paired outputs/CSR. This is a software comparison
on the same wide SoC, not a full-model speedup or a hardware-width comparison.
`collect_followups.py --study gqa6|preparation --run <completed-run> --output
<fresh-dir>` replays these completed studies, including image/protocol checks or
native QEMU provenance, respectively. Compact receipts are in
`evidence/output_gqa6_20261106_01` and `evidence/preparation_census_20261106_01`.

`audit.py` implements the first, read-only step of the end-to-end performance
plan. It does not build software, start VCS/QEMU, access the board, alter a sealed
input, or promote an experimental runtime. Separate reconstruction and bounded
QEMU experiments are described below; they do build and execute software.

Run from the Ara repository:

```sh
python3 -B -m unittest discover \
  -s verification/performance/end_to_end_baseline -p 'test_*.py' -v
python3 -B verification/performance/end_to_end_baseline/audit.py \
  --output verification/performance/evidence/end_to_end_baseline_next
```

The output directory must not exist. Explicit `--ara`, `--llama`,
`--verification` and `--board` arguments override the local evidence locations.
Missing or changed inputs fail the replay; the tool does not fetch substitutes.
The external evidence and checker sources must be trusted local campaign inputs.

## What is checked

- Current repository commits, delivery commits and hashes of tracked local
  differences are recorded separately. Local differences are not build inputs.
- The board campaign's final requirements audit anchors four accepted observer
  receipts. Their source pins and collected artifacts are rehashed; unsafe,
  duplicate and escaping collection paths are rejected.
- The original F16 full-answer, M4 ABBA, quantized native full-answer and Q4/Q8
  restored-prefix grid checkers run again on the collected data. Returned fields
  must match the accepted receipts, including negative results and limitations.
- The existing graph schedule checker replays the historical QEMU log. This is
  a log-level functional replay, not revalidation of every old build input.
- Output preserves software candidate versus production identities and leaves
  hardware per-stage fractions unknown. QEMU timestamps are never converted to
  hardware timing.

## Result and remaining work

`EVIDENCE_REPLAY_PASS_STAGE_ATTRIBUTION_PENDING` means the existing records
passed replay, **not** that a new simulator, current RTL or a newly compiled
model passed. The result includes complete-application paired measurements,
graph/reuse evidence and the gates still required for stage attribution.

The initial replay is stored in
`verification/performance/evidence/end_to_end_baseline_20261105_01/result.json`.
No raw external log or model is duplicated here. Reproducing the audit requires
the referenced local archives. No new timing measurement is claimed.

See `hardware/docs/LLAMA_END_TO_END_BASELINE_AUDIT_20261105.md` for the Chinese
conclusions and the narrowed next experiment.

## Reconstruct the previously measured trace-context change

`prepare_trace.py --output <fresh-directory>` extracts the fixed llama.cpp
delivery sources, applies `trace-context.patch`, checks the exact measured
postimage, and repeats GCC/Clang host checks. It does not modify the dirty llama
checkout or rebuild/replace the complete production binary. Configuration is
sampled at each blocking execution context, not once per native command.

## Output residency experiment

```sh
python3 -B verification/performance/end_to_end_baseline/run_output_tile.py \
  --suite online \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/output_online_next
```

Available suites are `leaf`, `online`, `runtime`, and `entry`. Each requires a
new output directory. Each compiles pinned sources and runs bounded VLEN1024
and VLEN256 QEMU guests. No board access or RTL performance is implied.

- `leaf`: scalar FMA oracle, old Register-PV, and output-resident leaf; includes
  actual captured V and unaligned Q8_0 byte payloads.
- `online`: complete Softmax/PV schedule with controlled QK callbacks; checks
  recurrence state, results, flags, callback sequence and terminal failures.
- `runtime`: existing layout/selector/descriptor fixture with a QBS reference
  executor, redirected to the independent `quant_output_tile_execute` symbol.
- `entry`: actual CSR/VLEN rejection without issuing work or changing outputs.

`collect_output_tile.py --leaf <dir> --online <dir> --runtime <dir> --entry <dir>
--output <new-json>` rechecks current source identities, ELF hashes and raw guest
verdicts. The accepted receipt is
`verification/performance/evidence/output_tile_20261106_02/result.json`.
The failed original runtime tests remain in the external run area; their
diagnostic translation unit is `test_output_binding.c` and their exact compiler
commands remain in those runs' `commands.json` files.

The prototype is not a production default. Its `value_decodes` retains the
existing logical-row report definition; it is **not** a physical decode counter
because multiple head pairs re-read V. See
`hardware/docs/LLAMA_OUTPUT_RESIDENCY_EXPERIMENT_20261106.md` for costs and the
required real-QK, RTL and model gates. The overall architectural goal remains
broader than this experiment and permits justified additional hardware.

## Real graph, model, and RTL scopes

The graph adapter is reconstructed from the fixed llama.cpp delivery into
isolated build inputs; it does not overwrite the dirty external checkout.
`prepare_output_backend.py` and `check_output_backend.py` check the opt-in
patch and its compilation. Actual GGML graph dispatch is covered by the
`output_graph_20261106_01` receipt. The original graph run with a missing native
QBS CPU flag is preserved as FAIL; its successful replay uses the same ELF and
initramfs with the correct emulator configuration.

`output_model_20261106_01/result.json` records a complete Qwen3-1.7B paired
model run with 40 prompt tokens and three logits records per KV profile.
The program compared 911616 logit values bitwise, and the independent audit
verified routes, native work, final CSR equality and emulator provenance.
This is functionality evidence, not model throughput or acceptance of the
subsequent optional wide-dot RTL.

The two Qwen3 GQA2/D128/visible20 full-call VCS pairs are in
`output_native_20261106_01/result.json`: output residency gives about
1.25--1.27x versus the accepted Register-PV software on the same hardware.
Do not turn these selected head-group measurements into a full-model speedup.

## Optional matrix throughput experiment

`WideMatrixDot` defaults off. The candidate accelerates M3/M4 local waves for
256-element profiles and uses row-local integer correction lanes; short blocks
and M1/M2 keep their original dot issue step. FP arithmetic and ISA are unchanged.

`run_matrix_dot_pair.py` builds matched compute-level VCS images and uses the
existing C oracle. Only structural dot-cycle and capacity expectations differ
between vector files; payloads, outputs, flags and remaining counters do not.
Both configurations passed 38 cases; the receipt is
`matrix_dot_pair_20261106_01/result.json` in the evidence directory. Its ratios
include testbench-controlled input delivery, not the native SDK's overhead.

The full-command successor also includes the production shared reader and
commit path, two response schedules, and context lifecycle/fault recovery:

```sh
python3 -B verification/performance/end_to_end_baseline/run_matrix_engine_pair.py \
  --component-run /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_matrix_dot_pair_20261106_01 \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/matrix_engine_next
```

Use a new output directory. Run the worker directly under the owning service,
not through a launcher that exits before its children. The original frozen
wrapper and assertions are retained; a separate derived wrapper only forwards
the width parameter. A passing worker can be re-audited using
`collect_matrix_engine_pair.py --run <run> --output <fresh-evidence-directory>`.
It still does not cover CVA6 dispatch, SDK preparation or complete inference.
