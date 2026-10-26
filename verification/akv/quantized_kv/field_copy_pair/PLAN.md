# Fixed-field-copy measurement and software-path consolidation

## User scope

Complete two items only: measure the fixed-size field-copy change on the same
RTL and real complete Attention workload, then organize actual software paths
and feature switches. No synthesis, FPGA, broad final evaluation, new hardware
mechanism, or modification to the separate dirty llama.cpp checkout.

## Measurement acceptance

- Baseline is the implementation before 083d4ed8 (839a0362); candidate is the
  fixed-size copy implementation. Retain ordinary bulk K-panel transfers.
- Use original real Q4_0 K / Q8_0 V data and complete Attention operations with
  mapping, admission, preparation, gathering, compute and completion included.
- Both sides use the same actual canonical RTL image, flags, floating-point
  policy, input values, trial schedule and correctness checks. Rebuild every
  object affected by a changed inline header. Old primitive objects cannot
  silently stand in for candidate V decoding or admission.
- Record layout differences and control them where feasible. Do not present
  a new binary as the previous accepted ELF or reuse historical timing as a
  fresh paired control.
- Check output/golden tolerance, repeat consistency, FCSR/VCSR, command/work
  counts, guards and raw UVM protocol checks. Preserve failures and timeouts.
- Pin compiler, sources, programs, helpers and image before/after. Independent
  result review must precede any reported performance acceptance.
- Long jobs run under a directly owning systemd service in fresh directories;
  confirm actual execution once, then do not repeatedly poll.

## Software-path acceptance

- Source-grounded inventory of default, explicit opt-in, and negative-result
  disabled paths with actual switches, capability/shape gates and fallback.
- Separate shared software, standalone experiment and actual llama.cpp backend
  integration. Explain rebuild requirements and any integration drift.
- Preserve opt-in policy and ordinary RVV fallback. No unsupported promotion
  of experiments to defaults merely because one captured shape passed.

## Ownership

Preparation agent owns prepare/. Execution agent owns worker/. Documentation
agent owns hardware/docs/qbs_akv_software_paths.md and any software_paths audit.
Parent reviews frozen artifacts, launches only after preflight, independently
checks results and commits accepted artifacts. Old sealed helpers are read-only.

## Initial source review (2026-10-26)

The intended comparison uses two fresh six-call H/S/B/B/S/H binaries, each with
the genuine six-query-head, D128, 128-visible-token Q4_0 K / Q8_0 V workload.
Each run must retain 4608 checked output words and 16 native QBS commands.
Retirement tracing is not required for this performance comparison; keep the
existing original numerical and protocol gates instead. The current source
change affects main and runtime inline consumers, not only one leaf function.

The separate llama.cpp checkout is dirty and remains read-only. Source review
finds GGML_RISCV_AKV_QUANT_KV as an OFF-by-default CMake option and an explicit
runtime environment gate. Its entry distinguishes complete, pre-admission
fallback and post-admission failure; the latter aborts rather than silently
rerunning fallback after possible partial output. This is source evidence,
not proof that an existing compiled model binary contains the new headers.
