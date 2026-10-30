# One-query F16 D128/GQA6 QK PANEL4 candidate

## Scope and selection

The new helper is `akv_v2_compute_scores_f16_d128_gqa6_panel4(query, score,
tile_tokens, query_row_stride_bytes)`. This is one Query position with six GQA
heads, not two-query Prefill. Six score rows keep the existing 64-float stride.
Valid token counts are 1..64, derived by the existing validated plan/tile loop.
Query rows retain the caller's byte stride. Platform prerequisites are the
existing native AKV-v2 four-lane/VLEN1024 setup with scalar/vector F16 support.

`akv_attention_execute_v2_with_features_native()` selects once before its tile
loop. Exact environment value `AKV_QK_PANEL4=1` is required; unset, `0`, empty,
other strings, or an absent environment provider keep singles. Only F16 D128,
six-row plans reach the capability query. The existing extended capability
decoder validates all four info words; F16, D128, at least six Q rows, valid
token-axis/tail support and PANEL4 must be advertised. A missing/invalid
capability falls back to the existing singles helper. Segmented D256 returns
through its pre-existing path before this selection. Prefill is unchanged.

`getenv` is a weak GNU reference so existing freestanding applications without
libc/environment support continue to link and default OFF. A bare-metal ABBA
harness can supply `char *getenv(const char *)` returning `"0"` or `"1"` for
`AKV_QK_PANEL4` from a per-call test mode (NULL for other names). Mode changes
must occur between complete calls; there is no process-global cached policy.
The build gate exercises the weak-missing-provider case as well as a provider.
An environment provider must not concurrently mutate its returned string.

## Arithmetic and register mapping

Accumulators remain EW32/m2 at v0, v2, v4, v6, v10 and v12, physically spanning
v0-v7 and v10-v13. New column groups alternate aligned v16-v19 and v20-v23.
Using an LMUL4 destination at v8 would overwrite v10-v11 and is forbidden.
Each command exposes dimensions d..d+3 in successive registers. Exactly six
`vfwmacc.vf` execute for d, then six for d+1, through d127. The source/query
half values, F32 accumulator precision, dimension order and score stores are
unchanged. No reduction, new FP conversion, query duplication or Q2 scheduling
is introduced. Runtime VL remains token count under EW16/m1, then EW32/m2
for the six final score stores. The scalar/FPR/vector registers used are
caller-saved under the existing standard scalar calling convention.

The documented shared Decode workload in
`hardware/docs/akv_refill_overlap_implementation.md` uses two KV heads and two
64-token tiles: 512 singles column commands become 128 PANEL4 commands, while
the 768 widening vector FMAs per six-head tile, logical K values and external
Q/K/V traffic stay unchanged. With unchanged two FULL/two REFILL/two RELEASE
and 256 V-row loads, the predicted command count is 390 instead of 774.
These are static work counts, not measured cycles. Dispatch savings can be
offset by replay/VRF write or operand-port pressure; no speedup is claimed.

PV, softmax, FULL/REFILL/RELEASE lifetime and all pre-existing assembly helpers
are unchanged. `AKV_REFILL_OVERLAP` remains OFF in the new object build; this
candidate does not enable overlap or alter its existing compile-time policy.

## Bounded gate

```sh
python3 verification/akv/qk_panel4_build.py \
  --before verification/out/akv-qk-panel4-sidecar-20261023-01/before \
  --output verification/out/akv-qk-panel4-sidecar-20261023-01/build
```

The builder produces GNU RV64GCV+Zfh+Zvfh `attention.o`, `native.o`, and the
actual existing application's amalgamated `shared-runtime.o`, with REFILL
overlap disabled. Only the self-contained assembly is linked to an ELF for
static inspection; no native executable is run. Exact commands, dependency
source hashes, tools, objects and disassembly are pinned in the result.

The host selection test compiles a verbatim extracted production selector
against the existing production capability decoder, with mocked environment
and info reads: 39 provider cases plus one absent-provider case. This is not
execution of the complete native RVV TU. The builder checks the real native
object references both helpers and weak getenv, and verifies that reverting
only the added selector/declaration/Decode call restores the archived C file.

The disassembly checker interprets the narrow instruction subset used by both
QK helpers against an independent small-integer matrix. It tests all token
tails 1..64 and Query strides 256/320/512/768, checks score-tail canaries, and
requires the exact (dimension, head) FMA sequence and 128/32 custom commands.
All fixture products and partial sums are exactly representable, so this
checks mapping/order, not exceptional FP semantics. Four deliberate register,
query-pointer and store mutations must fail. It also compares every existing
assembly symbol body against the pre-edit object byte-for-byte.

No VCS/QEMU/Spike simulation or performance gate is launched. Before enabling
the opt-in, the parent must run the actual shared Decode path OFF/ON with the
same fixed-address real inputs and unchanged tolerance, checking outputs,
FCSR/VCSR, native command selection/counts and canaries. ABBA should retain
the common environment lookup and include the once-per-call capability query
cost for ON. Add native tail, query-stride and exceptional-FP cases; the static
integer matrix cannot certify rounding/flags or RTL hazards.
