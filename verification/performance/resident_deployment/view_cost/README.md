# Registered live KV and batched Linux Resident calls

This candidate changes the Linux driver, SDK client and GGML portal, not RTL.
It has no measured FPGA speedup until the paired board run succeeds. It stays
opt-in with `GGML_RISCV_AKV_LINUX_VIEWS=1`, which also retains a per-thread FD.
The ordinary native AKV path remains available. The older copy portal still
works when this option is off.

## What changes

- Register read-only aliases of the existing KV pages once. Read current KV
  contents, including application updates between calls. Do not cache a second
  copy of the tensor. Honor token-major or head-major physical strides.
- Pin mappings with `FOLL_LONGTERM`, validate RAM pages once and retain interval
  MMU notifiers. Insertion and pinning use the interval sequence protocol;
  invalidation permanently rejects the handle. Never clear its invalid bit.
- Copy Q and mask once per batch, not K/V. Up to 16 head groups share an ioctl
  and one kernel F/V ownership scope. A group remains at most 8 query heads and
  256 KV tokens; enable interrupts between completed groups.
- Retain numerical admission, finite scans, exact output/flags checks, device
  epoch checks, one-online-CPU enforcement and the native fallback before work.
  No optimization skips ownership or memory validation.

## Contracts

Use the approved coherent-RAM device tree, locked matching kernel and module,
one worker and one online CPU. Exclude concurrent userspace, kernel, DMA and
firmware writes to the registered input while a batch executes. Read-only
kernel aliases do not make the original user mappings immutable. Do not free
or reuse tensor storage during a call. Close the retained FD at worker teardown.

Capacity is at most 256 tokens, 32 KV heads, and 1 MiB per K/V span. There are
32 handles per FD and a global 64 MiB limit on page-rounded pin charges. That
limit is not a promise about total physically retained huge-folio memory.
This is a privileged research driver, not a multi-tenant accelerator service.

Untouched/COW storage can invalidate itself while long-term pinning unshares
pages. Preparation should touch the intended KV storage before registration;
failure declines safely, never silently refreshing a stale handle. Pinning
cannot guarantee availability of arbitrary layouts or memory mappings.

Computation failure does not publish results. `copy_to_user` is not atomic:
copyout failure can modify a private user output prefix. GGML keeps these
destinations private and publishes to its destination only after every batch
succeeds. Any failure after a successful group/batch is terminal, with no replay.

## Board experiment

Use one matching new module and the same existing bitstream. Do not replace
the accepted application. `run_board.sh` does not install modules or reboot.
The board session must verify platform ownership and save the old module first.

The bundle compares `native`, copy `session`, and registered `views`, interleaved
forward/reverse, with six warm samples per process. Points: 65/128/137 active
tokens, one/four KV heads. A separate stream case keeps capacity 256 and varies
active length and V values between calls. Four-head data replicates the real
captured Qwen3 head with alternating V signs; it tests batch/layout correctness,
not an independently captured whole attention layer. Independent goldens cover
original, negative and zero V values; output bits, flags, guards, unmodified
inputs, registration count and actual ioctl/group completion are checked.

Primary timings disable phase probes. For separate diagnosis use
`RESIDENT_PHASE_STATS=1 ./resident-ggml-pair views 137 4`; never mix that latency
with the primary samples. Full Linux call time, including conversion, submission
and copyout, is the acceptance measure. Reducing copy bytes is not itself a speedup.

Required qualification: host layout and portal tests with sanitizers, real
Linux mapping/lifecycle tests, and a focused VCS run of the exact new compute
object on packed and strided captured inputs. QEMU lifecycle checks alone do
not validate custom Resident arithmetic or FPGA timing.
