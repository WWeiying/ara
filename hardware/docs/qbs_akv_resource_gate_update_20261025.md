# Shared-Resource Acceptance Update

This is a successor to the frozen resource/runtime acceptance documents. It
does not supersede the full scope in `qbs_akv_efficiency_execution.md`. No
canonical RTL promotion, synthesis, PPA measurement or model-level speedup is
claimed by this update.

## Completed Ordinary RVV Regression

The worker in `verification/out/ordinary-rvv-unified-20261025-01/` completed
with checked PASS. A separate offline acceptance review is required before
promoting its receipt. The original ELF is unchanged:

`1be2be23ec376dc119c317687fb4dc4614acc11ee14d3303ec647882fd9beddd`.

| Trial | Actual path | Original cycles | Unified-resource cycles |
| --- | --- | ---: | ---: |
| 0 | Ordinary RVV | 245497 | 245497 |
| 1 | Generic AKV | 81047 | 81047 |
| 2 | Paired-head AKV | 58341 | 58341 |
| 3 | Paired-head AKV | 58310 | 58310 |
| 4 | Generic AKV | 80523 | 80523 |
| 5 | Ordinary RVV | 245088 | 245088 |

The worker compares all 3864 hardware command records, corresponding output
checksums and FCSR/VCSR, and the original on-chip 512-output checks. Ordinary
RVV is an actual separate implementation, not native AKV with a software
optimization disabled. It is not the stronger tiled-RVV comparison and is not
a whole-model measurement. Equality here establishes resource-regression
behavior, not an additional speedup caused by resource sharing.

The shared-reader-only Q4/Q8 real strided-cache workers also completed. Their
independent audits must use QBS records and the quantized fixture's original
checker, not the F16 Decode/Prefill-only auditor or AKV record counts.

## Held-AR Error Gate

Build `reader-held-ar-build-20261025-01` remains a preserved FAIL: its baseline
VCS compilation returned zero, but a standalone compile-log checker rejected
the full-SoC command header and two inherited monitor diagnostics. Its
candidate image and functional simulations were not run.

Commit `d725c9d1` adds a local full-SoC adapter. It verifies the complete VCS
argv and admits only the two exact historical monitor warning blocks, bound
to source hashes, line, port names, order and count. The remaining diagnostic
stream still passes through the original TLB warning admission. New warnings,
changed blocks and nonzero compiler exit status reject. The legacy checker,
testbench and RTL are unchanged. Parent testing passed all 28 host tests and
independently accepted the actual failed build's log without modifying it.

Fresh prepare05 SHA256:
`7f6e32ea7dc30a5a8cac4f30b2ab2089620792229aedb7e6df12022e9abc741b`.
Preflight03 passed without launching a compiler. Fresh build02 is owned by
`reader-held-ar-build-20261025-02.service`; preparation is not proof that VCS
has started, and a successful build is not a functional PASS.

After both images build, review their ELF, source graphs, compile admissions
and image pins before executing the 71-command paired gate. It must observe
real held-AR/error/drain/recovery signals and retain original output checks;
it does not emulate a Linux page-fault/MMU environment.

## Remaining Promotion Conditions

1. Independently audit terminal real-input workers and preserve raw evidence.
2. Pass the held-AR fault/recovery gate on both images.
3. Finish or audit all live consumers before changing their pinned sources.
4. Promote RTL, Bender, standalone generators and measurement interfaces as
   one coherent change, then validate the actual canonical source graph.
5. Preserve legacy physical-flow organization support. The first static
   compatibility proposal unnecessarily requires a Q64 library in the old
   split-storage standalone flow; it is not approved for application as-is.

The quantitative KV attribution workers remain distinct from these resource
gates. Their H/S/B comparison is needed to decide the next performance change;
resource equivalence does not close that requirement.
