# Complete-call software optimization results

## Decisions

Keep the installed M4 prepared-activation cache available as an opt-in.
The complete Q/V/K slice improves, not merely its isolated preparation phase.
Keep grouped PV default OFF: its complete quantized Attention call remains
slower. No new RTL or additional arithmetic/storage resources are justified
by either experiment.

| Current-software comparison | Baseline paired cycles | Candidate paired cycles | Speedup | Cycle change |
| --- | ---: | ---: | ---: | ---: |
| Complete M4 Q/V/K projections | 1659431 | 1243088 | 1.33493x | -25.0895% |
| Complete quantized Decode Attention group | 961317 | 970618 | 0.99042x | +0.9675% |

Both are same-ELF ABBA trials using real model inputs and the same QBS hardware
on both arms. These are incremental software effects, not new RVV-versus-QBS
speedups. They cannot be multiplied together or substituted for model tokens/s.

## Projection attribution

The first four real rows from a Qwen2.5-1.5B Q4_K_M Prefill capture are shared
by Q, V and K. M=4 and K=1536; Q has 1536 outputs per row with Q4_K weights,
V has 256 with Q6_K, and K has 256 with Q4_K. All output channels and K elements
are retained. Every trial checks 8192 outputs.

| Sum over two trials | Recompute | Exact-byte reuse | Difference |
| --- | ---: | ---: | ---: |
| Plan admission | 11926 | 11967 | +41 |
| Preparation | 689620 | 272660 | -416960 |
| SDK/native execution | 955880 | 956466 | +586 |
| Remaining timed loop overhead | 2005 | 1995 | -10 |
| Total | 1659431 | 1243088 | -416343 |

Preparation savings explain the improvement; execution time is effectively
unchanged at this scale. Do not call the preparation difference a hardware
compute improvement. Cold allocation, owned input snapshot, exact comparison,
prepared-byte copying and final release are included. Cache construction,
initial repacking, numerical checking, actual GGML graph scans/threadpool
scheduling and intervening model operators are excluded. Those omissions
prevent declaring 25.09% lower complete model latency.

The four trial totals are 830187 / 621885 / 621203 / 829244 cycles. All target
numerical, byte, guard, input/weight integrity and CSR checks pass. Native work
is exactly 256 commands and 131072 result bytes across the suite. Independent
UVM checking passes: 87810 requests/responses and 84112 backend allocations/
completions, with no issues or aborts. Parent replay reproduces the raw-output
and vector-byte checks, revalidates source pins and replays protocol identity.

Receipt: `verification/qbs/m4_prepared_reuse/qkv/review-20261027.json`.
The isolated earlier 2.5502x preparation result has a different scope and is
not the complete projection speedup.

## Runtime integration and supported use

The canonical cache is installed in the real GGML RISC-V backend. Enable it
explicitly with both `GGML_RISCV_QBS_M4_PREPARE=1` and
`GGML_RISCV_QBS_M4_CACHE=1`. Do not enable grouped PV as part of that setting.
The checked normal-library model run compares 911616 logits bitwise, with
matching tokens, CSR states and native work. It reduces actual M4 producer
invocations from 386 to 220, with 166 exact-input hits. These activity counts
are not timing measured under QEMU.

Current reuse is bounded to one worker, supported contiguous Q8_K preparation,
RNE/zero restart, eligible graph consumers and the first eight four-row groups.
It owns input and output bytes rather than retaining GGML scratch pointers.
Unsupported formats, layouts, workers, shapes and single-row tails retain the
original path. Five weight families sharing the activation representation are
admitted only after the actual QBS capability/layout planner succeeds; this
does not mean five complete model-format performance campaigns have passed.

The tested slice supports retaining the optimization, not globally enabling
it for every model or batch. Broader real-input complete-call cases, graph
planning costs and multi-worker handling remain separate work before global
default promotion. No existing numerical contract or fallback is weakened.

## Attention decision and next attribution

The current grouped-PV build removes a repeated stride-check division but
still loses in the complete H6/D128/T128 Q4_0-K/Q8_0-V Attention call. Full
output/state/work and independent protocol checks pass; exact current results
and limitations are in `grouped_pv_current_source_decision_20261027.md`.
Do not claim savings from fewer V loads while ignoring scalar setup and
dependency costs. The original shared schedule already decodes V once/token.

Further Attention changes need bounded retired-PC/cycle attribution of the
current shared schedule before choosing a new implementation. Prioritize
genuinely repeated work in the actual caller over expanding native QK compute:
native QBS busy time is only a small part of this complete-call interval.
Keep hardware ownership, exception, CSR and ordinary RVV ordering intact.
