# Decision: retain current Prefill query admission

Both paired real-input VCS experiments completed successfully, but the candidate
did not improve complete-call cycles. Do not promote it into canonical software.

| K-cache | Original grouped Prefill mean cycles | Block-check candidate mean cycles | Candidate slowdown |
|---|---:|---:|---:|
| Q4_0 | 145541.0 | 145883.5 | 0.23533% |
| Q8_0 | 146868.5 | 147574.5 | 0.48070% |

Each comparison uses its own ABBA ELF with fixed scratch/output addresses.
Both use Q8_0 V-cache and captured Qwen3 query positions 16..19, GQA2, D128.
The ROI includes admission, grouped execution and scatter. These figures are
not comparable as an incremental ratio against older per-query-vs-grouped
experiments with different executables.

Acceptance includes 1024 output elements per trial, paired bit equality,
captured-golden tolerance, FCSR/VCSR, four QBS commands, twenty V decodes, one
K panel and protocol checking. Each run's 885 recorded source/image inputs
were independently rehashed after completion; the raw-log parser and protocol
receipt were independently rechecked. Both checks passed. No production RTL,
runtime or default switch was changed by this experiment.

## What the evidence establishes

The GNU code-generation check establishes that an exponent-mask operation and
nonfinite branch were removed from the element loop. The complete VCS result
establishes that this source-level simplification is not beneficial for these
representative calls. Surrounding code generation, register allocation and
instruction-cache effects also change; the present data do not isolate which
one accounts for the small loss. It would be incorrect to attribute all cycles
to a specific pipeline effect without additional probes.

The candidate stays available as an experiment. Do not keep tuning it with
different compiler flags or input sizes merely to obtain a favorable result.
The existing production admission still provides identical functional behavior
and is the preferred implementation based on the measured complete-call cost.

## Evidence

Directories:

- `verification/out/query-guard-q4-vcs-20261029-01`
- `verification/out/query-guard-q8-vcs-20261029-01`

| Artifact | SHA-256 |
|---|---|
| Q4 result | `71180165058591b257b17e347643bcc2d44e8671b5a2ae0ab7d478ac69ca031a` |
| Q4 raw VCS log | `494ec29c50fcb6f6151e8d0d8e04d31e099d5d35503e40d4bf8564badd289818` |
| Q4 protocol receipt | `8fabe16d9cec0756ab860bc8145daf77d421cbfc2046cdbbd1e17628723abd86` |
| Q8 result | `9ee0001756da4a413a8e317ae4a8013e2202e2739fee808cfaabe1daf64ca8d1` |
| Q8 raw VCS log | `5dc4b62da813b27a9e179e18896296d8555e2419572485f8860a07b45492ebca` |
| Q8 protocol receipt | `314409b36173bf8f281e5bb6d23edb9c6405d65676c3ac1527fa799aa0427ac6` |

## Consequence for the broader optimization work

Together with the rejected hint-first cache lookup, this result argues against
prioritizing further small control-flow rewrites without a measured cost
breakdown. Keep the accepted quantization, cross-consumer reuse, grouped
Prefill, register-PV and hardware retirement changes intact. The remaining
broader task is real-runtime attribution and investigation of repeated data
movement across larger query groups. Those are not established speedups and
must not be presented as completed work.
