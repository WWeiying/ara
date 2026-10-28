# Ordinary RVV fallback: confirmed stride mismatch

The original normal-library run is preserved at
`verification/out/m4-stride-rvv-fallback-20261027-01`. Its result is **FAIL**,
with `conclusion=CONFIRMED`; successful reproduction is not a passing kernel.
No RTL or live runtime source was changed.

## Reproduction

- Q4_K weights, K512, N32, M4, VLEN1024. QBS, emulation, M4 preparation,
  packed preparation, cache, wide-M and activation-context flags are all off.
- QEMU has `xaraqbs=false`. Actual repack selection is
  `Q4_K_32x1_Q8_K`; QBS coverage reports zero selected tensors, and no QBS
  call or execution record is permitted by the checker.
- The activations and weights are genuine captured Qwen2.5-1.5B data, using
  the first 512 elements/two quantization blocks of each original row. There
  are 32 original weight rows, with no synthetic requantization.
- Three matmuls share the same logical values: dense reference, dense repeat
  control, and a VIEW with 4-byte element stride and 2112-byte row stride
  (16 padding floats between rows). Scheduler callbacks prove that the VIEW
  reaches repack without a hidden contiguous replacement.

| Logical output row (zero-based) | Mismatches | Outputs |
| --- | ---: | ---: |
| 0 | 0 | 32 |
| 1 | 32 | 32 |
| 2 | 32 | 32 |
| 3 | 32 | 32 |
| Total | 96 | 128 |

The first mismatch is row 1, column 0: dense `0xbb0ad2de`
(-0.00211828155), strided `0x3ee7b01b` (0.452515453). Dense repeat matches
exactly. Complete output dumps are finite; input, backing, padding, captured
weights and the repacked allocation retain their original bytes.

The harness stops immediately on this mismatch. Three prepared adjacent cases
(M7 padded rows and M4/M7 with 8-byte element stride) were **not executed**.
They remain useful repair regression cases, not additional confirmed failures.

## Cause and repair scope

The ordinary `tensor_traits::forward_mul_mat` selects the first row with
`i11 * nb11`, but calls a four-contiguous-row producer. That producer derives
the next row from `x + row*K`, ignoring `nb11`. This predicts the observed
matching first row and wrong remaining rows. The current private QBS gather
repair is guarded by `is_qbs_block_type`, so ordinary RVV misses that fix.

Extend the blockwise-gather call-site handling to the corresponding ordinary
Q8_K/Q8_0 repack producers, without changing their arithmetic or interleave
format. Keep dense input on its original path. Verify the original failing
driver and its unexecuted tail/element-stride cases, then regress QBS, packed
selection and cache rejection of strided inputs. Do not claim that compiling
with QBS disabled proves these execution paths correct. `MUL_MAT_ID` remains
a distinct path and is not covered by this reproduction.

## Evidence

Raw log SHA-256:
`b5e23b3b84ca55524c64a941d9cff86a3bebfb7f0d707121b8c9ef2535fd951a`.
`comparison.json` records all affected rows; `first-mismatch.json` retains
the exact first raw diagnostic. `manifest.json` records the normal archives,
captured data, original driver, ELF, initramfs and tools. The inherited active
VCS inventory was checked before and after this run.

The three checker tests replay the failure and reject inconsistent evidence.
This is a software-layout functional bug, not hardware timing evidence or a
newly demonstrated RTL bug. Repair and installed-runtime acceptance remain
pending.
