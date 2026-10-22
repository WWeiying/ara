# Reference Attempt Stopped: Observer Classification Error

The sole authorized Spike execution returned numeric **0**, PID3424126, 8.339231s, no timeout/retry. The offline audit returned numeric **1**, PID3424192, 78.480145s, no timeout/retry. The driver PID3424078 returned numeric **1**, observed directly in command completion (tool chunk384c4c). No DUT or second reference execution occurred.

The original `reference01/STOPPED.json` remains `NOT_ACCEPTED_NO_RETRY`. There is no READY or full-scope acceptance, and firmware-to-HTIF cost is not yet established by a complete independent parse.

## Exact First Failure

`reference01/firstfailure.json`: raw line1437394; firmware-before1437388; last target call3360; PC0x80000d6e; instruction0xc310; `ValueError('RNG exact source-seed owner')`.

This event belongs to setup for source call3361: seed1/op25/VL0/mode0/start0. Call3360 is the preceding seed1/op24 call, not the failing setup's target ordinal.

The sealed software02 `spike/functions.json` identifies PC0x80000d6e as `e32m4_refresh_fp.constprop.0: sw a2,0(a4)`. The sealed `artifact01/spike.json` FP seed1 path identifies its exact event as A[0], address2147759072, size4, value0xc0000000. It is absent from FP seed0 and seed2 paths. Each seed has256 store PCs; seed1 has256 PCs absent from seed0.

The observer's `fp_store_pcs` classification was derived from `self.fp[0]` only. Consequently the real seed1 FP write falls into the RNG branch and is rejected. This is an observer classification defect, not evidence of a numerical or RTL failure. Initial focused FP positives covered only seed0; cache and other negative tests did not expose this omission. Hilbert independently confirmed the static cause without reading raw again.

## Recovery Boundary

No sealed checker has been changed and no second raw parse has run. A narrow independent successor can classify FP writes using the union of the three actual FP store-PC sets, then retain the exact current-row seed event match (PC/address/width/value/order). Required focused tests: all three seed paths, wrong-seed PC, missing first/last store and duplicate store. This must not weaken freshness, permit unknown writes or skip any of the483840 SW. Any subsequent recovery must reuse this same closed raw under separate authorization; do not rerun Spike.

## Evidence Identity

- Entry: `53a0e58f395ec6e6f62acdb444dfa90392fd439d23149b8aaad351c456ef379e`.
- Independent entry review: `cb7a3cf1ddd1a3144fc4af2c715822ef91e3bb6e35b78d13b001f3bf90f7c448`.
- Actual Spike receipt: `e646f31e1edf3a14045087bea957247cd2f3c08d4487c4602a6f97348343749f`.
- Actual audit receipt: `b78f6f526ccb031082b2e5dbff4bfa7f4e2ab04b736d25a9215e8cc98d158ba9`.
- First failure: `7adcbc722fc17fc2afcbff96bcc0fec4b65fb96e879c9b7ddc99ef1c6d9025fe`.
- STOPPED: `34f869f5862e517ee246aed47ab26d1b505c6ec5d321fb89e15b731be8af8725`.
- Closed raw SHA, recorded before the sole audit: `4c570d9e9a24d3b0dd2a50dd865c999ac017a8d918efd17b190c30acc941ceee`.

The driver rechecked input pins on its failure path before publishing STOPPED. No additional raw read was used to establish this static diagnosis; only closed small receipts and sealed compiled/source-event metadata were inspected.
