# Resident PV: Same-Image Complete-Call Comparison

## Experiment

The accepted Qwen3 attention slice has D128, two query heads, one KV head and
137 tokens, executed as tiles of 64, 64 and 9. Both arms use the same native-auto
caller, executable, production-SoC image, real captured data and result format.
The control uses the already optimized rotating-register PV loop, not the
earlier unrotated implementation. The candidate includes ordinary-RVV operand
preparation followed by resident PV. QK, online softmax and normalization are
unchanged. The final explicit drain is included in every measurement.

The order is control, candidate, candidate, control. This is a bounded slice
comparison, not a whole-model, FPGA, PPA or runtime-deployment acceptance.

| Trial | Arm | To return, cycles | Final drain | Complete call |
| --- | --- | ---: | ---: | ---: |
| 0 | Rotating RVV | 34915 | 38 | 34953 |
| 1 | Resident PV | 33103 | 38 | 33141 |
| 2 | Resident PV | 33325 | 38 | 33363 |
| 3 | Rotating RVV | 34290 | 38 | 34328 |
| Mean | Rotating RVV | 34602.5 | 38 | 34640.5 |
| Mean | Resident PV | 33214 | 38 | 33252 |

The complete-call cycle reduction is **4.0083%**, or **1.04176x** speedup.
Comparing the candidate mean only with the last, already warm control gives
**1.03236x**. All individual measurements are retained; the two-trial means are
not a confidence interval or evidence of general benefit across all shapes.

## Attribution

ELF function symbols and the ordered retirement trace identify QK and PV helper
intervals. The PV interval is the union of the wrapper, preparation and rotating
body, so the baseline tail call and candidate preparation are both included.
Every rdcycle marker has the same monitor offset of one cycle.

| Mean interval, cycles | Rotating RVV | Resident PV | Difference |
| --- | ---: | ---: | ---: |
| QK helpers | 9903.5 | 9898.5 | 5 |
| PV helpers, including preparation | 4533 | 3396 | 1137 |
| Remaining caller and drain | 20204 | 19957.5 | 246.5 |
| Complete call | 34640.5 | 33252 | 1388.5 |

These are disjoint retirement intervals, not an additive hardware-stall
breakdown or an isolated causal measurement of each optimization. Exit gaps,
cache state and asynchronous completion can affect the interval differences.
Private FPU service intervals overlap these CPU intervals and must not be
added to them.

Each candidate call executes 35072 useful scalar FP16 FMAs. The T64 commands
accept 1024 SIMD FMA inputs per lane in 1148 controller-service cycles
(89.20%); T9 accepts 144 in 213 cycles (67.61%). Across all three commands the
rate is 2192/2509, or 87.37%. These rates count actual accepted FPU inputs, not
occupied pipeline stages or whole-call FPU utilization. The control does not
have equivalent per-cycle FPU handshake samples, so no control utilization is
inferred from retired instruction counts.

## Correctness And Identity

All four arms have bitwise-identical outputs: 1024 checked FP32 words against
the independent, pinned native reference. Each finishes with FCSR3 and passes
the input fingerprint and output guards. The accepted run also checks:

- Exactly 674 legacy AKV commands and 664 ordered AKV/PV vector allocations.
- Six resident PV commands, replacing 274 control-arm V-row commands while
  preserving useful arithmetic work.
- Actual VRF writes, byte enables, lane-local FMA counts, exception-flag unions
  and final-write acknowledgements.
- Independent passive CPU/backend/AXI protocol checks and post-run executable,
  library, original-source and copied-input identities.

The offline attribution independently repeats the terminal result, numerical,
work, protocol and artifact checks before reading the retirement trace. It
writes only to a new output directory, never into the sealed run.

Evidence under `ara_dsa_signoff_integration/verification/out`:

- Build: `resident_pv_soc_build_20261109_03`.
- Software: `resident_pv_soc_eval_abba_20261109_01`.
- Accepted run: `resident_pv_soc_abba_vcs_20261109_01`.
- Attribution: `resident_pv_soc_attribute_20261109_01`.
- Image SHA256:
  `70fe9cae0fd260e15894f38d2bf5461948723ab445051e402a1ea2bbde183ab4`.
- ELF SHA256:
  `4057d833a46f8b5f402303de68df2a3f67311b990dd3cf466128bbeec7c1baa5`.

VCS simulation took 1058.102 seconds. The directly owned worker completed with
exit code zero. No synthesis or bitstream change was performed.

## Next Gate

Keep the capability zero and production automatic selection disabled. Complete
the independent SoC instruction-boundary matrix and broader complete-call
shape comparisons before considering deployment. QK remains a separate next
step: reuse the same private accumulator storage and existing FP32 lane FPU,
without another multiplier array, bus change or assumption that local service
savings equal model-level speedup.
