# V reuse experiment: do not promote

The bounded cross-query-group V cache is rejected for production. Neither
copy transport nor direct cached-row transport establishes an improvement.
No third variant or additional long performance run is planned in this round.
The existing production Prefill executor remains unchanged.

## Completed direct-pointer measurements

Real Qwen3 capture, queries 0..7, GQA2, D128, one KV head; complete C execution
entry including admission and scatter. Both cases use Q8_0 V. Four ABBA trials
compare original grouped Prefill against bounded direct cached-row consumption.

| K format | Original mean cycles | Candidate mean cycles | Latency increase |
|---|---:|---:|---:|
| Q4_0 | 152800 | 158661 | 3.835733% |
| Q8_0 | 154852 | 161463.5 | 4.269561% |

Both workers finished PASS: all 2048 outputs per trial satisfy the real golden
tolerance, paired output bits match, FCSR=9 and VCSR=5 match, and independent
protocol checkers return PASS with no issues. Each comparison keeps eight
QBS commands and reduces V decodes from 12 to 8. Reducing those calls is not
sufficient to improve complete-call latency.

All 886 source/image/artifact pins per worker were independently rehashed
after completion, with no drift. Accepted results:

| Result under verification/out | SHA256 of result.json |
|---|---|
| value-pointer-q4-vcs-20261029-01 | 82aa9429c8fbe5a7c59b85a812e91e6cd945a0135698a0b3061bae56758d2d19 |
| value-pointer-q8-vcs-20261029-01 | 2e39b7e4ff70523559d85bac8b86ccb25c4b0cab3dbe0289f7986d1fb40d5483 |

These are incremental comparisons against an already optimized native QBS
Prefill path, not against ordinary RVV and not whole-model throughput.
They do not establish the outcome for larger query batches or long contexts.

## Copy candidate: timeout, not acceptance

`value-cache-q4-vcs-20261029-01` and `value-cache-q8-vcs-20261029-01` exceeded
their 7200-second runtime limit. The logs printed four trial headers with
zero self-reported errors and worse candidate cycle counts, but the workers
did not complete their independent acceptance sequence. Their original
`result.json` files remain FAIL/TimeoutExpired. Do not label them PASS, use
partial output as a complete numerical check, or restart solely to obtain a
green status for an already unprofitable candidate.

## What is known about the cost

Static inspection established extra scalar copies in the first candidate.
Direct-pointer transport removes explicit intermediate copies but still has
cache control, larger state and different code/address layout. It also changes
where PV reads its values. The measured loss persists without those copies.
No cycle-level causal attribution separates these remaining effects, so the
report does not assign the loss to one unmeasured cache or pipeline stall.

The experiment answered the promotion question: both complete direct-pointer
pairs regress, despite less decoding. The precise split of the residual
overhead is not needed to reject this candidate. Keep the tests and evidence,
do not change production admission, floating-point order, or generic callback
semantics, and move to final acceptance of the useful existing changes.
