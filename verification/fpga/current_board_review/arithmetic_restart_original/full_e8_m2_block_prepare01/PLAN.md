# e8/m2 Full4095 Software Preparation

Status: source review pending; no Host/compile/reference/DUT yet.

Original campaign rvv_extended04 rvv_matrix_e8_m2, recovery22 binary-equivalent
C reconstruction (not recovered original C bytes and not a Linux execution).
Original Linux ELF SHA256 fe193c889801184a3144895f4817f0e9e6a9dfffae3144f6bf5bbcd311a1c0c6.
Original .S SHA256 4e73c13c43d558cf7a4102590197abcd57db9a48e3cd15e373565207116f2237.

CAP256 follows actual e8/m2 helper at VLEN1024: physical registers2/full256B,
vtype1, actual vlm32B. All128 software mask bytes remain initialized;
upper96 are zero. Original a/b[1024], out[1026] backing remains.

All3 seeds,25ops and original VL order0,1,2,3,128,255,256,3 masks,
original start formulas and25 kind values yield4095 calls. RNG consumes256
elements per seed, never a smaller-shape seed prefix. Expected1048320 results,
8190guards,4095 returned-vstart checks,53235 helper instructions,135135
output scalar reads are hypotheses to confirm from source/actual machine.
Index b[2]=255 is valid for CAP256 even at targetVL3: read a[255], not zero.
Slidedown uses CAP256 too. No calls or repeated histories deduplicated.

Scalar-only representation:
- Flat4095*33*8=1081080B cannot fit1MiB. Deduplicate exact64B values,
  retain5 uint16 blockIDs per call (40950B) plus64N dictionary and384 mask.
- Fully unroll4 blocks*8word compare, then exact offset256 halfword.
  Tail2 contains result255 plus rear guard; front guard is firstword.
- Initialize32words plus tailSH; memcpy avoids alias/alignment UB.
  No output rounding to320B; zero padding exists only in expectedROM.
- Original byte fallback/diagnostics/counters and returnedCSR checks unchanged.
  Original helper machine bytes must match archive; no compiler-addedRVV.
- Actual linker bound reserves64KiB stack within1MiB; actual frame inspected.

Source gate precedes Host/compile. Host compares originalC and packed for
full4095 plus active/prestart/masked/tail/front/rear/vstart/tail-result/gather
mutations, UBSan and exact protected-page/unaligned footprint.
No reference until independent actual-artifact and exact observer entry review.
One finite rs4000000+quit,120s/768MiB; firmware<=3M required, no automatic retry.
No DUT permission. Future owner contract must retain exact VI2/VL<=2 no-op
qualification and nonempty op24 target ownership, not general slide waiver.
