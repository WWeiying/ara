# F16 AKV Paired-Head Full-Call Evaluation

This campaign keeps the accepted post-area RTL and VCS image unchanged. It
evaluates the existing paired-head/PANEL4 implementation before modifying any
production default, SDK policy or GGML integration. It does not measure PPA.

## Stages

1. Real Qwen3 D128/GQA2/T137/capacity256, one KV-head group, tiles64+64+9.
   The same ELF executes generic/candidate/candidate/generic. Full-call timing
   includes preparation, admission, native execution and the original final
   drain. Mathematical work, per-head accumulation order and precision remain
   unchanged. Shape or preparation differences are not counted as speedup.
2. Reuse the existing bounded regression stimuli for D64/D96/D128, odd heads,
   tile tails and the existing D128/GQA6 specialization on this current image.
   Derived captures remain labeled as derived, not new native model shapes.
3. Only after reproducible benefit and correctness are established, improve
   call-local shape/type/capability selection for the main GGML runtime. Keep
   original generic/RVV fallback and the optimized six-head path. Do not use
   process-wide environment mutation as a per-operation selection mechanism.

## Gates

- Freeze committed SDK and real captures, not dirty assembly or runtime files.
- Full output bits, captured/native references, FCSR/VCSR/VSTART, guards and
  original input signatures must pass. Caller checks are outside timing.
- Reconcile every lifecycle, K-column/PANEL4, V-row and byte-work record.
  Generic and candidate have different valid command signatures; a marker
  claiming candidate selection is not evidence of executing that path.
- Check independent vector-allocation signatures and UVM backend/AXI reads/writes.
- Source/image/ELF/data identities must match before and after execution.
- Report performance separately from functional PASS. A useful default candidate
  needs at least 5% full-call cycle reduction and clear separation of the two
  arm samples; confirm a second representative shape before promotion.
- Numerical failure or image/checker drift stops affected dispatch. Preserve
  the first failure; do not weaken a sealed checker or retry blindly.

The owner is `run.py`, executed directly by a systemd user service. Each VCS
run uses a fresh directory under the sole verification worktree, has a maximum
of three hours, and is not polled at short intervals. `--preflight-only` checks
identities and the image/memory contract without claiming an RTL result.

No synthesis, FPGA rebuild, new arithmetic array, SRAM or wider interface is
part of this goal. Historical functional PASS does not substitute for current
image measurements, and operator speedups are not whole-model speedups.
