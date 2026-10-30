# Experimental paired-head Attention helpers

Isolated assembly candidate, not linked by production runtime or GGML. No
environment selection, context lifecycle commands, capability query, or fallback
is implemented here. Preserve the optimized D128/GQA6 path in any later dispatch.
No RTL numerical or performance acceptance is claimed by host/object checks.

## Caller contract

```c
void akv_experimental_qk_f16_pair_panel4(
    const uint16_t *query, float *score, uint32_t tokens,
    size_t query_stride_bytes, uint32_t head_dim);
void akv_experimental_pv_f16_pair(
    const float *score, uint16_t *accumulator, const float *old_scales,
    uint32_t tokens, uint32_t head_dim);
```

Exactly two real heads share one KV head/tile. This is not two query positions
(Q2), and must not be called on a phantom odd head. The upstream caller validates:

* rv64gcv_zfh_zvfh, four-lane VLEN1024 native platform; D is 64, 96, or 128;
  tokens is 1..64 and does not exceed the currently resident token count.
* Valid enabled token-axis context with appropriate D/row/tail capabilities;
  PANEL4 capability additionally required for QK. Same resident KV tile remains
  owned throughout all paired-head calls, under the existing operation lock.
* QK query base/stride are at least halfword aligned; stride >= 2*D. Both rows
  contain D valid F16 values. Score base is float aligned, rows stride256B,
  with space for two 64-float rows. Only tokens elements per row are written.
* PV score rows stride256B; two old scales are contiguous float-aligned F32.
  Halfword-aligned accumulator rows stride512B, even for D64/D96; only D F16
  elements per row are read/written. The caller supplies nonoverlapping writable
  outputs and inputs, no pointer overflow, and no concurrent buffer mutation.

No checks occur inside the leaf: invalid D can select the wrong V encoding,
invalid lengths can truncate VL or overrun memory. Negative arguments must be
rejected before native issue by future runtime preflight.

## Arithmetic and register contract

QK saves a4=D into t5 before using a4 as a query pointer. Accumulators v0:v1
and v2:v3 are FP32; v8-v11 hold four consecutive F16 K columns. For each
dimension, head0 then head1 receive vfwmacc before moving to the next dimension.
Each head retains the original dimension0..D-1 order and zero initialization.

PV uses F16/m2 v0:v1 and v2:v3, with V in disjoint v8:v9. Each old scale is
converted using fcvt.h.s and multiplied once into its own accumulator, then each
score is converted by fcvt.h.s and applied by F16 vfmacc in token0..tokens-1 order.
It does not widen the PV accumulator, fuse its initial scale, or reassociate sums.
The instructions use current frm; they do not clear incoming sticky fflags or
write vcsr. The union of per-head exceptions should match singles, but exact
rounding/exception behavior requires actual native RTL testing, not this checker.

Both leaves are call-free and stack-free, touch only scalar/FP caller-saved
registers and caller-saved vector registers under the ordinary C ABI, and leave
vl/vtype changed. No vector calling-convention variant is declared. No live
vector state may be carried across a C call. Fences/lifecycle and normal-store
drain remain caller responsibilities, exactly as for canonical compute helpers.
There is no atomic whole-Attention rollback: do not catch a fault after partial
issue and retry through generic software on possibly modified buffers/context.
FULL/REFILL/RELEASE remain once per existing operation/tile schedule, not per pair.

## Static work, not measured speedup

For H heads, D dimensions and T tokens, current generic QK issues H*D singles;
pairs issue floor(H/2)*(D/4) plus (H%2)*D if the odd head uses existing generic
singles. ceil(H/2)*(D/4) would require a separate one-real-head PANEL4 path.
PV uses ceil(H/2)*T commands with generic odd fallback versus H*T currently.
FMA work stays H*D*T for each of QK and PV. Per-head update order stays unchanged.

For H2/D128/T64, QK256->32 commands and PV128->64; combined SRAM-to-VRF
replay64->32KiB. External FULL/REFILL KV traffic is unchanged. For H8, pairing
is not maximal reuse: a wider live-head kernel could further reduce replay but
needs its own register/precision and numerical analysis. No speedup follows from
these static counts alone.

## Independent object checks

```sh
python3 -B verification/akv/paired_heads/build.py \
  --output verification/out/akv-paired-heads-object-20261023-01
```

The new standalone checker interprets a bounded subset of linked GNU
disassembly, rejects unexpected instructions/encodings, validates live register
mapping, load/store addresses, FMA/convert/scale order, and tail/gap canaries.
It uses a separate small exactly representable integer matrix oracle for all
D64/96/128 and tokens1..64, with several Q strides. No reference kernel or
production implementation is used as its numerical oracle. This is not an ISA
simulator: NaNs, non-RNE, exception flags and actual SRAM/hazard/fault handling
remain unverified. No simulation is launched by this build/check entry point.
