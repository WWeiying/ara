# Q8_0 register-PV: complete online schedule candidate

## Status

This is an independent experiment, not the installed runtime. No RTL, ISA,
GGML dispatch, production fallback or existing measurement inputs changed.
The new schedule passes 896 synthetic complete-schedule cases under RVV QEMU,
including an independent scalar oracle. Unsupported-VLEN and non-RNE rejection
also pass. There is no measured hardware speedup for this schedule. The
preceding 12,928 passing leaf tests and these schedule cases do not establish
real-model whole-Attention integration or hardware performance.

## Purpose and data path

The current shared schedule decodes one Q8_0 V row into a float workspace,
then reads that workspace during each query head's PV update. The candidate
decodes up to four 32-element blocks into an RVV m4 register group, updates
the output heads, and never materializes that decoded row in memory.
It retains QBS QK head grouping (4/2/1), 32-token score tiles, token-order
online softmax, separate output rescaling, fused multiply-add, and final
normalization. It does not replace expf or change QK arithmetic.

The raw V view is explicit: base address, byte stride between tokens, and
accessible byte extent for the selected KV head. It is not a value callback
that falsely returns success without producing a decoded row. The original
plan's value/MAD callbacks are deliberately bypassed only in this experiment.
QK and final scale callbacks remain active.

## Admission and failure boundaries

- Supported candidate: VLEN=1024, RNE, Q8_0 V, 1--8 query heads, D=32--256 in
  multiples of 32, an admitted finite zero-mask visible prefix.
- Admission must establish finite Q/K/V and production arithmetic bindings;
  the inner schedule does not repeat the expensive content scan.
- View extent, address arithmetic, output/workspace/input overlap, plan and
  workspace alignment are checked before output initialization.
- Unsupported VLEN or rounding mode returns before callbacks/output writes.
- Buffers, plan and callback bindings must remain immutable during execution.
  Caller owns allocation validity and any opaque QK context aliasing checks.
- After initialization or the first QK callback, failure is terminal. Partial
  output must never be retried through fallback. Sticky flags are observed
  only at call boundaries; floating-point traps are masked.

## Executed regression

`verification/akv/quantized_kv/register_pv/test_online.c` compares the existing
shared schedule with the candidate for 896 synthetic cases:

- Heads 1 through 8; D=32,64,...,256.
- Visible tokens 1,2,20,31,32,33,65, crossing score-tile boundaries.
- Two initial sticky-flag states; increasing/decreasing repeated scores.
- Padded output and V rows; exact output, maximum, sum and FCSR comparison.
- QK call count equality; reference V decode count equals token count;
  candidate never calls the old V decoder.
- A short-view rejection preserves output and flags without calling QK.
- An injected QK failure propagates as terminal, not fallback.
- An independent scalar head-major loop computes decoded values, softmax and
  PV without the candidate/shared schedule or decode helpers; output and FCSR
  match exactly. It uses the same libm expf/fmaf primitives, not a separate
  high-precision mathematical oracle. Test scales are finite normal halves;
  the earlier leaf suite covers additional scale/arithmetic boundaries.
- RDN with sticky DZ rejects without QK/value calls or output/flag changes.
- A separate boot of the same ELF at VLEN=256 confirms unsupported-VLEN
  rejection without QK/value calls or output/flag changes.

These are deterministic schedule tests with synthetic scores and values, not
model or hardware-performance tests. The earlier leaf suite separately checks
captured real V rows and arithmetic boundaries.

Evidence: `verification/out/register-online-reference-20261028-01/result.json`
reports PASS, both guest exits zero and input hashes unchanged before/after.
ELF SHA256:
`0a4695f1f1e42651e41fc1577eac223f24f3c95b9c9edad8604d8a384c0187d6`.
Input-pins SHA256:
`49241378773f7f31e25a47a2d6db1c7e98d67df4c0e52a842e9da3e4bc4854c6`.
The runner is `verification/akv/quantized_kv/register_pv/run_online.py`.
Use a fresh output under `verification/out` and `--execute-reviewed` to run;
without that flag it only builds and reports BUILT_NOT_EXECUTED.

## Remaining acceptance

1. Synthetic complete-schedule comparison and unsupported-VLEN/rounding
   rejection are complete. Real captured Q/K/V full-call validation remains;
   synthetic QK callbacks are not evidence of QBS protocol correctness.
2. Bind an independent full-call experiment to real captured Q/K/V, actual QBS
   commands and the current admission/query preparation path. Do not mutate
   the two in-flight Prefill workers' pinned sources.
3. Measure full-call ABBA on VCS: same ELF/image and data, strict source/image
   identities, output/flags/guards, protocol checker and unchanged command work.
   Include admission, preparation, QK, online PV and normalization in the ROI.
4. Check more than one head/context shape. Register assembly, output traffic,
   extra validation and changed LMUL can outweigh the eliminated scratch load;
   fewer memory operations alone are not proof of speedup.
5. Promote to shared software/GGML only after reproducible benefit, preserving
   current fallback for unsupported inputs. Keep separate QK commands,
   processed V rows, decoder calls and eliminated scratch bytes: the candidate
   still decodes V even though it no longer invokes the old decoder callback.
