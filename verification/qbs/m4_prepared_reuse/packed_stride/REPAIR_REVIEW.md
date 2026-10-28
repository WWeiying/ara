# Padded-row input: private repair acceptance

## Confirmed failure

The original normal-library reproducer is retained unchanged at
`verification/out/m4-packed-stride-repro-20261027-01`. Its result is **FAIL**:
four contiguous controls pass, while all eight padded-row cases fail. Of 528
paired output values, 192 differ. The scheduler callbacks prove that the views
were not replaced by contiguous copies. All graph calls complete, all outputs
are finite, and complete source/padding/weight integrity checks pass.

The first mismatch is Q4_K, K256, N8, M4, one float of row padding, output index
8: expected `bfc2110f` (-1.51614559), actual `c0704f0f` (-3.75482535). Row 0 and
the M7 single-row tail match; rows 1-3 do not. This agrees with the source path:
the caller honors `nb11` for the start of a four-row group, but the callee
addresses subsequent rows as `x + row*K`. It is an existing GGML integration
defect, not evidence against the packed producer's arithmetic or the RTL.

## Repair structure

`repair.py` builds a private copy of the real `repack.cpp`; it does not change
the installed fork or the source-pinned VCS experiment. The normal compiler
recipe is retained, with dependency outputs redirected into the private build.
The only replaced link object is this explicit repack candidate. The exact
original test object, libraries, firmware, capture and checker are reused.

For QBS-tagged MUL_MAT:

- Dense input continues to the existing quantizer without a gather call.
- A non-dense four-row input is copied according to its actual element/row
  strides, one independent quantization block at a time. The same existing
  quantizer consumes that block and writes its normal interleaved output.
- The maximum scratch space is four rows times 256 FP32 values: 4096 bytes in
  an out-of-line helper. There is no full-K allocation or persistent copy.
- Element-strided single-row inputs in the tail and wide-M preparation paths
  use the same helper with one row. Ordinary row-padding alone already works
  in those single-row loops and does not invoke the helper there.
- The helper copies bit patterns with `memcpy`; it performs no arithmetic on
  activation values. Each block retains the existing scale, rounding, sum and
  output format. Cache admission and command scheduling are unchanged.

The template supports the existing 32-element Q8_0 and 256-element Q8_K
activation blocks. This implementation scope is broader than the graph
acceptance below: Q8_0 graphs, element-strided graphs and wide-M graphs still
require explicit integration regressions. MUL_MAT_ID is not modified or
claimed covered by this repair.

## Evidence

`verification/out/m4-packed-stride-repair-20261027-01/result.json`: **PASS**.

| Check | Result |
| --- | --- |
| Original 12 graphs / 24 matmuls | All complete successfully |
| Paired outputs | 528/528 bit-exact |
| Previously failing padded cases | 8/8 pass |
| Contiguous controls | 4/4 pass |
| Full activation, padding and weight integrity | Pass |
| Native QEMU QBS execution | Both Q4_K and Q6_K; no software emulation |
| Parent replay of raw output checker | Pass; equals worker result |
| Source/library manifest after execution | All hashes match |

Result SHA-256:
`b8c6b4e5a18bb2eeb4d8a53ebdbb0c0be155df9c682c9379b0b1a80f9f45dc48`.
Raw log SHA-256:
`4e3453e1f1e1cb79f015d40b3344e7c50e42f53c55e410fdd45a8596feb166e1`.

`test_gather.cpp` additionally passes 216 Clang/UBSan cases spanning one/four
rows, 32/256-element blocks, zero to 32 blocks, three element strides and three
row paddings. It checks exact gathered values, callback block count, complete
output addressing/canaries and input integrity. It tests memory/layout logic,
not QBS arithmetic. The host GCC sanitizer link could not run because its
installed libasan/libubsan shared-library targets are missing; no GCC sanitizer
PASS is claimed.

```sh
clang++ -std=c++17 -O2 -Wall -Wextra -Werror \
  -fsanitize=undefined -fno-sanitize-recover=all \
  verification/qbs/m4_prepared_reuse/packed_stride/test_gather.cpp \
  -o /tmp/ara-m4-stride-gather
/tmp/ara-m4-stride-gather

python3 verification/qbs/m4_prepared_reuse/packed_stride/repair.py \
  --output verification/out/NEW_PRIVATE_STRIDE_REPAIR
```

This is a bounded software-functional repair result, not a normal installed
runtime, whole-model, RTL timing, or FPGA acceptance. Normal installation must
wait for the active source-pinned projection consumer to finish, then include
fresh normal-library graph/model gates and the remaining stride/layout cases.
No hardware or runtime default was changed in this step.
