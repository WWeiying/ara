# AKV Direct Lease: Isolated TEST Kernel v4

This is a candidate overlay for the local Linux 6.19.6 tree, not a deployed
board environment or a production-compatible kernel. No SDK source is edited.
The default is CONFIG_RISCV_AKV_DIRECT=n. Enabling it intentionally changes
AKV compatibility for the entire boot, not just while a lease is held.

## Activation and configuration

On hardware exposing the exact 0x414b5601 signature in CSR 0x5c0[63:32], boot
sets STRICT and never restores legacy mode. All unleased native AKV/GGML and
supervisor AKV are denied. The ara_resident module is explicitly rejected,
including forced module loads. Ordinary RVV and QBS are not gated by this CSR.
An absent/unknown CSR gives ENODEV from GET_INFO/ACQUIRE, via exception-table
fixups, not a kernel panic. On old hardware the missing gate cannot enforce
isolation: do not treat that boot as a direct-lease environment.

The prepared configuration is RV64 + MMU + FPU + standard V, SMP=n,
PREEMPT_NONE=y, PREEMPT_RT=n, SUSPEND=n, HIBERNATION=n, CPU_IDLE=n, KVM=n.
The build records the complete configuration diff. Both native and portable
benchmark modes must use this same TEST kernel; an old SMP baseline is not
directly comparable. Admission also requires the only online CPU to be hart0.

## Contract and hooks

The main-owned direct_uapi.h is copied unchanged to the kernel UAPI directory.
Both structures are 64 bytes. GET_INFO reports ABI1, feature bits 7 (lease
mechanics, NOT arithmetic capability), signature and monotonic generation.
ACQUIRE accepts only abi=1 and bytes=64; every other input bit must be zero.
The root/CAP_SYS_RAWIO owner must be a single-thread, untraced non-init task
with an unshared mm, allocated/initialized V state and saved user VS/FS
enabled. Execute ordinary V and FP setup before acquiring, not just prctl.
The task and mm are bound, not just the numeric PID.
RELEASE accepts arg=0 and only the bound task/mm; no lease is ENOENT, another
task is EPERM, unknown commands are ENOTTY. The device mode is 0600. No caller
can request supervisor permission, and there are no arbitrary user callbacks.

Owner user entry closes the gate and drains vl with actual kernel VS
temporarily enabled/restored, then marks saved user VS and enabled FS DIRTY.
This precedes ecall vector discard and also runs at generic user entry. A
UP grant flag avoids a second ecall drain. switch_to uses the same guard if
a grant remains, so it cannot bypass the drain. Only the active owner gets
UALLOW at final user-return preparation. Ordinary syscalls, including gettid,
and timer scheduling are allowed, with normal Linux vector syscall ABI rules.
There is no ioctl per calculation and no IRQ-off computation window. Kernel
vector save/restore does not authorize supervisor AKV.

MMU notifier invalidation-start/release drains and revokes before PTE/page
changes. Pending signal handling revokes and queues SIGKILL before handlers
or restart. All user page faults while leased are fatal, including ordinary
lazy faults; they never reach handle_mm_fault or REFILL retry. Unhandled user
traps and misaligned emulation are also intercepted. Fork/clone, exec and
affinity-changing syscalls revoke/kill before dispatch; exit drains before
exit_mm. A revoked FD remains exclusive until close/release. Inherited or
transferred FDs cannot perform the owner's RELEASE. Prefault buffers, code
and stack before acquiring; prefaulting is not an isolation proof.

## Cleanup and hardware prerequisites

Under a short UP local-IRQ-disabled lock, cleanup closes UALLOW, saves actual
VS and VSTART, enables VS, reads vl and fences, zeros VSTART, enables only
STRICT|SALLOW, issues RELEASE word 0x0000505b, reads vl and fences again,
closes SALLOW, and restores VSTART/VS. It does not call kernel_vector_begin
or kernel_fpu_begin, and must not write VRF. First acquisition performs the
same cleanup to invalidate any pre-boot legacy context. A RELEASE trap is
fixed up, returns EIO and permanently poisons future grants.

This sequence is safe ONLY if hardware guarantees all of the following:

- External-memory FULL/REFILL and Resident operations retain their request
  through terminal completion/fault. Local LOAD/COLUMN_LOAD may early-ack;
  explicit owner-entry and teardown vl drains finish that replay before
  VRF or lease ownership transfer. There is no universal terminal-before-IRQ
  assumption and no reliance on vsetvl as a drain.
- The vl CSR read plus fence drains custom memory operations, including fault
  completion. Gate closure by itself is NOT a drain.
- RELEASE at VS enabled/VSTART0 invalidates every native/resident context,
  writes no VRF/VL/VTYPE/FCSR, and needs no user addresses or retry.
- MMU/PMA permissions apply to every custom access and custom faults arrive
  as user exceptions. No stale autonomous refill continues after terminal.

If these conditions fail, this overlay is not ready for board use. Neither
host tests, kernel compilation nor an absent-CSR QEMU boot proves them.
Poisoning prevents new grants after cleanup failure; memory safety still
depends on terminal/drain completing before RELEASE can fail.

## Reproducible build

Use verification/performance/resident_deployment/direct_cost/linux/incremental_v3.py
with --parent pointing at the completed v3 output and --out at a NEW
directory under ara_dsa_signoff_integration/verification/out. It freezes
inputs and a reflink/copy of Linux, cleans only that copy, emits and applies
linux-hooks.patch, runs host ABI/validation tests, compiles touched objects
first, then builds Image. Logs, source pins, base source inventory, full
config diff and result.json remain in that output, including on failure.
Do not edit these inputs while the build is running; use a successor after
review/pinning. No board, production module, QEMU arithmetic or VCS run is
part of this build. Runtime lifecycle/CSR validation remains outstanding.

The sealed v1 overlay failed compilation because Linux 6.19 removed no_llseek.
This successor changes only that operation to NULL; nonseekable_open remains.
The build helper also disables ACPI_PROCESSOR to prevent selection of CPU_IDLE.
See ../REVIEW_V1_20261113.md for scoped hardware evidence and validation limits.

The v3 predecessor removes the skipped-VS-save assumption via explicit entry
drain and dirty marking before Linux V discard/save/restore. The inherited
.config/UTS release is retained for incremental build identity. The instruction
class distinction is in ../CONTRACT_V3_20261113.md; its proposed explicit
entry drain is now implemented. Runtime validation is still pending.

V4 never promotes saved VS=OFF: dirty marking is conditional on saved VS
being enabled, as it already is for FS. Final return revalidates allocated
V state, enabled saved VS/FS and V control before UALLOW; invalid state is
revoked and the owner killed. These checks also cover state changes made by
ordinary syscalls while the lease is active.
