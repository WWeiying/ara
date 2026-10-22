# Eight-operation native harness repair, 2026-10-08

## Failure attribution

The original run remains **FAIL**, not a coverage-qualified PASS:
`verification/out/masklogical-restart8-build04-20261008-01/`.

- First exception: `trace_hart_0.log:220323`, time 2626930000,
  PC `0x8000668e`, Environment Call User Mode.
- The original disassembly identifies this instruction as `_fstat`'s `ecall`,
  immediately following `li a7, 0x50` at `0x8000668a`.
- Subsequent instruction access faults at `0x001fffffffffff00` are trap-path
  fallout, not the first failure.
- The test included `<stdio.h>` and called `printf`; merely linking common
  `printf.c` does not rename that call. The common implementation is `printf_`,
  selected through the macro in `apps/common/printf.h`.
- Original `native-link.log` includes libc printf/vfprintf and libgloss
  syscall stubs. Original main calls `printf` at `0x80006ba0`.

This is a native software harness fault. Spike uses a different HTIF runtime;
its successful preflight did not validate the native terminal path. No RTL
modification or rebuild is needed for this repair.

## Completed computation evidence in the failed run

Read-only parsing of the original `commit_trace.csv` and `vector_trace.csv`
gave the following results against the sealed independent Boolean reference:

| Operation | Architecture sequence | Allocation / completion | Correct destination bytes |
|---|---:|---:|---:|
| VMAND | 8 | 1 / 1 | 128 |
| VMNAND | 19 | 1 / 1 | 128 |
| VMANDNOT | 30 | 1 / 1 | 128 |
| VMOR, vd=vs1 | 41 | 1 / 1 | 128 |
| VMNOR | 52 | 1 / 1 | 128 |
| VMORNOT | 63 | 1 / 1 | 128 |
| VMXOR, vs1=v0 | 74 | 1 / 1 | 128 |
| VMXNOR | 85 | 1 / 1 | 128 |

All eight instruction retirements match their original ELF PCs and words.
Every operation has VL=1024 and vstart=256. Complete VRF destination writes
match the independent reference, including the preserved prefix. All 1152
distinct result/guard bytes were read back through retired LBU instructions
and matched, with zero mismatches. No truncated CSV row was encountered.

Reconstruction of scalar register writes before the final printf call gives
`a2=0x2091=8337` checks and `a3=0` errors. These are argument values in the
retirement trace, not an invented console PASS. Normal MMIO completion was
not reached; the failed run must not be promoted to full acceptance.

## Minimal successor

- `masklogical_restart8_nativefix.c` includes stdio first, then the common
  printf header only for native, then includes the sealed original C body.
- No vector instruction, data pattern, alias, restart value, self-check,
  prefix/guard comparison or check count changes.
- `build_masklogical_restart8_nativefix.py` reuses the existing Build class
  without editing its file. Native linking uses `-nostdlib`, explicit common
  runtime objects and compiler builtins. It rejects ECALL, libc/libgloss
  linkage, ordinary printf and known syscall/stdio helper symbols.
- Spike retains the original stdio/HTIF path and independent reference.
- `run_masklogical_restart8_nativefix.py` selects the successor ELF and reuses
  the frozen eight-case acceptance, bind_build, pins, timeout=900 seconds,
  exit recording, architecture sequence/word binding, retirement PC checks,
  full destination comparison, native readback and normal MMIO terminal.
- The original C, build helper, runner, ELF and failed logs are unchanged.
  The fixed 23-case suite and cache prerequisite are unchanged.

## Preflight and handoff

New preflight directory:
`verification/out/masklogical-restart8-nativefix-preflight-20261008-01/`.

- Spike: eight operations, 8337 checks, 1152 independent reference bytes PASS.
- Native runtime guard: printf_, no ECALL, no libc, no libgloss PASS.
- Runtime guard unit tests: positive and five negative fixtures PASS.
- Existing runner tests repeated against successor ELF: positive and nine
  negative fixtures PASS. These are checker tests, not RTL simulation.
- Native build04 rerun: **pending parent scheduling**. No EDA task launched
  by this repair helper.

| Artifact | SHA256 |
|---|---|
| New native input.elf | `a306e117bab7c28967da01ff38b7a23bc21ac1690ac222d84f2e4b674524485b` |
| Native wrapper C | `cc38991465d7b0eaee54dc9d0254e02d7c5ab56bda512a2996232493f9010c04` |
| Successor builder | `6637fe63ec252dc9f20b850fdb1c52ca87c26562f1d06c1e3dc5dd3b240ab501` |
| Successor runner | `8995f8d0581335752aadb64db3add5ea2a77b0008466dfdf0decb18d1444ae3c` |

From this worktree, with the existing build04 directory and a fresh output:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/usr/lib64/python3.9/site-packages \
verification/tools/soc-venv/bin/python \
  verification/coverage/run_masklogical_restart8_nativefix.py \
  --build /absolute/path/to/build04 \
  --output /absolute/path/to/new/nativefix-run
```

The 68-case runtime successor belongs to Avicenna; it is not edited here.
