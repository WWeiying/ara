# CSR-Safe Model Provider Successor

The seven execution-v1 files and their five actual linked cases remain sealed.
This mechanical successor reuses the same checker, PID1, model inputs, libraries,
four-gate reader, one-shot service and launch policy. No model or AKV was run.

The independently executed OS probe is frozen at
`OUT/stage5_models_oscsr_20261110_01/result.json`, SHA256
`4951e7f36a1ee7b2df074721ddda9ddf6954fa3b6a08a91f41acb6b24a57a1ad`.
One old QBS-only QEMU boot of the actual pinned Linux Image produced six samples.
Three raw getpid calls cleared nonzero VSTART and set VL=0/VTYPE=vill; their
VCSR/FCSR were preserved. Three no-syscall controls preserved every sampled CSR.
This is a standard-RVV/Linux observation, not S3, native AKV, or model acceptance.
The three probe source files are sealed by that receipt; do not rerun the probe.

Each model child now calls explicit OS preauthorization before backend/model
work and before any seeded ROI CSR. The same hardware-probe, auxv, vector policy,
main-thread, one-task and CPU-affinity checks remain. Authorization binds the
thread pointer in this fixed, source-pinned process, which does not exec or
change vector policy after setup. It is not a general Linux capability grant.

`state` checks only cached authorization/thread identity before invoking the
sealed VSTART-first scalar CSR reader: no syscall, copy, or CSR write.
`acquire` first uses that reader, so nonzero VSTART rejects before even reading
the request. It retains all actual OS/task/affinity/mapping/span checks and
restores the scalar FCSR/VCSR/VSTART snapshot on every admitted-state return,
including failed eligibility. The entry snapshot can only have VSTART zero;
this restoration never hides a nonzero incoming VSTART. Linux's caller-clobbered
VL/VTYPE and vector registers are not promised preserved by this C callback.
`release` validates the cookie and thread pointer and clears the lease using
scalar memory only, including cleanup after BAD_VSTART. No syscall/CSR write.

Host tests inject syscall CSR clobbering solely to test these guards/restores;
they do not model numerical execution. The same GNU objects, actual four-library
link, full-logit/CSR/trace checker and actual four-gate S3 binding remain required.
Host limit8GiB, guest4GiB, single CPU, direct service, one attempt. No model run
is allowed from prelink; actual preparation rebinds the final accepted S3 image.
