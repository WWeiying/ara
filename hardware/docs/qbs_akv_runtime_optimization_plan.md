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
that checked graph result and rebuilds actual llama.cpp using current shared
sources. Its result is still pending at this checkpoint. Do not edit its pinned
SDK or external source files while it runs.

The next candidate is an explicit grouped-PV leaf: retain one decoded V vector
across heads and avoid a separate Y round trip on maximum updates. Prototype
work is isolated in `verification/akv/quantized_kv/grouped_pv/`; its
`INTEGRATION.md` states the arithmetic and promotion gates. No RTL or production
dispatch changes are justified by this prototype alone.
