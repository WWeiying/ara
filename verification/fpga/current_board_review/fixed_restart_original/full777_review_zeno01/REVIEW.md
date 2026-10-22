# Full777 Independent Preparation Review

Decision: **NO_BLOCKER_SOFTWARE_PREPARATION_ONLY**. No DUT/launch approval.

## Findings

- No blocking software-conversion issue found in the reviewed preparation.
- The earlier aggregate-only backend count allowed dropping a whole owner alloc/done pair. Reported directly to Aquinas; checker `f2f7cc2979f3dc596522b5df37fb7feb8b2d9f3079f657c8aeef5f4034dc1001` now requires all 3885 memory owners. Independent focused positive and whole-pair-drop negative confirm the correction.
- No final software READY or worker-plan READY existed at this review snapshot. `PREPARED.json` is the earlier pre-reference status; the later reference receipt and bridge must be bound by the eventual sealed release. This report does not fill in an absent READY or authorize execution.

## Passing Evidence

- Independently reconstructed the original loop's first 777 tuples, not a reordered/reduced matrix. All are seed0/op0; last trial776 is VL512/mask0/vstart256/control0.
- Independently reconstructed original RNG inputs, mask128, old destination and signed fractional multiply rounding/sticky saturation for every call. All 399378 bytes (397824 result + 1554 guard) agree with calls.json and actual SoC/Spike ELF ROM contents.
- Original helper is **24 instructions / 90 bytes**, not 24 bytes. Exact encoded body occurs in the archived original ELF (SHA ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc); all four helper instruction sequences also match the previous prepared ELFs.
- `AGNOSTIC_POLICY=0` and actual `tu,mu`: no agnostic-tail allowance was lost. Oldvd is 0x5b. The 64 scalar 8-byte accesses plus bytes512/513 cover the same 514-byte span; `out+1` and both guards remain unchanged. ROM deduplication (54 rows) changes neither call order nor expected bytes.
- Fresh-init coverage requires every byte0..513, current sentinel contents, complete original RNG/mask store order, helper argument context, exact helper PC/opcode sequence and all 66 oracle read addresses/widths/values. Relevant RVFI addresses, byte enables and store operands are checked; unknown scalar operands are not defaulted to zero.
- Returned vstart=0 and expected sticky vxsat are checked per call; vxrm/vxsat restore operands are matched to each call's saved CSR reads. **No final CSR readback claim**: reports explicitly retain that limitation.
- Verified 163 source/input pins and actual command/log hashes for 16 exit receipts. Original/optimized/scalar Host receipts are rc0; all nine mutation receipts are rc1. Existing Spike receipt is actual rc0 / 19.402s, firmware790055; existing bridge covers777 calls,51282 reads,18648 helper instructions,1472 RNG stores,8758 mask stores.
- SoC bss_end=0x80009088, footprint37000B; stack_top=0x800ffff0, gap1011560B. Spike footprint45456B, gap1003104B. Both satisfy the unchanged 64KiB linker stack reserve. ROM payload30411B; out is 8-byte aligned. This is a static allocation bound, not a measured stack high-water mark.

## Scope

Only the genuine first777 of original10752 are reviewed. No full-parent closure, original Linux ABI replay, SoC/DUT PASS, final CSR readback or launch authorization. Reviewer did not rebuild, run Spike/DUT, or reparse the reference raw log. Only independent review files were created; author/source/RTL files were untouched.

Detailed hashes and actual evidence counts: `evidence.json`.

