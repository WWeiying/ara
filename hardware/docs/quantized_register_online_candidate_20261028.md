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

## Full runtime adapter validation

`register_pv/runtime_candidate.c` includes the current shared
`runtime_strided.c` implementation with independent exported symbols. The only
redirected operations are selection (actual CSR capability guard followed by
the unchanged selector) and the online schedule. K panel gathering, query
quantization callbacks, descriptor construction, executor dispatch, workspace
layout and terminal error handling are inherited, not separately rewritten.
Production callers still call the original entry; this adapter is experimental.

The adapter selects the V head using `kv_head * head_stride` and subtracts
that offset from the tensor extent before constructing the raw view. This is
important for interleaved layouts: total tensor bytes cannot be reused as the
remaining capacity after advancing the base. Successful `value_decodes` counts
processed Q8_0 rows even though the original decode callback is bypassed. An
error report is partial and must not be used for performance accounting.

The full adapter has passed 288 QEMU/reference-executor cases:

| Axis | Values |
|---|---|
| K encoding | Q4_0, Q8_0 |
| D | 32, 96, 128 |
| Query heads per KV head | 1, 3, 6, 7 |
| KV heads | 1, 2 |
| Visible prefix | 1, 31, 32, 33, 64, 65 |
| Layout | Token-interleaved K and V, padded output |

Checks cover bit-exact full output (including untouched padding), FCSR,
unchanged QBS command counts, K panel counts and copied bytes, query quantizer
counts, completed groups and processed V rows. The legacy V callback count is
zero for the candidate. A first-command injected execution failure returns a
terminal execution error without fallback; malformed extent returns fallback
before quantization, commands or output writes. A separate VLEN=256 boot also
rejects without those side effects.

Evidence: `verification/out/register-runtime-reference-20261028-01/result.json`,
state PASS, both guest exits zero, source identities unchanged.
ELF SHA256:
`9ec031a7034e8aa2e504ad2bfc6af176c65b3e0fe22e1225dc91ab4d5a62ad42`.
Input-pins SHA256:
`5fee3773ecdbfb3fbcb351840fbd156227eab12f1da945cde8f0aca100980540`.
Reproduce with `run_online.py --runtime --execute-reviewed --output <fresh-dir>`.

This fixture uses deterministic integer-valued queries and a test quantizer,
with the independent QBS descriptor reference model as executor. It does not
execute custom instructions on RTL and is not real GGML/model validation.
Real captured-data ABBA remains the next gate; no speedup is claimed here.
