# Resident deployment adapter

This is a fail-closed adapter, not a VCU118 driver or a board authorization.
There is no accepted board binding in this directory. The default linked
binding returns NULL, before user CSR reads, INFO or custom instructions.
Do not link the default-deny adapter into the existing non-Resident native
build: leave `GGML_RISCV_AKV_PROVIDER_SOURCE` unset and Resident OFF instead.

## Platform gaps

- `software/llama/provider_link_fixture.c` is only a deny-all link test.
- Stage5 `models/final/provider.c` binds a closed static `/test`, exact model,
  single-vCPU QEMU Linux deployment. Its setup, procfs checks and scalar CSR
  restoration are not a general board driver or a scheduler exclusion policy.
- The FPGA Linux implementation is under
  `hardware/fpga/ara_dsa_vcu118/linux/`, not `hardware/fpga/vcu118/linux/`.
  Existing `diagnostics/restore_serial_fragment.S` restores architectural
  RVV registers/VL/VTYPE/VSTART. This does not establish save/restore of the
  private Resident QK/PV state, memory leases or accelerator ownership.
- Resident capability index 4 is deliberately zero in the SDK/RTL contract.
  Neither enabled RTL defines nor the candidate_all source configuration is
  composed hardware acceptance. This adapter does not invent a capability
  encoding or probe by taking SIGILL. Composed availability needs an exact,
  independently validated image allowlist or a future reviewed discovery ABI.

## Trusted binding

Implement `ara_resident_deployment_current_v1()` in reviewed platform code,
returning an immutable `ara_resident_deployment_v1` or NULL. Use
`ARA_RESIDENT_PROVIDER_V1(binding, HASH)` for its `resident` member; set the
binding ABI and size and supply the three authority callbacks. The contract
digest covers launcher, image, ISA, OS, models, memory and ownership policy;
it is provenance, not a secret or an application-controlled credential.

`observe` is a scalar-safe check on the actual calling thread before any user
CSR access. A reviewed kernel entry may establish image/owner/CSR access safety
only when its complete entry/return path is proven to preserve exact
FCSR/VCSR/VSTART, including nonzero VSTART, private state and any existing lease
on both allow and deny. Before that proof, no user CSR reads, writes or probes
are permitted; do not use an unaudited libc or syscall path to discover safety.
It must report all eight guarantees, matching digest, profiles,
lane count, VLEN and a current owner identity. Do not derive these guarantees
from environment variables, procfs RAM mappings, mlock, CPU affinity, a process
mutex or a one-worker setting. User callbacks must remain scalar and must not
run FP/vector or custom accelerator computation. Compile bindings with the
same scalar flags as the adapter. A supported kernel entry for observe/acquire/release
is permitted only when its complete entry/return path is proven to preserve
the required CSR state, private context and lease; this is not a blanket
authorization for ordinary Linux syscalls.

State protection must be one of:

- A kernel/firmware implementation that preserves the full Resident private
  state and ownership across every relevant trap, signal, context switch,
  migration and fault, not just ordinary RVV register state.
- A firmware execution domain that actually prevents preemption and excludes
  other users, including vector/accelerator use by interrupt and fault handlers,
  for the whole lease. A Linux application cannot simply declare this mode.

`acquire(authority, owner, request)` must atomically revalidate the observation
and enforce the exact spans and lifetime, including intermediate pages, access
rights, normal RAM, accelerator reachability, cache coherence, unmapping,
remapping, COW/faults and internal workspace. A nonzero cookie guarantees this
through SDK RELEASE. The platform must reject competing/nested owners and
handle owner death; an owner token must not survive fork, exec or thread reuse.
Returning zero retains no lease. Both outcomes preserve FCSR/VCSR/VSTART.

`release` validates the cookie and current owner even after authorization has
been revoked, and must reliably clean up even with nonzero VSTART. A reviewed
kernel lease-release syscall is permitted under the preservation proof above.
Preserve the exact entry FCSR/VCSR/VSTART on return; scalar CSR restoration is
permitted, but clearing BAD_VSTART or changing the caller's policy is not.
The existing admission reader rejects nonzero VSTART without a snapshot, so
it cannot serve as the cleanup snapshot helper. Linux may discard vector state
before the ioctl handler; a scalar handler alone does not prove preservation.
Finish follows SDK RELEASE/drain, not just command submission, and ownership
and memory lifetime remain protected until release is confirmed. Misuse,
unresolved release errors or inability to preserve the lease are fatal, never
permission to retry partially written output on RVV. Interrupted or repeated
cleanup needs explicit platform semantics before deployment.

This corrects an adapter documentation restriction, not an upstream ABI change.
Final 03 also supersedes the blanket observe/no-OS wording in the earlier
release erratum. The original 01 and 02 inputs/reports remain sealed. The
default-deny runtime is unchanged; this correction does not implement or
validate a Linux syscall path. The 03 audit checks comment consistency and
object identity; it inherits only the unchanged behavior scope of 02 and does
not repeat or relabel the 918-check executions as kernel-path validation.

The adapter cannot enforce these privileged guarantees. A binding that lies
can violate the contract; a successful host test is not platform acceptance.

## Independent native admission

Legacy native is separately opt-in via the `legacy` member: ABI/size, exact
resident provider pointer, the same digest, explicit operation mask and
`whole_process_ram=1`. The live observation must independently approve these
operations and whole-process RAM, including future internal stack/heap scratch.
Do not copy this flag from tensor span validation. With no legacy approval,
`ggml_akv_legacy_current_v1()` returns NULL. The current frontend also requires
legacy BASE admission before Resident, so Resident-only authority intentionally
does not make that frontend execute. This is a parent-integration constraint,
not a reason to grant unproved RAM authority.

The existing frontend retains shape/feature selection, whole-call preflight,
CSR guards and no-retry behavior. Eligible calls on a fully matching binding
can use its AUTO Resident policy. Unsupported Resident shapes retain separately
authorized native, otherwise ordinary GGML/RVV. BAD_VSTART is a hard rejection,
not vector fallback. Unknown or mismatched bindings return NULL without CSR
access; a stale provider pointer is rechecked at every state/admission boundary.
During a lease, guarantees must remain enforced asynchronously; checking again
after preemption cannot repair already lost private state.

## Configure

Use a fresh build-input directory and a reviewed binding source. The existing
llama CMake accepts one source and propagates its provider OBJECT to executables:

```sh
cmake -DARA_RESIDENT_DEPLOYMENT_SOURCE=/absolute/reviewed_binding.c \
  -DARA_RESIDENT_PROVIDER_OUTPUT=/absolute/fresh_inputs/provider_bundle.c \
  -P /home/wangwy/openproject/ara_dsa/software/llama/platform/configure_provider.cmake
```

Then pass `-DGGML_RISCV_AKV_PROVIDER_SOURCE=/absolute/fresh_inputs/provider_bundle.c`
to the existing Ara-optimized llama build. Do not globally set NORMAL_MEMORY.
Explicit `GGML_RISCV_AKV_RESIDENT=OFF` at configure time and runtime `=0`
remain authoritative. The bundle references source paths; freeze and hash the
binding, adapter, headers and SDK closure before consumption. This does not
modify existing CMake, platform.c, resident.inc, dirty SDK ASM or dependencies.

## Evidence

`verification/performance/optimization_extension/resident/run.py` runs bounded
host contract/lease tests, UBSan, GNU scalar object audit and bundle checks.
Its positive binding is a test double, not a deployable platform. It extracts
the fixed SDK with git archive; it never consumes local dirty SDK ASM.
All evidence goes to a fresh direct child of the sole signoff
`verification/out/`. No Linux boot, VCS, synthesis or board run is performed.
