# Source/Reference and Checker Review

**NO_BLOCKER** for the prepared e64/sc0 + e64/sc3 source/reference and checker.
READY SHA `8c2f89e677e1cf6148ad3d1013f1598a91ed77506a73266603d956ffe9672e1e`.
Review result SHA `5f5a32bc4294928d7adff06402cb5a659f80e92bdb51a6fe3287105342ecc306`.
No DUT acceptance or final worker-plan review is claimed here.

- Original archived single C/assembly/ELF identities match the manifest and
  confirmed cause13 board failures at their actual target PCs. Both original
  11-instruction helpers plus capacity3 were independently compared against
  the real SoC and Spike ELF bytes: 100 instruction comparisons total.
- sc0: allactive FOF at P-32, requested VL8. The checker checks immediate
  returned VL4/start0, then the original helper restores VL8 before its full
  output store. Only final output indices5..8 are unconstrained. Initial130,
  defined final126, original guards0/9 and full ancillary checks remain.
- sc3: ordinary masked load at invalid page P, VL8 and alloff predicate.
  All130 output elements remain strict typed uint64 0x5b; return VL8/start0.
  Alloff is not treated as VL0: all four memory sites, including this target,
  must have a nonempty completed backend owner.
- `source_owners.Checker` passes all rows unchanged into the complete data/CSR
  checker. Owner VL8 is the reconstructed pre-instruction CSR context, NOT
  a claim that FOF post-state VL remained8. The following actual CSR-read
  retirement checks VL4; the store follows the original VL8 reconfiguration.
- Only the later completion S-ecall is allowed; neither target may raise an
  architectural exception. sc0 shortening is checked separately from traps.
  Four-owner full-pair deletion negatives cover both scenarios in Host12;
  code and actual Host rc0/log were read, not rerun.
- Actual SoC ELF uses CTRL0 store/park, not Spike HTIF1. Checker requires
  completed full oracle and CSR restoration before CTRL0; raw1/17 negatives
  are present. Reference metadata records HTIF1, one S-ecall and actual rc0
  for both unique runs. Counts: sc0 5477 checks, sc3 5481 checks. Reported
  firmware counts172761/172547 include post-HTIF parking; the result separately
  records `firmware_to_htif` to avoid overstating workload.

Evidence check process actual exit0, tool wall time0.480006237s (chunk a68c3b).
Only small source/metadata/ELF inputs were read/hash-checked. No raw trace
parse, repeated Host/reference, live query or DUT launch. The full725 manifest
is bound by its digest, not claimed independently rehashed in this short review.

Future worker must call `source_owners.analyze`, require its exact PASS and
four-owner signature alongside generic protocol checks, durable child numeric0,
raw failure veto and immutable image/input pins. This preserves the existing
worker contract without another source/reference review. Real Sv39 is not
Linux clone/COW/signal equivalence; no physical zero-MMU/AXI activity inference.
