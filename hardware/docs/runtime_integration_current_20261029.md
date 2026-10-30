# Current QBS / Attention optimization integration

This is a current-source integration audit, not a new performance experiment.
It supersedes the *integration status* in the earlier
`llama_optimization_integration_audit_20261028.md`; that historical document is
retained because completed and running experiments pin its bytes.

## What actually executes

Linear projection enters the GGML CPU repack path. For admitted K-quant weights,
four F32 activation rows are quantized and packed into Q8_K, then submitted to
QBS. The parallel-sum producer changes the integer group-sum calculation, not
the quantization definition. Prepared-input reuse retains exact-byte and
graph/source-lifetime checks. QBS's final-dot retirement optimization removes
a completion bubble; it does not change descriptor contents or arithmetic.

Attention has two distinct native routes. In `arch/riscv/akv.cpp`, the
quantized-KV attempt occurs before the original floating-point AKV selection:

| Route | Hardware/software division | Selection |
| --- | --- | --- |
| Floating-point KV Attention | Existing AKV commands and shared vector resources | Original AKV capability, layout and runtime gates |
| Q4_0/Q8_0 K, Q8_0 V Attention | QBS DIRECT for quantized QK; RVV/software for online Softmax and PV | Quant-KV build/runtime gates and shared SDK admission |
| Register-PV Decode | Same quantized QK; decode Q8_0 values and update PV in vector registers | Additional Register-PV build/runtime selection |
| Grouped Prefill | Share K panels and value decoding across causal query prefixes | Separate Prefill build/runtime selection |
| Unsupported inputs | Existing ordinary implementation | Return fallback before native execution |

The quant-KV adapter takes the AKV context lock and uses
`ggml_riscv_qbs_direct_run`. The latter excludes concurrent QBS context
operations but does not wait for a reservation whose consumer is later in the
same graph. An admitted execution failure is propagated as failure, not silently
retried through ordinary RVV after potentially modifying outputs.

Consequently `GGML_RISCV_AKV=0` in the accepted quantized-KV model test does
**not** mean all Attention optimization is disabled. That test enables
`GGML_RISCV_AKV_QUANT_KV=1` and native QBS; the floating-point AKV branch remains
disabled in both comparison modes. Do not attribute the quantized-KV results
solely to the original floating-point AKV compute path.

## Exact activation conditions

| Optimization | Required selection | Important restrictions |
| --- | --- | --- |
| Parallel M4 sums | `GGML_RISCV_QBS_M4_PREPARE=1`, `GGML_RISCV_QBS_M4_PACKED=1`, `GGML_RISCV_QBS_M4_PARALLEL_SUMS=1` | Supported producer domain; producer tag 3 differs from the original packed tag 2 |
| Prepared M4 reuse | `GGML_RISCV_QBS_M4_CACHE=1` with graph/lifetime eligibility | Exact input bytes, producer tag, shape and lifetime must match; not pointer-only reuse |
| Quantized Attention | Build `GGML_RISCV_AKV_QUANT_KV=ON`; runtime `GGML_RISCV_AKV_QUANT_KV=1`, `GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY=1`, native QBS enabled | Single worker, supported formats/layout/mask/shape, valid device; software QBS emulation is not native admission |
| Register-PV | Build `GGML_RISCV_AKV_REGISTER_PV=ON`; runtime `GGML_RISCV_AKV_REGISTER_PV=1` | Guarded entry requires VLEN1024, RNE and vstart=0, in addition to common admission |
| Grouped Prefill | Build `GGML_RISCV_AKV_QUANT_PREFILL=ON`; runtime `GGML_RISCV_AKV_QUANT_PREFILL=1` | Multiple query rows and supported causal-prefix mapping; single worker |

The Attention build options are nested under the existing QBS/AKV/RVV backend
configuration. Setting an environment variable cannot add code that was not
compiled. Register-PV and the earlier `GGML_RISCV_AKV_GROUPED_PV` Decode
experiment are mutually exclusive: enabling both selects fallback. The accepted
combined model tests keep GROUPED_PV=0. Grouped *Prefill* is a different option
and is enabled alongside Register-PV Decode.

These switches remain opt-in. No global defaults, admission limits, numerical
policy, or production sources were changed by this audit.

## Which results can be claimed together

| Evidence | Accepted result | Scope |
| --- | --- | --- |
| M4 preparation | 76060 to 44443 cycles, 1.711406x | Preparation only; already included in the projection comparison below |
| Q/V/K slice, software plus retirement update | 582799.5 to 547856 mean cycles, 1.063782x | Same slice/work, not an entire model |
| Guarded Register-PV Decode | 47885.5 to 43075.5 mean cycles, 1.111664x | Real Qwen3 Q4_0-K/Q8_0-V, D128, two heads, 20 visible tokens |
| Grouped Prefill, Q4_0 K | 174314.5 to 147469 mean cycles, 1.182042x | Four real queries, overlapping causal prefixes |
| Grouped Prefill, Q8_0 K | 179726 to 148884.5 mean cycles, 1.207151x | Same query/prefix structure, different K format |
| Combined software model validation | Qwen2.5-1.5B and Qwen3-1.7B, 1823232 paired logits bit-exact | QEMU functionality, token and CSR equality, not model throughput |

The projection baseline already uses QBS. The Attention baseline already uses
the shared RVV value decoder and QBS QK. These are incremental improvements,
not the original QBS-versus-direct-RVV acceleration. None of the ratios may be
multiplied to claim a model speedup. The prepared-cache cost experiment likewise
must not be counted again: cache reuse is already enabled in both projection
paths.

Evidence and exact checked scopes:

- `qbs_retirement_acceptance_20261029.md` and
  `verification/out/qbs-retire-projection-vcs-20261029-01/result.json`.
- `register_pv_guarded_acceptance_20261028.md`.
- `prefill_production_acceptance_20261028.md`.
- `m4_parallel_sums_integration_acceptance_20261029.md` and
  `verification/out/m4-sums-models-20261029-01/result.json`.
- `prepared_cache_cost_acceptance_20261029.md`.

The external llama.cpp checkout contains uncommitted integration work. The
accepted binaries and source inventories establish what was tested; a checkout
name alone does not. Do not reset that tree or assume another machine's build
contains these opt-ins merely because it uses the same branch name.

## Remaining work and decision order

1. Finish the isolated graph-probe ON/OFF Qwen3 functional test. Its current
   run is `graph-cycles-model-20261029-03`. The Linux counter-access preflight
   passed, but launch is not model-test acceptance.
2. Before using the probe for hardware attribution, establish graph/fusion/
   reuse and command-count equivalence and a bounded RTL overhead comparison.
   The current model checker explicitly does not verify hardware command or
   reuse counts. QEMU timestamps are not RTL performance evidence.
3. Measure complete runtime boundaries: GGML dispatch, Prefill allocation,
   preparation, execution and cleanup. Existing C-entry measurements omit some
   C++ caller costs; the graph timer also excludes graph construction and its
   own buffer allocation. No unmeasured overhead is assumed to dominate.
4. Choose the next optimization from that measured attribution. Possible
   allocation reuse must retain worker ownership, allocation-failure fallback,
   and fresh per-call panel validity. Do not introduce persistent data reuse
   simply because persistent workspace storage appears cheaper.

The current investigation does not require another RTL feature, synthesis or
FPGA run. It first establishes whether further improvement belongs in runtime
preparation, scheduling, or the hardware execution path.
