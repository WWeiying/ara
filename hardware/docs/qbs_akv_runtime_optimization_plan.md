# QBS / AKV runtime and hardware optimization plan

## Objective and baseline

Optimize the existing QBS/RVV linear-projection and AKV/RVV Attention paths
together with their real llama.cpp callers. Preserve ordinary RVV, unsupported
shape/type fallback, numerical policy, and device/context ownership. Do not
replace this objective with an isolated instruction-throughput improvement.

The starting verification revision is `d0c0f8c5`. Its Q4_0 K / Q8_0 V capture
has six query heads, D128 and 128 visible tokens. The fresh H/S/B paired result
is recorded in `verification/akv/quantized_kv/field_copy_pair/RESULTS.md`.
Candidate B totals 951711 cycles for two full calls; native busy totals 17609.
The latter is not an exclusive stall breakdown. No whole-model speedup is
inferred from these numbers.

The user requested software/hardware optimization, not synthesis or FPGA work.
Use the sole verification worktree for experiments and retained fixes. Do not
merge or overwrite the separate main worktree or the dirty external llama.cpp
checkout implicitly. Keep evidence and candidate changes separate until review.

## Work packages and acceptance

| Stage | Work | Required evidence |
| --- | --- | --- |
| 1. Current runtime integration | Rebuild actual GGML with the current shared SDK; run contiguous/strided Q4_0 and Q8_0 KV graph comparisons, then short model generation | Actual native command counts, output/CSR comparison, fallback cases, source/build hashes and checked terminal results. QEMU is functional evidence only. |
| 2. Complete-call attribution | Inspect projection preparation, QK, online Softmax/PV, KV conversion, dispatch and lifecycle costs | Current-source call/dataflow audit plus measured counters or a bounded representative RTL trace. Distinguish retired-PC interval accounting, hardware busy and whole-call cycles. |
| 3. Targeted optimization | Select the largest supported opportunity; reduce repeated preparation, calls or movement before adding compute resources | A falsifiable hypothesis and expected signals before editing; shared benchmark/backend implementation; unchanged admission and failure contracts. Hardware edits require RTL evidence, not just a software profile. |
| 4. Correctness and performance | Validate boundary cases and a fresh paired full-call benchmark; run representative ordinary RVV and device interleave tests for changed RTL | Independent numerical/protocol checks, flags, guard regions, actual work, fresh baseline/candidate builds and bounded VCS timing. Report regressions rather than hiding them. |
| 5. Runtime retention | Connect beneficial changes to actual GGML selection, document defaults and consolidate results | Rebuilt runtime functional tests and selection evidence; shape/type/capability gates, fallback, lifecycle rules and reproducible launch configuration. Commit reviewed milestones. |

Stages 2 and 3 cover both mechanisms. A hardware candidate without a supported
whole-call benefit is rejected or remains opt-in, not promoted merely because
an isolated unit is faster. If the measured limit is outside native execution,
report that limit and improve the software feeding the existing hardware.

## Immediate checks

- The external quant-KV adapter already includes the shared `q8_0_value.h` and
  `ggml_entry_strided.h`; the latest field-copy change needs rebuilding, not a
  duplicate implementation in GGML. Its sealed eight-file integration snapshot
  still matches the external sources at the initial audit.
- Quantized Decode admits one worker, native QBS, supported format/layout and
  an explicit normal-memory opt-in. F16 AKV and quant-KV have separate switches.
  Do not remove these gates solely to increase reported native coverage.
- Shared online Attention reuses decoded V across heads, but still updates
  heads individually. Review the actual scale/mad and expf paths before choosing
  batching, fusion or an instruction extension. Preserve each head's arithmetic
  order and floating-point exceptions; do not silently replace exact production
  operations with an approximation.
- The combined Zvfh-enabled runtime does not select the no-Zvfh M4 quantization
  opt-in. Any further projection optimization must check actual compile-time
  and runtime selection, not assume all earlier standalone gains are cumulative.

## Execution policy

Use independent build/output directories and immutable worker inputs. A
long-running service directly owns its worker. Confirm build versus actual
simulation explicitly, then avoid frequent polling. Use GNU tools and VCS on
the host; no Verilator, URG, ZCC, synthesis or physical evaluation in this plan.
Representative VCS workloads should remain within roughly three hours without
dropping the behavior needed to distinguish the hypothesis. Failed original
evidence is preserved; do not increase timeouts or shrink workloads blindly.

The first new service is `quantkv-current-graph-20261026-01.service`, with fresh
build and output under `verification/out/quantkv-current-graph*-20261026-01`.
It reused the reviewed `run_strided_graph.py` and completed PASS: 16 native calls,
160 commands, two formats, two layouts, 128/5 visible-token prefixes and six
fallback cases. Parent raw-log replay agrees; the receipt is
`verification/akv/results/current-ggml-graph-20261026.json`.

The fresh model worker is `quantkv-current-model-20261026-01.service`. It consumes
that checked graph result and rebuilt actual llama.cpp using current shared
sources. It completed PASS: 112 native Attention calls, 448 commands and six
paired logit comparisons with zero max-absolute error, RMSE and KL. All four
independent contexts generated the same three tokens. The receipt is
`verification/akv/results/current-llama-model-20261026.json`. This is short-model
functional evidence under QEMU, not model throughput or long-generation quality.

The next candidate is an explicit grouped-PV leaf: retain one decoded V vector
across heads and avoid a separate Y round trip on maximum updates. Prototype
work is isolated in `verification/akv/quantized_kv/grouped_pv/`; its
`INTEGRATION.md` states the arithmetic and promotion gates. Host/code-generation
tests passed, and actual RVV execution under QEMU passed 13824 numerical and
17 rejection cases at each of VLEN256/1024. The receipt is
`verification/akv/results/grouped-pv-reference-20261026.json`. Full online
integration and paired RTL timing remain pending. No RTL or production dispatch
changes are justified by the leaf prototype alone.

## Grouped-PV integration in progress

The shared SDK now has additive `*_grouped_pv` runtime/GGML entry points and
`akv_quant_online_shared_grouped`. The old entry points retain the old callback
schedule. The new entry groups only the PV arithmetic: each head still consumes
tokens in order, a maximum update uses a separate rounded multiply before FMA,
and final normalization still uses the original scale binding. It shares the
existing format/layout/RNE/memory admission and workspace; no RTL change or new
cross-call state is introduced. Fast-math builds reject the new entry before
execution rather than weakening its numerical contract.

The private llama.cpp adapter has an explicit default-OFF
`GGML_RISCV_AKV_GROUPED_PV` switch, guarded by the actual RVV/SIMD compile macros.
A separate trace line reports the requested grouped path and completed groups.
This adapter change is pending real GGML and model validation; merely building
the SDK does not establish that the new path was selected.

Whole-schedule checks now pass at host O0/O3 and actual QEMU RVV VLEN256/1024:
2800 inputs per configuration, 12 injected callback failures, six preflight
rejections, exact output/maximum/sum/flags, callback work/order, padding guards,
and an independent double-precision softmax oracle. See
`verification/akv/results/grouped-online-reference-20261026.json`. These are
deterministic schedule fixtures, not a substitute for real captured data or
VCS timing. Full-call paired preparation and actual GGML tests are the next
gates; performance benefit and default promotion remain unproven.

The first actual GGML suite remains FAIL due to a two-thread fallback checker
assumption. Its 32 native call records passed, but that is not a full-suite
acceptance. A separate 16-call control with both optimized paths disabled
produced identical complete outputs while caller FCSR varied between 9 and 11;
GGML dynamically distributes head chunks and does not aggregate worker fflags.
The successor changes only the two-thread comparison, retaining output bits,
FRM/VCSR and preset sticky flags. Native/single-thread exact CSR checks remain.
See `verification/akv/quantized_kv/grouped_pv/GGML_CHECKER_REVIEW.md`.

Two independent workers have been launched after review:

- `grouped-pv-ggml-20261026-02.service`: fresh actual-GGML build and functional
  suite; output `verification/out/grouped-pv-ggml-20261026-02`.
- `grouped-pv-vcs-pair-20261026-01.service`: one canonical RTL image, one fresh
  ELF, four complete Q4_0 K/Q8_0 V H6/D128/T128 calls in OFF/ON/ON/OFF order.
  Output `verification/out/grouped-pv-vcs-pair-20261026-01`. Simulation process
  and increasing interface cycles were confirmed; no long-run polling.

Both workers must reach checked terminal results before acceptance. The VCS
pair includes complete numerical/guard/CSR/work checks and independent protocol
checks; neither preparation nor launch is performance evidence. The next linear
projection candidate is recorded separately in
`qbs_projection_preparation_audit_20261026.md`; no production changes to that
candidate are made while the current consumers have frozen their inputs.
