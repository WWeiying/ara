# Real Gemma D256 Boundary

One ELF, two calls, one fixed real point: Gemma-3-1B-IT Q4_K_M layer0, all four
query heads0..3 to KV head0, D256, Decode KV17, capacity256, F16 K/V. Exact
captured scale1 is retained, NOT 1/sqrt(D). Original mask and every effective K
are retained; no repeated, cropped or synthetic operands. Original captured
model gold remains authoritative at atol0.004 + rtol0.002*abs(gold).

## Static Conclusion

The D256 QK/PV assembly block, D256 online-softmax/native executor C block and
whole akv_online_internal.h are byte-identical between old validated-software
revision4410dce9368751aa474b2223bcde90144cf2bad9 and current pinned SDK archive
dbe2b78817ef45b912444afcb85ad6e01a2be135. A build records both source identities
and the comparison. This is numerical-source compatibility ONLY, never old RTL
PASS, FPGA acceptance, timing or capability promotion.

The SDK constructs two physical D128 descriptors for one logical D256 plan.
First FULL supplies K-low/K-high and query-low; 64 panel4 column commands cover
dimensions0..255 in order. Token-order maximum updates produce a separate F32
rescale for each token. Vector-exp supplies weights. The sum uses separate F32
multiply/add per token, not a tile reduction. Second FULL supplies V-low/V-high
and query-high. The PV kernel widens F16 accumulator/value, applies F32 rescale
and FMA, then narrows to F16 after each token. Both segments precede RELEASE
and F32 normalization. Resident must not execute for D256.

## Minimal Change

No SDK production, numerical C or assembly is patched. All SDK and common
sources come from git archive; the local dirty native AKV assembly is never a
compiler input. One wrapper converts Q, invokes real Decode/plan/native APIs,
checks exact descriptor mapping, and times the whole call. The second arm is
a small same-schedule ordinary-memory comparator sharing the unchanged SDK
D256 softmax/store; its transpose is included in ROI. This is a test-side
adapter, NOT an accepted strongest RVV baseline or the historical plain-RVV
dot kernel, whose unordered F32 reduction is a different schedule.

The fixed-point independent audit is limited to this one1024-output input.
Pinned Spike SoftFloat supplies exact F32/F16 casts, FMA, rescale, sum and
normalization. The SDK vector-exp polynomial is evaluated using independent
scalar SoftFloat. Target newlib scalar expf is instruction/constant-bound to
the linked libm; only this dataset's nonpositive finite |x|<88 and -Inf inputs
are admitted. Host glibc is not a golden or flags source. A failed exact
schedule or original model tolerance stops preparation, never relaxes it.

## Evidence

Both calls compare every raw output against independent exact gold and every
output against original model tolerance outside ROI. Query/input/gold hashes,
outer guards, inactive workspace heads/tokens, VCSR5, vstart0 and incoming
sticky DZ8 are checked. Natural flags are computed, not copied from old RTL.
Only first64 diagnostics per call are printed. Native work must be two FULL,
64 panel loads,34 row loads and RELEASE:101 commands,2048 query external
bytes,17408 KV external bytes,17408 replay bytes. QK and PV each do17408 FMAs;
vector-exp does544. Each ROI must account for35360 accepted native F32 FMA
elements and zero Resident. Entry PCs, exact custom allocation order and CSR
records are ELF/pin bound. Parent independently checks protocol and image.

## Build

```sh
env -u LD_LIBRARY_PATH python3 -B verification/performance/operator_eval_20261115/d256/prepare.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_d256_prepare_20261115_gemma17_01
python3 -B verification/performance/operator_eval_20261115/d256/test_d256.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_d256_prepare_20261115_host_tests_01
```

No VCS, Spike execution, hardware compile, SDK edits or commits. Parent timeout
is bounded at10800 seconds. No context/model matrix, features, quantized KV,
Linux/board admission, Resident performance or end-to-end claim is prepared.
