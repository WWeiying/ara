# Normal Runtime Integration

The reviewed combined delta was installed on 2026-10-28 UTC into the local
llama.cpp runtime. It changes no RTL. Installation is not model acceptance.

## Installed Changes

- Both direct M4 preparation and cache misses use the same packed producer
  selector. `GGML_RISCV_QBS_M4_PACKED=1` enables it; unset remains the original
  producer. Cache identities distinguish the producers.
- The shared one-byte-interleave Q8_K/Q8_0 preparation path gathers legal
  noncontiguous F32 rows blockwise, for QBS and ordinary RVV. Dense inputs keep
  their previous path. Other interleave layouts are unchanged.
- Canonical controller and gather helper are under `software/qbs/ggml`.
  `installed-runtime.patch` is the scoped external-runtime delta, not a dump
  of unrelated local llama.cpp modifications.

## Evidence and Recovery

Before installation, all 1993 entries of the promotion manifest matched.
Original files and exact candidate bytes are retained under
`verification/out/m4-packed-promotion-20261028-01/{before,candidate}`.
All four installed runtime files were checked byte-for-byte against those
candidates. No other external runtime file was replaced.

`../COMPLETE_CALL_REVIEW.md` independently replays the measured slice and
protocol evidence. The service was also checked by the parent: inactive,
MainPID=0, Result=success. The measured 1.4231231x speedup is for the complete
Q/V/K slice, not a complete GGML graph or model.

The old preparation manifest remains a pre-installation record. Its live-file
hashes are expected to differ after installation; never refresh those hashes
to disguise the change. New builds capture a new source inventory.

## Pending Acceptance

Normal CMake build: `verification/out/m4-packed-normal-build-20261028-01`,
directly owned by `m4-packed-normal-build-20261028-01.service`.
At writing, configuration is running; no build PASS is claimed.

After that build passes, use `../../run_packed_installed.py` for graph/model
acceptance with four normal libraries and no object overrides. Its successor
driver switches packed and cache together, and requires actual execution of
both producers, not only cache hits. Repeat the accepted strided-view cases
against the normal libraries as well. Until these checks pass, retain opt-in
selection and do not claim complete model qualification.
