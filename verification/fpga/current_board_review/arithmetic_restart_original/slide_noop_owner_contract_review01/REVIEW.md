# Frozen M9 slide-up no-op owner contract

Static review only. No active CSV read, DUT query, reference/Host execution,
checker modification, recovery parse, or service action was performed.
The reported e8m4 terminal failure is upstream evidence, not independently
reparsed here. Existing failures and running sealed workers must remain intact.

## Confirmed contract mismatch

Frozen M9 `sources/hardware/src/ara_dispatcher.sv` SHA256
`c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d`:

- Lines 2330-2340 decode VSLIDEUP.VI with unsigned five-bit offset and set
  `null_vslideup` when offset >= architectural VL. The VX counterpart is at
  2080-2091, with an additional high-offset-bit test.
- Lines 5349-5351 exclude this architectural no-op from layout maintenance.
- Lines 5970-5978 acknowledge successful no-op instructions with
  `ara_req_valid=0`; lines 5997-6001 reset vstart on successful response.
- VSLIDEDOWN is not covered by `null_vslideup`. Masked-off operands alone do
  not justify removing an otherwise required arithmetic target owner.

`full_e8_mf2_packed_vcs_m9_plan01/checker.py:229` and
`full_e8_m8_block_vcs_m9_plan01/checker.py:221` require every target with
vstart < VL to have a backend owner. Their `owner_counts()` and final coverage
assertions repeat this predicate. This is too strict for the exact original
op19 `vslideup.vi v24,v8,2,v0.t`, instruction 0x38813c57.
The original mf2 assembly lines 292-307 retain full setup, target, returned
vstart read, full-capacity result store, and return.

## Exact static impact

Both source models use three seeds, op19 kind1 (one start=0), seven VL choices
including 0,1,2,3, and three mask modes. Thus VL1 and VL2 each contribute
three no-op calls per seed: 18 targets per complete4095 sequence. VL0 was
already optional under the existing predicate. This is source-loop arithmetic,
not an executed owner recount or a statement about current DUT completion.

Affected zero-based call ordinals are 1200..1205, 2565..2570, 3930..3935;
one-based ordinals are each +1. The first is seed0/op19/VL1/start0/mode0,
consistent with the upstream first failure. Both mf2 and m8 retain this order.
Predicted corrected minimum is 20475 memory owners + (2610-18) required
targets = 23067. All 117 nonempty op24 memory targets remain mandatory.

## Narrow future offline correction

Only after a CSV is closed and recovery is authorized, bind a new observer to
the original plan, exact ELF/helper instruction and frozen dispatcher hash.
Derive target eligibility from actual helper decode plus the model VL/vstart:
ordinary nonempty target remains required, except exactly decoded VSLIDEUP.VI
with its unsigned offset >= VL. Do not waive all slide operations, all op19
calls, masked-alloff targets, configuration history, or memory helpers.

Keep lossless generic transport and actual-owner ID/pair accounting; optional
no-op status is not permission to discard malformed events. Keep all 13 helper
instructions, original inputs/init/mask freshness, all output bytes/guards,
actual vstart return, and every existing CSR/error/exit/pin veto unchanged.
These helpers do not add a flags read: retain existing CSR coverage without
claiming a new measured flags readback. No-op result and vstart remain checked.

Focused successor negatives should still reject deleting op19 VL3 owners,
op20 VSLIDEDOWN owners at VL1/2, op24 owners, or any of the five memory-helper
owners; reject wrong instruction/offset/ID and altered no-op output/guard or
returned-vstart. Legitimate VL1/2 no-owner targets should pass only with the
entire original oracle and lifecycle otherwise intact.

No recovery was performed. Original worker terminal labels must not be
rewritten; any future acceptance is a separately recorded offline result with
real child outcome preserved, never a VCS rerun.

## Read identities

- mf2 checker: `cdf3dbb42e6c9d4ac72b5f57c9727ad660e441776064752aea6aee875bf85652`
- m8 checker: `9c01b3a5064bd820021ea13e099b75e6bda814cc8a3428a5e4de7085a3307c99`
- mf2 source model: `66abb0a8824616530e188b34634ade72416f87c6359a8dd7094b492e40a04019`
- m8 source model: `7013a988e91a323fe100919343ea48733ad885b7a6d615ca52b605d0e3a0287e`
