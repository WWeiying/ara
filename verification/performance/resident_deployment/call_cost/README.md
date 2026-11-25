# Resident Linux call-cost candidate

This is a software-only candidate for the existing Resident-capable bitstream.
It is not a measured board speedup or a new hardware acceptance.

## Changes

- GGML passes contiguous K/V and the mask directly to the copying ioctl.
  Strided K/V is packed; query conversion and private output publication remain.
- Per-thread userspace workspace reuses allocation capacity, not tensor contents.
  Retained output is limited to 64 KiB; larger legal outputs use temporary storage.
- The driver reuses six aligned buffers behind the existing global accelerator
  mutex. Inputs are copied and checked on every call; output/scratch are reset.
  Pool storage is bounded by admitted shapes and released on device removal.
- Integer RVV checks replace scalar scans of Q/K/V F16 exponent fields. Finite,
  Inf/NaN, mask, scale and FFLAGS semantics are unchanged.
- Optional GET_STATS reports allocation/copy counts and phase times. Load the
  module with `profile=1` only for diagnostic runs; the default is `profile=0`.

Per-call vector policy/hardware admission, open/GET_INFO/close, normal-RAM
checks, the single-hart constraint, F/V ownership, IRQ protection and terminal
post-start failure rules remain. This is not DMA zero-copy or persistent KV.
Resident remains opt-in; do not enable it for full models before paired testing.

## Prepare (Host Only)

```sh
python3 verification/performance/resident_deployment/call_cost/prepare.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_board_pair_cost_YYYYMMDD_01
```

The script freezes the two base commits plus an explicit overlay list, excludes
the unrelated local AKV assembly, builds the static ELF and Linux 6.19.6 module,
tests host admission/packing/pool logic, tests the RVV finite gate on Spike, and
runs QEMU Linux negative/lifecycle checks. QEMU does not validate Resident
arithmetic or provide hardware performance. Inspect `qualification.json`.

## FPGA Handoff

Use the existing all-on Resident bitstream and previously validated Resident DT
and firmware. Do not replace the bitstream. The board must run the matching
Linux 6.19.6 module ABI and meet the existing single-hart/coherency contract.
Stop other Resident users before unloading the old module; a busy module must
not be forcibly unloaded. Load the bundle's `ara_resident.ko` with `profile=0`.
Never overwrite the old ELF/module/evidence; use a new board directory.

```sh
cd /path/to/new/board
sha256sum -c SHA256SUMS
uname -r
insmod ./ara_resident.ko profile=0
./resident-ggml-pair --probe
# RESIDENT_BOARD_ID identifies the actual board/bitstream.
RESIDENT_PLATFORM_ACCEPTED=yes RESIDENT_BOARD_ID=<board-and-bitstream-id> \
  RESIDENT_MODULE_SHA256=$(sha256sum ara_resident.ko | cut -d' ' -f1) \
  sh run_board.sh /path/to/fresh/results
```

Keep the same ELF for native/Resident, frequency, dimensions and input capture.
The three cases are D128, Hq=2, Hkv=1 and effective KV=65/128/137, derived from
the same real Qwen3 capture as the earlier board pair. Tests retain exact output,
FFLAGS, guards, input checksums, actual portal execution and no-fallback checks.
`GGML_RISCV_AKV_LINUX_REUSE=0` disables only the userspace allocation cache;
it does not restore the old driver or the previous packing implementation.

For a separate diagnostic run, unload/reload the module with `profile=1`, then:

```sh
RESIDENT_PHASE_STATS=1 ./resident-ggml-pair resident 137 > phases-137.log
```

This emits `PHASE` records. `buffer_ns` includes pool growth and zeroing;
`input_copy_ns` is kernel input copying; `address_check_ns` is RAM validation;
`execute_ns` includes F/V ownership, numerical admission and complete Resident
attention, not just RTL computation; `output_copy_ns` is publication.
`total_ns` includes mutex waiting and initial job validation. The phase ioctl
adds diagnostic overhead, so do not mix these samples into primary latency.
The counters verify fresh copying and zero allocation growth on repeated shapes.

Acceptance requires unchanged results and actual Resident execution. Report cold
and warm samples separately. A second-call page/cache transient is not evidence
of steady state. Only board measurements can establish whether the reduced
software overhead makes Resident competitive with native AKV. If Resident is
still slower, retain native AKV as the default and use phases to choose further
work; do not remove safety checks merely to improve the number.
