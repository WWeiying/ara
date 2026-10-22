# Full17920 M9 Terminal Metadata Review

Decision: `ACCEPTED_FULL17920_M9_METADATA_REVIEW_NOT_LINUX`.

- Original source: `rvv_fp_compare_unboxed_unmasked_e16_mf4`; runtime ID: `fp_compare_unboxed_e16_mf4_full17920`. The complete contiguous 32-seed parent history is accepted on frozen M9, not the Linux execution environment.
- Actual simulator wait: return code 0, 6687.05148726888 seconds, no timeout/failure indication. Producer completed with no abort or retry, within the unchanged 10800-second case budget.
- Actual ExecStopPost receipt: `SERVICE_RESULT=success`, `EXIT_CODE=exited`, `EXIT_STATUS=0`. This is the recorded service environment, not a later GC/default-state inference.
- Actual collector wait: 0, 9.037510651163757 seconds, not timed out. Independent observer subprocess wait: 0, not timed out. The single foreground inotify notification wait also exited 0; no follow-up progress polling was used.

## Exact Scope

The existing full strict report accounts for 17920 calls, 286720 result bits, 35840 guards, 17920 flags and vstarts, 326144 helper instructions plus three capacity instructions, 734720 fresh stores, 143360 input LDs, 17920 output LWUs, and 2240 record LDs.

All 10752 FPR committed writebacks are covered, 336 for each of 32 original raw seeds. This is committed writeback evidence, not physical FPR readback or an accelerator operand snapshot. The original malformed FP16 boxing remains unchanged.

Source-derived owner contract: 89600 required memory owners, 15360 required targets, and 2560 VL0-elidable targets. The full report pairs actual allocations/completions and accounts for 3413323 CSV rows. This terminal review reads only metadata, not the semantic CSV again.

## Binding

- Plan SHA256: `b6d0677124a045a35294a1c0be4a7b0f6a004f52e9f570e6e5b9478c4296bdbd`.
- Independent result SHA256: `3e93fcbcb3309cf16a18062d90377ded614772e42da30614c59243c145d33b61` (`result.json`).
- Producer complete SHA256: `8f9d7ac68ee54a98c8a704098ba307c2c9b29d74ede0ba1efb45b405f911b29a`.
- Collector result SHA256: `1ff1b0af52932ca1e2e759a86aee5f4a3766a63b8f128624bd1d474749e43dec`.
- Collector wait SHA256: `cebb6defc7f9fb4501c8507103db0a935128cc6c6a4a8643422d4459d259f4a0`.
- Closed CSV SHA256 inherited consistently from producer/strict/collector: `05b8a0413378031366c55e0f6e478a422d7fcfe989132dcd8f89c001b8b0bfa4`. No second CSV hash or semantic read was performed here.

The producer and collector report the 750-pin input set unchanged. This observer independently checked the exact plan/ready, original ELF, terminal executable identities, actual collector command, and the small terminal evidence hashes in `result.json`; it does not claim a second full 750-file/raw rehash.

Receipts: `attached.json`, `systemd_run.json`, `observer.wait.json`, `notification.json`, and `notification_wait.receipt.json`. Original prepared01 HOLD and all earlier failures remain unchanged. No new DUT/reference/build execution or RTL edit occurred in this observation task.
