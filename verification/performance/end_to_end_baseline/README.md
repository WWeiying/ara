# End-to-end optimization experiments and evidence

## Single-input SDK submission experiment

`prepare_sdk_single_input.py` builds independently namespaced old/candidate SDKs
from the sealed accepted runtime. GCC and Clang+UBSan each passed 24,535 cases;
the seven existing SDK fixtures also passed on each version. The production
runtime is unchanged. The registered prototype is under
`software/qbs/experimental/single_input/`.

`build_sdk_single_input_native.py --host-result <attempt/result.json> --output
<fresh-dir>` builds one ELF with both SDKs and the accepted actual Qwen3 Decode
inputs. It reuses ten original objects and rebuilds the caller and candidate
runtime. Compiler dependencies must match the sealed caller/common inventories
or the exact isolated host preparation; conflicts and unknown inputs reject.
The first build's missing inherited toolchain-header rejection remains FAIL.

`sdk_single_input_campaign.py --build <build> --run <fresh-run> --audit
<fresh-audit> --output <fresh-campaign>` owns bounded VCS and independent replay.
Order is ABBA, with production quantization, all output bytes/CSR/guards and
independent protocol checks retained: 112 commands and 3,584 outputs. Both cold
and warmed baseline times are reported. Equal hardware work is required, but a
speedup is not required for functional PASS. No production promotion or model
speedup is implied.

The pair completed: execution ratio 1.03539x; preparation-inclusive region ratio
1.02242x. Mean execution saves 4991 cycles while mean QBS busy increases by only
6.5 cycles, locating the benefit outside busy rather than in dot throughput.
All seven warmed call comparisons remain positive. See
`evidence/sdk_single_input_20261106_01/result.json` for the actual ABBA times.

The trace-context candidate library separately completed its full Qwen3 paired
functional check: 607,744 logits, token/CSR and actual work match across two KV
choices. See `evidence/trace_context_model_20261106_01/result.json`. QEMU is used
only for functionality; no hardware timing is inferred from this run.

## SDK integration and supply decision

`build_sdk_dispatch_library.py` reconstructs the accepted original runtime object
byte for byte using the original GGML compile recipe. It compiles the measured
single-input candidate without symbol renaming, replaces only `qbs_runtime.c.o`
in a copy of the accepted trace-context library, and checks all other 31 archive
members, member order and exported symbols. The 13-test archive suite and its
compact receipt are under `evidence/sdk_dispatch_library_20261106_01/`.

`sdk_dispatch_model_campaign.py --run <fresh-run> --audit <fresh-audit> --output
<fresh-campaign>` owns the complete Qwen3 paired functional run and independent
replay. It reuses the accepted model object and full-logit comparison driver,
reproduces the prior baseline ELF exactly, then links a candidate with only the
SDK archive changed. No model or driver translation unit is recompiled. The
guest compares 607744 logits, tokens/CSR and the full projection/Attention work
for both KV choices. Existing `TRACE_CONTEXT_*` guest markers are retained
because the driver binary is unchanged; the worker/audit states identify the
SDK experiment. This is not a new trace-context optimization or a cycle result.
Production code remains unchanged until functional and non-M1 performance
acceptance are both available.

The SDK-dispatch model pair has now completed: 607744 full logits, token/CSR and
788 QBS calls per variant agree exactly. An independent successor,
`audit_sdk_guest_payload.py`, parses the actual newc archive rather than merely
reading its listing. It verifies the exact guest entry set, ELF contents/modes,
distinct baseline/candidate binaries and link/library identities. Its 14-test
suite rejects A/A packaging, traversal, hardlinks, duplicate entries and malformed
archives. The completed model result was replayed with the same audited cpio
and final worker inventory; see `evidence/sdk_dispatch_model_20261106_01/`.
The payload-only audit itself is not a model PASS, and neither result is RTL
timing. Non-M1 performance and production promotion remain separate gates.

`study_weight_supply_codec.py` is a host-only, exact-GGUF feasibility check for
one lossless residual-byte codec. It preserves quantized values and metadata,
accounts for mode/bitmap/panel-index bytes and allows whole-tensor raw fallback.
All 197 Qwen3 projection tensors, 6720512 blocks and 1100961792 raw bytes were
checked; every tensor selects raw fallback, with zero net saving. The 15-test
suite includes an independent scalar plane mapping and serialized decoder
negatives. `evidence/weight_supply_codec_20261106_01/result.json` binds the
replayed statistics and source/artifact hashes. This candidate is rejected for
RTL implementation, not presented as a compressed-memory speedup. It neither
rules out every other codec nor removes the local decoded-input bandwidth limit.

## Wide-supply components, not yet a wide SoC

`hardware/docs/LLAMA_WEIGHT_SUPPLY_ARCHITECTURE_20261106.md` defines the physical
memory, native mapping, permissions and comparison requirements. Logical SRAM
bytes remaining constant does not imply constant physical macro area.

`qbs_weight_line_assembler.sv` is an uninstantiated per-bank building block.
It retains a partial 32-byte word, emits at most one word per port/cycle and
flushes a final second-word tail without overwriting an older output. Valid and
mask state reset; invalid payload storage need not reset. Its contract requires
ordered nonempty prefixes and clear before another bank owner. The first VCS
worker's 16387 normal cases pass; it remains FAIL because it incorrectly rejects
VCS's zero exit on a specifically expected fatal. The successor
`collect_weight_line_assembler.py --run <first-run> --output <fresh-audit>`
preserves that report, replays normal byte/guard/state checks and completes four
specific negative contracts. Do not use its old worker state as a clean PASS.
Those width/abort-combination gaps now have a separate successor:
`run_weight_line_boundaries.py --output <fresh-dir>` checks widths 6/7/8/16,
short fragments, capacity edges, simultaneous emit/tail abort and immediate
epoch reuse. Its 68 cases and eight aborts pass, with globally unique expected
fatals. The original worker and helper remain unchanged.

`run_weight_wide_mapper.py --output <fresh-dir>` checks the balanced native-byte
mapper against an explicit nine-profile oracle: 4608 cases, all row counts and
physical phases, two schedules, 36 aborts and eight contract rejections.
`evidence/weight_wide_components_20261106_01/result.json` binds the independent
raw-log, pin and artifact replay of both successors. Neither establishes a
complete SRAM ingress or wide SoC.

`qbs_weight_wide_bank.sv` now connects the mapper, eight assemblers and actual
generic payload SRAM. Its first VCS worker passes all functional assertions but
remains FAIL at a resource-banner gate: four shared initial tallies each
undercount by four. No RTL was changed or simulation repeated.
`collect_weight_wide_bank.py` permits only the exact known resource record,
derives logical/macro/register storage from frozen declarations, retains the
original trace and FAIL, and replays the unchanged functional checker with an
explicit resource-only projection. The precise simulator scheduling cause of
the tally error is not established; the observed tally is not used as area.

The independently replayed scope covers 4608 normal cases, 72 reuse cases,
72 aborts and 72 cancelled reads. There are 45832 synchronous reads, zero
unthrottled input stalls, maximum two-edge final-input drain, and 1526 actual
mixed-target stalls (803 with side metadata). It checks byte writes/readback,
completion, X-safe public controls, idle-window hold and atomic admission.
`evidence/weight_wide_bank_20261106_01/result.json` binds the successor. This is
bank-local functional/II1 evidence, not compute-engine integration, a wide
physical SoC, macro/PPA acceptance or SDK speedup.

`qbs_read_engine.sv` adds default-disabled `PerRangeTransferSize` and a
`range_size_i` input. The size is stored per range and per outstanding burst,
affecting AR alignment/length, the checked physical footprint and response lane
progression. A narrow transfer on a wide physical bus must alternate physical
halves correctly. The existing shared reader still selects full bus width.

Use `run_mixed_reader_checked.py --output <fresh-dir>` for the reviewed fixture.
Both legacy128 MMU modes retain mapped-page/fault recovery and six held-AR fault
cases each. The 256-bit component checks 258 mixed-size/phase cases, four fault
cases and actual payload/tag/offset/beat accounting. The first mixed fixture
remains failed: it injected an older response error before the younger AR had
been sampled as stalled. The successor adds that sampling edge and records
`ar_stalled_q: 0 -> 1` before injection; no DUT change followed that simulation.
Its original post-fault checks are retained, not weakened. Real CVA6 PMP, wide
SoC storage, native weight steering/SRAM integration and SDK latency are not
proved by this component acceptance.

### Optional integrated wide ingress

`run_wide_compute.py` freezes two compute-only images with identical arithmetic
and the original versus wide SRAM weight path. Both pass 66 normal commands,
five numeric recoveries and five faults; 17736 FP events have equal operands
and per-accumulator order. All nine native profiles, both layouts and M1--M8
remain checked. This is not a complete reader/SoC or SDK speedup measurement.

`run_wide_default_engine.py --output <fresh-dir>` rechecks the complete
default128 QBS controller/shared-reader/commit against the sealed original
36-case raw reference. Every direct/context cycle and work result matches.
Context lifecycle, fault/retry and reset tests are retained. The optional
feature remains disabled, so this gate alone cannot accept the wide path.

`run_wide_complete_engine.py --output <fresh-dir>` generates a separate
successor fixture and pairs full128/256 command paths with unchanged original
arithmetic. Its synthetic target returns a full physical word, steps by the
captured ARSIZE and places narrow responses in the correct bus half. Both
response gaps retain the original golden/work/atomic-fault checks. It records
per-command cycles and traffic, not SDK/model speedup or real PMP acceptance.
The original sealed benchmark and all older worker failures remain untouched.

The complete pair now passes 36 commands per width at response gaps zero/three;
the accepted default128 cycles remain identical. `collect_wide_ingress.py
--output <fresh-dir>` binds exact worker result hashes and replays all three
component/controller checkers, 332 pins and the original artifacts. The compact
receipt is `evidence/wide_ingress_20261106_01/result.json`. The synthetic direct
command totals, 30179/29445 and 48907/43674 cycles, are not model speedup data.

The new shared-client worker's first compile fails on testbench typedef syntax,
before simulation. Its checked successor passes all 128 normal cases/12 faults
and 128 field-copy vectors, but fails negative-source-line attribution: VCS
reports the correct SVA `assert property` line rather than its `else $fatal`
line. Preserve both original FAILs; any scoped host replay must bind the exact
source and retain every other negative gate, without rerunning the RTL.
`collect_wide_clients_scoped.py --collect` now provides that completed audit:
exact mask property, instance, time and unique fatal are checked before only
the fatal-header line is projected for the unchanged negative checker. All
66 pins, nine artifacts and both raw checkers were independently replayed;
`evidence/wide_clients_20261106_01/result.json` binds the accepted scope. The
original FAILs and raw logs are unchanged. Host mutation tests reject unrelated
origins, lines, predicates, duplicate fatals and unexpected PASS text.
Wide client selection remains default-OFF. Ordinary RVV and actual AKV SoC
operation, physical memory width, real permission checks and SDK performance
are later integration gates, not implied by these command/component fixtures.

### Physical SoC width experiment

`prepare_wide_soc.py prepare --output <fresh-dir>` snapshots the accepted full
processor/dependency inventory, overlays only the reviewed QBS integration and
adds four new source modules. It excludes unrelated main-tree ALU/multiplier/
VRF area changes. This is an experimental build-input tree without Git metadata,
not another development worktree or canonical-source promotion. The baseline
Makefile metadata is pinned, but no Bender/Make regeneration or dirty dependency
selection occurs: compilation reuses the exact native VCS compiler recipe and
frozen DPI object. Historical filelist target names do not invoke Verilator.

`prepare_wide_soc.py compile --prepared <dir> --prepared-sha <sha> --width
128|256 --output <fresh-dir>` selects actual generic SRAM word width and the
matching weight ingress. Both use four lanes, VLEN1024, 16 MiB and WideMatrixDot.
The two full-processor builds have completed; each preserves all 131 exact
baseline compile diagnostics. Source, artifact, image-library and raw compiler
checks were independently replayed. See
`evidence/physical_wide_soc_builds_20261106_01/result.json`. Compilation alone
is not runtime or performance acceptance.

`wide_soc_memory_smoke_build.py --build` produces one ELF for both images,
using scalar reference arithmetic rather than vectorized expected results.
It checks 180 scalar cases and 240 vector cases across all naturally aligned
bus phases, e8/e16/e32/e64, masks, tails and 4-KiB physical boundaries. At
VLEN1024 the independent host oracle requires 360 value checks, 113728 byte
checks, 90 source and 90 destination crossings, and digest 96466774f378327d.
No agnostic register bytes are compared. The ELF contains 1924 planned dynamic
vector instructions; this is stimulus work, not evidence of executed work.

`run_wide_soc_smoke.py` requires exact image/program receipt hashes, independently
parses ELF64 PT_LOAD records to reject unaligned/overlapping rounded DPI writes,
checks physical memory geometry/activity and runs the existing independent
CVXIF/VID/AXI UVM checker. Its UART oracle is separate from the full-log protocol
check, so normal zero-error UVM summaries are not mistaken for UART errors.
The platform probe observes all SoC memory traffic; it is not a QBS ROI counter.

`continue_wide_soc.py --output <fresh-dir>` waits on terminal result-file events,
not timed polling. Only after both memory runs pass does it execute the same
committed QBS/AKV/RVV handoff ELF on both images in parallel. A producer/consumer
receipt adapter changes build-state spelling only, preserving the exact ELF,
source inventory, load checks and original successful build report. Any failed
gate stops subsequent dispatch. Neither these smoke tests nor a passing build
authorizes wide Linux/NORMAL_MEMORY use; real PMP footprint and actual-SDK/model
performance remain separate requirements. No synthesis or board action runs.

## Ordered fused RMSNorm: scoped replay

`collect_rms_norm_scoped.py --output <fresh-dir>` audits the preserved completed
RMSNorm run without launching a simulation. The original worker remains FAIL
because its inherited checker demanded positive Ara AXI-write coverage. Actual
ELF encodings and the independent allocation trace prove zero vector stores;
the fused functions write output with scalar FSW. The unchanged checker is
replayed on the same logs, omitting only `--require-axi-write`; every other
report field, instruction work, image identity and protocol check must match.

Eight real-input ABBA calls check 40960 outputs, 53 boundaries and ten
order-sensitive sums. Decode and Prefill complete-call ratios are 1.09882x and
1.10816x. The receipt is `evidence/rms_norm_scoped_20261106_01/result.json`.
These are software-call results, not model timing, vector-write coverage,
production integration or a new hardware performance claim.

## Projection and matrix experiments

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

The full-N pair completed: 1287703 versus 803294 region cycles (1.60303x),
1224484 versus 740075 SDK execution cycles (1.65454x), with identical 57816
preparation cycles. `diagnose_full_projection.py --pair <pair/result.json>
--output <fresh-dir>` replays the pair and its strict-wait buckets: 524288 saved
dot issues minus 39879 extra wait cycles equals the 484409 actual region-cycle
reduction. The compact full-output receipt is
`evidence/full_qwen3_qkv_20261106_01/result.json`. Full output N is not all prompt
rows, a complete GGML call, or whole-model timing.

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

The pair completed with all outputs, payloads, CSR and independent protocol
checks passing: SDK execution is 191186 versus 116797 cycles (1.63691x), while
the N128 region including preparation is 430352 versus 355963 (1.20898x).
These distinct scopes must not be used interchangeably or as full FFN latency.

## Genuine Decode input capture

`run_decode_capture.py --output <fresh-dir>` uses the shared source-gated
`capture_model_inputs.py` runner and the accepted complete-model libraries.
It finishes the real 40-token Prefill, checks greedy token 22406, then captures
actual M1 inputs for first-layer QKV/gate/up/down and final vocabulary projection.
It stops before the Decode vocabulary operation, not after a completed Decode.
The checker audits 196 logical projection calls and 17920 native commands,
source boundaries, actual Attention routes, and use of activation context.
Prefill rows cannot be relabelled as Decode. Weight inventory is checked before
the bounded QEMU run; QEMU provides operands/functionality, never RTL timing.
See `hardware/docs/LLAMA_DECODE_INPUT_STUDY_20261106.md` for the intended M1
baseline and the remaining model-library trace-context integration step.

The genuine Decode capture completed. `collect_decode_capture.py --run
<capture> --output <fresh-dir>` independently replays source boundaries and all
operands, re-extracts seven weight prefixes from the original GGUF, and checks
native QEMU provenance. The receipt is
`evidence/decode_capture_20261106_01/result.json`. Observed context counts belong
to the capture scope before the vocabulary operation, not complete-model timing.

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

## Real Decode M1 baseline

`build_decode_native.py` consumes the independently audited real Qwen3 Decode
capture, retaining full K, N128 prefixes, production RVV `quantize_row_q8_K`,
Q/V/K and gate/up activation-context reuse, long-K DIRECT fallback, and a
vocabulary-head prefix. It does not relabel a Prefill row or disable existing
context support. The seven calls contain 28 native commands and 896 outputs.

`run_decode_native.py` supports a no-simulation preflight (default) and explicit
`--execute-reviewed`. `decode_native_campaign.py --build BUILD --run NEW_RUN
--audit NEW_AUDIT --output NEW_CAMPAIGN` owns simulation plus independent protocol
checks and replay collection in one background service. All output directories
must be new. No RTL build, synthesis, URG or Verilator is performed.

`check_decode_native.py` reconciles all outputs/quantized bytes/guards/CSR,
command and context work, exclusive phases, strict weight-wait buckets and
reader payload. `activation_bytes` is **compute intake including SRAM replay**,
not activation AXI traffic. Four checker tests reject weakened context baselines,
CSR mismatches, changed payload accounting, wrong oracles and incomplete work.
The accepted status is `REAL_QWEN3_DECODE_SDK_BASELINE_REAUDITED`, not preflight
or simulator launch. Timing excludes cold weight repack and full GGML dispatch;
the sampled output channels cannot establish full-model speedup.

The baseline has now completed VCS and independent replay: 227810 region cycles,
68377 preparation, 11610 admission, 145475 SDK execution, and 130052 QBS busy.
All 896 outputs and four quantized payloads match the independent oracle. The
917-input audit is retained under `e2e_decode_native_audit_20261106_01` in the
verification tree. `diagnose_decode_native.py --audit <audit/result.json>
--output <fresh-dir>` checks service/byte accounting and reports bounded local
headroom, not full-model speedup. In particular the 107012 R beats cannot be
removed by more multipliers; strict WAIT subdivisions are shared-reader signals,
and the 15423 SDK cycles outside QBS busy are not all CPU arithmetic.

## Isolated model trace-context library

`build_trace_context_library.py --output <fresh-dir>` reconstructs the registered
trace-context patch against exact sealed pre/postimages and recompiles only the
actual model's `qbs.cpp` using its recorded compiler options. It replaces the
same-named `qbs.cpp.o` member in a copied `libggml-cpu.a`; the original library
is never edited. Archive inventory/order, every unchanged member, global defined
exports, actual header closure, compiler/tool identities and artifacts are checked.
Twelve unit tests exercise malformed archives, duplicate/reordered/stale members,
dependency/symlink drift and exact patch application. This is an archive-verified
candidate, not a new target/model numerical or timing acceptance. Consumers must
keep trace flags fixed inside a blocking context and refresh at the next one.

`trace_context_model_campaign.py --run <fresh-run> --audit <fresh-audit> --output
<fresh-campaign>` performs a full-model functional pair and independent replay.
Both static executables share one mechanically derived model object, varying
only the verified CPU archive. Each executes the accepted 40-token Qwen3 prompt
and one complete Decode step for both KV choices. A separate guest comparator
checks all 607744 logits, tokens, CSR and exact record lengths. Host tests
compile this comparator and reject last-logit mutations, nonfinite values,
truncated/extra records and CSR mismatches.

The runner binds a 197-tensor projection schema to the original GGUF and graph.
The checker verifies per-step CALL order/shapes, profile/mode/native-command
accounting, eligible context bounds and all Attention layout/PV/control work
against the accepted control. No per-command lifetime trace flood is emitted.
`run_trace_context_model.py --output <fresh-dir>` is preflight only; add
`--execute-reviewed` for explicit execution. QEMU supplies functional evidence,
never RTL timing. Only the independent
`TRACE_CONTEXT_QWEN3_MODEL_PAIR_REAUDITED` result closes this software gate.

## Physical supply SDK pair

`run_supply_sdk.py --kind decode|prefill --width 128|256 --output <fresh-dir>`
checks the actual full-processor image, SDK build, input hashes and DPI preload
geometry without executing VCS. `--execute-reviewed` requires the accepted
physical memory and QBS/AKV handoff pair before starting a bounded simulation.
Each pair uses the same ELF and fixed WideMatrixDot=1. Descriptors/activations
remain 16-byte transfers even on the actual 256-bit bus; only weights widen.
The checked old 128-bit raw logs replay through both successor checkers.

`continue_supply_sdk.py --output <fresh-dir>` seals both pairs, waits for the
existing memory/handoff campaign's terminal-file event, then runs Decode and
full-QKV Prefill in sequence, with two widths concurrent. It independently
replays raw SDK results and binds the UVM check to the same log, trace, ELF and
image. An unfinished/failed prerequisite never admits execution, and partially
published JSON cannot poison the retry inventory. Fresh source/image drift or
a functional/protocol failure stops subsequent dispatch. Each simulation has a
two-hour limit; no simulator compilation, synthesis or physical flow is started.

The terminal campaign status is `PHYSICAL_SUPPLY_SDK_PAIR_PASS`. This means
the same-work functional/protocol pair passed, **not** that a performance target
was reached. `completed_pairs` records preparation/admission/execution/region
cycles and ratios, exact reader work, the 10%-cycle-reduction screening result,
and >2% region regressions. Same-platform best RVV and translated Linux paths
remain separate acceptance requirements; generic-SRAM bandwidth is not DDR
bandwidth, and neither SDK workload is full-model timing.

`build_decode_rvv.py --output <fresh-dir>` prepares the real Decode counterpart
using frozen production Q4 R32 GEMV, Q6 VLEN-dispatched RVV and the original
quantizer. It does not run a simulator. Q4 byte-layout conversion has a separate
inverse and independent field-placement tests. Its numerical driver emits all
896 output words after timing and explicitly marks its current reference as a
QBS-reference tolerance screen, not independent bit-exact RVV acceptance.

The compiled build-03 ELF has a scoped successor audit:
`collect_decode_rvv_build.py --output <fresh-dir>` binds its exact original FAIL
receipt and accepts only the known GCC `.isra.0` clone, its actual VLEN1024
dispatch target and all unchanged build/admission checks. It neither modifies
the failed producer nor recompiles the ELF. The accepted state ends in
`BUILD_REAUDITED_NOT_EXECUTED`; runtime numerics/protocol, matched initial CSR
state and timed-instrumentation accounting remain necessary before timing claims.

The same ELF now has an independent functional reference from
`run_decode_rvv_isa.py`: 896 exact output words and eleven CSR records, with
the existing quantized payload/guard checks. `spike_soc_ports.cc` is an IO-only
UART/memory-map/exit adapter, not a kernel emulation. The first `rdcycle` fault
was traced before enabling Zicntr; the ELF, ISA binary and instruction budget
were unchanged. Receipt: `evidence/decode_rvv_isa_20261106_01/result.json`.
Never use the ISA model's cycle values as hardware timings.

`run_decode_rvv_rtl.py --width 128|256 --output <fresh-verification-directory>`
performs preflight without simulation. With `--execute-reviewed --timeout 10800`,
it reuses the already built actual-memory SoC image and requires completed
memory/handoff acceptance. All RVV outputs and CSR records must match Spike
exactly, followed by independent protocol checks. It records RTL preparation,
dispatch and execution cycles, but deliberately does not accept an SDK
complete-call ratio: the driver has extra timed CSR observations. Actual
disassembly proves both drivers seed VCSR=5, not different initial values.
Use directly owned systemd workers and distinct width-specific output directories;
this helper does not alter the running SDK queue or launch synthesis.

The physical Decode SDK pair has completed: 227810 -> 194611 cycles including
preparation (1.17059x); its execution interval is 145475 -> 115410 (1.26051x).
The same ELF retains all 28 commands, 896 outputs, production contexts and CSR
checks on both images. See `evidence/physical_supply_decode_20261106_01/`.
This is the combined bus/native-ingress experiment, not an isolated SRAM change
or model speedup; the Prefill pair is a separately pending result.
