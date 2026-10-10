# Bounded FPnew upstream correctness absorption, 2026-10-09

This directory owns the directed tests and evidence for five audited FPnew fix
groups. Work is confined to `ara_dsa_signoff_integration`. The parent agent owns
dependency patch bundles/registry updates; this work does not edit those files,
MVP, Ara RTL, or the main worktree.

## Independent reference and actual DUT

The arithmetic oracle calls the installed Spike SoftFloat shared library through
typed FFI. `softfloat_detectTininess=softfloat_tininess_afterRounding` is set for
each operation; rounding mode and exception flags are reset for each call.
Results are bit-exact, and all five flags (NV/DZ/OF/UF/NX) are compared.

The library is copied into each run's `inputs/` and hashed before generating
vectors. Its SHA256 is
`dd2349915d26aacb040f24e4d576c8907ad42074797762a7d54b0cc028d59a77`.
This installed Spike build exports actual `f16_to_i8/ui8` saturating conversion
functions. The INT8 oracle does not truncate a wider conversion to manufacture
the reference. Unit tests check signed/unsigned saturation and NV independently.
INT8 cases compare the packed destination byte and all flags; they do not claim
scalar 64-bit sign-extension coverage for an INT8 instruction.

VCS instantiates the real `fpnew_cast_multi`, `fpnew_fma_multi`, three actual
`fpnew_fma` H/S/D instances, and `fpnew_divsqrt_th_64_multi` including the real
vendored C910 divider. There are no forced DUT values and no behavioral arithmetic
replacements. All source/header files and the fixture are frozen under each
output directory, along with the compile command, executable hash, oracle cases,
raw results, internal FMA probes, simulator logs, and independent host audit.

## Upstream chains and local adaptations

| Group | Official commit | Local action |
|---|---|---|
| I2F OF/NX versus NV | [`2c794772`](https://github.com/openhwfoundation/cvfpu/commit/2c7947726a0859c08cc27cbbd45662424dedb41e) | Correct only FP-result status construction |
| Cast UF boundary | [`cb3f0e59`](https://github.com/openhwfoundation/cvfpu/commit/cb3f0e596a445188cc9fe73994e11fd3dc97d7a7) | Include tiny unbounded-exponent results that round to min-normal |
| FMA UF boundary | [`822047af`](https://github.com/openhwfoundation/cvfpu/commit/822047af5f05515994dd433156be3a99c2773727), then [`a6af6915`](https://github.com/openhwfoundation/cvfpu/commit/a6af691551ffbd76d5d9cf30774d3295a41615e4) | Apply both boundary detection and transaction-aligned RM; adapt narrow-format bit selection |
| C910 UF boundary | [`f322dd95`](https://github.com/openhwfoundation/cvfpu/commit/f322dd95b81d9a9e4df40d72bea84ce3dccf009c) | Correct `ex4_cor_uf` in `ct_vfdsu_pack.v` |
| THMULTI flush | [`bb0e8bbb`](https://github.com/openhwfoundation/cvfpu/commit/bb0e8bbbddaf47f1feb3e37af8320c94c8e99a78) | Flush clears launch tokens and retained SIMD done state |

The local negative signed boundary, negative unsigned wrap, infinity conversion,
FP16/INT8 enabling, C910 rounding, and wrapper holding fixes are preserved.
The upstream I2F commit also changes regular F2I NV logic. Locally all F2I overflow
already selects the invalid-only special-status path, so that redundant change
is not imported. No new pipeline stage, architectural result latency, or normal
ready/valid behavior is introduced.

### Why a rounded normal result can still raise UF

After-rounding tininess is evaluated at destination precision with an unbounded
exponent, not simply by reading the exponent of the final finite-format encoding.
For example, FP64 `0x380fffffe0000000` converted to FP32 under RNE produces
`0x00800000` and UF|NX (`0x03`). The old cast reports only NX (`0x01`). Both
result and flags are taken from independent SoftFloat, not the RTL expressions.

### Multiformat FMA: direct copying of upstream is insufficient

The initial direct backport raised UF incorrectly on 48 H/S multiformat cases
(`out/candidate01`), while the single-format versions passed. In this local
super-format datapath the bit immediately below the destination's round bit is:

- For a narrow destination: `final_mantissa[SUPER_MAN_BITS-MAN_BITS-1]`.
- For the full-width destination: `sum_sticky_bits[2*SUPER_MAN_BITS+4]`.

Using `sum_sticky_bits[2*MAN_BITS+4]` for a narrow destination reads a different,
lower part of the super-format tail. This is a layout adaptation, not a change to
the IEEE rule or the oracle. Measured example: half `0x03fe * 0x3c02` under RNE
returns `0x0400`, flags NX only. The probe records pre=`0x03ff`, rounded=`0x0400`,
RS=`11`, final mantissa=`0x1ffff800000000`, tail=0. The relevant bit is in
`final_mantissa[41]`, whereas the unadapted tail bit is zero.

A separate discriminating FMA input is
`0x0300 * 0x3bff + 0x0100` in half precision. It is exactly min-normal minus
3/8 of a subnormal ULP: RNE returns min-normal with UF|NX; RUP returns the same
encoding with NX only. The test changes the live input RM after acceptance,
so using `rnd_mode_i` instead of the stored `rnd_mode_q` is observable.

### Flush evidence is reported precisely

The old actual DUT leaves `op_sel=1` after a flush at launch delay 0, and leaves
`unit_done_q=1` when a vector result is canceled while waiting for SIMD peers.
The test verifies these actual registers, then checks the next DIV result and
absence of ghost outputs. This campaign reproduced stale cancellation state;
it did not reproduce an architectural deadlock. Do not describe the old run as
a measured hang merely because the official upstream issue describes a hang.

## Test structure

- H/S/D MUL, FMA, DIV and SQRT; cast D-to-S and S-to-H boundaries.
- Signed I32 and explicit unsigned I32/I64 to H/S/D, including overflow.
- Five architectural rounding modes, both signs, subnormal/normal boundaries,
  exact cases, zero, infinity, qNaN/sNaN, divide-by-zero, and nonzero FMA addends.
- Existing negative signed boundary and negative unsigned F2I regressions.
- Three cycles of held output per sequential transaction, checking result,
  flags, tag, and valid stability.
- Real overlapping streams through cast and fixed/multiformat FMA with changing
  RM, periodic backpressure, strict ordered tags, and measured in-flight depth.
- Flush at launch delays 0/1/2/3 and at retained SIMD completion, each followed
  by a checked DIV. Accepted-work reset and fresh-result checks for all six DUTs.

These are functional checks, not line/toggle/FSM coverage or full IEEE signoff.
BF16/FP8, stochastic rounding, unboxed scalar frontend behavior, the quarantined
MVP backend, every pipeline parameterization, and full-SoC instruction execution
are outside this fixture. Normal-path latency comparisons are unit measurements,
not a claim about whole-kernel performance or PPA.

## Reproduction

Use host VCS; no container, URG, Verilator, ZCC or synthesis is needed. Output
directories must be new. From the repository root:

```sh
python3 -m unittest discover -s verification/fpnew_upstream_20261009 -p test_runner.py -v
python3 verification/fpnew_upstream_20261009/run.py \
  --output verification/fpnew_upstream_20261009/out/NEW_CANDIDATE --flush --stress
python3 verification/fpnew_upstream_20261009/run.py \
  --output verification/fpnew_upstream_20261009/out/NEW_BASELINE --flush --stress \
  --rtl-snapshot verification/fpnew_upstream_20261009/out/baseline01/inputs
```

`--rtl-snapshot` copies the archived source; it never replaces live RTL. Old
failing logs remain unchanged. VCS may return zero even when an SV failure is
reported, so acceptance requires the complete trace, exact IDs/tags, independent
result/flag checks, stress/flush markers, and absence of fatal/error diagnostics.
See `RESULTS.md` for the final paired measurements and hashes.
