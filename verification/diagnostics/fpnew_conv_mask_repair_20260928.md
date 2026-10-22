# FPNEW CONV repair handoff

Root: `/home/wangwy/openproject/ara_dsa_signoff_integration`.
RTL/TB/script frozen; final half extended source manifest rechecked against current
files with all 12 entries OK. No TB edits followed the final passing run.

## Two measured defects

1. Physical finest-format masks were indexed directly as conversion-lane masks.
   FP32->FP16 mask0101 lost active upper sNaN NV: raw status10, mask0,
   merged00. FP16->FP32 mask0011 enabled an unused upper tail: raw xX,
   mask1, mergedxX. Numerical gap29 results matched while flags failed.
2. Mask-only repair left 76 extended failures. Sparse per-lane input validity
   allowed different-format tokens to diverge under common lane0-controlled
   output readiness. In the mask-only CSV, cycle393 master tag364 and upper
   tag365 were consumed together; cycle573 lower tag444 and upper tag445
   mixed upper NV into the preceding conversion. This explains incorrect
   results, flags and output changes under backpressure. These are real RTL
   failures, not testbench races or invalid FP16/INT8 proxies.

The FP16->INT8 test uses src/dst FP16 with int_fmt INT8, matching VMFPU
proxy mapping; expecting four integer elements is valid. Package capabilities
were unchanged between the 76-failure and passing runs. No failing checks were
removed and no drains were inserted between adjacent operations.

## Repair scope and invariant

Only `hardware/deps/fpnew/src/fpnew_opgroup_multifmt_slice.sv` changed for this
repair. Existing DIV mapping and validity/format-based status filtering remain.

- F2F mask index: lane * max(source FP width, destination FP width) / finest width.
- F2I uses actual integer destination width, not destination FP routing proxy.
- I2F uses actual integer source width, not source FP routing proxy.
- CPKAB/CPKCD retain direct independent-operand mask mapping.
- Out-of-range physical indices return zero; scalar lane0 retains mask0.
- Every CONV lane and the CONV bypass now receive every token and common ready.
  Equal pipeline occupancy is maintained across formats/scalar transitions.
  A token-aligned auxiliary participation bit suppresses unused lane outputs;
  existing status filtering therefore also suppresses unused X status.
- No new stages or serialization; dummy lanes may switch more often.

## Evidence

All paths below are relative to `verification/out/`.

| Directory | Result |
| --- | --- |
| fp16-conv-mask-unit-before-20260928-01 | Historical original RTL: 562 failed checks |
| fp16-conv-mask-unit-after-20260928-01 | Historical mask-only RTL: 76 failed checks |
| fp16-conv-mask-unit-lockstep-20260928-01 | Final half extended: 696 sent/received, 0 failures; 608 adjacent, 435 output stalls |
| fp16-conv-mask-unit-byte-20260928-01 | Final finest8 extended: 712 sent/received, 0 failures; includes CPKCD |
| fp16-conv-mask-unit-scalar-20260928-01 | Final scalar-only: 4 sent/received, 0 failures |
| fp64-fp32-conv-lockstep-regression-20260928-01 | Final existing FP64/FP32 regression: 16 sent/received, 0 failures |

Primary pipeline evidence is the lockstep directory: `run.log`,
`run.exitcode` (0), `sources.sha256`, `sources.check.log`, `lane_probes.csv`,
and source snapshots. Its exact success marker is `PASS fp16_conv_mask`.
The byte and scalar runs have the same marker. FP64 marker is
`PASS fp64_fp32_conv_flags`.

Reproduction command (requires a new output directory):

```sh
bash verification/uvm/run_fp16_conv_mask_unit.sh NEW_OUTPUT_DIR half extended
```

Source hashes include a relative snapshot path: run `sha256sum -c sources.sha256`
from the evidence directory, not the repository root.

## Registration and remaining gates

Canonical dependency patch exported to `verification/patches/fpnew-local-fixes.patch`;
`verification/patches/dependencies.json` records SHA256
`2b463ccb376662d1982b2a74dae90996b20958b5fea80414102e75c7cfd012f0`.
`patch_state` is `applied`; only the slice patch section changed relative to the
previous registered bundle. Dependency-patch tests: 21 passed.

No known CONV unit failure remains. Independent read-only review found no static
blocker. Curie/parent review remains the parent-controlled release decision.
Tests exercise production two-register DISTRIBUTED configuration; flush is not
exercised. Full-system six FP16 modes, adjacent conversions, AXPY and campaign
gates remain with the parent; these unit results do not claim their completion.

The attempted DIV regression in `divsqrt-conv-lockstep-regression-20260928-01`
did not simulate: the supplied whole-SoC filelist introduces ara_tb hierarchical
references unresolved under the standalone unit top (XMRE). This is a harness
compile failure, not a passing DIV regression or observed RTL failure. Existing
DIV mapping/status logic was preserved; no unrelated debug expansion was made.
