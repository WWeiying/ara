# Optimization enablement acceptance

This campaign tests retained optimizations together before promoting a unified
configuration. It does not authorize synthesis, FPGA deployment, relaxed
numerical checks, memory authorization, or changes to sealed historical inputs.

## Final Disposition

The bounded campaign is finished. The final item-by-item decisions are in
`hardware/docs/OPTIMIZATION_ENABLEMENT_20261111.md`; current source, SDK and ELF
identities are in `software/llama/integration_manifest_20261111.json`.
Neither file is a new FPGA acceptance or an instruction-set signoff claim.

- Configuration, real lane combinations, nine SoC runs and their independent
  terminal audit passed. Shared FMA has a small measured latency cost; explicit
  disable remains available.
- Retained-maxima has target and real Qwen graph evidence. PANEL4 has current
  RTL OFF/AUTO evidence. Portable has target checks and a real native Refact
  pair, with its non-bitwise Decode differences reported rather than hidden.
- Original failures remain intact. Separate audits explain UART framing,
  post-build output path, and whole-model versus SDK-local vector CSR rules.
- Resident platform authority, global WIDE_M, conflicting alternatives and
  measured regressions remain restricted for the documented reasons.

## Acceptance Matrix

| Item | Required evidence | Final disposition |
| --- | --- | --- |
| Existing ALU/shift, VRF return, FIFO and storage sharing | Source identity and representative SoC regression | Retain current implementation |
| Shared integer multiplier | Explicit build selection; native integer and private borrower results | Included in candidate_all; combined gates passed |
| Shared FMA, compact pipeline and tags | Native results/flags; Resident ownership/results; complete-call regression | Included in candidate_all; functional gates passed, small latency cost retained explicitly |
| Resident QK/PV | Real lane and SoC results, CSR/VRF retirement, trusted software admission | Conditional route; never invent platform authority |
| Cooperative QBS M8 | Real multiplier results; complete-call cycles; format/producer contract | Conditional candidate; not global WIDE_M |
| Existing QBS/AKV, activation context and M4 reuse | Default-policy checks and existing full-program evidence | Keep optimized-profile defaults |
| Quantized KV, Grouped Prefill and Register-PV | Type/layout/state/memory admission and explicit-disable checks | Keep conditional defaults |
| Old GROUPED_PV | Mutual-exclusion review with Register-PV | Do not enable both |
| Retained-maxima helper | Target bytes/CSR/cache and actual K1536 graph | Conditional optimized-profile default |
| Features-v2 Resident | Whole-call evidence and GGML/provider contract | Explicit SDK route only; no blanket promotion |
| PANEL4 and Portable | Runtime admission, native execution and numerical evidence | Conditional selection; see exact scopes and metrics in final ledger |
| NORMAL_MEMORY, provider, emulation and tracing | Real deployment contract, not an optimization flag | No implicit authorization or emulation |

## Gates

1. `config_*`: Makefile define propagation, invalid combinations and unchanged
   generic configuration. This is configuration evidence, not functional RTL
   execution or PPA.
2. `lane_combo_*`: current frozen real VMFPU, shared arithmetic, borrower and
   Resident interfaces, independent arithmetic oracle and ownership checks.
3. `soc_*`: current frozen main RTL with locked dependency inputs; representative
   ordinary RVV, QBS M4/M8 and complete Resident QK/PV firmware. Test both output
   correctness and relevant complete-call cycles.
4. `run_host_policy.py`: actual default-policy header and actual platform
   admission implementation; explicit disables, no implicit authority and
   complete lease lifecycle. Host results do not prove native instruction
   execution or model performance.
5. `software_*`: numerical-contract, shape and runtime selection decisions for
   routes that cannot safely be enabled globally.

All new execution outputs belong under the sole signoff worktree:
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`.
Use fresh `enablement_*` names. Preserve first failures. A new functional
failure stops the affected gate; do not continue by weakening checks.

Long workers must be directly owned by their systemd service and use frozen
inputs. Confirm launch once, then inspect terminal evidence rather than
repeatedly polling. Do not edit a helper after its execution pins are sealed.

## Delivery requirements

The final decision ledger must list each switch, its default, actual gate
results and reasons for any restriction. A switch in an optimized profile does
not prove it ran. Preserve ordinary RVV fallback and generic build behavior.
Model functional evidence, RTL cycle evidence and FPGA acceptance remain
separate claims. No branch/tag or board image is changed by this README.
