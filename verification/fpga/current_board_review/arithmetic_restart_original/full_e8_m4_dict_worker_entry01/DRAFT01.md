# Full e8/m4 4095 Worker Entry: Narrow Static Review

Status: ENTRY_PENDING. This is not launch admission or DUT acceptance.

Reviewed the current `full_e8_m4_dict_vcs_m9_plan01/checker.py`,
`replay.py`, and `host_records.py`, plus the actual imported runner and
OwnerObserver interfaces. No Host/reference/CSV replay or simulation was run.
FP700 and the old whole-register prepared01 were not re-audited.

## Concrete Finding

The reviewed checker constructs `init_stores` as a list of tuples. JSON
serialization converts the tuples into lists. Both `replay.validate()` and
`validate_reset()` compare the reloaded spec directly against
`specification()`, so an otherwise correct disk plan would be rejected.
This is a finding in this new draft, not attribution of the old whole-register
precheck to the e8/mf4 DUT. Zeno was notified to make the new spec JSON-native
and cover the actual disk round trip before sealing. No old file needs changes.

## Confirmed Wiring

- Full 4095 continuous calls, 514 fresh output bytes per call, 64 aligned
  word reads plus a final two-byte read; both original guards remain checked.
- Original seed/group initialization reuse is explicit; output initialization
  remains mandatory for every call, not a partition reset.
- Five compulsory memory owners per call: 20475 total. Nonempty target
  eligibility is `vstart < vl`: 2610 required targets including 117 op24
  memory targets. Imported coverage requires each eligible owner's completed
  alloc/done pair, not merely an aggregate event count.
- Full original helper PC/code windows, source arguments, returned vstart,
  actual scalar read value/address/BE, startup reset authority, and CTRL raw
  zero exit are checked. No new division/exception waiver was introduced.
- Runtime artifact checking uses `case.id`; historical source name remains
  distinct. The imported worker persists numeric child outcome before
  postchecks and retains abort/fresh disk-plan gates.
- `common.BAD` already explicitly matches `RVV_MATRIX_FAIL`; its underscores
  do not evade the raw failure veto.

## Remaining Entry Work

Await Zeno's actual Host results (including full positive stream, removal of
an op24 required pair, fresh interval/tail deletion, and JSON round trip),
final prepared/dryrun plan, and collector/launch files. Review only their
narrow delta and exact hashes before final entry binding. Zeno remains the
sole authorized launcher after NO_BLOCKER; this draft does not authorize it.

Reviewed draft hashes:

- checker.py: `0f09dbabf040d9e382766976b1271194e775ddf5e3cd92943c83e532f41f6281`
- replay.py: `1c8bd500fb8e7c04248d0f2650df0dc7975556ffc59f12bf03de5a66848aa839`
- host_records.py: `8421c62a818492a00add5e5acd945cd5cbb68f17e4d0eaee38ca47cf9469caac`
